"""별도 인증을 사용하는 실험용 수신함. 기존 서재 DB에는 쓰지 않아요."""
import base64
import hashlib
import hmac
import json
import math
import shutil
import sqlite3
import stat
from urllib.parse import urlsplit
import os
from pathlib import Path
import re
import threading
import uuid
import time
import zipfile

PROTOCOL = 'botkive-inbox/2'
TTL = 24 * 3600
ACTIONS = {'hello','begin','chunk','chunks','finish','abort','cleanup','list','inspect','compare','library-folders','folder-map'}
CHUNK = 256 * 1024                  # 예전 플러그인이 보내는 조각 크기(hello의 chunkBytes)
MAX_CHUNK = 8 * 1024 * 1024         # 새 플러그인이 보낼 수 있는 가장 큰 조각(hello의 maxChunkBytes)
MAX_BATCH = 1024                    # 묶음 요청(chunks) 하나에 담을 수 있는 조각 수. 합계는 MAX_CHUNK까지
MAX_REQUEST = 32 * 1024 * 1024      # 비교·시작·조각 요청 하나의 크기. 시작 요청은 나눌 수 없어 넉넉히 둬요
# 에셋이 많은 카드(합계 수백 MB)도 받게 늘렸어요. 플러그인은 hello로 이 값을 받아 따라요.
MAX_ASSET = 64 * 1024 * 1024        # 파일 하나
MAX_TOTAL = 1024 * 1024 * 1024      # 캐릭터 하나 합계
MAX_ASSETS = 6144                   # 캐릭터 하나 에셋 개수
DISK_RESERVE = 2 * 1024**3          # 받은 뒤에도 디스크에 이만큼은 남겨요
COMPLETED_LIMIT = (100_000, 4 * 1024**4)  # 개수만 실제로 막고, 용량은 남은 디스크로 봐요(check_disk)
QUARANTINE_LIMIT = (128, 512 * 1024**2)
LOCK = threading.Lock()
TEXTS = 'name creator desc personality scenario firstMessage exampleMessage creatorNotes systemPrompt postHistoryInstructions replaceGlobalNote characterVersion'.split()
LORE = dict.fromkeys('key secondkey comment content mode id folder'.split(), str) | dict.fromkeys(['insertorder','activationPercent','bookVersion'], (int,float)) | dict.fromkeys(['alwaysActive','selective','useRegex'], bool)
REGEX = dict.fromkeys('comment in out type flag'.split(), str) | {'ableFlag': bool}
SETTINGS = {'scanDepth':(int,float),'tokenBudget':(int,float),'recursiveScanning':bool,'fullWordMatching':bool}


class Refused(ValueError):
    """봇카이브가 이유를 정해 거절했어요. 코드에 적힌 고정 문구만 담아서 봉인 응답으로 플러그인에 알려요."""


def require(ok, message='수신 형식이 맞지 않아요'):
    if not ok:
        raise Refused(message)


def decoded_size(text):
    """Base64를 풀지 않고 풀린 크기를 계산해요(=로 채운 만큼 빼요). 잘못된 글자는 put_piece의 해독에서 걸러요."""
    return len(text)//4*3-text[-2:].count('=')


class StorageFull(ValueError):
    """봇카이브 쪽 저장 공간이 모자라요. 다음 캐릭터도 같아서 플러그인은 여기서 멈춰요(HTTP 507)."""


def check_disk(path, incoming):
    free = shutil.disk_usage(path).free
    if free - incoming < DISK_RESERVE:
        raise StorageFull('봇카이브 저장 공간이 부족해요')


def safe_path(path, directory=False):
    """기존 링크·Windows 재분석 지점·특수 파일을 따라가지 않아요."""
    try:
        info=path.lstat()
    except FileNotFoundError:
        return
    require(not stat.S_ISLNK(info.st_mode) and not getattr(info,'st_file_attributes',0) & getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400))
    require(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode) and info.st_nlink==1)


def entry_bytes(path):
    if path.is_dir():
        safe_path(path,directory=True)
        total=0
        for child in path.iterdir():
            safe_path(child)
            total+=child.stat().st_size
        return total
    safe_path(path)
    return path.stat().st_size


def check_capacity(parent, incoming_bytes, limits):
    max_entries, max_bytes=limits
    total=incoming_bytes
    if not (max_entries>0 and total<=max_bytes):
        raise StorageFull('저장 공간 한도에 도달했어요')
    for count, entry in enumerate(parent.iterdir(),1):
        if count>=max_entries:
            raise StorageFull('보관 개수 한도에 도달했어요')
        total+=entry_bytes(entry)
        if total>max_bytes:
            raise StorageFull('저장 공간 한도에 도달했어요')


