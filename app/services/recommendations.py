from __future__ import annotations

from typing import Any


def get_recommended_blogs(db, viewer=None, limit: int = 5) -> list[dict[str, Any]]:
    """포털 내부 추천 블로그.

    공개 글이 있는 활발한 블로그를 글 수·최근 활동 순으로 추천한다.
    로그인 사용자에게는 본인과 이미 팔로우한 블로그를 제외한다.
    """
    from sqlalchemy import func

    from app import models

    q = (
        db.query(models.User, func.count(models.BoardPost.id).label("post_count"))
        .join(
            models.BoardPost,
            (models.BoardPost.user_id == models.User.id)
            & (models.BoardPost.is_private == False),  # noqa: E712
        )
        .filter(models.User.handle.isnot(None))
        .group_by(models.User.id)
    )

    exclude_ids: set[int] = set()
    if viewer is not None:
        exclude_ids.add(viewer.id)
        exclude_ids |= {
            row.author_user_id
            for row in db.query(models.AuthorFollow)
            .filter(models.AuthorFollow.user_id == viewer.id)
            .all()
        }
    if exclude_ids:
        q = q.filter(~models.User.id.in_(exclude_ids))

    rows = (
        q.order_by(
            func.count(models.BoardPost.id).desc(),
            func.max(models.BoardPost.created_at).desc(),
        )
        .limit(limit)
        .all()
    )
    return [{"user": u, "post_count": n} for (u, n) in rows]


def get_curated_home_recommendations() -> list[dict[str, Any]]:
    """
    홈 화면 추천 슬롯용 수동 큐레이션 데이터.
    추후 DB/관리자 페이지 연동 전까지 기본값으로 사용한다.
    """
    return [
        {
            "title": "Substack",
            "url": "https://substack.com/",
            "summary": "독립 뉴스레터/블로그 생태계",
            "kind": "newsletter_platform",
        },
        {
            "title": "Medium",
            "url": "https://medium.com/",
            "summary": "큐레이션 중심 읽기 경험",
            "kind": "blog_platform",
        },
        {
            "title": "Ghost",
            "url": "https://ghost.org/",
            "summary": "오너십 중심 퍼블리싱 플랫폼",
            "kind": "publishing_platform",
        },
        {
            "title": "Hashnode",
            "url": "https://hashnode.com/",
            "summary": "개발자 블로그/시리즈 중심",
            "kind": "dev_blog_platform",
        },
    ]
