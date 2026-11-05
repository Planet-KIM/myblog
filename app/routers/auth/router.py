"""Authentication pages: signup, login, logout and email verification.

Login state is the ``user_id`` stored in the signed session cookie. Signup
and login are rate-limited per client IP, and login also per account. Admin
rights are never granted here; operators use ``scripts/set_admin.py``.
"""
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
from app.services import email_verification
from app.services.profile import generate_unique_handle
from app.services.ratelimit import enforce
from app.services.static_assets import asset_version
from app.auth_utils import (
    get_password_hash,
    verify_password,
    validate_password_rule,
    get_current_user,
    get_current_user_optional,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# 로그아웃 직후 다음 페이지에서 브라우저에 남은 계정 데이터를 지우라는 표시 (app.js 가 읽고 지운다)
LOGGED_OUT_COOKIE = "logged_out"

templates = Jinja2Templates(directory="app/templates")
templates.env.globals["asset_ver"] = asset_version


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


# ─────────────────────────────────────
# 회원가입 폼
# ─────────────────────────────────────
@router.get("/signup", response_class=HTMLResponse)
def signup_form(
    request: Request,
    next: Optional[str] = None,
    current_user=Depends(get_current_user_optional),
):
    """Show the signup form, or redirect users who are already logged in.

    Args:
        request: The incoming request.
        next: Local path to go to after signing up.
        current_user: The logged-in user, or None.

    Returns:
        The ``signup.html`` page, or a 303 redirect to the safe ``next`` path
        (default ``/board/``) when already logged in.
    """
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
    """Create an account, log it in and redirect.

    The email is trimmed and lower-cased. On success the user gets an
    auto-generated blog handle and is logged in, and, while email
    verification is active, a verification mail. An unverified email never
    grants anything (admin rights included).

    Args:
        request: The incoming request.
        email: Email address for the account.
        password: Chosen password.
        password_confirm: Password typed a second time.
        next: Local path to go to after signing up.
        db: Database session.

    Returns:
        A 303 redirect to the safe ``next`` path (default ``/board/``), or the
        ``signup.html`` page with an error and status 400 when the passwords
        differ, the password breaks the strength rule, or the email is taken.

    Raises:
        HTTPException: 429 when the signup rate limit is exceeded.
    """
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

    # 인증이 켜져 있으면 인증 메일 (보내지 못해도 가입은 끝난다: 인증 화면에서 다시 보낼 수 있다)
    if email_verification.verification_active():
        email_verification.send_verification(user, _site_base(request))

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
    """Show the login form, or redirect users who are already logged in.

    Args:
        request: The incoming request.
        next: Local path to go to after logging in.
        current_user: The logged-in user, or None.

    Returns:
        The ``login.html`` page, or a 303 redirect to the safe ``next`` path
        (default ``/board/``) when already logged in.
    """
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
    """Check the credentials and log the user in.

    Attempts are limited per client IP and, so that changing IPs does not
    help, per account email as well.

    Args:
        request: The incoming request.
        email: Email address; trimmed and lower-cased before lookup.
        password: Password to verify.
        next: Local path to go to after logging in.
        db: Database session.

    Returns:
        A 303 redirect to the safe ``next`` path (default ``/board/``), or the
        ``login.html`` page with an error and status 400 when the email or
        password is wrong.

    Raises:
        HTTPException: 429 when the IP or the account login limit is exceeded.
    """
    enforce(request, "login", settings.LOGIN_RATE_LIMIT, settings.LOGIN_RATE_WINDOW,
            message="로그인 시도가 너무 많습니다. 잠시 후 다시 시도해주세요.")
    email = email.strip().lower()
    enforce(request, "login-account", settings.LOGIN_ACCOUNT_RATE_LIMIT,
            settings.LOGIN_ACCOUNT_RATE_WINDOW, subject=email,
            message="이 계정의 로그인 시도가 너무 많습니다. 잠시 후 다시 시도해주세요.")

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

    # 세션에 user_id 저장
    request.session["user_id"] = user.id

    return RedirectResponse(safe_next_url(next), status_code=303)


# ─────────────────────────────────────
# 이메일 인증
# ─────────────────────────────────────
# ?reason= 로 고를 수 있는 안내 문구 (URL 의 글을 그대로 보여 주지 않는다)
VERIFY_NOTICES = {
    "publish": "글은 비공개로 저장했습니다. 이메일을 인증한 뒤 공개로 바꿀 수 있습니다.",
    "sent": "인증 메일을 보냈습니다. 메일함(스팸함 포함)을 확인해주세요.",
    "unsent": "지금은 인증 메일을 보낼 수 없습니다. 잠시 후 다시 시도해주세요.",
}


def _site_base(request: Request) -> str:
    """Return the site URL for links in mails: ``SITE_BASE_URL``, else the request's base."""
    return settings.SITE_BASE_URL.strip() or str(request.base_url)


def _verify_page(request: Request, user, *, result: Optional[str] = None, reason: Optional[str] = None,
                 next_url: Optional[str] = None, status_code: int = 200):
    """Render the email verification page.

    Args:
        request: The incoming request.
        user: The logged-in account, or None.
        result: ``"ok"`` or ``"invalid"`` after a link was opened.
        reason: Key of a ``VERIFY_NOTICES`` message.
        next_url: A safe local path to offer as "go back".
        status_code: The response status.

    Returns:
        The ``verify_email.html`` page.
    """
    return templates.TemplateResponse(
        request,
        "verify_email.html",
        {
            "request": request,
            "current_user": user,
            "active": email_verification.verification_active(),
            "verified": email_verification.is_verified(user) if user else False,
            "result": result,
            "notice": VERIFY_NOTICES.get(reason or ""),
            "next": next_url,
        },
        status_code=status_code,
    )


@router.get("/verify-email", response_class=HTMLResponse)
def verify_email(
    request: Request,
    token: Optional[str] = None,
    reason: Optional[str] = None,
    next: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_optional),
):
    """Verify an email from a mailed link, or show the account's verification status.

    Opening the link works without being logged in: the signed token itself
    proves the mail was received.

    Args:
        request: The incoming request.
        token: The token from the mailed link, if any.
        reason: Key of a notice to show (``VERIFY_NOTICES``).
        next: Local path to offer as "go back".
        db: Database session.
        current_user: The logged-in user, or None.

    Returns:
        The verification page; 400 for an invalid or expired link, and a
        redirect to the login page when opened without a token or a session.
    """
    if token:
        user = email_verification.confirm_token(db, token)
        return _verify_page(request, current_user or user, result="ok" if user else "invalid",
                            status_code=200 if user else 400)
    if current_user is None:
        return RedirectResponse("/auth/login?next=/auth/verify-email", status_code=303)
    return _verify_page(request, current_user, reason=reason,
                        next_url=safe_next_url(next, default="") if next else None)


