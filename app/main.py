import asyncio
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import blog, board, admin, auth, upload, api

# DB 스키마는 Alembic이 단일 소스로 관리합니다 (create_all 제거: alembic 마이그레이션과의 충돌 방지).
#   신규 설치:  alembic upgrade head
#   기존 DB:    alembic stamp 0001 && alembic upgrade head


# ── 서버 시작/종료 수명주기 ────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    서버 시작 시:
      - 맞춤법 모델은 웹서버에 로드하지 않음
        → 모델은 Celery 워커 프로세스에서만 로드 (메모리 중복 방지)
        → 웹서버는 task를 Celery에 전달하고 결과만 받음
      - 동시 추론 제한용 asyncio.Semaphore 초기화
    """
    # 동시 추론 세마포어 — api.py에서 req.app.state.spellcheck_semaphore 로 접근
    app.state.spellcheck_semaphore = asyncio.Semaphore(
        settings.SPELLCHECK_MAX_CONCURRENT
    )
    print(
        f"[Startup] 준비 완료 "
        f"(맞춤법은 Celery 워커 전담, "
        f"동시 태스크 최대 {settings.SPELLCHECK_MAX_CONCURRENT}개, "
        f"유저당 {settings.SPELLCHECK_RATE_LIMIT}회/{settings.SPELLCHECK_RATE_WINDOW}s)"
    )

    yield  # ← 이 지점부터 서버가 요청을 받기 시작

    print("[Shutdown] 서버 종료")


# ── 앱 인스턴스 ───────────────────────────────────────────
app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 실제 서비스 시 도메인으로 제한 권장
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# same_site="lax" helps prevent CSRF by preventing the browser from sending
# the session cookie along with cross-site POST requests.
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY, same_site="lax")


# ── Body 크기 제한 미들웨어 ───────────────────────────────
# add_middleware 보다 나중에 선언된 @app.middleware("http") 가
# 스택에서 가장 바깥에 쌓이므로 가장 먼저 실행됨.
# 즉, SessionMiddleware / CORSMiddleware 전에 크기 초과 요청을 차단.
@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    """
    HTTP 요청 body 크기 제한.
    Content-Length 헤더 기준으로 BOARD_MAX_BODY_SIZE(기본 50MB) 초과 시
    413 반환. 글 저장 시 content_blocks JSON + content_html 합산 크기가
    이 한도 이하여야 함. 순수 텍스트 기준 수백만 자 수용 가능.
    """
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings.BOARD_MAX_BODY_SIZE:
        return JSONResponse(
            status_code=413,
            content={
                "detail": (
                    f"요청 크기가 너무 큽니다. "
                    f"최대 {settings.BOARD_MAX_BODY_SIZE // (1024 * 1024)}MB까지 허용됩니다."
                )
            },
        )
    return await call_next(request)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")


@app.exception_handler(404)
async def not_found_exception_handler(request: Request, _exc):
    return templates.TemplateResponse(request, "404.html", {"request": request}, status_code=404)


@app.exception_handler(500)
async def internal_error_exception_handler(request: Request, _exc):
    return templates.TemplateResponse(request, "500.html", {"request": request}, status_code=500)


def _is_api_request(request: Request) -> bool:
    """API 경로 또는 XHR 요청이면 JSON으로 응답하도록 구분."""
    return (
        request.url.path.startswith("/api/")
        or request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"
    )


@app.exception_handler(401)
async def unauthorized_exception_handler(request: Request, exc):
    """미인증(401): 페이지는 로그인으로 리다이렉트(원위치 next 보존), API는 JSON."""
    detail = getattr(exc, "detail", "로그인이 필요합니다.")
    if _is_api_request(request):
        return JSONResponse(status_code=401, content={"detail": detail})
    if request.method == "GET":
        next_path = request.url.path
        if request.url.query:
            next_path = f"{next_path}?{request.url.query}"
        return RedirectResponse(f"/auth/login?next={quote(next_path, safe='/?=&')}", status_code=303)
    return RedirectResponse("/auth/login", status_code=303)


@app.exception_handler(403)
async def forbidden_exception_handler(request: Request, exc):
    """권한 없음(403): 로그인했지만 접근 불가. 페이지는 안내 화면, API는 JSON."""
    detail = getattr(exc, "detail", "접근 권한이 없습니다.")
    if _is_api_request(request):
        return JSONResponse(status_code=403, content={"detail": detail})
    return templates.TemplateResponse(
        request, "403.html", {"request": request}, status_code=403
    )


app.include_router(auth.router)
app.include_router(blog.router)
app.include_router(board.router)
app.include_router(admin.router)
app.include_router(upload.router)
app.include_router(api.router)