def object_fields(value, fields, nullable=(), message='수신 형식이 맞지 않아요'):
    require(isinstance(value, dict) and set(value) <= set(fields), message)
    for key, item in value.items():
        if item is None and key in nullable:
            continue
        expected = fields[key]
        require(type(item) in expected if isinstance(expected, tuple) else type(item) is expected, message)
        if type(item) in (int, float):
            require(math.isfinite(item), message)
    return value


def validate_manifest(m):
    require(isinstance(m,dict))
    require(set(m) == {'protocol','sourceId','operationId','sourceCharacterId','folders','character','assets','warnings'},'플러그인과 봇카이브의 수신 형식이 달라요. 둘 다 업데이트해 주세요')
    require(m['protocol'] == PROTOCOL,'플러그인과 봇카이브의 수신 형식이 달라요. 둘 다 업데이트해 주세요')
    for key in ['sourceId','operationId']:
        require(isinstance(m[key],str) and re.fullmatch('[a-zA-Z0-9_-]{16,80}',m[key]))
    require(isinstance(m['folders'],list) and len(m['folders']) <= 100,'폴더 정보가 100개를 넘어요')
    folder_ids=set()
    for folder in m['folders']:
        require(isinstance(folder,dict) and set(folder)=={'id','name'},'폴더 정보 형식이 맞지 않아요')
        require(all(isinstance(v,str) and 0<len(v)<=200 for v in folder.values()),'폴더 정보 형식이 맞지 않아요')
        require(folder['id'] not in folder_ids,'폴더 정보가 겹쳐요')
        folder_ids.add(folder['id'])
    require(isinstance(m['sourceCharacterId'], str) and 0 < len(m['sourceCharacterId']) <= 200,'캐릭터 ID 형식이 맞지 않아요')
    c = object_fields(m['character'], dict.fromkeys(TEXTS, str) | {'alternateGreetings':list,'tags':list,'globalLore':list,'customscript':list,'loreSettings':dict}, message='캐릭터 설정 형식이 맞지 않아요')
    require(isinstance(c.get('name'), str) and len(c['name']) <= 1000,'캐릭터 이름이 없거나 1000자를 넘어요')
    for key in ['alternateGreetings','tags']:
        require(all(isinstance(x,str) for x in c.get(key,[])),'인사말·태그 형식이 맞지 않아요')
    for value in c.get('globalLore',[]):
        object_fields(value, LORE | {'extentions':dict,'loreCache':dict}, ('activationPercent','alwaysActive','selective','useRegex','secondkey','comment','mode','id','folder','bookVersion','extentions','loreCache'), message='로어북 항목 형식이 맞지 않아요')
        if value.get('extentions') is not None:
            object_fields(value['extentions'],{'risu_case_sensitive':bool},('risu_case_sensitive',),message='로어북 항목 형식이 맞지 않아요')
        if value.get('loreCache') is not None:
            cache=object_fields(value['loreCache'],{'key':str,'data':list},message='로어 캐시 형식이 맞지 않아요')
            require(set(cache)=={'key','data'} and all(isinstance(x,str) for x in cache['data']),'로어 캐시 형식이 맞지 않아요')
    for value in c.get('customscript',[]):
        object_fields(value, REGEX, message='정규식 스크립트 형식이 맞지 않아요')
    object_fields(c.get('loreSettings',{}), SETTINGS, message='로어북 설정 형식이 맞지 않아요')
    require(isinstance(m['warnings'], list) and all(isinstance(x,str) for x in m['warnings']),'안내 문구 형식이 맞지 않아요')
    require(isinstance(m['assets'], list) and len(m['assets']) <= MAX_ASSETS,'에셋 개수 한도를 넘었어요')
    for a in m['assets']:
        require(isinstance(a,dict) and set(a) == {'name','kind','ext'},'에셋 정보 형식이 맞지 않아요')
        require(all(isinstance(v,str) for v in a.values()),'에셋 정보 형식이 맞지 않아요')
        require(len(a['name']) <= 500,'에셋 이름이 500자를 넘어요')
        require(re.fullmatch('[a-z0-9]{1,10}',a['ext']),'에셋 확장자 형식이 맞지 않아요')
        require(a['kind'] in ['icon','emotion','x-risu-asset','image','audio','video'],'지원하지 않는 에셋 종류예요')
        # 같은 이름의 파일이 여러 개일 수 있어요(PocketRisu에서 허용). 저장은 번호로 해서 서로 덮어쓰지 않아요.


