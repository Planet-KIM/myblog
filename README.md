# FastAPI Blog & Board

FastAPI + SQLAlchemy + Jinja2 기반 블로그/게시판 프로젝트입니다.  
Nginx + Gunicorn + Celery + Redis 조합으로 운영 가능한 구조를 갖추고 있으며, 에디터는 Milkdown/Tiptap 빌드 산출물을 사용합니다.

## 1. 핵심 기능

- 블로그 메인/큐레이션 피드: `/`
- CV/소개 페이지: `/main`
- 개인 대시보드(북마크, 승인 API 카탈로그, GitHub Issues): `/me`
- 게시판 목록/검색/정렬/저장글 필터: `/board/`
- 게시글 작성/수정/상세:
  - 작성: `/board/new?editor=milkdown|tiptap`
  - 수정: `/board/{post_id}/edit`
  - 상세: `/board/{post_id}`
- 카테고리 관리(로그인 필요): `/board/categories`
- 인증:
  - `/auth/signup`
  - `/auth/login`
  - `/auth/logout`
- 관리자 페이지: `/admin/` (권한 부여는 서버에서 `python3 scripts/set_admin.py <가입한 이메일>`)
- API:
  - 좋아요/북마크/팔로우
  - 태그 추천/인기 태그
  - 뉴스레터 구독/검증/해지
  - 맞춤법 검사(Celery 비동기 워커)
  - 업로드(이미지/문서/코드/아카이브/미디어)

## 2. 아키텍처

```text
Client
  -> Nginx (5052 -> 80)
  -> Gunicorn (UvicornWorker, web:8000)
  -> FastAPI app
       -> SQLite (app.db)
       -> Redis (rate-limit / queue / result)
       -> Celery Worker (spellcheck queue)
```

운영 포인트:
- Nginx가 `/static/`를 직접 서빙하고 앱으로 프록시합니다.
- Gunicorn이 프로세스(worker)를 관리합니다.
- 맞춤법 검사는 Celery 워커로 분리되어 웹 프로세스 메모리 부담을 줄입니다.

## 3. 기술 스택

- Backend: FastAPI, Starlette, SQLAlchemy, Jinja2
- Server: Gunicorn + UvicornWorker, Nginx
- Queue: Celery, Redis
- Auth: SessionMiddleware + `pbkdf2_sha256`(passlib)
- Editor build: Vite, Milkdown/Crepe, Tiptap
- ML(맞춤법): transformers, torch

## 4. 프로젝트 구조

```text
myblog/
├── app/
│   ├── main.py                 # FastAPI 엔트리포인트
│   ├── config.py               # 설정(.env)
│   ├── models.py               # DB 모델
│   ├── routers/                # blog/board/auth/admin/upload/api
│   ├── services/               # spellcheck/newsletter/recommendations 등
│   ├── tasks/                  # Celery 앱/태스크
│   ├── static/                 # css/js/editor/uploads
│   └── templates/              # Jinja 템플릿
├── frontend/                   # 에디터 JS 소스 + vite config
├── scripts/                    # 학습/데이터 파이프라인 스크립트
├── Dockerfile
├── docker-compose.yml
├── nginx.conf
├── requirements.txt          # 직접 의존성 (버전 고정)
├── constraints.txt           # 간접 의존성까지 전체 버전 (Docker 이미지와 같은 조합)
└── .env.example
```

## 5. 사전 요구사항

- Python 3.11+
- Node.js 18+
- Docker Desktop (Docker 테스트 시)

## 6. 환경변수 설정

```bash
cp .env.example .env
```

최소 필수:
- `SECRET_KEY` (필수, 없으면 앱 기동 실패)

