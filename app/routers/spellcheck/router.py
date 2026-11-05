"""Spell-check access page: see your level and daily quota, ask for more, withdraw a request.

The rules live in ``app/services/spellcheck_requests.py``. Here: login is
required, changes are POST only (the cross-site check in ``app/main.py``
applies), and submissions and withdrawals are rate-limited per user id.
Messages shown on the page come from fixed text, never from the URL.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import models
from app.auth_utils import get_current_user
from app.config import settings
from app.database import get_db
from app.services import spellcheck_requests as access_requests
from app.services.ratelimit import enforce
from app.services.spellcheck_access import LEVEL_LABELS, effective_level
from app.services.static_assets import asset_version

templates = Jinja2Templates(directory="app/templates")
templates.env.globals["asset_ver"] = asset_version

router = APIRouter(prefix="/spellcheck", tags=["spellcheck"])

PAGE_URL = "/spellcheck/access"
SECONDS_PER_DAY = 24 * 60 * 60
# ?msg= 로 고를 수 있는 안내 문구 (URL 의 글을 그대로 보여 주지 않는다)
NOTICES = {
    "sent": "신청했습니다. 관리자가 검토하면 알림으로 알려드립니다.",
    "cancelled": "신청을 취소했습니다.",
}


def _render(request: Request, db: Session, user: models.User, *, notice: Optional[str] = None,
            error: Optional[str] = None, status_code: int = 200):
    """Render the access page for ``user``.

    Args:
        request: The incoming request.
        db: Database session.
        user: The logged-in account.
        notice: A fixed confirmation message, if any.
        error: Why the last action was refused, if it was.
        status_code: The response status.

    Returns:
        The ``spellcheck_access.html`` page.
    """
    return templates.TemplateResponse(
        request,
        "spellcheck_access.html",
        {
            "request": request,
            "current_user": user,
            "level": effective_level(user),
            "level_labels": LEVEL_LABELS,
            "latest": access_requests.latest_request(db, user.id),
            "blocked": access_requests.request_block_reason(db, user),
            "requestable": access_requests.requestable_levels(user),
            "reason_max": access_requests.REASON_MAX_CHARS,
            "daily_limit": settings.SPELLCHECK_DAILY_LIMIT,
            "large_daily_limit": settings.SPELLCHECK_LARGE_DAILY_LIMIT,
            "notice": notice,
            "error": error,
        },
        status_code=status_code,
    )


def _limit_changes(request: Request, user: models.User) -> None:
    """Count a submission or withdrawal against the user's daily limit.

    Args:
        request: The incoming request.
        user: The logged-in account.

    Raises:
        HTTPException: 429 after ``SPELLCHECK_REQUEST_DAILY_LIMIT`` changes in 24 hours.
    """
    enforce(request, "spellcheck-request", settings.SPELLCHECK_REQUEST_DAILY_LIMIT, SECONDS_PER_DAY,
            subject=str(user.id), message="오늘은 더 신청하거나 취소할 수 없습니다. 내일 다시 시도해주세요.")


@router.get("/access", response_class=HTMLResponse)
def access_page(
    request: Request,
    msg: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Show the user's spell-check level, quota, latest request and the request form.

    Args:
        request: The incoming request.
        msg: Key of a confirmation message (``NOTICES``); others are ignored.
        db: Database session.
        current_user: The logged-in user.

    Returns:
        The ``spellcheck_access.html`` page.

    Raises:
        HTTPException: 401 if not logged in.
    """
    return _render(request, db, current_user, notice=NOTICES.get(msg or ""))


@router.post("/access/request", response_class=HTMLResponse)
def submit_request(
    request: Request,
    level: int = Form(...),
    reason: str = Form(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """File a spell-check access request.

    Args:
        request: The incoming request.
        level: The level asked for (1 or 2).
        reason: The user's note to the admin.
        db: Database session.
        current_user: The logged-in user.

    Returns:
        A 303 redirect to the page with a confirmation, or the page with the
        reason for refusing and status 400.

    Raises:
        HTTPException: 401 if not logged in, 429 over the daily change limit.
    """
    _limit_changes(request, current_user)
    try:
        access_requests.create_request(db, current_user, level, reason)
    except access_requests.RequestRefused as exc:
        return _render(request, db, current_user, error=str(exc), status_code=400)
    return RedirectResponse(f"{PAGE_URL}?msg=sent", status_code=303)


@router.post("/access/cancel")
def cancel_request(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Withdraw the user's pending request.

    Args:
        request: The incoming request.
        db: Database session.
        current_user: The logged-in user.

    Returns:
        A 303 redirect to the page.

    Raises:
        HTTPException: 401 if not logged in, 429 over the daily change limit.
    """
    _limit_changes(request, current_user)
    cancelled = access_requests.cancel_request(db, current_user)
    return RedirectResponse(f"{PAGE_URL}?msg=cancelled" if cancelled else PAGE_URL, status_code=303)
