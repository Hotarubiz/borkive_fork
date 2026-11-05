"""botkive-link/3 시험 전송 계층. 요청마다 봉인한 봉투로 등록 경계를 열어요.

일반 부팅은 이 서비스를 만들지 않아요(서버 기본값은 410). 파이썬 표준 라이브러리만 써요.

- 페어링 비밀 S(32바이트)는 네트워크로 오가지 않아요. 사용자가 Botkive에서 받아 플러그인에 직접 넣어요.
- S에서 HKDF-SHA256으로 공개 식별자 kid와 방향별 암호화·MAC 키를 유도해요.
- 본문은 HKDF-SHA256 확장 출력을 키스트림으로 XOR하고, HMAC-SHA256으로 봉인해요(Encrypt-then-MAC).
  봉인 범위(AAD)에 Botkive 공개 출처와 요청 경로가 들어가서, 다른 주소로 간 요청은 쓸모가 없어요.
- 요청 ID(rid)별 처리 결과를 SQLite에 남겨 재전송·중복 요청을 다시 실행하지 않아요.
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from registration_gateway import Grant, Reject
from sync_inbox import MAX_REQUEST, Refused, StorageFull, safe_path

VERSION = 'botkive-link/3'
SALT = b'botkive-link/3'
BLOCK = 8160  # HKDF-SHA256 한 번에 낼 수 있는 최대 길이(255×32)
WINDOW_MS = 300_000
KEEP_SECONDS = 7 * 86400
STALE_PENDING = 120
# 이 동작만 부작용 없이 다시 조회할 수 있어요. 쓰기 실패는 실행 여부가 불확실해요.
SAFE_RETRY = {'snapshot', 'inbox/hello', 'inbox/compare'}
ROUTES = {'snapshot': 'read', 'register': 'commit',
          **{'inbox/' + a: 'prepare' for a in ('hello', 'compare', 'begin', 'chunk', 'chunks', 'finish', 'abort')}}
# finish에는 에셋마다 해시가 실려요(6144개면 약 410KB). 16KB 한도면 에셋 약 240개부터 마지막에 실패해요.
LARGE = {'inbox/compare', 'inbox/begin', 'inbox/chunk', 'inbox/chunks', 'inbox/finish'}
PLAIN_LIMIT, SMALL_LIMIT = MAX_REQUEST, 16384
ENVELOPE_LIMIT = PLAIN_LIMIT * 4 // 3 + 4096
B64 = re.compile(r'[A-Za-z0-9_-]*')
ENVELOPE_KEYS = {'v', 'kid', 'rid', 'n', 'ts', 'c', 't'}


def b64e(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def b64d(text, size=None):
    if not isinstance(text, str) or not B64.fullmatch(text) or len(text) % 4 == 1:
        raise Reject(401)
    data = base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))
    if size is not None and len(data) != size:
        raise Reject(401)
    return data


def expand(prk, info, length):
    out, block, counter = [], b'', 1
    while 32 * (counter - 1) < length:
        block = hmac.digest(prk, block + info + bytes([counter]), 'sha256')
        out.append(block)
        counter += 1
    return b''.join(out)[:length]


def hkdf(ikm, salt, info, length):
    return expand(hmac.digest(salt, ikm, 'sha256'), info, length)


def derive(secret):
    return {'kid': b64e(hkdf(secret, SALT, b'kid', 12)),
            **{name: hkdf(secret, SALT, name.replace('_', '-').encode(), 32)
               for name in ('req_enc', 'req_mac', 'res_enc', 'res_mac')}}


def stream(key, nonce, data):
    prk = hmac.digest(nonce, key, 'sha256')
    out = []
    for index, offset in enumerate(range(0, len(data), BLOCK)):
        part = data[offset:offset + BLOCK]
        pad = expand(prk, b'bkl3-stream' + index.to_bytes(4, 'big'), len(part))
        out.append((int.from_bytes(part, 'big') ^ int.from_bytes(pad, 'big')).to_bytes(len(part), 'big'))
    return b''.join(out)


def aad(*fields):
    return '\n'.join([VERSION, *map(str, fields)]).encode()


def tag(key, header, ciphertext):
    return hmac.digest(key, b'bkl3-tag' + len(header).to_bytes(8, 'big') + header + ciphertext, 'sha256')


def parse_code(code):
    if not isinstance(code, str) or not re.fullmatch(r'bkl3_[A-Za-z0-9_-]{43}', code):
        raise ValueError('페어링 코드 형식 오류')
    return b64d(code[5:], 32)


class LinkKeys:
    """페어링 기록과 rid 처리 기록. 비밀은 이 파일에만 있고 로그·응답에 쓰지 않아요.

    프로토콜 판(proto)마다 페어링 코드가 따로 발급돼요. 한 판의 키는 다른 판 경로에서 찾지 않아요.
    """
    PROTO, CODE = 3, 'bkl3_'

    @staticmethod
    def kid_of(secret):
        return derive(secret)['kid']

    def __init__(self, path):
        self.path = Path(path)
        safe_path(self.path)
        with self.tx() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS link_keys(kid TEXT PRIMARY KEY, secret BLOB NOT NULL,
                library TEXT NOT NULL, source TEXT NOT NULL, rights TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
                created REAL NOT NULL)''')
            # 예전 기록 파일에는 proto 칸이 없어요. 그 키는 모두 botkive-link/3 키예요.
            if 'proto' not in {r['name'] for r in db.execute('PRAGMA table_info(link_keys)')}:
                db.execute('ALTER TABLE link_keys ADD COLUMN proto INTEGER NOT NULL DEFAULT 3')
            db.execute('''CREATE TABLE IF NOT EXISTS link_requests(kid TEXT NOT NULL, rid TEXT NOT NULL,
                digest BLOB NOT NULL, state TEXT NOT NULL, status INTEGER, response TEXT, created REAL NOT NULL,
                PRIMARY KEY(kid, rid))''')
            db.execute('CREATE INDEX IF NOT EXISTS link_requests_retention ON link_requests(state, created)')

    @contextmanager
    def tx(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.execute('COMMIT')
        finally:
            db.close()  # 예외 시 미완료 트랜잭션을 되돌려요.

    def pair(self, library, source, rights=('read', 'prepare', 'commit')):
        rights = frozenset(rights)
        if (not isinstance(library, str) or not re.fullmatch(r'[0-9a-f]{32}', library) or
                not isinstance(source, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,80}', source) or not rights or
                not rights <= {'read', 'prepare', 'commit'}):
            raise ValueError('잘못된 페어링 범위')
        secret = secrets.token_bytes(32)
        with self.tx() as db:
            db.execute('INSERT INTO link_keys(kid,secret,library,source,rights,created,proto) VALUES(?,?,?,?,?,?,?)',
                       (self.kid_of(secret), secret, library, source, ','.join(sorted(rights)), time.time(), self.PROTO))
        return self.CODE + b64e(secret)

    def revoke(self, kid):
        with self.tx() as db:
            db.execute('UPDATE link_keys SET revoked=1 WHERE kid=?', (kid,))

    def lookup(self, kid):
        with self.tx() as db:
            row = db.execute('SELECT * FROM link_keys WHERE kid=? AND revoked=0 AND proto=?',
                             (kid, self.PROTO)).fetchone()
        if not row:
            return None
        return bytes(row['secret']), Grant(row['library'], row['source'], frozenset(row['rights'].split(',')),
                                           float('inf'))


class SecureLinkGateway:
    V, KEYS = 3, ENVELOPE_KEYS

    def __init__(self, gateway, keys, origin, *, clock=time.time):
        if not re.fullmatch(r'https?://[^/\s]+', origin):
            raise ValueError('Botkive 공개 출처 형식 오류')
        self.gateway, self.keys, self.origin, self.clock = gateway, keys, origin, clock
        self.slots = threading.BoundedSemaphore(4)

    def read_envelope(self, handler):
        sizes = handler.headers.get_all('Content-Length', [])
        if handler.headers.get('Transfer-Encoding') is not None or len(sizes) != 1 or not re.fullmatch('[0-9]{1,8}', sizes[0]):
            raise Reject(400)
        size = int(sizes[0])
        if size > ENVELOPE_LIMIT:
            raise Reject(413)
        handler.connection.settimeout(5)
        raw = handler.rfile.read(size)
        if len(raw) != size:
            raise Reject(400)
        try:
            env = json.loads(raw)
        except (ValueError, RecursionError):
            raise Reject(400)
        if (not isinstance(env, dict) or set(env) != self.KEYS or env['v'] != self.V or isinstance(env['v'], bool) or
                not isinstance(env['ts'], int) or isinstance(env['ts'], bool) or
                not all(isinstance(env[k], str) for k in self.KEYS - {'v', 'ts'})):
            raise Reject(400)
        return env

    def open(self, env, route, method):
        found = self.keys.lookup(env['kid'])
        if not found:
            raise Reject(401)
        secret, grant = found
        keys = derive(secret)
        b64d(env['rid'], 16)
        nonce, ciphertext, given = b64d(env['n'], 16), b64d(env['c']), b64d(env['t'], 32)
        header = aad('req', method, self.origin, '/api/link/v3/' + route, env['kid'], env['rid'], env['n'], env['ts'])
        # 경로·출처·시각이 하나라도 다르면 여기서 거절해요. 비교는 상수 시간이에요.
        if not hmac.compare_digest(tag(keys['req_mac'], header, ciphertext), given):
            raise Reject(401)
        if abs(int(self.clock() * 1000) - env['ts']) > WINDOW_MS:
            raise Reject(401)
        return keys, grant, stream(keys['req_enc'], nonce, ciphertext)

    def run(self, grant, route, plain):
        try:
            if grant.library != self.gateway.library:
                raise Reject(403)
            right = ROUTES.get(route)
            if not right or right not in grant.rights:
                raise Reject(403)
            if len(plain) > (PLAIN_LIMIT if route in LARGE else SMALL_LIMIT):
                raise Reject(413)
            body = json.loads(plain)
            if not isinstance(body, dict):
                raise Reject(400)
            return 200, self.gateway.execute(grant, route, body)
        except Reject as error:
            return error.status, {'error': 'rejected'}
        except StorageFull:
            # 저장 공간 부족은 다음 캐릭터도 같아요. 플러그인이 여기서 멈추게 따로 알려요.
            return 507, {'error': 'storage'}
        except Refused as error:
            # 코드에 적힌 고정 문구만 보내요. 그 밖의 오류 문구에는 받은 내용이 섞일 수 있어 보내지 않아요.
            return 400, {'error': 'invalid', 'reason': str(error)}
        except (TypeError, ValueError, KeyError, RecursionError, OverflowError):
            return 400, {'error': 'invalid'}
        except (sqlite3.Error, OSError):
            return 503, {'error': 'unavailable'}
        except Exception:
            return 500, {'error': 'registration failed'}

    def once(self, kid, rid, route, plain, work, *, require_active=False):
        """완료 응답은 복구하고, 실행 여부가 불확실한 요청은 재실행하지 않아요.

        pending은 프로세스 사망 증거가 아니에요. 서재·파일 쓰기와 이 DB는
        같은 트랜잭션이 아니므로 중단된 쓰기를 자동으로 이어 실행할 수 없어요.
        """
        digest = hashlib.sha256(route.encode() + b'\0' + plain).digest()
        now = self.clock()
        with self.keys.tx() as db:
            # 폐기와 실행 예약을 같은 SQLite 쓰기 잠금으로 순서 지어요.
            # 예약 이후 실행 중인 작업을 취소한다는 뜻은 아니에요.
            if require_active and not db.execute(
                    'SELECT 1 FROM link_keys WHERE kid=? AND revoked=0', (kid,)).fetchone():
                return 401, {'error': 'rejected'}
            # 오래된 응답 본문만 지워요. rid/digest 표식은 재실행 방지를 위해 남겨요.
            db.execute("UPDATE link_requests SET state='expired',response=NULL WHERE state='done' AND created<?",
                       (now - KEEP_SECONDS,))
            row = db.execute('SELECT * FROM link_requests WHERE kid=? AND rid=?', (kid, rid)).fetchone()
            if row:
                if bytes(row['digest']) != digest:
                    return 409, {'error': 'conflict'}
                if row['state'] == 'done':
                    return row['status'], json.loads(row['response'])
                if row['state'] == 'expired':
                    return 409, {'error': 'result_expired'}
                if row['state'] == 'uncertain':
                    return 409, {'error': 'uncertain'}
                return 409, {'error': 'pending' if now - row['created'] < STALE_PENDING else 'uncertain'}
            else:
                db.execute("INSERT INTO link_requests(kid,rid,digest,state,created) VALUES(?,?,?,'pending',?)",
                           (kid, rid, digest, now))
        status, result = work()
        with self.keys.tx() as db:
            if status >= 500 and route in SAFE_RETRY:
                db.execute('DELETE FROM link_requests WHERE kid=? AND rid=?', (kid, rid))
            elif status >= 500:
                db.execute("UPDATE link_requests SET state='uncertain',status=? WHERE kid=? AND rid=?",
                           (status, kid, rid))
            else:
                db.execute("UPDATE link_requests SET state='done',status=?,response=?,created=? WHERE kid=? AND rid=?",
                           (status, json.dumps(result, ensure_ascii=False), self.clock(), kid, rid))
        return status, result

    def seal(self, keys, method, route, env, status, result):
        nonce = secrets.token_bytes(16)
        header = aad('res', method, self.origin, '/api/link/v3/' + route, env['kid'], env['rid'], env['n'],
                     b64e(nonce), status)
        ciphertext = stream(keys['res_enc'], nonce, json.dumps(result, ensure_ascii=False).encode())
        return {'v': 3, 'rid': env['rid'], 'n': b64e(nonce), 's': status,
                'c': b64e(ciphertext), 't': b64e(tag(keys['res_mac'], header, ciphertext))}

    def handle(self, handler, route):
        handler.close_connection = True
        if not self.slots.acquire(blocking=False):
            return handler.send(503, {'error': 'busy'})
        try:
            try:
                env = self.read_envelope(handler)
                keys, grant, plain = self.open(env, route, handler.command)
            except Reject as error:
                # 인증 전 실패는 이유를 구분하지 않아요.
                return handler.send(error.status, {'error': 'rejected'})
            except (sqlite3.Error, OSError):
                return handler.send(503, {'error': 'unavailable'})
            try:
                status, result = self.once(env['kid'], env['rid'], route, plain,
                                           lambda: self.run(grant, route, plain), require_active=True)
            except (sqlite3.Error, OSError):
                status, result = 503, {'error': 'unavailable'}
            return handler.send(status, self.seal(keys, handler.command, route, env, status, result))
        finally:
            self.slots.release()
