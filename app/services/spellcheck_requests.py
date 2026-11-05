"""Spell-check access requests: a user asks, an admin approves or rejects.

Accounts are not email-verified, so anyone can open many of them. The rules
keep requests cheap to review and hard to abuse:

- only an established account may ask: signed up at least
  ``SPELLCHECK_REQUEST_MIN_ACCOUNT_DAYS`` ago (accounts older than the
  ``users.created_at`` column count as established) or with a public post;
- one pending request per user (also a partial unique index in the
  database), a cooldown after a rejection, and a cap on pending requests
  site-wide;
- the reason is plain text of bounded length, shown escaped to admins;
- a decision changes a request only while it is still pending (one atomic
  UPDATE), so a double click or two admins cannot decide it twice, and the
  user's level never comes from the request form.

Routes add the transport rules: POST only, the cross-site check in
``app/main.py``, a per-user rate limit on submissions, and admin-only
decisions.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.services.notifications import notify
from app.services.spellcheck_access import LEVEL_BASIC, LEVEL_FULL, effective_level

PENDING, APPROVED, REJECTED, CANCELLED = "pending", "approved", "rejected", "cancelled"
REASON_MAX_CHARS = 500
NOTE_MAX_CHARS = 500
# 알림 type (notifications 페이지가 문구를 만든다)
NOTIFY_APPROVED, NOTIFY_REJECTED = "spellcheck_approved", "spellcheck_rejected"

# 줄바꿈·탭을 뺀 제어 문자, 그리고 방향 바꿈 문자(보이는 글과 실제 글을 다르게 만드는 데 쓰인다)
_UNSAFE_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f‪-‮⁦-⁩]")
_BLANK_LINES = re.compile(r"\n{3,}")


class RequestRefused(Exception):
    """A request or decision the rules do not allow; the message is shown to the user."""


class RequestNotFound(RequestRefused):
    """The request to decide does not exist."""


def kst_now() -> datetime:
    """Return the current KST time without tzinfo, as the database stores timestamps."""
    return models.now_kst().replace(tzinfo=None)


def clean_text(raw: Optional[str], limit: int) -> str:
    """Normalize free text from a form: no control or direction characters, bounded.

    Args:
        raw: The submitted text.
        limit: Most characters allowed.

    Returns:
        The text with Windows line ends unified, unsafe characters removed,
        runs of blank lines shortened and the ends trimmed.

    Raises:
        RequestRefused: The cleaned text is longer than ``limit``.
    """
    text = (raw or "").replace("\r\n", "\n").replace("\r", "\n")
    text = _BLANK_LINES.sub("\n\n", _UNSAFE_CHARS.sub("", text)).strip()
    if len(text) > limit:
        raise RequestRefused(f"{limit}자 이내로 적어주세요.")
    return text


def pending_request(db: Session, user_id: int) -> Optional[models.SpellcheckRequest]:
    """Return the user's pending request, if any."""
    return db.query(models.SpellcheckRequest).filter_by(user_id=user_id, status=PENDING).first()


def latest_request(db: Session, user_id: int) -> Optional[models.SpellcheckRequest]:
    """Return the user's most recent request, whatever its status."""
    return (
        db.query(models.SpellcheckRequest)
        .filter_by(user_id=user_id)
        .order_by(models.SpellcheckRequest.id.desc())
        .first()
    )


def _is_established(db: Session, user: models.User, now: datetime) -> bool:
    """Return True if the account is old enough, or has a public post, to ask.

    Args:
        db: Database session.
        user: The account.
        now: Current KST time (naive).

    Returns:
        Whether the account may file a request.
    """
    if user.created_at is None:
        return True
    if now - user.created_at >= timedelta(days=settings.SPELLCHECK_REQUEST_MIN_ACCOUNT_DAYS):
        return True
    public_post = (
        db.query(models.BoardPost.id)
        .filter(models.BoardPost.user_id == user.id, models.BoardPost.is_private == False)  # noqa: E712
        .first()
    )
    return public_post is not None


def request_block_reason(db: Session, user: models.User, now: Optional[datetime] = None) -> Optional[str]:
    """Explain why the user cannot file a request now, or return None if they can.

    Args:
        db: Database session.
        user: The logged-in account.
        now: Current KST time (naive); defaults to now.

    Returns:
        A message for the user, or None.
    """
    now = now or kst_now()
    if effective_level(user) >= LEVEL_FULL:
        return "이미 모든 맞춤법 모델을 쓸 수 있습니다."
    if pending_request(db, user.id):
        return "검토를 기다리는 신청이 있습니다."
    rejected = (
        db.query(models.SpellcheckRequest)
        .filter_by(user_id=user.id, status=REJECTED)
        .order_by(models.SpellcheckRequest.decided_at.desc())
        .first()
    )
    if rejected and rejected.decided_at:
        retry_at = rejected.decided_at + timedelta(days=settings.SPELLCHECK_REQUEST_COOLDOWN_DAYS)
        if now < retry_at:
            return f"거절된 신청은 {retry_at:%Y-%m-%d %H:%M} 이후에 다시 할 수 있습니다."
    if not _is_established(db, user, now):
        return (f"가입 후 {settings.SPELLCHECK_REQUEST_MIN_ACCOUNT_DAYS}일이 지나거나 공개 글을 "
                "하나 이상 쓴 뒤 신청할 수 있습니다.")
    pending_total = db.query(models.SpellcheckRequest).filter_by(status=PENDING).count()
    if pending_total >= settings.SPELLCHECK_REQUEST_PENDING_CAP:
        return "지금은 검토를 기다리는 신청이 많아 받을 수 없습니다. 나중에 다시 시도해주세요."
    return None


