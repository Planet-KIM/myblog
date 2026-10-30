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
import hashlib
import logging
import time
import secrets
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app import models
from app.auth_utils import get_current_user, get_current_user_optional
from app.config import settings
from app.services.newsletter import (
    build_unsubscribe_token,
    send_subscription_confirmed_email,
    send_verification_email,
    verify_unsubscribe_token,
)
from app.services.recommendations import get_curated_home_recommendations
from app.services.post_links import search_link_targets

# 맞춤법 전용 스레드풀 (Celery 없이 직접 추론할 때 사용)
_spellcheck_executor = ThreadPoolExecutor(max_workers=2)
_SPELLCHECK_TASK_MAX_ATTEMPTS = 2
logger = logging.getLogger(__name__)

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
        """Start with no recorded requests."""
        # {user_key: [timestamp, ...]}
        self._windows: dict = defaultdict(list)
        self._lock = asyncio.Lock()

    async def is_allowed(self, key: str, limit: int, window: int) -> bool:
        """Record a request for ``key`` if it fits in the sliding window.

        Args:
            key: Rate-limit bucket, for example ``"spellcheck_rl:<user_id>"``.
            limit: Maximum requests allowed per window.
            window: Window length in seconds.

        Returns:
            True if the request is allowed (and recorded); False if ``limit``
            requests were already made in the last ``window`` seconds.
        """
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

async def _run_spellcheck(
    loop: asyncio.AbstractEventLoop,
    text: str,
    en_variant: str = "vennify",
    ko_variant: str = "et5",
) -> str:
    """
    Celery 워커에 태스크를 전달하고 결과를 기다립니다.
    웹서버는 모델을 들고 있지 않으므로 Celery가 반드시 실행 중이어야 합니다.
    실패 시 태스크를 정리(revoke/forget)하고 새 태스크로 1회 재실행합니다.
    반복 실패 시 503으로 전환합니다.
    """
    try:
        from app.tasks.spellcheck_task import run_spellcheck
        from celery.exceptions import TimeoutError as CeleryTimeoutError

        payload_hash = hashlib.sha1(
            f"{en_variant}|{ko_variant}|{text}".encode("utf-8")
        ).hexdigest()[:12]

        def _dispatch_and_wait():
            """Send the spell-check task to Celery and block until it returns.

            Runs in the spell-check thread pool. Each attempt waits up to 60 s
            (120 s for the large ``coedit``/``pko`` models); a failed or timed-out
            task is revoked and forgotten, and a fresh task is sent, up to
            ``_SPELLCHECK_TASK_MAX_ATTEMPTS`` attempts in total.

            Returns:
                The corrected text from the task result.

            Raises:
                RuntimeError: If every attempt failed or returned a malformed result.
            """
            # 대형 모델(coedit/pko)은 첫 추론 시 워밍업으로 60~90초 소요 가능
            is_large = en_variant == "coedit" or ko_variant == "pko"
            timeout = 120 if is_large else 60
            last_exc: Exception | None = None

            for attempt in range(1, _SPELLCHECK_TASK_MAX_ATTEMPTS + 1):
                task = run_spellcheck.delay(text, en_variant, ko_variant)
                success = False

                try:
                    result = task.get(timeout=timeout)
                    if not isinstance(result, dict) or "corrected" not in result:
                        raise RuntimeError("Celery 결과 포맷이 올바르지 않습니다.")
                    success = True
                    try:
                        task.forget()
                    except Exception:
                        logger.debug(
                            "[SpellCheck] 성공 결과 forget 실패 task_id=%s payload=%s",
                            task.id,
                            payload_hash,
                            exc_info=True,
                        )
                    return result["corrected"]
                except CeleryTimeoutError as exc:
                    last_exc = exc
                    logger.warning(
                        "[SpellCheck] timeout task_id=%s attempt=%s/%s payload=%s",
                        task.id,
                        attempt,
                        _SPELLCHECK_TASK_MAX_ATTEMPTS,
                        payload_hash,
                    )
                except Exception as exc:
                    last_exc = exc
                    logger.exception(
                        "[SpellCheck] 실패 task_id=%s attempt=%s/%s payload=%s",
                        task.id,
                        attempt,
                        _SPELLCHECK_TASK_MAX_ATTEMPTS,
                        payload_hash,
                    )
                finally:
                    if not success:
                        try:
                            # terminate=True는 운영용 비상옵션이며 프로그램적 사용은 지양.
                            task.revoke(terminate=False)
                        except Exception:
                            logger.debug(
                                "[SpellCheck] revoke 실패 task_id=%s payload=%s",
                                task.id,
                                payload_hash,
                                exc_info=True,
                            )
                        try:
                            task.forget()
                        except Exception:
                            logger.debug(
                                "[SpellCheck] 실패 결과 forget 실패 task_id=%s payload=%s",
                                task.id,
                                payload_hash,
                                exc_info=True,
                            )

                if attempt < _SPELLCHECK_TASK_MAX_ATTEMPTS:
                    logger.info(
                        "[SpellCheck] 태스크 재실행 attempt=%s/%s payload=%s",
                        attempt + 1,
                        _SPELLCHECK_TASK_MAX_ATTEMPTS,
                        payload_hash,
                    )

            raise RuntimeError("맞춤법 태스크가 반복 실패했습니다. 잠시 후 다시 시도해주세요.") from last_exc

        return await loop.run_in_executor(_spellcheck_executor, _dispatch_and_wait)

    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(
            f"Celery 워커에 연결할 수 없습니다. 워커가 실행 중인지 확인하세요. ({e})"
        ) from e


