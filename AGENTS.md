# 봇카이브 — LLM 작업 안내

이 문서는 사용자 대신 봇카이브를 **설치하거나 고치는 LLM 에이전트**가 읽는 글이에요. 사람이 읽을 설명은 [README.md](README.md)에 있어요.

봇카이브는 리스(RisuAI) 봇 카드·소개글·채팅 로그·모듈을 파일로 보관하는 개인용 웹앱이에요.
- 서버: 파이썬 표준 라이브러리만 씀 + SQLite
- 화면: HTML 파일 하나 (빌드 도구 없음)
- 계정 없음. 비밀번호 잠금은 선택(기본 꺼짐)

## 꼭 지킬 것

1. **인터넷에 열지 말 것.** 잠금은 기본으로 꺼져 있고, 켜도 혼자 쓰는 서버라 공개용으로는 약해요(HTTPS 없음).
   - 서버는 `127.0.0.1`에만 묶어 두세요. 도커에서는 컨테이너 안만 `HOST=0.0.0.0`이고, 포트 공개는 `127.0.0.1:포트`로 해요.
   - 공유기 포트포워딩, `tailscale funnel`, ngrok·cloudflared 같은 공개 터널은 사용자가 요청해도 위험을 먼저 설명하세요. 대신 Tailscale `serve`(내 기기끼리만)를 권하세요.
2. **사용자 자료(`data/`)를 지우거나 덮어쓰지 말 것.** 자료를 건드리는 작업 전에는 `data/` 폴더를 통째로 복사해 두세요. 지우기는 사용자에게 먼저 물어보세요.
3. **사용자에게는 한국어로, 쉬운 말로** 알리세요. 명령어를 붙여 넣으라고 할 때는 어느 창(PowerShell·터미널)에 넣을지까지 말하세요.
4. **외부 사이트에 대량 요청하는 기능을 만들지 말 것.** 아카라이브 글 가져오기와 리스 랠름 카드 받기는 사용자가 누를 때 한 번씩만 요청해요.

## 설치 맡기기

사용자가 "설치해 줘"라고 하면 이 순서를 따르세요. 단계마다 결과를 확인하고 넘어가세요.

### 1. 환경 보기
- 운영체제를 확인하세요 (윈도우 / 맥 / 리눅스).
- `docker --version` 과 `docker compose version` 이 되면 **도커 방법**을 쓰세요.
- 도커가 없으면 `python --version` (또는 `python3`)으로 **3.12 이상**인지 보고 **파이썬 방법**을 쓰세요.
- 둘 다 없으면 Docker Desktop이나 파이썬 3.12+ 설치를 안내하세요. 사용자 허락 없이 프로그램을 설치하지 마세요.

### 2. 받기
```bash
git clone https://github.com/redarchive77-coder/botkive.git
cd botkive
```
git이 없으면 저장소 페이지에서 ZIP으로 받아 풀어도 돼요.

### 3-A. 도커 방법
```bash
mkdir data                 # 꼭 먼저 만들기 — 도커가 만들면 root 소유가 돼서 앱이 못 씀
docker compose up -d
```
- 리눅스: `id -u`·`id -g`가 1000이 아니면 `.env.example`을 `.env`로 복사해 `BOTSHELF_UID`·`BOTSHELF_GID`를 맞추고 다시 `docker compose up -d` 하세요.
- 8391 포트가 이미 쓰이고 있으면 `.env`의 `BOTSHELF_PORT`를 바꾸세요.
- 확인: `curl http://127.0.0.1:8391/api/health` 에서 `{"ok": true, ...}` 가 나와야 해요. 안 되면 `docker logs botshelf` 를 보세요.
- 컴퓨터를 켤 때 같이 켜지려면 Docker Desktop의 'Start when you sign in'만 켜 두면 돼요. compose에 `restart: unless-stopped`가 있어요.

### 3-B. 파이썬 방법
```bash
cd app
DATA_DIR=../data python3 server.py                    # 맥·리눅스
```
```powershell
cd app; $env:DATA_DIR = "..\data"; python server.py   # 윈도우 PowerShell
```
- 확인: 다른 창에서 `http://127.0.0.1:8391/api/health`.
- 창을 닫으면 꺼진다는 걸 알리세요. 계속 켜 두고 싶어하면 운영체제에 맞는 방법을 사용자에게 고르게 하세요 (윈도우 작업 스케줄러 · 맥 launchd · 리눅스 systemd 사용자 서비스).

