"""알림 생성 헬퍼.

호출부가 commit 한다. 자기 자신에 대한 알림은 만들지 않는다.
"""
from __future__ import annotations


def notify(db, *, recipient_id, actor_id, type, post_id=None, comment_id=None):
    """Add a notification for ``recipient_id`` to the session without committing.

    Args:
        db: SQLAlchemy session; the caller commits.
        recipient_id: User who receives the notification.
        actor_id: User whose action triggered it.
        type: Notification type string stored on the row.
        post_id: Related post id, if any.
        comment_id: Related comment id, if any.

    Returns:
        The new, uncommitted ``Notification``, or ``None`` when there is no
        recipient or the recipient is the actor.
    """
    from app import models

    if not recipient_id or recipient_id == actor_id:
        return None
    n = models.Notification(
        user_id=recipient_id,
        actor_user_id=actor_id,
        type=type,
        post_id=post_id,
        comment_id=comment_id,
    )
    db.add(n)
    return n
