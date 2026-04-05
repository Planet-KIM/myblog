"""
API 라우터

맞춤법 검사 엔드포인트는 두 레이어로 보호됩니다:

  Layer 1 — Rate Limiter (Redis sliding window)
    유저 ID 기반, 분당 N회 제한 (SPELLCHECK_RATE_LIMIT)
    Redis 없으면 in-memory fallback (단, 서버 재시작 시 초기화됨)

  Layer 2 — Semaphore (asyncio)
    서버 전체 동시 추론 수 제한 (SPELLCHECK_MAX_CONCURRENT)
    모델이 동시에 과부하 걸리는 것을 방지
    대기 중 요청은 큐잉, 타임아웃 초과 시 429 반환
"""

from typing import Optional, List
from datetime import datetime
import asyncio
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app import models
from app.auth_utils import get_current_user
from app.config import settings

# 맞춤법 전용 스레드풀 (Celery 없이 직접 추론할 때 사용)
_spellcheck_executor = ThreadPoolExecutor(max_workers=2)

router = APIRouter(prefix="/api", tags=["api"])


# ─────────────────────────────────────────────
# Rate Limiter
# ─────────────────────────────────────────────

class _InMemoryRateLimiter:
    """
    Redis 없을 때 사용하는 in-memory sliding window rate limiter.
    서버 재시작 시 카운트가 초기화되는 한계가 있음.
    """

    def __init__(self):
        # {user_key: [timestamp, ...]}
        self._windows: dict = defaultdict(list)
        self._lock = asyncio.Lock()

    async def is_allowed(self, key: str, limit: int, window: int) -> bool:
        async with self._lock:
            now = time.time()
            timestamps = self._windows[key]
            # 윈도우 밖 타임스탬프 제거
            self._windows[key] = [t for t in timestamps if now - t < window]
            if len(self._windows[key]) >= limit:
                return False
            self._windows[key].append(now)
            return True


_in_memory_limiter = _InMemoryRateLimiter()


async def _check_rate_limit(user_id: int) -> None:
    """
    유저별 맞춤법 요청 빈도 검사.
    Redis 연결 가능 → Redis sliding window
    Redis 없음     → in-memory fallback
    429 초과 시 HTTPException 발생.
    """
    limit  = settings.SPELLCHECK_RATE_LIMIT
    window = settings.SPELLCHECK_RATE_WINDOW
    key    = f"spellcheck_rl:{user_id}"

    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

        # ZADD + ZREMRANGEBYSCORE 슬라이딩 윈도우
        now = time.time()
        pipe = r.pipeline()
        pipe.zremrangebyscore(key, 0, now - window)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, window)
        results = await pipe.execute()
        count = results[2]
        await r.aclose()

        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"요청이 너무 많습니다. {window}초에 최대 {limit}회 가능합니다.",
            )
    except HTTPException:
        raise
    except Exception:
        # Redis 연결 실패 → in-memory fallback
        allowed = await _in_memory_limiter.is_allowed(key, limit, window)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"요청이 너무 많습니다. {window}초에 최대 {limit}회 가능합니다.",
            )


# ─────────────────────────────────────────────
# Celery 디스패치 (fallback: ThreadPoolExecutor)
# ─────────────────────────────────────────────

async def _run_spellcheck_celery_or_fallback(loop: asyncio.AbstractEventLoop, text: str) -> str:
    """
    Celery 워커가 살아있으면 태스크로 디스패치하고 결과를 기다립니다.
    Redis / Celery 미실행 상태면 ThreadPoolExecutor로 직접 추론합니다.

    Celery 경로:
      run_spellcheck.delay(text)  →  Redis 큐  →  워커 추론  →  AsyncResult.get()

    Fallback 경로:
      run_in_executor(_spellcheck_executor, correct, text)
    """
    try:
        from app.tasks.spellcheck_task import run_spellcheck

        # AsyncResult.get() 은 블로킹 → executor에서 실행
        def _dispatch_and_wait():
            task = run_spellcheck.delay(text)
            # timeout=30: 30초 안에 워커 응답 없으면 예외
            result = task.get(timeout=30)
            return result["corrected"]

        corrected = await loop.run_in_executor(_spellcheck_executor, _dispatch_and_wait)
        return corrected

    except Exception as celery_err:
        # Celery / Redis 미실행 → 직접 추론으로 fallback
        print(f"[SpellCheck] Celery 미사용, 직접 추론으로 전환: {celery_err}")
        from app.services.spellcheck import correct
        return await loop.run_in_executor(_spellcheck_executor, correct, text)


# ─────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────

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


class SpellCheckRequest(BaseModel):
    text: str
    lang: Optional[str] = None  # "ko" | "en" | None (자동 감지)


class SpellCheckResponse(BaseModel):
    original: str
    corrected: str
    lang: str
    model: str


# ─────────────────────────────────────────────
# Draft Auto-Save Endpoint
# ─────────────────────────────────────────────

