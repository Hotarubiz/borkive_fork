"""botkive-link/4 시험 전송 계층. botkive-link/3의 자체 키스트림+HMAC를 표준 AES-256-GCM으로 바꿨어요.

일반 부팅은 이 서비스를 만들지 않아요(서버 기본값은 410). 이 파일만 외부 패키지 cryptography를 써요.
서버 본체(server.py)는 이 파일을 불러오지 않으므로 일반 부팅에는 cryptography가 필요 없어요.

- 페어링 비밀 S(32바이트)는 네트워크로 오가지 않아요. 코드 앞머리가 bkl4_라 v3 코드와 섞이지 않아요.
- S에서 HKDF-SHA256(salt=botkive-link/4)으로 kid와 방향별 AES-256 키 2개를 유도해요(v3와 다른 salt·info).
- 요청·응답마다 무작위 96비트 nonce. 같은 키에서 같은 nonce로 다른 암호문이 오면 키를 폐기해요.
- AAD는 필드마다 4바이트 길이를 붙여 이어요(구분자 충돌 없음). 판·방향·메서드·공개 출처·경로·kid·rid·nonce·시각을 묶어요.
- 인증(GCM 태그 확인)이 끝난 뒤에만 평문을 써요. 재전송·중복·폐기·권한 처리는 v3(Phase 14.1 수정)를 그대로 써요.
"""
import hashlib
import json
import re
import secrets
import sqlite3
from contextlib import contextmanager

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import secure_link as v3
from sync_inbox import safe_path
from secure_link import KEEP_SECONDS, STALE_PENDING, WINDOW_MS, Reject, b64d, b64e, hkdf  # noqa: F401

VERSION = 'botkive-link/4'
SALT = b'botkive-link/4'
PREFIX = '/api/link/v4/'
NONCE, TAG = 12, 16
# 무작위 96비트 nonce는 키당 2^32회 아래로 써야 해요(NIST SP 800-38D 8.3). 응답 봉인 몫까지 넉넉히 남겨요.
MAX_REQUESTS = 1 << 28
ENVELOPE_KEYS = {'v', 'kid', 'rid', 'n', 'ts', 'c'}
REPLY_KEYS = {'v', 'rid', 'n', 's', 'c'}


def derive(secret):
    return {'kid': b64e(hkdf(secret, SALT, b'bkl4/kid', 12)),
            'req': hkdf(secret, SALT, b'bkl4/req/aes-256-gcm', 32),
            'res': hkdf(secret, SALT, b'bkl4/res/aes-256-gcm', 32)}


def aad(*fields):
    out = []
    for field in (VERSION, *fields):
        data = str(field).encode()
        out.append(len(data).to_bytes(4, 'big') + data)
    return b''.join(out)


def parse_code(code):
    if not isinstance(code, str) or not re.fullmatch(r'bkl4_[A-Za-z0-9_-]{43}', code):
        raise ValueError('페어링 코드 형식 오류')
    return b64d(code[5:], 32)


def seal_box(key, nonce, plain, header):
    return AESGCM(key).encrypt(nonce, plain, header)


def open_box(key, nonce, ciphertext, header):
    """태그가 맞을 때만 평문을 돌려줘요. 틀리면 Reject(401)이고 평문은 만들어지지 않아요."""
    if len(nonce) != NONCE or len(ciphertext) < TAG:
        raise Reject(401)
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, header)
    except InvalidTag:
        raise Reject(401) from None


