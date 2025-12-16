from typing import Optional
from pathlib import Path
import re

from fastapi import (
    APIRouter, Depends, Form, HTTPException, Request
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from ..auth_utils import get_current_user, get_current_user_optional

router = APIRouter(prefix="/board", tags=["board"])

templates = Jinja2Templates(directory="app/templates")


# ------------------------------------------------------------
# Markdown 첫 줄에서 제목 추출
# ------------------------------------------------------------
def extract_title_from_markdown(content: str) -> str:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return "Untitled"
    title = lines[0]
    if title.startswith("#"):
        title = title.lstrip("#").strip()
    return title[:200] if title else "Untitled"


# ------------------------------------------------------------
# normal 기본 카테고리 자동 생성
# ------------------------------------------------------------
def ensure_default_category(db: Session):
    normal = db.query(models.BoardCategory).filter_by(name="normal").first()
    if not normal:
        normal = models.BoardCategory(
            name="normal",
            description="Default category",
        )
        db.add(normal)
        db.commit()
        db.refresh(normal)
    return normal


# ------------------------------------------------------------
# 업로드된 이미지들을 /uploads/<user>/<post_id>/ 로 정리하는 헬퍼
# ------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent  # app/
STATIC_DIR = BASE_DIR / "static"
UPLOAD_ROOT = STATIC_DIR / "uploads"

# /static/uploads/<user>/<something> 패턴
IMG_URL_RE = re.compile(r"/static/uploads/(\d+)/([^)\s\"']+)")


def _build_image_mapping(text: str, user_id: int, post_id: int):
    """
    text 안에서 /static/uploads/<user>/<filename> 형태만 골라
    /static/uploads/<user>/<post_id>/<filename> 으로 바꿔야 할 매핑을 만든다.
    이미 /<user>/<post_id>/ 로 되어 있는 경우는 건드리지 않는다.
    """
    mapping = {}
    if not text:
        return mapping

    for m in IMG_URL_RE.finditer(text):
        uid = int(m.group(1))
        rest = m.group(2)  # 예: "abc.png" 또는 "5/abc.png"

        if uid != user_id:
            continue

        # 이미 /<user>/<post_id>/... 형태이면 스킵
        if re.match(r"^\d+/", rest):
            continue

        old_url = m.group(0)  # "/static/uploads/<user>/<filename>"
        new_url = f"/static/uploads/{user_id}/{post_id}/{rest}"
        mapping[old_url] = new_url

    return mapping


def relocate_images_to_post_folder(post: models.BoardPost) -> None:
    """
    post.content / post.content_html 안에 있는
    /static/uploads/<user>/<filename> 형태의 URL을 찾아서

    1) 실제 파일을 /static/uploads/<user>/<post.id>/<filename> 으로 이동하고
    2) 두 필드의 URL을 모두 새 경로로 치환한다.

    이미 /static/uploads/<user>/<post_id>/... 인 URL은 건드리지 않는다.
    """
    raw_content = post.content or ""
    raw_html = post.content_html or ""

    # content + content_html 전체를 대상으로 매핑 추출
    union_text = raw_content + "\n" + raw_html
    mapping = _build_image_mapping(union_text, post.user_id, post.id)
    if not mapping:
        return

    # 1) 실제 파일 이동
    for old_url, new_url in mapping.items():
        # old_url: /static/uploads/<user>/<filename>
        # -> 파일 경로는 UPLOAD_ROOT/<user>/<filename>
        without_prefix = old_url[len("/static/uploads/") :]
        parts = without_prefix.split("/")
        user_id_str = parts[0]
        filename = "/".join(parts[1:])

        src = UPLOAD_ROOT / user_id_str / filename
        if src.exists():
            dest_dir = UPLOAD_ROOT / user_id_str / str(post.id)
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / filename.split("/")[-1]
            try:
                src.rename(dest)
            except FileExistsError:
                # 이미 있으면 이동만 생략하고 URL만 갱신
                pass

    # 2) 실제 텍스트의 URL 교체 (파일 존재 여부와 무관하게)
    def _apply(text: str) -> str:
        if not text:
            return text
        # 긴 URL부터 치환
        for old, new in sorted(mapping.items(), key=lambda kv: len(kv[0]), reverse=True):
            text = text.replace(old, new)
        return text

    post.content = _apply(raw_content)
    post.content_html = _apply(raw_html)


# ------------------------------------------------------------
# 마크다운의 {height="..."} 정보를 content_html <img> 태그에 반영
# ------------------------------------------------------------
IMG_SIZE_MARK_RE = re.compile(
    r'!\[[^\]]*\]\(([^)]+)\)\s*\{height="([^"]+)"\}'
)
IMG_TAG_RE = re.compile(r'(<img\b[^>]*src=")([^"]+)("([^>]*>))')


def apply_image_heights_from_markdown(post: models.BoardPost) -> None:
    """
    post.content 안에 들어있는
      ![alt](url){height="200"}
      ![alt](url){height="200px"}
    형태의 정보를 읽어서,
    post.content_html 의 <img src="url"> 태그에
      style="height:200px;" data-height="200"
    를 주입한다.
    """

    markdown = post.content or ""
    html = post.content_html or ""
    if not markdown or not html:
        return

    # 1) 마크다운에서 url -> height 매핑 수집
    sizes: dict[str, str] = {}
    for m in IMG_SIZE_MARK_RE.finditer(markdown):
        url = m.group(1).strip()
        h = m.group(2).strip()
        if not url or not h:
            continue
        sizes[url] = h

    if not sizes:
        return

    # 2) HTML 의 <img src="url"> 태그에 스타일 주입
    def repl(match: re.Match) -> str:
        prefix, url, suffix = match.groups()
        url = url.strip()
        raw_h = sizes.get(url)
        if not raw_h:
            return match.group(0)

        # ✨ 숫자만 있으면 px 단위를 붙여준다 (예: "240" -> "240px")
        if re.fullmatch(r"\d+(\.\d+)?", raw_h):
            css_height = f"{raw_h}px"
        else:
            css_height = raw_h

        tag = prefix + url + suffix  # 원래 <img ...> 태그 전체

        # style 속성 추가/보강
        if 'style="' in tag:
            tag = tag.replace('style="', f'style="height:{css_height}; ')
        else:
            tag = tag[:-1] + f' style="height:{css_height};">'

        # data-height 없으면 추가 (원래 숫자 값 그대로)
        if 'data-height="' not in tag:
            tag = tag[:-1] + f' data-height="{raw_h}">'

        return tag

    post.content_html = IMG_TAG_RE.sub(repl, html)


# ============================================================
# 카테고리 목록 / 생성
# ============================================================
@router.get("/categories", response_class=HTMLResponse)
def category_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ensure_default_category(db)

    categories = (
        db.query(models.BoardCategory)
        .order_by(models.BoardCategory.created_at.asc())
        .all()
    )

    return templates.TemplateResponse(
        "board_categories.html",
        {
            "request": request,
            "categories": categories,
            "current_user": current_user,
            "error": None,
        },
    )


@router.post("/categories", response_class=HTMLResponse)
def category_create(
    request: Request,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ensure_default_category(db)
    name = name.strip()

    if not name:
        error = "Category name is required."
    else:
        exists = (
            db.query(models.BoardCategory)
            .filter(models.BoardCategory.name == name)
            .first()
        )
        if exists:
            error = "Category already exists."
        else:
            category = models.BoardCategory(
                name=name,
                description=description or None,
            )
            db.add(category)
            db.commit()
            return RedirectResponse("/board/categories", status_code=303)

    categories = (
        db.query(models.BoardCategory)
        .order_by(models.BoardCategory.created_at.asc())
        .all()
    )
    return templates.TemplateResponse(
        "board_categories.html",
        {
            "request": request,
            "categories": categories,
            "current_user": current_user,
            "error": error,
        },
    )


# ============================================================
# 새 글 작성 (/board/new)
# ============================================================
@router.get("/new", response_class=HTMLResponse)
def board_new(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    normal = ensure_default_category(db)

    categories = (
        db.query(models.BoardCategory)
        .order_by(models.BoardCategory.created_at.asc())
        .all()
    )

    return templates.TemplateResponse(
        "board_new.html",
        {
            "request": request,
            "categories": categories,
            "normal_category_id": normal.id,
            "current_user": current_user,
        },
    )


@router.post("/new", response_class=HTMLResponse)
def board_create(
    request: Request,
    content: str = Form(...),
    content_html: Optional[str] = Form(None),
    is_private: Optional[bool] = Form(False),
    category_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    normal = ensure_default_category(db)

    # 선택 안 했거나, 0/빈값이면 normal로 강제
    category_id_int = int(category_id) if category_id not in (None, "", "0") else normal.id

    category = (
        db.query(models.BoardCategory)
        .filter(models.BoardCategory.id == category_id_int)
        .first()
    )
    if not category:
        raise HTTPException(400, "Invalid category")

    title = extract_title_from_markdown(content)

    post = models.BoardPost(
        title=title,
        content=content,
        content_html=content_html,
        author=current_user.email,
        is_private=is_private,
        user_id=current_user.id,
        category_id=category_id_int,
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    # 1) 이미지 파일을 /uploads/<user>/<file> -> /uploads/<user>/<post_id>/<file> 로 정리
    relocate_images_to_post_folder(post)
    # 2) 마크다운의 {height="..."} 정보를 HTML에 반영 (리사이즈 유지)
    apply_image_heights_from_markdown(post)
    db.commit()

    return RedirectResponse(f"/board/{post.id}", status_code=303)


# ============================================================
# 글 수정 (/board/{post_id}/edit)
# ============================================================
@router.get("/{post_id}/edit", response_class=HTMLResponse)
def board_edit(
    post_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    normal = ensure_default_category(db)

    post = (
        db.query(models.BoardPost)
        .filter(models.BoardPost.id == post_id)
        .first()
    )
    if not post:
        raise HTTPException(404, "Post not found")

    if post.user_id != current_user.id:
        raise HTTPException(403, "Not authorized")

    categories = (
        db.query(models.BoardCategory)
        .order_by(models.BoardCategory.created_at.asc())
        .all()
    )

    return templates.TemplateResponse(
        "board_edit.html",
        {
            "request": request,
            "post": post,
            "categories": categories,
            "normal_category_id": normal.id,
            "current_user": current_user,
        },
    )


@router.post("/{post_id}/edit", response_class=HTMLResponse)
def board_update(
    post_id: int,
    request: Request,
    content: str = Form(...),
    content_html: Optional[str] = Form(None),
    is_private: Optional[bool] = Form(False),
    category_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    normal = ensure_default_category(db)

    post = (
        db.query(models.BoardPost)
        .filter(models.BoardPost.id == post_id)
        .first()
    )
    if not post:
        raise HTTPException(404, "Post not found")

    if post.user_id != current_user.id:
        raise HTTPException(403, "Not authorized")

    category_id_int = int(category_id) if category_id not in (None, "", "0") else normal.id

    post.title = extract_title_from_markdown(content)
    post.content = content
    post.content_html = content_html
    post.is_private = is_private
    post.category_id = category_id_int

    relocate_images_to_post_folder(post)
    apply_image_heights_from_markdown(post)
    db.commit()

    return RedirectResponse(f"/board/{post.id}", status_code=303)


# ============================================================
# 게시글 목록 (/board/)
# ============================================================
@router.get("/", response_class=HTMLResponse)
def board_list(
    request: Request,
    category_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user_optional),
):
    ensure_default_category(db)

    categories = (
        db.query(models.BoardCategory)
        .order_by(models.BoardCategory.created_at.asc())
        .all()
    )

    q = db.query(models.BoardPost)

    if category_id:
        q = q.filter(models.BoardPost.category_id == category_id)

    if current_user is None:
        q = q.filter(models.BoardPost.is_private == False)
    else:
        q = q.filter(
            or_(
                models.BoardPost.is_private == False,
                models.BoardPost.user_id == current_user.id,
            )
        )

    posts = q.order_by(models.BoardPost.created_at.desc()).all()

    return templates.TemplateResponse(
        "board_list.html",
        {
            "request": request,
            "posts": posts,
            "categories": categories,
            "selected_category_id": category_id,
            "current_user": current_user,
        },
    )


# ============================================================
# 게시글 상세 (/board/{post_id})  ← 항상 맨 마지막
# ============================================================
@router.get("/{post_id}", response_class=HTMLResponse)
def board_detail(post_id: int, request: Request,
                 db: Session = Depends(get_db),
                 current_user: Optional[models.User] = Depends(get_current_user_optional)):

    ensure_default_category(db)

    post = db.query(models.BoardPost).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(404, "Post not found")

    if post.is_private and (not current_user or post.user_id != current_user.id):
        raise HTTPException(403, "Not authorized")

    return templates.TemplateResponse(
        "board_detail.html",
        {"request": request, "post": post, "current_user": current_user},
    )
