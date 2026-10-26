"""Admin pages: moderation dashboard, hide/unhide, report resolution and digest.

Every route requires a logged-in admin. Queries here pass
``include_hidden=True`` so admins also see moderated (hidden) content.
"""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.auth_utils import get_current_user

templates = Jinja2Templates(directory="app/templates")

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
    the target is hidden or deleted, and a link to it. The ``digest`` query
    parameter, set after a digest send, is shown as a status message.

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
        },
    )


@router.post("/moderate")
def admin_moderate(
    target_type: str = Form(...),
    target_id: int = Form(...),
    action: str = Form(...),  # "hide" | "unhide"
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Hide or unhide a post or comment.

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
