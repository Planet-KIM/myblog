from typing import Optional
import re
from uuid import uuid4
from pathlib import Path
from datetime import datetime
from urllib.parse import quote

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
from app.routers.upload.router import relocate_draft_files, normalize_draft_id
from app.services.sanitize import sanitize_html, sanitize_content_blocks
from app.services.ratelimit import enforce
from app.services.seo import post_jsonld, breadcrumb_jsonld, post_meta
from app.services.recommendations import get_related_posts
from app.config import settings
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
# Milkdown 최상단 1줄 제목 추출
# ------------------------------------------------------------
def extract_title_from_milkdown_top_line(
    content_html: Optional[str],
    content: Optional[str] = None,
) -> str:
    """Milkdown 콘텐츠에서 최상단 유효 1줄만 제목으로 추출."""
    import html as html_module

    source = (content_html or content or "").strip()
    if not source:
        return "Untitled"

    # 1) entity decode
    text = html_module.unescape(source)

    # 2) 코드/스타일 블록 제거 (제목 후보에서 제외)
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "\n", text)
    text = re.sub(r"(?is)<pre[^>]*>.*?</pre>", "\n", text)
    text = re.sub(r"(?is)<code[^>]*>.*?</code>", "\n", text)

    # 3) 줄 경계 보존
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(
        r"(?i)</(h[1-6]|p|div|li|blockquote|section|article|header|footer|tr|td|th)>",
        "\n",
        text,
    )
    text = re.sub(
        r"(?i)<(h[1-6]|p|div|li|blockquote|section|article|header|footer|tr|td|th)[^>]*>",
        "",
        text,
    )

    # 4) 나머지 태그 제거
    text = re.sub(r"(?is)<[^>]+>", "", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    boilerplate_phrases = (
        "여기에 내용을 작성하세요.",
        "type here...",
        "print(\"hello world\")",
        "print('hello world')",
    )

    in_code_fence = False
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        if re.match(r"^```", line):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue

        if line.startswith("#"):
            line = line.lstrip("#").strip()
        if not line:
            continue

        if re.match(r"^!\[[^\]]*\]\([^)]+\)", line):
            continue

        lower_line = line.lower()
        if any(phrase in lower_line for phrase in boilerplate_phrases):
            continue

        # 저장 중 섞인 태그 잔재 문자열 방어
        if "data-text-color" in lower_line or "<span" in lower_line or "</span" in lower_line:
            continue

        cleaned = re.sub(r"\s+", " ", line).strip()
        if cleaned:
            return cleaned[:200]

    return "Untitled"


# ------------------------------------------------------------
# Markdown to plain text preview (마크다운 기호 제거)
# ------------------------------------------------------------
def create_preview(
    content_html: Optional[str],
    content: Optional[str] = None,
    max_length: int = 200,
) -> str:
    """HTML/Markdown 혼합 본문에서 카드용 순수 텍스트 미리보기 생성."""
    import html as html_module

    source = (content_html or content or "").strip()
    if not source:
        return "No preview available..."

    text = html_module.unescape(source)

    # 코드/스크립트/스타일 블록 제거
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "\n", text)
    text = re.sub(r"(?is)<pre[^>]*>.*?</pre>", "\n", text)
    text = re.sub(r"(?is)<code[^>]*>.*?</code>", "\n", text)
    text = re.sub(r"```[\s\S]*?```", "\n", text)

    # 블록 경계 보존
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(h[1-6]|p|div|li|blockquote|section|article|header|footer|tr|td|th)>", "\n", text)
    text = re.sub(r"(?i)<(h[1-6]|p|div|li|blockquote|section|article|header|footer|tr|td|th)[^>]*>", "", text)

    # 잔여 태그 제거 및 공백 정리
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return "No preview available..."

    if len(text) > max_length:
        text = text[:max_length].rsplit(" ", 1)[0] + "..."

    return text


