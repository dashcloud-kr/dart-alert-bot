# dart-alert-bot — 24/7 공시 알림 텔레그램 봇

[![CI](https://github.com/dashcloud-kr/dart-alert-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/dashcloud-kr/dart-alert-bot/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

**DART 전자공시**를 5분마다 확인해서 관심기업·키워드 공시를 실시간으로 알려주는 텔레그램 봇입니다.
[대시클라우드(DashCloud)](https://dashcloud.kr)에서 **평생 무료로 24시간** 가동할 수 있습니다.

> **English** — A Telegram bot that watches DART (Korean corporate disclosures) every 5 minutes and pushes alerts for your watchlist companies and keywords, with a daily morning summary. Built to run 24/7 on [DashCloud](https://dashcloud.kr) for free.

## 기능

| 기능 | 설명 |
| --- | --- |
| 관심기업 알림 | 최대 20개 — 기업의 **모든** 신규 공시를 즉시 알림 |
| 키워드 알림 | 최대 10개 (예: `유상증자`, `자사주`) — 모든 기업 대상 제목 매칭 |
| 기업 검색 | 11만+ 기업 고유번호 캐시 (시작 시 자동 다운로드) — 버튼으로 등록 |
| 중복 방지 | 접수번호 기준 — 같은 공시는 절대 두 번 오지 않음 |
| 아침 요약 | `/morning on` — 매일 08:30 어제 관심기업 공시 정리 |
| 원문 링크 | DART 원문 바로가기 포함 |

## 명령어

```
/add 삼성전자          관심기업 검색 후 등록 (버튼)
/list /rms 3           관심기업 목록/삭제

/keyword 유상증자       키워드 알림 등록
/keywords /del 유상증자  목록/삭제

/latest                최근 공시 5건
/morning on            매일 08:30 아침 요약
/settings              내 설정 요약
/status /id            봇 상태 / 내 chat id
```

## 준비물 — DART API 키 (무료, 즉시 발급)

1. [opendart.fss.or.kr](https://opendart.fss.or.kr) 회원가입
2. **오픈API → 인증키 신청** → 즉시 발급 (일 20,000건)
3. `.env`의 `DART_API_KEY`에 입력

## 30초 로컬 실행

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# .env 에 TELEGRAM_BOT_TOKEN, DART_API_KEY 입력

python bot.py
```

## DashCloud로 24시간 무료 가동

1. [dashcloud.kr](https://dashcloud.kr) 가입 — 휴대폰 인증 1회, 결제 정보 불필요
2. 이 폴더를 대시보드에 **드래그 앤 드롭**
3. 환경변수에 `TELEGRAM_BOT_TOKEN`, `DART_API_KEY` 등록
4. 배포 — `dashcloud.json`이 런타임(Python 3.12)과 진입점을 자동 설정합니다

> 노트북을 덮어도 봇이 계속 돌아갑니다. Free 플랜은 평생 무료이며 갱신·슬립이 없습니다.

## 구조

```
dart-alert-bot/
├── bot.py                       # 엔트리포인트 (기업코드 캐시·잡 등록)
├── app/
│   ├── clients/dart.py          # DART API (corpCode ZIP 파싱·공시 목록 순회)
│   ├── services/
│   │   ├── formatting.py        # 공시·아침 요약 메시지 (순수 함수)
│   │   └── repository.py        # SQLite CRUD (기업·관심기업·키워드·공시)
│   ├── handlers/dart.py         # 명령어 + 인라인 버튼 + 폴링/아침 잡
│   └── utils/                   # 메시지 분할 등 공통
└── tests/                       # 71개 (ZIP 파싱·페이지 순회·CRUD·잡 통합)
```

## 테스트

```bash
pip install -r requirements-dev.txt
ruff check . && pytest -q
```

## 라이선스

[MIT](LICENSE) — 자유롭게 복사·수정·배포하세요.
