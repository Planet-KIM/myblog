from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine
from .routers import blog, board, admin, auth, upload

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.PROJECT_NAME)

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

app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")

@app.exception_handler(404)
async def not_found_exception_handler(request: Request, exc):
    return templates.TemplateResponse("404.html", {"request": request}, status_code=404)

@app.exception_handler(500)
async def internal_error_exception_handler(request: Request, exc):
    return templates.TemplateResponse("500.html", {"request": request}, status_code=500)

app.include_router(auth.router)
app.include_router(blog.router)
app.include_router(board.router)
app.include_router(admin.router)
app.include_router(upload.router)