### 4. 알려 주기
- 브라우저 주소: `http://127.0.0.1:8391` (포트를 바꿨으면 그 포트)
- 자료는 `data/` 폴더에 쌓이고, 백업은 `data/backups/`에 하루 하나씩(30일치) 생긴다는 것
- 다른 기기에서 쓰고 싶으면 README의 'Tailscale' 부분을 안내하세요. 직접 설정할 때는 사용자 확인을 먼저 받으세요:
  `tailscale serve --bg --https=8443 http://127.0.0.1:8391`

### 막힐 때
| 증상 | 원인·해결 |
|---|---|
| `PermissionError` / `unable to open database file` | `data/` 소유자 문제. 리눅스는 UID·GID 맞추기, 또는 `sudo chown -R $(id -u):$(id -g) data` (사용자 확인 후) |
| `address already in use` | 포트 충돌. `.env`의 `BOTSHELF_PORT` 바꾸기 (파이썬 방법은 `PORT=8392`) |
| 컨테이너가 계속 다시 켜짐 | `docker logs botshelf`로 오류 보기 |
| 모듈 로어북·에셋이 안 보임 | `app/rpack_map.bin`이 빠졌는지 확인 |
| 비밀번호를 잊음 | 도커: `.env`에 `BOTSHELF_RESET_AUTH=1` → `docker compose up -d` → 풀리면 다시 비우고 `up -d`. 파이썬: `RESET_AUTH=1`을 붙여 한 번 켜기 |
| 화면이 옛날 그대로 | 브라우저 새로고침 (캐시) |

### 업데이트·지우기
- 업데이트: `git pull` 다음 `docker compose restart` (파이썬 방법은 껐다 켜기). 새 DB 칸은 켤 때 자동으로 더해져요.
- 지우기: `docker compose down` 후 폴더를 지우면 돼요. **`data/`는 사용자 자료라 지우기 전에 꼭 물어보세요.**

## 코드 고치기

### 파일
- `app/server.py`: HTTP 서버(`ThreadingHTTPServer`) + SQLite. 맨 위 docstring에 API 목록이 있어요.
  - 환경 변수: `DATA_DIR`(기본 `/data`) · `PORT`(8391) · `HOST`(127.0.0.1)
- `app/index.html`: CSS · HTML · JS가 다 든 한 파일짜리 화면. 해시 라우팅(`#/all`, `#/b/<id>`, `#/c/<id>`, `#/shelf` …).
- `app/rpack_map.bin`: 리스 모듈(.risum) 읽기 표 (THIRD_PARTY_NOTICES.md 참고).
- `docker-compose.yml`: `python:3.12-slim` 이미지에 `app/`을 읽기 전용으로, `data/`를 쓰기용으로 붙여요. 이미지를 따로 빌드하지 않아요.