@router.post("/drafts/save", response_model=DraftSaveResponse)
async def save_draft(
    request: DraftSaveRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """임시 저장 (자동 저장) 엔드포인트"""

    if request.draft_id:
        draft = db.query(models.Draft).filter(
            models.Draft.id == request.draft_id,
            models.Draft.user_id == current_user.id
        ).first()

        if not draft:
            draft = models.Draft(id=request.draft_id, user_id=current_user.id)
            db.add(draft)
    else:
        draft = models.Draft(id=str(uuid4()), user_id=current_user.id)
        db.add(draft)

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


# ─────────────────────────────────────────────
# Tag Endpoints
# ─────────────────────────────────────────────

@router.get("/tags/suggest", response_model=List[TagResponse])
async def suggest_tags(query: str, limit: int = 10, db: Session = Depends(get_db)):
    tags = db.query(models.Tag).filter(
        models.Tag.name.like(f"%{query}%")
    ).order_by(models.Tag.count.desc()).limit(limit).all()
    return [TagResponse(id=t.id, name=t.name, slug=t.slug, count=t.count) for t in tags]


@router.get("/tags/popular", response_model=List[TagResponse])
async def get_popular_tags(limit: int = 20, db: Session = Depends(get_db)):
    tags = db.query(models.Tag).order_by(models.Tag.count.desc()).limit(limit).all()
    return [TagResponse(id=t.id, name=t.name, slug=t.slug, count=t.count) for t in tags]


# ─────────────────────────────────────────────
# Post Statistics Endpoint
# ─────────────────────────────────────────────

@router.post("/stats/update")
async def update_post_stats(request: StatsUpdateRequest, db: Session = Depends(get_db)):
    post = db.query(models.BoardPost).filter(models.BoardPost.id == request.post_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    stats = db.query(models.PostStats).filter(
        models.PostStats.post_id == request.post_id
    ).first()
    if not stats:
        stats = models.PostStats(post_id=request.post_id)
        db.add(stats)

    if request.increment_views:
        stats.views += 1
        stats.last_viewed_at = datetime.utcnow()
    if request.increment_likes:
        stats.likes += 1

    db.commit()
    return {"post_id": request.post_id, "views": stats.views, "likes": stats.likes, "message": "Stats updated"}


# ─────────────────────────────────────────────
# Reading Time Calculation
# ─────────────────────────────────────────────

@router.post("/calculate-reading-time")
async def calculate_reading_time(content: str):
    char_count = len(content.replace(" ", ""))
    reading_time = max(1, round(char_count / 350))
    return {"char_count": char_count, "reading_time_minutes": reading_time, "message": f"약 {reading_time}분 읽기"}


# ─────────────────────────────────────────────
# Markdown Preview Endpoint
# ─────────────────────────────────────────────

@router.post("/markdown/preview")
async def preview_markdown(content: str):
    import markdown
    md = markdown.Markdown(
        extensions=["fenced_code", "tables", "toc", "nl2br", "sane_lists", "codehilite", "meta"]
    )
    html_content = md.convert(content)
    return {"html": html_content, "toc": md.toc if hasattr(md, "toc") else None}


# ─────────────────────────────────────────────
# Spell Check Endpoint
# ─────────────────────────────────────────────

@router.post("/spellcheck", response_model=SpellCheckResponse)
async def check_spelling(
    sc_request: SpellCheckRequest,
    http_request: Request,
    current_user: models.User = Depends(get_current_user),
):
    """
    맞춤법 교정 API

    보호 레이어:
      1. 로그인 필수 (get_current_user)
      2. Rate limit: 유저당 60초에 최대 20회
      3. Semaphore: 서버 전체 동시 추론 최대 2개
         (대기 큐 존재, 10초 내 슬롯 확보 못하면 429)

    글자 수 제한: 최대 500자 (SPELLCHECK_MAX_CHARS)
    """
    text = sc_request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="텍스트를 입력해주세요.")

    max_chars = settings.SPELLCHECK_MAX_CHARS
    if len(text) > max_chars:
        raise HTTPException(
            status_code=400,
            detail=f"텍스트가 너무 깁니다. (최대 {max_chars}자, 현재 {len(text)}자)"
        )

    # ── Layer 1: Rate Limit ───────────────────────────────
    await _check_rate_limit(current_user.id)

    # ── Layer 2: Semaphore (서버 전체 동시 추론 제한) ─────
    semaphore: asyncio.Semaphore = http_request.app.state.spellcheck_semaphore

    try:
        # 10초 내에 슬롯 확보 못하면 서버 과부하로 429 반환
        await asyncio.wait_for(semaphore.acquire(), timeout=10.0)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="서버가 바쁩니다. 잠시 후 다시 시도해주세요.",
        )

    try:
        from app.services.spellcheck import detect_lang, model_info
        loop = asyncio.get_event_loop()
        result = await _run_spellcheck_celery_or_fallback(loop, text)
        lang = sc_request.lang or detect_lang(text)
        return SpellCheckResponse(
            original=text,
            corrected=result,
            lang=lang,
            model=model_info(text),
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"맞춤법 검사 오류: {str(e)}")
    finally:
        # 성공/실패 무관하게 반드시 슬롯 반환
        semaphore.release()


# ─────────────────────────────────────────────
# Tag Helpers (내부 함수)
# ─────────────────────────────────────────────

def get_or_create_tag(db: Session, tag_name: str) -> models.Tag:
    tag_name = tag_name.strip().lower()
    tag_slug = tag_name.replace(" ", "-")
    tag = db.query(models.Tag).filter(models.Tag.name == tag_name).first()
    if not tag:
        tag = models.Tag(name=tag_name, slug=tag_slug, count=0)
        db.add(db)
        db.commit()
        db.refresh(tag)
    return tag


def process_post_tags(db: Session, post: models.BoardPost, tag_names: List[str]):
    post.tags.clear()
    for tag_name in tag_names:
        if tag_name:
            tag = get_or_create_tag(db, tag_name)
            post.tags.append(tag)
            tag.count = db.query(models.BoardPost).filter(
                models.BoardPost.tags.contains(tag)
            ).count()
    db.commit()
