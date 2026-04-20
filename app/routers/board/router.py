from typing import Optional
import re
from uuid import uuid4
from pathlib import Path
from datetime import datetime

from fastapi import (
    APIRouter, Depends, Form, HTTPException, Request
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import or_, func
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app import models
from app.auth_utils import get_current_user, get_current_user_optional
from app.routers.upload.router import relocate_draft_files
from app.services.category_counts import (
    collect_descendant_category_ids,
    order_categories_parent_first,
    rollup_category_counts,
)

router = APIRouter(prefix="/board", tags=["board"])

templates = Jinja2Templates(directory="app/templates")


# ------------------------------------------------------------
# Markdown 첫 줄 제목 추출
# ------------------------------------------------------------
def extract_title_from_markdown(content: str) -> str:
    import re
    import markdown
    import html as html_module

    lines = content.splitlines()
    for line in lines:
        line = line.strip()
        # 이미지나 빈 줄 건너뛰기
        if not line or line.startswith("!["):
            continue

        if line.startswith("#"):
            line = line.lstrip("#").strip()

        # Markdown -> HTML -> Plain Text 로 변환하여 **나 __ 처리
        raw_html = markdown.markdown(line)
        plain = re.sub(r'<[^>]+>', '', raw_html)
        plain = html_module.unescape(plain).strip()

        if plain:
            return plain[:200]

    return "Untitled"


# ------------------------------------------------------------
# HTML 에서 제목 추출 (TipTap용)
# ------------------------------------------------------------
def extract_title_from_html(html: str) -> str:
    """HTML 콘텐츠에서 첫 번째 heading 또는 텍스트를 제목으로 추출."""
    import html as html_module

    # h1~h3 태그에서 추출 시도
    heading_match = re.search(r'<h[1-3][^>]*>(.*?)</h[1-3]>', html, re.DOTALL)
    if heading_match:
        plain = re.sub(r'<[^>]+>', '', heading_match.group(1))
        plain = html_module.unescape(plain).strip()
        if plain:
            return plain[:200]

    # heading 없으면 첫 번째 <p> 텍스트 사용
    p_match = re.search(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
    if p_match:
        plain = re.sub(r'<[^>]+>', '', p_match.group(1))
        plain = html_module.unescape(plain).strip()
        if plain:
            return plain[:200]

    return "Untitled"


# ------------------------------------------------------------
# Markdown to plain text preview (마크다운 기호 제거)
# ------------------------------------------------------------
def create_preview(content: str, max_length: int = 200) -> str:
    """마크다운에서 일반 텍스트 미리보기 생성"""
    import re

    # 제목 제거 (첫 줄이 제목이면)
    lines = content.splitlines()
    text = content

    if lines and lines[0].startswith('#'):
        text = '\n'.join(lines[1:])

    # 마크다운 기호들 제거
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)  # 이미지
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)  # 링크
    text = re.sub(r'```[\s\S]*?```', '', text)  # 코드 블록
    text = re.sub(r'`([^`]+)`', r'\1', text)  # 인라인 코드
    text = re.sub(r'#+\s', '', text)  # 헤딩
    text = re.sub(r'[*_]{1,2}([^*_]+)[*_]{1,2}', r'\1', text)  # Bold, italic
    text = re.sub(r'^\s*[-*+]\s', '', text, flags=re.MULTILINE)  # 리스트
    text = re.sub(r'^\s*\d+\.\s', '', text, flags=re.MULTILINE)  # 번호 리스트
    text = re.sub(r'>\s', '', text)  # 인용구

    # 여러 공백을 하나로
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()

    # 길이 제한
    if len(text) > max_length:
        text = text[:max_length].rsplit(' ', 1)[0] + '...'

    return text if text else 'No preview available...'


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
    created: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ensure_default_category(db)

    categories = (
        db.query(models.BoardCategory)
        .order_by(models.BoardCategory.created_at.asc())
        .all()
    )

    count_rows = (
        db.query(models.BoardPost.category_id, func.count(models.BoardPost.id))
        .group_by(models.BoardPost.category_id)
        .all()
    )
    direct_post_count_map = {row[0]: row[1] for row in count_rows}
    post_count_map = rollup_category_counts(categories, direct_post_count_map)

    return templates.TemplateResponse(
        "board_categories.html",
        {
            "request": request,
            "categories": categories,
            "post_count_map": post_count_map,
            "current_user": current_user,
            "error": None,
            "success": "Category created successfully!" if created else None,
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
        count_rows = (
            db.query(models.BoardPost.category_id, func.count(models.BoardPost.id))
            .group_by(models.BoardPost.category_id)
            .all()
        )
        direct_post_count_map = {row[0]: row[1] for row in count_rows}
        post_count_map = rollup_category_counts(categories, direct_post_count_map)

        return templates.TemplateResponse(
            "board_categories.html",
            {
                "request": request,
                "categories": categories,
                "post_count_map": post_count_map,
                "current_user": current_user,
                "error": error,
                "success": None,
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

    return RedirectResponse("/board/categories?created=1", status_code=303)


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
# ★ 카테고리 삭제
# ============================================================
@router.post("/categories/{category_id}/delete")
def category_delete(
    category_id: int,
    reassign_to: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    category = db.query(models.BoardCategory).filter(
        models.BoardCategory.id == category_id
    ).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    if category.name == "normal":
        raise HTTPException(status_code=400, detail="Cannot delete the default category")

    post_count = db.query(models.BoardPost).filter(
        models.BoardPost.category_id == category_id
    ).count()

    if post_count > 0:
        if not reassign_to:
            raise HTTPException(
                status_code=400,
                detail=f"Category has {post_count} post(s). Provide reassign_to.",
            )
        try:
            reassign_id = int(reassign_to)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid reassign_to value")

        target = db.query(models.BoardCategory).filter(
            models.BoardCategory.id == reassign_id
        ).first()
        if not target:
            raise HTTPException(status_code=400, detail="Reassign target not found")
        if target.id == category_id:
            raise HTTPException(status_code=400, detail="Cannot reassign to the same category")

        db.query(models.BoardPost).filter(
            models.BoardPost.category_id == category_id
        ).update({"category_id": reassign_id})

    # 자식 카테고리를 삭제 카테고리의 부모로 re-parent (고아 방지)
    db.query(models.BoardCategory).filter(
        models.BoardCategory.parent_id == category_id
    ).update({"parent_id": category.parent_id})
    db.flush()

    db.delete(category)
    db.commit()
    return {"status": "success", "deleted_id": category_id}


# ============================================================
# ★ 카테고리 이름 변경
# ============================================================
class CategoryRenameRequest(BaseModel):
    name: str


@router.post("/categories/{category_id}/rename")
def category_rename(
    category_id: int,
    req: CategoryRenameRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    if len(name) > 100:
        raise HTTPException(status_code=400, detail="Name too long (max 100 chars)")

    category = db.query(models.BoardCategory).filter(
        models.BoardCategory.id == category_id
    ).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    existing = db.query(models.BoardCategory).filter(
        models.BoardCategory.name == name,
        models.BoardCategory.id != category_id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Category name already exists")

    category.name = name
    db.commit()
    return {"status": "success", "id": category_id, "name": category.name}


# ============================================================
# ★ 이미지 임시 업로드 폴더 이전 로직
# ============================================================
def relocate_draft_images(post: models.BoardPost, draft_id: str, db: Session) -> None:
    """
    새 글 작성 시 임시로 YYYY/MM/draft_<draft_id> 에 저장된 이미지를
    YYYY/MM/<post_id> 로 이동시키고, URL을 업데이트합니다.
    """
    if not post.content:
        return

    # Match: /static/uploads/<user_id>/<YYYY>/<MM>/draft_<draft_id>/<filename>
    # Note: re.escape ensures draft_id is safe just in case.
    pattern = re.compile(rf"/static/uploads/({post.user_id})/(\d{{4}}/\d{{2}})/draft_{re.escape(draft_id)}/([^)\s\"']+)")
    
    mapping = {}
    raw_content = post.content or ""
    raw_html = post.content_html or ""
    union_text = raw_content + "\n" + raw_html
    
    # Path to the uploads directory relative to this file
    UPLOAD_ROOT = Path(__file__).resolve().parent.parent.parent / "static" / "uploads"
    
    for m in pattern.finditer(union_text):
        old_url = m.group(0)
        uid = m.group(1)
        year_month = m.group(2)
        filename = m.group(3)
        
        new_url = f"/static/uploads/{uid}/{year_month}/{post.id}/{filename}"
        mapping[old_url] = new_url
        
        # 파일 이동 처리
        src_path = UPLOAD_ROOT / uid / year_month / f"draft_{draft_id}" / filename
        if src_path.exists():
            dest_dir = UPLOAD_ROOT / uid / year_month / str(post.id)
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path = dest_dir / filename
            try:
                src_path.rename(dest_path)
            except FileExistsError:
                pass
                
    if mapping:
        for old, new in sorted(mapping.items(), key=lambda kv: len(kv[0]), reverse=True):
            raw_content = raw_content.replace(old, new)
            raw_html = raw_html.replace(old, new)
        post.content = raw_content
        post.content_html = raw_html
        db.commit()

    # draft 폴더 삭제 (이동 후 비어있으면 정리)
    import shutil
    for uid in {m.group(1) for m in pattern.finditer(union_text)}:
        for ym in {m.group(2) for m in pattern.finditer(union_text)}:
            draft_dir = UPLOAD_ROOT / uid / ym / f"draft_{draft_id}"
            if draft_dir.exists():
                shutil.rmtree(draft_dir, ignore_errors=True)


# ============================================================
# ★ 새 글 작성 (/new)
# ============================================================
@router.get("/new", response_class=HTMLResponse)
def board_new(
    request: Request,
    editor: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # 에디터 선택 안 했으면 선택 페이지로
    if editor not in ("milkdown", "tiptap"):
        return templates.TemplateResponse(
            "board_select_editor.html",
            {"request": request, "current_user": current_user},
        )

    normal = ensure_default_category(db)

    categories = (
        db.query(models.BoardCategory)
        .order_by(models.BoardCategory.created_at.asc())
        .all()
    )

    template_name = "board_new_tiptap.html" if editor == "tiptap" else "board_new_clean.html"

    return templates.TemplateResponse(
        template_name,
        {
            "request": request,
            "categories": categories,
            "normal_category_id": normal.id,
            "current_user": current_user,
            "draft_id": str(uuid4()),
        },
    )


@router.post("/new", response_class=HTMLResponse)
def board_create(
    request: Request,
    content: str = Form(...),
    content_html: Optional[str] = Form(None),
    is_private: Optional[bool] = Form(False),
    show_title: Optional[bool] = Form(False),
    category_id: Optional[str] = Form(None),
    draft_id: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    editor_type: Optional[str] = Form("milkdown"),
    content_blocks: Optional[str] = Form(None),
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

    # TipTap은 HTML 기반이므로 제목 추출 방식 분기
    if editor_type == "tiptap":
        title = extract_title_from_html(content_html or content)
    else:
        title = extract_title_from_markdown(content)

    post = models.BoardPost(
        title=title,
        content=content,
        content_html=content_html,
        editor_type=editor_type or "milkdown",
        content_blocks=content_blocks,
        is_private=is_private,
        show_title=show_title,
        author=current_user.email,
        user_id=current_user.id,
        category_id=category_id_int,
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    # Process tags if provided
    if tags:
        from ..api import process_post_tags
        tag_list = [t.strip() for t in tags.split(',') if t.strip()]
        process_post_tags(db, post, tag_list)

    # Create initial statistics record
    stats = models.PostStats(post_id=post.id, views=0, likes=0)
    db.add(stats)
    db.commit()

    if draft_id:
        relocate_draft_images(post, draft_id, db)
        relocate_draft_files(post, draft_id, db)

        # Delete draft after successful post creation
        draft = db.query(models.Draft).filter(
            models.Draft.id == draft_id,
            models.Draft.user_id == current_user.id
        ).first()
        if draft:
            db.delete(draft)
            db.commit()

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

    template_name = "board_edit_tiptap.html" if post.editor_type == "tiptap" else "board_edit.html"

    return templates.TemplateResponse(
        template_name,
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
    show_title: Optional[bool] = Form(False),
    category_id: Optional[str] = Form(None),
    draft_id: Optional[str] = Form(None),
    editor_type: Optional[str] = Form(None),
    content_blocks: Optional[str] = Form(None),
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

    # 에디터 타입에 따라 제목 추출 분기
    if editor_type == "tiptap" or post.editor_type == "tiptap":
        post.title = extract_title_from_html(content_html or content)
    else:
        post.title = extract_title_from_markdown(content)

    post.content = content
    post.content_html = content_html
    post.is_private = is_private
    post.show_title = show_title
    post.category_id = category_id_int

    if editor_type:
        post.editor_type = editor_type
    if content_blocks:
        post.content_blocks = content_blocks

    db.commit()

    if draft_id:
        relocate_draft_files(post, draft_id, db)

    return RedirectResponse(f"/board/{post_id}", status_code=303)


# ============================================================
# ★ 게시글 삭제
# ============================================================
@router.post("/{post_id}/delete")
def board_delete(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    import shutil

    post = db.query(models.BoardPost).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(404, "Post not found")

    if post.user_id != current_user.id:
        raise HTTPException(403, "Not authorized")

    # 첨부 파일 DB 레코드 삭제 (디스크는 폴더째 삭제)
    db.query(models.UploadedFile).filter(
        models.UploadedFile.post_id == post_id
    ).delete()

    # 업로드 폴더 전체 삭제
    UPLOAD_ROOT = Path(__file__).resolve().parent.parent.parent / "static" / "uploads"
    post_folder = UPLOAD_ROOT / str(post.user_id) / "posts" / str(post_id)
    if post_folder.exists():
        shutil.rmtree(post_folder, ignore_errors=True)

    db.delete(post)
    db.commit()

    return RedirectResponse("/board/", status_code=303)


# ============================================================
# ★ 게시글 목록
# ============================================================
@router.get("/", response_class=HTMLResponse)
def board_list(
    request: Request,
    category_id: Optional[int] = None,
    q: Optional[str] = None,
    sort: str = "recent",
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
    ordered_categories, category_depths = order_categories_parent_first(categories)

    selected_category_ids: list[int] | None = None
    if category_id:
        selected_category_ids = collect_descendant_category_ids(categories, category_id)

    query = db.query(models.BoardPost).options(
        joinedload(models.BoardPost.category),
        joinedload(models.BoardPost.user),
        joinedload(models.BoardPost.stats)
    )

    if selected_category_ids:
        query = query.filter(models.BoardPost.category_id.in_(selected_category_ids))

    if q:
        query = query.filter(
            or_(
                models.BoardPost.title.ilike(f"%{q}%"),
                models.BoardPost.content.ilike(f"%{q}%"),
                models.BoardPost.content_html.ilike(f"%{q}%"),
                models.BoardPost.author.ilike(f"%{q}%"),
            )
        )

    # 로그인 안 했으면 Public만
    if not current_user:
        query = query.filter(models.BoardPost.is_private == False)
    else:
        query = query.filter(
            or_(
                models.BoardPost.is_private == False,
                models.BoardPost.user_id == current_user.id,
            )
        )

    # Pagination logic
    total_posts = query.count()
    total_pages = (total_posts + size - 1) // size if total_posts > 0 else 1
    page = max(1, min(page, total_pages))
    
    sort_mode = (sort or "recent").strip().lower()
    if sort_mode == "popular":
        query = query.outerjoin(models.PostStats, models.PostStats.post_id == models.BoardPost.id).order_by(
            func.coalesce(models.PostStats.views, 0).desc(),
            models.BoardPost.created_at.desc(),
        )
    elif sort_mode == "discussed":
        query = query.outerjoin(models.PostStats, models.PostStats.post_id == models.BoardPost.id).order_by(
            func.coalesce(models.PostStats.likes, 0).desc(),
            models.BoardPost.created_at.desc(),
        )
    else:
        sort_mode = "recent"
        query = query.order_by(models.BoardPost.created_at.desc())

    posts = query.offset((page - 1) * size).limit(size).all()

    # Add preview to each post
    for post in posts:
        if not hasattr(post, 'preview') or not post.preview:
            post.preview = create_preview(post.content)

    return templates.TemplateResponse(
        "board_list_writer.html",
        {
            "request": request,
            "posts": posts,
            "categories": ordered_categories,
            "category_depths": category_depths,
            "selected_category_id": category_id,
            "search_query": q,
            "selected_sort": sort_mode,
            "current_user": current_user,
            "current_page": page,
            "total_pages": total_pages,
            "size": size,
            "current_time": datetime.now(),
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

    # Increment view count
    stats = db.query(models.PostStats).filter_by(post_id=post_id).first()
    if not stats:
        stats = models.PostStats(post_id=post_id, views=0, likes=0)
        db.add(stats)

    stats.views += 1
    stats.last_viewed_at = datetime.utcnow()
    db.commit()

    # Get previous and next posts
    prev_post = db.query(models.BoardPost).filter(
        models.BoardPost.id < post_id,
        models.BoardPost.is_private == False
    ).order_by(models.BoardPost.id.desc()).first()

    next_post = db.query(models.BoardPost).filter(
        models.BoardPost.id > post_id,
        models.BoardPost.is_private == False
    ).order_by(models.BoardPost.id.asc()).first()

    # editor_type에 따라 다른 상세 템플릿 사용
    template_name = "board_detail_magazine.html" if post.editor_type == "tiptap" else "board_detail_writer.html"

    return templates.TemplateResponse(
        template_name,
        {
            "request": request,
            "post": post,
            "current_user": current_user,
            "stats": stats,
            "prev_post": prev_post,
            "next_post": next_post,
        },
    )
