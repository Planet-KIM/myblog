from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from urllib.parse import urlparse

from app.config import settings
from app.database import get_db
from app import models
from app.services.profile import generate_unique_handle
from app.services.ratelimit import enforce
from app.auth_utils import (
    get_password_hash,
    verify_password,
    validate_password_rule,
    get_current_user_optional,
)

router = APIRouter(prefix="/auth", tags=["auth"])

templates = Jinja2Templates(directory="app/templates")


def safe_next_url(next_url: Optional[str], default: str = "/board/") -> str:
    """오픈 리다이렉트 방지: 로컬 경로만 허용한다."""
    if not next_url:
        return default
    if any(c in next_url for c in "\r\n\t ") or not next_url.startswith("/") or next_url.startswith("//"):
        return default
    parsed = urlparse(next_url)
    if parsed.scheme or parsed.netloc:
        return default
    return next_url


def _admin_emails() -> set[str]:
    return {e.strip().lower() for e in (settings.ADMIN_EMAILS or "").split(",") if e.strip()}


def maybe_promote_admin(user: models.User, db: Session) -> None:
    """ADMIN_EMAILS에 포함된 계정을 로그인 시 is_admin으로 승격."""
    if user.email.lower() in _admin_emails() and not user.is_admin:
        user.is_admin = True
        db.commit()


# ─────────────────────────────────────
# 회원가입 폼
# ─────────────────────────────────────
@router.get("/signup", response_class=HTMLResponse)
def signup_form(
    request: Request,
    next: Optional[str] = None,
    current_user=Depends(get_current_user_optional),
):
    # 이미 로그인 되어 있으면 보드로 리다이렉트
    if current_user:
        return RedirectResponse(safe_next_url(next), status_code=303)

    return templates.TemplateResponse(
        request,
        "signup.html",
        {
            "request": request,
            "error": None,
            "email": "",
            "next": next or "",
        },
    )


# ─────────────────────────────────────
# 회원가입 처리
# ─────────────────────────────────────
@router.post("/signup", response_class=HTMLResponse)
def signup(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    next: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    enforce(request, "signup", settings.SIGNUP_RATE_LIMIT, settings.SIGNUP_RATE_WINDOW,
            message="가입 시도가 너무 많습니다. 잠시 후 다시 시도해주세요.")
    email = email.strip().lower()

    # 비밀번호 일치 확인
    if password != password_confirm:
        return templates.TemplateResponse(
            request,
            "signup.html",
            {
                "request": request,
                "error": "비밀번호가 서로 일치하지 않습니다.",
                "email": email,
                "next": next or "",
            },
            status_code=400,
        )

    # 비밀번호 규칙 체크
    try:
        validate_password_rule(password)
    except HTTPException as e:
        return templates.TemplateResponse(
            request,
            "signup.html",
            {
                "request": request,
                "error": e.detail,
                "email": email,
                "next": next or "",
            },
            status_code=400,
        )

    # 이메일 중복 확인
    existing = db.query(models.User).filter(models.User.email == email).first()
    if existing:
        return templates.TemplateResponse(
            request,
            "signup.html",
            {
                "request": request,
                "error": "이미 사용 중인 이메일입니다.",
                "email": email,
                "next": next or "",
            },
            status_code=400,
        )

    # 사용자 생성
    user = models.User(
        email=email,
        password_hash=get_password_hash(password),
        is_admin=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # 가입 시 블로그 핸들 자동 생성 (/@handle 즉시 사용 가능)
    user.handle = generate_unique_handle(db, user.email)
    db.commit()

    # ADMIN_EMAILS에 해당하면 관리자 승격
    maybe_promote_admin(user, db)

    # 가입 후 자동 로그인
    request.session["user_id"] = user.id

    return RedirectResponse(safe_next_url(next), status_code=303)


# ─────────────────────────────────────
# 로그인 폼
# ─────────────────────────────────────
@router.get("/login", response_class=HTMLResponse)
def login_form(
    request: Request,
    next: Optional[str] = None,
    current_user=Depends(get_current_user_optional),
):
    if current_user:
        return RedirectResponse(safe_next_url(next), status_code=303)

    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "request": request,
            "error": None,
            "email": "",
            "next": next or "",
        },
    )


# ─────────────────────────────────────
# 로그인 처리
# ─────────────────────────────────────
@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    enforce(request, "login", settings.LOGIN_RATE_LIMIT, settings.LOGIN_RATE_WINDOW,
            message="로그인 시도가 너무 많습니다. 잠시 후 다시 시도해주세요.")
    email = email.strip().lower()

    user = db.query(models.User).filter(models.User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "request": request,
                "error": "이메일 또는 비밀번호가 올바르지 않습니다.",
                "email": email,
                "next": next or "",
            },
            status_code=400,
        )

    # ADMIN_EMAILS에 포함된 계정이면 관리자로 승격
    maybe_promote_admin(user, db)

    # 세션에 user_id 저장
    request.session["user_id"] = user.id

    return RedirectResponse(safe_next_url(next), status_code=303)


# ─────────────────────────────────────
# 로그아웃
# ─────────────────────────────────────
@router.get("/logout")
def logout(request: Request):
    request.session.pop("user_id", None)
    return RedirectResponse("/", status_code=303)