# ─────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────

class DraftSaveRequest(BaseModel):
    """Body of an autosave request; omitted (null) fields are left unchanged.

    Attributes:
        draft_id: Draft to update; created under this id if the user has no
            such draft, or under a new UUID when omitted.
        title: Draft title.
        content: Draft body.
        tags: Tags as a JSON string.
        category_id: Chosen category.
        is_private: Chosen visibility (always written).
    """

    draft_id: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[str] = None
    category_id: Optional[int] = None
    is_private: bool = False


class DraftSaveResponse(BaseModel):
    """Result of an autosave.

    Attributes:
        draft_id: Id of the saved draft.
        saved_at: Time the draft was saved.
        message: Status message for the editor.
    """

    draft_id: str
    saved_at: datetime
    message: str


class TagResponse(BaseModel):
    """A tag with its usage count."""

    id: int
    name: str
    slug: str
    count: int


class StatsUpdateRequest(BaseModel):
    """Body of a manual stats update for one post.

    Attributes:
        post_id: The post to update.
        increment_views: Add one view when true.
        increment_likes: Add one like when true.
    """

    post_id: int
    increment_views: bool = False
    increment_likes: bool = False


class NewsletterSubscribeRequest(BaseModel):
    """Body of a newsletter signup.

    Attributes:
        email: Address to subscribe.
        source: Where the signup form was shown (default ``"home"``).
    """

    email: str
    source: Optional[str] = "home"


class ToggleResponse(BaseModel):
    """Result of a like or bookmark toggle.

    Attributes:
        post_id: The post.
        active: Whether the like/bookmark exists after the toggle.
        likes: The post's like count.
        bookmarks: The post's bookmark count.
    """

    post_id: int
    active: bool
    likes: int
    bookmarks: int


class FollowToggleResponse(BaseModel):
    """Result of a follow toggle.

    Attributes:
        active: Whether the user follows the target after the toggle.
        target_type: ``"category"`` or ``"author"``.
        target_id: Id of the category or author.
    """

    active: bool
    target_type: str
    target_id: int


class NewsletterSubscribeResponse(BaseModel):
    """Result of a newsletter signup.

    Attributes:
        email: The normalized email address.
        status: ``"pending"`` or ``"confirmed"``.
        verify_url: Confirmation link, returned only when the email could not
            be sent.
        message: Message to show the user.
    """

    email: str
    status: str
    verify_url: Optional[str] = None
    message: str


class NewsletterUnsubscribeResponse(BaseModel):
    """Result of a newsletter unsubscribe."""

    email: str
    status: str
    message: str


