from typing import Optional
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..auth_utils import get_current_user_optional
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user_optional),
):
    post_count = db.query(models.BoardPost).count()
    posts = db.query(models.BoardPost).order_by(models.BoardPost.created_at.desc()).limit(20).all()
    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "post_count": post_count,
            "posts": posts,
            "current_user": current_user,
        },
    )
