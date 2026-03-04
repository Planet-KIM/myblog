from typing import Optional

from fastapi import (
    APIRouter, Depends, Form, HTTPException, Request
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app import models
from app.auth_utils import get_current_user, get_current_user_optional

router = APIRouter(prefix="/board", tags=["board"])

templates = Jinja2Templates(directory="app/templates")


# ------------------------------------------------------------
# Markdown 첫 줄 제목 추출
# ------------------------------------------------------------
def extract_title_from_markdown(content: str) -> str:
    import re
    # Remove image tags ![...](...) and link tags [...](...) to extract pure text
    lines = content.splitlines()
    for line in lines:
        # Remove images
        clean_line = re.sub(r'!\[.*?\]\(.*?\)', '', line)
        # Remove links, keeping the link text
        clean_line = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', clean_line)
        clean_line = clean_line.strip()
        
        if clean_line:
            if clean_line.startswith("#"):
                clean_line = clean_line.lstrip("#").strip()
            return clean_line[:200] if clean_line else "Untitled"
            
    return "Untitled"


# ------------------------------------------------------------
# normal 기본 카테고리 자동 생성
# ------------------------------------------------------------
def ensure_default_category(db: Session):
    normal = db.query(models.BoardCategory).filter_by(name="normal").first()
    if not normal:
        normal = models.BoardCategory(
            name="normal",
            description="Default category (auto created)",
            parent_id=None,   # 최상위
        )
        db.add(normal)
        db.commit()
        db.refresh(normal)
    return normal


# ============================================================
# ★ 카테고리 페이지 (항상 최상단)
# ============================================================
@router.get("/categories", response_class=HTMLResponse)
def category_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ensure_default_category(db)

    # parent, children 관계를 사용하기 위해 전부 로드
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
    parent_id: Optional[str] = Form(None),  # ★ 폼에서 넘어오는 parent_id (문자열)
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):

    ensure_default_category(db)

    name = name.strip()
    error: Optional[str] = None

    # ─────────────────────────────────────────
    # 1) 기본 검증: 이름 필수
    # ─────────────────────────────────────────
    if not name:
        error = "Category name is required."

    # ─────────────────────────────────────────
    # 2) 중복 이름 체크
    # ─────────────────────────────────────────
    if not error:
        exists = (
            db.query(models.BoardCategory)
            .filter(models.BoardCategory.name == name)
            .first()
        )
        if exists:
            error = "Category already exists."

    # ─────────────────────────────────────────
    # 3) parent_id 해석 (빈 문자열이면 최상위)
    # ─────────────────────────────────────────
    parent = None
    print(parent_id)
    if not error:
        if parent_id not in (None, ""):
            try:
                parent_id = int(parent_id)
                print(parent_id)
            except ValueError:
                error = "Invalid parent category."
            else:
                parent = (
                    db.query(models.BoardCategory)
                    .filter(models.BoardCategory.id == parent_id)
                    .first()
                )
                if not parent:
                    error = "Parent category not found."

    # ─────────────────────────────────────────
    # 4) 에러 있으면 다시 리스트 렌더
    # ─────────────────────────────────────────
    if error:
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

    # ─────────────────────────────────────────
    # 5) 실제 카테고리 생성 (parent_id 반영!)
    # ─────────────────────────────────────────
    category = models.BoardCategory(
        name=name,
        description=description or None,
        parent_id=parent.id if parent else None,  # ★ 핵심
    )
    db.add(category)
    db.commit()

    return RedirectResponse("/board/categories", status_code=303)


# ============================================================
# ★ 카테고리 이동 (Drag & Drop API)
# ============================================================
class CategoryMoveRequest(BaseModel):
    category_id: int
    new_parent_id: Optional[int] = None

