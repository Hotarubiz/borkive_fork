# 함께 쓰는 남의 것들

## 저장소에 들어 있는 것

### rpack_map.bin — RisuAI
- 출처: [kwaroran/RisuAI](https://github.com/kwaroran/RisuAI) `src/ts/rpack/rpack_map.bin`
- 쓰는 곳: 리스 모듈 파일(.risum) 안의 로어북·에셋을 읽을 때 쓰는 256칸 바이트 치환표예요.
- 라이선스: Rpack.js는 MIT와 AGPL-3.0 이중 라이선스예요. 리스 안에서만 쓸 때는 MIT이고, 다른 앱에서 쓰면 AGPL-3.0을 따라야 해요. 봇카이브는 리스 밖의 앱이라 AGPL-3.0으로 쓰고, 그래서 봇카이브 전체도 AGPL-3.0이에요([LICENSE](LICENSE)).

## 프로톤 드라이브 받기 묶음 (`app/proton.js`)

- 원본: [tools/proton/entry.js](tools/proton/entry.js) — `cd tools/proton && npm ci && npm run build`로 다시 만들 수 있어요.
- 쓰는 곳: 아카 글 붙여넣기에서 프로톤 드라이브 공개 링크의 파일을 브라우저에서 풀 때만 불러와요.
- 묶인 패키지(각 라이선스 전문은 `app/proton.js` 맨 위 주석에 있어요):

| 패키지 | 라이선스 |
|---|---|
| @protontech/drive-sdk 0.23.0 — [ProtonDriveApps/sdk](https://github.com/ProtonDriveApps/sdk) | MIT |
| @protontech/crypto 2.2.0 | GPL-3.0 |
| @protontech/openpgp 6.3.1 | LGPL-3.0+ |
| @noble/hashes 2.4.0 · @openpgp/web-stream-tools 0.3.1 · ttag 1.8.12 · core-js 3.47.0 | MIT |
| bcryptjs 3.0.3 | BSD-3-Clause |

봇카이브는 프로톤과 상관없는 비공식 앱이에요. 프로톤 SDK 규칙대로 요청에 앱 이름(`external-drive-botkive`)을 밝혀요.

## 쓸 때 인터넷에서 불러오는 것 (저장소에는 없음)

| 무엇 | 어디서 | 라이선스 |
|---|---|---|
| Pretendard 글꼴 | cdn.jsdelivr.net (orioncactus/pretendard) | SIL OFL 1.1 |
| 나눔스퀘어 네오 글꼴 | hangeul.pstatic.net | 네이버 나눔글꼴 라이선스 (OFL 1.1) |
| Noto Serif KR · 나눔명조 · 고운바탕 · 고운돋움 · IBM Plex Sans KR · Black Han Sans 글꼴 | fonts.googleapis.com | SIL OFL 1.1 |
| Twemoji 이모지 그림 (아카라이브 소개글을 가져올 때 이모지 그림을 PNG로 받아 보관) | cdn.jsdelivr.net (jdecked/twemoji) | 그림 CC BY 4.0 — © Twitter, Inc and other contributors / jdecked |

## 관계 밝힘
봇카이브는 RisuAI(리스)와 상관없는 개인 프로젝트예요. 리스에서 내보낸 카드·모듈·채팅 파일을 읽을 뿐이에요.