### 데이터
- `data/botshelf.db` 표:
  - `bots`: 봇과 자료함 자료를 같이 담아요. `itype`이 `''`이면 봇, 값이 있으면 자료 종류 키예요.
  - `versions`, `files`, `intros`, `links`
  - `chats`, `messages`, `marks`
  - `bimages`: 봇 그림 탭(채팅하며 만든 그림). `chat_id` · `idx`(메시지 0부터)로 그 채팅 자리를 이어 둠(`bimage_link`가 그 봇 채팅인지 · 메시지 번호가 있는지 확인). 채팅을 지우면 잇기만 풀고, 봇을 지우면 같이 지워요. 그림 탭에는 장면(`marks.image`) 그림도 같이 보여요(`scene_pics`). 채팅 화면 주소 `#/c/<id>/<메시지 번호(1부터)>`는 그 메시지로 스크롤
  - `folders`: `scope`가 `bot`이면 서재 폴더, `item`이면 자료함 폴더, `style`이면 그림체 폴더예요. 봇·자료는 `bot_folders`, 그림체는 `style_folders`로 이어져요.
  - `statuses`, `itypes`, `stypes`: 이름표 표 (기본 몇 개 + 사용자가 더한 것). `stypes`는 그림체 분류
  - `styles`, `style_images`, `style_folders`, `bot_styles`: 그림체(프롬프트·설정 + 견본 그림), 그림체 폴더, 봇 ↔ 그림체(`role` official|mine)
  - `style_variants` · `sgallery`: 그림체 변형(`styles` 줄 = '기본' 변형, 이름은 `styles.vlabel`, 화면에서는 id 0) · 갤러리(`variant_id` NULL = 그림체 공통, 0 = 기본). `style_images.variant_id` NULL = 기본 변형 견본(목록 표지는 기본 견본부터). 변형을 지우면 그 견본은 지우고 갤러리 그림은 공통으로. 나눔 파일엔 변형까지, 전부 내보내기엔 갤러리도(`갤러리/` 파일, json은 file로 가리킴)
  - `pgroups` · `personas`: 페르소나 폴더(사람 하나)와 그 안의 버전(`group_id` · `label` · `sort`, 맨 앞이 대표). 버전 = 그림 한 장 + 프롬프트 + 메모. `pfiles`는 자료실(`persona_id` NULL = 폴더 공통, 원본은 버전 자료 `data/personas/<버전 id 4자리>/` · 공통 `data/personas/g<폴더 id 4자리>/`, 버전↔공통으로 바꾸면 `move_pfile`이 옮김, 버전을 지우면 그 버전 자료도 지움). 예전 `personas.module`은 켤 때 `pfiles`로 옮겨지고 비어 있어요. 마지막 버전을 지우면 폴더도 지워요. `pimages`는 폴더 갤러리(`persona_id` NULL = 폴더 공통, 버전을 지우면 공통으로, 폴더를 지우면 같이 지움). 페르소나 자료는 파일 토큰 `pm:<경로>?<수정 시각>`(`pfile_token`)으로 봇 파일처럼 로어북 · 에셋을 읽어요(`fpath`). `pgroups.ptype`은 `ptypes` 이름표(기본 male 남캐 · female 여캐, '' = 분류 없음 — 지운 분류도 여기로). `chats.persona_id`는 그 로그의 페르소나 버전, `bots.persona_id`는 새 로그에 알아서 붙일 기본 페르소나 (NULL = 지정 안 함)
  - `settings`, `sessions`: 잠금 설정과 로그인
  - `shelves`: 예전 자료함 칸
- 그림은 `data/media/`, 백업은 `data/backups/`.
- 원본 파일은 `data/bots/<봇 id 4자리>/v<버전 id>/<올린 이름>` (자료는 `data/items/`, 봇 없는 파일은 `data/loose/`). 버전 없는 파일은 봇 폴더 바로 아래.
  - `files.file` = 바뀌지 않는 토큰(주소 `/f/<토큰>`·캐시 열쇠), `files.path` = `data` 기준 실제 자리. 원본을 열 때는 항상 `fpath(토큰)`.
  - 옮기기는 `place_file()`만 써요. 새 자리를 먼저 적고(`moving` = 예전 자리) 옮겨서, 중간에 꺼져도 켤 때 `settle_files()`가 마저 옮겨요.
  - 봇 폴더마다 `info.txt`(사람용 메모)를 봇카이브가 고쳐 써요. 거꾸로 읽지는 않아요.
  - 예전 `data/files/`(무작위 이름)는 켤 때 자동으로 봇 폴더로 옮겨져요.
- `GET /api/export`: 전부 내보내기 zip을 흘려보내요(`봇/<첫 폴더>/<봇>/<버전 이름>/` · `자료함/<종류>/` · `그림체/<분류>/` · `페르소나/<분류>/<폴더>/<버전>/` · `봇카이브.json`). 페르소나는 봇·로그가 내보낸 서재의 페르소나 id로 가리키고, 그림이 PNG면 리스 페르소나 조각(tEXt `persona`)을 넣어요.
- 폴더째 들이기(화면만, `dirImport`): 폴더 파일을 브라우저에서 읽어(`scanOne` — 카드·모듈·채팅 로그) `groupScan`으로 봇·버전으로 나눈 뒤 기존 API(`POST /api/bots`·`/api/versions`·`PUT /api/upload`·`POST /api/chats`)로 넣어요. 새로 만든 봇은 `bots.inbox=1`(정리 전, `#/inbox`). `PUT /api/bots/<id>`에 폴더를 넣으면 `inbox`를 따로 안 보내도 0이 돼요.
- 들이기(`/api/import`): zip을 64MB 이하 조각으로 `data/tmp/import-<토큰>.zip`에 이어 붙이고(같은 파일이면 받아 둔 데부터), `run`이면 스레드에서 `봇카이브.json`을 따라 새로 만들어요. 소개글은 `Cleaner`로 다시 정리하고, 원본은 `tmp/`에 풀어 `place_file`로 옮겨요. 중간에 실패하면 이번에 만든 봇·그림체·그림을 걷어 내요. 내보내기에 칸을 더하면 들이기(`_import_zip`)도 같이 고치고, 시험은 내보내기 → 빈 서재로 들이기 → DB·원본 해시 비교로 해요.

