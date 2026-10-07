"""
구조화 데이터(JSON-LD / schema.org) 빌더
=========================================
검색엔진·SNS가 글/블로그/사이트를 리치 결과로 이해하도록 schema.org JSON-LD를 생성한다.
- 모든 빌더는 <script type="application/ld+json">에 그대로 넣어도 안전하도록
  `<`, `>`, `&` 및 U+2028/U+2029 를 이스케이프한 **문자열**을 반환한다(템플릿에서 |safe).
- 값이 없는(None/빈) 키는 자동으로 제거해 깔끔한 그래프를 만든다.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

SITE_NAME = "Planet KIM's Travel"


def _abs(request, path_or_url: str) -> str:
    """사이트 절대 URL로 변환. 이미 http(s) 절대 URL이면 그대로 둔다."""
    if not path_or_url:
        return ""
    if path_or_url.startswith(("http://", "https://")):
        return path_or_url
    base = str(request.base_url).rstrip("/")
    if path_or_url.startswith("/"):
        return base + path_or_url
    return f"{base}/{path_or_url}"


def _iso(dt: Optional[datetime]) -> Optional[str]:
    """ISO-8601. naive 값은 DB 기본값이 KST이므로 +09:00 오프셋을 붙인다."""
    if not dt:
        return None
    if dt.tzinfo is None:
        return dt.isoformat() + "+09:00"
    return dt.isoformat()


def _prune(obj):
    """None/빈 값을 재귀적으로 제거."""
    if isinstance(obj, dict):
        return {k: _prune(v) for k, v in obj.items() if v not in (None, "", [], {})}
    if isinstance(obj, list):
        return [_prune(v) for v in obj]
    return obj


def _dump(data: dict) -> str:
    """직렬화 + <script> 탈출 방지 이스케이프."""
    txt = json.dumps(_prune(data), ensure_ascii=False, separators=(",", ":"))
    return (
        txt.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )


def _author_node(request, user) -> dict:
    """Person 노드 (작성자/블로그 주인)."""
    if not user:
        return {}
    name = (
        user.display_name
        or (("@" + user.handle) if user.handle else None)
        or (user.email.split("@")[0] if getattr(user, "email", None) else "작성자")
    )
    node = {"@type": "Person", "name": name}
    if user.handle:
        node["url"] = _abs(request, f"/@{user.handle}")
    if user.avatar_url:
        node["image"] = _abs(request, user.avatar_url)
    return node


def post_jsonld(request, post, description: str = "", image: str = "") -> str:
    """글 상세: BlogPosting."""
    url = _abs(request, f"/board/{post.id}")
    data = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": (post.title or "")[:110],
        "mainEntityOfPage": {"@type": "WebPage", "@id": url},
        "url": url,
        "datePublished": _iso(getattr(post, "created_at", None)),
        "dateModified": _iso(getattr(post, "updated_at", None) or getattr(post, "created_at", None)),
        "author": _author_node(request, getattr(post, "user", None)),
        "publisher": {
            "@type": "Organization",
            "name": SITE_NAME,
            "logo": {"@type": "ImageObject", "url": _abs(request, "/static/favicon.svg")},
        },
        "description": description or None,
        "image": _abs(request, image) if image else None,
        "keywords": ", ".join(t.name for t in (getattr(post, "tags", None) or [])) or None,
    }
    return _dump(data)


def blog_jsonld(request, owner) -> str:
    """블로그 홈(/@handle): Blog + 주인 Person."""
    blog_url = _abs(request, f"/@{owner.handle}")
    blog_name = owner.blog_title or owner.display_name or ("@" + owner.handle)
    author = _author_node(request, owner)
    data = {
        "@context": "https://schema.org",
        "@type": "Blog",
        "@id": blog_url,
        "url": blog_url,
        "name": blog_name,
        "description": owner.bio or None,
        "author": author,
        "publisher": author or None,
    }
    return _dump(data)


def website_jsonld(request) -> str:
    """홈: WebSite + 사이트 내 검색(SearchAction)."""
    base = str(request.base_url).rstrip("/")
    data = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "url": base + "/",
        "potentialAction": {
            "@type": "SearchAction",
            "target": {"@type": "EntryPoint", "urlTemplate": base + "/?q={search_term_string}"},
            "query-input": "required name=search_term_string",
        },
    }
    return _dump(data)
