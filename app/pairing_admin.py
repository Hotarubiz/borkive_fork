"""botkive-link/4 페어링 관리(발급·목록·폐기). 일반 부팅은 이 서비스를 만들지 않아요(경로가 404).

페어링 코드는 등록 권한까지 줄 수 있는 비밀이라 일반 잠금보다 엄격하게 지켜요.
- Botkive 비밀번호가 설정돼 있어야만 쓸 수 있어요. 잠금이 '꺼짐'이어도, 이 컴퓨터(루프백)에서 열어도 비밀번호를 다시 물어요.
- 비밀번호를 확인하면 10분짜리 관리 세션(HttpOnly·SameSite=Strict 쿠키, 경로 /api/pairing)과 CSRF 토큰을 줘요.
  세션·토큰 원문은 저장하지 않고 sha256만 메모리에 둬요. 서버를 다시 켜거나 비밀번호를 바꾸면 모두 풀려요.
- 모든 관리 요청은 X-BS: 1, CSRF 헤더, 같은 출처(Origin·Sec-Fetch-Site)를 확인해요.
- 코드 원문은 발급 응답에 한 번만 담아요(Cache-Control: no-store). 목록·감사 기록·오류에는 넣지 않아요.
- 발급은 이 서버의 서재 하나에만 해요. 폐기는 그 서재의 v4 키만 할 수 있어요.
"""
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from pathlib import Path

from secure_link import b64d

APP = Path(__file__).resolve().parent
COOKIE = 'bk_pair'
TTL = 600
BODY_LIMIT = 4096
RIGHTS = ('read', 'prepare', 'commit')
LABEL = re.compile(r'[^\x00-\x1f\x7f]{1,40}')
SOURCE = re.compile(r'[A-Za-z0-9_-]{16,80}')
KID = re.compile(r'[A-Za-z0-9_-]{16}')
PAGE_CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; "
            "frame-ancestors 'self'; base-uri 'none'; form-action 'none'")  # 봇카이브 화면 안의 창으로만 띄울 수 있어요
FILES = {('pairing',): ('pairing.html', 'text/html; charset=utf-8'),
         ('pairing', 'app.js'): ('pairing.js', 'text/javascript; charset=utf-8'),
         ('pairing', 'app.css'): ('pairing.css', 'text/css; charset=utf-8')}


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


