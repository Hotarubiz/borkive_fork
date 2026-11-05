"""검증된 Phase 5 수신본의 내부 등록 서비스. HTTP·CLI 진입점 없음."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import uuid
import zipfile

from server import file_unfiled, now
from sync_inbox import Inbox, Refused, canonical_digest, check_disk, safe_path, validate_manifest, verify_archive


def require(ok, message):
    if not ok:
        raise Refused(message)


@contextmanager
def transaction(root, *, write=True):
    path = root/'botshelf.db'
    safe_path(path)
    db = sqlite3.connect(path.as_uri()+'?mode=rw', uri=True, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        yield db
        db.commit()
    finally:
        db.close()  # 예외 시 미완료 트랜잭션을 되돌려요.


def initialize(root):
    """이미 초기화된 봇카이브 DB에서 한 번만 호출해요."""
    with transaction(Path(root).resolve()) as db:
        cols = {r['name'] for r in db.execute('PRAGMA table_info(bots)')}
        if 'link_origin' not in cols:
            db.execute('ALTER TABLE bots ADD COLUMN link_origin TEXT')
            db.execute('CREATE UNIQUE INDEX bots_link_origin ON bots(link_origin)')
            db.execute('CREATE TABLE link_library(singleton INTEGER PRIMARY KEY CHECK(singleton=1), id TEXT NOT NULL UNIQUE)')
            db.execute('INSERT INTO link_library VALUES(1,?)', (uuid.uuid4().hex,))
            db.execute("""CREATE TABLE link_jobs(
                library TEXT NOT NULL REFERENCES link_library(id), source TEXT NOT NULL, cha TEXT NOT NULL,
                token TEXT NOT NULL UNIQUE, state TEXT NOT NULL CHECK(state IN ('pending','failed','complete')),
                digest TEXT, bot INTEGER UNIQUE, version INTEGER UNIQUE, fid INTEGER UNIQUE,
                PRIMARY KEY(library,source,cha))""")
        db.execute("""CREATE TABLE IF NOT EXISTS link_folders(
            library TEXT NOT NULL REFERENCES link_library(id), source TEXT NOT NULL, src_folder TEXT NOT NULL,
            folder_id INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
            PRIMARY KEY(library,source,src_folder))""")
        return identity(db)


def identity(db):
    row = db.execute('SELECT id FROM link_library WHERE singleton=1').fetchone()
    require(row and re.fullmatch('[0-9a-f]{32}', row[0]), '서재 ID 불일치')
    return row[0]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked_path(root, relative):
    parts = relative.split('/')
    require(parts[0]=='bots' and all(re.fullmatch(r'[a-zA-Z0-9_.-]+', p) and p not in ('.','..') for p in parts), '카드 경로 불일치')
    path = root
    for p in parts[:-1]:
        path /= p
        safe_path(path, directory=True)
    path /= parts[-1]
    safe_path(path)
    return path


def publish_copy(archive, target, expected):
    # 예약 토큰별 임시 이름. 완성 파일과 같은 inode인 임시 링크만 재시작 시 정리해요.
    if target.is_file() and not target.is_symlink() and target.stat().st_nlink==2:
        for part in target.parent.glob(target.stem+'.*.publish-part'):
            if not part.is_symlink() and os.path.samefile(part,target):
                require(digest(target)==expected,'중단된 파일 공개 상태 불일치')
                part.unlink()
                break
    safe_path(target)
    if not target.exists():
        part=target.with_suffix('.'+uuid.uuid4().hex+'.publish-part')
        with part.open('xb') as out, archive.open('rb') as src:
            try:
                shutil.copyfileobj(src,out,1024*1024)
                out.flush()
                os.fsync(out.fileno())
            except BaseException:
                out.close()
                part.unlink()
                raise
        require(digest(part)==expected,'카드 복사 실패')
        if os.name=='nt':
            os.rename(part,target)  # Windows rename은 기존 파일을 교체하지 않아요.
        else:
            os.link(part,target)
            part.unlink()
    require(digest(target)==expected,'기존 보관 파일 불일치')


COVER_LIMIT = 15_000_000  # 화면에서 표지를 올릴 때(save_data_url)와 같은 한도


def image_ext(raw):
    """확장자 이름이 아니라 내용으로 그림 형식을 봐요. 그림이 아니면 None."""
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if raw.startswith(b'\xff\xd8\xff'):
        return 'jpg'
    if raw[:6] in (b'GIF87a', b'GIF89a'):
        return 'gif'
    if raw[:4] == b'RIFF' and raw[8:12] == b'WEBP':
        return 'webp'
    return None


def cover_image(archive, assets):
    """표지 후보: 대표 그림(icon·main)을 먼저, 없으면 다른 icon. (bytes, 확장자) 또는 None."""
    order = sorted((i for i, a in enumerate(assets) if a.get('kind') == 'icon'), key=lambda i: assets[i].get('name') != 'main')
    with zipfile.ZipFile(archive) as z:
        for i in order:
            try:
                info = z.getinfo(f"assets/{i}.{assets[i]['ext']}")
            except KeyError:
                continue
            if info.file_size > COVER_LIMIT:
                continue
            raw = z.read(info)
            ext = image_ext(raw)
            if ext:
                return raw, ext
    return None


def save_cover(root, archive, assets):
    """media/에 새 이름으로 저장하고 이름을 돌려줘요. 표지는 덤이라 실패해도 등록은 막지 않아요(None)."""
    try:
        found = cover_image(archive, assets)
        if not found:
            return None
        raw, ext = found
        media = Path(root) / 'media'
        safe_path(media, directory=True)
        media.mkdir(exist_ok=True)
        name = f'{secrets.token_hex(10)}.{ext}'
        part = media / (name + '.part')
        part.write_bytes(raw)
        os.replace(part, media / name)
        return name
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        return None


def drop_cover(root, name):
    if name and re.fullmatch(r'[0-9a-f]{20}\.(?:png|jpg|gif|webp)', name):
        (Path(root) / 'media' / name).unlink(missing_ok=True)


def fill_missing_covers(root):
    """연동으로 등록했는데 표지가 빈 봇만 채워요(이전 판으로 등록한 봇). 이미 표지가 있으면 건드리지 않아요. 채운 개수."""
    root = Path(root).resolve()
    with transaction(root, write=False) as db:
        rows = db.execute("""SELECT b.id, f.path FROM link_jobs j JOIN bots b ON b.id=j.bot JOIN files f ON f.id=j.fid
            WHERE j.state='complete' AND (b.cover IS NULL OR b.cover='')""").fetchall()
    filled = 0
    for row in rows:
        try:
            archive = checked_path(root, row['path'])
            with zipfile.ZipFile(archive) as z:
                assets = json.loads(z.read('botkive-link.json'))['assets']
        except (OSError, ValueError, KeyError, zipfile.BadZipFile):
            continue
        name = save_cover(root, archive, assets)
        if not name:
            continue
        with transaction(root) as db:
            done = db.execute("UPDATE bots SET cover=? WHERE id=? AND (cover IS NULL OR cover='')", (name, row['id'])).rowcount
        if done:
            filled += 1
        else:
            drop_cover(root, name)  # 그 사이 사용자가 표지를 정했어요.
    return filled


class Registration:
    """호출자가 별도로 신뢰한 서재·출처에 묶어요. manifest는 권한 증명이 아니에요."""
    def __init__(self, root, library, trusted_source, *, inbox=None):
        self.root = Path(root).resolve()
        self.library = library
        require(re.fullmatch(r'[A-Za-z0-9_-]{16,80}', trusted_source), '출처 ID 형식 오류')
        self.source = trusted_source
        self.inbox = inbox if inbox is not None else Inbox(self.root)

    def key(self, cha):
        require(isinstance(cha,str) and 0<len(cha)<=200, '원본 ID 형식 오류')
        return (self.library,self.source,cha)

    def origin(self, cha):
        return json.dumps(self.key(cha),ensure_ascii=True,separators=(',',':'))

    def check_scope(self, db):
        require(identity(db)==self.library,'다른 서재의 등록 기록')

    def job(self, db, cha):
        return db.execute('SELECT * FROM link_jobs WHERE library=? AND source=? AND cha=?', self.key(cha)).fetchone()

    def state(self, db, cha, job):
        bot = db.execute('SELECT id FROM bots WHERE link_origin=?',(self.origin(cha),)).fetchone()
        if not job:
            return 'inconsistent' if bot else 'unregistered'
        if job['state']!='complete':
            return 'inconsistent' if bot or any(job[k] is not None for k in ('bot','version','fid')) else job['state']
        if not bot or bot[0]!=job['bot']:
            return 'inconsistent'
        file = db.execute("""SELECT f.path,f.moving,f.size FROM files f JOIN versions v ON v.id=f.version_id
            WHERE f.id=? AND f.file=? AND f.kind='card' AND f.bot_id=? AND v.bot_id=f.bot_id AND v.id=?""",
            (job['fid'],job['token'],job['bot'],job['version'])).fetchone()
        if not file or file['moving']:
            return 'inconsistent'
        try:
            path = checked_path(self.root,file['path'])
            if path.stat().st_size==file['size'] and digest(path)==job['digest']:
                return 'complete'
        except (ValueError,OSError,AttributeError):
            pass
        return 'inconsistent'

    def snapshot(self):
        with transaction(self.root,write=False) as db:
            self.check_scope(db)
            ids = {r[0] for r in db.execute('SELECT cha FROM link_jobs WHERE library=? AND source=?',(self.library,self.source))}
            # 매핑이 사라져도 봇의 독립 표식이 있으면 신규로 오인하지 않아요.
            for row in db.execute('SELECT link_origin FROM bots WHERE link_origin IS NOT NULL'):
                key=json.loads(row[0])
                require(isinstance(key,list) and len(key)==3 and key[0]==self.library and
                        all(isinstance(s,str) and s for s in key) and
                        json.dumps(key,ensure_ascii=True,separators=(',',':'))==row[0],'손상된 서재 표식')
                if key[1]==self.source:
                    ids.add(key[2])
            registrations, unresolved=[],[]
            for cha in sorted(ids):
                job=self.job(db,cha)
                state=self.state(db,cha,job)
                if state=='complete':
                    registrations.append({'chaId':cha,'botId':job['bot']})
                else:
                    unresolved.append({'chaId':cha,'state':state})
            return {'sourceId':self.source,'botkiveId':self.library,'complete':not unresolved,
                    'registrations':registrations,'unresolved':unresolved}

    def status(self, cha):
        with transaction(self.root,write=False) as db:
            self.check_scope(db)
            return self.state(db,cha,self.job(db,cha))

    def register(self, cha, session):
        key=self.key(cha)
        require(isinstance(session,str) and re.fullmatch('[0-9a-f]{32}',session),'세션 ID 형식 오류')
        with transaction(self.root) as db:
            self.check_scope(db)
            row=self.job(db,cha)
            state=self.state(db,cha,row)
            if state=='complete':
                return {'state':'skipped','botId':row['bot']}
            require(state!='inconsistent','등록 기록 불일치')
            if not row:
                db.execute("INSERT INTO link_jobs(library,source,cha,token,state) VALUES(?,?,?,?,'pending')",
                           (*key,secrets.token_hex(12)))
        # 예약은 재시작 후에도 남아요. 실제 서재 행은 한 트랜잭션에서만 공개해요.
        error=None
        with transaction(self.root) as db:
            self.check_scope(db)
            row=self.job(db,cha)
            state=self.state(db,cha,row)
            if state=='complete':
                return {'state':'skipped','botId':row['bot']}
            require(state in ('pending','failed'),'등록 기록 불일치')
            db.execute('SAVEPOINT publish')
            try:
                result=self.publish(db,row,session)
            except Exception as exc:
                db.execute('ROLLBACK TO publish')
                db.execute("UPDATE link_jobs SET state='failed' WHERE token=?",(row['token'],))
                error=exc
            db.execute('RELEASE publish')
        if error is not None:
            raise error
        return result

    def publish(self, db, row, session):
        inbox=self.inbox
        folder=inbox.root/'completed'/session
        inbox.safe_session(folder)
        receipt=json.loads((folder/'receipt.json').read_text(encoding='utf-8'))
        require(not receipt.get('duplicateOf'),'원본 CHARX가 있는 완료 세션이 필요해요')
        m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        validate_manifest(m)
        require((m['sourceId'],m['sourceCharacterId'])==(self.source,row['cha']),'원본 식별자 불일치')
        archive=folder/'character.charx'
        verify_archive(archive,m,receipt)
        expected=digest(archive)
        token=row['token']
        require(re.fullmatch('[0-9a-f]{24}',token),'파일 토큰 불일치')
        relative='bots/link-registered/'+token+'.charx'
        for directory in (self.root/'bots',self.root/'bots'/'link-registered'):
            safe_path(directory,directory=True)
        target=self.root/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():
            check_disk(target.parent,archive.stat().st_size)  # 서재 사본 자리
        # 원본 수신본은 별도로 유지해요. 완료 전 중단되면 같은 예약·동일 바이트만 재사용해요.
        require(not db.execute('SELECT 1 FROM files WHERE file=? OR path=?',(token,relative)).fetchone(),
                '이미 다른 서재 파일에서 사용 중인 경로')
        publish_copy(archive,target,expected)
        verify_archive(target,m,receipt)
        c=m['character']
        info=json.dumps({'lore':len(c.get('globalLore',[])),'assets':len(m['assets']),
                         'version':c.get('characterVersion',''),'desc':len(c.get('desc',''))})
        at=now()
        # 대표 그림을 표지로(화면에서 카드를 올릴 때와 같아요). 그림이 없거나 못 읽으면 표지 없이 등록해요.
        cover=save_cover(self.root,target,m['assets'])
        try:
            bid=db.execute('INSERT INTO bots(name,creator,info,created,updated,opened,link_origin,cover) VALUES(?,?,?,?,?,?,?,?)',
                           (c['name'],c.get('creator',''),info,at,at,at,self.origin(row['cha']),cover)).lastrowid
            vid=db.execute('INSERT INTO versions(bot_id,name,current,info,created) VALUES(?,?,1,?,?)',
                           (bid,'첫 버전',info,at)).lastrowid
            fid=db.execute("""INSERT INTO files(bot_id,version_id,kind,name,file,path,size,created)
                VALUES(?,?,'card','character.charx',?,?,?,?)""",(bid,vid,token,relative,target.stat().st_size,at)).lastrowid
            db.execute("UPDATE link_jobs SET state='complete',digest=?,bot=?,version=?,fid=? WHERE token=?",
                       (expected,bid,vid,fid,token))
            folder_state=self.apply_folders(db,bid,m.get('folders',[]))
            self.file_received(db,bid)
        except BaseException:
            drop_cover(self.root,cover)  # 등록을 되돌리면 표지 파일도 남기지 않아요.
            raise
        out={'state':'registered','botId':bid}
        if folder_state is not None:
            out['folderState']=folder_state
        return out

    def explicit_folder_map(self, src_folder):
        path=self.inbox.root/'folder-maps.json'
        safe_path(path)
        if not path.exists():
            return None
        mappings=json.loads(path.read_text(encoding='utf-8'))
        require(isinstance(mappings,dict),'폴더 매핑 형식 오류')
        entry=mappings.get(canonical_digest([self.source,src_folder]))
        if entry is None:
            return None
        require(isinstance(entry,dict) and entry.get('sourceId')==self.source and
                entry.get('folderId')==src_folder and type(entry.get('targetId')) is int,'폴더 매핑 항목 오류')
        return entry['targetId']

    def resolve_folder(self, db, folder):
        src_id=folder['id']
        mapped=self.explicit_folder_map(src_id)
        if mapped is not None:
            hit=db.execute("SELECT id FROM folders WHERE id=? AND COALESCE(scope,'bot')='bot'",(mapped,)).fetchone()
            require(hit,'매핑된 서재 폴더가 없어요')
            db.execute('INSERT INTO link_folders(library,source,src_folder,folder_id) VALUES(?,?,?,?) '
                       'ON CONFLICT(library,source,src_folder) DO UPDATE SET folder_id=excluded.folder_id',
                       (self.library,self.source,src_id,mapped))
            return mapped
        existing=db.execute("""SELECT lf.folder_id FROM link_folders lf JOIN folders f ON f.id=lf.folder_id
            WHERE lf.library=? AND lf.source=? AND lf.src_folder=? AND COALESCE(f.scope,'bot')='bot'""",
            (self.library,self.source,src_id)).fetchone()
        if existing:
            return existing[0]
        name=re.sub(r'\s+',' ',folder['name']).strip()[:20] or src_id[:20]
        fid=db.execute("INSERT INTO folders(name,color,sort,created,scope) VALUES(?, '#C7C5CC', "
                       "(SELECT COALESCE(MAX(sort),0)+1 FROM folders), ?, 'bot')",(name,now())).lastrowid
        db.execute('INSERT INTO link_folders(library,source,src_folder,folder_id) VALUES(?,?,?,?) '
                   'ON CONFLICT(library,source,src_folder) DO UPDATE SET folder_id=excluded.folder_id',
                   (self.library,self.source,src_id,fid))
        return fid

    def file_received(self, db, bid):
        """PocketRisu 폴더가 없으면 '받은 봇'으로 넣어요. 실패해도 등록은 그대로 두고, 다음에 켤 때 다시 넣어요."""
        db.execute('SAVEPOINT file_received')
        try:
            file_unfiled(db,bid)
        except sqlite3.Error:
            db.execute('ROLLBACK TO file_received')
        db.execute('RELEASE file_received')

    def apply_folders(self, db, bid, folders):
        if not folders:
            return None
        db.execute('SAVEPOINT folders_apply')
        try:
            db.execute("""CREATE TABLE IF NOT EXISTS link_folders(
                library TEXT NOT NULL REFERENCES link_library(id), source TEXT NOT NULL, src_folder TEXT NOT NULL,
                folder_id INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
                PRIMARY KEY(library,source,src_folder))""")
            for f in folders:
                fid=self.resolve_folder(db,f)
                db.execute('INSERT OR IGNORE INTO bot_folders(bot_id,folder_id) VALUES(?,?)',(bid,fid))
        except Exception:
            db.execute('ROLLBACK TO folders_apply')
            db.execute('RELEASE folders_apply')
            return 'failed'
        db.execute('RELEASE folders_apply')
        return 'applied'

    def repair_folders(self, cha, session):
        self.key(cha)
        require(isinstance(session,str) and re.fullmatch('[0-9a-f]{32}',session),'세션 ID 형식 오류')
        folder=self.inbox.root/'completed'/session
        self.inbox.safe_session(folder)
        m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        validate_manifest(m)
        require((m['sourceId'],m['sourceCharacterId'])==(self.source,cha),'원본 식별자 불일치')
        with transaction(self.root) as db:
            self.check_scope(db)
            row=self.job(db,cha)
            require(self.state(db,cha,row)=='complete','등록 완료된 캐릭터만 폴더를 복구할 수 있어요')
            state=self.apply_folders(db,row['bot'],m.get('folders',[]))
            return {'state':'repaired' if state in ('applied',None) else 'failed','botId':row['bot'],
                    'folderState':state or 'none'}
