from typing import Optional, List
from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app import models
from app.auth_utils import get_current_user

_spellcheck_executor = ThreadPoolExecutor(max_workers=1)

router = APIRouter(prefix="/api", tags=["api"])


# ─────────────────────────────
# Request/Response Models
# ─────────────────────────────
class DraftSaveRequest(BaseModel):
    draft_id: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[str] = None
    category_id: Optional[int] = None
    is_private: bool = False


class DraftSaveResponse(BaseModel):
    draft_id: str
    saved_at: datetime
    message: str


class TagResponse(BaseModel):
    id: int
    name: str
    slug: str
    count: int


class StatsUpdateRequest(BaseModel):
    post_id: int
    increment_views: bool = False
    increment_likes: bool = False


# ─────────────────────────────
# Draft Auto-Save Endpoint
# ─────────────────────────────
@router.post("/drafts/save", response_model=DraftSaveResponse)
async def save_draft(
    request: DraftSaveRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """임시 저장 (자동 저장) 엔드포인트"""

    # 기존 draft 찾기 또는 새로 생성
    if request.draft_id:
        draft = db.query(models.Draft).filter(
            models.Draft.id == request.draft_id,
            models.Draft.user_id == current_user.id
        ).first()

        if not draft:
            # Draft ID는 있지만 찾을 수 없는 경우 새로 생성
            draft = models.Draft(
                id=request.draft_id,
                user_id=current_user.id
            )
            db.add(draft)
    else:
        # 새 draft 생성
        draft = models.Draft(
            id=str(uuid4()),
            user_id=current_user.id
        )
        db.add(draft)

    # Draft 내용 업데이트
    if request.title is not None:
        draft.title = request.title
    if request.content is not None:
        draft.content = request.content
    if request.tags is not None:
        draft.tags = request.tags
    if request.category_id is not None:
        draft.category_id = request.category_id
    draft.is_private = request.is_private
    draft.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(draft)

    return DraftSaveResponse(
        draft_id=draft.id,
        saved_at=draft.updated_at,
        message="임시 저장 완료"
    )


# ─────────────────────────────
# Tag Suggestions Endpoint
# ─────────────────────────────
@router.get("/tags/suggest", response_model=List[TagResponse])
async def suggest_tags(
    query: str,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """태그 자동 완성 제안"""

    tags = db.query(models.Tag).filter(
        models.Tag.name.like(f"%{query}%")
    ).order_by(
        models.Tag.count.desc()
    ).limit(limit).all()

    return [
        TagResponse(
            id=tag.id,
            name=tag.name,
            slug=tag.slug,
            count=tag.count
        )
        for tag in tags
    ]


# ─────────────────────────────
# Popular Tags Endpoint
# ─────────────────────────────
@router.get("/tags/popular", response_model=List[TagResponse])
async def get_popular_tags(
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """인기 태그 목록"""

    tags = db.query(models.Tag).order_by(
        models.Tag.count.desc()
    ).limit(limit).all()

    return [
        TagResponse(
            id=tag.id,
            name=tag.name,
            slug=tag.slug,
            count=tag.count
        )
        for tag in tags
    ]


# ─────────────────────────────
# Post Statistics Endpoint
# ─────────────────────────────
@router.post("/stats/update")
async def update_post_stats(
    request: StatsUpdateRequest,
    db: Session = Depends(get_db)
):
    """포스트 통계 업데이트 (조회수, 좋아요 등)"""

    # 포스트 확인
    post = db.query(models.BoardPost).filter(
        models.BoardPost.id == request.post_id
    ).first()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )

    # 통계 레코드 찾기 또는 생성
    stats = db.query(models.PostStats).filter(
        models.PostStats.post_id == request.post_id
    ).first()

    if not stats:
        stats = models.PostStats(post_id=request.post_id)
        db.add(stats)

    # 통계 업데이트
    if request.increment_views:
        stats.views += 1
        stats.last_viewed_at = datetime.utcnow()

    if request.increment_likes:
        stats.likes += 1

    db.commit()

    return {
        "post_id": request.post_id,
        "views": stats.views,
        "likes": stats.likes,
        "message": "Stats updated"
    }


# ─────────────────────────────
# Reading Time Calculation
# ─────────────────────────────
@router.post("/calculate-reading-time")
async def calculate_reading_time(
    content: str
):
    """읽기 시간 계산 (한국어 기준)"""

    # 한국어는 분당 300-400자 읽기 속도
    # 영어는 분당 200-250단어 읽기 속도

    # 간단한 계산: 글자수 / 350
    char_count = len(content.replace(" ", ""))
    reading_time = max(1, round(char_count / 350))

    return {
        "char_count": char_count,
        "reading_time_minutes": reading_time,
        "message": f"약 {reading_time}분 읽기"
    }


# ─────────────────────────────
# Markdown Preview Endpoint
# ─────────────────────────────
@router.post("/markdown/preview")
async def preview_markdown(
    content: str
):
    """마크다운 미리보기 HTML 변환"""

    import markdown
    from markdown.extensions import fenced_code, tables, toc

    # Markdown to HTML conversion with extensions
    md = markdown.Markdown(
        extensions=[
            'fenced_code',
            'tables',
            'toc',
            'nl2br',
            'sane_lists',
            'codehilite',
            'meta'
        ]
    )

    html_content = md.convert(content)

    return {
        "html": html_content,
        "toc": md.toc if hasattr(md, 'toc') else None
    }


# ─────────────────────────────
# Spell Check Endpoint
# ─────────────────────────────
class SpellCheckRequest(BaseModel):
    text: str
    lang: Optional[str] = None  # "ko" | "en" | None (자동 감지)


class SpellCheckResponse(BaseModel):
    original: str
    corrected: str
    lang: str
    model: str


@router.post("/spellcheck", response_model=SpellCheckResponse)
async def check_spelling(request: SpellCheckRequest):
    """
    ByT5 기반 맞춤법 교정 (한국어 + 영어)

    - 모델: google/byt5-small (기본) 또는 SPELLCHECK_MODEL 환경변수로 지정
    - 첫 요청 시 모델 로딩 (수 초 소요)
    - 텍스트 최대 2000자
    """
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="텍스트를 입력해주세요")
    if len(text) > 2000:
        raise HTTPException(status_code=400, detail="텍스트가 너무 깁니다 (최대 2000자)")

    try:
        from app.services.spellcheck import correct, detect_lang, model_info
        loop = asyncio.get_event_loop()
        corrected = await loop.run_in_executor(
            _spellcheck_executor,
            correct,
            text
        )
        lang = request.lang or detect_lang(text)
        return SpellCheckResponse(
            original=text,
            corrected=corrected,
            lang=lang,
            model=model_info(text)
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"맞춤법 검사 오류: {str(e)}")


# ─────────────────────────────
# Get or Create Tag Helper
# ─────────────────────────────
def get_or_create_tag(db: Session, tag_name: str) -> models.Tag:
    """태그를 가져오거나 없으면 생성"""

    tag_name = tag_name.strip().lower()
    tag_slug = tag_name.replace(" ", "-")

    tag = db.query(models.Tag).filter(
        models.Tag.name == tag_name
    ).first()

    if not tag:
        tag = models.Tag(
            name=tag_name,
            slug=tag_slug,
            count=0
        )
        db.add(tag)
        db.commit()
        db.refresh(tag)

    return tag


# ─────────────────────────────
# Process Tags for Post
# ─────────────────────────────
def process_post_tags(db: Session, post: models.BoardPost, tag_names: List[str]):
    """포스트에 태그 연결 및 카운트 업데이트"""

    # 기존 태그 제거
    post.tags.clear()

    # 새 태그 추가
    for tag_name in tag_names:
        if tag_name:
            tag = get_or_create_tag(db, tag_name)
            post.tags.append(tag)
            tag.count = db.query(models.BoardPost).filter(
                models.BoardPost.tags.contains(tag)
            ).count()

    db.commit()