# ------------------------------------------------------------
# normal 기본 카테고리 자동 생성
# ------------------------------------------------------------
def ensure_default_category(db: Session, user: models.User):
    """사용자(블로그 소유자)별 기본 '일반' 카테고리를 보장한다."""
    normal = (
        db.query(models.BoardCategory)
        .filter_by(name="일반", user_id=user.id)
        .first()
    )
    if not normal:
        normal = models.BoardCategory(
            name="일반",
            description="기본 카테고리 (자동 생성)",
            parent_id=None,   # 최상위
            user_id=user.id,
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
    ensure_default_category(db, current_user)

    categories = (
        db.query(models.BoardCategory)
        .filter(models.BoardCategory.user_id == current_user.id)
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
        request,
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

    ensure_default_category(db, current_user)

    name = name.strip()
    error: Optional[str] = None

    # ─────────────────────────────────────────
    # 1) 기본 검증: 이름 필수
    # ─────────────────────────────────────────
    if not name:
        error = "Category name is required."

    # ─────────────────────────────────────────
    # 2) 중복 이름 체크 (본인 블로그 범위 내에서만)
    # ─────────────────────────────────────────
    if not error:
        exists = (
            db.query(models.BoardCategory)
            .filter(
                models.BoardCategory.name == name,
                models.BoardCategory.user_id == current_user.id,
            )
            .first()
        )
        if exists:
            error = "Category already exists."

    # ─────────────────────────────────────────
    # 3) parent_id 해석 (빈 문자열이면 최상위, 본인 소유만 허용)
    # ─────────────────────────────────────────
    parent = None
    if not error:
        if parent_id not in (None, ""):
            try:
                parent_id = int(parent_id)
            except ValueError:
                error = "Invalid parent category."
            else:
                parent = (
                    db.query(models.BoardCategory)
                    .filter(
                        models.BoardCategory.id == parent_id,
                        models.BoardCategory.user_id == current_user.id,
                    )
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
            .filter(models.BoardCategory.user_id == current_user.id)
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
            request,
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
    # 5) 실제 카테고리 생성 (소유자 + parent_id 반영)
    # ─────────────────────────────────────────
    category = models.BoardCategory(
        name=name,
        description=description or None,
        parent_id=parent.id if parent else None,
        user_id=current_user.id,
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
    category = db.query(models.BoardCategory).filter(
        models.BoardCategory.id == req.category_id,
        models.BoardCategory.user_id == current_user.id,
    ).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Prevent circular dependency (e.g. moving parent into its own child)
    if req.new_parent_id == req.category_id:
        raise HTTPException(status_code=400, detail="Cannot move category into itself")

    if req.new_parent_id:
        # 새 부모도 반드시 본인 소유여야 함
        current_parent = db.query(models.BoardCategory).filter(
            models.BoardCategory.id == req.new_parent_id,
            models.BoardCategory.user_id == current_user.id,
        ).first()
        if not current_parent:
            raise HTTPException(status_code=404, detail="Parent category not found")
        while current_parent:
            if current_parent.id == req.category_id:
                raise HTTPException(status_code=400, detail="Cannot move a category into its own descendant")
            if current_parent.parent_id:
                current_parent = db.query(models.BoardCategory).filter(
                    models.BoardCategory.id == current_parent.parent_id,
                    models.BoardCategory.user_id == current_user.id,
                ).first()
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
        models.BoardCategory.id == category_id,
        models.BoardCategory.user_id == current_user.id,
    ).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    if category.name in ("일반", "normal"):
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
            models.BoardCategory.id == reassign_id,
            models.BoardCategory.user_id == current_user.id,
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
        models.BoardCategory.id == category_id,
        models.BoardCategory.user_id == current_user.id,
    ).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    existing = db.query(models.BoardCategory).filter(
        models.BoardCategory.name == name,
        models.BoardCategory.user_id == current_user.id,
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
            request,
            "board_select_editor.html",
            {"request": request, "current_user": current_user},
        )

    normal = ensure_default_category(db, current_user)

    categories = (
        db.query(models.BoardCategory)
        .filter(models.BoardCategory.user_id == current_user.id)
        .order_by(models.BoardCategory.created_at.asc())
        .all()
    )

    template_name = "board_new_tiptap.html" if editor == "tiptap" else "board_new_clean.html"
    popular_tags = (
        db.query(models.Tag)
        .filter(models.Tag.count > 0)
        .order_by(models.Tag.count.desc(), models.Tag.name.asc())
        .limit(12)
        .all()
    )

    return templates.TemplateResponse(
        request,
        template_name,
        {
            "request": request,
            "categories": categories,
            "normal_category_id": normal.id,
            "current_user": current_user,
            "draft_id": str(uuid4()),
            "tags_value": "",
            "popular_tags": popular_tags,
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
    # draft_id는 DB 기록 전에 검증 (잘못된 값이면 글 생성 전 400)
    draft_id = normalize_draft_id(draft_id)

    normal = ensure_default_category(db, current_user)

    # 카테고리 선택 없으면 normal 에 저장
    try:
        category_id_int = int(category_id) if category_id not in (None, "", "0") else normal.id
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid category ID format")

    # 유효성 검사: 반드시 본인 소유 카테고리여야 함
    category = (
        db.query(models.BoardCategory)
        .filter(
            models.BoardCategory.id == category_id_int,
            models.BoardCategory.user_id == current_user.id,
        )
        .first()
    )
    if not category:
        raise HTTPException(400, "Invalid category")

    # 에디터 타입별 제목 추출 분기
    if editor_type == "tiptap":
        title = extract_title_from_html(content_html or content)
    elif editor_type == "milkdown":
        title = extract_title_from_milkdown_top_line(content_html, content)
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
    normal = ensure_default_category(db, current_user)

    post = db.query(models.BoardPost).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(404, "Post not found")

    if post.user_id != current_user.id:
        raise HTTPException(403, "Not authorized")

    categories = (
        db.query(models.BoardCategory)
        .filter(models.BoardCategory.user_id == current_user.id)
        .order_by(models.BoardCategory.created_at.asc())
        .all()
    )

    template_name = "board_edit_tiptap.html" if post.editor_type == "tiptap" else "board_edit.html"

    # XSS 방어: 에디터에 주입되는 content_blocks도 정제 (스크립트 태그 탈출 방지)
    post.content_blocks_safe = sanitize_content_blocks(post.content_blocks)

    popular_tags = (
        db.query(models.Tag)
        .filter(models.Tag.count > 0)
        .order_by(models.Tag.count.desc(), models.Tag.name.asc())
        .limit(12)
        .all()
    )

    return templates.TemplateResponse(
        request,
        template_name,
        {
            "request": request,
            "post": post,
            "categories": categories,
            "normal_category_id": normal.id,
            "current_user": current_user,
            "tags_value": ", ".join(t.name for t in post.tags),
            "popular_tags": popular_tags,
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
    tags: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    draft_id = normalize_draft_id(draft_id)

    normal = ensure_default_category(db, current_user)

    post = db.query(models.BoardPost).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(404, "Post not found")

    if post.user_id != current_user.id:
        raise HTTPException(403, "Not authorized")

    try:
        category_id_int = int(category_id) if category_id not in (None, "", "0") else normal.id
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid category ID format")

    # 선택 카테고리는 반드시 본인 소유여야 함 (아니면 기본 카테고리로)
    owned = db.query(models.BoardCategory).filter(
        models.BoardCategory.id == category_id_int,
        models.BoardCategory.user_id == current_user.id,
    ).first()
    if not owned:
        category_id_int = normal.id

    # 에디터 타입에 따라 제목 추출 분기
    effective_editor_type = editor_type or post.editor_type or "milkdown"
    if effective_editor_type == "tiptap":
        post.title = extract_title_from_html(content_html or content)
    elif effective_editor_type == "milkdown":
        post.title = extract_title_from_milkdown_top_line(content_html, content)
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

    # 태그 갱신 (제출된 경우에만; 빈 문자열이면 전체 해제)
    if tags is not None:
        from ..api import process_post_tags
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        process_post_tags(db, post, tag_list)

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
    category_id: Optional[str] = None,
    q: Optional[str] = None,
    scope: str = "all",
    sort: str = "recent",
    page: int = 1,
    size: int = 10,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user_optional),
):
    # 페이지네이션 파라미터 방어 (size=0 시 ZeroDivision 방지, 과대 size 제한)
    page = max(1, page)
    size = max(1, min(size, 50))

    categories = (
        db.query(models.BoardCategory)
        .order_by(models.BoardCategory.created_at.asc())
        .all()
    )
    ordered_categories, category_depths = order_categories_parent_first(categories)

    selected_category_id: Optional[int] = None
    if category_id not in (None, ""):
        try:
            selected_category_id = int(category_id)
        except (TypeError, ValueError):
            selected_category_id = None

    selected_category_ids: list[int] | None = None
    if selected_category_id is not None:
        selected_category_ids = collect_descendant_category_ids(categories, selected_category_id)

    scope_mode = (scope or "all").strip().lower()
    if scope_mode not in {"all", "saved"}:
        scope_mode = "all"

    if scope_mode == "saved" and not current_user:
        next_path = request.url.path
        if request.url.query:
            next_path = f"{next_path}?{request.url.query}"
        encoded_next = quote(next_path, safe="/")
        return RedirectResponse(f"/auth/login?next={encoded_next}", status_code=303)

    query = db.query(models.BoardPost).options(
        joinedload(models.BoardPost.category),
        joinedload(models.BoardPost.user),
        joinedload(models.BoardPost.stats)
    )

    if scope_mode == "saved" and current_user:
        query = query.join(
            models.PostBookmark,
            models.PostBookmark.post_id == models.BoardPost.id,
        ).filter(models.PostBookmark.user_id == current_user.id)

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
            func.coalesce(models.PostStats.likes, 0).desc(),
            models.PostBookmark.created_at.desc() if scope_mode == "saved" else models.BoardPost.created_at.desc(),
            models.BoardPost.created_at.desc(),
        )
    elif sort_mode == "discussed":
        query = query.outerjoin(models.PostStats, models.PostStats.post_id == models.BoardPost.id).order_by(
            func.coalesce(models.PostStats.likes, 0).desc(),
            func.coalesce(models.PostStats.views, 0).desc(),
            models.PostBookmark.created_at.desc() if scope_mode == "saved" else models.BoardPost.created_at.desc(),
            models.BoardPost.created_at.desc(),
        )
    else:
        sort_mode = "recent"
        if scope_mode == "saved":
            query = query.order_by(models.PostBookmark.created_at.desc(), models.BoardPost.created_at.desc())
        else:
            query = query.order_by(models.BoardPost.created_at.desc())

    posts = query.offset((page - 1) * size).limit(size).all()

    # Add preview to each post
    for post in posts:
        if not hasattr(post, 'preview') or not post.preview:
            post.preview = create_preview(post.content_html, post.content)

    return templates.TemplateResponse(
        request,
        "board_list_writer.html",
        {
            "request": request,
            "posts": posts,
            "categories": ordered_categories,
            "category_depths": category_depths,
            "selected_category_id": selected_category_id,
            "selected_scope": scope_mode,
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
    # 관리자는 숨김 글도 열람 가능 (모더레이션)
    post_q = db.query(models.BoardPost).filter_by(id=post_id)
    if current_user and current_user.is_admin:
        post_q = post_q.execution_options(include_hidden=True)
    post = post_q.first()
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

    # 이전/다음 글: 같은 블로그(작성자) 안에서만, 공개 글 기준
    prev_post = db.query(models.BoardPost).filter(
        models.BoardPost.id < post_id,
        models.BoardPost.user_id == post.user_id,
        models.BoardPost.is_private == False
    ).order_by(models.BoardPost.id.desc()).first()

    next_post = db.query(models.BoardPost).filter(
        models.BoardPost.id > post_id,
        models.BoardPost.user_id == post.user_id,
        models.BoardPost.is_private == False
    ).order_by(models.BoardPost.id.asc()).first()

    # editor_type에 따라 다른 상세 템플릿 사용
    template_name = "board_detail_magazine.html" if post.editor_type == "tiptap" else "board_detail_writer.html"

    # XSS 방어: 출력 직전 본문 정제 (저장값은 그대로, 렌더 시에만 정제)
    post.content_html_safe = sanitize_html(post.content_html)
    post.content_blocks_safe = sanitize_content_blocks(post.content_blocks)

    # 공유/SEO 메타
    meta_description = create_preview(post.content_html, post.content, 160)
    img_match = (
        re.search(r"!\[[^\]]*\]\(([^)\s]+)", post.content or "")
        or re.search(r'<img[^>]+src=["\']([^"\']+)', (post.content_html or post.content or ""), re.I)
    )
    og_image = img_match.group(1) if img_match else ""
    if og_image.startswith("/"):
        og_image = str(request.base_url).rstrip("/") + og_image

    # 댓글 목록 (작성 시간순)
    comments = (
        db.query(models.Comment)
        .filter(models.Comment.post_id == post_id)
        .options(joinedload(models.Comment.user))
        .order_by(models.Comment.created_at.asc())
        .all()
    )

    # 작성자 카드용: 같은 블로그의 다른 공개 글 (최신 3)
    author_other_posts = (
        db.query(models.BoardPost)
        .filter(
            models.BoardPost.user_id == post.user_id,
            models.BoardPost.id != post.id,
            models.BoardPost.is_private == False,  # noqa: E712
        )
        .order_by(models.BoardPost.created_at.desc())
        .limit(3)
        .all()
    )

    # 태그를 공유하는 다른 공개 글 (블로그 경계 없이) — 토픽 기반 탐색
    related_posts = get_related_posts(db, post, limit=4)

    # 시리즈(series:<이름> 태그) 감지
    series_label = series_slug = None
    for _t in (post.tags or []):
        if (_t.name or "").lower().startswith("series:"):
            series_label = _t.name.split(":", 1)[1].strip()
            series_slug = series_label.lower()
            break

    return templates.TemplateResponse(
        request,
        template_name,
        {
            "request": request,
            "post": post,
            "current_user": current_user,
            "stats": stats,
            "prev_post": prev_post,
            "next_post": next_post,
            "comments": comments,
            "author_other_posts": author_other_posts,
            "related_posts": related_posts,
            "series_label": series_label,
            "series_slug": series_slug,
            "meta_description": meta_description,
            "og_title": post.title,
            "og_image": og_image,
            "og_type": "article",
            "jsonld": [
                post_jsonld(request, post, meta_description, og_image),
                breadcrumb_jsonld(request, post),
            ],
            **post_meta(request, post),
        },
    )


# ============================================================
# ★ 댓글 작성 / 삭제 (평문, 서버 렌더 폼)
# ============================================================
@router.post("/{post_id}/comment")
def board_comment_create(
    post_id: int,
    request: Request,
    body: str = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    enforce(request, "comment", settings.COMMENT_RATE_LIMIT, settings.COMMENT_RATE_WINDOW,
            subject=str(current_user.id),
            message="댓글을 너무 자주 작성하고 있습니다. 잠시 후 다시 시도해주세요.")
    post = db.query(models.BoardPost).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(404, "Post not found")
    # 비공개 글은 작성자만 열람/댓글 가능
    if post.is_private and post.user_id != current_user.id:
        raise HTTPException(403, "비공개 게시글입니다.")

    text = (body or "").strip()[:2000]
    if text:
        comment = models.Comment(post_id=post.id, user_id=current_user.id, body=text)
        db.add(comment)
        db.flush()
        from app.services.notifications import notify
        notify(db, recipient_id=post.user_id, actor_id=current_user.id,
               type="comment", post_id=post.id, comment_id=comment.id)
        db.commit()
    return RedirectResponse(f"/board/{post_id}#comments", status_code=303)


@router.post("/{post_id}/comment/{comment_id}/delete")
def board_comment_delete(
    post_id: int,
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    comment = (
        db.query(models.Comment)
        .filter(models.Comment.id == comment_id, models.Comment.post_id == post_id)
        .first()
    )
    if not comment:
        raise HTTPException(404, "Comment not found")
    post = db.query(models.BoardPost).filter_by(id=post_id).first()
    # 삭제 권한: 댓글 작성자 / 글 작성자 / 관리자
    if not (
        comment.user_id == current_user.id
        or (post and post.user_id == current_user.id)
        or current_user.is_admin
    ):
        raise HTTPException(403, "삭제 권한이 없습니다.")
    db.delete(comment)
    db.commit()
    return RedirectResponse(f"/board/{post_id}#comments", status_code=303)


# ============================================================
# ★ 매거진 레이아웃 템플릿 (저장 / 재사용)
# ============================================================
@router.post("/{post_id}/save-template")
def board_save_template(
    post_id: int,
    request: Request,
    name: str = Form(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    post = db.query(models.BoardPost).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(404, "Post not found")
    if post.user_id != current_user.id:
        raise HTTPException(403, "Not authorized")
    if not post.content_blocks:
        raise HTTPException(400, "저장할 레이아웃이 없습니다 (매거진 글만 가능).")
    tpl = models.LayoutTemplate(
        user_id=current_user.id,
        name=(name or "").strip()[:100] or (post.title or "내 레이아웃")[:100],
        content_blocks=post.content_blocks,
    )
    db.add(tpl)
    db.commit()
    return RedirectResponse(f"/board/{post_id}?saved_template=1", status_code=303)


@router.post("/from-template/{template_id}")
def board_from_template(
    template_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    tpl = db.query(models.LayoutTemplate).filter_by(id=template_id, user_id=current_user.id).first()
    if not tpl:
        raise HTTPException(404, "템플릿을 찾을 수 없습니다.")
    return _create_draft_from_blocks(db, current_user, tpl.content_blocks)


@router.post("/from-starter/{key}")
def board_from_starter(
    key: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from app.services.starter_templates import get_starter_blocks
    blocks = get_starter_blocks(key)
    if not blocks:
        raise HTTPException(404, "시작 템플릿을 찾을 수 없습니다.")
    return _create_draft_from_blocks(db, current_user, blocks)


def _create_draft_from_blocks(db, current_user, content_blocks):
    normal = ensure_default_category(db, current_user)
    post = models.BoardPost(
        title="(제목 없는 매거진)",
        content="",
        content_html="",
        content_blocks=content_blocks,
        editor_type="tiptap",
        is_private=True,   # 초안: 발행 전까지 비공개
        show_title=True,
        user_id=current_user.id,
        author=current_user.email,
        category_id=normal.id,
    )
    db.add(post)
    db.commit()
    return RedirectResponse(f"/board/{post.id}/edit", status_code=303)


# ============================================================
# ★ 신고 (모더레이션 입력)
# ============================================================
def _create_report(db, request, current_user, target_type, target_id, reason):
    enforce(request, "report", 20, 3600, subject=str(current_user.id),
            message="신고가 너무 많습니다. 잠시 후 다시 시도해주세요.")
    db.add(models.Report(
        reporter_user_id=current_user.id,
        target_type=target_type,
        target_id=target_id,
        reason=(reason or "").strip()[:500] or None,
    ))
    db.commit()


@router.post("/{post_id}/report")
def board_report_post(
    post_id: int,
    request: Request,
    reason: str = Form(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _create_report(db, request, current_user, "post", post_id, reason)
    return RedirectResponse(f"/board/{post_id}", status_code=303)


@router.post("/{post_id}/comment/{comment_id}/report")
def board_report_comment(
    post_id: int,
    comment_id: int,
    request: Request,
    reason: str = Form(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _create_report(db, request, current_user, "comment", comment_id, reason)
    return RedirectResponse(f"/board/{post_id}#comments", status_code=303)