class SpellCheckRequest(BaseModel):
    """Body of a spell-check request.

    Attributes:
        text: Text to correct.
        lang: ``"ko"``, ``"en"``, or None to detect the language.
        en_variant: English model, ``"vennify"`` or ``"coedit"``; None uses
            the configured default.
        ko_variant: Korean model, ``"et5"`` (fast) or ``"pko"`` (higher
            quality); None means ``"et5"``.
    """

    text: str
    lang: Optional[str] = None        # "ko" | "en" | None (자동 감지)
    en_variant: Optional[str] = None  # "vennify" | "coedit" | None (기본값 사용)
    ko_variant: Optional[str] = None  # "et5" (빠름) | "pko" (고품질) | None (기본값 사용)


class SpellCheckResponse(BaseModel):
    """Result of a spell check.

    Attributes:
        original: The input text, trimmed.
        corrected: The corrected text.
        lang: The requested or detected language.
        model: Description of the model that was used.
    """

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
    """Suggest tags whose name contains the query, most used first.

    Args:
        query: Substring to match in tag names.
        limit: Maximum number of tags to return.
        db: Database session.

    Returns:
        Matching tags ordered by usage count, descending.
    """
    tags = db.query(models.Tag).filter(
        models.Tag.name.like(f"%{query}%")
    ).order_by(models.Tag.count.desc()).limit(limit).all()
    return [TagResponse(id=t.id, name=t.name, slug=t.slug, count=t.count) for t in tags]


@router.get("/tags/popular", response_model=List[TagResponse])
async def get_popular_tags(limit: int = 20, db: Session = Depends(get_db)):
    """List the most used tags.

    Args:
        limit: Maximum number of tags to return.
        db: Database session.

    Returns:
        Tags ordered by usage count, descending.
    """
    tags = db.query(models.Tag).order_by(models.Tag.count.desc()).limit(limit).all()
    return [TagResponse(id=t.id, name=t.name, slug=t.slug, count=t.count) for t in tags]


# ─────────────────────────────────────────────
# Post Statistics Endpoint
# ─────────────────────────────────────────────

