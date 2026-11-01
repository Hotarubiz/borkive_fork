"""봇카이브 — 서버 (파이썬 표준 라이브러리만, 설치할 패키지 없음).

리스(RisuAI)에 다 넣어 두기 버거운 봇을 파일로 보관하고, 봇마다 소개글·채팅 로그·자료·링크·메모를 모아 둔다.
혼자 쓰는 앱(계정·비밀번호 없음 — 내 컴퓨터나 Tailscale 같은 내 기기끼리만 열어 둘 것). 쓰기 요청은 X-BS: 1 헤더 필요(다른 사이트에서 몰래 보내는 요청 막기).
환경 변수: DATA_DIR(기본 /data) · PORT(기본 8391) · HOST(기본 127.0.0.1 — 도커 안에서는 0.0.0.0)
          TRUST_GATEWAY=1(도커: 컨테이너 게이트웨이 = 이 컴퓨터로 봄) · RESET_AUTH=1(켤 때 잠금 풀기 — 비밀번호를 잊었을 때)
잠금: 끔 · 밖에서만(이 컴퓨터에서 바로 열 땐 그냥, 프록시·다른 기기로 오면 비밀번호) · 항상. 로그인은 30일 쿠키.

데이터: SQLite(/data/botshelf.db) + 그림(/data/media) + 올린 원본(/data/bots/0012/v37/원래이름 · 자료는 /data/items/ · 봇마다 info.txt).
      6시간마다 DB 백업(30개). 예전 /data/files(무작위 이름)는 켤 때 봇 폴더로 옮김.
API (JSON):
  GET    /api/state                      폴더·자료함 칸·개수
  GET    /api/bots?folder=&status=       봇 목록(요약)     POST /api/bots
  GET    /api/bots/<id>                  봇 + 폴더 + 링크 + 파일 + 채팅 목록
  PUT    /api/bots/<id>   DELETE /api/bots/<id>
  POST   /api/bots/<id>/intro            {html, version_id?, intro_id?, title?, url?, author?} 붙여넣은 소개글을 그 버전(기본 지금 버전)에
                                         새 글로 저장, intro_id가 있으면 그 글을 바꿈(그림은 받아서 보관)
  PUT    /api/intros/<id>                {title} 글 이름   DELETE /api/intros/<id>
  PUT    /api/series                     {bot_id, name, ids?: [채팅 id], from?: 예전 시리즈 이름} 채팅을 시리즈로 묶기·이름 바꾸기·풀기(name '')
  GET    /api/files/<id>/lore            카드·모듈 파일 속 로어북 {sources: [{label, entries}]} (charx 속 module.risum, .risum까지)
  GET    /api/files/<id>/assets          파일 속 에셋 목록 {sources: [{label, kind c|m, assets}]}
  GET    /api/files/<id>/asset/<n>       카드 에셋 하나   GET /api/files/<id>/masset/<n> 모듈(.risum) 에셋 하나
  GET    /api/realm/<uuid>               (X-BS) 리스 랠름에서 카드 파일을 받아 그대로 넘김 — charx → png → json 순서로 되는 형식
  POST   /api/bots/<id>/basic            {html, scope: all|ver, version_id} 기본 소개(모든 버전 공통 또는 그 버전 전용, 빈 글이면 지움)
  POST   /api/bots/<id>/intro/fetch      {url, version_id?} 아카라이브 글 가져오기
  POST   /api/versions {bot_id, name, note, released, info, current}   PUT|DELETE /api/versions/<id>
         버전 = 업데이트 하나(카드·모듈·소개글 묶음). 버전 없는 봇 자료는 공통 자료.
  POST   /api/folders  PUT|DELETE /api/folders/<id>      POST /api/shelves  PUT|DELETE /api/shelves/<id>
  POST   /api/links    PUT|DELETE /api/links/<id>
  POST   /api/statuses {name, color}   PUT|DELETE /api/statuses/<key>   봇 상태 (기본 3개는 이름·색만, 더한 건 지우기도 — 지우면 그 봇은 '찜'으로)
  POST   /api/itypes {name, color}     PUT|DELETE /api/itypes/<key>     자료 종류 (지우면 그 자료는 '기타'로)
         자료 = bots 줄 중 itype이 있는 것 (봇과 같은 페이지·버전·소개글을 씀, 자료함에만 나옴). 폴더도 scope bot|item으로 따로.
  PUT    /api/upload?bot=&version=|shelf=&kind=&name=    파일 원본(본문 그대로)
  GET    /api/files?all=1   PUT|DELETE /api/files/<id>
  GET    /api/chats?bot=    POST /api/chats    GET|PUT|DELETE /api/chats/<id>
  GET    /api/styles   GET|PUT|DELETE /api/styles/<id>   POST /api/styles {name, stype, prompt, negative, settings, images: [{data, meta}], folders, tags…}
  POST   /api/styles/<id>/images {images}   PUT|DELETE /api/style_images/<id> ({front: true} = 대표 그림)
  POST   /api/styles/<id>/bots {bot_id, role: official|mine}   DELETE /api/styles/<id>/bots/<bot_id>   그림체 ↔ 봇 잇기
  GET    /api/export                     전부 내보내기 zip (봇/<폴더>/<봇>/버전/원본 · 채팅 로그 · 그림체 · 봇카이브.json)
  GET    /api/styles/export?ids=1,2      그림체 파일(.botkive-style.json, 그림 포함)   POST /api/styles/import (그 파일 내용)
         그림체 = 그림 생성 프롬프트(작가·스타일 태그) + 견본 그림. 분류 stypes(이름표), 폴더 scope style.
  GET    /api/stats                      홈 숫자: 봇 수·상태별, 지금 버전 로어북 토큰·항목, 채팅 로그 토큰, 지금 버전 에셋 수 (토큰은 어림값)
  GET    /api/auth   PUT /api/auth {mode, current, password}   POST /api/auth/login {password}   POST /api/auth/logout
  PUT    /api/marks                      {chat_id, idx, on, memo, image, drop_image} 장면 표시
  GET    /api/health
  GET    /m/<그림>   GET /f/<파일>?dl=<이름>
"""
import base64
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import socket
import sqlite3
import threading
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from html import escape, unescape
from html.parser import HTMLParser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, unquote_plus, urljoin, urlsplit

DATA = Path(os.environ.get("DATA_DIR", "/data"))
APP = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", "8391"))
HOST = os.environ.get("HOST", "127.0.0.1")  # 기본은 이 컴퓨터에서만. 0.0.0.0이면 같은 망의 다른 기기도 들어옴 (로그인이 없으니 주의)
MEDIA = DATA / "media"
FILES = DATA / "files"     # 예전 자리 (무작위 이름) — 켤 때 봇 폴더로 옮기고 비면 지움
TMP = DATA / "tmp"         # 올리는 중인 파일
STORE_ROOTS = {"bots", "items", "loose", "tmp", "files"}  # 원본 파일이 있을 수 있는 data 아래 폴더
KST = timezone(timedelta(hours=9))
KEEP_BACKUPS = 30
MAX_BODY = 80_000_000      # 채팅 로그 JSON (그림은 빼고 글만 오니 이 정도면 충분)
MAX_FILE = 2_000_000_000   # 카드·모듈·자료 원본
MAX_REMOTE = 40_000_000    # 소개글 그림 하나
RANGE_CHUNK = 2_000_000
MEDIA_RE = r"[0-9a-f]{20}\.(?:webp|jpg|png|gif|mp4|webm)"
FILE_RE = r"[0-9a-f]{24}"
CTYPES = {"jpg": "image/jpeg", "webp": "image/webp", "png": "image/png", "gif": "image/gif", "mp4": "video/mp4", "webm": "video/webm"}
REMOTE_TYPES = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif", "video/mp4": "mp4", "video/webm": "webm"}
# 아카 등의 이모지는 twemoji SVG — SVG는 안 받으니 같은 그림의 PNG로 바꿔 받음
TWEMOJI_RE = re.compile(r"/twemoji/(?:[^?#]*/)?(?:svg|72x72)/([0-9a-f]{2,6}(?:-[0-9a-f]{2,6})*)\.(?:svg|png)(?:[?#]|$)", re.I)
TWEMOJI_PNG = "https://cdn.jsdelivr.net/gh/jdecked/twemoji@15.1.0/assets/72x72/{}.png"


def twemoji_char(u):
    """twemoji 주소 → 이모지 글자 (PNG도 못 받았을 때 대신 넣음)."""
    m = TWEMOJI_RE.search(u or "")
    try:
        cps = [int(x, 16) for x in m.group(1).split("-")] if m else []
        return "".join(map(chr, cps)) if cps and max(cps) < 0xE0080 else ""
    except ValueError:
        return ""


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"

DEFAULT_ITYPES = [("module", "모듈", "#B9A6F5"), ("preset", "프리셋", "#7FD1E8"), ("lore", "로어북", "#C9A27A"),
                  ("plugin", "플러그인", "#9CCB6E"), ("etc", "기타", "#C7C5CC")]  # 자료 종류 기본 (키 고정, etc는 지운 종류가 가는 곳)
DEFAULT_STYPES = [("cel", "셀화", "#8FB8E8"), ("paint", "두꺼운 칠", "#C9A27A"), ("water", "수채", "#7FD1E8"),
                  ("semi", "반실사", "#E89BCB"), ("etc", "기타", "#C7C5CC")]  # 그림체 분류 기본 (etc는 지운 분류가 가는 곳)
LABELS = {"statuses": ("상태", 12, "s"), "itypes": ("종류", 20, "t"), "stypes": ("분류", 20, "g")}  # 이름표 표: 부를 이름, 최대 개수, 더한 키 앞글자
LABEL_MOVE = {"statuses": ("bots", "status", "later"), "itypes": ("bots", "itype", "etc"), "stypes": ("styles", "stype", "etc")}  # 지울 때 옮길 곳
STYLE_FIELDS = {"name": 200, "creator": 200, "source": 1000, "prompt": 20000, "negative": 20000, "memo": 20000}  # 글자 수 한도
DEFAULT_STATUSES = [("playing", "하는 중", "#F2B655"), ("later", "찜", "#8FB8E8"), ("done", "끝", "#5EC2B7")]  # 키는 고정 (홈이 playing을 씀)
KINDS = {"card", "module", "preset", "lore", "plugin", "images", "regex", "memo", "etc"}
COLORS = {"#F2B655", "#5EC2B7", "#B9A6F5", "#8FB8E8", "#F08A8A", "#9CCB6E", "#E89BCB", "#C9A27A", "#7FD1E8", "#C7C5CC"}

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
       "font-src https://fonts.gstatic.com https://cdn.jsdelivr.net https://hangeul.pstatic.net; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'none'")

BOT_FIELDS = {"name": str, "creator": str, "status": str, "itype": str, "in_risu": bool, "memo": str, "info": dict,
              "intro_url": str, "intro_title": str, "intro_author": str}