@router.post("/categories/move")
def category_move(
    req: CategoryMoveRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    category = db.query(models.BoardCategory).filter(models.BoardCategory.id == req.category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
        
    # Prevent circular dependency (e.g. moving parent into its own child)
    if req.new_parent_id == req.category_id:
        raise HTTPException(status_code=400, detail="Cannot move category into itself")

    if req.new_parent_id:
        current_parent = db.query(models.BoardCategory).filter(models.BoardCategory.id == req.new_parent_id).first()
        while current_parent:
            if current_parent.id == req.category_id:
                raise HTTPException(status_code=400, detail="Cannot move a category into its own descendant")
            if current_parent.parent_id:
                current_parent = db.query(models.BoardCategory).filter(models.BoardCategory.id == current_parent.parent_id).first()
            else:
                break
                
    category.parent_id = req.new_parent_id
    db.commit()
    return {"status": "success"}


# ============================================================
# ★ 새 글 작성 (/new)
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

    # 카테고리 선택 없으면 normal 에 저장
    try:
        category_id_int = int(category_id) if category_id not in (None, "", "0") else normal.id
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid category ID format")

    # 유효성 검사
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
        is_private=is_private,
        author=current_user.email,
        user_id=current_user.id,
        category_id=category_id_int,
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    return RedirectResponse(f"/board/{post.id}", status_code=303)


# ============================================================
# ★ 글 수정
# ============================================================
@router.get("/{post_id}/edit", response_class=HTMLResponse)
def board_edit(
    post_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    normal = ensure_default_category(db)

    post = db.query(models.BoardPost).filter_by(id=post_id).first()
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

    post = db.query(models.BoardPost).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(404, "Post not found")

    if post.user_id != current_user.id:
        raise HTTPException(403, "Not authorized")

    try:
        category_id_int = int(category_id) if category_id not in (None, "", "0") else normal.id
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid category ID format")

    post.title = extract_title_from_markdown(content)
    post.content = content
    post.content_html = content_html
    post.is_private = is_private
    post.category_id = category_id_int

    db.commit()
    return RedirectResponse(f"/board/{post_id}", status_code=303)


# ============================================================
# ★ 게시글 목록
# ============================================================
@router.get("/", response_class=HTMLResponse)
def board_list(
    request: Request,
    category_id: Optional[int] = None,
    page: int = 1,
    size: int = 10,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user_optional),
):
    ensure_default_category(db)

    categories = (
        db.query(models.BoardCategory)
        .order_by(models.BoardCategory.created_at.asc())
        .all()
    )

    q = db.query(models.BoardPost).options(
        joinedload(models.BoardPost.category),
        joinedload(models.BoardPost.user)
    )

    if category_id:
        q = q.filter(models.BoardPost.category_id == category_id)

    # 로그인 안 했으면 Public만
    if not current_user:
        q = q.filter(models.BoardPost.is_private == False)
    else:
        q = q.filter(
            or_(
                models.BoardPost.is_private == False,
                models.BoardPost.user_id == current_user.id,
            )
        )

    # Pagination logic
    total_posts = q.count()
    total_pages = (total_posts + size - 1) // size if total_posts > 0 else 1
    page = max(1, min(page, total_pages))
    
    posts = q.order_by(models.BoardPost.created_at.desc()).offset((page - 1) * size).limit(size).all()

    return templates.TemplateResponse(
        "board_list.html",
        {
            "request": request,
            "posts": posts,
            "categories": categories,
            "selected_category_id": category_id,
            "current_user": current_user,
            "page": page,
            "total_pages": total_pages,
            "size": size,
        },
    )


# ============================================================
# ★ 게시글 상세페이지 (맨 마지막!)
# ============================================================
@router.get("/{post_id}", response_class=HTMLResponse)
def board_detail(
    post_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user_optional),
):
    ensure_default_category(db)

    post = db.query(models.BoardPost).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(404, "Post not found")

    if post.is_private and (not current_user or post.user_id != current_user.id):
        raise HTTPException(403, "Not authorized")

    return templates.TemplateResponse(
        "board_detail.html",
        {
            "request": request,
            "post": post,
            "current_user": current_user,
        },
    )

