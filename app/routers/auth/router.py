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

from app.database import get_db
from app import models
from app.auth_utils import (
    get_password_hash,
    verify_password,
    validate_password_rule,
    get_current_user_optional,
)

router = APIRouter(prefix="/auth", tags=["auth"])

templates = Jinja2Templates(directory="app/templates")


# ─────────────────────────────────────
# 회원가입 폼
# ─────────────────────────────────────
@router.get("/signup", response_class=HTMLResponse)
def signup_form(
    request: Request,
    current_user=Depends(get_current_user_optional),
):
    # 이미 로그인 되어 있으면 보드로 리다이렉트
    if current_user:
        return RedirectResponse("/board/", status_code=303)

    return templates.TemplateResponse(
        "signup.html",
        {
            "request": request,
            "error": None,
            "email": "",
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
    db: Session = Depends(get_db),
):
    email = email.strip().lower()

    # 비밀번호 일치 확인
    if password != password_confirm:
        return templates.TemplateResponse(
            "signup.html",
            {
                "request": request,
                "error": "비밀번호가 서로 일치하지 않습니다.",
                "email": email,
            },
            status_code=400,
        )

    # 비밀번호 규칙 체크
    try:
        validate_password_rule(password)
    except HTTPException as e:
        return templates.TemplateResponse(
            "signup.html",
            {
                "request": request,
                "error": e.detail,
                "email": email,
            },
            status_code=400,
        )

    # 이메일 중복 확인
    existing = db.query(models.User).filter(models.User.email == email).first()
    if existing:
        return templates.TemplateResponse(
            "signup.html",
            {
                "request": request,
                "error": "이미 사용 중인 이메일입니다.",
                "email": email,
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

    # 가입 후 자동 로그인
    request.session["user_id"] = user.id

    return RedirectResponse("/board/", status_code=303)


# ─────────────────────────────────────
# 로그인 폼
# ─────────────────────────────────────
@router.get("/login", response_class=HTMLResponse)
def login_form(
    request: Request,
    current_user=Depends(get_current_user_optional),
):
    if current_user:
        return RedirectResponse("/board/", status_code=303)

    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": None,
            "email": "",
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
    db: Session = Depends(get_db),
):
    email = email.strip().lower()

    user = db.query(models.User).filter(models.User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "이메일 또는 비밀번호가 올바르지 않습니다.",
                "email": email,
            },
            status_code=400,
        )

    # 세션에 user_id 저장
    request.session["user_id"] = user.id

    return RedirectResponse("/board/", status_code=303)


# ─────────────────────────────────────
# 로그아웃
# ─────────────────────────────────────
@router.get("/logout")
def logout(request: Request):
    request.session.pop("user_id", None)
    return RedirectResponse("/", status_code=303)