def split_keys(value):
    return [key.strip() for key in value.split(',') if key.strip()]

def canonical_digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def card(m, legacy=False):
    c=m['character']
    mapping={'name':'name','creator':'creator','desc':'description','personality':'personality','scenario':'scenario','firstMessage':'first_mes','exampleMessage':'mes_example','creatorNotes':'creator_notes','systemPrompt':'system_prompt','characterVersion':'character_version'}
    data={target:c.get(source,'') for source,target in mapping.items()}
    data['post_history_instructions']=c.get('replaceGlobalNote') or c.get('postHistoryInstructions','')
    data['alternate_greetings']=c.get('alternateGreetings',[])
    data['tags']=c.get('tags',[])
    settings=c.get('loreSettings',{})
    data['character_book']={'entries':[], 'extensions':{'risu_fullWordMatching':settings.get('fullWordMatching',False)}}
    for source,target in [('scanDepth','scan_depth'),('tokenBudget','token_budget'),('recursiveScanning','recursive_scanning')]:
        if source in settings:
            data['character_book'][target]=settings[source]
    for i,lore in enumerate(c.get('globalLore',[])):
        # 이전 영수증 검증 전용. 새 내보내기에서는 기본 확률을 만들지 않아요.
        if legacy:
            data['character_book']['entries'].append({'keys':split_keys(lore.get('key','')),'secondary_keys':split_keys(lore.get('secondkey','')),'content':lore.get('content',''),'insertion_order':lore.get('insertorder',0),'constant':lore.get('alwaysActive',False),'selective':lore.get('selective',False),'name':lore.get('comment',''),'comment':lore.get('comment',''),'enabled':True,'id':i,'use_regex':lore.get('useRegex',False),'mode':lore.get('mode','normal'),'extensions':{'risu_activationPercent':lore.get('activationPercent',100)}})
            continue
        entry={'keys':split_keys(lore.get('key','')),'content':lore.get('content',''),'enabled':True,'id':i,'extensions':{}}
        for source,target in [('insertorder','insertion_order'),('alwaysActive','constant'),('selective','selective'),('comment','name'),('mode','mode'),('useRegex','use_regex'),('folder','folder')]:
            if source in lore:
                entry[target]=lore[source]
        if 'secondkey' in lore:
            entry['secondary_keys']=split_keys(lore['secondkey']) if lore['secondkey'] is not None else None
        ext=lore.get('extentions') or {}
        if 'risu_case_sensitive' in ext:
            entry['case_sensitive']=ext['risu_case_sensitive']
            entry['extensions']['risu_case_sensitive']=ext['risu_case_sensitive']
        for source,target in [('activationPercent','risu_activationPercent'),('loreCache','risu_loreCache')]:
            if source in lore:
                entry['extensions'][target]=lore[source]
        data['character_book']['entries'].append(entry)
    data['extensions']={'risuai':{'customScripts':c.get('customscript',[])},'botkive_link':{'protocol':PROTOCOL,'partial':True}}
    data['assets']=[{'type':a['kind'],'name':a['name'],'ext':a['ext'],'uri':f'embeded://assets/{i}.{a["ext"]}'} for i,a in enumerate(m['assets'])]
    return {'spec':'chara_card_v3','spec_version':'3.0','data':data}


def verify_archive(path, m, receipt):
    require(len(receipt['hashes'])==len(m['assets']))
    with zipfile.ZipFile(path) as z:
        expected={'card.json','botkive-link.json'}|{f'assets/{i}.{a["ext"]}' for i,a in enumerate(m['assets'])}
        require(set(z.namelist())==expected and len(z.namelist())==len(expected))
        require(all(x.file_size<=MAX_ASSET for x in z.infolist()))
        require(receipt.get('cardConverter',1) in (1,2))
        require(json.loads(z.read('card.json'))==card(m,legacy=receipt.get('cardConverter',1)==1))
        require(json.loads(z.read('botkive-link.json'))==m)
        for i,a in enumerate(m['assets']):
            with z.open(f'assets/{i}.{a["ext"]}') as f:
                require(hashlib.file_digest(f,'sha256').hexdigest()==receipt['hashes'][i])