class LinkKeys(v3.LinkKeys):
    PROTO, CODE = 4, 'bkl4_'

    @staticmethod
    def kid_of(secret):
        return derive(secret)['kid']

    def __init__(self, path):
        super().__init__(path)
        # nonce 기록은 키 기록과 다른 파일에 둬요. 재전송 방지(rid 예약)에는 쓰지 않는 감지용 자료라
        # 디스크 동기화를 끄고(빠름), 정전 때 마지막 몇 건을 잃는 것을 허용해요. 파일이 깨지면 503으로 멈춰요.
        self.nonce_path = self.path.with_name(self.path.name + '.nonces')
        safe_path(self.nonce_path)
        with self.nonce_tx() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS link_nonces(kid TEXT NOT NULL, nonce BLOB NOT NULL,
                digest BLOB NOT NULL, seen REAL NOT NULL, PRIMARY KEY(kid, nonce))''')
            db.execute('CREATE INDEX IF NOT EXISTS link_nonces_seen ON link_nonces(seen)')
            db.execute('CREATE TABLE IF NOT EXISTS link_uses(kid TEXT PRIMARY KEY, uses INTEGER NOT NULL)')

    @contextmanager
    def nonce_tx(self):
        db = sqlite3.connect(self.nonce_path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA journal_mode=MEMORY')
            db.execute('PRAGMA synchronous=OFF')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.execute('COMMIT')
        finally:
            db.close()

    def record(self, kid, nonce, digest, now):
        """인증된 요청의 nonce를 남겨요. 'new' / 'same'(같은 봉투 재전송) / 'reused' / 'exhausted'.

        폐기 여부는 once 예약 트랜잭션이 다시 확인해요(Phase 14.1 A5).
        """
        with self.nonce_tx() as db:
            db.execute('DELETE FROM link_nonces WHERE seen<?', (now - v3.KEEP_SECONDS,))
            seen = db.execute('SELECT digest FROM link_nonces WHERE kid=? AND nonce=?', (kid, nonce)).fetchone()
            if seen:
                state = 'same' if bytes(seen['digest']) == digest else 'reused'
            else:
                row = db.execute('SELECT uses FROM link_uses WHERE kid=?', (kid,)).fetchone()
                if row and row['uses'] >= MAX_REQUESTS:
                    return 'exhausted'
                db.execute('INSERT INTO link_nonces(kid,nonce,digest,seen) VALUES(?,?,?,?)', (kid, nonce, digest, now))
                db.execute('INSERT INTO link_uses(kid,uses) VALUES(?,1) ON CONFLICT(kid) DO UPDATE SET uses=uses+1', (kid,))
                return 'new'
        if state == 'reused':
            # 같은 키·같은 nonce로 다른 내용이 왔어요. 클라이언트 난수가 고장 났거나 키가 새어 나간 거예요.
            self.revoke(kid)
        return state


class SecureLinkGateway(v3.SecureLinkGateway):
    """봉투 열기·봉인만 바꾸고 once/run/handle(재전송·폐기·권한 검사)은 v3를 그대로 물려받아요."""
    V, KEYS = 4, ENVELOPE_KEYS

    def __init__(self, gateway, keys, origin, **kwargs):
        if keys is not None and not isinstance(keys, LinkKeys):
            raise TypeError('botkive-link/4 키 기록이 필요해요')
        super().__init__(gateway, keys, origin, **kwargs)

    def open(self, env, route, method):
        found = self.keys.lookup(env['kid'])
        if not found:
            raise Reject(401)
        secret, grant = found
        keys = derive(secret)
        b64d(env['rid'], 16)
        nonce, ciphertext = b64d(env['n'], NONCE), b64d(env['c'])
        header = aad('req', method, self.origin, PREFIX + route, env['kid'], env['rid'], env['n'], env['ts'])
        plain = open_box(keys['req'], nonce, ciphertext, header)
        now = self.clock()
        if abs(int(now * 1000) - env['ts']) > v3.WINDOW_MS:
            raise Reject(401)
        if self.keys.record(env['kid'], nonce, hashlib.sha256(ciphertext).digest(), now) not in ('new', 'same'):
            raise Reject(401)
        return keys, grant, plain

    def seal(self, keys, method, route, env, status, result):
        nonce = secrets.token_bytes(NONCE)
        header = aad('res', method, self.origin, PREFIX + route, env['kid'], env['rid'], env['n'], b64e(nonce), status)
        ciphertext = seal_box(keys['res'], nonce, json.dumps(result, ensure_ascii=False).encode(), header)
        return {'v': 4, 'rid': env['rid'], 'n': b64e(nonce), 's': status, 'c': b64e(ciphertext)}
