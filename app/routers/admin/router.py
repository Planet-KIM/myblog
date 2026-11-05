"""Admin pages: moderation dashboard, hide/unhide, report resolution, digest,
spell-check access levels and access requests.

Every route requires a logged-in admin. Queries here pass
``include_hidden=True`` so admins also see moderated (hidden) content.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.auth_utils import get_current_user
from app.routers.api import recount_tags
from app.services import spellcheck_requests as access_requests
from app.services.spellcheck_access import LEVEL_LABELS
from app.services.static_assets import asset_version

# 맞춤법 권한 표에 보여 줄 최대 계정 수
SPELLCHECK_USER_LIMIT = 200

templates = Jinja2Templates(directory="app/templates")
templates.env.globals["asset_ver"] = asset_version

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(user: models.User) -> None:
    """Ensure the user is an admin.

    Args:
        user: The logged-in user.

    Raises:
        HTTPException: 403 if ``user.is_admin`` is false.
    """
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Render the admin dashboard.

    Shows the total post count and the 20 newest posts (hidden ones included),
    plus up to 50 open reports, each with a short summary of its target, whether
    the target is hidden or deleted, and a link to it, the pending and recent
    spell-check access requests, and the accounts with their spell-check
    level. The ``digest`` query parameter, set after a digest send, is shown
    as a status message.

    Args:
        request: The incoming request.
        db: Database session.
        current_user: The logged-in user.

    Returns:
        The ``admin_dashboard.html`` page.

    Raises:
        HTTPException: 401 if not logged in, 403 if not an admin.
    """
    _require_admin(current_user)

    # 관리자: 숨김 포함 전체 집계/목록
    base = db.query(models.BoardPost).execution_options(include_hidden=True)
    post_count = base.count()
    posts = base.order_by(models.BoardPost.created_at.desc()).limit(20).all()

    open_reports = (
        db.query(models.Report)
        .filter(models.Report.resolved == False)  # noqa: E712
        .order_by(models.Report.created_at.desc())
        .limit(50)
        .all()
    )
    report_items = []
    for r in open_reports:
        if r.target_type == "post":
            target = (
                db.query(models.BoardPost).execution_options(include_hidden=True)
                .filter_by(id=r.target_id).first()
            )
            summary = target.title if target else "(삭제됨)"
            link = f"/board/{r.target_id}"
        else:
            target = (
                db.query(models.Comment).execution_options(include_hidden=True)
                .filter_by(id=r.target_id).first()
            )
            summary = (target.body[:60] if target else "(삭제됨)")
            link = f"/board/{target.post_id}#comments" if target else "#"
        report_items.append({
            "report": r,
            "summary": summary,
            "hidden": bool(target.is_hidden) if target else None,
            "exists": target is not None,
            "link": link,
        })

    pending_requests, decided_requests = access_requests.review_queue(db)

    return templates.TemplateResponse(
        request,
        "admin_dashboard.html",
        {
            "request": request,
            "post_count": post_count,
            "posts": posts,
            "report_items": report_items,
            "current_user": current_user,
            "digest_msg": request.query_params.get("digest"),
            "users": db.query(models.User).order_by(models.User.id.asc()).limit(SPELLCHECK_USER_LIMIT).all(),
            "spellcheck_levels": LEVEL_LABELS,
            "pending_requests": pending_requests,
            "decided_requests": decided_requests,
            "note_max": access_requests.NOTE_MAX_CHARS,
        },
    )


def _decide_spellcheck_request(db: Session, request_id: int, admin: models.User, approve: bool,
                               granted_level: Optional[int], note: str) -> RedirectResponse:
    """Approve or reject a spell-check access request and go back to the dashboard.

    Args:
        db: Database session.
        request_id: The request.
        admin: The logged-in admin (already checked).
        approve: True to approve, False to reject.
        granted_level: Level to grant on approval.
        note: The admin's note to the requester.

    Returns:
        A 303 redirect to the requests section of ``/admin/``.

    Raises:
        HTTPException: 404 if the request does not exist, 409 if it is
            already decided or the level is not allowed.
    """
    try:
        access_requests.decide_request(db, request_id, admin, approve, granted_level, note)
    except access_requests.RequestNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except access_requests.RequestRefused as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return RedirectResponse("/admin/#spellcheck-requests", status_code=303)