@router.post("/verify-email/resend")
def resend_verification(
    request: Request,
    current_user=Depends(get_current_user),
):
    """Mail the logged-in user a new verification link.

    Limited per user (``EMAIL_VERIFY_RESEND_LIMIT`` per hour), so the form
    cannot be used to flood a mailbox.

    Args:
        request: The incoming request.
        current_user: The logged-in user.

    Returns:
        A 303 redirect to the verification page with a notice.

    Raises:
        HTTPException: 401 if not logged in, 429 over the resend limit.
    """
    if email_verification.is_verified(current_user) or not email_verification.verification_active():
        return RedirectResponse("/auth/verify-email", status_code=303)
    enforce(request, "verify-resend", settings.EMAIL_VERIFY_RESEND_LIMIT, 3600, subject=str(current_user.id),
            message="인증 메일을 너무 자주 요청했습니다. 잠시 후 다시 시도해주세요.")
    sent, _info = email_verification.send_verification(current_user, _site_base(request))
    return RedirectResponse(f"/auth/verify-email?reason={'sent' if sent else 'unsent'}", status_code=303)


# ─────────────────────────────────────
# 로그아웃
# ─────────────────────────────────────
@router.get("/logout")
def logout(request: Request):
    """Log the user out by removing ``user_id`` from the session.

    Also sets a short-lived ``logged_out`` cookie; ``static/js/app.js`` sees
    it on the next page and removes what the account left in this browser
    (recently read posts, magazine editor autosaves). ``Clear-Site-Data:
    "cache"`` empties the pages the browser kept, back/forward cache
    included, so "back" does not show signed-in pages.

    Args:
        request: The incoming request.

    Returns:
        A 303 redirect to the home page.
    """
    request.session.pop("user_id", None)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(LOGGED_OUT_COOKIE, "1", max_age=300, path="/", samesite="lax",
                        secure=settings.SESSION_COOKIE_SECURE)
    # 이 브라우저에 저장된 페이지(뒤로 가기 캐시 포함)를 비운다
    response.headers["Clear-Site-Data"] = '"cache"'
    return response