@router.post("/stats/update")
async def update_post_stats(
    request: StatsUpdateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Increment the view and/or like counters of the user's own post.

    Creates the post's stats row if it does not exist yet.

    Args:
        request: Which post and which counters to increment.
        db: Database session.
        current_user: The logged-in user.

    Returns:
        A dict with ``post_id``, the new ``views`` and ``likes`` and a
        ``message``.

    Raises:
        HTTPException: 401 if not logged in, 404 if the post does not exist,
            403 if the post belongs to another user.
    """
    post = db.query(models.BoardPost).filter(models.BoardPost.id == request.post_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    if post.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="본인 게시글만 수정할 수 있습니다.")

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


@router.post("/posts/{post_id}/like", response_model=ToggleResponse)
async def toggle_post_like(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Like the post, or remove the like if the user already liked it.

    Keeps the cached like count in the post's stats row in step (never below
    zero), creating the row if needed.

    Args:
        post_id: The post to like or unlike.
        db: Database session.
        current_user: The logged-in user.

    Returns:
        The new like state with the post's like and bookmark counts.

    Raises:
        HTTPException: 401 if not logged in, 404 if the post does not exist.
    """
    post = db.query(models.BoardPost).filter(models.BoardPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    stats = db.query(models.PostStats).filter(models.PostStats.post_id == post_id).first()
    if not stats:
        stats = models.PostStats(post_id=post_id, views=0, likes=0)
        db.add(stats)
        db.flush()

    like = (
        db.query(models.PostLike)
        .filter(models.PostLike.post_id == post_id, models.PostLike.user_id == current_user.id)
        .first()
    )
    if like:
        db.delete(like)
        stats.likes = max((stats.likes or 0) - 1, 0)
        active = False
    else:
        db.add(models.PostLike(post_id=post_id, user_id=current_user.id))
        stats.likes = (stats.likes or 0) + 1
        active = True

    db.commit()
    bookmark_count = db.query(models.PostBookmark).filter(models.PostBookmark.post_id == post_id).count()
    return ToggleResponse(
        post_id=post_id,
        active=active,
        likes=stats.likes or 0,
        bookmarks=bookmark_count,
    )


@router.post("/posts/{post_id}/bookmark", response_model=ToggleResponse)
async def toggle_post_bookmark(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Bookmark the post, or remove the bookmark if it already exists.

    Args:
        post_id: The post to bookmark or unbookmark.
        db: Database session.
        current_user: The logged-in user.

    Returns:
        The new bookmark state with the post's like and bookmark counts.

    Raises:
        HTTPException: 401 if not logged in, 404 if the post does not exist.
    """
    post = db.query(models.BoardPost).filter(models.BoardPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    stats = db.query(models.PostStats).filter(models.PostStats.post_id == post_id).first()
    if not stats:
        stats = models.PostStats(post_id=post_id, views=0, likes=0)
        db.add(stats)
        db.flush()

    bookmark = (
        db.query(models.PostBookmark)
        .filter(models.PostBookmark.post_id == post_id, models.PostBookmark.user_id == current_user.id)
        .first()
    )
    if bookmark:
        db.delete(bookmark)
        active = False
    else:
        db.add(models.PostBookmark(post_id=post_id, user_id=current_user.id))
        active = True

    db.commit()
    bookmark_count = db.query(models.PostBookmark).filter(models.PostBookmark.post_id == post_id).count()
    return ToggleResponse(
        post_id=post_id,
        active=active,
        likes=stats.likes or 0,
        bookmarks=bookmark_count,
    )


@router.get("/posts/{post_id}/engagement")
async def get_post_engagement(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user_optional),
):
    """Return a post's like/bookmark counts and the viewer's own state.

    Args:
        post_id: The post.
        db: Database session.
        current_user: The logged-in user, or None for guests.

    Returns:
        A dict with ``post_id``, ``likes``, ``bookmarks``, and ``liked`` /
        ``bookmarked`` for the viewer (always false for guests).

    Raises:
        HTTPException: 404 if the post does not exist, 403 if it is private and
            the viewer is not its author.
    """
    post = db.query(models.BoardPost).filter(models.BoardPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    # 비공개 글은 작성자 본인만 상태 조회 가능
    if post.is_private and (not current_user or post.user_id != current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="비공개 게시글입니다.")

    stats = db.query(models.PostStats).filter(models.PostStats.post_id == post_id).first()
    bookmarks = db.query(models.PostBookmark).filter(models.PostBookmark.post_id == post_id).count()
    liked = False
    bookmarked = False
    if current_user:
        liked = (
            db.query(models.PostLike)
            .filter(models.PostLike.post_id == post_id, models.PostLike.user_id == current_user.id)
            .first()
            is not None
        )
        bookmarked = (
            db.query(models.PostBookmark)
            .filter(models.PostBookmark.post_id == post_id, models.PostBookmark.user_id == current_user.id)
            .first()
            is not None
        )

    return {
        "post_id": post_id,
        "likes": stats.likes if stats else 0,
        "bookmarks": bookmarks,
        "liked": liked,
        "bookmarked": bookmarked,
    }


@router.get("/posts/link-targets")
def post_link_targets(
    q: str = "",
    exclude: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Posts the writer can link to, for the editors' post picker (글 연결).

    Args:
        q: Search text (title or body), or a post URL; empty lists the
            writer's own latest posts.
        exclude: Post being edited, left out.
        db: Database session.
        current_user: The logged-in writer (401 otherwise).

    Returns:
        Up to 8 posts, newest first (see post_links.search_link_targets).
    """
    return search_link_targets(db, current_user, q, exclude_id=exclude)


@router.post("/follow/category/{category_id}", response_model=FollowToggleResponse)
async def toggle_follow_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Follow a category, or unfollow it if already followed.

    Args:
        category_id: The category.
        db: Database session.
        current_user: The logged-in user.

    Returns:
        The new follow state.

    Raises:
        HTTPException: 401 if not logged in, 404 if the category does not exist.
    """
    category = db.query(models.BoardCategory).filter(models.BoardCategory.id == category_id).first()
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    row = (
        db.query(models.CategoryFollow)
        .filter(models.CategoryFollow.user_id == current_user.id, models.CategoryFollow.category_id == category_id)
        .first()
    )
    if row:
        db.delete(row)
        active = False
    else:
        db.add(models.CategoryFollow(user_id=current_user.id, category_id=category_id))
        active = True
    db.commit()

    return FollowToggleResponse(active=active, target_type="category", target_id=category_id)


@router.post("/follow/author/{author_user_id}", response_model=FollowToggleResponse)
async def toggle_follow_author(
    author_user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Follow an author, or unfollow them if already followed.

    A new follow also sends the author a ``"follow"`` notification.

    Args:
        author_user_id: The user to follow.
        db: Database session.
        current_user: The logged-in user.

    Returns:
        The new follow state.

    Raises:
        HTTPException: 401 if not logged in, 404 if the author does not exist,
            400 if users try to follow themselves.
    """
    author = db.query(models.User).filter(models.User.id == author_user_id).first()
    if not author:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Author not found")
    if author.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot follow yourself")

    row = (
        db.query(models.AuthorFollow)
        .filter(models.AuthorFollow.user_id == current_user.id, models.AuthorFollow.author_user_id == author_user_id)
        .first()
    )
    if row:
        db.delete(row)
        active = False
    else:
        db.add(models.AuthorFollow(user_id=current_user.id, author_user_id=author_user_id))
        active = True
        from app.services.notifications import notify
        notify(db, recipient_id=author.id, actor_id=current_user.id, type="follow")
    db.commit()

    return FollowToggleResponse(active=active, target_type="author", target_id=author_user_id)


@router.get("/notifications/unread_count")
async def notifications_unread_count(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_optional),
):
    """Return the viewer's number of unread notifications.

    Args:
        db: Database session.
        current_user: The logged-in user, or None for guests.

    Returns:
        ``{"count": n}``; ``n`` is 0 for guests.
    """
    if not current_user:
        return {"count": 0}
    count = (
        db.query(models.Notification)
        .filter(models.Notification.user_id == current_user.id, models.Notification.is_read == False)  # noqa: E712
        .count()
    )
    return {"count": count}


@router.post("/newsletter/subscribe", response_model=NewsletterSubscribeResponse)
async def subscribe_newsletter(
    payload: NewsletterSubscribeRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """Start a double opt-in newsletter subscription.

    The email is trimmed and lower-cased. An already confirmed address is
    reported as such and left unchanged. Otherwise the subscriber is set to
    ``"pending"`` with a fresh verification token, and a confirmation email is
    sent. When the email cannot be sent (no SMTP or a send error), the
    confirmation link is returned in the response instead.

    Args:
        payload: The email address and signup source.
        http_request: The incoming request, used to build the confirmation URL.
        db: Database session.

    Returns:
        The subscription status and a message for the user.

    Raises:
        HTTPException: 400 if the email is obviously malformed.
    """
    email = payload.email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email format")

    subscriber = (
        db.query(models.NewsletterSubscriber)
        .filter(models.NewsletterSubscriber.email == email)
        .first()
    )

    if subscriber and subscriber.status == "confirmed":
        return NewsletterSubscribeResponse(
            email=email,
            status="confirmed",
            message="이미 구독이 확인된 이메일입니다.",
        )

    token = secrets.token_urlsafe(24)
    if not subscriber:
        subscriber = models.NewsletterSubscriber(
            email=email,
            status="pending",
            verify_token=token,
            source=payload.source or "home",
        )
        db.add(subscriber)
    else:
        subscriber.status = "pending"
        subscriber.verify_token = token
        subscriber.source = payload.source or subscriber.source or "home"
        subscriber.confirmed_at = None

    # verify 토큰 만료 시간 계산 기준
    subscriber.created_at = datetime.utcnow()

    db.commit()

    verify_url = f"{http_request.url_for('verify_newsletter')}?token={token}"
    mail_sent, send_state = send_verification_email(email, verify_url)

    if mail_sent:
        response_verify_url = None
        response_message = "확인 이메일을 발송했습니다. 메일함(스팸함 포함)을 확인해주세요."
    else:
        # 메일 서버가 없거나 발송 실패 시 개발/로컬 환경 fallback
        response_verify_url = verify_url
        response_message = (
            "메일 전송 설정이 없어 확인 링크를 화면에 표시합니다. "
            "링크를 열어 구독을 완료해주세요."
            if send_state == "SMTP_NOT_CONFIGURED"
            else "메일 발송에 실패하여 확인 링크를 화면에 표시합니다. 링크를 열어 구독을 완료해주세요."
        )

    return NewsletterSubscribeResponse(
        email=email,
        status="pending",
        verify_url=response_verify_url,
        message=response_message,
    )


@router.get("/newsletter/verify", name="verify_newsletter")
async def verify_newsletter(token: str, http_request: Request, db: Session = Depends(get_db)):
    """Confirm a newsletter subscription from the emailed link.

    On success the subscriber becomes ``"confirmed"``, the token is cleared,
    and a best-effort "subscription confirmed" email with a signed
    unsubscribe link is sent.

    Args:
        token: Verification token from the confirmation link.
        http_request: The incoming request, used to build the unsubscribe URL.
        db: Database session.

    Returns:
        A dict with the ``email``, ``status`` ``"confirmed"`` and a ``message``.

    Raises:
        HTTPException: 404 if the token is unknown, 400 if the subscription has
            no issue time, 410 if the token is older than
            ``NEWSLETTER_VERIFY_TOKEN_TTL_HOURS``.
    """
    subscriber = (
        db.query(models.NewsletterSubscriber)
        .filter(models.NewsletterSubscriber.verify_token == token)
        .first()
    )
    if not subscriber:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid verification token")

    issued_at = subscriber.created_at
    if issued_at is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification timestamp")

    verify_ttl_seconds = max(1, settings.NEWSLETTER_VERIFY_TOKEN_TTL_HOURS) * 3600
    if issued_at.tzinfo is not None:
        now = datetime.now(tz=issued_at.tzinfo)
    else:
        now = datetime.utcnow()
    if (now - issued_at).total_seconds() > verify_ttl_seconds:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Verification token expired")

    subscriber.status = "confirmed"
    subscriber.confirmed_at = datetime.utcnow()
    subscriber.verify_token = None
    db.commit()

    unsubscribe_token, unsubscribe_issued_at = build_unsubscribe_token(subscriber.email)
    unsubscribe_query = urlencode(
        {
            "email": subscriber.email,
            "token": unsubscribe_token,
            "ts": unsubscribe_issued_at,
        }
    )
    unsubscribe_url = (
        f"{http_request.url_for('unsubscribe_newsletter')}?{unsubscribe_query}"
    )
    # 확인 완료 메일은 실패해도 주 흐름을 깨지 않도록 best-effort
    send_subscription_confirmed_email(
        subscriber.email,
        unsubscribe_url=unsubscribe_url,
    )

    return {"email": subscriber.email, "status": "confirmed", "message": "뉴스레터 구독이 완료되었습니다."}


@router.get("/newsletter/unsubscribe", response_model=NewsletterUnsubscribeResponse, name="unsubscribe_newsletter")
async def unsubscribe_newsletter(email: str, token: str, ts: int, db: Session = Depends(get_db)):
    """Unsubscribe an email address using a signed unsubscribe link.

    Args:
        email: Subscriber address; trimmed and lower-cased.
        token: Signature from the unsubscribe link.
        ts: Time the token was issued (Unix seconds).
        db: Database session.

    Returns:
        The address with status ``"unsubscribed"``.

    Raises:
        HTTPException: 400 if the token is invalid or older than
            ``NEWSLETTER_UNSUBSCRIBE_TOKEN_TTL_HOURS``, 404 if the address is
            not subscribed.
    """
    normalized_email = email.strip().lower()
    unsubscribe_ttl_seconds = max(1, settings.NEWSLETTER_UNSUBSCRIBE_TOKEN_TTL_HOURS) * 3600
    if not verify_unsubscribe_token(
        normalized_email,
        token,
        issued_at=ts,
        max_age_seconds=unsubscribe_ttl_seconds,
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid unsubscribe token")

    subscriber = (
        db.query(models.NewsletterSubscriber)
        .filter(models.NewsletterSubscriber.email == normalized_email)
        .first()
    )
    if not subscriber:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscriber not found")

    subscriber.status = "unsubscribed"
    subscriber.verify_token = None
    db.commit()

    return NewsletterUnsubscribeResponse(
        email=normalized_email,
        status="unsubscribed",
        message="뉴스레터 구독이 해지되었습니다.",
    )


@router.get("/recommendations/home")
async def get_home_recommendations(db: Session = Depends(get_db)):
    """Return the home page recommendation data.

    Args:
        db: Database session.

    Returns:
        A dict with ``curated`` (hand-picked links), ``trending_topics`` (the
        six categories with the most posts, as ``category_id``/``name``/
        ``post_count``) and ``generated_at`` (UTC ISO timestamp).
    """
    category_stats = (
        db.query(
            models.BoardCategory.id,
            models.BoardCategory.name,
            func.count(models.BoardPost.id).label("post_count"),
        )
        .outerjoin(models.BoardPost, models.BoardPost.category_id == models.BoardCategory.id)
        .group_by(models.BoardCategory.id, models.BoardCategory.name)
        .order_by(func.count(models.BoardPost.id).desc(), models.BoardCategory.name.asc())
        .limit(6)
        .all()
    )

    trending_topics = [
        {"category_id": row.id, "name": row.name, "post_count": row.post_count}
        for row in category_stats
    ]
    curated = get_curated_home_recommendations()
    return {
        "curated": curated,
        "trending_topics": trending_topics,
        "generated_at": datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────
# Reading Time Calculation
# ─────────────────────────────────────────────

@router.post("/calculate-reading-time")
async def calculate_reading_time(content: str):
    """Estimate the reading time of a text.

    Counts characters other than spaces and assumes 350 characters per minute.

    Args:
        content: The text to measure (a query parameter).

    Returns:
        A dict with ``char_count``, ``reading_time_minutes`` (at least 1) and a
        Korean ``message``.
    """
    char_count = len(content.replace(" ", ""))
    reading_time = max(1, round(char_count / 350))
    return {"char_count": char_count, "reading_time_minutes": reading_time, "message": f"약 {reading_time}분 읽기"}


# ─────────────────────────────────────────────
# Markdown Preview Endpoint
# ─────────────────────────────────────────────

@router.post("/markdown/preview")
async def preview_markdown(content: str):
    """Render Markdown to HTML for a live preview.

    Args:
        content: Markdown source (a query parameter).

    Returns:
        A dict with the rendered ``html`` and the generated ``toc`` HTML.
    """
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

    en_variant = sc_request.en_variant or settings.SPELLCHECK_EN_DEFAULT_VARIANT
    ko_variant = sc_request.ko_variant or "et5"
    is_large = en_variant == "coedit" or ko_variant == "pko"

    try:
        # 대형 모델(coedit/pko)은 추론이 오래 걸리므로 슬롯 대기 시간도 길게
        wait_timeout = 30.0 if is_large else 10.0
        await asyncio.wait_for(semaphore.acquire(), timeout=wait_timeout)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="서버가 바쁩니다. 잠시 후 다시 시도해주세요.",
        )

    try:
        from app.services.spellcheck import detect_lang, model_info
        loop = asyncio.get_event_loop()
        result = await _run_spellcheck(loop, text, en_variant, ko_variant)
        lang = sc_request.lang or detect_lang(text)
        return SpellCheckResponse(
            original=text,
            corrected=result,
            lang=lang,
            model=model_info(text, en_variant, ko_variant),
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
    """Return the tag with this name, creating and committing it if missing.

    Args:
        db: Database session.
        tag_name: Tag name; trimmed and lower-cased, and its slug is the name
            with spaces replaced by hyphens.

    Returns:
        The existing or newly created tag.
    """
    tag_name = tag_name.strip().lower()
    tag_slug = tag_name.replace(" ", "-")
    tag = db.query(models.Tag).filter(models.Tag.name == tag_name).first()
    if not tag:
        tag = models.Tag(name=tag_name, slug=tag_slug, count=0)
        db.add(tag)
        db.commit()
        db.refresh(tag)
    return tag


def process_post_tags(db: Session, post: models.BoardPost, tag_names: List[str]):
    """게시글 태그를 교체하고 영향받은 태그의 count를 정확히 유지한다.

    count는 연관(post_tags)을 커밋한 뒤 재계산해야 새로 추가된 링크가 반영된다.
    제거된 태그도 다시 세어 untag 시 수치가 과대 계상되지 않도록 한다.
    """
    previous = set(post.tags)
    new_tags = []
    seen = set()
    for tag_name in tag_names:
        name = (tag_name or "").strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        new_tags.append(get_or_create_tag(db, name))

    post.tags = new_tags
    db.commit()  # 먼저 연관을 반영

    for tag in set(new_tags) | previous:
        tag.count = (
            db.query(models.BoardPost)
            .filter(models.BoardPost.tags.contains(tag))
            .count()
        )
    db.commit()
