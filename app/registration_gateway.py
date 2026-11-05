"""서버 내부 등록 경계. 일반 부팅은 이 서비스를 구성하거나 토큰을 발급하지 않아요."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time

from library_registration import Registration, transaction, identity
from sync_inbox import Inbox, MAX_REQUEST, safe_path


class Reject(Exception):
    def __init__(self, status):
        self.status=status


@dataclass(frozen=True)
class Grant:
    library: str
    source: str
    rights: frozenset
    expires: float


class GrantAuthority:
    """신뢰된 서버 소유자가 보유하는 발급 권한. HTTP 처리기에는 verify만 전달해요."""
    def __init__(self, library, *, clock=time.monotonic):
        self.library=library
        self.clock=clock
        self._grants={}
        self._lock=threading.Lock()

    def issue(self, source, rights, ttl=300):
        rights=frozenset(rights)
        if (not re.fullmatch(r'[A-Za-z0-9_-]{16,80}',source) or not rights or
                not rights <= {'read','prepare','commit'} or not 0<ttl<=300):
            raise ValueError('잘못된 발급 범위')
        token='bk1_'+secrets.token_hex(32)
        with self._lock:
            now=self.clock()
            self._grants={k:v for k,v in self._grants.items() if v.expires>now}
            self._grants[hashlib.sha256(token.encode()).digest()]=Grant(self.library,source,rights,now+ttl)
        return token

    def verify(self, auth):
        if len(auth)!=1 or not re.fullmatch(r'Bearer bk1_[0-9a-f]{64}',auth[0]):
            raise Reject(401)
        with self._lock:
            grant=self._grants.get(hashlib.sha256(auth[0][7:].encode()).digest())
            if not grant or grant.expires<=self.clock():
                raise Reject(401)
        return grant


class RegistrationGateway:
    def __init__(self, root, library, verify):
        self.root=Path(root)
        with transaction(self.root,write=False) as db:
            if identity(db)!=library:
                raise ValueError('서재 ID 불일치')
        self.library=library
        self.verify=verify
        self.slots=threading.BoundedSemaphore(4)

    def dispatch(self, auth, path):
        grant=self.verify(auth)
        parts=path.split('/',2)
        if len(parts)!=3 or grant.library!=self.library or tuple(parts[:2])!=(grant.library,grant.source):
            raise Reject(403)
        route=parts[2]
        right={'snapshot':'read','register':'commit'}.get(route)
        if route in {'inbox/'+a for a in ('hello','compare','begin','chunk','chunks','finish','abort')}:
            right='prepare'
        if not right or right not in grant.rights:
            raise Reject(403)
        return grant,route

    def session_owner(self, inbox, session, grant, cha=None):
        if not isinstance(session,str) or not re.fullmatch('[0-9a-f]{32}',session):
            raise Reject(403)
        for kind in ('completed','staging'):
            folder=inbox.root/kind/session
            if folder.exists():
                inbox.safe_session(folder)
                m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
                if m['sourceId']==grant.source and (cha is None or cha==m['sourceCharacterId']):
                    return
        raise Reject(403)

    def execute(self,grant,route,body):
        # v3도 dispatch를 거치지 않고 이 경계를 호출하므로 경로 생성 전에 검사해요.
        if grant.library != self.library:
            raise Reject(403)
        # 경로는 발급된 권한에서만 파생해 자동 정리·용량 한도도 출처별로 격리해요.
        scope_dir=self.root/'registration-inboxes'/grant.library/hashlib.sha256(grant.source.encode()).hexdigest()
        for directory in (scope_dir.parent.parent,scope_dir.parent,scope_dir):
            safe_path(directory,directory=True)
            directory.mkdir(exist_ok=True)
        inbox=Inbox(scope_dir)
        reg=Registration(self.root,grant.library,grant.source,inbox=inbox)
        if route=='snapshot':
            if body:raise Reject(400)
            return reg.snapshot()
        if route=='register':
            if set(body)!={'cha','session'} or not isinstance(body['cha'],str):raise Reject(400)
            self.session_owner(inbox,body['session'],grant,body['cha'])
            return reg.register(body['cha'],body['session'])
        action=route.split('/')[1]
        if action in ('begin','compare'):
            if body.get('sourceId')!=grant.source:raise Reject(403)
        elif action!='hello':
            self.session_owner(inbox,body.get('session'),grant)
        elif body:
            raise Reject(400)
        return inbox.run(action,body)

    def handle(self, handler, path):
        handler.close_connection=True
        if not self.slots.acquire(blocking=False):
            return handler.send(503,{'error':'busy'})
        try:
            auth=handler.headers.get_all('Authorization',[])
            grant,route=self.dispatch(auth,path)
            sizes=handler.headers.get_all('Content-Length',[])
            if handler.headers.get('Transfer-Encoding') is not None or len(sizes)!=1 or not re.fullmatch('[0-9]{1,8}',sizes[0]):
                raise Reject(400)
            limit=MAX_REQUEST if route in ('inbox/compare','inbox/begin','inbox/chunk','inbox/chunks','inbox/finish') else 16384
            size=int(sizes[0])
            if size>limit:raise Reject(413)
            handler.connection.settimeout(5)
            raw=handler.rfile.read(size)
            if len(raw)!=size:raise Reject(400)
            body=json.loads(raw)
            if not isinstance(body,dict):raise Reject(400)
            self.verify(auth)  # 본문을 기다리는 동안 만료됐는지 확인해요.
            result=self.execute(grant,route,body)
            status=200
        except Reject as error:
            status,result=error.status,{'error':'rejected'}
        except (TypeError,ValueError,KeyError,RecursionError,OverflowError):
            status,result=400,{'error':'invalid'}
        except (sqlite3.Error,OSError):
            status,result=503,{'error':'unavailable'}
        except Exception:
            status,result=500,{'error':'registration failed'}
        finally:
            self.slots.release()
        return handler.send(status,result)
