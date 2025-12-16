from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .database import Base, engine
from .routers import blog, board, admin, auth, upload

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.PROJECT_NAME)

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(blog.router)
app.include_router(board.router)
app.include_router(admin.router)
app.include_router(upload.router)