자주 쓰는 항목:
- `DATABASE_URL` (기본: `sqlite:///./app.db`)
- `CELERY_BROKER_URL` (로컬 기본: `redis://localhost:6379/0`)
- `CELERY_RESULT_BACKEND` (로컬 기본: `redis://localhost:6379/1`)
- `REDIS_URL` (로컬 기본: `redis://localhost:6379/2`)
- `SPELLCHECK_EN_DEFAULT_VARIANT` (`vennify`/`coedit`)
- `NEWSLETTER_ENABLE_SEND` (`false` 권장: 로컬)
- `GITHUB_REPO` (`owner/repo`, 예: `Planet-KIM/myblog`)
- `GITHUB_TOKEN` (private 저장소/높은 호출량일 때 권장)

## 7. 로컬 실행 (Python 프로세스 직접 실행)

### 7.1 의존성 설치

```bash
# Docker 이미지와 같은 Python 3.11 을 쓴다 (3.9 등 오래된 Python 에서는 설치·실행이 안 될 수 있음)
python3.11 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt -c constraints.txt
```

### 7.2 프론트 빌드

```bash
cd frontend
npm install
npm run build
cd ..
```

Vite 빌드는 `frontend/vite.config.mjs`에 따라 `app/static/editor`로 출력됩니다.

### 7.3 Redis 실행 (로컬)

```bash
docker run --name fastapi-blog-redis-dev -p 6379:6379 -d redis:7-alpine
```

### 7.4 Celery 워커 실행

```bash
celery -A app.tasks worker --loglevel=info --pool=solo --concurrency=1 -Q spellcheck
```

### 7.5 FastAPI 실행

```bash
uvicorn app.main:app --reload
```

접속:
- http://127.0.0.1:8000/
- http://127.0.0.1:8000/board/

## 8. Docker 실행 (권장 테스트 경로)

### 8.1 기동

```bash
docker compose down --remove-orphans
docker compose up -d --build
docker compose ps
```

접속:
- http://127.0.0.1:5052/
- http://127.0.0.1:5052/board/

### 8.2 로그 확인

```bash
docker compose logs -f nginx web celery-worker
```

### 8.3 종료

```bash
docker compose down
```

## 9. 주요 라우트 맵

### 9.1 페이지 라우트

- `GET /` 블로그 메인
- `GET /main` CV/소개
- `GET /me` 개인 대시보드(로그인 필요)
- `GET /board/` 게시글 목록
- `GET /board/new` 작성 페이지
- `POST /board/new` 작성 처리
- `GET /board/{post_id}` 상세
- `GET /board/{post_id}/edit` 수정 페이지
- `POST /board/{post_id}/edit` 수정 처리
- `POST /board/{post_id}/delete` 삭제
- `GET /auth/signup`, `POST /auth/signup`
- `GET /auth/login`, `POST /auth/login`
- `GET /auth/logout`
- `GET /admin/`

### 9.2 API 라우트 (`/api`)

- Draft: `POST /drafts/save`
- Tag: `GET /tags/suggest`, `GET /tags/popular`
- Engagement:
  - `POST /posts/{post_id}/like`
  - `POST /posts/{post_id}/bookmark`
  - `GET /posts/{post_id}/engagement`
- Follow:
  - `POST /follow/category/{category_id}`
  - `POST /follow/author/{author_user_id}`
- Newsletter:
  - `POST /newsletter/subscribe`
  - `GET /newsletter/verify`
  - `GET /newsletter/unsubscribe`
- Recommendation: `GET /recommendations/home`
- Utility:
  - `POST /calculate-reading-time`
  - `POST /spellcheck`
- Upload:
  - `POST /upload`
  - `POST /images` (하위 호환)
  - `GET /files/{post_id}`
  - `DELETE /files/{file_id}`

## 10. 맞춤법 검사 설계 요약

- 웹 API는 Celery 태스크를 큐에 보내고 결과를 대기합니다.
- 보호 레이어:
  - 유저별 Rate Limit (`SPELLCHECK_RATE_LIMIT`, `SPELLCHECK_RATE_WINDOW`)
  - 서버 동시 처리 제한(`SPELLCHECK_MAX_CONCURRENT`)
- 장애 내성:
  - 태스크 실패 시 revoke/forget 정리 후 1회 재시도
  - 반복 실패 시 503 응답
- 워커는 `--pool=solo`, `--concurrency=1` 기준으로 운영