### 규칙
- **외부 패키지·빌드 도구를 들이지 마세요.** 서버는 표준 라이브러리만, 화면은 순수 JS예요.
- **DB 구조를 바꿀 때는** `DB.__init__`처럼 "칸이 없으면 `ALTER TABLE … ADD COLUMN`"으로 더하세요. 이미 쓰고 있는 DB가 깨지면 안 돼요.
- **쓰기 API는 `X-BS: 1` 헤더 검사(`write_ok`)를 유지하세요.** 화면에서는 `api()` 도우미를 쓰면 붙어요.
- **화면 글은 한국어 해요체 + 쉬운 말.** 코드 주석도 한국어로 짧게 써요. 주변 코드 모양(이름 짓기, 한 줄 길이, 주석 양)을 따르세요.
- **CSS 클래스 이름이 겹치지 않게** 새 이름은 먼저 검색하세요. 예: `.dim`은 창 뒤 어두운 배경(화면 전체 고정)이라 다른 데 쓰면 화면이 깨져요.
- **주소 바꾸기:** 방문 기록을 안 남기는 이동은 `location.replace` 대신 `replaceHash()`를 쓰세요. 뒤로 버튼(`navStack`)이 어긋나지 않게요.
- **봇과 자료:** `/api/bots`는 봇만, `/api/bots?items=1`은 자료만 돌려줘요. 봇 페이지(`drawBot`)가 둘을 같이 그리고, `B.itype`으로 나눠요.
- **이름표:** 상태·자료 종류·그림체 분류는 서버 `LABELS`(지울 때 옮길 곳은 `LABEL_MOVE`), 화면 `labelDialog(t)`·`syncStatus()`를 같이 써요.
- **그림체 파일:** `{"format": "botkive-style", "version": 1, "styles": [...]}`. 그림은 data URL로 들어 있어요. 형식을 바꾸면 `version`을 올리고, 예전 파일도 읽히게 하세요.
- **잠금:** 새 API나 파일 주소를 만들 때 `do_*`의 `self.gate()` 검사 뒤에 두세요. 로그인 없이 열리는 건 화면(`/`), `/api/auth`, `/api/auth/login|logout`, `/api/health`(잠겨 있으면 개수 없이)뿐이에요.
  - 비밀번호는 `settings.auth_hash`(scrypt)에, 로그인은 `sessions`(쿠키 토큰의 sha256)에 저장해요. 비밀번호 원문이나 토큰 원문은 저장하지도, 기록하지도 마세요.
  - '밖에서만' 판단(`is_local`): 프록시 표시(`X-Forwarded-For`, `Tailscale-User-Login` 등)가 없고 루프백·도커 게이트웨이(`TRUST_GATEWAY=1`)에서 온 요청만 '이 컴퓨터'로 봐요.

### 시험
자동 시험은 없어요. **진짜 자료로 시험하지 말고 복사본으로** 하세요.

1. DB 복사본 만들기 (켜진 채로도 안전하게). 원본 파일까지 시험하려면 `data/bots`·`data/items`·`data/media`도 복사하세요:
   ```bash
   mkdir -p /tmp/bk-test/backups
   python3 -c "import sqlite3; s=sqlite3.connect('data/botshelf.db'); d=sqlite3.connect('/tmp/bk-test/botshelf.db'); s.backup(d); d.close()"
   ```
2. 다른 포트로 띄우기: `cd app && DATA_DIR=/tmp/bk-test PORT=8477 python3 server.py`
3. 브라우저로 열어 확인하고 콘솔 오류를 보세요. 헤드리스 브라우저로 눌러 봐도 좋아요. 쓰기 요청을 직접 보낼 때는 `X-BS: 1` 헤더를 붙이세요.
4. 문법 확인:
   - 파이썬: `python3 -c "import ast; ast.parse(open('app/server.py', encoding='utf-8').read())"`
   - 화면: `index.html`의 `<script>` 내용을 뽑아 `node --check`
5. 다 쓴 시험 서버는 **내가 띄운 프로세스만** 끄세요.

### 고친 뒤 반영
- `index.html`만 바꿨으면 브라우저 새로고침이면 돼요.
- `server.py`를 바꿨으면 `docker compose restart` 하세요 (파이썬 방법은 껐다 켜기).