class Inbox:
    def __init__(self, data, library_folders=lambda: []):
        self.library_folders=library_folders
        self.data=Path(data)
        self.root=self.data/'sync-inbox'

    def authenticate(self, token):
        safe_path(self.data/'sync-token.sha256')
        try:
            expected=(self.data/'sync-token.sha256').read_text(encoding='utf-8').strip()
        except FileNotFoundError:
            return False
        return bool(re.fullmatch('[0-9a-f]{64}',expected) and re.fullmatch('[A-Za-z0-9_-]{32,128}',token) and hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(),expected))

    def run(self, action, d):
        with LOCK:
            return {'protocol':PROTOCOL, **self._run(action,d)}

    def _run(self, action, d):
        require(action in ACTIONS)
        if action == 'hello':
            return {'maxAssetBytes':MAX_ASSET,'maxTotalBytes':MAX_TOTAL,'maxAssets':MAX_ASSETS,'chunkBytes':CHUNK,'maxChunkBytes':MAX_CHUNK,'maxBatchItems':MAX_BATCH,
                    'partial':True,'registrationEnabled':False}
        safe_path(self.root,directory=True)
        self.root.mkdir(mode=0o700, exist_ok=True)
        staging=self.root/'staging'
        completed=self.root/'completed'
        safe_path(staging,directory=True)
        safe_path(completed,directory=True)
        staging.mkdir(exist_ok=True)
        completed.mkdir(exist_ok=True)
        if action == 'library-folders':
            return {'folders':self.library_folders(),'registrationEnabled':False}
        if action == 'folder-map':
            require(set(d)=={'sourceId','folderId','targetId'})
            require(isinstance(d['sourceId'],str) and isinstance(d['folderId'],str) and type(d['targetId']) is int)
            require(any(f['id']==d['targetId'] for f in self.library_folders()),'대상 폴더가 없어요')
            require(any(m.get('sourceId')==d['sourceId'] and any(f['id']==d['folderId'] for f in m.get('folders',[])) for _,m,_ in self.records(completed)),'보관된 원본 폴더가 없어요')
            path=self.root/'folder-maps.json';temp=self.root/'folder-maps.part'
            safe_path(path)
            safe_path(temp)
            mappings=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
            require(isinstance(mappings,dict))
            mappings[canonical_digest([d['sourceId'],d['folderId']])]=d
            temp.write_text(json.dumps(mappings));os.replace(temp,path)
            return {'mapping':d,'registrationEnabled':False}
        if action == 'cleanup':
            return self.cleanup(staging)
        if action == 'list':
            return self.summary(staging,completed,d)
        if action == 'inspect':
            session=self.session_id(d)
            return self.inspect(completed/session)
        if action == 'compare':
            validate_manifest(d)
            return self.compare(d,completed)
        if action == 'begin':
            validate_manifest(d)
            self.cleanup(staging)
            session=canonical_digest([d['sourceId'],d['operationId']])[:32]
            for parent in [completed,staging]:
                existing=parent/session
                if existing.exists() or existing.is_symlink():
                    self.safe_session(existing)
                    require(json.loads((existing/'manifest.json').read_text(encoding='utf-8'))==d,'같은 작업 ID의 내용이 달라요')
                    if parent==completed:
                        require(self.inspect(existing)['integrity']=='verified','기존 보관본의 무결성을 확인해 주세요')
                        return {'session':session,'state':'complete','partial':True}
                    os.utime(existing,None)
                    return {'session':session,'state':'uploading'}
            require(sum(self.valid_session(entry) for entry in staging.iterdir()) < 8, '미완료 작업 8개 한도예요. 수신함을 점검해 주세요')
            folder=staging/session
            folder.mkdir(mode=0o700)
            (folder/'manifest.json').write_text(json.dumps(d,ensure_ascii=False),encoding='utf-8')
            return {'session':session}
        session=self.session_id(d)
        if action == 'abort':
            folder=staging/session
            if folder.exists() or folder.is_symlink():
                self.safe_session(folder)
                shutil.rmtree(folder)
            return {'session':session,'state':'complete' if (completed/session).is_dir() else 'aborted'}
        done=completed/session
        if action == 'finish' and done.exists():
            self.safe_session(done)
            require(self.inspect(done)['integrity']=='verified','기존 보관본의 무결성을 확인해 주세요')
            require(d.get('hashes') == json.loads((done/'receipt.json').read_text(encoding='utf-8'))['hashes'])
            receipt=json.loads((done/'receipt.json').read_text(encoding='utf-8'))
            if receipt.get('duplicateOf'):
                return {'session':session,'state':'identical','partial':True,'duplicateOf':receipt['duplicateOf']}
            return {'session':session,'state':'complete','partial':True,'comparison':receipt.get('state','new'),'changes':receipt.get('changes',[])}
        folder=staging/session
        self.safe_session(folder)
        m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        if action == 'chunk':
            require(set(d)=={'session','index','offset','size','sha256','data'})
            received=self.put_piece(folder,m,d,[None])
            os.utime(folder,None)
            return {'received':received}
        if action == 'chunks':
            # 작은 파일 여러 개를 요청 하나로 받아요. 중간에 실패해도 다시 보내면 받은 부분은 비교만 하고 이어 받아요.
            require(set(d)=={'session','items'} and isinstance(d['items'],list) and 0<len(d['items'])<=MAX_BATCH,'묶음 요청 형식이 맞지 않아요')
            for piece in d['items']:
                require(isinstance(piece,dict) and set(piece)=={'index','offset','size','sha256','data'} and isinstance(piece['data'],str),'묶음 요청 형식이 맞지 않아요')
            # Base64 글자 수가 아니라 풀린 크기로 봐요. 글자 수는 조각마다 끝 맞춤이 달라서 한도 안의 묶음도 넘어 보일 수 있어요.
            require(sum(decoded_size(piece['data']) for piece in d['items'])<=MAX_CHUNK,'한 번에 보내는 크기 한도를 넘었어요')
            total=[None]  # 받은 합계는 요청마다 한 번만 읽어요(에셋마다 다시 읽으면 에셋이 많을수록 느려져요)
            for piece in d['items']:
                self.put_piece(folder,m,piece,total)
            os.utime(folder,None)
            return {'received':len(d['items'])}
        if action == 'finish':
            hashes=d.get('hashes')
            require(isinstance(hashes,list) and len(hashes)==len(m['assets']),'에셋 해시 목록이 맞지 않아요')
            for i,digest in enumerate(hashes):
                path=folder/f'{i}.bin'; spec=folder/f'{i}.json'
                require(path.is_file() and spec.is_file(),'에셋 파일이 빠졌어요')
                info=json.loads(spec.read_text(encoding='utf-8'))
                with path.open('rb') as f:
                    actual=hashlib.file_digest(f,'sha256').hexdigest()
                require(path.stat().st_size==info['size'] and actual==digest==info['sha256'],'에셋 검증에 실패했어요')
            comparison=self.compare(m,completed,hashes)
            if comparison.get('state')=='identical' and self.inspect(completed/comparison['session'])['integrity']!='verified':
                comparison={**comparison,'state':'recovery-candidate','changes':['damaged-archive']}
            if comparison.get('state')=='identical':
                # 중복 CHARX는 만들지 않고 작업 영수증만 남겨 재시도에 응답해요.
                target=comparison['session']
                require(self.inspect(completed/target)['integrity']=='verified','기존 보관본이 손상됐어요')
                receipt={'hashes':hashes,'completed':time.time(),'duplicateOf':target,'changes':[]}
                check_capacity(completed,(folder/'manifest.json').stat().st_size+len(json.dumps(receipt).encode()),COMPLETED_LIMIT)
                for child in folder.iterdir():
                    if child.name!='manifest.json':
                        child.unlink()
                (folder/'receipt.json').write_text(json.dumps(receipt))
                os.rename(folder,done)
                return {'session':session,'state':'identical','partial':True,'duplicateOf':target}
            temp=folder/'character.charx.part'
            check_disk(folder,sum((folder/f'{i}.bin').stat().st_size for i in range(len(m['assets']))))
            with zipfile.ZipFile(temp,'w',compression=zipfile.ZIP_STORED) as z:
                z.writestr('card.json',json.dumps(card(m),ensure_ascii=False))
                z.writestr('botkive-link.json',json.dumps(m,ensure_ascii=False))
                for i,a in enumerate(m['assets']):
                    z.write(folder/f'{i}.bin',f'assets/{i}.{a["ext"]}')
            os.replace(temp,folder/'character.charx')
            (folder/'receipt.json').write_text(json.dumps({'cardConverter':2,'hashes':hashes,'completed':time.time(),'changes':comparison.get('changes',[]),'state':comparison['state']}))
            # 같은 파일시스템의 디렉터리 rename으로 완성본만 공개해요.
            check_capacity(completed,entry_bytes(folder),COMPLETED_LIMIT)
            os.rename(folder,done)
            # 조각 파일은 CHARX 안에 다 들어 있어요. 공개한 뒤에 지워 디스크를 반으로 줄여요(검증은 CHARX만 봐요).
            for i in range(len(m['assets'])):
                for leftover in (done/f'{i}.bin', done/f'{i}.json'):
                    try:
                        leftover.unlink()
                    except FileNotFoundError:
                        pass
            return {'session':session,'state':'complete','partial':True,'comparison':comparison['state'],'changes':comparison.get('changes',[])}
        raise ValueError('지원하지 않는 수신 요청이에요')


    @staticmethod
    def session_id(d):
        session=d.get('session','')
        require(isinstance(session,str) and re.fullmatch('[0-9a-f]{32}',session))
        return session

    def put_piece(self, folder, m, d, total):
        """조각 하나를 이어 받고 그 파일의 받은 크기를 돌려줘요. total[0]은 이 요청에서 계산한 캐릭터 합계예요."""
        i=d['index']; offset=d['offset']; size=d['size']; digest=d['sha256']
        require(type(i) is int and 0<=i<len(m['assets']),'에셋 번호가 맞지 않아요')
        require(type(offset) is int and offset>=0 and type(size) is int and size>0,'에셋 크기 정보가 맞지 않아요')
        require(size<=MAX_ASSET,'파일 하나의 크기 한도를 넘었어요')
        require(isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest),'에셋 해시 형식이 맞지 않아요')
        require(isinstance(d['data'],str) and len(d['data'])<=4*((MAX_CHUNK+2)//3),'조각 하나의 크기 한도를 넘었어요')
        raw=base64.b64decode(d['data'],validate=True)
        require(0<len(raw)<=MAX_CHUNK and offset+len(raw)<=size,'조각 크기가 맞지 않아요')
        spec=folder/f'{i}.json'
        info={'size':size,'sha256':digest}
        if spec.exists():
            require(json.loads(spec.read_text(encoding='utf-8'))==info,'같은 에셋의 크기·해시가 앞 조각과 달라요')
        else:
            if total[0] is None:
                total[0]=sum(json.loads(x.read_text(encoding='utf-8'))['size'] for x in folder.glob('[0-9]*.json'))
            require(total[0]+size<=MAX_TOTAL,'캐릭터 용량 한도를 넘었어요')
            # 받은 조각 + 완성 CHARX + 서재 사본 자리를 미리 봐요(전부 보내고 나서야 실패하지 않게).
            check_disk(folder,3*size)
            spec.write_text(json.dumps(info))
            total[0]+=size
        path=folder/f'{i}.bin'
        current=path.stat().st_size if path.exists() else 0
        require(offset<=current,'수신 위치가 달라요')
        overlap=min(len(raw),current-offset)
        if offset<current:
            with path.open('rb') as f:
                f.seek(offset)
                require(f.read(overlap)==raw[:overlap],'재시도 내용이 달라요')
        if overlap<len(raw):
            # 디스크 부족으로 일부만 기록됐어도 일치하는 앞부분 뒤에서 재개해요.
            with path.open('ab') as f:
                f.write(raw[overlap:])
        return path.stat().st_size

    def safe_session(self, folder):
        safe_path(self.root,directory=True)
        safe_path(folder.parent,directory=True)
        safe_path(folder,directory=True)
        require(re.fullmatch('[0-9a-f]{32}',folder.name) and folder.is_dir() and not folder.is_symlink())
        require(folder.parent in [self.root/'staging',self.root/'completed'])
        require(not folder.parent.is_symlink() and not self.root.is_symlink())
        for child in folder.iterdir():
            safe_path(child)
            require(child.is_file() and not child.is_symlink())
            require(child.name in ['manifest.json','receipt.json','character.charx','character.charx.part'] or re.fullmatch(r'[0-9]+\.(bin|json)',child.name))
        require((folder/'manifest.json').is_file())
        m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        require(isinstance(m,dict))
        # 이전 MVP의 미완료 자료도 구조를 검증한 뒤에만 정리해요.
        if m.get('protocol')=='botkive-inbox/1':
            m={**m,'protocol':PROTOCOL,'sourceId':'legacy_source_001','operationId':'legacy_operation_001','folders':[]}
        validate_manifest(m)

    def valid_session(self, folder):
        try:
            self.safe_session(folder)
            m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
            for child in folder.iterdir():
                if re.fullmatch(r'[0-9]+\.json',child.name):
                    index=int(child.stem);spec=json.loads(child.read_text(encoding='utf-8'))
                    require(index<len(m['assets']) and isinstance(spec,dict) and set(spec)=={'size','sha256'})
                    require(type(spec['size']) is int and 0<spec['size']<=MAX_ASSET)
                    require(isinstance(spec['sha256'],str) and re.fullmatch('[0-9a-f]{64}',spec['sha256']))
                    binary=folder/(child.stem+'.bin')
                    require(not binary.exists() or binary.stat().st_size<=spec['size'])
                elif re.fullmatch(r'[0-9]+\.bin',child.name):
                    require((folder/(child.stem+'.json')).is_file())
            return True
        except (ValueError,TypeError,KeyError,OSError,OverflowError):
            return False

    def cleanup(self, staging):
        removed=[];quarantined=[];retained=[]
        quarantine=self.root/'quarantine'
        safe_path(quarantine,directory=True)
        for entry in list(staging.iterdir())[:64]:
            try:
                safe_path(entry,directory=entry.is_dir())
                if entry.is_symlink() or time.time()-entry.stat().st_mtime <= TTL:
                    continue
                if self.valid_session(entry):
                    shutil.rmtree(entry)
                    removed.append(entry.name)
                else:
                    # 알 수 없는 중첩 경로/링크는 건드리지 않고, 단순 손상 항목만 보존 이동해요.
                    if entry.is_dir() and any(x.is_symlink() or not x.is_file() for x in entry.iterdir()):
                        retained.append(entry.name)
                        continue
                    if entry.is_dir():
                        for child in entry.iterdir():
                            safe_path(child)
                    require(entry.is_file() or entry.is_dir())
                    quarantine.mkdir(mode=0o700,exist_ok=True)
                    check_capacity(quarantine,entry_bytes(entry),QUARANTINE_LIMIT)
                    target=quarantine/(uuid.uuid4().hex+'-'+entry.name[:64])
                    os.rename(entry,target)
                    quarantined.append(entry.name)
            except (ValueError,TypeError,KeyError,OSError,OverflowError):
                retained.append(entry.name)
        return {'removed':removed,'quarantined':quarantined,'retained':retained}

    def records(self, completed):
        for folder in completed.iterdir():
            try:
                self.safe_session(folder)
                receipt=json.loads((folder/'receipt.json').read_text(encoding='utf-8'))
                require(isinstance(receipt,dict) and type(receipt.get('completed')) in (int,float) and math.isfinite(receipt['completed']) and isinstance(receipt.get('hashes'),list))
                m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
                yield folder,m,receipt
            except (ValueError,TypeError,KeyError,OSError):
                continue

    def compare(self, m, completed, hashes=None):
        candidates=[r for r in self.records(completed) if not r[2].get('duplicateOf') and r[1].get('sourceId')==m['sourceId'] and r[1]['sourceCharacterId']==m['sourceCharacterId']]
        if not candidates:
            return {'state':'new','changes':[],'assetComparison':'unknown' if hashes is None else 'verified','libraryState':'unregistered'}
        folder,previous,receipt=max(candidates,key=lambda r:r[2]['completed'])
        changes=[]
        if canonical_digest(m['character'])!=canonical_digest(previous['character']): changes.append('settings')
        if canonical_digest(sorted(m['folders'],key=lambda f:f['id']))!=canonical_digest(sorted(previous.get('folders',[]),key=lambda f:f['id'])): changes.append('folders')
        if canonical_digest(m['assets'])!=canonical_digest(previous['assets']) or (hashes is not None and hashes!=receipt['hashes']): changes.append('assets')
        if m['warnings']!=previous['warnings']: changes.append('warnings')
        return {'state':'changed' if changes else ('metadata-identical' if hashes is None else 'identical'),'session':folder.name,'changes':changes,'assetComparison':'unknown' if hashes is None else 'verified','libraryState':'unregistered'}

    def inspect(self, folder):
        self.safe_session(folder)
        receipt=json.loads((folder/'receipt.json').read_text(encoding='utf-8'))
        require(isinstance(receipt,dict))
        if receipt.get('duplicateOf'):
            target=self.session_id({'session':receipt['duplicateOf']})
            require(target!=folder.name)
            original=self.root/'completed'/target
            self.safe_session(original)
            require(not json.loads((original/'receipt.json').read_text(encoding='utf-8')).get('duplicateOf'))
            return self.inspect(original)
        m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        if m.get('protocol')!=PROTOCOL:
            return {'session':folder.name,'integrity':'legacy-unverified','partial':True,'registrationEnabled':False}
        try:
            verify_archive(folder/'character.charx',m,receipt)
            return {'session':folder.name,'integrity':'verified','partial':True,'registrationEnabled':False}
        except (ValueError,KeyError,IndexError,zipfile.BadZipFile,OSError):
            return {'session':folder.name,'integrity':'failed','partial':True,'registrationEnabled':False}

    def summary(self, staging, completed, d):
        offset=d.get('offset',0)
        require(type(offset) is int and offset>=0)
        rows=[]
        for parent,state in [(staging,'incomplete'),(completed,'complete')]:
            for folder in parent.iterdir():
                try:
                    self.safe_session(folder)
                    m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
                    r=json.loads((folder/'receipt.json').read_text(encoding='utf-8')) if state=='complete' else {}
                    require(isinstance(r,dict))
                    if state=='complete':
                        require(type(r.get('completed')) in (int,float) and math.isfinite(r['completed']))
                    rows.append({'session':folder.name,'state':'identical' if r.get('duplicateOf') else state,'name':m['character']['name'],'creator':m['character'].get('creator',''),'sourceId':m.get('sourceId'),'sourceCharacterId':m['sourceCharacterId'],'folders':m.get('folders',[]),'warnings':m['warnings'],'at':r.get('completed',folder.stat().st_mtime),'changes':r.get('changes',[]),'integrity':'unchecked','libraryState':'unregistered'})
                except (ValueError,KeyError,TypeError,OSError):
                    continue
        rows.sort(key=lambda r:(-r['at'],r['session']))
        mapping_file=self.root/'folder-maps.json'
        safe_path(mapping_file)
        mappings=json.loads(mapping_file.read_text(encoding='utf-8')) if mapping_file.exists() else {}
        require(isinstance(mappings,dict))
        return {'items':rows[offset:offset+50],'total':len(rows),'mappings':list(mappings.values()),'registrationEnabled':False}


def cors(handler, data, preflight=False):
    """동기화 경로 전용. preflight는 토큰 없이 허용해도 본 요청 인증은 유지해요."""
    origin=handler.headers.get('Origin')
    headers=[('Vary','Origin')]
    if origin is not None:
        try:
            allowed=json.loads((Path(data)/'sync-origins.json').read_text(encoding='utf-8'))
            require(isinstance(allowed,list))
            require(origin in allowed and origin!='null')
            u=urlsplit(origin)
            require(u.scheme=='https' and u.netloc and not u.username and not u.password and not u.path and not u.query and not u.fragment)
        except (OSError,ValueError,TypeError):
            handler.close_connection=True
            handler.send(403,{'error':'허용하지 않은 동기화 출처예요'},headers=headers)
            return None
        headers.append(('Access-Control-Allow-Origin',origin))
    if preflight:
        requested={x.strip().lower() for x in handler.headers.get('Access-Control-Request-Headers','').split(',') if x.strip()}
        if not origin or handler.headers.get('Access-Control-Request-Method')!='POST' or not requested<={'authorization','x-bs','content-type'}:
            handler.send(403,{'error':'허용하지 않은 사전 요청이에요'},headers=headers)
            return None
        headers += [('Access-Control-Allow-Methods','POST'),('Access-Control-Allow-Headers','Authorization, X-BS, Content-Type'),('Access-Control-Max-Age','300')]
        handler.send(204,b'',headers=headers)
    return headers


def handle(handler, data, action, library_folders=lambda: []):
    """기존 로그인과 독립적인 수신 전용 인증. 일반 API에는 적용하지 않아요."""
    handler.close_connection=True
    headers=cors(handler,data)
    if headers is None:
        return
    def send(code,body):
        handler.send(code,body,headers=headers)
    if handler.headers.get('X-BS')!='1':
        send(403,{'error':'잘못된 요청'})
        return
    inbox=Inbox(data,library_folders)
    try:
        authenticated=handler.headers.get('Authorization','').startswith('Bearer ') and inbox.authenticate(handler.headers.get('Authorization','').removeprefix('Bearer '))
    except (OSError,ValueError):
        # 인증 설정 오류를 상위 repr 응답으로 넘기거나 토큰과 함께 기록하지 않아요.
        send(503, {'error':'동기화 인증 설정을 확인해 주세요'})
        return
    if not authenticated:
        send(401, {'error':'동기화 인증이 필요해요'})
        return
    try:
        require(not handler.headers.get('Transfer-Encoding'))
        n=int(handler.headers.get('Content-Length','0'))
        require(0<n<=MAX_REQUEST,'수신 요청이 너무 커요')
        handler.connection.settimeout(15)
        raw=handler.rfile.read(n)
        require(len(raw)==n,'요청이 중간에 끊겼어요')
        d=json.loads(raw,parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        require(isinstance(d,dict))
        result=inbox.run(action,d)
    except (ValueError,TypeError,KeyError,OverflowError,RecursionError):
        send(400, {'error':'요청 형식·파일 누락·수신 한도를 확인해 주세요'})
        return
    except (OSError,sqlite3.Error):
        send(503, {'error':'수신 저장소를 확인해 주세요'})
        return
    send(200,result)