@router.post("/spellcheck-requests/{request_id}/approve")
def admin_approve_spellcheck_request(
    request_id: int,
    granted_level: int = Form(...),
    note: str = Form(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Approve a spell-check access request, granting at most the requested level.

    Args:
        request_id: The request.
        granted_level: 1 or 2, not above what was requested.
        note: Optional note to the requester.
        db: Database session.
        current_user: The logged-in user.

    Returns:
        A 303 redirect to ``/admin/``.

    Raises:
        HTTPException: 401/403 if not an admin, 404/409 from
            :func:`_decide_spellcheck_request`.
    """
    _require_admin(current_user)
    return _decide_spellcheck_request(db, request_id, current_user, True, granted_level, note)


@router.post("/spellcheck-requests/{request_id}/reject")
def admin_reject_spellcheck_request(
    request_id: int,
    note: str = Form(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Reject a spell-check access request (the user may ask again after the cooldown).

    Args:
        request_id: The request.
        note: Optional note to the requester.
        db: Database session.
        current_user: The logged-in user.

    Returns:
        A 303 redirect to ``/admin/``.

    Raises:
        HTTPException: 401/403 if not an admin, 404/409 from
            :func:`_decide_spellcheck_request`.
    """
    _require_admin(current_user)
    return _decide_spellcheck_request(db, request_id, current_user, False, None, note)


@router.post("/users/{user_id}/spellcheck")
def admin_set_spellcheck_level(
    user_id: int,
    level: int = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Set an account's spell-check level.

    Args:
        user_id: The account.
        level: 0 (none), 1 (fast models) or 2 (large models too).
        db: Database session.
        current_user: The logged-in user.

    Returns:
        A 303 redirect to the spell-check section of ``/admin/``.

    Raises:
        HTTPException: 401 if not logged in, 403 if not an admin, 400 for an
            unknown level, 404 if the account does not exist.
    """
    _require_admin(current_user)
    if level not in LEVEL_LABELS:
        raise HTTPException(status_code=400, detail="알 수 없는 등급입니다.")
    user = db.query(models.User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다.")
    user.spellcheck_level = level
    db.commit()
    return RedirectResponse("/admin/#spellcheck", status_code=303)


@router.post("/moderate")
def admin_moderate(
    target_type: str = Form(...),
    target_id: int = Form(...),
    action: str = Form(...),  # "hide" | "unhide"
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Hide or unhide a post or comment (a post's tags are recounted).

    Args:
        target_type: ``"post"`` for a post; any other value means a comment.
        target_id: Id of the post or comment.
        action: ``"hide"`` hides the target; any other value unhides it.
        db: Database session.
        current_user: The logged-in user.

    Returns:
        A 303 redirect to ``/admin/``.

    Raises:
        HTTPException: 401 if not logged in, 403 if not an admin, 404 if the
            target does not exist.
    """
    _require_admin(current_user)
    model = models.BoardPost if target_type == "post" else models.Comment
    obj = db.query(model).execution_options(include_hidden=True).filter_by(id=target_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="대상을 찾을 수 없습니다.")
    obj.is_hidden = (action == "hide")
    if model is models.BoardPost:
        recount_tags(db, obj.tags)   # 숨긴 글은 공개 태그 수에서 빠진다
    db.commit()
    return RedirectResponse("/admin/", status_code=303)


@router.post("/reports/{report_id}/resolve")
def admin_resolve_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Mark a moderation report as resolved.

    Args:
        report_id: Id of the report.
        db: Database session.
        current_user: The logged-in user.

    Returns:
        A 303 redirect to ``/admin/``.

    Raises:
        HTTPException: 401 if not logged in, 403 if not an admin, 404 if the
            report does not exist.
    """
    _require_admin(current_user)
    report = db.query(models.Report).filter_by(id=report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="신고를 찾을 수 없습니다.")
    report.resolved = True
    db.commit()
    return RedirectResponse("/admin/", status_code=303)


@router.get("/digest/preview", response_class=HTMLResponse)
def admin_digest_preview(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Preview the weekly digest email as HTML without sending it.

    Args:
        request: The incoming request; its base URL is used for post links.
        db: Database session.
        current_user: The logged-in user.

    Returns:
        The digest's HTML body, or a short "no posts to send" page when there
        is nothing to include.

    Raises:
        HTTPException: 401 if not logged in, 403 if not an admin.
    """
    _require_admin(current_user)
    from app.services.digest import build_weekly_digest
    digest = build_weekly_digest(db, str(request.base_url))
    if not digest:
        return HTMLResponse("<p style='font-family:sans-serif;padding:2rem;'>보낼 글이 없습니다.</p>")
    return HTMLResponse(digest["html"])


@router.post("/digest/send")
def admin_digest_send(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Send the weekly digest to all confirmed newsletter subscribers now.

    Args:
        request: The incoming request; its base URL is used for links.
        db: Database session.
        current_user: The logged-in user.

    Returns:
        A 303 redirect to ``/admin/`` with a ``digest`` query parameter that
        reports the number of mails sent, or why sending was skipped.

    Raises:
        HTTPException: 401 if not logged in, 403 if not an admin.
    """
    _require_admin(current_user)
    from app.services.digest import send_weekly_digest
    result = send_weekly_digest(db, str(request.base_url))
    from urllib.parse import urlencode
    msg = (f"발송 {result.get('sent', 0)}건" if not result.get("skipped")
           else f"건너뜀 ({result.get('reason')})")
    return RedirectResponse("/admin/?" + urlencode({"digest": msg}), status_code=303)