def review_queue(db: Session, recent: int = 10) -> tuple[list[dict], list[models.SpellcheckRequest]]:
    """Return what an admin needs to review requests.

    Args:
        db: Database session.
        recent: How many decided requests to list as history.

    Returns:
        ``(pending, decided)``: the pending requests, oldest first, each as
        ``{"request", "user", "public_posts"}`` (the requester's public post
        count helps judge throwaway accounts), and the latest decided or
        cancelled requests, newest first.
    """
    pending = (
        db.query(models.SpellcheckRequest)
        .filter_by(status=PENDING)
        .order_by(models.SpellcheckRequest.id.asc())
        .all()
    )
    items = []
    for request in pending:
        public_posts = (
            db.query(models.BoardPost)
            .filter(models.BoardPost.user_id == request.user_id, models.BoardPost.is_private == False)  # noqa: E712
            .count()
        )
        items.append({"request": request, "user": request.user, "public_posts": public_posts})
    decided = (
        db.query(models.SpellcheckRequest)
        .filter(models.SpellcheckRequest.status != PENDING)
        .order_by(models.SpellcheckRequest.decided_at.desc())
        .limit(recent)
        .all()
    )
    return items, decided


def requestable_levels(user: models.User) -> list[int]:
    """Return the levels the user may ask for: those above their current level."""
    return [level for level in (LEVEL_BASIC, LEVEL_FULL) if level > effective_level(user)]


def create_request(db: Session, user: models.User, level: int, reason: Optional[str]) -> models.SpellcheckRequest:
    """File a request for spell-check access and commit.

    Args:
        db: Database session.
        user: The logged-in account.
        level: The level asked for (1 or 2, above the current level).
        reason: The user's note (plain text, at most ``REASON_MAX_CHARS``).

    Returns:
        The new pending request.

    Raises:
        RequestRefused: The account may not ask now, the level is not one it
            can ask for, or the reason is too long.
    """
    blocked = request_block_reason(db, user)
    if blocked:
        raise RequestRefused(blocked)
    if level not in requestable_levels(user):
        raise RequestRefused("신청할 수 없는 등급입니다.")
    request = models.SpellcheckRequest(
        user_id=user.id,
        requested_level=level,
        reason=clean_text(reason, REASON_MAX_CHARS),
        status=PENDING,
    )
    db.add(request)
    try:
        db.commit()
    except IntegrityError:   # 동시에 두 번 보낸 경우: 대기 신청 1건 고유 인덱스
        db.rollback()
        raise RequestRefused("검토를 기다리는 신청이 있습니다.")
    return request


def cancel_request(db: Session, user: models.User) -> bool:
    """Withdraw the user's pending request and commit.

    Args:
        db: Database session.
        user: The logged-in account.

    Returns:
        True if a pending request was cancelled.
    """
    changed = (
        db.query(models.SpellcheckRequest)
        .filter_by(user_id=user.id, status=PENDING)
        .update({"status": CANCELLED, "decided_at": kst_now()}, synchronize_session=False)
    )
    db.commit()
    return changed > 0


def decide_request(
    db: Session,
    request_id: int,
    admin: models.User,
    approve: bool,
    granted_level: Optional[int] = None,
    note: Optional[str] = None,
) -> models.SpellcheckRequest:
    """Approve or reject a pending request, update the user's level, notify them, commit.

    The status changes in one ``UPDATE ... WHERE status = 'pending'``, so a
    request is decided once even if two decisions arrive together. An
    approval grants ``granted_level`` (at most the requested level) and never
    lowers a level the user already has.

    Args:
        db: Database session.
        request_id: The request.
        admin: The deciding admin (the caller checks ``is_admin``).
        approve: True to approve, False to reject.
        granted_level: Level to grant on approval; defaults to the requested one.
        note: The admin's note to the requester.

    Returns:
        The decided request.

    Raises:
        RequestNotFound: The request does not exist.
        RequestRefused: It is already decided, or the granted level is not
            1 or 2 or above the requested one.
    """
    request = db.query(models.SpellcheckRequest).filter_by(id=request_id).first()
    if request is None:
        raise RequestNotFound("신청을 찾을 수 없습니다.")
    level = (granted_level or request.requested_level) if approve else None
    if approve and (level not in (LEVEL_BASIC, LEVEL_FULL) or level > request.requested_level):
        raise RequestRefused("승인할 수 없는 등급입니다.")
    changed = (
        db.query(models.SpellcheckRequest)
        .filter_by(id=request_id, status=PENDING)
        .update(
            {
                "status": APPROVED if approve else REJECTED,
                "granted_level": level,
                "decided_by_user_id": admin.id,
                "decision_note": clean_text(note, NOTE_MAX_CHARS) or None,
                "decided_at": kst_now(),
            },
            synchronize_session=False,
        )
    )
    if changed == 0:
        db.rollback()
        raise RequestRefused("이미 처리된 신청입니다.")
    if approve:
        user = db.query(models.User).filter_by(id=request.user_id).one()
        user.spellcheck_level = max(int(user.spellcheck_level or 0), level)
    notify(db, recipient_id=request.user_id, actor_id=admin.id,
           type=NOTIFY_APPROVED if approve else NOTIFY_REJECTED)
    db.commit()
    db.refresh(request)
    return request