class Refuse(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class PairingAdmin:
    def __init__(self, keys, library, *, password_hash, check_password, clock=time.time, ttl=TTL, public_origin=None):
        if getattr(keys, 'PROTO', None) != 4:
            raise TypeError('botkive-link/4 키 기록이 필요해요')
        if not re.fullmatch(r'[0-9a-f]{32}', library or ''):
            raise ValueError('서재 ID 형식 오류')
        self.keys, self.library = keys, library
        self.password_hash, self.check_password = password_hash, check_password
        self.clock, self.ttl = clock, ttl
        # 운영자가 정한 공개 주소(BOTKIVE_LINK_ORIGIN). 역방향 프록시가 Host를 내부 주소로 바꿔도 이 출처는 받아요.
        self.public_origin = public_origin
        self._sessions = {}  # sha256(세션) → (만료 시각, sha256(CSRF), 비밀번호 해시 지문)
        self._lock = threading.Lock()
        with keys.tx() as db:
            cols = {r['name'] for r in db.execute('PRAGMA table_info(link_keys)')}
            if 'label' not in cols:
                db.execute("ALTER TABLE link_keys ADD COLUMN label TEXT NOT NULL DEFAULT ''")
            if 'revoked_at' not in cols:
                db.execute('ALTER TABLE link_keys ADD COLUMN revoked_at REAL')
            db.execute('''CREATE TABLE IF NOT EXISTS link_audit(at REAL NOT NULL, action TEXT NOT NULL, ok INTEGER NOT NULL,
                kid TEXT, label TEXT, source TEXT, rights TEXT, peer TEXT)''')

    # ---- 세션 ----
    def _fingerprint(self):
        stored = self.password_hash() or ''
        return digest(stored) if stored else ''

    def _session(self, handler):
        """유효한 관리 세션이면 (세션 지문, 항목), 아니면 None."""
        from http.cookies import SimpleCookie
        cookie = SimpleCookie()
        try:
            cookie.load(handler.headers.get('Cookie') or '')
        except Exception:
            return None
        token = cookie.get(COOKIE)
        if not token:
            return None
        key = digest(token.value)
        with self._lock:
            now = self.clock()
            self._sessions = {k: v for k, v in self._sessions.items() if v[0] > now}
            entry = self._sessions.get(key)
            if entry and entry[2] != self._fingerprint():  # 비밀번호가 바뀌었으면 풀어요.
                self._sessions.pop(key, None)
                entry = None
        return (key, entry) if entry else None

    def _require(self, handler):
        found = self._session(handler)
        if not found:
            raise Refuse(401, '관리 세션이 없거나 끝났어요. 비밀번호를 다시 확인해 주세요.')
        given = handler.headers.get('X-Pairing-CSRF') or ''
        if not hmac.compare_digest(digest(given), found[1][1]):
            raise Refuse(403, '요청을 확인할 수 없어요. 화면을 새로 고친 뒤 다시 해 주세요.')
        return found

    # ---- 요청 검사 ----
    def _same_origin(self, handler):
        site = handler.headers.get('Sec-Fetch-Site')
        if site is not None and site not in ('same-origin', 'none'):
            raise Refuse(403, '다른 사이트에서 온 요청은 받지 않아요.')
        origin = handler.headers.get('Origin')
        if origin is not None:
            proto = 'https' if handler.headers.get('X-Forwarded-Proto') == 'https' else 'http'
            host = handler.headers.get('X-Forwarded-Host') or handler.headers.get('Host') or ''
            if origin != f'{proto}://{host}' and origin != self.public_origin:
                raise Refuse(403, '다른 사이트에서 온 요청은 받지 않아요.')

    def _body(self, handler):
        if handler.headers.get('X-BS') != '1':
            raise Refuse(403, '잘못된 요청')
        if (handler.headers.get('Content-Type') or '').split(';')[0].strip() != 'application/json':
            raise Refuse(415, 'JSON 요청만 받아요.')
        sizes = handler.headers.get_all('Content-Length', [])
        if handler.headers.get('Transfer-Encoding') is not None or len(sizes) != 1 or not re.fullmatch('[0-9]{1,5}', sizes[0]):
            raise Refuse(400, '잘못된 요청')
        if int(sizes[0]) > BODY_LIMIT:
            raise Refuse(413, '요청이 너무 커요.')
        handler.connection.settimeout(5)
        raw = handler.rfile.read(int(sizes[0]))
        try:
            body = json.loads(raw or b'{}')
        except (ValueError, RecursionError):
            raise Refuse(400, '잘못된 요청') from None
        if not isinstance(body, dict):
            raise Refuse(400, '잘못된 요청')
        return body

    def _audit(self, handler, action, ok, kid=None, label=None, source=None, rights=None):
        with self.keys.tx() as db:
            db.execute('INSERT INTO link_audit VALUES(?,?,?,?,?,?,?,?)',
                       (self.clock(), action, int(ok), kid, label, source, rights, handler.peer()))

    # ---- 처리 ----
    def handle(self, handler, parts):
        handler.close_connection = True
        try:
            if tuple(parts) in FILES:
                if handler.command != 'GET':
                    raise Refuse(405, '지원하지 않는 요청')
                name, ctype = FILES[tuple(parts)]
                # 봇카이브 화면 안의 창(같은 출처)에서만 열려요. 다른 사이트는 이 화면을 품지 못해요.
                headers = [('Content-Security-Policy', PAGE_CSP), ('X-Frame-Options', 'SAMEORIGIN')] if ctype.startswith('text/html') else []
                return handler.send(200, (APP / name).read_bytes(), ctype, 'no-store', headers=headers)
            route = '/'.join(parts[2:])
            if handler.command == 'GET' and route == 'status':
                found = self._session(handler)
                return handler.send(200, {'hasPassword': bool(self.password_hash()), 'unlocked': bool(found),
                                          'expiresIn': max(0, int(found[1][0] - self.clock())) if found else 0,
                                          'library': self.library, 'protocol': 'botkive-link/4'})
            if handler.command != 'POST':
                raise Refuse(405, '지원하지 않는 요청')
            self._same_origin(handler)
            body = self._body(handler)
            if route == 'unlock':
                return self._unlock(handler, body)
            found = self._require(handler)
            if route == 'lock':
                with self._lock:
                    self._sessions.pop(found[0], None)
                self._audit(handler, 'lock', True)
                return handler.send(200, {'ok': True}, headers=[self._cookie(handler, '', 0)])
            if route == 'keys':
                return self._list(handler, body)
            if route == 'issue':
                return self._issue(handler, body)
            if route == 'revoke':
                return self._revoke(handler, body)
            raise Refuse(404, '없음')
        except Refuse as error:
            return handler.send(error.status, {'error': error.message})

    def _cookie(self, handler, value, age):
        https_public = bool(self.public_origin and self.public_origin.startswith('https://') and
                            handler.headers.get('Origin') == self.public_origin)
        secure = '; Secure' if handler.headers.get('X-Forwarded-Proto') == 'https' or https_public else ''
        return ('Set-Cookie', f'{COOKIE}={value}; Path=/api/pairing; Max-Age={age}; HttpOnly; SameSite=Strict{secure}')

    def _unlock(self, handler, body):
        if not self.password_hash():
            raise Refuse(403, '먼저 Botkive 설정에서 비밀번호를 정해 주세요. 비밀번호 없이는 페어링을 관리할 수 없어요.')
        if handler.too_many():
            raise Refuse(429, '너무 많이 틀렸어요. 5분 뒤에 다시 해 보세요.')
        if not isinstance(body.get('password'), str) or not self.check_password(body['password'], self.password_hash()):
            handler.failed()
            self._audit(handler, 'unlock', False)
            time.sleep(0.5)
            raise Refuse(403, '비밀번호가 맞지 않아요.')
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[digest(token)] = (self.clock() + self.ttl, digest(csrf), self._fingerprint())
        self._audit(handler, 'unlock', True)
        return handler.send(200, {'csrf': csrf, 'expiresIn': self.ttl}, headers=[self._cookie(handler, token, self.ttl)])

    def _rows(self):
        with self.keys.tx() as db:
            rows = db.execute('''SELECT kid, label, library, source, rights, revoked, created, revoked_at FROM link_keys
                WHERE proto=? AND library=? ORDER BY created DESC''', (self.keys.PROTO, self.library)).fetchall()
        return [{'kid': r['kid'], 'label': r['label'], 'library': r['library'], 'source': r['source'],
                 'rights': r['rights'].split(','), 'state': 'revoked' if r['revoked'] else 'active',
                 'created': r['created'], 'revokedAt': r['revoked_at']} for r in rows]

    def _list(self, handler, body):
        if body:
            raise Refuse(400, '잘못된 요청')
        return handler.send(200, {'keys': self._rows()})

    def _issue(self, handler, body):
        if set(body) != {'label', 'source', 'rights', 'library'}:
            raise Refuse(400, '입력 칸이 맞지 않아요.')
        label, source, rights, library = body['label'], body['source'], body['rights'], body['library']
        if library != self.library:
            raise Refuse(403, '이 서버의 서재에만 발급할 수 있어요.')
        if not isinstance(label, str) or not LABEL.fullmatch(label.strip()):
            raise Refuse(400, '연결 이름은 1~40자로, 줄바꿈 없이 적어 주세요.')
        if not isinstance(source, str) or not SOURCE.fullmatch(source):
            raise Refuse(400, '출처 식별자는 영문·숫자·_·- 16~80자예요.')
        if (not isinstance(rights, list) or not rights or len(set(rights)) != len(rights) or
                not all(isinstance(r, str) and r in RIGHTS for r in rights)):
            raise Refuse(400, '권한은 read·prepare·commit 중에서 골라 주세요.')
        code = self.keys.pair(self.library, source, rights)
        kid = self.keys.kid_of(b64d(code[5:], 32))
        with self.keys.tx() as db:
            db.execute('UPDATE link_keys SET label=? WHERE kid=?', (label.strip(), kid))
        self._audit(handler, 'issue', True, kid, label.strip(), source, ','.join(sorted(rights)))
        row = next(r for r in self._rows() if r['kid'] == kid)
        return handler.send(200, {'code': code, 'key': row}, headers=[('Pragma', 'no-cache')])

    def _revoke(self, handler, body):
        if set(body) != {'kid', 'confirm'} or not isinstance(body['kid'], str) or not KID.fullmatch(body['kid']):
            raise Refuse(400, '잘못된 요청')
        if body['confirm'] != body['kid']:
            raise Refuse(400, '확인 값이 키 식별자와 같아야 해요.')
        with self.keys.tx() as db:
            row = db.execute('SELECT revoked, label, source, rights FROM link_keys WHERE kid=? AND proto=? AND library=?',
                             (body['kid'], self.keys.PROTO, self.library)).fetchone()
            if row and not row['revoked']:
                db.execute('UPDATE link_keys SET revoked=1, revoked_at=? WHERE kid=?', (self.clock(), body['kid']))
        if not row:
            self._audit(handler, 'revoke', False, body['kid'])
            raise Refuse(404, '그 키를 찾지 못했어요.')
        self._audit(handler, 'revoke', True, body['kid'], row['label'], row['source'], row['rights'])
        return handler.send(200, {'key': next(r for r in self._rows() if r['kid'] == body['kid'])})
