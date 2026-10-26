"""주간 다이제스트: 지난 7일 인기 글을 확정 구독자에게 이메일로 보낸다.

- build_weekly_digest(): 발송 내용(제목/본문)만 생성 — 순수 함수(테스트 가능)
- send_weekly_digest(): 확정 구독자에게 발송. SMTP 미설정이면 안전하게 건너뜀.
"""
from __future__ import annotations

import html as _html
from datetime import timedelta
from urllib.parse import urlencode


def _cutoff_kst(days: int):
    """Return the naive KST datetime that lies ``days`` days before now.

    Args:
        days: How many days to go back.

    Returns:
        A timezone-naive ``datetime`` in KST, comparable with the naive
        ``created_at`` values stored on posts.
    """
    from app.models import now_kst
    return now_kst().replace(tzinfo=None) - timedelta(days=days)


def top_weekly_posts(db, days: int = 7, limit: int = 5):
    """Pick the most popular public posts created in the last ``days`` days.

    Posts are ranked by ``likes * 3 + views`` (missing stats count as 0), with
    newer posts first on ties. If no public post was created in that window,
    the newest public posts overall are returned instead.

    Args:
        db: SQLAlchemy session.
        days: Size of the look-back window in days.
        limit: Maximum number of posts to return.

    Returns:
        A list of up to ``limit`` ``BoardPost`` rows; empty only when there are
        no public posts at all.
    """
    from sqlalchemy import func
    from app import models

    score = (func.coalesce(models.PostStats.likes, 0) * 3 + func.coalesce(models.PostStats.views, 0))
    base = (
        db.query(models.BoardPost)
        .outerjoin(models.PostStats, models.PostStats.post_id == models.BoardPost.id)
        .filter(models.BoardPost.is_private == False)  # noqa: E712
        .options()
    )
    posts = (
        base.filter(models.BoardPost.created_at >= _cutoff_kst(days))
        .order_by(score.desc(), models.BoardPost.created_at.desc())
        .limit(limit)
        .all()
    )
    if not posts:  # 최근 7일에 글이 없으면 전체 최신으로 폴백
        posts = base.order_by(models.BoardPost.created_at.desc()).limit(limit).all()
    return posts


def build_weekly_digest(db, base_url: str, days: int = 7, limit: int = 5):
    """Build the subject and plain-text/HTML bodies of the weekly digest email.

    Only reads the database; nothing is sent. Each post gets a link, its
    author (display name or ``@handle``) and a 120-character plain-text preview.
    The HTML uses inline styles because email clients require them.

    Args:
        db: SQLAlchemy session.
        base_url: Public site root used to build absolute post links; a
            trailing slash is ignored.
        days: Look-back window passed to :func:`top_weekly_posts`.
        limit: Maximum number of posts in the digest.

    Returns:
        ``None`` if there are no posts, otherwise a dict with keys
        ``subject`` (str), ``text`` (str), ``html`` (str) and ``posts`` (the
        ``BoardPost`` rows used).
    """
    from app.routers.blog.router import markdown_to_plain

    posts = top_weekly_posts(db, days=days, limit=limit)
    if not posts:
        return None

    base = (base_url or "").rstrip("/")
    subject = f"[Planet KIM] 이번 주 읽어볼 글 {len(posts)}선"

    text_lines = ["이번 주 Planet KIM에서 주목받은 글이에요.\n"]
    html_items = []
    for p in posts:
        link = f"{base}/board/{p.id}"
        author = ""
        if getattr(p, "user", None) and p.user.handle:
            author = p.user.display_name or ("@" + p.user.handle)
        preview = markdown_to_plain(p.content_html or p.content or "", max_len=120)
        title = p.title or "Untitled"
        text_lines.append(f"- {title} ({author})\n  {link}")
        html_items.append(
            "<li style=\"margin:0 0 18px;\">"
            f"<a href=\"{_html.escape(link)}\" style=\"font-size:17px;font-weight:700;color:#b4542f;text-decoration:none;\">{_html.escape(title)}</a>"
            + (f"<div style=\"font-size:13px;color:#8a7c6d;margin:2px 0;\">{_html.escape(author)}</div>" if author else "")
            + f"<div style=\"font-size:14px;color:#4c4239;\">{_html.escape(preview)}</div>"
            "</li>"
        )

    html_body = (
        "<div style=\"font-family:system-ui,sans-serif;max-width:560px;margin:0 auto;\">"
        "<h1 style=\"font-size:22px;color:#262019;\">이번 주 읽어볼 글</h1>"
        "<p style=\"color:#8a7c6d;font-size:14px;\">Planet KIM에서 주목받은 글을 모았어요.</p>"
        f"<ul style=\"list-style:none;padding:0;\">{''.join(html_items)}</ul>"
        f"<p style=\"margin-top:24px;\"><a href=\"{_html.escape(base + '/')}\" style=\"color:#2a82c4;\">더 많은 글 보기 →</a></p>"
    )
    return {"subject": subject, "text": "\n".join(text_lines), "html": html_body, "posts": posts}


def send_weekly_digest(db, base_url: str):
    """Email the weekly digest to every confirmed newsletter subscriber.

    Each message gets a personal unsubscribe link appended to both bodies.
    Does nothing when SMTP is not configured or there are no posts. A failed
    send to one subscriber does not stop the others.

    Args:
        db: SQLAlchemy session.
        base_url: Public site root used for post and unsubscribe links.

    Returns:
        A summary dict: ``{"sent": 0, "skipped": True, "reason":
        "SMTP_NOT_CONFIGURED"}`` without SMTP, ``{"sent": 0, "reason":
        "NO_POSTS"}`` without posts, otherwise ``{"sent": <successful sends>,
        "subscribers": <confirmed subscribers>}``.
    """
    from app import models
    from app.services import newsletter

    if not newsletter._smtp_config_ready():
        return {"sent": 0, "skipped": True, "reason": "SMTP_NOT_CONFIGURED"}

    digest = build_weekly_digest(db, base_url)
    if not digest:
        return {"sent": 0, "reason": "NO_POSTS"}

    subscribers = (
        db.query(models.NewsletterSubscriber)
        .filter(models.NewsletterSubscriber.status == "confirmed")
        .all()
    )
    base = (base_url or "").rstrip("/")
    sent = 0
    for sub in subscribers:
        token, ts = newsletter.build_unsubscribe_token(sub.email)
        unsub = f"{base}/api/newsletter/unsubscribe?" + urlencode({"email": sub.email, "token": token, "ts": ts})
        footer = (
            f"<hr style=\"margin:24px 0;border:none;border-top:1px solid #e8dfd2;\">"
            f"<p style=\"font-size:12px;color:#8a7c6d;\"><a href=\"{_html.escape(unsub)}\" style=\"color:#8a7c6d;\">구독 해지</a></p>"
        )
        ok, _info = newsletter._send_email(digest["subject"], sub.email, digest["text"] + f"\n\n구독 해지: {unsub}", digest["html"] + footer)
        if ok:
            sent += 1
    return {"sent": sent, "subscribers": len(subscribers)}