JSON_COLS = {"info"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS folders (id INTEGER PRIMARY KEY, name TEXT NOT NULL, color TEXT, sort INTEGER DEFAULT 0, created TEXT);
CREATE TABLE IF NOT EXISTS file_stats (file TEXT PRIMARY KEY, data TEXT);
CREATE TABLE IF NOT EXISTS stypes (key TEXT PRIMARY KEY, name TEXT NOT NULL, color TEXT, sort INTEGER DEFAULT 0, builtin INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, created TEXT, expires REAL);
CREATE TABLE IF NOT EXISTS styles (id INTEGER PRIMARY KEY, name TEXT NOT NULL, creator TEXT DEFAULT '', source TEXT DEFAULT '', stype TEXT DEFAULT 'etc',
  prompt TEXT DEFAULT '', negative TEXT DEFAULT '', settings TEXT DEFAULT '{}', memo TEXT DEFAULT '', tags TEXT DEFAULT '[]', created TEXT, updated TEXT, opened TEXT);
CREATE TABLE IF NOT EXISTS style_images (id INTEGER PRIMARY KEY, style_id INTEGER REFERENCES styles(id) ON DELETE CASCADE, image TEXT, sort INTEGER DEFAULT 0, meta TEXT DEFAULT '{}', created TEXT);
CREATE TABLE IF NOT EXISTS style_folders (style_id INTEGER REFERENCES styles(id) ON DELETE CASCADE, folder_id INTEGER REFERENCES folders(id) ON DELETE CASCADE, PRIMARY KEY (style_id, folder_id));
CREATE TABLE IF NOT EXISTS bot_styles (bot_id INTEGER REFERENCES bots(id) ON DELETE CASCADE, style_id INTEGER REFERENCES styles(id) ON DELETE CASCADE, role TEXT DEFAULT 'mine', PRIMARY KEY (bot_id, style_id));
CREATE TABLE IF NOT EXISTS itypes (key TEXT PRIMARY KEY, name TEXT NOT NULL, color TEXT, sort INTEGER DEFAULT 0, builtin INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS statuses (key TEXT PRIMARY KEY, name TEXT NOT NULL, color TEXT, sort INTEGER DEFAULT 0, builtin INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS shelves (id INTEGER PRIMARY KEY, name TEXT NOT NULL, sort INTEGER DEFAULT 0, created TEXT);
CREATE TABLE IF NOT EXISTS bots (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, creator TEXT DEFAULT '', status TEXT DEFAULT 'later', in_risu INTEGER DEFAULT 0,
  cover TEXT, memo TEXT DEFAULT '', info TEXT DEFAULT '{}',
  intro_html TEXT DEFAULT '', intro_url TEXT DEFAULT '', intro_title TEXT DEFAULT '', intro_author TEXT DEFAULT '', intro_at TEXT,
  created TEXT, updated TEXT, opened TEXT);
CREATE TABLE IF NOT EXISTS bot_folders (bot_id INTEGER REFERENCES bots(id) ON DELETE CASCADE, folder_id INTEGER REFERENCES folders(id) ON DELETE CASCADE,
  PRIMARY KEY (bot_id, folder_id));
CREATE TABLE IF NOT EXISTS links (id INTEGER PRIMARY KEY, bot_id INTEGER REFERENCES bots(id) ON DELETE CASCADE, title TEXT, url TEXT, note TEXT DEFAULT '', sort INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS files (
  id INTEGER PRIMARY KEY, bot_id INTEGER REFERENCES bots(id) ON DELETE CASCADE, shelf_id INTEGER REFERENCES shelves(id) ON DELETE SET NULL,
  kind TEXT DEFAULT 'etc', name TEXT, file TEXT, size INTEGER, note TEXT DEFAULT '', current INTEGER DEFAULT 0, created TEXT);
CREATE TABLE IF NOT EXISTS chats (
  id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER REFERENCES bots(id) ON DELETE CASCADE, title TEXT, memo TEXT DEFAULT '', source TEXT DEFAULT '',
  count INTEGER DEFAULT 0, first_at INTEGER, last_at INTEGER, created TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS messages (chat_id INTEGER REFERENCES chats(id) ON DELETE CASCADE, idx INTEGER, role TEXT, name TEXT, text TEXT, at INTEGER,
  PRIMARY KEY (chat_id, idx));
CREATE TABLE IF NOT EXISTS marks (chat_id INTEGER REFERENCES chats(id) ON DELETE CASCADE, idx INTEGER, memo TEXT DEFAULT '', image TEXT, created TEXT,
  PRIMARY KEY (chat_id, idx));
CREATE TABLE IF NOT EXISTS versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER REFERENCES bots(id) ON DELETE CASCADE, name TEXT, note TEXT DEFAULT '', released TEXT DEFAULT '',
  current INTEGER DEFAULT 0, info TEXT DEFAULT '{}',
  intro_html TEXT DEFAULT '', intro_url TEXT DEFAULT '', intro_title TEXT DEFAULT '', intro_author TEXT DEFAULT '', intro_at TEXT, created TEXT);
CREATE INDEX IF NOT EXISTS files_bot ON files(bot_id);
CREATE INDEX IF NOT EXISTS chats_bot ON chats(bot_id);
CREATE INDEX IF NOT EXISTS versions_bot ON versions(bot_id);
CREATE TABLE IF NOT EXISTS intros (
  id INTEGER PRIMARY KEY AUTOINCREMENT, version_id INTEGER REFERENCES versions(id) ON DELETE CASCADE,
  title TEXT DEFAULT '', html TEXT DEFAULT '', url TEXT DEFAULT '', author TEXT DEFAULT '', at TEXT, sort INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS intros_ver ON intros(version_id);
"""
DEFAULT_FOLDERS = [("운영 봇", "#F2B655"), ("자작 봇", "#5EC2B7"), ("받은 봇", "#B9A6F5"), ("해 볼 것", "#8FB8E8")]
DEFAULT_SHELVES = ["공용 모듈", "프롬프트 프리셋", "참고 그림"]


# ---- 잠금(로그인) ----
# 모드: off · remote(밖에서 올 때만) · always. 비밀번호는 scrypt로만 저장, 로그인 쿠키 토큰은 sha256으로만 저장
AUTH_MODES = ("off", "remote", "always")
SESSION_DAYS = 30
COOKIE = "bk_session"
FWD_HEADERS = ("X-Forwarded-For", "Forwarded", "X-Real-IP", "Tailscale-User-Login", "CF-Connecting-IP")  # 하나라도 있으면 프록시 거쳐 온 바깥 요청
_fails, _fails_lock = {}, threading.Lock()  # 틀린 로그인: 주소 → [시각…] (5분에 5번까지)


def gateway_ip():
    """도커 안에서 기본 게이트웨이(= 이 컴퓨터) 주소."""
    try:
        for line in open("/proc/net/route").read().splitlines()[1:]:
            f = line.split()
            if f[1] == "00000000":
                return ipaddress.IPv4Address(int(f[2], 16).to_bytes(4, "little")).exploded
    except (OSError, ValueError, IndexError):
        pass
    return None


LOCAL_PEERS = {"127.0.0.1", "::1"} | ({gateway_ip()} - {None} if os.environ.get("TRUST_GATEWAY") == "1" else set())


def setting(k, default=""):
    r = db.q("SELECT value FROM settings WHERE key=?", (k,))
    return r[0]["value"] if r else default


def set_setting(k, v):
    db.x("INSERT INTO settings(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))


def pw_hash(pw):
    salt = secrets.token_bytes(16)
    return f"scrypt$16384$8$1${salt.hex()}${hashlib.scrypt(pw.encode(), salt=salt, n=16384, r=8, p=1, dklen=32).hex()}"


def pw_ok(pw, stored):
    try:
        _, n, r, p, salt, h = stored.split("$")
        got = hashlib.scrypt(str(pw or "").encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(got.hex(), h)
    except (ValueError, TypeError):
        return False


def tok_hash(t):
    return hashlib.sha256(t.encode()).hexdigest()


def now():
    return datetime.now(KST).isoformat(timespec="seconds")


class DB:
    def __init__(self, path):
        self.lock = threading.Lock()
        self.c = sqlite3.connect(path, check_same_thread=False)
        self.c.row_factory = sqlite3.Row
        self.c.execute("PRAGMA journal_mode=WAL")
        self.c.execute("PRAGMA foreign_keys=ON")
        self.c.executescript(SCHEMA)
        if not self.c.execute("SELECT 1 FROM folders LIMIT 1").fetchone() and not self.c.execute("SELECT 1 FROM bots LIMIT 1").fetchone():
            for i, (n, col) in enumerate(DEFAULT_FOLDERS):
                self.c.execute("INSERT INTO folders(name, color, sort, created) VALUES (?,?,?,?)", (n, col, i, now()))
            for i, n in enumerate(DEFAULT_SHELVES):
                self.c.execute("INSERT INTO shelves(name, sort, created) VALUES (?,?,?)", (n, i, now()))
        self.c.commit()
        if "version_id" not in [r["name"] for r in self.c.execute("PRAGMA table_info(files)")]:
            self.migrate_versions()
        for t in ("bots", "versions"):  # 기본 소개: 봇 공통 + 버전 전용
            if "basic" not in [r["name"] for r in self.c.execute(f"PRAGMA table_info({t})")]:
                self.c.execute(f"ALTER TABLE {t} ADD COLUMN basic TEXT DEFAULT ''")
        if "series" not in [r["name"] for r in self.c.execute("PRAGMA table_info(chats)")]:  # 채팅 시리즈 (같은 이야기의 여러 기록)
            self.c.execute("ALTER TABLE chats ADD COLUMN series TEXT DEFAULT ''")
        if "tags" not in [r["name"] for r in self.c.execute("PRAGMA table_info(bots)")]:  # 봇 태그 (JSON 목록)
            self.c.execute("ALTER TABLE bots ADD COLUMN tags TEXT DEFAULT '[]'")
        if "rx" not in [r["name"] for r in self.c.execute("PRAGMA table_info(bots)")]:  # 로그 표시 규칙: 정규식 키 → 방식 (봇마다 직접 고른 것)
            self.c.execute("ALTER TABLE bots ADD COLUMN rx TEXT DEFAULT '{}'")
        if not self.c.execute("SELECT 1 FROM statuses LIMIT 1").fetchone():
            for i, (k, n, col) in enumerate(DEFAULT_STATUSES):
                self.c.execute("INSERT INTO statuses(key, name, color, sort, builtin) VALUES (?,?,?,?,1)", (k, n, col, i))
            if self.c.execute("SELECT 1 FROM bots WHERE status='archived' LIMIT 1").fetchone():  # 예전 '보관'에 둔 봇이 있으면 더한 상태로 남김
                self.c.execute("INSERT INTO statuses(key, name, color, sort) VALUES ('archived','보관','#C7C5CC',3)")
        if "itype" not in [r["name"] for r in self.c.execute("PRAGMA table_info(bots)")]:  # 자료함 자료 (''이면 봇)
            self.c.execute("ALTER TABLE bots ADD COLUMN itype TEXT DEFAULT ''")
        if "scope" not in [r["name"] for r in self.c.execute("PRAGMA table_info(folders)")]:  # 서재 폴더(bot) · 자료함 폴더(item)
            self.c.execute("ALTER TABLE folders ADD COLUMN scope TEXT DEFAULT 'bot'")
        if not self.c.execute("SELECT 1 FROM stypes LIMIT 1").fetchone():
            for i, (k, n, col) in enumerate(DEFAULT_STYPES):
                self.c.execute("INSERT INTO stypes(key, name, color, sort, builtin) VALUES (?,?,?,?,1)", (k, n, col, i))
        if not self.c.execute("SELECT 1 FROM itypes LIMIT 1").fetchone():
            for i, (k, n, col) in enumerate(DEFAULT_ITYPES):
                self.c.execute("INSERT INTO itypes(key, name, color, sort, builtin) VALUES (?,?,?,?,1)", (k, n, col, i))
        if "tokens" not in [r["name"] for r in self.c.execute("PRAGMA table_info(chats)")]:  # 채팅 로그 토큰 어림값 (NULL = 아직 안 셈)
            self.c.execute("ALTER TABLE chats ADD COLUMN tokens INTEGER")
        if "chars" not in [r["name"] for r in self.c.execute("PRAGMA table_info(styles)")]:  # 그림체 캐릭터 칸 (NAI v4) [{prompt, negative}]
            self.c.execute("ALTER TABLE styles ADD COLUMN chars TEXT DEFAULT '[]'")
        if "ep" not in [r["name"] for r in self.c.execute("PRAGMA table_info(chats)")]:  # 시리즈 화 번호 직접 지정 (NULL = 제목에서 읽음)
            self.c.execute("ALTER TABLE chats ADD COLUMN ep INTEGER")
        if "path" not in [r["name"] for r in self.c.execute("PRAGMA table_info(files)")]:  # 디스크 자리 (data 기준), moving = 옮기는 중인 예전 자리
            self.c.execute("ALTER TABLE files ADD COLUMN path TEXT")
            self.c.execute("ALTER TABLE files ADD COLUMN moving TEXT")
        self.c.commit()
        if self.c.execute("SELECT 1 FROM versions WHERE intro_html != '' LIMIT 1").fetchone():
            self.migrate_intros()

    def migrate_intros(self):
        """버전마다 하나였던 소개글 → intros 표(버전마다 여러 글)."""
        (DATA / "backups").mkdir(exist_ok=True)
        dst = sqlite3.connect(DATA / "backups" / f"pre-intros-{datetime.now(KST):%Y-%m-%d}.db")
        self.c.backup(dst)
        dst.close()
        with self.c:
            self.c.execute("""INSERT INTO intros(version_id, title, html, url, author, at)
                              SELECT id, intro_title, intro_html, intro_url, intro_author, intro_at FROM versions WHERE intro_html != ''""")
            self.c.execute("UPDATE versions SET intro_html='', intro_url='', intro_title='', intro_author='', intro_at=NULL")
        print("소개글을 글 목록으로 옮기기 끝", flush=True)

    def migrate_versions(self):
        """카드 하나 = 버전 하나로 옮김. 소개글은 지금 버전에, 카드가 하나뿐인 봇은 다른 자료도 그 버전에."""
        if self.c.execute("SELECT 1 FROM bots LIMIT 1").fetchone():
            (DATA / "backups").mkdir(exist_ok=True)
            dst = sqlite3.connect(DATA / "backups" / f"pre-versions-{datetime.now(KST):%Y-%m-%d}.db")
            self.c.backup(dst)
            dst.close()
        with self.c:
            self.c.execute("ALTER TABLE files ADD COLUMN version_id INTEGER")
            self.c.execute("CREATE INDEX IF NOT EXISTS files_ver ON files(version_id)")
            for b in self.c.execute("SELECT * FROM bots").fetchall():
                info = json.loads(b["info"] or "{}") if b["info"] else {}
                cards = self.c.execute("SELECT * FROM files WHERE bot_id=? AND kind='card' ORDER BY created, id", (b["id"],)).fetchall()
                cur = None
                for f in cards:
                    name = f"v{info['version']}"[:40] if f["current"] and info.get("version") else re.sub(r"\.[^.]+$", "", f["name"] or "")[:40] or "예전 버전"
                    vid = self.c.execute("INSERT INTO versions(bot_id, name, current, info, created) VALUES (?,?,?,?,?)",
                                         (b["id"], name, f["current"], b["info"] if f["current"] else "{}", f["created"])).lastrowid
                    self.c.execute("UPDATE files SET version_id=? WHERE id=?", (vid, f["id"]))
                    if f["current"]:
                        cur = vid
                if len(cards) == 1:
                    self.c.execute("UPDATE files SET version_id=? WHERE bot_id=? AND version_id IS NULL", (cur, b["id"]))
                if b["intro_html"]:
                    if not cur:
                        cur = self.c.execute("INSERT INTO versions(bot_id, name, current, info, created) VALUES (?,?,1,?,?)",
                                             (b["id"], "첫 버전", b["info"] or "{}", b["created"])).lastrowid
                    self.c.execute("""UPDATE versions SET intro_html=?, intro_url=?, intro_title=?, intro_author=?, intro_at=? WHERE id=?""",
                                   (b["intro_html"], b["intro_url"], b["intro_title"], b["intro_author"], b["intro_at"], cur))
                    self.c.execute("UPDATE bots SET intro_html='' WHERE id=?", (b["id"],))
        print("버전으로 옮기기 끝", flush=True)

    def q(self, sql, args=()):
        with self.lock:
            return [row(r) for r in self.c.execute(sql, args).fetchall()]

    def x(self, sql, args=()):
        with self.lock:
            cur = self.c.execute(sql, args)
            self.c.commit()
            return cur.lastrowid, cur.rowcount

    def many(self, sql, rows):
        with self.lock:
            self.c.executemany(sql, rows)
            self.c.commit()


def row(r):
    d = dict(r)
    for k in JSON_COLS & d.keys():
        try:
            d[k] = json.loads(d[k] or "{}")
        except ValueError:
            d[k] = {}
    if "in_risu" in d:
        d["in_risu"] = bool(d["in_risu"])
    if "current" in d:
        d["current"] = bool(d["current"])
    return d


def clean(data, fields):
    out = {}
    for k, t in fields.items():
        if k not in data:
            continue
        v = data[k]
        if t is bool:
            out[k] = 1 if v else 0
        elif t is str:
            out[k] = str(v or "")[:200_000].strip() if k == "memo" else str(v or "")[:300].strip()
        elif t is dict:
            out[k] = json.dumps(v if isinstance(v, dict) else {}, ensure_ascii=False)[:400_000]
    if "status" in out and not db.q("SELECT 1 FROM statuses WHERE key=?", (out["status"],)):
        del out["status"]
    if out.get("itype") and not db.q("SELECT 1 FROM itypes WHERE key=?", (out["itype"],)):
        del out["itype"]
    if "name" in out and not out["name"]:
        del out["name"]
    return out


def set_folders(bot_id, ids):
    ok = {f["id"] for f in db.q("SELECT id FROM folders")}
    db.x("DELETE FROM bot_folders WHERE bot_id=?", (bot_id,))
    db.many("INSERT OR IGNORE INTO bot_folders(bot_id, folder_id) VALUES (?,?)", [(bot_id, int(i)) for i in ids if str(i).isdigit() and int(i) in ok])


def save_data_url(data_url):
    m = re.match(r"^data:image/(webp|jpeg|png);base64,(.+)$", data_url or "", re.S)
    if not m:
        raise ValueError("이미지 형식 아님")
    raw = base64.b64decode(m.group(2))
    if len(raw) > 15_000_000:
        raise ValueError("그림이 너무 커요")
    name = f"{secrets.token_hex(10)}.{ {'jpeg': 'jpg'}.get(m.group(1), m.group(1))}"
    (MEDIA / name).write_bytes(raw)
    return name


def drop_media(*names):
    for n in names:
        if n and re.fullmatch(MEDIA_RE, n):
            (MEDIA / n).unlink(missing_ok=True)


def drop_file(f):
    """files 줄(file·path)의 원본 지우기."""
    if f.get("path"):
        drop_path(f["path"])
    elif re.fullmatch(FILE_RE, f.get("file") or ""):
        (FILES / f["file"]).unlink(missing_ok=True)


# ---- 원본 파일 자리: data/bots/0012/v37/원래이름.charx (자료는 items/, 봇 없는 파일은 loose/) ----
# 번호·버전 번호는 이름을 바꿔도 안 변해서 파일을 옮길 일이 거의 없음. 봇 폴더마다 사람이 읽는 info.txt.
_WIN_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WIN_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_place_lock = threading.Lock()


def split_ext(name):
    stem, dot, ext = name.rpartition(".")
    return (stem, "." + ext) if dot and stem and 0 < len(ext) <= 12 else (name, "")


def safe_name(name, fallback="file", limit=120):
    """윈도우·리눅스 어디서나 되는 파일·폴더 이름."""
    n = re.sub(r"\s+", " ", _WIN_BAD.sub("_", str(name or ""))).strip().rstrip(". ") or fallback
    stem, ext = split_ext(n)
    if stem.split(".")[0].upper() in _WIN_RESERVED:
        stem = "_" + stem
    return stem[:max(1, limit - len(ext))].rstrip(". ") + ext


def free_name(name, taken):
    """taken(소문자 이름 모음 또는 폴더)과 안 겹치게 ' (2)'를 붙임."""
    stem, ext = split_ext(name)
    used = (lambda c: (taken / c).exists()) if isinstance(taken, Path) else (lambda c: c.lower() in taken)
    cand, i = name, 2
    while used(cand):
        cand, i = f"{stem} ({i}){ext}", i + 1
    if not isinstance(taken, Path):
        taken.add(cand.lower())
    return cand


def bot_home(bot_id, itype):
    return f"{'items' if itype else 'bots'}/{bot_id:04d}"


def file_home(f):
    if not f["bot_id"]:
        return "loose"
    home = bot_home(f["bot_id"], f["itype"])
    return f"{home}/v{f['version_id']}" if f["version_id"] else home


def fpath(token):
    """파일 토큰 → 디스크 경로 (옮기는 사이에는 예전 자리)."""
    r = db.q("SELECT path, moving FROM files WHERE file=?", (token,))
    if not r or not r[0]["path"]:
        return FILES / token
    p = DATA / r[0]["path"]
    if r[0]["moving"] and not p.exists() and (DATA / r[0]["moving"]).exists():
        return DATA / r[0]["moving"]
    return p


def prune(d):
    """빈 폴더를 위로 올라가며 지움 (bots/ 같은 맨 위 폴더와 data는 남김)."""
    d = Path(d)
    while d.parent != DATA and DATA in d.parents:
        try:
            d.rmdir()
        except OSError:
            return
        d = d.parent


def drop_path(rel):
    if not rel or rel.split("/")[0] not in STORE_ROOTS or ".." in rel.split("/"):
        return
    p = DATA / rel
    p.unlink(missing_ok=True)
    prune(p.parent)


def place_file(fid):
    """파일을 있어야 할 자리로 옮김. 새 자리를 먼저 적고(moving = 예전 자리) 옮겨서, 중간에 꺼져도 켤 때 마저 옮김."""
    with _place_lock:
        r = db.q("""SELECT f.id, f.file, f.name, f.path, f.bot_id, f.version_id, COALESCE(b.itype, '') AS itype
                    FROM files f LEFT JOIN bots b ON b.id=f.bot_id WHERE f.id=?""", (fid,))
        if not r:
            return
        f = r[0]
        home = file_home(f)
        if f["path"] and f["path"].rsplit("/", 1)[0] == home:
            return
        cur = DATA / f["path"] if f["path"] else FILES / f["file"]
        if not cur.is_file():
            return
        d = DATA / home
        d.mkdir(parents=True, exist_ok=True)
        new = d / free_name(safe_name(f["name"], f["file"]), d)
        old_rel = cur.relative_to(DATA).as_posix()
        db.x("UPDATE files SET path=?, moving=? WHERE id=?", (new.relative_to(DATA).as_posix(), old_rel, fid))
        try:
            os.replace(cur, new)
        except OSError:  # 윈도우에서 다른 곳이 열고 있으면 못 옮김 — 다음에 켤 때 다시
            db.x("UPDATE files SET path=?, moving=NULL WHERE id=?", (f["path"] or old_rel, fid))
            return
        db.x("UPDATE files SET moving=NULL WHERE id=?", (fid,))
        prune(cur.parent)


def place_bot(bid):
    """봇 ↔ 자료를 바꾼 뒤: 파일을 새 집으로 옮기고 예전 집의 info.txt를 걷음."""
    for f in db.q("SELECT id FROM files WHERE bot_id=?", (bid,)):
        place_file(f["id"])
    for itype in ("", "x"):
        home = DATA / bot_home(bid, itype)
        if not any(p.name != "info.txt" for p in home.glob("*")):
            (home / "info.txt").unlink(missing_ok=True)
            prune(home)
    write_info(bid)


def settle_files():
    """켤 때: 옮기다 만 파일을 마저 옮기고, 예전 자리(files/ 무작위 이름)나 올리다 만 파일을 봇 폴더로."""
    for f in db.q("SELECT id, path, moving FROM files WHERE moving IS NOT NULL AND moving != ''"):
        new, old = DATA / f["path"], DATA / f["moving"]
        if not new.is_file() and old.is_file():
            new.parent.mkdir(parents=True, exist_ok=True)
            os.replace(old, new)
            prune(old.parent)
        db.x("UPDATE files SET moving=NULL WHERE id=?", (f["id"],))
    moved = 0
    for f in db.q("SELECT id, path FROM files"):
        try:
            place_file(f["id"])
            moved += not f["path"]
        except Exception as e:
            print(f"파일 옮기기 오류 {f['id']}: {e!r}", flush=True)
    if moved:
        print(f"원본 파일 {moved}개를 봇 폴더(bots/ · items/)로 옮겼어요", flush=True)
    for d in (FILES, TMP, DATA / "items", DATA / "loose"):  # 빈 자리는 치움 (필요할 때 다시 만듦)
        try:
            d.rmdir()
        except OSError:
            pass
    for b in db.q("SELECT id FROM bots"):
        write_info(b["id"])


def info_text(bid, vdir=None, fnames=None):
    """봇 하나를 사람이 읽는 글로. 내보내기에서는 vdir(버전 id → 폴더 이름)·fnames(파일 id → 이름)를 줌."""
    b = db.q("SELECT * FROM bots WHERE id=?", (bid,))
    if not b:
        return ""
    b = b[0]
    names = lambda t: {r["key"]: r["name"] for r in db.q(f"SELECT key, name FROM {t}")}
    item = b["itype"] or ""
    folders = [r["name"] for r in db.q("SELECT f.name FROM bot_folders x JOIN folders f ON f.id=x.folder_id WHERE x.bot_id=? ORDER BY f.sort, f.id", (bid,))]
    lines = [f"이름: {b['name']}"]
    if b["creator"]:
        lines.append(f"만든 사람: {b['creator']}")
    lines.append(f"종류: 자료 · {names('itypes').get(item, item)}" if item else f"상태: {names('statuses').get(b['status'], b['status'])}")
    if tags := tags_of(b["tags"]):
        lines.append("태그: " + ", ".join(tags))
    if folders:
        lines.append("폴더: " + ", ".join(folders))
    for l in db.q("SELECT title, url FROM links WHERE bot_id=? ORDER BY sort, id", (bid,)):
        lines.append(f"링크: {l['title'] or ''} {l['url']}".replace("  ", " "))
    if (b["memo"] or "").strip():
        lines += ["", "메모", b["memo"].strip()]
    files = db.q("SELECT id, name, path, version_id FROM files WHERE bot_id=? ORDER BY created, id", (bid,))
    fname = lambda f: fnames.get(f["id"], f["name"]) if fnames else f["path"].rsplit("/", 1)[-1] if f["path"] else (f["name"] or "file")
    vers = db.q("SELECT id, name, released, current FROM versions WHERE bot_id=? ORDER BY created, id", (bid,))
    if vers:
        lines += ["", "버전"]
    for v in vers:
        tag = (vdir or {}).get(v["id"], f"v{v['id']}")
        extra = " · ".join(x for x in (v["released"], "지금 버전" if v["current"] else "") if x)
        lines.append(f"  {tag}/  {v['name'] or ''}" + (f"  ({extra})" if extra else ""))
        if fs := [fname(f) for f in files if f["version_id"] == v["id"]]:
            lines.append("      " + " · ".join(fs))
    if loose := [fname(f) for f in files if not f["version_id"]]:
        lines += ["", "버전 없이 둔 파일", "  " + " · ".join(loose)]
    lines += ["", "─" * 30, "봇카이브가 알아서 고쳐 쓰는 메모예요. 여기를 고쳐도 봇카이브에는 반영되지 않아요."]
    return "\n".join(lines) + "\n"


def write_info(bid):
    """봇 폴더에 info.txt (폴더가 있을 때만 — 파일 없는 봇은 폴더도 안 만듦)."""
    b = db.q("SELECT itype FROM bots WHERE id=?", (bid,))
    if not b:
        return
    home = DATA / bot_home(bid, b[0]["itype"] or "")
    if not home.is_dir():
        return
    txt, f = info_text(bid), home / "info.txt"
    try:
        if not f.is_file() or f.read_text(encoding="utf-8") != txt:
            f.write_text(txt, encoding="utf-8")
    except OSError as e:
        print(f"info.txt 오류 {bid}: {e!r}", flush=True)


def drop_home(bid):
    """봇을 지운 뒤 남은 info.txt와 빈 폴더 정리."""
    for itype in ("", "x"):
        home = DATA / bot_home(bid, itype)
        (home / "info.txt").unlink(missing_ok=True)
        prune(home)


def intro_media(html):
    return re.findall(r'/m/(' + MEDIA_RE + r')', html or "")


# ---- 소개글: 아카라이브 가져오기 + 붙여넣은 HTML 정리 ----
ALLOWED = {"p", "br", "span", "strong", "b", "em", "i", "u", "s", "del", "strike", "h1", "h2", "h3", "h4", "h5", "blockquote",
           "ul", "ol", "li", "a", "img", "video", "hr", "table", "thead", "tbody", "tr", "td", "th", "div", "figure", "figcaption",
           "sub", "sup", "code", "pre", "font", "details", "summary", "center",
           "section", "article", "header", "footer", "aside", "small", "mark", "label", "button"}
VOID = {"br", "img", "hr"}
DROP = {"script", "style", "iframe", "object", "embed", "noscript", "template", "svg", "math", "form", "input",
        "textarea", "select", "head", "title", "meta", "link", "audio", "canvas"}
DROP_VOID = {"meta", "link", "input"}
# 글 상자 모양(배경·테두리·여백·둥근 모서리·그라데이션·가로 배치)까지는 살리고,
# 자리를 빼앗는 것(position·z-index·transform)과 바깥 주소(url)는 막음
_SIDES = ("", "-top", "-right", "-bottom", "-left")
STYLE_OK = {"color", "background-color", "background", "background-image", "font-size", "font-weight", "font-style", "font-family",
            "text-align", "text-decoration", "text-shadow", "text-transform", "text-indent", "letter-spacing", "word-spacing",
            "line-height", "white-space", "vertical-align", "word-break", "opacity", "box-shadow", "box-sizing",
            "border-radius", "border-top-left-radius", "border-top-right-radius", "border-bottom-left-radius", "border-bottom-right-radius",
            "border-color", "border-style", "border-width", "border-collapse", "border-spacing",
            "width", "max-width", "min-width", "min-height", "display", "gap", "row-gap", "column-gap",
            "flex", "flex-direction", "flex-wrap", "flex-grow", "flex-shrink", "flex-basis", "justify-content", "align-items",
            "align-self", "grid-template-columns", "list-style", "list-style-type"} \
    | {f"{k}{side}" for k in ("border", "padding", "margin") for side in _SIDES}
DISPLAY_OK = {"block", "inline", "inline-block", "flex", "inline-flex", "grid", "none", "list-item", "table", "table-row", "table-cell"}
RENAME = {"font": "span", "center": "div", "strike": "s", "button": "span", "label": "span"}


def clean_style(s):
    out = []
    for part in (s or "").split(";"):
        k, _, v = part.partition(":")
        k, v = k.strip().lower(), v.strip()
        if k not in STYLE_OK or not v or len(v) > 300 or re.search(r"url|expression|javascript|[\\<>@{}]|/\*", v, re.I):
            continue
        if k == "display" and v.lower().replace("!important", "").strip() not in DISPLAY_OK:
            continue
        out.append(f"{k}: {v}")
    return "; ".join(out)[:4000]


def abs_url(u):
    u = (u or "").strip()
    if u.startswith("//"):
        u = "https:" + u
    return u


LAZY_SRC = ("data-src", "data-original", "data-lazy-src", "data-url")


def pick_src(a):
    """지연 로딩 그림은 src가 빈 자리표시(data:)이고 진짜 주소는 data-src 등에 있음."""
    src = (a.get("src") or "").strip()
    lazy = next((a[k].strip() for k in LAZY_SRC if (a.get(k) or "").strip()), "")
    if lazy and (not src or src.startswith("data:")):
        src = lazy
    return abs_url(src)


class Cleaner(HTMLParser):
    """허용한 태그·속성만 남김. 모르는 태그는 벗겨 내고 글자는 남긴다. src는 fix(url)로 바꿔 끼움(None이면 그림 빼기)."""

    def __init__(self, fix=None):
        super().__init__(convert_charrefs=True)
        self.fix, self.out, self.stack, self.drop, self.srcs = fix, [], [], 0, []

    def handle_starttag(self, tag, attrs):
        if tag in DROP or self.drop:
            if tag in DROP and tag not in DROP_VOID:
                self.drop += 1
            return
        if tag not in ALLOWED:
            return
        a = dict((k, v or "") for k, v in attrs)
        name = RENAME.get(tag, tag)
        keep = []
        style = clean_style(a.get("style", ""))
        if tag == "font" and re.fullmatch(r"#?[0-9A-Za-z]{3,20}", a.get("color", "")):
            style = f"color: {a['color']}" + (f"; {style}" if style else "")
        if tag == "center":
            style = "text-align: center" + (f"; {style}" if style else "")
        if tag == "button":  # 단추 모양은 줄 안 상자여야 위아래가 안 겹침
            style = "display: inline-block" + (f"; {style}" if style else "")
        if style:
            keep.append(("style", style))
        if tag == "a":
            href = abs_url(a.get("href"))
            if re.match(r"https?://", href):
                keep.append(("href", href))
        if tag in ("img", "video"):
            src = pick_src(a)
            if not src:
                return
            self.srcs.append(src)
            emoji = tag == "img" and bool(TWEMOJI_RE.search(src))
            if self.fix:
                orig, src = src, self.fix(src)
                if not src:  # 이모지 그림은 alt에 글자가 들어 있는 경우가 많음
                    alt = a.get("alt", "").strip() or twemoji_char(orig)
                    self.out.append(escape(alt[:20], quote=False) if alt and len(alt) <= 20 else '<span class="miss">[그림을 못 가져왔어요]</span>')
                    return
            keep.append(("src", src))
            if tag == "video":
                keep += [("loop", ""), ("muted", ""), ("autoplay", ""), ("playsinline", "")] if "autoplay" in a or "loop" in a else [("controls", "")]
            if a.get("alt"):
                keep.append(("alt", a["alt"][:200]))
            if emoji:
                keep.append(("class", "emoji"))
        if tag in ("td", "th"):
            for k in ("colspan", "rowspan"):
                if a.get(k, "").isdigit():
                    keep.append((k, a[k]))
        self.out.append(f"<{name}" + "".join(f' {k}="{escape(v)}"' if v else f" {k}" for k, v in keep) + ">")
        if tag not in VOID:
            self.stack.append(name)

    def handle_startendtag(self, tag, attrs):
        if tag in DROP or self.drop:
            return
        self.handle_starttag(tag, attrs)
        if tag not in VOID and tag in ALLOWED and self.stack and self.stack[-1] == RENAME.get(tag, tag):
            self.out.append(f"</{self.stack.pop()}>")

    def handle_endtag(self, tag):
        if self.drop:
            if tag in DROP:
                self.drop -= 1
            return
        name = RENAME.get(tag, tag)
        if tag in ALLOWED and tag not in VOID and name in self.stack:
            while self.stack:
                t = self.stack.pop()
                self.out.append(f"</{t}>")
                if t == name:
                    break

    def handle_data(self, data):
        if not self.drop:
            self.out.append(escape(data, quote=False))

    def result(self):
        self.close()
        while self.stack:
            self.out.append(f"</{self.stack.pop()}>")
        return "".join(self.out)


def safe_remote(url):
    """밖으로 나가는 요청은 https 공개 주소만 (내부망·자기 자신 금지)."""
    p = urlsplit(url)
    if p.scheme != "https" or not p.hostname:
        return False
    try:
        for info in socket.getaddrinfo(p.hostname, 443, proto=socket.IPPROTO_TCP):
            ip = ipaddress.ip_address(info[4][0])
            if not ip.is_global:
                return False
    except OSError:
        return False
    return True


def fetch(url, limit, referer="https://arca.live/"):
    if not safe_remote(url):
        raise ValueError("가져올 수 없는 주소")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": referer, "Accept-Language": "ko-KR,ko;q=0.9"})
    with urllib.request.urlopen(req, timeout=20) as r:
        if not safe_remote(r.geturl()):
            raise ValueError("가져올 수 없는 주소")
        ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        n = int(r.headers.get("Content-Length") or 0)
        if n > limit:
            raise ValueError("너무 큼")
        data = r.read(limit + 1)
        if len(data) > limit:
            raise ValueError("너무 큼")
        return data, ctype


def grab_media(url):
    """소개글 그림·영상을 받아 media에 저장. 같은 주소(쿼리 빼고)는 같은 파일."""
    try:
        data, ctype = fetch(url, MAX_REMOTE)
        ext = REMOTE_TYPES.get(ctype)
        if not ext:
            return None
        name = hashlib.sha1(data).hexdigest()[:20] + "." + ext
        f = MEDIA / name
        if not f.exists():
            f.write_bytes(data)
        return "/m/" + name
    except Exception as e:
        print(f"그림 받기 실패 {urlsplit(url).hostname}: {e!r}", flush=True)
        return None


def save_data_uri(u):
    """글 속에 그대로 들어 있는 그림(data:image/...;base64) → media."""
    m = re.match(r"^data:image/(png|jpe?g|gif|webp);base64,([A-Za-z0-9+/=\s]+)$", u, re.I)
    if not m:
        return None
    try:
        raw = base64.b64decode(m.group(2))
    except ValueError:
        return None
    if not 0 < len(raw) <= 15_000_000:
        return None
    ext = {"jpeg": "jpg"}.get(m.group(1).lower(), m.group(1).lower())
    name = hashlib.sha1(raw).hexdigest()[:20] + "." + ext
    f = MEDIA / name
    if not f.exists():
        f.write_bytes(raw)
    return "/m/" + name


def clean_intro(html, base=""):
    """붙여넣은/가져온 HTML → 허용 태그만 + 바깥 그림은 받아서 /m/ 로. base는 상대 주소를 풀 원문 주소."""
    probe = Cleaner()
    probe.feed(html or "")
    probe.result()

    def where(u):  # 받을 주소 (못 받는 종류면 None)
        m = TWEMOJI_RE.search(u)
        if m and not u.startswith("data:"):
            return TWEMOJI_PNG.format(m.group(1).lower())
        if u.startswith("http://"):
            return "https://" + u[7:]
        if u.startswith("https://"):
            return u
        if base and re.match(r"https?://", base) and not re.match(r"[a-z][a-z0-9+.-]*:", u, re.I):
            return "https://" + urljoin(base, u).split("://", 1)[1]
        return None

    srcs = list(dict.fromkeys(probe.srcs))
    remote = list(dict.fromkeys(w for w in map(where, srcs) if w))[:400]
    with ThreadPoolExecutor(6) as ex:
        got = dict(zip(remote, ex.map(grab_media, remote)))
    inline = {u: save_data_uri(u) for u in srcs if u.startswith("data:")}

    def fix(u):
        if re.fullmatch(r"/m/" + MEDIA_RE, u):
            return u
        return inline.get(u) or got.get(where(u) or "")

    miss = [u for u in srcs if not fix(u)]
    for u in miss[:20]:  # 다음에 원인 찾기 쉽게 어떤 주소였는지만 남김
        print(f"소개글 그림 못 받음: {u[:60]}", flush=True)

    c = Cleaner(fix)
    c.feed(html or "")
    out = c.result().strip()
    if len(out) > 3_000_000:
        raise ValueError("소개글이 너무 길어요")
    return out, len(srcs) - len(miss), len(miss)


def arca_article(page):
    """아카라이브 글 HTML → (제목, 글쓴이, 본문 HTML)."""
    m = re.search(r'<div class="[^"]*\barticle-content\b[^"]*"[^>]*>', page)
    if not m:
        return None
    depth, pos = 1, m.end()
    for t in re.finditer(r"<(/?)div\b[^>]*>", page[pos:]):
        depth += -1 if t.group(1) else 1
        if depth == 0:
            body = page[pos:pos + t.start()]
            break
    else:
        return None
    title = re.search(r'<meta property="og:title" content="([^"]*)"', page)
    title = unescape(title.group(1)) if title else ""
    title = re.sub(r"\s+-\s+[^-]+$", "", title).strip()
    head = page[page.find('class="article-head"'):][:20000]
    author = re.search(r'data-filter="([^"]+)"', head)
    return title, unescape(author.group(1)) if author else "", body


def fetch_arca(url):
    p = urlsplit(url.strip())
    if p.scheme not in ("http", "https") or p.hostname not in ("arca.live", "www.arca.live") or not re.match(r"/b/[\w-]+/\d+", p.path):
        raise LookupError("아카라이브 글 주소(arca.live/b/채널/번호)만 가져올 수 있어요. 다른 곳의 글은 붙여넣기로 넣어 주세요.")
    url = f"https://arca.live{p.path}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            page = r.read(8_000_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 451):
            raise LookupError("로그인해야 보이는 글(성인 글 등)이라 주소로는 못 가져와요. 글 화면에서 본문을 복사해 붙여넣어 주세요.")
        if e.code == 404:
            raise LookupError("글을 찾을 수 없어요. 지워졌거나 주소가 틀렸을 수 있어요.")
        raise LookupError(f"아카라이브가 {e.code}로 거절했어요. 잠시 뒤 다시 하거나 붙여넣기로 넣어 주세요.")
    except OSError:
        raise LookupError("아카라이브에 연결하지 못했어요. 잠시 뒤 다시 해 주세요.")
    art = arca_article(page)
    if not art:
        raise LookupError("글 본문을 찾지 못했어요. 붙여넣기로 넣어 주세요.")
    return url, art


# ---- 목록·상세 ----
def folders_of(bot_ids):
    if not bot_ids:
        return {}
    out = {}
    for r in db.q(f"SELECT bot_id, folder_id FROM bot_folders WHERE bot_id IN ({','.join('?' * len(bot_ids))})", bot_ids):
        out.setdefault(r["bot_id"], []).append(r["folder_id"])
    return out


def tags_of(raw):
    try:
        t = json.loads(raw or "[]")
    except ValueError:
        return []
    return [str(x) for x in t if str(x)] if isinstance(t, list) else []


# ---- 그림체 ----
def style_rows():
    rows = db.q("""SELECT s.id, s.name, s.creator, s.stype, s.tags, s.created, s.updated, s.opened,
                     (SELECT image FROM style_images i WHERE i.style_id=s.id ORDER BY sort, id LIMIT 1) AS cover,
                     (SELECT COUNT(*) FROM style_images i WHERE i.style_id=s.id) AS nimg,
                     (SELECT COUNT(*) FROM bot_styles b WHERE b.style_id=s.id) AS nbots
                   FROM styles s ORDER BY COALESCE(s.opened, s.updated) DESC""")
    fm = {}
    for r in db.q("SELECT style_id, folder_id FROM style_folders"):
        fm.setdefault(r["style_id"], []).append(r["folder_id"])
    for r in rows:
        r["tags"] = tags_of(r["tags"])
        r["folders"] = fm.get(r["id"], [])
    return rows


def style_detail(id):
    r = db.q("SELECT * FROM styles WHERE id=?", (id,))
    if not r:
        return None
    s = r[0]
    s["tags"] = tags_of(s["tags"])
    try:
        s["settings"] = json.loads(s["settings"] or "{}")
    except ValueError:
        s["settings"] = {}
    try:
        s["chars"] = json.loads(s.get("chars") or "[]")
    except ValueError:
        s["chars"] = []
    s["images"] = db.q("SELECT id, image, meta FROM style_images WHERE style_id=? ORDER BY sort, id", (id,))
    for i in s["images"]:
        try:
            i["meta"] = json.loads(i["meta"] or "{}")
        except ValueError:
            i["meta"] = {}
    s["folders"] = [x["folder_id"] for x in db.q("SELECT folder_id FROM style_folders WHERE style_id=?", (id,))]
    s["bots"] = db.q("""SELECT b.id, b.name, b.cover, bs.role FROM bot_styles bs JOIN bots b ON b.id=bs.bot_id
                        WHERE bs.style_id=? ORDER BY bs.role='official' DESC, b.name""", (id,))
    return s


def style_vals(d):
    vals = {k: str(d[k] or "").strip()[:n] for k, n in STYLE_FIELDS.items() if k in d}
    if "name" in vals and not vals["name"]:
        del vals["name"]
    if "stype" in d and db.q("SELECT 1 FROM stypes WHERE key=?", (str(d["stype"]),)):
        vals["stype"] = str(d["stype"])
    if isinstance(d.get("settings"), dict):
        vals["settings"] = json.dumps({str(k)[:40]: str(v)[:300] for k, v in list(d["settings"].items())[:24] if str(v or "").strip()}, ensure_ascii=False)
    if "tags" in d:
        vals["tags"] = json.dumps(clean_tags(d["tags"]), ensure_ascii=False)
    if isinstance(d.get("chars"), list):  # 캐릭터 칸: NAI는 6명까지
        cs = [{"prompt": str(c.get("prompt") or "").strip()[:5000], "negative": str(c.get("negative") or "").strip()[:2000]} for c in d["chars"] if isinstance(c, dict)]
        vals["chars"] = json.dumps([c for c in cs if c["prompt"] or c["negative"]][:6], ensure_ascii=False)
    return vals


def set_style_folders(sid, ids):
    ok = {f["id"] for f in db.q("SELECT id FROM folders WHERE scope='style'")}
    db.x("DELETE FROM style_folders WHERE style_id=?", (sid,))
    db.many("INSERT OR IGNORE INTO style_folders(style_id, folder_id) VALUES (?,?)", [(sid, int(i)) for i in ids if str(i).isdigit() and int(i) in ok])


def add_style_images(sid, imgs):
    """견본 그림 넣기 (data URL + 그림에서 읽은 프롬프트 같은 메타). 한 번에 40장까지."""
    n = db.q("SELECT COALESCE(MAX(sort), 0) AS n FROM style_images WHERE style_id=?", (sid,))[0]["n"]
    for x in (imgs if isinstance(imgs, list) else [])[:40]:
        if not isinstance(x, dict):
            continue
        name = save_data_url(x.get("data"))
        n += 1
        meta = json.dumps(x.get("meta") if isinstance(x.get("meta"), dict) else {}, ensure_ascii=False)[:30000]
        db.x("INSERT INTO style_images(style_id, image, sort, meta, created) VALUES (?,?,?,?,?)", (sid, name, n, meta, now()))
    db.x("UPDATE styles SET updated=? WHERE id=?", (now(), sid))


def new_style(d):
    vals = style_vals(d)
    vals.setdefault("name", "이름 없는 그림체")
    vals["created"] = vals["updated"] = vals["opened"] = now()
    sid, _ = db.x(f"INSERT INTO styles({', '.join(vals)}) VALUES ({','.join('?' * len(vals))})", tuple(vals.values()))
    set_style_folders(sid, d.get("folders") or [])
    add_style_images(sid, d.get("images"))
    return sid


STYLE_MIME = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}


def style_export(ids):
    """나눠 줄 그림체 파일 — 그림은 data URL로 넣음 (폴더·이은 봇은 빼고)."""
    out = []
    for i in ids:
        s = style_detail(i)
        if not s:
            continue
        imgs = []
        for g in s["images"]:
            ext = g["image"].rsplit(".", 1)[1]
            f = MEDIA / g["image"]
            if ext in STYLE_MIME and f.is_file():
                imgs.append({"data": f"data:{STYLE_MIME[ext]};base64,{base64.b64encode(f.read_bytes()).decode()}", "meta": g["meta"]})
        st = db.q("SELECT name FROM stypes WHERE key=?", (s["stype"],))
        out.append({k: s[k] for k in ("name", "creator", "source", "prompt", "negative", "chars", "settings", "memo", "tags")} | {"stype_name": st[0]["name"] if st else "", "images": imgs})
    return {"format": "botkive-style", "version": 1, "styles": out}


def style_import(d):
    if not isinstance(d, dict) or d.get("format") != "botkive-style" or not isinstance(d.get("styles"), list):
        raise ValueError("봇카이브 그림체 파일이 아니에요")
    ids = []
    for s in d["styles"][:200]:
        if not isinstance(s, dict):
            continue
        name = str(s.get("stype_name") or "").strip()[:12]
        hit = db.q("SELECT key FROM stypes WHERE name=?", (name,)) if name else []
        if not hit and name and db.q("SELECT COUNT(*) AS n FROM stypes")[0]["n"] < LABELS["stypes"][1]:  # 없는 분류는 더해 줌
            key = "g" + secrets.token_hex(4)
            db.x("INSERT INTO stypes(key, name, color, sort) VALUES (?,?,'#C7C5CC',(SELECT COALESCE(MAX(sort),0)+1 FROM stypes))", (key, name))
            hit = [{"key": key}]
        ids.append(new_style({**{k: s[k] for k in STYLE_FIELDS if k in s}, "settings": s.get("settings"), "chars": s.get("chars") or [], "tags": s.get("tags") or [],
                              "stype": hit[0]["key"] if hit else "etc", "images": s.get("images")}))
    return ids


# ---- 전부 내보내기: 봇카이브 없이도 열리는 폴더 + 다시 들이기용 봇카이브.json ----
def intro_doc(title, html):
    """소개글을 브라우저로 바로 열리는 문서로 (그림은 옆 '그림' 폴더)."""
    body = re.sub(r'/m/(' + MEDIA_RE + r')', r'그림/\1', html or "")
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{escape(title)}</title></head><body style="max-width:900px;margin:24px auto;padding:0 16px">{body}</body></html>')


def risu_chat(c):
    """리스의 채팅 불러오기로 다시 넣을 수 있는 risuChat (앱의 채팅 내려받기와 같은 모양)."""
    msgs = db.q("SELECT role, text, at FROM messages WHERE chat_id=? ORDER BY idx", (c["id"],))
    data = {"name": c["title"], "note": c["memo"] or "", "localLore": [], "fmIndex": -1,
            "message": [{"role": "user" if m["role"] == "user" else "char", "data": m["text"], **({"time": m["at"]} if m["at"] else {})} for m in msgs]}
    return json.dumps({"type": "risuChat", "ver": 1, "data": data}, ensure_ascii=False)


EXPORT_README = """봇카이브 내보내기

봇/<폴더>/<봇 이름>/       봇 하나. 폴더가 여러 개면 첫 폴더에, 없으면 '폴더 없음'에 있어요.
    info.txt              이름 · 만든 사람 · 상태 · 태그 · 폴더 · 링크 · 메모 · 버전 목록
    표지.*                 표지 그림
    <버전 이름>/           그 버전의 원본 파일(카드 · 모듈 · 프리셋 …)과 소개글(.html, 그림은 '그림' 폴더)
    버전 없이 둔 파일/
    채팅 로그/             리스 형식(.json) — 리스의 채팅 불러오기나 봇카이브에 다시 넣을 수 있어요
자료함/<종류>/<이름>/       자료함 자료 (봇과 같은 모양)
그림체/<분류>/<이름>/       프롬프트.txt · 샘플 그림 · .botkive-style.json(봇카이브 그림체 가져오기용)
봇카이브.json              위 내용을 기계가 읽는 목록 (나중에 통째로 다시 들이기용)

원본 파일은 올린 그대로예요. 봇카이브가 없어도 리스에 바로 넣을 수 있어요.
"""


def export_zip(out):
    """전부 내보내기를 zip으로 흘려보냄 (원본은 압축 없이 그대로 — 카드·그림은 이미 압축돼 있음)."""
    root = f"봇카이브 내보내기 {datetime.now(KST):%Y-%m-%d}"
    names = lambda t: {r["key"]: r["name"] for r in db.q(f"SELECT key, name FROM {t}")}
    statuses, itypes, stypes = names("statuses"), names("itypes"), names("stypes")
    folders = {r["id"]: r for r in db.q("SELECT id, name, scope FROM folders")}
    taken = {}  # 폴더 → 쓴 이름 (소문자)
    slot = lambda d, n: f"{d}/{free_name(safe_name(n, 'file'), taken.setdefault(d, set()))}"
    text = lambda arc, s: z.writestr(zipfile.ZipInfo(arc, time.localtime()[:6]), s, compress_type=zipfile.ZIP_DEFLATED)
    manifest = {"format": "botkive-export", "version": 1, "exported": now(), "statuses": statuses, "itypes": itypes, "stypes": stypes,
                "folders": [{"name": f["name"], "scope": f["scope"] or "bot"} for f in folders.values()], "bots": [], "styles": []}
    with zipfile.ZipFile(out, "w", allowZip64=True) as z:
        def media(arc, name):
            f = MEDIA / name if name and re.fullmatch(MEDIA_RE, name) else None
            if f and f.is_file():
                z.write(f, arc, compress_type=zipfile.ZIP_STORED)

        def intro(d, title, html):
            arc = slot(d, (title or "소개글") + ".html")
            text(arc, intro_doc(title or "소개글", html))
            seen = taken.setdefault(f"{d}/그림", set())
            for n in set(intro_media(html)) - seen:
                seen.add(n)
                media(f"{d}/그림/{n}", n)
            return arc.rsplit("/", 1)[1]

        for b in db.q("SELECT * FROM bots ORDER BY id"):
            item = b["itype"] or ""
            fl = [folders[r["folder_id"]]["name"] for r in db.q(
                "SELECT x.folder_id FROM bot_folders x JOIN folders f ON f.id=x.folder_id WHERE x.bot_id=? ORDER BY f.sort, f.id", (b["id"],))]
            group = f"자료함/{safe_name(itypes.get(item, item) or '기타')}" if item else f"봇/{safe_name(fl[0] if fl else '폴더 없음')}"
            bdir = slot(f"{root}/{group}", b["name"] or f"봇 {b['id']}")
            taken[bdir] = {"info.txt", "채팅 로그"}
            mb = {k: b[k] for k in ("name", "creator", "status", "itype", "in_risu", "memo", "created", "updated")} | {
                "tags": tags_of(b["tags"]), "folders": fl, "dir": bdir[len(root) + 1:], "versions": [], "loose": [], "chats": [],
                "links": db.q("SELECT title, url, note FROM links WHERE bot_id=? ORDER BY sort, id", (b["id"],))}
            if b["cover"]:
                arc = slot(bdir, "표지." + b["cover"].rsplit(".", 1)[1])
                media(arc, b["cover"])
                mb["cover"] = arc.rsplit("/", 1)[1]
            if (b["basic"] or "").strip():  # 모든 버전 공통 기본 소개
                mb["basic"] = intro(bdir, "기본 소개", b["basic"])
            files = db.q("SELECT id, kind, name, note, file, version_id FROM files WHERE bot_id=? ORDER BY created, id", (b["id"],))
            vdir, fnames = {}, {}

            def put(d, f):
                arc = slot(d, f["name"] or "file")
                p = fpath(f["file"])
                if p.is_file():
                    z.write(p, arc, compress_type=zipfile.ZIP_STORED)
                fnames[f["id"]] = arc.rsplit("/", 1)[1]
                return {"kind": f["kind"], "name": f["name"], "note": f["note"], "file": fnames[f["id"]]}

            for i, v in enumerate(db.q("SELECT * FROM versions WHERE bot_id=? ORDER BY created, id", (b["id"],)), 1):
                d = slot(bdir, v["name"] or f"버전 {i}")
                vdir[v["id"]] = d.rsplit("/", 1)[1]
                mv = {k: v[k] for k in ("name", "note", "released", "current", "created")} | {"dir": vdir[v["id"]], "info": v["info"], "files": [], "intros": []}
                mv["files"] = [put(d, f) for f in files if f["version_id"] == v["id"]]
                if (v["basic"] or "").strip():  # 이 버전 전용 기본 소개
                    mv["basic"] = intro(d, "기본 소개", v["basic"])
                for it in db.q("SELECT title, html, url, author, at FROM intros WHERE version_id=? ORDER BY sort, id", (v["id"],)):
                    if (it["html"] or "").strip():
                        mv["intros"].append({k: it[k] for k in ("title", "url", "author", "at")} | {"file": intro(d, it["title"] or "소개글", it["html"])})
                mb["versions"].append(mv)
            if loose := [f for f in files if not f["version_id"]]:
                d = slot(bdir, "버전 없이 둔 파일")
                mb["loose"] = [put(d, f) for f in loose]
            for c in db.q("SELECT id, title, memo, series, ep, source FROM chats WHERE bot_id=? ORDER BY first_at, id", (b["id"],)):
                arc = slot(f"{bdir}/채팅 로그", (c["title"] or "채팅 로그") + ".json")
                text(arc, risu_chat(c))
                marks = db.q("SELECT idx, memo FROM marks WHERE chat_id=? ORDER BY idx", (c["id"],))
                mb["chats"].append({k: c[k] for k in ("title", "memo", "series", "ep", "source")} | {"file": arc.rsplit("/", 1)[1], "marks": marks})
            text(f"{bdir}/info.txt", info_text(b["id"], vdir, fnames))
            manifest["bots"].append(mb)

        for s in db.q("SELECT id FROM styles ORDER BY id"):
            s = style_detail(s["id"])
            sdir = slot(f"{root}/그림체/{safe_name(stypes.get(s['stype'], '기타'))}", s["name"] or "그림체")
            lines = [f"이름: {s['name']}"] + [f"{k}: {s[c]}" for k, c in (("만든 사람", "creator"), ("출처", "source")) if s[c]]
            lines += ["", "프롬프트", s["prompt"] or "", "", "네거티브", s["negative"] or ""]
            for i, ch in enumerate(s["chars"] or [], 1):
                if isinstance(ch, dict):
                    lines += ["", f"캐릭터 {i}", str(ch.get("prompt") or ""), f"캐릭터 {i} 네거티브", str(ch.get("negative") or "")]
            if s["settings"]:
                lines += ["", "설정"] + [f"  {k}: {v}" for k, v in s["settings"].items()]
            if (s["memo"] or "").strip():
                lines += ["", "메모", s["memo"].strip()]
            text(f"{sdir}/프롬프트.txt", "\n".join(lines) + "\n")
            for i, g in enumerate(s["images"], 1):
                media(f"{sdir}/샘플 {i:02d}.{g['image'].rsplit('.', 1)[1]}", g["image"])
            text(f"{sdir}/{safe_name(s['name'] or '그림체')}.botkive-style.json", json.dumps(style_export([s["id"]]), ensure_ascii=False))
            linked = db.q("SELECT b.name, x.role FROM bot_styles x JOIN bots b ON b.id=x.bot_id WHERE x.style_id=?", (s["id"],))
            manifest["styles"].append({"name": s["name"], "dir": sdir[len(root) + 1:], "folders": [folders[i]["name"] for i in s["folders"] if i in folders], "bots": linked})
        text(f"{root}/읽어 주세요.txt", EXPORT_README)
        text(f"{root}/봇카이브.json", json.dumps(manifest, ensure_ascii=False, indent=1))


def clean_tags(v):
    """앞 # 떼고, 30자까지, 대소문자 무시 중복 빼고 30개까지."""
    out, seen = [], set()
    for x in v if isinstance(v, list) else []:
        t = re.sub(r"\s+", " ", str(x or "")).strip().lstrip("#").strip()[:30]
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:30]


def bot_summaries(folder=None, items=False):
    sql = """SELECT b.id, b.name, b.creator, b.status, b.itype, b.in_risu, b.cover, b.updated, b.opened, b.created, b.tags,
               (SELECT COUNT(*) FROM chats c WHERE c.bot_id=b.id) AS chats,
               (SELECT COUNT(*) FROM files f WHERE f.bot_id=b.id) AS files,
               (SELECT MAX(COALESCE(c.updated, c.created)) FROM chats c WHERE c.bot_id=b.id) AS chat_at,
               EXISTS(SELECT 1 FROM intros i JOIN versions v ON v.id=i.version_id WHERE v.bot_id=b.id) AS has_intro,
               (SELECT name FROM versions v WHERE v.bot_id=b.id AND v.current=1) AS version
             FROM bots b WHERE """ + ("COALESCE(b.itype, '') != ''" if items else "COALESCE(b.itype, '') = ''")
    args = ()
    if folder:
        sql += " AND b.id IN (SELECT bot_id FROM bot_folders WHERE folder_id=?)"
        args = (folder,)
    rows = db.q(sql + " ORDER BY COALESCE(b.opened, b.updated) DESC", args)
    fm = folders_of([r["id"] for r in rows])
    for r in rows:
        r["folders"] = fm.get(r["id"], [])
        r["has_intro"] = bool(r["has_intro"])
        r["tags"] = tags_of(r["tags"])
    return rows


def bot_detail(id):
    b = db.q("SELECT * FROM bots WHERE id=?", (id,))
    if not b:
        return None
    b = b[0]
    b["folders"] = folders_of([id]).get(id, [])
    b["links"] = db.q("SELECT * FROM links WHERE bot_id=? ORDER BY sort, id", (id,))
    b["files"] = db.q("SELECT * FROM files WHERE bot_id=? ORDER BY created DESC", (id,))
    b["versions"] = db.q("SELECT * FROM versions WHERE bot_id=? ORDER BY created DESC, id DESC", (id,))
    ins = db.q("""SELECT i.* FROM intros i JOIN versions v ON v.id=i.version_id WHERE v.bot_id=? ORDER BY i.sort, i.id""", (id,))
    for v in b["versions"]:
        v["intros"] = [i for i in ins if i["version_id"] == v["id"]]
    b["chats"] = chat_list(id)
    b["tags"] = tags_of(b.get("tags"))
    b["styles"] = db.q("""SELECT s.id, s.name, s.stype, bs.role, (SELECT image FROM style_images i WHERE i.style_id=s.id ORDER BY sort, id LIMIT 1) AS cover
                          FROM bot_styles bs JOIN styles s ON s.id=bs.style_id WHERE bs.bot_id=? ORDER BY bs.role='official' DESC, s.name""", (id,))
    try:
        b["rx"] = json.loads(b.get("rx") or "{}")
    except ValueError:
        b["rx"] = {}
    return b


# ---- 버전 (카드·모듈·소개글을 업데이트마다 묶음) ----
VER_FIELDS = {"name": 40, "note": 4000, "released": 20}


def version_of(vid, bot_id=None):
    v = db.q("SELECT * FROM versions WHERE id=?", (vid,)) if isinstance(vid, int) else []
    return v[0] if v and (bot_id is None or v[0]["bot_id"] == bot_id) else None


def set_current(vid):
    v = version_of(vid)
    if not v:
        return
    db.x("UPDATE versions SET current=CASE WHEN id=? THEN 1 ELSE 0 END WHERE bot_id=?", (vid, v["bot_id"]))
    if v["info"]:  # 오른쪽 '카드에서 읽은 것'은 지금 버전 기준
        db.x("UPDATE bots SET info=?, updated=? WHERE id=?", (json.dumps(v["info"], ensure_ascii=False), now(), v["bot_id"]))


def new_version(bot_id, name="", note="", released="", info=None, current=True):
    if not name:
        ver = str((info or {}).get("version") or "").strip()
        n = db.q("SELECT COUNT(*) AS n FROM versions WHERE bot_id=?", (bot_id,))[0]["n"]
        name = f"v{ver}" if ver else ("첫 버전" if not n else "{0.year}. {0.month}. {0.day}. 버전".format(datetime.now(KST)))
    vid, _ = db.x("INSERT INTO versions(bot_id, name, note, released, info, created) VALUES (?,?,?,?,?,?)",
                  (bot_id, name[:40], note[:4000], released[:20], json.dumps(info or {}, ensure_ascii=False)[:400_000], now()))
    if current or not db.q("SELECT 1 FROM versions WHERE bot_id=? AND current=1", (bot_id,)):
        set_current(vid)
    return vid


REALM_RE = re.compile(r"(?:https?://)?realm\.risuai\.net/character/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.I)


def add_realm_link(bot_id, html):
    """소개글에 랠름 주소가 있으면 주요 링크에 한 번만 등록 (이미 랠름 링크가 있으면 그대로)."""
    m = REALM_RE.search(html or "")
    if not m or db.q("SELECT 1 FROM links WHERE bot_id=? AND url LIKE '%realm.risuai.net/character/%'", (bot_id,)):
        return
    db.x("INSERT INTO links(bot_id, title, url, note, sort) VALUES (?,?,?,?,(SELECT COALESCE(MAX(sort),0)+1 FROM links WHERE bot_id=?))",
         (bot_id, "랠름", f"https://realm.risuai.net/character/{m.group(1).lower()}", "소개글에서 찾음", bot_id))


# ---- 카드 파일 들여다보기 (로어북·에셋) — 큰 charx(수백 MB)도 필요한 조각만 읽음 ----
ASSET_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp", "gif": "image/gif", "avif": "image/avif",
               "mp4": "video/mp4", "webm": "video/webm", "mp3": "audio/mpeg", "ogg": "audio/ogg", "wav": "audio/wav"}
_png_index = {}  # 파일 이름 → {키: (위치, 길이)} PNG 글 조각 자리 (에셋 하나 볼 때마다 전체를 훑지 않게)


def png_chunks(path):
    idx = {}
    with open(path, "rb") as fh:
        if fh.read(8) != b"\x89PNG\r\n\x1a\n":
            return idx
        while True:
            head = fh.read(8)
            if len(head) < 8:
                break
            n, typ = int.from_bytes(head[:4], "big"), head[4:]
            pos = fh.tell()
            if typ == b"tEXt":
                key = fh.read(min(n, 80)).split(b"\0", 1)[0]
                idx[key.decode("latin-1")] = (pos + len(key) + 1, n - len(key) - 1)
            if typ == b"IEND":
                break
            fh.seek(pos + n + 4)
    return idx


def png_text(path, key):
    idx = _png_index.get(path.name)
    if idx is None:
        idx = _png_index[path.name] = png_chunks(path)
        while len(_png_index) > 20:
            _png_index.pop(next(iter(_png_index)))
    if key not in idx:
        return None
    pos, n = idx[key]
    with open(path, "rb") as fh:
        fh.seek(pos)
        return fh.read(n)


def card_parts(fname):
    """→ (형식, 카드 JSON, 열린 zip 또는 None). 형식: zip(charx·jpeg 뒤 charx)·png·json"""
    path = fpath(fname)
    with open(path, "rb") as fh:
        sig = fh.read(4)
    if sig[:2] == b"\x89P":
        raw = png_text(path, "ccv3") or png_text(path, "chara")
        if not raw:
            raise ValueError("그림 안에 카드 정보가 없어요")
        return "png", json.loads(base64.b64decode(raw)), None
    if sig[:2] in (b"PK", b"\xff\xd8"):
        try:
            z = zipfile.ZipFile(path)
        except zipfile.BadZipFile:
            raise ValueError("카드를 열지 못했어요")
        if "card.json" not in z.namelist():
            z.close()
            raise ValueError("charx 안에 card.json이 없어요")
        return "zip", json.loads(z.read("card.json")), z
    if sig[:1] in (b"{", b"["):
        return "json", json.loads(path.read_text(encoding="utf-8")), None
    raise ValueError("카드 파일이 아니에요")


# 리스 모듈(.risum): [111][0][길이 4바이트 LE][rpack로 바꾼 JSON] 다음에 [1][길이][rpack 에셋]… [0]
# rpack = 256칸 바이트 치환표 (RisuAI src/ts/rpack/rpack_map.bin — 리스 밖에서는 AGPL-3.0, THIRD_PARTY_NOTICES.md 참고. 앞 256 = 인코딩, 뒤 256 = 디코딩)
_RPACK = APP / "rpack_map.bin"
RPACK_DEC = _RPACK.read_bytes()[256:512] if _RPACK.is_file() else None
_risum_index = {}  # 파일 이름 → [(위치, 길이)] 에셋 자리


def risum_main(fh):
    if RPACK_DEC is None:
        raise ValueError("모듈 읽기 표(rpack_map.bin)가 없어요")
    if fh.read(2) != b"\x6f\x00":
        raise ValueError("리스 모듈 파일이 아니에요")
    n = int.from_bytes(fh.read(4), "little")
    m = json.loads(fh.read(n).translate(RPACK_DEC))
    if not isinstance(m, dict) or m.get("type") != "risuModule":
        raise ValueError("리스 모듈 파일이 아니에요")
    return m.get("module") or {}, 6 + n


def is_risum(fname):
    with open(fpath(fname), "rb") as fh:
        return fh.read(2) == b"\x6f\x00"


def risum_assets_at(fname):
    """모듈 에셋 자리를 한 번 훑어 기억 (길이 머리만 읽고 건너뜀)."""
    if fname in _risum_index:
        return _risum_index[fname]
    out = []
    with open(fpath(fname), "rb") as fh:
        _, pos = risum_main(fh)
        fh.seek(pos)
        while (mark := fh.read(1)) == b"\x01":
            n = int.from_bytes(fh.read(4), "little")
            out.append((fh.tell(), n))
            fh.seek(n, 1)
    _risum_index[fname] = out
    while len(_risum_index) > 20:
        _risum_index.pop(next(iter(_risum_index)))
    return out


def mod_entry(e):
    mode = str(e.get("mode") or "normal")
    key = str(e.get("key") or "")
    folder = e.get("folder")
    return {"name": str(e.get("comment") or "")[:200], "keys": [] if mode == "folder" else [k.strip() for k in key.split(",") if k.strip()][:50],
            "secondary": [k.strip() for k in str(e.get("secondkey") or "").split(",") if k.strip()][:50], "content": str(e.get("content") or ""),
            "enabled": True, "constant": e.get("alwaysActive") in (True, "true", "True"), "order": e.get("insertorder"),
            "mode": mode, "fid": key if mode == "folder" else "", "folder": "" if folder in (None, "None") else str(folder)}


def file_module(fname):
    """→ 모듈 dict 또는 None (.risum 파일, 또는 charx 속 module.risum)."""
    if is_risum(fname):
        with open(fpath(fname), "rb") as fh:
            return risum_main(fh)[0]
    try:
        z = zipfile.ZipFile(fpath(fname))
    except (zipfile.BadZipFile, OSError):
        return None
    with z:
        if "module.risum" not in z.namelist():
            return None
        with z.open("module.risum") as fh:
            return risum_main(fh)[0]


# ---- 홈 숫자 ----
# 토큰은 어림값: 한글·한자·가나 1자 ≈ 1토큰, 영어·숫자 4자 ≈ 1토큰(단어마다 최소 1), 기호 2개 ≈ 1토큰. 모델마다 실제 값은 달라요
_TK_CJK = re.compile(r"[가-힣぀-ヿ一-鿿]")
_TK_WORD = re.compile(r"[A-Za-z0-9]+")
_TK_SYM = re.compile(r"[^\sA-Za-z0-9가-힣぀-ヿ一-鿿]")


def est_tokens(t):
    if not t:
        return 0
    return round(len(_TK_CJK.findall(t)) + sum(max(1.0, len(w) / 4) for w in _TK_WORD.findall(t)) + len(_TK_SYM.findall(t)) / 2)


_ext_re = re.compile(r"(\.(png|webp|jpe?g|gif|avif|mp4|webm|mp3|wav|ogg))+$")  # 카드는 에셋 이름에 확장자를 한 번 더 붙이기도 해서 (…webp.webp) 떼고 비교


def file_stat(fname):
    """카드·모듈 파일 하나의 로어북 항목(이름+내용 해시, 토큰)과 에셋 이름 해시. 파일은 안 바뀌니 한 번 세어 file_stats에 둠.
    해시로 두는 건 같은 봇의 카드 속 모듈과 따로 올린 모듈이 겹칠 때 한 번만 세려고."""
    r = db.q("SELECT data FROM file_stats WHERE file=?", (fname,))
    if r:
        d = json.loads(r[0]["data"])
        if d.get("v") == 3:
            return d
    hx = lambda *x: hashlib.sha1("|".join(map(str, x)).encode()).hexdigest()[:10]
    st = {"v": 3, "lore": [], "assets": []}
    try:
        for src in file_lore(fname)["sources"]:
            if src.get("pinned"):  # 카드 프롬프트(설명·글로벌 노트 등)는 로어북이 아님
                continue
            st["lore"] += [[hx(e.get("name"), e.get("content")), est_tokens(e.get("content"))] for e in src["entries"] if e.get("mode") != "folder"]
    except Exception:
        pass
    try:
        st["assets"] = [hx(_ext_re.sub("", str(a.get("name") or "").lower()) or f"#{i}") for src in file_assets(fname)["sources"] for i, a in enumerate(src["assets"])]
    except Exception:
        pass
    db.x("INSERT OR REPLACE INTO file_stats(file, data) VALUES (?,?)", (fname, json.dumps(st)))
    return st


def lib_stats():
    bots = db.q("SELECT id, status FROM bots WHERE COALESCE(itype, '') = ''")
    out = {"bots": len(bots), "status": {}, "lore_tokens": 0, "lore_entries": 0, "lore_bots": 0, "assets": 0, "asset_bots": 0}
    for b in bots:
        out["status"][b["status"]] = out["status"].get(b["status"], 0) + 1
        cur = current_version(b["id"], create=False)
        fs = db.q("SELECT file FROM files WHERE bot_id=? AND kind IN ('card', 'module') AND " + ("version_id=?" if cur else "version_id IS NULL"),
                  (b["id"], cur) if cur else (b["id"],))
        lore, assets = {}, set()  # 봇마다 겹치는 건 한 번만
        for f in fs:
            st = file_stat(f["file"])
            lore.update(dict(st["lore"]))
            assets.update(st["assets"])
        out["lore_tokens"] += sum(lore.values())
        out["lore_entries"] += len(lore)
        out["assets"] += len(assets)
        out["lore_bots"] += bool(lore)
        out["asset_bots"] += bool(assets)
    for c in db.q("SELECT id FROM chats WHERE tokens IS NULL"):  # 채팅 로그는 올린 뒤 안 바뀌니 한 번만 셈
        n = sum(est_tokens(m["text"]) for m in db.q("SELECT text FROM messages WHERE chat_id=?", (c["id"],)))
        db.x("UPDATE chats SET tokens=? WHERE id=?", (n, c["id"]))
    r = db.q("SELECT COUNT(*) AS n, COALESCE(SUM(tokens), 0) AS t, (SELECT COUNT(*) FROM messages) AS m FROM chats")[0]
    out.update(chats=r["n"], chat_tokens=r["t"], messages=r["m"])
    return out


def file_lore(fname):
    """카드 로어북 + 모듈 로어북을 출처별로."""
    srcs, name = [], ""
    mod = file_module(fname)
    mod_entries = [mod_entry(e) for e in (mod or {}).get("lorebook") or [] if isinstance(e, dict)]
    if not is_risum(fname):
        c = card_lore(fname)
        name = c["name"]
        seen = {(e["name"], e["content"]) for e in mod_entries}
        own = [e for e in c["entries"] if (e["name"], e["content"]) not in seen]  # 모듈을 charx로 내보낸 파일은 같은 걸 두 번 담기도 함
        if c["prompts"]:
            srcs.append({"label": "카드 프롬프트", "pinned": True, "entries": c["prompts"]})
        if own:
            srcs.append({"label": "카드 로어북", "entries": own})
    if mod_entries:
        srcs.append({"label": f"모듈 · {mod.get('name') or '이름 없음'}" if is_risum(fname) else "카드 속 모듈" if own else "카드 로어북", "entries": mod_entries})
    return {"name": name or str((mod or {}).get("name") or ""), "sources": srcs}


ASSET_CBS = re.compile(r"\{\{(?:raw|asset|image|img|emotion|path|source|bg)::[^}]*\}\}", re.I)


def img_only(out):
    """정규식 결과가 그림뿐인가 (에셋 표기·<style>·{{#if}} 같은 CBS·태그를 걷어내면 보이는 글자가 없음). 상태창처럼 글이 섞인 건 빼려고."""
    if not ASSET_CBS.search(out):
        return False
    rest = re.sub(r"<style[\s\S]*?</style>", "", ASSET_CBS.sub("", out), flags=re.I)
    for _ in range(10):  # {{#if {{greater_equal::{{chat_index}}::…}}}} 처럼 겹친 것은 안쪽부터
        rest, n = re.subn(r"\{\{[^{}]*\}\}", "", rest)
        if not n:
            break
    return not re.sub(r"\s|&nbsp;", "", re.sub(r"<[^>]*>", "", rest))


RX_MODES = ("off", "img", "imgall", "text", "hide")  # 안 씀(원문 그대로) · 그림만 · 그림 전부 · 글로 바꾸기 · 지우기


def display_regex(fname):
    """카드·모듈의 표시용 정규식(editdisplay) 전부 — 채팅 읽기에서 봇 전용 표기를 바꾸는 데 씀.
    auto = 그림만 넣는 것은 'img', 나머지(상태창 등 글이 섞인 것)는 'off'. 봇마다 bots.rx로 바꿀 수 있음."""
    scripts = []
    if not is_risum(fname):
        try:
            _, j, z = card_parts(fname)
            if z:
                z.close()
            d = j.get("data", j) if isinstance(j, dict) else {}
            scripts += ((d.get("extensions") or {}).get("risuai") or {}).get("customScripts") or []
        except (ValueError, OSError):
            pass
    try:
        scripts += (file_module(fname) or {}).get("regex") or []
    except Exception:
        pass
    out = []
    for s in scripts:
        if not (isinstance(s, dict) and s.get("type") == "editdisplay" and s.get("in")):
            continue
        rin, rout = str(s["in"]), str(s.get("out") or "")
        out.append({"key": hashlib.sha1((rin + "|" + rout).encode()).hexdigest()[:12], "comment": str(s.get("comment") or "")[:100],
                    "in": rin[:2000], "out": rout[:8000], "flag": str(s.get("flag") or "") if s.get("ableFlag") else "",
                    "auto": "img" if img_only(rout) else "off"})
    return out[:80]


def file_assets(fname):
    rx = display_regex(fname)
    if is_risum(fname):
        mod = file_module(fname) or {}
        at = risum_assets_at(fname)
        assets = [{"i": i, "type": "", "name": str(a[0] if isinstance(a, list) and a else "")[:200],
                   "ext": str(a[2] if isinstance(a, list) and len(a) > 2 else "").lower(), "here": i < len(at) and at[i][1] > 0, "url": ""}
                  for i, a in enumerate(mod.get("assets") or [])]
        return {"name": str(mod.get("name") or ""), "sources": [{"label": f"모듈 · {mod.get('name') or ''}", "kind": "m", "assets": assets}] if assets else [], "regex": rx}
    c = card_assets(fname)
    return {"name": c["name"], "sources": [{"label": "카드 에셋", "kind": "c", "assets": c["assets"]}] if c["assets"] else [], "regex": rx}


def card_lore(fname):
    _, j, z = card_parts(fname)
    if z:
        z.close()
    d = j.get("data", j) if isinstance(j, dict) else {}
    book = d.get("character_book") or {}
    out = []
    for e in book.get("entries") or []:
        if not isinstance(e, dict):
            continue
        ext = e.get("extensions") or {}
        keys = [str(k) for k in (e.get("keys") or []) if str(k)][:50]
        mode = str(e.get("mode") or "")  # 리스: mode 'folder' 항목이 폴더(키 첫 칸 = 폴더 id), 안에 든 항목은 folder = 그 id
        out.append({"name": str(e.get("comment") or e.get("name") or "")[:200], "keys": [] if mode == "folder" else keys,
                    "secondary": [str(k) for k in (e.get("secondary_keys") or []) if str(k)][:50], "content": str(e.get("content") or ""),
                    "enabled": e.get("enabled", True) is not False, "constant": bool(e.get("constant")), "order": e.get("insertion_order"),
                    "mode": mode, "fid": keys[0] if mode == "folder" and keys else "", "folder": str(e.get("folder") or ext.get("risu_folder") or "")})
    # 로어북 맨 위에 둘 카드 프롬프트 (리스: 캐릭터 설명 = 메인 프롬프트, 글로벌 노트 = post_history_instructions)
    prompts = [{"name": n, "keys": [], "secondary": [], "content": str(d.get(k) or ""), "enabled": True, "constant": False,
                "order": None, "mode": "prompt", "fid": "", "folder": ""}
               for k, n in (("system_prompt", "시스템 프롬프트"), ("description", "캐릭터 설명 (메인 프롬프트)"),
                            ("post_history_instructions", "글로벌 노트"), ("personality", "성격"), ("scenario", "시나리오"))
               if str(d.get(k) or "").strip()]
    return {"name": str(d.get("name") or ""), "book": str(book.get("name") or ""), "entries": out, "prompts": prompts}


def card_assets(fname):
    kind, j, z = card_parts(fname)
    d = j.get("data", j) if isinstance(j, dict) else {}
    names = set(z.namelist()) if z else set()
    if z:
        z.close()
    out = []
    for i, a in enumerate(d.get("assets") or []):
        if not isinstance(a, dict):
            continue
        uri, ext = str(a.get("uri") or ""), str(a.get("ext") or "").lower()
        here = (re.sub(r"^embed+ed://", "", uri) in names) if kind == "zip" else uri.startswith("__asset:") if kind == "png" else False
        out.append({"i": i, "type": str(a.get("type") or ""), "name": str(a.get("name") or "")[:200], "ext": ext,
                    "here": here, "url": uri if uri.startswith("https://") else ""})
    return {"name": str(d.get("name") or ""), "assets": out}


def intro_of(iid, bot_id=None):
    i = db.q("SELECT i.*, v.bot_id FROM intros i JOIN versions v ON v.id=i.version_id WHERE i.id=?", (iid,)) if isinstance(iid, int) else []
    return i[0] if i and (bot_id is None or i[0]["bot_id"] == bot_id) else None


def current_version(bot_id, create=True):
    v = db.q("SELECT id FROM versions WHERE bot_id=? AND current=1", (bot_id,))
    if v:
        return v[0]["id"]
    if not create:
        return None
    info = db.q("SELECT info FROM bots WHERE id=?", (bot_id,))
    return new_version(bot_id, info=info[0]["info"] if info else {})


def chat_list(bot_id=None):
    sql = """SELECT c.id, c.bot_id, c.title, c.memo, c.source, c.count, c.first_at, c.last_at, c.created, c.updated, COALESCE(c.series, '') AS series, c.ep,
               b.name AS bot_name, b.cover AS bot_cover,
               (SELECT COUNT(*) FROM marks m WHERE m.chat_id=c.id) AS marks,
               (SELECT COUNT(*) FROM marks m WHERE m.chat_id=c.id AND m.image IS NOT NULL) AS pics
             FROM chats c JOIN bots b ON b.id=c.bot_id"""
    if bot_id:
        return db.q(sql + " WHERE c.bot_id=? ORDER BY COALESCE(c.last_at, 0) DESC, c.id DESC", (bot_id,))
    return db.q(sql + " ORDER BY COALESCE(c.updated, c.created) DESC")


def recent_marks(limit=12):
    return db.q("""SELECT m.chat_id, m.idx, m.memo, m.image, m.created, c.title AS chat_title, b.id AS bot_id, b.name AS bot_name,
                     substr(g.text, 1, 160) AS text, g.role
                   FROM marks m JOIN chats c ON c.id=m.chat_id JOIN bots b ON b.id=c.bot_id
                   LEFT JOIN messages g ON g.chat_id=m.chat_id AND g.idx=m.idx
                   ORDER BY m.created DESC LIMIT ?""", (limit,))


def state():
    return {
        "folders": db.q("""SELECT f.*, (SELECT COUNT(*) FROM bot_folders bf WHERE bf.folder_id=f.id) + (SELECT COUNT(*) FROM style_folders sf WHERE sf.folder_id=f.id) AS count
                           FROM folders f ORDER BY sort, id"""),
        "statuses": db.q("""SELECT s.*, (SELECT COUNT(*) FROM bots b WHERE b.status=s.key AND COALESCE(b.itype, '')='') AS count
                            FROM statuses s ORDER BY sort, key"""),
        "itypes": db.q("""SELECT t.*, (SELECT COUNT(*) FROM bots b WHERE b.itype=t.key) AS count
                          FROM itypes t ORDER BY sort, key"""),
        "items": db.q("SELECT COUNT(*) AS n FROM bots WHERE COALESCE(itype, '') != ''")[0]["n"],
        "stypes": db.q("""SELECT t.*, (SELECT COUNT(*) FROM styles s WHERE s.stype=t.key) AS count FROM stypes t ORDER BY sort, key"""),
        "styles": db.q("SELECT COUNT(*) AS n FROM styles")[0]["n"],
        "shelves": db.q("""SELECT s.*, (SELECT COUNT(*) FROM files f WHERE f.shelf_id=s.id AND f.bot_id IS NULL) AS count
                           FROM shelves s ORDER BY sort, id"""),
        "bots": db.q("SELECT COUNT(*) AS n FROM bots WHERE COALESCE(itype, '') = ''")[0]["n"],
        "chats": db.q("SELECT COUNT(*) AS n FROM chats")[0]["n"],
        "loose": db.q("SELECT COUNT(*) AS n FROM files WHERE bot_id IS NULL")[0]["n"],
        "colors": sorted(COLORS),
    }


def clean_messages(msgs):
    out = []
    for i, m in enumerate(msgs[:200_000]):
        if not isinstance(m, dict):
            continue
        role = "user" if m.get("r") == "user" else "char"
        at = m.get("at")
        out.append((i, role, str(m.get("n") or "")[:80], str(m.get("t") or "")[:400_000], int(at) if isinstance(at, (int, float)) and at > 0 else None))
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "botshelf/1"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def send(self, code, body, ctype="application/json; charset=utf-8", cache="no-store", headers=()):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        for k, v in headers:
            self.send_header(k, v)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", cache)
        self.send_header("Content-Length", str(len(body)))
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        if ctype.startswith("text/html"):
            self.send_header("Content-Security-Policy", CSP)
        self.end_headers()
        self.wfile.write(body)

    def relay_realm(self, rid):
        """랠름 카드 받기 — 주소는 realm.risuai.net 고정 + uuid만 받으니 다른 곳으로는 못 나감. 메모리에 쌓지 않고 1MB씩 흘려보냄."""
        if not re.fullmatch(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}", rid):
            return self.send(400, {"error": "랠름 주소가 아니에요"})
        last = "랠름에서 받지 못했어요"
        for kind, ext in (("charx-v3", "charx"), ("png-v3", "png"), ("json-v3", "json")):
            req = urllib.request.Request(f"https://realm.risuai.net/api/v1/download/{kind}/{rid.lower()}?non_commercial=true", headers={"User-Agent": UA})
            try:
                r = urllib.request.urlopen(req, timeout=30)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return self.send(404, {"error": "랠름에 없는 캐릭터예요 (지워졌거나 비공개)"})
                last = f"랠름이 내려받기를 막았어요 ({e.code})"
                continue
            except (urllib.error.URLError, TimeoutError) as e:
                return self.send(502, {"error": f"랠름에 연결하지 못했어요: {e}"})
            with r:
                n = int(r.headers.get("Content-Length") or 0)
                if n > MAX_FILE:
                    return self.send(413, {"error": "카드가 너무 커요"})
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("X-Ext", ext)
                if n:
                    self.send_header("Content-Length", str(n))
                self.send_header("Cache-Control", "no-store")
                for k, v in SECURITY_HEADERS.items():
                    self.send_header(k, v)
                if not n:  # 길이를 모르면 끝을 연결 끊기로 알림
                    self.close_connection = True
                    self.send_header("Connection", "close")
                self.end_headers()
                while chunk := r.read(1 << 20):
                    self.wfile.write(chunk)
            return
        return self.send(403, {"error": last})

    def send_mod_asset(self, fname, i):
        at = risum_assets_at(fname)
        if not 0 <= i < len(at):
            return self.send(404, {"error": "에셋이 없어요"})
        mod = file_module(fname) or {}
        a = (mod.get("assets") or [])[i] if i < len(mod.get("assets") or []) else []
        ext = str(a[2] if isinstance(a, list) and len(a) > 2 else "").lower()
        pos, n = at[i]
        with open(fpath(fname), "rb") as fh:
            fh.seek(pos)
            data = fh.read(n).translate(RPACK_DEC)
        return self.send(200, data, ASSET_TYPES.get(ext, "application/octet-stream"), "private, max-age=31536000, immutable")

    def send_card_asset(self, fname, i):
        kind, j, z = card_parts(fname)
        try:
            d = j.get("data", j) if isinstance(j, dict) else {}
            assets = d.get("assets") or []
            if not 0 <= i < len(assets) or not isinstance(assets[i], dict):
                return self.send(404, {"error": "에셋이 없어요"})
            a = assets[i]
            uri, ext = str(a.get("uri") or ""), str(a.get("ext") or "").lower()
            ctype = ASSET_TYPES.get(ext, "application/octet-stream")
            if kind == "png" and uri.startswith("__asset:"):
                path = fpath(fname)
                raw = png_text(path, "chara-ext-asset_:" + uri[8:]) or png_text(path, "chara-ext-asset_" + uri[8:])
                if raw is None:
                    return self.send(404, {"error": "에셋이 없어요"})
                return self.send(200, base64.b64decode(raw), ctype, "private, max-age=31536000, immutable")
            if kind != "zip":
                return self.send(404, {"error": "파일 안에 든 에셋이 아니에요"})
            member = re.sub(r"^embed+ed://", "", uri)
            try:
                info = z.getinfo(member)
            except KeyError:
                return self.send(404, {"error": "에셋이 없어요"})
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(info.file_size))
            self.send_header("Cache-Control", "private, max-age=31536000, immutable")  # 올린 파일은 바뀌지 않음
            for k, v in SECURITY_HEADERS.items():
                self.send_header(k, v)
            self.end_headers()
            with z.open(info) as src:
                while chunk := src.read(1 << 20):
                    self.wfile.write(chunk)
        finally:
            if z:
                z.close()

    def send_export(self):
        """전부 내보내기 zip — 크기를 미리 모르니 길이 없이 보내고 연결을 닫아 끝을 알림."""
        self.close_connection = True
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Cache-Control", "no-store")
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        name = f"봇카이브 내보내기 {datetime.now(KST):%Y-%m-%d}.zip"
        self.send_header("Content-Disposition", f"attachment; filename=\"botkive-export.zip\"; filename*=UTF-8''{quote(name)}")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            export_zip(self.wfile)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            print(f"내보내기 오류: {e!r}", flush=True)

    def send_file(self, f, ctype, download=None):
        if not f.is_file():
            return self.send(404, {"error": "없음"})
        size = f.stat().st_size
        start, end = 0, size - 1
        rng = None if download else re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if rng and size:
            a, b = rng.groups()
            if a:
                start = int(a)
                end = min(int(b) if b else start + RANGE_CHUNK - 1, size - 1)
            elif b:
                start, end = max(0, size - int(b)), size - 1
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        length = end - start + 1
        self.send_response(206 if rng else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "private, max-age=31536000, immutable" if not download else "no-store")
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if download:
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(download)}")
        if rng:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(f, "rb") as fh:
            fh.seek(start)
            left = length
            while left > 0:
                chunk = fh.read(min(1 << 20, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                left -= len(chunk)

    def body(self):
        n = int(self.headers.get("Content-Length", "0"))
        if n > MAX_BODY:
            raise ValueError("too large")
        d = json.loads(self.rfile.read(n) or b"{}")
        if not isinstance(d, dict):
            raise ValueError("bad json")
        return d

    def route(self):
        path, _, qs = self.path.partition("?")
        params = dict(p.split("=", 1) if "=" in p else (p, "") for p in qs.split("&") if p)
        params = {k: unquote_plus(v) for k, v in params.items()}
        return [unquote(p) for p in path.split("/") if p], params

    # ---- 잠금 ----
    def is_local(self):
        """이 컴퓨터에서 바로 연 요청인지 (프록시 표시가 없고 루프백·도커 게이트웨이에서 옴)."""
        if any(self.headers.get(k) for k in FWD_HEADERS):
            return False
        ip = self.client_address[0]
        return (ip[7:] if ip.startswith("::ffff:") else ip) in LOCAL_PEERS

    def peer(self):
        return (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip() or self.client_address[0]

    def session_ok(self):
        c = SimpleCookie()
        try:
            c.load(self.headers.get("Cookie") or "")
        except Exception:
            return False
        t = c.get(COOKIE)
        return bool(t and db.q("SELECT 1 FROM sessions WHERE token=? AND expires>?", (tok_hash(t.value), time.time())))

    def need_login(self):
        mode = setting("auth_mode", "off")
        if mode not in ("remote", "always") or not setting("auth_hash"):
            return False
        return not (mode == "remote" and self.is_local())

    def authed(self):
        return not self.need_login() or self.session_ok()

    def gate(self):
        """잠겨 있고 로그인 안 했으면 401 보내고 False."""
        if self.authed():
            return True
        self.close_connection = True  # 올리던 본문을 안 읽고 끊음
        self.send(401, {"error": "로그인이 필요해요", "login": True})
        return False

    def new_session(self):
        t = secrets.token_urlsafe(32)
        db.x("DELETE FROM sessions WHERE expires<?", (time.time(),))
        db.x("INSERT INTO sessions(token, created, expires) VALUES (?,?,?)", (tok_hash(t), now(), time.time() + SESSION_DAYS * 86400))
        secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
        return ("Set-Cookie", f"{COOKIE}={t}; Path=/; Max-Age={SESSION_DAYS * 86400}; HttpOnly; SameSite=Strict{secure}")

    def too_many(self):
        with _fails_lock:
            l = [x for x in _fails.get(self.peer(), []) if x > time.time() - 300]
            _fails[self.peer()] = l
            return len(l) >= 5

    def failed(self):
        with _fails_lock:
            _fails.setdefault(self.peer(), []).append(time.time())

    def auth_info(self):
        return {"mode": setting("auth_mode", "off"), "has_password": bool(setting("auth_hash")), "local": self.is_local(),
                "need": self.need_login(), "authed": self.authed(), "session": self.session_ok()}

    def auth_post(self, p, d):
        if p == ["auth", "login"]:
            if self.too_many():
                return self.send(429, {"error": "너무 많이 틀렸어요. 5분 뒤에 다시 해 보세요"})
            if not setting("auth_hash") or not pw_ok(d.get("password"), setting("auth_hash")):
                self.failed()
                time.sleep(0.5)
                return self.send(403, {"error": "비밀번호가 맞지 않아요"})
            with _fails_lock:
                _fails.pop(self.peer(), None)
            return self.send(200, {"ok": True}, headers=[self.new_session()])
        c = SimpleCookie()  # logout
        try:
            c.load(self.headers.get("Cookie") or "")
        except Exception:
            pass
        if c.get(COOKIE):
            db.x("DELETE FROM sessions WHERE token=?", (tok_hash(c[COOKIE].value),))
        return self.send(200, {"ok": True}, headers=[("Set-Cookie", f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict")])

    def auth_put(self, d):
        """잠금 바꾸기. 비밀번호가 있으면 지금 비밀번호를 꼭 확인."""
        has = setting("auth_hash")
        if has:
            if self.too_many():
                return self.send(429, {"error": "너무 많이 틀렸어요. 5분 뒤에 다시 해 보세요"})
            if not pw_ok(d.get("current"), has):
                self.failed()
                return self.send(403, {"error": "지금 비밀번호가 맞지 않아요"})
        new = str(d.get("password") or "")
        if new and len(new) < 6:
            return self.send(400, {"error": "비밀번호는 6자 이상으로 해 주세요"})
        mode = d.get("mode") if d.get("mode") in AUTH_MODES else setting("auth_mode", "off")
        if mode != "off" and not (new or has):
            return self.send(400, {"error": "먼저 비밀번호를 정해 주세요"})
        if new:
            set_setting("auth_hash", pw_hash(new))
            db.x("DELETE FROM sessions")  # 비밀번호를 바꾸면 다른 기기 로그인은 모두 풀림
        set_setting("auth_mode", mode)
        return self.send(200, {"ok": True}, headers=[self.new_session()] if mode != "off" else [])

    def write_ok(self):
        if self.headers.get("X-BS") != "1":
            self.close_connection = True
            self.send(403, {"error": "잘못된 요청"})
            return False
        return True

    def do_GET(self):
        parts, params = self.route()
        try:
            if not parts or parts == ["index.html"]:
                return self.send(200, (APP / "index.html").read_bytes(), "text/html; charset=utf-8", "no-cache")
            if parts == ["api", "auth"]:
                return self.send(200, self.auth_info())
            if parts == ["api", "health"] and not self.authed():
                return self.send(200, {"ok": True, "locked": True})
            if not self.gate():
                return
            if parts[0] == "m" and len(parts) == 2 and re.fullmatch(MEDIA_RE, parts[1]):
                return self.send_file(MEDIA / parts[1], CTYPES[parts[1].rsplit(".", 1)[1]])
            if parts[0] == "f" and len(parts) == 2 and re.fullmatch(FILE_RE, parts[1]):
                r = db.q("SELECT name FROM files WHERE file=?", (parts[1],))
                if not r:
                    return self.send(404, {"error": "없음"})
                return self.send_file(fpath(parts[1]), "application/octet-stream", r[0]["name"] or "file")
            if parts[0] != "api":
                return self.send(404, {"error": "없음"})
            p = parts[1:]
            if len(p) == 2 and p[0] == "realm":
                if not self.write_ok():  # 바깥으로 나가는 요청이라 앱에서 부른 것만
                    return
                return self.relay_realm(p[1])
            if p == ["health"]:
                return self.send(200, {"ok": True, "bots": db.q("SELECT COUNT(*) AS n FROM bots")[0]["n"], "chats": db.q("SELECT COUNT(*) AS n FROM chats")[0]["n"]})
            if p == ["stats"]:
                return self.send(200, lib_stats())
            if p == ["state"]:
                return self.send(200, state())
            if p == ["bots"]:
                rows = bot_summaries(int(params["folder"]) if params.get("folder", "").isdigit() else None, params.get("items") == "1")
                return self.send(200, rows)
            if p == ["styles"]:
                return self.send(200, style_rows())
            if p == ["export"]:
                return self.send_export()
            if p == ["styles", "export"]:
                ids = [int(x) for x in params.get("ids", "").split(",") if x.isdigit()]
                one = style_detail(ids[0]) if len(ids) == 1 else None
                fname = f"{one['name'] if one else f'그림체 {len(ids)}개'}.botkive-style.json"
                return self.send(200, json.dumps(style_export(ids), ensure_ascii=False).encode(), cache="no-store",
                                 headers=[("Content-Disposition", f"attachment; filename=\"style.json\"; filename*=UTF-8''{quote(fname)}")])
            if len(p) == 2 and p[0] == "styles" and p[1].isdigit():
                s = style_detail(int(p[1]))
                if not s:
                    return self.send(404, {"error": "그림체가 없어요"})
                if params.get("open"):
                    db.x("UPDATE styles SET opened=? WHERE id=?", (now(), s["id"]))
                return self.send(200, s)
            if len(p) == 2 and p[0] == "bots" and p[1].isdigit():
                b = bot_detail(int(p[1]))
                if not b:
                    return self.send(404, {"error": "봇이 없어요"})
                if params.get("open"):
                    db.x("UPDATE bots SET opened=? WHERE id=?", (now(), b["id"]))
                return self.send(200, b)
            if len(p) in (3, 4) and p[0] == "files" and p[1].isdigit() and p[2] in ("lore", "assets", "asset", "masset"):
                f = db.q("SELECT file FROM files WHERE id=?", (int(p[1]),))
                if not f:
                    return self.send(404, {"error": "파일이 없어요"})
                try:
                    if p[2] == "lore" and len(p) == 3:
                        return self.send(200, file_lore(f[0]["file"]))
                    if p[2] == "assets" and len(p) == 3:
                        return self.send(200, file_assets(f[0]["file"]))
                    if p[2] == "masset" and len(p) == 4 and p[3].isdigit():
                        return self.send_mod_asset(f[0]["file"], int(p[3]))
                    if p[2] == "asset" and len(p) == 4 and p[3].isdigit():
                        return self.send_card_asset(f[0]["file"], int(p[3]))
                except (ValueError, json.JSONDecodeError, OSError, zipfile.BadZipFile) as e:
                    return self.send(422, {"error": str(e) or "카드를 읽지 못했어요"})
                return self.send(404, {"error": "없음"})
            if p == ["files"]:
                return self.send(200, db.q("""SELECT f.*, b.name AS bot_name FROM files f LEFT JOIN bots b ON b.id=f.bot_id
                                              ORDER BY f.created DESC"""))
            if p == ["chats"]:
                bid = int(params["bot"]) if params.get("bot", "").isdigit() else None
                return self.send(200, {"chats": chat_list(bid), "marks": [] if bid else recent_marks()})
            if len(p) == 2 and p[0] == "chats" and p[1].isdigit():
                c = chat_list()
                c = [x for x in c if x["id"] == int(p[1])]
                if not c:
                    return self.send(404, {"error": "채팅 로그가 없어요"})
                c = c[0]
                c["messages"] = db.q("SELECT idx, role, name, text, at FROM messages WHERE chat_id=? ORDER BY idx", (c["id"],))
                c["marks"] = db.q("SELECT idx, memo, image, created FROM marks WHERE chat_id=?", (c["id"],))
                return self.send(200, c)
            return self.send(404, {"error": "없음"})
        except Exception as e:
            self.send(500, {"error": repr(e)})

    def do_POST(self):
        parts, _ = self.route()
        try:
            if not self.write_ok():
                return
            d = self.body()
            p = parts[1:] if parts[:1] == ["api"] else None
            if p in (["auth", "login"], ["auth", "logout"]):
                return self.auth_post(p, d)
            if not self.gate():
                return
            if p == ["styles"]:
                return self.send(200, style_detail(new_style(d)))
            if p == ["styles", "import"]:
                ids = style_import(d)
                return self.send(200, {"ok": True, "ids": ids})
            if p and len(p) == 3 and p[0] == "styles" and p[1].isdigit() and p[2] in ("images", "bots"):
                sid = int(p[1])
                if not db.q("SELECT 1 FROM styles WHERE id=?", (sid,)):
                    return self.send(404, {"error": "그림체가 없어요"})
                if p[2] == "images":
                    add_style_images(sid, d.get("images"))
                else:
                    bid = d.get("bot_id")
                    if not isinstance(bid, int) or not db.q("SELECT 1 FROM bots WHERE id=?", (bid,)):
                        return self.send(404, {"error": "봇이 없어요"})
                    db.x("INSERT INTO bot_styles(bot_id, style_id, role) VALUES (?,?,?) ON CONFLICT(bot_id, style_id) DO UPDATE SET role=excluded.role",
                         (bid, sid, "official" if d.get("role") == "official" else "mine"))
                return self.send(200, style_detail(sid))
            if p == ["bots"]:
                vals = clean(d, BOT_FIELDS)
                vals.setdefault("name", "이름 없는 봇")
                vals.setdefault("status", "later")
                if d.get("cover"):
                    vals["cover"] = save_data_url(d["cover"])
                vals["created"] = vals["updated"] = vals["opened"] = now()
                cols = ", ".join(vals)
                bid, _ = db.x(f"INSERT INTO bots({cols}) VALUES ({','.join('?' * len(vals))})", tuple(vals.values()))
                set_folders(bid, d.get("folders") or [])
                return self.send(200, bot_detail(bid))
            if p and len(p) == 3 and p[0] == "bots" and p[1].isdigit() and p[2] == "rx":  # 로그 표시 규칙 하나 바꾸기 (mode 'auto' = 직접 고른 것 지움)
                b = db.q("SELECT rx FROM bots WHERE id=?", (int(p[1]),))
                key, mode = str(d.get("key") or "")[:12], d.get("mode")
                if not b or not re.fullmatch(r"[0-9a-f]{12}", key):
                    return self.send(404, {"error": "규칙이 없어요"})
                try:
                    rx = json.loads(b[0]["rx"] or "{}")
                except ValueError:
                    rx = {}
                if mode in RX_MODES:
                    rx[key] = mode
                else:
                    rx.pop(key, None)
                db.x("UPDATE bots SET rx=? WHERE id=?", (json.dumps(rx), int(p[1])))
                return self.send(200, {"ok": True, "rx": rx})
            if p and len(p) == 3 and p[0] == "bots" and p[1].isdigit() and p[2] == "basic":
                bid = int(p[1])
                b = db.q("SELECT basic FROM bots WHERE id=?", (bid,))
                if not b:
                    return self.send(404, {"error": "봇이 없어요"})
                v = version_of(d.get("version_id"), bid)
                raw = str(d.get("html") or "")
                html, ok, miss = clean_intro(raw) if raw.strip() else ("", 0, 0)
                old = ""
                if d.get("scope") == "ver":
                    if not v:
                        return self.send(404, {"error": "버전이 없어요"})
                    old = v["basic"]
                    db.x("UPDATE versions SET basic=? WHERE id=?", (html, v["id"]))
                else:
                    old = b[0]["basic"]
                    db.x("UPDATE bots SET basic=?, updated=? WHERE id=?", (html, now(), bid))
                    if v and v["basic"]:  # 공통으로 쓰면 그 버전 전용 글은 걷어 냄
                        old += v["basic"]
                        db.x("UPDATE versions SET basic='' WHERE id=?", (v["id"],))
                self.gc_intro(old)
                add_realm_link(bid, html)
                return self.send(200, {"ok": True, "got": ok, "miss": miss, "bot": bot_detail(bid)})
            if p and len(p) in (3, 4) and p[0] == "bots" and p[1].isdigit() and p[2] == "intro" and p[3:] in ([], ["fetch"]):
                bid = int(p[1])
                if not db.q("SELECT 1 FROM bots WHERE id=?", (bid,)):
                    return self.send(404, {"error": "봇이 없어요"})
                if p[3:] == ["fetch"]:
                    try:
                        url, (title, author, body) = fetch_arca(str(d.get("url") or ""))
                    except LookupError as e:
                        return self.send(422, {"error": str(e)})
                else:
                    url, title, author, body = str(d.get("url") or "")[:300], str(d.get("title") or ""), str(d.get("author") or ""), str(d.get("html") or "")
                html, ok, miss = clean_intro(body, url)
                old = intro_of(d.get("intro_id"), bid)
                if old:  # 그 글을 새로 넣기
                    iid, vid = old["id"], old["version_id"]
                    db.x("UPDATE intros SET title=?, html=?, url=?, author=?, at=? WHERE id=?",
                         (title[:300] or old["title"], html, url, author[:100], now(), iid))
                    self.gc_intro(old["html"])
                else:
                    v = version_of(d.get("version_id"), bid)
                    vid = v["id"] if v else current_version(bid)
                    n = db.q("SELECT COALESCE(MAX(sort), 0) + 1 AS n FROM intros WHERE version_id=?", (vid,))[0]["n"]
                    iid, _ = db.x("INSERT INTO intros(version_id, title, html, url, author, at, sort) VALUES (?,?,?,?,?,?,?)",
                                  (vid, title[:300], html, url, author[:100], now(), n))
                db.x("UPDATE bots SET updated=? WHERE id=?", (now(), bid))
                add_realm_link(bid, html)
                return self.send(200, {"ok": True, "got": ok, "miss": miss, "version_id": vid, "intro_id": iid, "bot": bot_detail(bid)})
            if p == ["versions"]:
                bid = d.get("bot_id")
                if not isinstance(bid, int) or not db.q("SELECT 1 FROM bots WHERE id=?", (bid,)):
                    return self.send(404, {"error": "봇이 없어요"})
                vid = new_version(bid, str(d.get("name") or "").strip(), str(d.get("note") or "").strip(), str(d.get("released") or "").strip(),
                                  d.get("info") if isinstance(d.get("info"), dict) else {}, d.get("current", True) is not False)
                db.x("UPDATE bots SET updated=? WHERE id=?", (now(), bid))
                return self.send(200, {"ok": True, "id": vid, "bot": bot_detail(bid)})
            if p == ["folders"]:
                name = str(d.get("name") or "").strip()[:20]
                if not name:
                    return self.send(400, {"error": "폴더 이름을 적어 주세요"})
                color = d.get("color") if d.get("color") in COLORS else "#C7C5CC"
                fid, _ = db.x("INSERT INTO folders(name, color, sort, created, scope) VALUES (?,?,(SELECT COALESCE(MAX(sort),0)+1 FROM folders),?,?)",
                              (name, color, now(), d.get("scope") if d.get("scope") in ("item", "style") else "bot"))
                return self.send(200, {"ok": True, "id": fid, "state": state()})
            if p and len(p) == 1 and p[0] in LABELS:
                t, (what, most, pre) = p[0], LABELS[p[0]]
                name = str(d.get("name") or "").strip()[:12]
                if not name:
                    return self.send(400, {"error": f"{what} 이름을 적어 주세요"})
                if db.q(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"] >= most:
                    return self.send(400, {"error": f"{what}는 {most}개까지예요"})
                color = d.get("color") if d.get("color") in COLORS else "#C7C5CC"
                key = pre + secrets.token_hex(4)
                db.x(f"INSERT INTO {t}(key, name, color, sort) VALUES (?,?,?,(SELECT COALESCE(MAX(sort),0)+1 FROM {t}))", (key, name, color))
                return self.send(200, {"ok": True, "key": key, "state": state()})
            if p == ["shelves"]:
                name = str(d.get("name") or "").strip()[:20]
                if not name:
                    return self.send(400, {"error": "칸 이름을 적어 주세요"})
                sid, _ = db.x("INSERT INTO shelves(name, sort, created) VALUES (?,(SELECT COALESCE(MAX(sort),0)+1 FROM shelves),?)", (name, now()))
                return self.send(200, {"ok": True, "id": sid, "state": state()})
            if p == ["links"]:
                bid = d.get("bot_id")
                url = str(d.get("url") or "").strip()[:1000]
                if not isinstance(bid, int) or not db.q("SELECT 1 FROM bots WHERE id=?", (bid,)):
                    return self.send(404, {"error": "봇이 없어요"})
                if not re.match(r"https?://", url):
                    return self.send(400, {"error": "http:// 또는 https:// 로 시작하는 주소를 넣어 주세요"})
                lid, _ = db.x("INSERT INTO links(bot_id, title, url, note, sort) VALUES (?,?,?,?,(SELECT COALESCE(MAX(sort),0)+1 FROM links WHERE bot_id=?))",
                              (bid, str(d.get("title") or "").strip()[:100] or url, url, str(d.get("note") or "").strip()[:500], bid))
                return self.send(200, {"ok": True, "id": lid})
            if p == ["chats"]:
                bid = d.get("bot_id")
                if not isinstance(bid, int) or not db.q("SELECT 1 FROM bots WHERE id=?", (bid,)):
                    return self.send(404, {"error": "봇이 없어요"})
                msgs = clean_messages(d.get("messages") or [])
                if not msgs:
                    return self.send(400, {"error": "메시지를 하나도 못 읽었어요"})
                ats = [m[4] for m in msgs if m[4]]
                cid, _ = db.x("""INSERT INTO chats(bot_id, title, memo, source, count, first_at, last_at, created, updated)
                                 VALUES (?,?,?,?,?,?,?,?,?)""",
                              (bid, str(d.get("title") or "").strip()[:200] or "채팅 로그", str(d.get("memo") or "")[:20000],
                               str(d.get("source") or "")[:200], len(msgs), min(ats) if ats else None, max(ats) if ats else None, now(), now()))
                db.many("INSERT INTO messages(chat_id, idx, role, name, text, at) VALUES (?,?,?,?,?,?)", [(cid, *m) for m in msgs])
                db.x("UPDATE bots SET updated=? WHERE id=?", (now(), bid))
                return self.send(200, {"ok": True, "id": cid})
            return self.send(404, {"error": "없음"})
        except ValueError as e:
            self.send(400, {"error": str(e)})
        except Exception as e:
            self.send(500, {"error": repr(e)})

    def gc_intro(self, old_html):
        """예전 소개글에만 있던 그림 파일 정리 (다른 소개글·표지·장면이 쓰면 남김)."""
        for n in set(intro_media(old_html)):
            like = f"%/m/{n}%"
            used = db.q("""SELECT 1 FROM bots WHERE intro_html LIKE ? OR basic LIKE ? OR cover=?
                           UNION SELECT 1 FROM versions WHERE intro_html LIKE ? OR basic LIKE ?
                           UNION SELECT 1 FROM intros WHERE html LIKE ? UNION SELECT 1 FROM marks WHERE image=? LIMIT 1""",
                        (like, like, n, like, like, like, n))
            if not used:
                drop_media(n)

    def do_PUT(self):
        parts, params = self.route()
        try:
            if not self.write_ok():
                return
            if not self.gate():
                return
            p = parts[1:] if parts[:1] == ["api"] else None
            if p == ["upload"]:
                return self.put_upload(params)
            d = self.body()
            if p == ["auth"]:
                return self.auth_put(d)
            if p and len(p) == 2 and p[0] == "bots" and p[1].isdigit():
                bid = int(p[1])
                b = db.q("SELECT cover FROM bots WHERE id=?", (bid,))
                if not b:
                    return self.send(404, {"error": "봇이 없어요"})
                vals = clean(d, BOT_FIELDS)
                if "tags" in d:
                    vals["tags"] = json.dumps(clean_tags(d["tags"]), ensure_ascii=False)
                if d.get("cover"):
                    vals["cover"] = save_data_url(d["cover"])
                if vals:
                    vals["updated"] = now()
                    db.x(f"UPDATE bots SET {', '.join(k + '=?' for k in vals)} WHERE id=?", (*vals.values(), bid))
                if "cover" in vals and b[0]["cover"]:
                    self.gc_intro(f"/m/{b[0]['cover']}")
                if isinstance(d.get("folders"), list):
                    set_folders(bid, d["folders"])
                if "itype" in vals:
                    place_bot(bid)
                else:
                    write_info(bid)
                if "intro_html" in d and not d["intro_html"]:  # 소개글 지우기
                    old = db.q("SELECT intro_html FROM bots WHERE id=?", (bid,))[0]["intro_html"]
                    db.x("UPDATE bots SET intro_html='', intro_url='', intro_title='', intro_author='', intro_at=NULL WHERE id=?", (bid,))
                    self.gc_intro(old)
                return self.send(200, bot_detail(bid))
            if p and len(p) == 2 and p[0] == "versions" and p[1].isdigit():
                v = version_of(int(p[1]))
                if not v:
                    return self.send(404, {"error": "버전이 없어요"})
                vals = {k: str(d[k] or "").strip()[:n] for k, n in VER_FIELDS.items() if k in d}
                if "name" in vals and not vals["name"]:
                    del vals["name"]
                if isinstance(d.get("info"), dict):
                    vals["info"] = json.dumps(d["info"], ensure_ascii=False)[:400_000]
                if "intro_html" in d and not d["intro_html"]:  # 소개글만 지우기
                    vals.update(intro_html="", intro_url="", intro_title="", intro_author="", intro_at=None)
                if vals:
                    db.x(f"UPDATE versions SET {', '.join(k + '=?' for k in vals)} WHERE id=?", (*vals.values(), v["id"]))
                if d.get("current") or (v["current"] and "info" in vals):
                    set_current(v["id"])
                write_info(v["bot_id"])
                if "intro_html" in vals:
                    self.gc_intro(v["intro_html"])
                return self.send(200, {"ok": True, "bot": bot_detail(v["bot_id"])})
            if p and len(p) == 2 and p[0] == "intros" and p[1].isdigit():
                i = intro_of(int(p[1]))
                if not i:
                    return self.send(404, {"error": "글이 없어요"})
                if "title" in d:
                    db.x("UPDATE intros SET title=? WHERE id=?", (str(d["title"] or "").strip()[:300], i["id"]))
                return self.send(200, {"ok": True, "bot": bot_detail(i["bot_id"])})
            if p and len(p) == 2 and p[0] == "styles" and p[1].isdigit():
                sid = int(p[1])
                if not db.q("SELECT 1 FROM styles WHERE id=?", (sid,)):
                    return self.send(404, {"error": "그림체가 없어요"})
                vals = style_vals(d)
                if vals:
                    vals["updated"] = now()
                    db.x(f"UPDATE styles SET {', '.join(k + '=?' for k in vals)} WHERE id=?", (*vals.values(), sid))
                if isinstance(d.get("folders"), list):
                    set_style_folders(sid, d["folders"])
                return self.send(200, style_detail(sid))
            if p and len(p) == 2 and p[0] == "style_images" and p[1].isdigit():
                g = db.q("SELECT style_id FROM style_images WHERE id=?", (int(p[1]),))
                if not g:
                    return self.send(404, {"error": "그림이 없어요"})
                if d.get("front"):  # 대표 그림 = 맨 앞
                    db.x("UPDATE style_images SET sort=(SELECT MIN(sort) FROM style_images WHERE style_id=?)-1 WHERE id=?", (g[0]["style_id"], int(p[1])))
                return self.send(200, style_detail(g[0]["style_id"]))
            if p and len(p) == 2 and p[0] in LABELS:
                vals = {}
                if str(d.get("name") or "").strip():
                    vals["name"] = str(d["name"]).strip()[:12]
                if d.get("color") in COLORS:
                    vals["color"] = d["color"]
                if vals:
                    db.x(f"UPDATE {p[0]} SET {', '.join(k + '=?' for k in vals)} WHERE key=?", (*vals.values(), p[1]))
                return self.send(200, {"ok": True, "state": state()})
            if p and len(p) == 2 and p[0] in ("folders", "shelves") and p[1].isdigit():
                vals = {}
                if str(d.get("name") or "").strip():
                    vals["name"] = str(d["name"]).strip()[:20]
                if p[0] == "folders" and d.get("color") in COLORS:
                    vals["color"] = d["color"]
                if isinstance(d.get("sort"), int):
                    vals["sort"] = d["sort"]
                if vals:
                    db.x(f"UPDATE {p[0]} SET {', '.join(k + '=?' for k in vals)} WHERE id=?", (*vals.values(), int(p[1])))
                return self.send(200, {"ok": True, "state": state()})
            if p and len(p) == 2 and p[0] == "links" and p[1].isdigit():
                vals = {k: str(d[k]).strip()[:1000 if k == "url" else 500] for k in ("title", "url", "note") if k in d}
                if "url" in vals and not re.match(r"https?://", vals["url"]):
                    return self.send(400, {"error": "http:// 또는 https:// 로 시작하는 주소를 넣어 주세요"})
                if vals:
                    db.x(f"UPDATE links SET {', '.join(k + '=?' for k in vals)} WHERE id=?", (*vals.values(), int(p[1])))
                return self.send(200, {"ok": True})
            if p and len(p) == 2 and p[0] == "files" and p[1].isdigit():
                fid = int(p[1])
                f = db.q("SELECT * FROM files WHERE id=?", (fid,))
                if not f:
                    return self.send(404, {"error": "파일이 없어요"})
                f = f[0]
                vals = {}
                for k in ("name", "note"):
                    if k in d:
                        vals[k] = str(d[k] or "").strip()[:200 if k == "name" else 2000]
                if d.get("kind") in KINDS:
                    vals["kind"] = d["kind"]
                if "shelf_id" in d:
                    sid = d["shelf_id"]
                    vals["shelf_id"] = sid if isinstance(sid, int) and db.q("SELECT 1 FROM shelves WHERE id=?", (sid,)) else None
                if "version_id" in d and f["bot_id"]:  # None = 버전 없이 공통 자료
                    v = version_of(d["version_id"], f["bot_id"])
                    vals["version_id"] = v["id"] if v else None
                if vals:
                    db.x(f"UPDATE files SET {', '.join(k + '=?' for k in vals)} WHERE id=?", (*vals.values(), fid))
                if "version_id" in vals:
                    place_file(fid)
                if f["bot_id"]:
                    write_info(f["bot_id"])
                return self.send(200, {"ok": True})
            if p and len(p) == 2 and p[0] == "chats" and p[1].isdigit():
                vals = {}
                if str(d.get("title") or "").strip():
                    vals["title"] = str(d["title"]).strip()[:200]
                if "memo" in d:
                    vals["memo"] = str(d["memo"] or "")[:20000]
                if "series" in d:
                    vals["series"] = str(d["series"] or "").strip()[:60]
                if "ep" in d:
                    vals["ep"] = d["ep"] if isinstance(d["ep"], int) and 0 <= d["ep"] <= 9999 else None
                if vals:
                    vals["updated"] = now()
                    db.x(f"UPDATE chats SET {', '.join(k + '=?' for k in vals)} WHERE id=?", (*vals.values(), int(p[1])))
                return self.send(200, {"ok": True})
            if p == ["series"]:
                bid, name = d.get("bot_id"), str(d.get("name") or "").strip()[:60]
                if not isinstance(bid, int):
                    return self.send(400, {"error": "봇이 없어요"})
                if isinstance(d.get("ids"), list):
                    ids = [i for i in d["ids"] if isinstance(i, int)][:500]
                    for i in ids:
                        db.x("UPDATE chats SET series=? WHERE id=? AND bot_id=?", (name, i, bid))
                elif isinstance(d.get("from"), str) and d["from"].strip():
                    db.x("UPDATE chats SET series=? WHERE bot_id=? AND series=?", (name, bid, d["from"].strip()))
                return self.send(200, {"ok": True, "chats": chat_list(bid)})
            if p == ["marks"]:
                cid, idx = d.get("chat_id"), d.get("idx")
                if not isinstance(cid, int) or not isinstance(idx, int) or not db.q("SELECT 1 FROM messages WHERE chat_id=? AND idx=?", (cid, idx)):
                    return self.send(404, {"error": "메시지가 없어요"})
                old = db.q("SELECT * FROM marks WHERE chat_id=? AND idx=?", (cid, idx))
                old_img = old[0]["image"] if old else None
                if d.get("on") is False:
                    db.x("DELETE FROM marks WHERE chat_id=? AND idx=?", (cid, idx))
                    if old_img:
                        self.gc_intro(f"/m/{old_img}")
                    return self.send(200, {"ok": True, "mark": None})
                if not old:
                    db.x("INSERT INTO marks(chat_id, idx, memo, created) VALUES (?,?,'',?)", (cid, idx, now()))
                if "memo" in d:
                    db.x("UPDATE marks SET memo=? WHERE chat_id=? AND idx=?", (str(d["memo"] or "")[:5000], cid, idx))
                if d.get("image"):
                    db.x("UPDATE marks SET image=? WHERE chat_id=? AND idx=?", (save_data_url(d["image"]), cid, idx))
                elif d.get("drop_image"):
                    db.x("UPDATE marks SET image=NULL WHERE chat_id=? AND idx=?", (cid, idx))
                if old_img and (d.get("image") or d.get("drop_image")):
                    self.gc_intro(f"/m/{old_img}")
                db.x("UPDATE chats SET updated=? WHERE id=?", (now(), cid))
                m = db.q("SELECT idx, memo, image, created FROM marks WHERE chat_id=? AND idx=?", (cid, idx))
                return self.send(200, {"ok": True, "mark": m[0] if m else None})
            return self.send(404, {"error": "없음"})
        except ValueError as e:
            self.send(400, {"error": str(e)})
        except Exception as e:
            self.send(500, {"error": repr(e)})

    def put_upload(self, params):
        """파일 원본을 그대로 받아 디스크에 씀 (1MB씩)."""
        self.close_connection = True
        bid = int(params["bot"]) if params.get("bot", "").isdigit() else None
        sid = int(params["shelf"]) if params.get("shelf", "").isdigit() else None
        if bid and not db.q("SELECT 1 FROM bots WHERE id=?", (bid,)):
            return self.send(404, {"error": "봇이 없어요"})
        if sid and not db.q("SELECT 1 FROM shelves WHERE id=?", (sid,)):
            sid = None
        kind = params.get("kind") if params.get("kind") in KINDS else "etc"
        name = re.sub(r'[\x00-\x1f/\\]', "_", params.get("name") or "file").strip()[:200] or "file"
        n = int(self.headers.get("Content-Length", "0"))
        if not 0 < n <= MAX_FILE:
            return self.send(413, {"error": f"파일은 {MAX_FILE // 1_000_000_000}GB까지 올릴 수 있어요"})
        fname = secrets.token_hex(12)
        TMP.mkdir(exist_ok=True)
        tmp = TMP / (fname + ".part")
        left = n
        with open(tmp, "wb") as fh:
            while left > 0:
                chunk = self.rfile.read(min(1 << 20, left))
                if not chunk:
                    break
                fh.write(chunk)
                left -= len(chunk)
        if left:
            tmp.unlink(missing_ok=True)
            return self.send(400, {"error": "업로드가 중간에 끊겼어요"})
        tmp.replace(TMP / fname)
        vid = None
        if bid:
            v = version_of(int(params["version"]), bid) if params.get("version", "").isdigit() else None
            vid = v["id"] if v else None
            if not v and kind == "card":  # 버전을 안 정하고 올린 카드: 지금 버전에 카드가 없으면 거기, 있으면 새 버전
                cur = current_version(bid, create=False)
                vid = cur if cur and not db.q("SELECT 1 FROM files WHERE version_id=? AND kind='card'", (cur,)) else None
                if not vid:
                    info = db.q("SELECT info FROM bots WHERE id=?", (bid,))[0]["info"]
                    vid = new_version(bid, info=info if not cur else {})
        fid, _ = db.x("INSERT INTO files(bot_id, shelf_id, version_id, kind, name, file, path, size, note, created) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (bid, None if bid else sid, vid, kind, name, fname, f"tmp/{fname}", n, str(params.get("note") or "")[:2000], now()))
        place_file(fid)
        if bid:
            db.x("UPDATE bots SET updated=? WHERE id=?", (now(), bid))
            write_info(bid)
        return self.send(200, {"ok": True, "id": fid, "version_id": vid})

    def do_DELETE(self):
        parts, _ = self.route()
        try:
            if not self.write_ok():
                return
            if not self.gate():
                return
            p = parts[1:] if parts[:1] == ["api"] else None
            if p and len(p) == 2 and p[0] in LABELS:
                what = LABELS[p[0]][0]
                st = db.q(f"SELECT builtin FROM {p[0]} WHERE key=?", (p[1],))
                if not st:
                    return self.send(404, {"error": f"없는 {what}예요"})
                if st[0]["builtin"]:
                    return self.send(400, {"error": f"기본 {what}는 지울 수 없어요"})
                t, col, to = LABEL_MOVE[p[0]]
                db.x(f"UPDATE {t} SET {col}=? WHERE {col}=?", (to, p[1]))
                db.x(f"DELETE FROM {p[0]} WHERE key=?", (p[1],))
                return self.send(200, {"ok": True, "state": state()})
            if p and len(p) == 4 and p[0] == "styles" and p[1].isdigit() and p[2] == "bots" and p[3].isdigit():
                db.x("DELETE FROM bot_styles WHERE style_id=? AND bot_id=?", (int(p[1]), int(p[3])))
                return self.send(200, style_detail(int(p[1])) or {"ok": True})
            if p and len(p) == 2 and p[0] in ("styles", "style_images") and p[1].isdigit():
                id = int(p[1])
                if p[0] == "styles":
                    imgs = [g["image"] for g in db.q("SELECT image FROM style_images WHERE style_id=?", (id,))]
                    db.x("DELETE FROM styles WHERE id=?", (id,))
                    drop_media(*imgs)
                    return self.send(200, {"ok": True})
                g = db.q("SELECT style_id, image FROM style_images WHERE id=?", (id,))
                if not g:
                    return self.send(404, {"error": "그림이 없어요"})
                db.x("DELETE FROM style_images WHERE id=?", (id,))
                drop_media(g[0]["image"])
                return self.send(200, style_detail(g[0]["style_id"]))
            if not p or len(p) != 2 or not p[1].isdigit() or p[0] not in ("bots", "folders", "shelves", "links", "files", "chats", "versions", "intros"):
                return self.send(404, {"error": "없음"})
            id = int(p[1])
            if p[0] == "bots":
                b = db.q("SELECT cover, intro_html || COALESCE(basic, '') AS intro_html FROM bots WHERE id=?", (id,))
                if not b:
                    return self.send(404, {"error": "봇이 없어요"})
                files = db.q("SELECT file, path FROM files WHERE bot_id=?", (id,))
                imgs = [m["image"] for m in db.q("SELECT m.image FROM marks m JOIN chats c ON c.id=m.chat_id WHERE c.bot_id=? AND m.image IS NOT NULL", (id,))]
                intros = "".join(v["h"] for v in db.q("SELECT intro_html || COALESCE(basic, '') AS h FROM versions WHERE bot_id=?", (id,))) + "".join(
                    i["html"] for i in db.q("SELECT i.html FROM intros i JOIN versions v ON v.id=i.version_id WHERE v.bot_id=?", (id,)))
                db.x("DELETE FROM bots WHERE id=?", (id,))
                for f in files:
                    drop_file(f)
                drop_home(id)
                self.gc_intro(b[0]["intro_html"] + intros + "".join(f" /m/{n}" for n in [b[0]["cover"], *imgs] if n))
                return self.send(200, {"ok": True})
            if p[0] == "files":
                f = db.q("SELECT file, path, bot_id, current FROM files WHERE id=?", (id,))
                if not f:
                    return self.send(404, {"error": "파일이 없어요"})
                db.x("DELETE FROM files WHERE id=?", (id,))
                drop_file(f[0])
                if f[0]["bot_id"]:
                    write_info(f[0]["bot_id"])
                return self.send(200, {"ok": True})
            if p[0] == "versions":  # 버전에 든 파일·소개글까지 지움, 지금 버전이었으면 가장 최근 버전이 이어받음
                v = version_of(id)
                if not v:
                    return self.send(404, {"error": "버전이 없어요"})
                files = db.q("SELECT file, path FROM files WHERE version_id=?", (id,))
                intros = "".join(i["html"] for i in db.q("SELECT html FROM intros WHERE version_id=?", (id,)))
                db.x("DELETE FROM files WHERE version_id=?", (id,))
                db.x("DELETE FROM versions WHERE id=?", (id,))
                for f in files:
                    drop_file(f)
                write_info(v["bot_id"])
                self.gc_intro(v["intro_html"] + (v["basic"] or "") + intros)
                if v["current"]:
                    nxt = db.q("SELECT id FROM versions WHERE bot_id=? ORDER BY created DESC, id DESC LIMIT 1", (v["bot_id"],))
                    if nxt:
                        set_current(nxt[0]["id"])
                return self.send(200, {"ok": True, "bot": bot_detail(v["bot_id"])})
            if p[0] == "intros":
                i = intro_of(id)
                if not i:
                    return self.send(404, {"error": "글이 없어요"})
                db.x("DELETE FROM intros WHERE id=?", (id,))
                self.gc_intro(i["html"])
                return self.send(200, {"ok": True, "bot": bot_detail(i["bot_id"])})
            if p[0] == "chats":
                imgs = [m["image"] for m in db.q("SELECT image FROM marks WHERE chat_id=? AND image IS NOT NULL", (id,))]
                db.x("DELETE FROM chats WHERE id=?", (id,))
                self.gc_intro("".join(f" /m/{n}" for n in imgs))
                return self.send(200, {"ok": True})
            if p[0] == "shelves":  # 칸을 지워도 파일은 '칸 없음'으로 남김
                db.x("UPDATE files SET shelf_id=NULL WHERE shelf_id=?", (id,))
            db.x(f"DELETE FROM {p[0]} WHERE id=?", (id,))
            return self.send(200, {"ok": True, "state": state()})
        except Exception as e:
            self.send(500, {"error": repr(e)})


def info_loop():
    """info.txt를 5분마다 맞춤 (폴더 이름·태그·지금 버전처럼 여기저기서 바뀌는 것까지)."""
    while True:
        time.sleep(300)
        try:
            for b in db.q("SELECT id FROM bots"):
                write_info(b["id"])
        except Exception as e:
            print(f"info.txt 오류: {e!r}", flush=True)


def backup_loop():
    d = DATA / "backups"
    d.mkdir(exist_ok=True)
    while True:
        try:
            f = d / f"botshelf-{datetime.now(KST):%Y-%m-%d}.db"
            with db.lock:
                dst = sqlite3.connect(f)
                db.c.backup(dst)
                dst.close()
            for old in sorted(d.glob("botshelf-*.db"))[:-KEEP_BACKUPS]:
                old.unlink()
        except Exception as e:
            print(f"백업 오류: {e!r}", flush=True)
        time.sleep(6 * 3600)


if __name__ == "__main__":
    MEDIA.mkdir(parents=True, exist_ok=True)
    for t in [*FILES.glob("*.part"), *TMP.glob("*.part")]:
        t.unlink()
    db = DB(DATA / "botshelf.db")
    settle_files()
    if os.environ.get("RESET_AUTH") == "1":  # 비밀번호를 잊었을 때: 잠금 끄고 비밀번호·로그인 지움
        db.x("DELETE FROM settings WHERE key IN ('auth_mode', 'auth_hash')")
        db.x("DELETE FROM sessions")
        print("잠금을 풀었어요 (RESET_AUTH) — 이제 RESET_AUTH 줄을 지우고 다시 켜 주세요", flush=True)
    threading.Thread(target=backup_loop, daemon=True).start()
    threading.Thread(target=info_loop, daemon=True).start()
    print(f"봇카이브 http://{HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
