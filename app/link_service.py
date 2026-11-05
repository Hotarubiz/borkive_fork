"""PocketRisu 연동(botkive-link/4) 켜기. 운영자가 환경 변수로 명시적으로 켰을 때만 서비스를 만들어요.

켜는 법(둘 다 필요):
  BOTKIVE_LINK=1
  BOTKIVE_LINK_ORIGIN=https://<사용자가 브라우저·PocketRisu에서 쓰는 봇카이브 HTTPS 주소>
이 두 값이 없거나 형식이 틀리거나 cryptography가 없으면 연동은 꺼진 채로 켜져요(v4 경로 410, 관리 화면 404).
업데이트만으로는 절대 켜지지 않아요.

처음 켤 때 서재 DB에 연동용 칸·표를 더해요(기존 자료는 바꾸지 않음). 그 전에 DB 복사본을 backups/에 남겨요.
"""
import re
import sqlite3
import time
from pathlib import Path

ORIGIN = re.compile(r'https://[A-Za-z0-9.-]+(:[0-9]{1,5})?|http://127\.0\.0\.1:[0-9]{1,5}')


def origin_ok(value):
    return bool(value) and bool(ORIGIN.fullmatch(value))


def normalize_origin(value):
    """적기 쉽게: 'botkive.example.com'만 넣어도 'https://botkive.example.com'으로 읽어요.

    앞뒤 공백·끝의 '/'를 떼고, 소문자로, https 기본 포트(:443)는 빼요. 플러그인 주소 칸(URL.origin)과 같은 모양이에요.
    http://는 붙여 주지 않아요(시험용 127.0.0.1 말고는 origin_ok에서 거절).
    """
    origin = (value or '').strip().rstrip('/').lower()
    if origin and '://' not in origin:
        origin = 'https://' + origin
    if origin.startswith('https://') and origin.endswith(':443'):
        origin = origin[:-4]
    return origin


def needs_migration(db_path):
    con = sqlite3.connect(Path(db_path).as_uri() + '?mode=ro', uri=True)
    try:
        return not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='link_library'").fetchone()
    finally:
        con.close()


def backup_db(db_path, backups, clock=time.time):
    """SQLite 백업 API로 켜진 DB도 안전하게 복사해요. 만든 파일 경로를 돌려줘요."""
    backups = Path(backups)
    backups.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime('%Y%m%d-%H%M%S', time.localtime(clock()))
    target = backups / f'before-botkive-link-{stamp}.db'
    n = 1
    while target.exists():
        target = backups / f'before-botkive-link-{stamp}-{n}.db'
        n += 1
    src, dst = sqlite3.connect(db_path), sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return target


def configure(data, environ, *, password_hash, check_password, log=print):
    """(secure_link_v4, pairing_admin) 또는 꺼짐이면 (None, None)."""
    if environ.get('BOTKIVE_LINK') != '1':
        return None, None
    origin = normalize_origin(environ.get('BOTKIVE_LINK_ORIGIN'))
    if not origin_ok(origin):
        log('PocketRisu 연동을 켜지 않았어요: BOTKIVE_LINK_ORIGIN에 봇카이브 도메인을 넣어 주세요(예: botkive.example.com).')
        return None, None
    try:
        import secure_link_v4 as v4  # cryptography가 필요한 유일한 모듈
    except ImportError:
        log('PocketRisu 연동을 켜지 않았어요: cryptography 패키지가 없어요(연동용 이미지로 실행해 주세요).')
        return None, None
    from library_registration import fill_missing_covers, initialize
    from registration_gateway import RegistrationGateway, Reject
    from pairing_admin import PairingAdmin

    data = Path(data)
    db_path = data / 'botshelf.db'
    if needs_migration(db_path):
        saved = backup_db(db_path, data / 'backups')
        log(f'연동용 칸을 더하기 전에 DB를 복사해 뒀어요: backups/{saved.name}')
    library = initialize(data)
    try:  # 예전 판으로 등록해 표지가 빈 봇만 채워요. 실패해도 켜지는 건 막지 않아요.
        filled = fill_missing_covers(data)
        if filled:
            log(f'연동으로 등록한 봇 {filled}개에 표지를 채웠어요(대표 그림).')
    except Exception as e:
        log(f'표지 채우기를 건너뛰었어요: {type(e).__name__}')

    def no_bearer(auth):
        raise Reject(401)  # 예전 v2 Bearer 경로는 계속 닫혀 있어요.

    keys = v4.LinkKeys(data / 'secure-link.sqlite3')
    gateway = RegistrationGateway(data, library, no_bearer)
    link = v4.SecureLinkGateway(gateway, keys, origin)
    admin = PairingAdmin(keys, library, password_hash=password_hash, check_password=check_password, public_origin=origin)
    log(f'PocketRisu 연동 켜짐 · 공개 주소 {origin} · 페어링 관리 {origin}/pairing (비밀번호 필요)')
    return link, admin
