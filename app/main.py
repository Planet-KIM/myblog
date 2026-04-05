import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine
from .routers import blog, board, admin, auth, upload, api

Base.metadata.create_all(bind=engine)


# ── 서버 시작/종료 수명주기 ────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    서버 시작 시:
      1. 맞춤법 모델 두 개를 별도 스레드에서 미리 로드 (Eager Loading)
         → 첫 요청 지연(20~30초) 제거
      2. 동시 추론 제한용 asyncio.Semaphore 초기화
         → 설정값: SPELLCHECK_MAX_CONCURRENT (기본 2)

    서버 종료 시:
      별도 정리 작업 없음 (모델은 프로세스 종료와 함께 해제됨)
    """
    print(f"[Startup] 맞춤법 모델 로딩 시작 (백그라운드 스레드)...")

    loop = asyncio.get_event_loop()
    try:
        from app.services.spellcheck import load_all
        # 모델 로드는 블로킹 IO → run_in_executor 로 이벤트루프 막지 않음
        await loop.run_in_executor(None, load_all)
    except Exception as e:
        # 모델 로드 실패해도 서버는 기동 (맞춤법 API만 503 반환)
        print(f"[Startup] 모델 로딩 실패 (맞춤법 API 비활성화): {e}")

    # 동시 추론 세마포어 — api.py에서 req.app.state.spellcheck_semaphore 로 접근
    app.state.spellcheck_semaphore = asyncio.Semaphore(
        settings.SPELLCHECK_MAX_CONCURRENT
    )
    print(
        f"[Startup] 준비 완료 "
        f"(동시 추론 최대 {settings.SPELLCHECK_MAX_CONCURRENT}개, "
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
    return templates.TemplateResponse("404.html", {"request": request}, status_code=404)


@app.exception_handler(500)
async def internal_error_exception_handler(request: Request, _exc):
    return templates.TemplateResponse("500.html", {"request": request}, status_code=500)


app.include_router(auth.router)
app.include_router(blog.router)
app.include_router(board.router)
app.include_router(admin.router)
app.include_router(upload.router)
app.include_router(api.router)