## 11. 업로드 정책 요약

저장 경로:
- 게시글: `app/static/uploads/{user_id}/posts/{post_id}/{type_folder}/`
- 임시글: `app/static/uploads/{user_id}/drafts/{draft_id}/{type_folder}/`

대표 제한:
- image: 10MB
- document: 50MB
- text/code: 5MB
- archive: 100MB
- video: 500MB
- audio: 50MB
- 기타: 20MB

## 12. 트러블슈팅

### 12.1 정적 파일 `ERR_CONNECTION_REFUSED`

증상:
- `/static/css/...`, `/static/js/...` 로딩 실패

확인 포인트:
1. `docker compose ps`에서 `nginx`, `web` 컨테이너가 `Up` 상태인지 확인
2. Nginx 경유 포트로 접속 중인지 확인 (`http://127.0.0.1:5052`)
3. 필요 시 재기동:

```bash
docker compose down --remove-orphans
docker compose up -d --build
```

### 12.2 맞춤법 API가 503

확인 포인트:
1. Redis 컨테이너 상태
2. Celery worker 로그(`docker compose logs -f celery-worker`)
3. `.env`의 Redis URL 설정값

### 12.3 에디터 JS가 반영되지 않음

```bash
cd frontend
npm run build
cd ..
```

브라우저 하드 리로드(캐시 무시)도 함께 권장합니다.

## 13. 보안/운영 메모

### 13.1 HTTPS 적용 (준비된 설정)

지금은 nginx(5052)로 평문 HTTP 를 받습니다. 외부에 공개하기 전에 HTTPS 를 붙이세요.

1. 도메인을 정하고, HTTPS 를 처리할 앞단을 고릅니다.
   - Cloudflare(프록시 또는 Tunnel), 또는 서버의 Caddy/nginx 가 인증서를 받아 `http://127.0.0.1:5052` 로 넘깁니다.
2. `.env` 를 바꿉니다.
   - `TRUSTED_PROXY_HOPS=1` — 방문자 IP 를 앞단이 붙인 `X-Forwarded-For` 에서 읽습니다 (레이트리밋).
   - `SESSION_COOKIE_SECURE=true` — 세션 쿠키가 HTTPS 로만 오갑니다. **HTTPS 가 붙은 뒤에** 켜세요.
   - `SITE_BASE_URL=https://내도메인` — 메일 속 링크(구독 확인, 이메일 인증)가 이 주소로 만들어집니다.
   - 앞단이 `Host` 헤더를 바꾸면 `TRUSTED_ORIGINS=https://내도메인` 도 적습니다 (쓰기 요청 허용 출처).
3. 방화벽에서 5052 포트는 앞단(프록시)에서만 접속되게 막습니다. 직접 열려 있으면 IP 헤더를 위조할 수 있습니다.
4. `docker compose up -d` 로 다시 띄웁니다. HTTPS 요청에는 HSTS 헤더가 자동으로 붙습니다.

### 13.2 기타

- 패키지 취약점 점검: `python3 scripts/check_vulns.py` — `constraints.txt` 의 버전을 공개 취약점 DB(OSV)에 조회합니다. 가끔(예: 한 달에 한 번) 돌리세요. 찾으면 종료 코드 1.
- 뉴스레터 구독 재확인: `python3 scripts/reconfirm_subscribers.py [--apply]` — 메일 없이(화면 링크로) 확정된 구독을 '확인 대기'로 되돌리고 확인 토큰을 지웁니다. 기본은 미리보기, DB 백업 뒤 `--apply`.
- `.env`는 절대 커밋하지 마세요.
- `SECRET_KEY`, SMTP 비밀번호는 운영 환경에서 안전한 비밀 저장소 사용을 권장합니다.
- 업로드 파일(`app/static/uploads`)은 백업 정책을 별도로 두는 것이 좋습니다.
- `app.db`(SQLite)는 단일 노드 개발/소규모 운영에는 편리하지만, 다중 인스턴스 운영 시 RDBMS 전환을 권장합니다.
