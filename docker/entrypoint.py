"""봇카이브 컨테이너 시작 도우미. 자료 폴더(/data) 권한을 맞춘 뒤 보통 사용자로 서버를 켜요.

Synology Container Manager·Portainer에서 "권한 부족(PermissionError / unable to open database file)"이 나는 이유:
컨테이너가 정해진 번호(1000:1000)로 돌았는데, NAS에서 만든 폴더 주인은 다른 번호(예: 1026:100)라서예요.

그래서 여기서는
  1. 사용자를 고르고: PUID·PGID를 적었으면 그 값, 아니면 /data 폴더 주인, 그 주인이 root면 1000:1000
  2. /data 안에서 그 사용자 것이 아닌 파일·폴더만 주인을 바꾸고 (내용은 건드리지 않아요)
  3. root 권한을 버리고 그 사용자로 server.py를 켜요.
그래도 쓸 수 없으면(NAS 공유 폴더 ACL 등) 이유를 로그에 남기고, PUID를 직접 적지 않았을 때만 root로 계속 켜요.
"""
import os
import sys

DATA = os.environ.get('DATA_DIR', '/data')
SERVER = ['python', '-u', '/app/server.py']
FALLBACK = (1000, 1000)


def log(msg):
    print(f'[시작] {msg}', flush=True)


def number(value):
    value = (value or '').strip()
    return int(value) if value.isdigit() else None


def pick(environ, owner):
    """(uid, gid, 직접 적었는지). owner는 /data의 (uid, gid)."""
    uid, gid = number(environ.get('PUID')), number(environ.get('PGID'))
    if uid is not None:
        return uid, gid if gid is not None else uid, True
    if owner[0] != 0:
        return owner[0], gid if gid is not None else owner[1], False
    return FALLBACK[0], gid if gid is not None else FALLBACK[1], False


def fix_owner(root, uid, gid):
    """주인이 다른 것만 바꿔요. 링크는 따라가지 않아요. 바꾼 개수."""
    changed = 0
    for path in [root, *walk(root)]:
        try:
            st = os.lstat(path)
            if (st.st_uid, st.st_gid) != (uid, gid):
                os.lchown(path, uid, gid)
                changed += 1
        except OSError as e:
            log(f'주인을 바꾸지 못했어요: {path} ({e.strerror})')
    return changed


def walk(root):
    for top, dirs, files in os.walk(root):
        for name in dirs + files:
            yield os.path.join(top, name)


def can_write(folder):
    test = os.path.join(folder, '.botkive-write-test')
    try:
        with open(test, 'w') as f:
            f.write('ok')
        os.remove(test)
        return True
    except OSError:
        return False


def become(uid, gid):
    os.setgroups([])
    os.setgid(gid)
    os.setuid(uid)


def main():
    os.makedirs(DATA, exist_ok=True)
    if os.getuid() != 0:  # compose에 user:를 적어 처음부터 보통 사용자로 켠 경우
        if not can_write(DATA):
            log(f'자료 폴더에 쓸 수 없어요 ({os.getuid()}:{os.getgid()}). compose의 user: 줄을 지우면 자동으로 맞춰요.')
        os.execvp(SERVER[0], SERVER)
    st = os.stat(DATA)
    uid, gid, explicit = pick(os.environ, (st.st_uid, st.st_gid))
    changed = fix_owner(DATA, uid, gid)
    if changed:
        log(f'자료 폴더 주인을 {uid}:{gid}로 맞췄어요 ({changed}개)')
    pid = os.fork()
    if pid == 0:  # 권한을 버린 채로 쓰기 시험만 해 봐요
        become(uid, gid)
        os._exit(0 if can_write(DATA) else 1)
    ok = os.waitpid(pid, 0)[1] == 0
    if ok:
        log(f'{uid}:{gid} 사용자로 켜요')
        become(uid, gid)
    elif explicit:
        log(f'PUID·PGID({uid}:{gid})로는 자료 폴더에 쓸 수 없어요. 값을 지우면 폴더 주인에 맞춰 자동으로 골라요.')
        sys.exit(1)
    else:
        log(f'{uid}:{gid}로는 자료 폴더에 쓸 수 없어(공유 폴더 권한·ACL) root로 켜요. '
            '안내서의 "권한" 부분을 보고 PUID·PGID를 적으면 보통 사용자로 켤 수 있어요.')
    os.execvp(SERVER[0], SERVER)


if __name__ == '__main__':
    main()
