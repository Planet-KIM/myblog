"""SQLAlchemy engine, session factory and declarative base.

Exposes ``engine``, ``SessionLocal``, ``Base`` and the ``get_db`` FastAPI
dependency. It also installs a session-wide ORM hook that hides moderated
(``is_hidden``) posts and comments from every SELECT by default.
"""
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, with_loader_criteria

from .config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# ── 모더레이션: 숨김 콘텐츠 전역 제외 ─────────────────────
# 모든 BoardPost/Comment SELECT에서 is_hidden=True 를 자동 제외한다.
# 관리자 조회 등 숨김까지 봐야 할 때는 .execution_options(include_hidden=True) 로 우회.
@event.listens_for(SessionLocal, "do_orm_execute")
def _exclude_hidden(execute_state):
    """Filter hidden posts and comments out of every ORM SELECT.

    Runs on each ``do_orm_execute`` event of ``SessionLocal`` sessions and
    adds loader criteria ``is_hidden == False`` for ``BoardPost`` and
    ``Comment`` (including aliases and relationship loads). Non-SELECT
    statements, and statements run with
    ``.execution_options(include_hidden=True)``, are left untouched.

    Args:
        execute_state: SQLAlchemy ``ORMExecuteState``; its ``statement`` is
            replaced in place.
    """
    if not execute_state.is_select:
        return
    if execute_state.execution_options.get("include_hidden", False):
        return
    from app import models  # 지연 임포트(순환 방지)

    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            models.BoardPost, models.BoardPost.is_hidden == False, include_aliases=True  # noqa: E712
        ),
        with_loader_criteria(
            models.Comment, models.Comment.is_hidden == False, include_aliases=True  # noqa: E712
        ),
    )


def get_db():
    """Provide a database session for one request (FastAPI dependency).

    Yields:
        A new ``SessionLocal`` session, closed when the request finishes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
