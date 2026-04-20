from __future__ import annotations

from typing import Any


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
