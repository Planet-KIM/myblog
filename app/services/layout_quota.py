"""Per-user limits on stored magazine layouts.

A layout (``content_blocks`` JSON) can be up to the request size limit, and
the server copies whole layouts on small requests (save as template, new post
from a template or starter). These checks bound what one account can make the
server store: a total size budget over the user's posts and templates, and a
maximum number of saved templates. Sizes are counted in characters, as the
database's ``length()`` does.
"""
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.config import settings


def stored_layout_chars(db: Session, user_id: int) -> int:
    """Return the size of every layout the user stores.

    Counts the ``content_blocks`` of all the user's posts, including
    moderator-hidden ones, and of all their saved templates.

    Args:
        db: Database session.
        user_id: The account.

    Returns:
        The total length in characters.
    """
    posts = (
        db.query(func.coalesce(func.sum(func.length(models.BoardPost.content_blocks)), 0))
        .execution_options(include_hidden=True)
        .filter(models.BoardPost.user_id == user_id)
        .scalar()
    )
    templates = (
        db.query(func.coalesce(func.sum(func.length(models.LayoutTemplate.content_blocks)), 0))
        .filter(models.LayoutTemplate.user_id == user_id)
        .scalar()
    )
    return int(posts or 0) + int(templates or 0)


def ensure_layout_budget(db: Session, user_id: int, added_chars: int) -> None:
    """Refuse a write that would take the user over the layout budget.

    Args:
        db: Database session.
        user_id: The account.
        added_chars: How much the write grows the user's stored layouts; zero
            or less (a write that shrinks them) is always allowed.

    Raises:
        HTTPException: 413 when the stored layouts plus ``added_chars`` would
            exceed ``settings.LAYOUT_STORAGE_BUDGET_CHARS``.
    """
    if added_chars <= 0:
        return
    if stored_layout_chars(db, user_id) + added_chars > settings.LAYOUT_STORAGE_BUDGET_CHARS:
        raise HTTPException(
            status_code=413,
            detail="매거진 레이아웃 저장 용량을 모두 썼습니다. 쓰지 않는 템플릿이나 글을 지워주세요.",
        )


def ensure_template_slot(db: Session, user_id: int) -> None:
    """Refuse a new saved template once the user has the maximum number.

    Args:
        db: Database session.
        user_id: The account.

    Raises:
        HTTPException: 409 when the user already has
            ``settings.LAYOUT_TEMPLATE_LIMIT`` templates.
    """
    count = db.query(models.LayoutTemplate).filter(models.LayoutTemplate.user_id == user_id).count()
    if count >= settings.LAYOUT_TEMPLATE_LIMIT:
        raise HTTPException(
            status_code=409,
            detail=f"템플릿은 {settings.LAYOUT_TEMPLATE_LIMIT}개까지 저장할 수 있습니다. 쓰지 않는 템플릿을 지워주세요.",
        )
