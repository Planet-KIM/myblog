"""Portal and personal-blog pages.

Serves the portal home (``/``), the CV page (``/main``), the user dashboard
(``/me``), profile editing, each user's blog (``/@handle``) and RSS feeds,
tag, series, search and explore pages, notifications, saved layout
templates, ``robots.txt``/``sitemap.xml`` and legacy ``/posts`` URLs. It
also holds the helpers that turn post bodies into card previews.

Visibility rule used throughout: guests see public posts only; a logged-in
user also sees their own private posts. Hidden (moderated) posts are always
excluded by the global session filter in ``app.database``.
"""
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import re
import html as html_module
import markdown
import copy

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import or_, func
from sqlalchemy.orm import Session, joinedload
from fastapi.templating import Jinja2Templates

from app import models
from app.config import settings
from app.database import get_db
from app.auth_utils import get_current_user, get_current_user_optional
from app.services.profile import validate_handle, validate_avatar_url, validate_accent_color
from app.services.seo import website_jsonld, blog_jsonld
from app.services.home_layout import (
    HOME_LAYOUT_STRATEGY_PER_REQUEST_RANDOM,
    HOME_LAYOUT_STRATEGY_DAILY_STABLE_BY_VIEWER,
    select_home_card_sizes,
)
from app.services.category_counts import (
    collect_descendant_category_ids,
    order_categories_parent_first,
    rollup_category_counts,
)
from app.services.recommendations import get_recommended_blogs
from app.cv_content import (
    cv_profile,
    education,
    experience,
    industry,
    skills,
    projects,
    skill_palette,
    research_interest,
)

router = APIRouter(prefix="/blog", tags=["blog"])

def render_markdown_fields(cv):
    """
    cv_content 에서 넘어온 데이터 구조에 맞춰
    **bold** 같은 인라인 마크다운을 HTML(<strong> 등)로 변환한다.
    - experience.ko.bullets / experience.en.bullets
    - projects[*].bullets_ko / projects[*].bullets_en
    만 처리한다.
    """
    cv_copy = copy.deepcopy(cv)

    def md_list(lst):
        """문자열 리스트에 markdown 변환 적용"""
        return [markdown.markdown(text, extensions=["extra"]) for text in lst]

    # 1) 연구실 Experience bullets (ko/en)
    exp = cv_copy.get("experience")
    if isinstance(exp, dict):
        for lang in ("ko", "en"):
            section = exp.get(lang)
            if isinstance(section, dict) and isinstance(section.get("bullets"), list):
                section["bullets"] = md_list(section["bullets"])

    # 2) Projects bullets_ko / bullets_en
    proj_list = cv_copy.get("projects") or []
    if isinstance(proj_list, list):
        for proj in proj_list:
            if not isinstance(proj, dict):
                continue
            for key in ("bullets_ko", "bullets_en"):
                if isinstance(proj.get(key), list):
                    proj[key] = md_list(proj[key])

    # 3) Research Interest 처리
    ri = cv_copy.get("research_interest")
    if isinstance(ri, dict):
        for sec in ri.get("sections", []):
            if isinstance(sec.get("bullets"), list):
                sec["bullets"] = md_list(sec["bullets"])
    return cv_copy

templates = Jinja2Templates(directory="app/templates")

router = APIRouter(tags=["blog"])


def build_approved_api_catalog() -> List[Dict[str, str]]:
    """내부에서 사용 가능한 승인 API 카탈로그."""
    return [
        {
            "name": "북마크 토글",
            "method": "POST",
            "path": "/api/posts/{post_id}/bookmark",
            "auth": "로그인 필요",
            "access": "쓰기",
            "purpose": "글을 저장/해제하여 나중에 다시 보기",
            "curl_example": "curl -X POST -H 'Content-Type: application/json' -b 'session=...' http://127.0.0.1:8000/api/posts/36/bookmark",
            "fetch_example": "fetch('/api/posts/36/bookmark', { method: 'POST', credentials: 'same-origin' })",
        },
        {
            "name": "좋아요 토글",
            "method": "POST",
            "path": "/api/posts/{post_id}/like",
            "auth": "로그인 필요",
            "access": "쓰기",
            "purpose": "좋아요 반응 등록/해제",
            "curl_example": "curl -X POST -H 'Content-Type: application/json' -b 'session=...' http://127.0.0.1:8000/api/posts/36/like",
            "fetch_example": "fetch('/api/posts/36/like', { method: 'POST', credentials: 'same-origin' })",
        },
        {
            "name": "게시글 참여 상태 조회",
            "method": "GET",
            "path": "/api/posts/{post_id}/engagement",
            "auth": "선택(로그인 시 개인 상태 포함)",
            "access": "읽기",
            "purpose": "likes/bookmarks 총량 + 내 active 상태 조회",
            "curl_example": "curl 'http://127.0.0.1:8000/api/posts/36/engagement'",
            "fetch_example": "fetch('/api/posts/36/engagement', { credentials: 'same-origin' })",
        },
        {
            "name": "카테고리 팔로우",
            "method": "POST",
            "path": "/api/follow/category/{category_id}",
            "auth": "로그인 필요",
            "access": "쓰기",
            "purpose": "관심 카테고리 팔로우/해제",
            "curl_example": "curl -X POST -H 'Content-Type: application/json' -b 'session=...' http://127.0.0.1:8000/api/follow/category/1",
            "fetch_example": "fetch('/api/follow/category/1', { method: 'POST', credentials: 'same-origin' })",
        },
        {
            "name": "작성자 팔로우",
            "method": "POST",
            "path": "/api/follow/author/{author_user_id}",
            "auth": "로그인 필요",
            "access": "쓰기",
            "purpose": "관심 작성자 팔로우/해제",
            "curl_example": "curl -X POST -H 'Content-Type: application/json' -b 'session=...' http://127.0.0.1:8000/api/follow/author/2",
            "fetch_example": "fetch('/api/follow/author/2', { method: 'POST', credentials: 'same-origin' })",
        },
        {
            "name": "태그 자동완성",
            "method": "GET",
            "path": "/api/tags/suggest?q=keyword",
            "auth": "불필요",
            "access": "읽기",
            "purpose": "입력 중인 태그 추천",
            "curl_example": "curl 'http://127.0.0.1:8000/api/tags/suggest?q=tr'",
            "fetch_example": "fetch('/api/tags/suggest?q=tr')",
        },
        {
            "name": "인기 태그 조회",
            "method": "GET",
            "path": "/api/tags/popular?limit=20",
            "auth": "불필요",
            "access": "읽기",
            "purpose": "홈/작성 화면에서 인기 태그 노출",
            "curl_example": "curl 'http://127.0.0.1:8000/api/tags/popular?limit=20'",
            "fetch_example": "fetch('/api/tags/popular?limit=20')",
        },
        {
            "name": "홈 추천 슬롯",
            "method": "GET",
            "path": "/api/recommendations/home",
            "auth": "불필요",
            "access": "읽기",
            "purpose": "홈 추천 링크 목록 조회",
            "curl_example": "curl 'http://127.0.0.1:8000/api/recommendations/home'",
            "fetch_example": "fetch('/api/recommendations/home')",
        },
        {
            "name": "뉴스레터 구독",
            "method": "POST",
            "path": "/api/newsletter/subscribe",
            "auth": "불필요",
            "access": "쓰기",
            "purpose": "double opt-in 구독 요청",
            "curl_example": "curl -X POST -H 'Content-Type: application/json' -d '{\"email\":\"you@example.com\"}' http://127.0.0.1:8000/api/newsletter/subscribe",
            "fetch_example": "fetch('/api/newsletter/subscribe', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'you@example.com' }) })",
        },
        {
            "name": "읽기시간 계산",
            "method": "POST",
            "path": "/api/calculate-reading-time",
            "auth": "불필요",
            "access": "읽기",
            "purpose": "텍스트 기반 예상 읽기시간 계산",
            "curl_example": "curl -X POST -H 'Content-Type: application/json' -d '{\"content\":\"example text\"}' http://127.0.0.1:8000/api/calculate-reading-time",
            "fetch_example": "fetch('/api/calculate-reading-time', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content: 'example text' }) })",
        },
        {
            "name": "마크다운 미리보기",
            "method": "POST",
            "path": "/api/markdown/preview",
            "auth": "불필요",
            "access": "읽기",
            "purpose": "마크다운을 렌더링 HTML로 변환",
            "curl_example": "curl -X POST -H 'Content-Type: application/json' -d '{\"content\":\"# hello\"}' http://127.0.0.1:8000/api/markdown/preview",
            "fetch_example": "fetch('/api/markdown/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content: '# hello' }) })",
        },
        {
            "name": "맞춤법 검사",
            "method": "POST",
            "path": "/api/spellcheck",
            "auth": "로그인 필요",
            "access": "쓰기",
            "purpose": "본문 맞춤법 교정 결과 반환 (rate limit 적용)",
            "curl_example": "curl -X POST -H 'Content-Type: application/json' -b 'session=...' -d '{\"text\":\"안녕하세요\"}' http://127.0.0.1:8000/api/spellcheck",
            "fetch_example": "fetch('/api/spellcheck', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: '안녕하세요' }) })",
        },
    ]


def markdown_to_plain(text: str, max_len: int = 180) -> str:
    """Markdown/HTML 혼합 본문에서 카드용 순수 텍스트 미리보기 생성."""
    text = (text or "").strip()
    if not text:
        return ""

    # 1) 이미지 문법은 미리 제거 (alt/url 노이즈 방지)
    text = re.sub(r'!\[.*?\]\(.*?\)', ' ', text)

    # 2) Markdown -> HTML 정규화
    raw_html = markdown.markdown(text, extensions=['fenced_code', 'tables'])

    # 3) 코드/스크립트/스타일 블록 제거 (카드 미리보기 노이즈 방지)
    raw_html = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', raw_html)
    raw_html = re.sub(r'(?is)<pre[^>]*>.*?</pre>', ' ', raw_html)
    raw_html = re.sub(r'(?is)<code[^>]*>.*?</code>', ' ', raw_html)

    # 4) 태그 제거 -> 엔티티 복원 -> 잔재 태그 재제거
    plain = re.sub(r'<[^>]+>', ' ', raw_html)
    plain = html_module.unescape(plain)
    plain = re.sub(r'<[^>\n]+>', ' ', plain)

    # 5) 남아있는 꺾쇠 제거 (엔티티 복원 후 생긴 태그 조각 방어)
    plain = plain.replace("<", " ").replace(">", " ")

    # 6) 줄바꿈/연속 공백 정리
    plain = re.sub(r'\s+', ' ', plain).strip()

    # 7) 최대 길이 제한
    if len(plain) > max_len:
        plain = plain[:max_len] + '...'
    return plain


def extract_first_image(text: str):
    """
    본문에서 첫 번째 이미지 URL을 추출한다.
    지원 포맷:
    1) Markdown: ![alt](url)
    2) HTML: <img src="..."> 또는 <img data-src="...">
    3) Inline style: background-image: url(...)
    """
    if not text:
        return None

    # 1) Markdown 이미지
    md_match = re.search(r'!\[[^\]]*]\(([^)]+)\)', text)
    if md_match:
        md_url = md_match.group(1).strip()
        # ![alt](url "title") 형태 대응: 첫 토큰만 URL로 사용
        md_url = md_url.split()[0].strip("<>")
        if md_url:
            return html_module.unescape(md_url)

    # 2) HTML 이미지 태그 (src / data-src)
    html_match = re.search(
        r'<img[^>]+(?:src|data-src)\s*=\s*["\']([^"\']+)["\']',
        text,
        flags=re.IGNORECASE,
    )
    if html_match:
        return html_module.unescape(html_match.group(1).strip())

    # 2-1) 따옴표 없는 속성값 fallback
    html_unquoted_match = re.search(
        r'<img[^>]+(?:src|data-src)\s*=\s*([^\s>]+)',
        text,
        flags=re.IGNORECASE,
    )
    if html_unquoted_match:
        return html_module.unescape(html_unquoted_match.group(1).strip())

    # 3) inline background-image
    bg_match = re.search(
        r'background-image\s*:\s*url\((["\']?)(.*?)\1\)',
        text,
        flags=re.IGNORECASE,
    )
    if bg_match and bg_match.group(2).strip():
        return html_module.unescape(bg_match.group(2).strip())

    return None


def estimate_reading_minutes(text: str) -> int:
    """Estimate the reading time of a post body.

    Args:
        text: Markdown or HTML body.

    Returns:
        Minutes at 350 non-whitespace characters per minute (counted on the
        plain-text form, at most 10,000 characters), never less than 1.
    """
    plain = markdown_to_plain(text or "", max_len=10000)
    char_count = len(re.sub(r"\s+", "", plain))
    return max(1, round(char_count / 350))


def count_toc_headings(text: str) -> int:
    """Count the headings that would appear in a table of contents.

    Args:
        text: Markdown or HTML body.

    Returns:
        Number of Markdown ATX headings (``#`` to ``######``) plus HTML
        ``<h1>``-``<h6>`` elements; 0 for empty text.
    """
    if not text:
        return 0
    markdown_headings = re.findall(r"^\s{0,3}#{1,6}\s+.+$", text, flags=re.MULTILINE)
    html_headings = re.findall(r"<h[1-6][^>]*>.*?</h[1-6]>", text, flags=re.IGNORECASE | re.DOTALL)
    return len(markdown_headings) + len(html_headings)


def detect_post_type(text: str) -> str:
    """Classify a post body for card styling.

    Args:
        text: Markdown or HTML body.

    Returns:
        ``"photo"`` if it contains an image; otherwise ``"link"`` if it contains
        an http(s) URL and under 900 plain-text characters; otherwise
        ``"note"`` if under 260 characters; otherwise ``"essay"``.
    """
    plain = markdown_to_plain(text or "", max_len=8000)
    plain_len = len(plain)
    has_image = extract_first_image(text or "") is not None
    has_url = bool(re.search(r"https?://", text or ""))

    if has_image:
        return "photo"
    if has_url and plain_len < 900:
        return "link"
    if plain_len < 260:
        return "note"
    return "essay"


def extract_key_sentence(text: str) -> str:
    """Pick a representative sentence from a post body.

    Args:
        text: Markdown or HTML body.

    Returns:
        The first sentence of at least 24 characters in the plain text (first
        3,000 characters), or the first 120 characters if there is none.
    """
    plain = markdown_to_plain(text or "", max_len=3000)
    sentences = re.split(r"(?<=[\.\!\?。！？])\s+", plain)
    for sentence in sentences:
        cleaned = sentence.strip()
        if len(cleaned) >= 24:
            return cleaned
    return plain[:120].strip()


def extract_series_label(post: models.BoardPost) -> Optional[str]:
    """Return the name of the series a post belongs to, if any.

    Looks first for a tag named ``series:<name>`` or ``시리즈:<name>`` (prefix
    case-insensitive), then for ``[series: <name>]`` / ``[시리즈 - <name>]`` in
    the title.

    Args:
        post: The post to inspect.

    Returns:
        The series name (``"Series"``/``"시리즈"`` when a series tag has an
        empty name), or None if the post is not part of a series.
    """
    for tag in (post.tags or []):
        tag_name = (tag.name or "").strip()
        lower = tag_name.lower()
        if lower.startswith("series:"):
            return tag_name.split(":", 1)[1].strip() or "Series"
        if lower.startswith("시리즈:"):
            return tag_name.split(":", 1)[1].strip() or "시리즈"
    title = post.title or ""
    match = re.search(r"\[(series|시리즈)\s*[:\-]\s*([^\]]+)\]", title, flags=re.IGNORECASE)
    if match:
        return match.group(2).strip()
    return None


@router.get("/", response_class=HTMLResponse)
def read_index(
    request: Request,
    feed: str = "latest",
    q: Optional[str] = None,
    category_id: Optional[int] = None,
    sort: str = "recent",
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user_optional),
):
    """홈(/) 페이지: 비로그인=public, 로그인=public+내 private"""
    feed_mode = (feed or "latest").strip().lower()
    if feed_mode not in {"latest", "following", "recommended"}:
        feed_mode = "latest"

    sort_mode = (sort or "recent").strip().lower()
    if sort_mode not in {"recent", "popular", "discussed"}:
        sort_mode = "recent"

    categories = db.query(models.BoardCategory).order_by(models.BoardCategory.id).all()
    selected_category_ids: list[int] | None = None
    if category_id:
        selected_category_ids = collect_descendant_category_ids(categories, category_id)

    def visible_posts_query(with_options: bool = True):
        """Build the query of posts the viewer may see, with the page's filters.

        Applies the visibility rule, the ``q`` search (title, body, HTML body or
        author) and the selected category with its sub-categories.

        Args:
            with_options: Eager-load category, user, stats and tags when true;
                pass False for count queries.

        Returns:
            An unordered SQLAlchemy query of ``BoardPost``.
        """
        query = db.query(models.BoardPost)
        if with_options:
            query = query.options(
                joinedload(models.BoardPost.category),
                joinedload(models.BoardPost.user),
                joinedload(models.BoardPost.stats),
                joinedload(models.BoardPost.tags),
            )

        if current_user:
            query = query.filter(
                or_(
                    models.BoardPost.is_private == False,
                    models.BoardPost.user_id == current_user.id,
                )
            )
        else:
            query = query.filter(models.BoardPost.is_private == False)

        if q:
            query = query.filter(
                or_(
                    models.BoardPost.title.ilike(f"%{q}%"),
                    models.BoardPost.content.ilike(f"%{q}%"),
                    models.BoardPost.content_html.ilike(f"%{q}%"),
                    models.BoardPost.author.ilike(f"%{q}%"),
                )
            )
        if selected_category_ids:
            query = query.filter(models.BoardPost.category_id.in_(selected_category_ids))
        return query

    def apply_sort(query):
        """Order a post query by the selected ``sort`` mode.

        Args:
            query: A ``BoardPost`` query.

        Returns:
            The query ordered by views (``"popular"``), by likes (``"discussed"``)
            or by newest first; ties are broken by newest first.
        """
        if sort_mode == "popular":
            return (
                query.outerjoin(models.PostStats, models.PostStats.post_id == models.BoardPost.id)
                .order_by(func.coalesce(models.PostStats.views, 0).desc(), models.BoardPost.created_at.desc())
            )
        if sort_mode == "discussed":
            return (
                query.outerjoin(models.PostStats, models.PostStats.post_id == models.BoardPost.id)
                .order_by(func.coalesce(models.PostStats.likes, 0).desc(), models.BoardPost.created_at.desc())
            )
        return query.order_by(models.BoardPost.created_at.desc())

    HOME_LIMIT = 12
    following_requires_login = False
    following_empty = False

    followed_category_ids: set[int] = set()
    followed_author_ids: set[int] = set()
    if current_user:
        followed_category_ids = {
            row.category_id
            for row in db.query(models.CategoryFollow)
            .filter(models.CategoryFollow.user_id == current_user.id)
            .all()
        }
        followed_author_ids = {
            row.author_user_id
            for row in db.query(models.AuthorFollow)
            .filter(models.AuthorFollow.user_id == current_user.id)
            .all()
        }

    posts: list[models.BoardPost] = []
    base_query = visible_posts_query(with_options=True)

    if feed_mode == "following":
        if not current_user:
            following_requires_login = True
        elif not followed_category_ids and not followed_author_ids:
            following_empty = True
        else:
            follow_filters = []
            if followed_category_ids:
                follow_filters.append(models.BoardPost.category_id.in_(followed_category_ids))
            if followed_author_ids:
                follow_filters.append(models.BoardPost.user_id.in_(followed_author_ids))
            posts = apply_sort(base_query.filter(or_(*follow_filters))).limit(HOME_LIMIT).all()
            if not posts:
                following_empty = True
    elif feed_mode == "recommended":
        posts = (
            base_query.outerjoin(models.PostStats, models.PostStats.post_id == models.BoardPost.id)
            .order_by(
                func.coalesce(models.PostStats.likes, 0).desc(),
                func.coalesce(models.PostStats.views, 0).desc(),
                models.BoardPost.created_at.desc(),
            )
            .limit(HOME_LIMIT)
            .all()
        )
    else:
        posts = apply_sort(base_query).limit(HOME_LIMIT).all()

    if feed_mode == "following" and not posts and not following_requires_login and not following_empty:
        following_empty = True

    latest_query = visible_posts_query(with_options=True)
    board_posts = latest_query.order_by(models.BoardPost.created_at.desc()).limit(5).all()

    # 히어로 아래 featured: 조회수 높은 공개 글 4개 (없으면 최신) — 커버 스토리 1 + 옆 목록 3
    featured_posts = (
        visible_posts_query(with_options=True)
        .outerjoin(models.PostStats, models.PostStats.post_id == models.BoardPost.id)
        .order_by(
            func.coalesce(models.PostStats.views, 0).desc(),
            models.BoardPost.created_at.desc(),
        )
        .limit(4)
        .all()
    )

    visible_post_total = (
        visible_posts_query(with_options=False)
        .with_entities(func.count(models.BoardPost.id))
        .scalar()
        or 0
    )

    # 포털 지표 & 사람(블로거) 노출
    blogger_count = (
        db.query(func.count(func.distinct(models.BoardPost.user_id)))
        .filter(models.BoardPost.is_private == False)  # noqa: E712
        .scalar()
        or 0
    )
    tag_total = (
        db.query(func.count(models.Tag.id)).filter(models.Tag.count > 0).scalar() or 0
    )
    featured_bloggers = [
        {"user": u, "post_count": n}
        for (u, n) in (
            db.query(models.User, func.count(models.BoardPost.id).label("cnt"))
            .join(
                models.BoardPost,
                (models.BoardPost.user_id == models.User.id)
                & (models.BoardPost.is_private == False),  # noqa: E712
            )
            .filter(models.User.handle.isnot(None))
            .group_by(models.User.id)
            .order_by(func.count(models.BoardPost.id).desc(), func.max(models.BoardPost.created_at).desc())
            .limit(8)
            .all()
        )
    ]

    def enrich_post(post: models.BoardPost):
        """Attach the display attributes the home cards need to a post, in place.

        Sets ``preview``, ``thumbnail``, ``reading_minutes``, ``toc_count``,
        ``series_label``, ``post_type``, ``type_label``, ``like_count``,
        ``view_count``, ``comment_count`` (always 0), ``discussion_score``,
        ``is_followed_category``, ``is_followed_author`` and ``card_variant``.

        Args:
            post: The post to decorate.
        """
        source = post.content_html or post.content or ""
        preview = markdown_to_plain(source)
        key_sentence = extract_key_sentence(source)
        toc_count = count_toc_headings(source)

        post.preview = key_sentence if len(preview) > 170 and key_sentence else preview
        post.thumbnail = extract_first_image(source)
        post.reading_minutes = estimate_reading_minutes(source)
        post.toc_count = toc_count
        post.series_label = extract_series_label(post)
        post.post_type = detect_post_type(source)
        post.type_label = {
            "essay": "에세이",
            "photo": "사진기록",
            "link": "링크노트",
            "note": "짧은메모",
        }.get(post.post_type, "에세이")
        post.like_count = post.stats.likes if post.stats else 0
        post.view_count = post.stats.views if post.stats else 0
        post.comment_count = 0
        post.discussion_score = (post.like_count * 3) + (post.view_count // 20)
        post.is_followed_category = bool(current_user and post.category_id in followed_category_ids)
        post.is_followed_author = bool(
            current_user
            and post.user_id in followed_author_ids
            and post.user_id != current_user.id
        )
        if not post.thumbnail:
            post.card_variant = f"thumbless-{post.post_type}"
        else:
            post.card_variant = "with-thumb"

    seen_ids = set()
    for item in posts + board_posts + featured_posts:
        if item.id in seen_ids:
            continue
        enrich_post(item)
        seen_ids.add(item.id)

    viewer_key = str(current_user.id) if current_user else (request.client.host if request.client else "anon")
    available_layout_strategies = {
        "random": HOME_LAYOUT_STRATEGY_PER_REQUEST_RANDOM,
        "stable": HOME_LAYOUT_STRATEGY_DAILY_STABLE_BY_VIEWER,
    }
    # 기본을 stable 로: 새로고침마다 카드 배치가 바뀌는 산만함 제거 (?layout=random 로 복귀 가능)
    layout_mode = request.query_params.get("layout", "stable").strip().lower()
    if layout_mode not in available_layout_strategies:
        layout_mode = "random"
    layout_strategy = available_layout_strategies[layout_mode]
    card_sizes = select_home_card_sizes(
        posts_count=len(posts),
        strategy=layout_strategy,
        viewer_key=viewer_key,
    )

    category_rows = (
        visible_posts_query(with_options=False)
        .with_entities(models.BoardPost.category_id, func.count(models.BoardPost.id))
        .filter(models.BoardPost.category_id.isnot(None))
        .group_by(models.BoardPost.category_id)
        .all()
    )
    direct_category_counts = {cid: cnt for cid, cnt in category_rows}
    category_counts = rollup_category_counts(categories, direct_category_counts)
    ordered_categories, category_depths = order_categories_parent_first(categories)
    tone_names = ["sea", "forest", "sunset", "rose", "violet", "amber"]
    category_tones = {cat.id: tone_names[cat.id % len(tone_names)] for cat in categories}

    trending_topics = [
        {
            "id": cat.id,
            "name": cat.name,
            "count": category_counts.get(cat.id, 0),
            "depth": category_depths.get(cat.id, 0),
        }
        for cat in ordered_categories
    ]
    # 포털 내부 추천: 활발한 다른 블로그 + 전역 인기 태그
    recommended_blogs = get_recommended_blogs(db, current_user, limit=5)
    popular_tags = (
        db.query(models.Tag)
        .filter(models.Tag.count > 0)
        .order_by(models.Tag.count.desc(), models.Tag.name.asc())
        .limit(15)
        .all()
    )

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "jsonld": website_jsonld(request),
            "posts": posts,
            "board_posts": board_posts,
            "featured_posts": featured_posts,
            "featured_bloggers": featured_bloggers,
            "today": datetime.now(),
            "blogger_count": blogger_count,
            "tag_total": tag_total,
            "categories": categories,
            "ordered_categories": ordered_categories,
            "category_depths": category_depths,
            "current_user": current_user,
            "card_sizes": card_sizes,
            "visible_post_total": visible_post_total,
            "category_counts": category_counts,
            "category_tones": category_tones,
            "selected_feed": feed_mode,
            "selected_sort": sort_mode,
            "search_query": q or "",
            "selected_category_id": category_id,
            "following_requires_login": following_requires_login,
            "following_empty": following_empty,
            "followed_category_ids": followed_category_ids,
            "followed_author_ids": followed_author_ids,
            "recommended_blogs": recommended_blogs,
            "popular_tags": popular_tags,
            "trending_topics": trending_topics,
        },
    )


@router.get("/main", response_class=HTMLResponse)
def main_page(
    request: Request,
    db: Session = Depends(get_db),
    published: bool = False,
    current_user: Optional[models.User] = Depends(get_current_user_optional),
):
    """
    CV 메인(/main)

    Recent Posts:
      - 작성 후 1일 이내(posted within last 24h)만 조회
      - 비로그인: public만
      - 로그인: public + 내가 쓴 private
    """
    q = db.query(models.BoardPost)
    cutoff = datetime.utcnow() - timedelta(days=1)

    if current_user:
        recent_posts = (
            q.filter(
                models.BoardPost.created_at >= cutoff,
                or_(
                    models.BoardPost.is_private == False,
                    models.BoardPost.user_id == current_user.id,
                ),
            )
            .order_by(models.BoardPost.created_at.desc())
            .limit(5)
            .all()
        )
    else:
        recent_posts = (
            q.filter(
                models.BoardPost.is_private == False,
                models.BoardPost.created_at >= cutoff,
            )
            .order_by(models.BoardPost.created_at.desc())
            .limit(5)
            .all()
        )

    # 프로젝트는 end_year(없으면 현재=9999), start_year 기준으로 내림차순 정렬
    sorted_projects = sorted(
        projects,
        key=lambda p: (
            p.get("end_year") or 9999,
            p.get("start_year") or 0,
        ),
        reverse=True,
    )

    cv = {
        "profile": cv_profile,
        "education": education,
        "experience": experience,
        "industry": industry,
        "skills": skills,
        "skill_palette": skill_palette,
        "projects": sorted_projects,
        "research_interest": research_interest,
    }
    # 추가항
    cv = render_markdown_fields(cv)
    return templates.TemplateResponse(
        request,
        "main.html",
        {
            "request": request,
            "published": published,
            "recent_posts": recent_posts,
            "current_user": current_user,
            "cv": cv,
            "current_year": datetime.utcnow().year,
        },
    )


@router.get("/me", response_class=HTMLResponse)
def my_page(
    request: Request,
    tab: str = "bookmarks",
    q: Optional[str] = None,
    category_id: Optional[str] = None,
    sort: str = "recent",
    page: int = 1,
    size: int = 20,
    issue_state: Optional[str] = None,
    issue_page: int = 1,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user_optional),
):
    """Render the user's dashboard (``/me``).

    Tabs: ``bookmarks`` (the user's bookmarked posts, filterable by search
    text and category, sortable by ``recent``, ``oldest`` or ``popular``, and
    paginated), ``apis`` (catalog of the site's public API endpoints) and
    ``issues`` (GitHub issues of ``settings.GITHUB_REPO``, fetched only on that
    tab). Unknown values fall back to the defaults.

    Args:
        request: The incoming request.
        tab: ``"bookmarks"``, ``"apis"`` or ``"issues"``.
        q: Search text for bookmarks.
        category_id: Category filter for bookmarks (sub-categories included);
            ignored if not an integer.
        sort: Bookmark order.
        page: Bookmark page, clamped to the valid range.
        size: Bookmarks per page, clamped to 1-50.
        issue_state: ``"open"``, ``"closed"`` or ``"all"``; defaults to
            ``settings.GITHUB_ISSUES_DEFAULT_STATE``.
        issue_page: GitHub issues page.
        db: Database session.
        current_user: The logged-in user, or None.

    Returns:
        The ``me.html`` page, or a 303 redirect to ``/auth/login`` for guests.
    """
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)

    tab_mode = (tab or "bookmarks").strip().lower()
    if tab_mode not in {"bookmarks", "apis", "issues"}:
        tab_mode = "bookmarks"

    sort_mode = (sort or "recent").strip().lower()
    if sort_mode not in {"recent", "oldest", "popular"}:
        sort_mode = "recent"

    page = max(1, page)
    size = max(1, min(size, 50))

    categories = db.query(models.BoardCategory).order_by(models.BoardCategory.id.asc()).all()
    selected_category_id: Optional[int] = None
    if category_id not in (None, ""):
        try:
            selected_category_id = int(category_id)
        except (TypeError, ValueError):
            selected_category_id = None

    selected_category_ids: list[int] | None = None
    if selected_category_id is not None:
        selected_category_ids = collect_descendant_category_ids(categories, selected_category_id)

    bookmark_query = (
        db.query(models.PostBookmark)
        .join(models.BoardPost, models.PostBookmark.post_id == models.BoardPost.id)
        .outerjoin(models.PostStats, models.PostStats.post_id == models.BoardPost.id)
        .options(
            joinedload(models.PostBookmark.post).joinedload(models.BoardPost.category),
            joinedload(models.PostBookmark.post).joinedload(models.BoardPost.stats),
            joinedload(models.PostBookmark.post).joinedload(models.BoardPost.tags),
        )
        .filter(models.PostBookmark.user_id == current_user.id)
        .filter(
            or_(
                models.BoardPost.is_private == False,
                models.BoardPost.user_id == current_user.id,
            )
        )
    )

    if q:
        bookmark_query = bookmark_query.filter(
            or_(
                models.BoardPost.title.ilike(f"%{q}%"),
                models.BoardPost.content.ilike(f"%{q}%"),
                models.BoardPost.content_html.ilike(f"%{q}%"),
                models.BoardPost.author.ilike(f"%{q}%"),
            )
        )

    if selected_category_ids:
        bookmark_query = bookmark_query.filter(models.BoardPost.category_id.in_(selected_category_ids))

    if sort_mode == "oldest":
        bookmark_query = bookmark_query.order_by(models.PostBookmark.created_at.asc())
    elif sort_mode == "popular":
        bookmark_query = bookmark_query.order_by(
            func.coalesce(models.PostStats.views, 0).desc(),
            func.coalesce(models.PostStats.likes, 0).desc(),
            models.PostBookmark.created_at.desc(),
        )
    else:
        bookmark_query = bookmark_query.order_by(models.PostBookmark.created_at.desc())

    total_bookmarks = (
        bookmark_query.order_by(None)
        .with_entities(func.count(models.PostBookmark.id))
        .scalar()
        or 0
    )
    total_pages = max(1, (total_bookmarks + size - 1) // size)
    page = min(page, total_pages)

    bookmark_rows = bookmark_query.offset((page - 1) * size).limit(size).all()

    bookmarked_posts: list[models.BoardPost] = []
    for row in bookmark_rows:
        post = row.post
        if not post:
            continue

        source = post.content_html or post.content or ""
        preview = markdown_to_plain(source, max_len=180)
        key_sentence = extract_key_sentence(source)

        post.preview = key_sentence if len(preview) > 170 and key_sentence else preview
        post.thumbnail = extract_first_image(source)
        post.reading_minutes = estimate_reading_minutes(source)
        post.like_count = post.stats.likes if post.stats else 0
        post.view_count = post.stats.views if post.stats else 0
        post.bookmark_saved_at = row.created_at
        bookmarked_posts.append(post)

    category_rows = (
        db.query(models.BoardPost.category_id, func.count(models.PostBookmark.id))
        .join(models.PostBookmark, models.PostBookmark.post_id == models.BoardPost.id)
        .filter(models.PostBookmark.user_id == current_user.id)
        .filter(
            or_(
                models.BoardPost.is_private == False,
                models.BoardPost.user_id == current_user.id,
            )
        )
        .group_by(models.BoardPost.category_id)
        .all()
    )
    bookmark_category_counts = {cid: cnt for cid, cnt in category_rows if cid is not None}
    approved_api_catalog = build_approved_api_catalog()

    issue_state_mode = (issue_state or settings.GITHUB_ISSUES_DEFAULT_STATE or "open").strip().lower()
    if issue_state_mode not in {"open", "closed", "all"}:
        issue_state_mode = "open"
    issue_page = max(1, issue_page)

    github_issue_items: list[dict] = []
    github_issue_has_next = False
    github_issue_has_prev = issue_page > 1
    github_issue_error: Optional[str] = None
    github_rate_remaining: Optional[str] = None

    if tab_mode == "issues":
        from app.services.github_issues import fetch_github_issues

        issue_result = fetch_github_issues(
            repo=settings.GITHUB_REPO,
            state=issue_state_mode,
            page=issue_page,
            per_page=settings.GITHUB_ISSUES_PER_PAGE,
            token=settings.GITHUB_TOKEN,
            timeout_seconds=settings.GITHUB_ISSUES_TIMEOUT_SECONDS,
        )
        github_issue_items = issue_result.get("items", [])
        github_issue_has_next = bool(issue_result.get("has_next"))
        github_issue_has_prev = bool(issue_result.get("has_prev"))
        github_issue_error = issue_result.get("error")
        github_rate_remaining = issue_result.get("rate_remaining")

    return templates.TemplateResponse(
        request,
        "me.html",
        {
            "request": request,
            "current_user": current_user,
            "selected_tab": tab_mode,
            "bookmarked_posts": bookmarked_posts,
            "search_query": q or "",
            "selected_category_id": selected_category_id,
            "selected_sort": sort_mode,
            "current_page": page,
            "total_pages": total_pages,
            "size": size,
            "total_bookmarks": total_bookmarks,
            "categories": categories,
            "bookmark_category_counts": bookmark_category_counts,
            "approved_api_catalog": approved_api_catalog,
            "github_repo": settings.GITHUB_REPO,
            "issue_state": issue_state_mode,
            "issue_page": issue_page,
            "github_issue_items": github_issue_items,
            "github_issue_has_next": github_issue_has_next,
            "github_issue_has_prev": github_issue_has_prev,
            "github_issue_error": github_issue_error,
            "github_rate_remaining": github_rate_remaining,
        },
    )


# ─────────────────────────────────────────────
# 프로필 편집 (/me/profile)
# ─────────────────────────────────────────────
@router.get("/me/profile", response_class=HTMLResponse)
def profile_edit_form(
    request: Request,
    saved: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
):
    """Render the profile edit form filled with the user's current values.

    Args:
        request: The incoming request.
        saved: When set, show the "profile saved" message.
        current_user: The logged-in user.

    Returns:
        The ``profile_edit.html`` page.

    Raises:
        HTTPException: 401 if not logged in.
    """
    return templates.TemplateResponse(
        request,
        "profile_edit.html",
        {
            "request": request,
            "current_user": current_user,
            "error": None,
            "success": "프로필이 저장되었습니다." if saved else None,
            "form": {
                "handle": current_user.handle or "",
                "display_name": current_user.display_name or "",
                "blog_title": current_user.blog_title or "",
                "bio": current_user.bio or "",
                "avatar_url": current_user.avatar_url or "",
                "cover_url": current_user.cover_url or "",
                "accent_color": current_user.accent_color or "",
            },
        },
    )


@router.post("/me/profile", response_class=HTMLResponse)
def profile_edit_save(
    request: Request,
    handle: str = Form(...),
    display_name: str = Form(""),
    blog_title: str = Form(""),
    bio: str = Form(""),
    avatar_url: str = Form(""),
    cover_url: str = Form(""),
    accent_color: str = Form(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Validate and save the user's blog profile.

    The handle must be valid and not used by another user; avatar and cover
    URLs must be http(s) or site-internal; the accent color must be
    ``#rrggbb``. Display name, blog title and bio are trimmed and cut to 60,
    100 and 500 characters, and empty values are stored as None.

    Args:
        request: The incoming request.
        handle: Blog handle used in ``/@handle``.
        display_name: Public display name.
        blog_title: Blog title.
        bio: Short introduction.
        avatar_url: Profile image URL.
        cover_url: Blog cover image URL.
        accent_color: Blog accent color.
        db: Database session.
        current_user: The logged-in user.

    Returns:
        A 303 redirect to the user's blog on success, or the form again with
        an error message and status 400.

    Raises:
        HTTPException: 401 if not logged in.
    """
    form = {
        "handle": handle, "display_name": display_name, "blog_title": blog_title,
        "bio": bio, "avatar_url": avatar_url, "cover_url": cover_url, "accent_color": accent_color,
    }

    def render_error(message: str):
        """Re-render the profile form with an error and the submitted values.

        Args:
            message: Error message to show.

        Returns:
            The ``profile_edit.html`` page with status 400.
        """
        return templates.TemplateResponse(
            request,
            "profile_edit.html",
            {"request": request, "current_user": current_user, "error": message,
             "success": None, "form": form},
            status_code=400,
        )

    handle_norm, err = validate_handle(handle)
    if err:
        return render_error(err)

    # 핸들 유니크 검사 (본인 제외)
    taken = (
        db.query(models.User)
        .filter(models.User.handle == handle_norm, models.User.id != current_user.id)
        .first()
    )
    if taken:
        return render_error("이미 사용 중인 핸들입니다. 다른 값을 입력해주세요.")

    avatar_safe, avatar_err = validate_avatar_url(avatar_url)
    if avatar_err:
        return render_error(avatar_err)

    cover_safe, cover_err = validate_avatar_url(cover_url)
    if cover_err:
        return render_error("커버 이미지 URL이 올바르지 않습니다. (http/https 또는 내부 경로만 허용)")

    accent_safe, accent_err = validate_accent_color(accent_color)
    if accent_err:
        return render_error(accent_err)

    current_user.handle = handle_norm
    current_user.display_name = (display_name or "").strip()[:60] or None
    current_user.blog_title = (blog_title or "").strip()[:100] or None
    current_user.bio = (bio or "").strip()[:500] or None
    current_user.avatar_url = avatar_safe
    current_user.cover_url = cover_safe
    current_user.accent_color = accent_safe
    db.commit()

    return RedirectResponse(f"/@{handle_norm}", status_code=303)


# ─────────────────────────────────────────────
# 개인 블로그 홈 (/@handle)
# ─────────────────────────────────────────────
@router.get("/@{handle}", response_class=HTMLResponse)
def blog_home(
    handle: str,
    request: Request,
    page: int = 1,
    category: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user_optional),
):
    """Render a user's personal blog home (``/@handle``).

    Lists the owner's posts, 10 per page and newest first, optionally limited
    to one of the owner's categories. The owner also sees their private posts.
    The header shows follower count, total posts, categories and the owner's
    series (``series:<name>`` tags on public posts).

    Args:
        handle: Blog handle; matched case-insensitively.
        request: The incoming request.
        page: Page number, clamped to the valid range.
        category: Id of one of the owner's categories; other ids are ignored.
        db: Database session.
        current_user: The logged-in user, or None.

    Returns:
        The ``blog_home.html`` page with SEO/Open Graph metadata.

    Raises:
        HTTPException: 404 if no user has this handle.
    """
    owner = (
        db.query(models.User)
        .filter(models.User.handle == (handle or "").lower())
        .first()
    )
    if not owner:
        raise HTTPException(status_code=404, detail="블로그를 찾을 수 없습니다.")

    is_owner = bool(current_user and current_user.id == owner.id)
    is_following = False
    if current_user and not is_owner:
        is_following = (
            db.query(models.AuthorFollow)
            .filter(
                models.AuthorFollow.user_id == current_user.id,
                models.AuthorFollow.author_user_id == owner.id,
            )
            .first()
            is not None
        )
    follower_count = (
        db.query(models.AuthorFollow)
        .filter(models.AuthorFollow.author_user_id == owner.id)
        .count()
    )
    size = 10
    page = max(1, page)

    base_query = db.query(models.BoardPost).filter(models.BoardPost.user_id == owner.id)
    if not is_owner:
        base_query = base_query.filter(models.BoardPost.is_private == False)  # noqa: E712

    # 헤더 통계는 블로그 전체 기준, 목록은 선택한 카테고리로 필터
    total_posts = base_query.with_entities(func.count(models.BoardPost.id)).scalar() or 0

    active_category = None
    list_query = base_query
    if category:
        cat = db.query(models.BoardCategory).filter_by(id=category, user_id=owner.id).first()
        if cat:
            active_category = cat.id
            list_query = base_query.filter(models.BoardPost.category_id == cat.id)

    filtered_total = list_query.with_entities(func.count(models.BoardPost.id)).scalar() or 0
    total_pages = max(1, (filtered_total + size - 1) // size)
    page = min(page, total_pages)

    posts = (
        list_query.options(joinedload(models.BoardPost.category), joinedload(models.BoardPost.stats))
        .order_by(models.BoardPost.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    for post in posts:
        source = post.content_html or post.content or ""
        post.preview = markdown_to_plain(source)
        post.thumbnail = extract_first_image(source)
        post.reading_minutes = estimate_reading_minutes(source)
        post.view_count = post.stats.views if post.stats else 0

    categories = (
        db.query(models.BoardCategory)
        .filter(models.BoardCategory.user_id == owner.id)
        .order_by(models.BoardCategory.created_at.asc())
        .all()
    )

    # 이 블로거의 매거진/시리즈 (series:<이름> 태그로 묶인 공개 글)
    owner_series = [
        {
            "label": t.name.split(":", 1)[1].strip(),
            "slug": t.name.split(":", 1)[1].strip().lower(),
            "count": c,
        }
        for (t, c) in (
            db.query(models.Tag, func.count(models.BoardPost.id))
            .join(models.BoardPost.tags)
            .filter(
                models.BoardPost.user_id == owner.id,
                models.BoardPost.is_private == False,  # noqa: E712
                func.lower(models.Tag.name).like("series:%"),
            )
            .group_by(models.Tag.id)
            .order_by(func.count(models.BoardPost.id).desc())
            .all()
        )
    ]

    blog_name = owner.blog_title or owner.display_name or ("@" + owner.handle)
    og_image = owner.avatar_url or ""
    if og_image.startswith("/"):
        og_image = str(request.base_url).rstrip("/") + og_image

    return templates.TemplateResponse(
        request,
        "blog_home.html",
        {
            "request": request,
            "owner": owner,
            "is_owner": is_owner,
            "is_following": is_following,
            "meta_description": owner.bio or f"@{owner.handle}의 블로그",
            "og_title": blog_name,
            "og_image": og_image,
            "og_type": "profile",
            "canonical_url": str(request.base_url).rstrip("/") + f"/@{owner.handle}",
            "jsonld": blog_jsonld(request, owner),
            "posts": posts,
            "categories": categories,
            "active_category": active_category,
            "follower_count": follower_count,
            "owner_series": owner_series,
            "current_user": current_user,
            "current_page": page,
            "total_pages": total_pages,
            "total_posts": total_posts,
        },
    )


# ─────────────────────────────────────────────
# 태그 피드 (/tags/{slug}) — 포털 전역 탐색 축
# ─────────────────────────────────────────────
@router.get("/tags/{slug}", response_class=HTMLResponse)
def tag_feed(
    slug: str,
    request: Request,
    page: int = 1,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user_optional),
):
    """Render the feed of posts with a given tag, 12 per page, newest first.

    Args:
        slug: Tag slug; matched case-insensitively.
        request: The incoming request.
        page: Page number, clamped to the valid range.
        db: Database session.
        current_user: The logged-in user, or None.

    Returns:
        The ``tags_feed.html`` page, with the 20 most used tags for navigation.

    Raises:
        HTTPException: 404 if the tag does not exist.
    """
    tag = db.query(models.Tag).filter(models.Tag.slug == (slug or "").lower()).first()
    if not tag:
        raise HTTPException(status_code=404, detail="태그를 찾을 수 없습니다.")

    size = 12
    page = max(1, page)

    query = (
        db.query(models.BoardPost)
        .join(models.BoardPost.tags)
        .filter(models.Tag.id == tag.id)
        .options(joinedload(models.BoardPost.user), joinedload(models.BoardPost.stats))
    )
    if current_user:
        query = query.filter(
            or_(models.BoardPost.is_private == False, models.BoardPost.user_id == current_user.id)  # noqa: E712
        )
    else:
        query = query.filter(models.BoardPost.is_private == False)  # noqa: E712

    total_posts = query.with_entities(func.count(models.BoardPost.id)).scalar() or 0
    total_pages = max(1, (total_posts + size - 1) // size)
    page = min(page, total_pages)

    posts = (
        query.order_by(models.BoardPost.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    for post in posts:
        source = post.content_html or post.content or ""
        post.preview = markdown_to_plain(source)
        post.thumbnail = extract_first_image(source)
        post.reading_minutes = estimate_reading_minutes(source)
        post.view_count = post.stats.views if post.stats else 0

    popular_tags = (
        db.query(models.Tag).order_by(models.Tag.count.desc(), models.Tag.name.asc()).limit(20).all()
    )

    return templates.TemplateResponse(
        request,
        "tags_feed.html",
        {
            "request": request,
            "tag": tag,
            "posts": posts,
            "popular_tags": popular_tags,
            "current_user": current_user,
            "current_page": page,
            "total_pages": total_pages,
            "total_posts": total_posts,
            "meta_description": f"#{tag.name} 태그의 글 {total_posts}개",
            "og_title": f"#{tag.name}",
        },
    )


# ─────────────────────────────────────────────
# 블로그별 RSS 2.0 피드 (/@{handle}/rss)
# ─────────────────────────────────────────────
@router.get("/@{handle}/rss")
def blog_rss(
    handle: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Serve an RSS 2.0 feed of a blog's 20 newest public posts.

    Args:
        handle: Blog handle; matched case-insensitively.
        request: The incoming request, used for absolute links.
        db: Database session.

    Returns:
        An ``application/rss+xml`` response.

    Raises:
        HTTPException: 404 if no user has this handle.
    """
    from xml.sax.saxutils import escape

    owner = db.query(models.User).filter(models.User.handle == (handle or "").lower()).first()
    if not owner:
        raise HTTPException(status_code=404, detail="블로그를 찾을 수 없습니다.")

    posts = (
        db.query(models.BoardPost)
        .filter(models.BoardPost.user_id == owner.id, models.BoardPost.is_private == False)  # noqa: E712
        .order_by(models.BoardPost.created_at.desc())
        .limit(20)
        .all()
    )

    base = str(request.base_url).rstrip("/")
    blog_name = owner.blog_title or owner.display_name or ("@" + owner.handle)
    self_url = f"{base}/@{owner.handle}"

    items = []
    for p in posts:
        link = f"{base}/board/{p.id}"
        desc = markdown_to_plain(p.content_html or p.content or "", max_len=300)
        pub = p.created_at.strftime("%a, %d %b %Y %H:%M:%S +0900") if p.created_at else ""
        items.append(
            "<item>"
            f"<title>{escape(p.title or 'Untitled')}</title>"
            f"<link>{escape(link)}</link>"
            f"<guid isPermaLink=\"true\">{escape(link)}</guid>"
            f"<pubDate>{escape(pub)}</pubDate>"
            f"<description>{escape(desc)}</description>"
            "</item>"
        )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        f"<title>{escape(blog_name)}</title>"
        f"<link>{escape(self_url)}</link>"
        f"<description>{escape(owner.bio or (blog_name + ' 블로그'))}</description>"
        f"{''.join(items)}"
        "</channel></rss>"
    )
    return Response(content=xml, media_type="application/rss+xml")


# ─────────────────────────────────────────────
# 포털 전역 RSS 피드 (/feed) — 모든 공개 글
# ─────────────────────────────────────────────
@router.get("/feed")
def portal_rss(request: Request, db: Session = Depends(get_db)):
    """Serve an RSS 2.0 feed of the 40 newest public posts across all blogs.

    Args:
        request: The incoming request, used for absolute links.
        db: Database session.

    Returns:
        An ``application/rss+xml`` response; items carry the author name when
        the author has a handle.
    """
    from xml.sax.saxutils import escape

    posts = (
        db.query(models.BoardPost)
        .options(joinedload(models.BoardPost.user))
        .filter(models.BoardPost.is_private == False)  # noqa: E712
        .order_by(models.BoardPost.created_at.desc())
        .limit(40)
        .all()
    )
    base = str(request.base_url).rstrip("/")
    items = []
    for p in posts:
        link = f"{base}/board/{p.id}"
        desc = markdown_to_plain(p.content_html or p.content or "", max_len=300)
        pub = p.created_at.strftime("%a, %d %b %Y %H:%M:%S +0900") if p.created_at else ""
        author = (p.user.display_name or ("@" + p.user.handle)) if (p.user and p.user.handle) else ""
        items.append(
            "<item>"
            f"<title>{escape(p.title or 'Untitled')}</title>"
            f"<link>{escape(link)}</link>"
            f"<guid isPermaLink=\"true\">{escape(link)}</guid>"
            f"<pubDate>{escape(pub)}</pubDate>"
            + (f"<author>{escape(author)}</author>" if author else "")
            + f"<description>{escape((author + ' · ' if author else '') + desc)}</description>"
            "</item>"
        )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        "<title>Planet KIM</title>"
        f"<link>{escape(base + '/')}</link>"
        "<description>모든 블로그의 공개 글</description>"
        f"{''.join(items)}"
        "</channel></rss>"
    )
    return Response(content=xml, media_type="application/rss+xml")


# ─────────────────────────────────────────────
# 알림 목록 (/notifications) — 보는 순간 읽음 처리
# ─────────────────────────────────────────────
@router.get("/notifications", response_class=HTMLResponse)
def notifications_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Render the user's 50 newest notifications and mark them read.

    Each item gets a message and a link (the follower's blog for follows, the
    post's comments for comments). Unread notifications shown are marked as
    read once the page is built.

    Args:
        request: The incoming request.
        db: Database session.
        current_user: The logged-in user.

    Returns:
        The ``notifications.html`` page.

    Raises:
        HTTPException: 401 if not logged in.
    """
    notes = (
        db.query(models.Notification)
        .options(joinedload(models.Notification.actor))
        .filter(models.Notification.user_id == current_user.id)
        .order_by(models.Notification.created_at.desc())
        .limit(50)
        .all()
    )
    post_ids = {n.post_id for n in notes if n.post_id}
    posts = {}
    if post_ids:
        rows = (
            db.query(models.BoardPost)
            .execution_options(include_hidden=True)
            .filter(models.BoardPost.id.in_(post_ids))
            .all()
        )
        posts = {p.id: p for p in rows}

    items, unread_ids = [], []
    for n in notes:
        if not n.is_read:
            unread_ids.append(n.id)
        actor = n.actor
        actor_name = (
            (actor.display_name or ("@" + actor.handle)) if (actor and actor.handle)
            else (actor.email.split("@")[0] if actor else "누군가")
        )
        if n.type == "follow":
            msg = f"{actor_name}님이 회원님을 팔로우했어요"
            link = f"/@{actor.handle}" if (actor and actor.handle) else "/"
        else:
            post = posts.get(n.post_id)
            title = post.title if post else "글"
            msg = f"{actor_name}님이 '{title}'에 댓글을 남겼어요"
            link = f"/board/{n.post_id}#comments" if n.post_id else "/"
        items.append({"n": n, "actor": actor, "msg": msg, "link": link})

    if unread_ids:
        db.query(models.Notification).filter(models.Notification.id.in_(unread_ids)).update(
            {models.Notification.is_read: True}, synchronize_session=False
        )
        db.commit()

    return templates.TemplateResponse(
        request,
        "notifications.html",
        {"request": request, "current_user": current_user, "items": items},
    )


# ─────────────────────────────────────────────
# 전용 검색 (/search) — 전 블로그 교차 검색 + 태그/작성자 필터
# ─────────────────────────────────────────────
@router.get("/search", response_class=HTMLResponse)
def search_page(
    request: Request,
    q: Optional[str] = None,
    tag: Optional[str] = None,
    author: Optional[str] = None,
    page: int = 1,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user_optional),
):
    """Search posts across all blogs, 12 per page, newest first.

    Filters combine: ``q`` matches title or body, ``tag`` is a tag slug and
    ``author`` a blog handle (an unknown handle matches nothing). With no
    criteria the page shows no results. Each result gets ``preview_html``: the
    HTML-escaped preview with matches wrapped in ``<mark>``.

    Args:
        request: The incoming request.
        q: Search text.
        tag: Tag slug; lower-cased.
        author: Author handle, with or without ``@``; lower-cased.
        page: Page number, clamped to the valid range.
        db: Database session.
        current_user: The logged-in user, or None.

    Returns:
        The ``search.html`` page.
    """
    size = 12
    page = max(1, page)
    q = (q or "").strip()
    tag = (tag or "").strip().lower()
    author = (author or "").strip().lstrip("@").lower()

    query = db.query(models.BoardPost).options(
        joinedload(models.BoardPost.user),
        joinedload(models.BoardPost.category),
        joinedload(models.BoardPost.stats),
    )
    if current_user:
        query = query.filter(
            or_(models.BoardPost.is_private == False, models.BoardPost.user_id == current_user.id)  # noqa: E712
        )
    else:
        query = query.filter(models.BoardPost.is_private == False)  # noqa: E712

    author_user = None
    if author:
        author_user = db.query(models.User).filter(models.User.handle == author).first()
        query = query.filter(models.BoardPost.user_id == (author_user.id if author_user else -1))
    if tag:
        query = query.join(models.BoardPost.tags).filter(models.Tag.slug == tag)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                models.BoardPost.title.ilike(like),
                models.BoardPost.content.ilike(like),
                models.BoardPost.content_html.ilike(like),
            )
        )

    has_criteria = bool(q or tag or author)
    total = query.with_entities(func.count(func.distinct(models.BoardPost.id))).scalar() or 0 if has_criteria else 0
    total_pages = max(1, (total + size - 1) // size)
    page = min(page, total_pages)

    posts = []
    if has_criteria:
        posts = (
            query.order_by(models.BoardPost.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )
        import html as _html
        import re as _re
        hl = None
        if q:
            hl = _re.compile(_re.escape(_html.escape(q)), _re.IGNORECASE)
        for post in posts:
            source = post.content_html or post.content or ""
            post.preview = markdown_to_plain(source)
            post.thumbnail = extract_first_image(source)
            post.reading_minutes = estimate_reading_minutes(source)
            post.view_count = post.stats.views if post.stats else 0
            # 검색어 하이라이트: 이스케이프한 미리보기에 <mark> 래핑(XSS 안전)
            esc = _html.escape(post.preview or "")
            post.preview_html = hl.sub(lambda m: f"<mark>{m.group(0)}</mark>", esc) if hl else esc

    return templates.TemplateResponse(
        request,
        "search.html",
        {
            "request": request,
            "current_user": current_user,
            "posts": posts,
            "q": q,
            "tag": tag,
            "author": author,
            "author_user": author_user,
            "has_criteria": has_criteria,
            "total": total,
            "current_page": page,
            "total_pages": total_pages,
            "meta_description": (f"'{q}' 검색 결과" if q else "검색"),
            "og_title": (f"'{q}' 검색" if q else "검색"),
        },
    )


# ─────────────────────────────────────────────
# 내 매거진 레이아웃 템플릿 (/me/templates)
# ─────────────────────────────────────────────
@router.get("/me/templates", response_class=HTMLResponse)
def my_templates(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """List the user's saved magazine layout templates and the starter layouts.

    Args:
        request: The incoming request.
        db: Database session.
        current_user: The logged-in user.

    Returns:
        The ``my_templates.html`` page; each saved template comes with its page
        count (1 when the layout JSON has no pages list).

    Raises:
        HTTPException: 401 if not logged in.
    """
    tpls = (
        db.query(models.LayoutTemplate)
        .filter(models.LayoutTemplate.user_id == current_user.id)
        .order_by(models.LayoutTemplate.created_at.desc())
        .all()
    )
    # 각 템플릿의 페이지 수(간단 파싱)
    import json as _json
    items = []
    for t in tpls:
        pages = 1
        try:
            data = _json.loads(t.content_blocks or "{}")
            if isinstance(data, dict) and isinstance(data.get("pages"), list):
                pages = len(data["pages"]) or 1
        except Exception:
            pass
        items.append({"t": t, "pages": pages})
    from app.services.starter_templates import list_starters
    return templates.TemplateResponse(
        request,
        "my_templates.html",
        {"request": request, "current_user": current_user, "items": items, "starters": list_starters()},
    )


@router.get("/me/templates/{template_id}/thumb.png")
def my_template_thumb(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """저장된 레이아웃의 첫 페이지를 도식 썸네일(PNG)로 — 소유자만."""
    tmpl = (
        db.query(models.LayoutTemplate)
        .filter_by(id=template_id, user_id=current_user.id)
        .first()
    )
    if not tmpl:
        raise HTTPException(404, "Not found")

    import hashlib
    from pathlib import Path

    sig = hashlib.md5((tmpl.content_blocks or "").encode("utf-8")).hexdigest()[:10]
    cache_dir = Path("app/static/og_cache")
    cache = cache_dir / f"tmpl-{template_id}-{sig}.png"
    headers = {"Cache-Control": "private, max-age=3600"}
    try:
        if cache.exists():
            data = cache.read_bytes()
        else:
            from app.services.og_image import render_layout_thumbnail

            data = render_layout_thumbnail(tmpl.content_blocks or "", width=600)
            cache_dir.mkdir(parents=True, exist_ok=True)
            for old in cache_dir.glob(f"tmpl-{template_id}-*.png"):
                if old != cache:
                    try:
                        old.unlink()
                    except OSError:
                        pass
            cache.write_bytes(data)
    except Exception:  # noqa: BLE001 — 썸네일 실패가 사이트를 깨지 않도록
        import logging

        logging.getLogger(__name__).exception("레이아웃 썸네일 생성 실패 id=%s", template_id)
        raise HTTPException(500, "thumb render failed")
    return Response(content=data, media_type="image/png", headers=headers)


@router.post("/me/templates/{template_id}/delete")
def delete_my_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Delete one of the user's saved layout templates.

    Ids that do not exist or belong to someone else are ignored.

    Args:
        template_id: Id of the template.
        db: Database session.
        current_user: The logged-in user.

    Returns:
        A 303 redirect to ``/me/templates``.

    Raises:
        HTTPException: 401 if not logged in.
    """
    tpl = db.query(models.LayoutTemplate).filter_by(id=template_id, user_id=current_user.id).first()
    if tpl:
        db.delete(tpl)
        db.commit()
    return RedirectResponse("/me/templates", status_code=303)


# ─────────────────────────────────────────────
# 시리즈/컬렉션 (/series/{slug}) — series:<이름> 태그로 묶인 글
# ─────────────────────────────────────────────
@router.get("/series/{slug}", response_class=HTMLResponse)
def series_page(
    slug: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user_optional),
):
    """Render a series: the visible posts tagged ``series:<slug>``, oldest first.

    Magazine (TipTap) posts without an image get their generated cover as
    thumbnail; the first thumbnail becomes the series cover and Open Graph
    image.

    Args:
        slug: Series name as used in the tag; matched case-insensitively.
        request: The incoming request.
        db: Database session.
        current_user: The logged-in user, or None.

    Returns:
        The ``series.html`` page.

    Raises:
        HTTPException: 404 if no such series tag exists.
    """
    name = ("series:" + (slug or "").strip()).lower()
    tag = db.query(models.Tag).filter(func.lower(models.Tag.name) == name).first()
    if not tag:
        raise HTTPException(status_code=404, detail="시리즈를 찾을 수 없습니다.")

    label = tag.name.split(":", 1)[1].strip() if ":" in tag.name else tag.name

    query = (
        db.query(models.BoardPost)
        .join(models.BoardPost.tags)
        .filter(models.Tag.id == tag.id)
        .options(joinedload(models.BoardPost.user), joinedload(models.BoardPost.stats))
    )
    if current_user:
        query = query.filter(
            or_(models.BoardPost.is_private == False, models.BoardPost.user_id == current_user.id)  # noqa: E712
        )
    else:
        query = query.filter(models.BoardPost.is_private == False)  # noqa: E712

    # 시리즈는 읽는 순서(오래된 → 최신)
    posts = query.order_by(models.BoardPost.created_at.asc()).all()
    cover_image = None
    author = None
    for p in posts:
        p.view_count = p.stats.views if p.stats else 0
        p.thumbnail = extract_first_image(p.content_html or p.content or "")
        # 매거진(tiptap) 레이아웃이면 대표 이미지가 없어도 커버를 자동 생성
        if not p.thumbnail and p.editor_type == "tiptap" and p.content_blocks:
            p.thumbnail = f"/board/{p.id}/cover.png"
        if cover_image is None and p.thumbnail:
            cover_image = p.thumbnail
        if author is None and p.user:
            author = p.user

    og_image = cover_image
    if og_image and og_image.startswith("/"):
        og_image = str(request.base_url).rstrip("/") + og_image

    return templates.TemplateResponse(
        request,
        "series.html",
        {
            "request": request,
            "current_user": current_user,
            "label": label,
            "slug": slug,
            "posts": posts,
            "total": len(posts),
            "cover_image": cover_image,
            "author": author,
            "meta_description": f"시리즈 '{label}' — {len(posts)}편",
            "og_title": f"시리즈: {label}",
            "og_image": og_image,
        },
    )


# ─────────────────────────────────────────────
# 블로그 디렉터리 (/explore) — 공개글이 있는 블로그 탐색
# ─────────────────────────────────────────────
@router.get("/explore", response_class=HTMLResponse)
def explore(
    request: Request,
    page: int = 1,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user_optional),
):
    """Render the blog directory and popular tags.

    Lists users with a handle and at least one public post, 24 per page,
    ordered by number of public posts, plus the 24 most used tags.

    Args:
        request: The incoming request.
        page: Page number, clamped to the valid range.
        db: Database session.
        current_user: The logged-in user, or None.

    Returns:
        The ``explore.html`` page.
    """
    size = 24
    page = max(1, page)

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

    total_blogs = q.count()
    total_pages = max(1, (total_blogs + size - 1) // size)
    page = min(page, total_pages)

    rows = (
        q.order_by(func.count(models.BoardPost.id).desc(), models.User.id.asc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    blogs = [{"user": u, "post_count": n} for (u, n) in rows]

    # 두 번째 탐색 축: 인기 태그
    popular_tags = (
        db.query(models.Tag)
        .filter(models.Tag.count > 0)
        .order_by(models.Tag.count.desc(), models.Tag.name.asc())
        .limit(24)
        .all()
    )

    return templates.TemplateResponse(
        request,
        "explore.html",
        {
            "request": request,
            "blogs": blogs,
            "popular_tags": popular_tags,
            "current_user": current_user,
            "current_page": page,
            "total_pages": total_pages,
            "total_blogs": total_blogs,
            "meta_description": "다양한 주제의 블로그를 둘러보세요 — 활동 중인 블로그 모음",
            "og_title": "Explore Blogs",
        },
    )


# ─────────────────────────────────────────────
# robots.txt / sitemap.xml (퍼블리시: 검색 노출)
# ─────────────────────────────────────────────
@router.get("/robots.txt")
def robots_txt(request: Request):
    """Serve ``robots.txt``.

    Allows crawling except the admin, dashboard, auth and editor paths, and
    points to the sitemap.

    Args:
        request: The incoming request, used for the sitemap URL.

    Returns:
        A ``text/plain`` response.
    """
    base = str(request.base_url).rstrip("/")
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin\n"
        "Disallow: /me\n"
        "Disallow: /auth\n"
        "Disallow: /board/new\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )
    return Response(content=body, media_type="text/plain")


@router.get("/sitemap.xml")
def sitemap_xml(request: Request, db: Session = Depends(get_db)):
    """Serve ``sitemap.xml``.

    Lists the home and explore pages, up to 2,000 public posts (with their
    last update date), every blog home and the feeds of tags in use.

    Args:
        request: The incoming request, used for absolute URLs.
        db: Database session.

    Returns:
        An ``application/xml`` response.
    """
    from xml.sax.saxutils import escape

    base = str(request.base_url).rstrip("/")

    def entry(loc: str, lastmod=None) -> str:
        """Build one sitemap ``<url>`` element.

        Args:
            loc: Absolute URL of the page; XML-escaped.
            lastmod: Optional datetime; its date is written as ``<lastmod>``.

        Returns:
            The ``<url>...</url>`` XML string.
        """
        s = f"<url><loc>{escape(loc)}</loc>"
        if lastmod is not None:
            s += f"<lastmod>{lastmod.date().isoformat()}</lastmod>"
        s += "</url>"
        return s

    parts = [entry(f"{base}/"), entry(f"{base}/explore")]

    # 공개 글 (숨김 글은 전역 필터로 자동 제외) — 최종 수정일 포함
    posts = (
        db.query(models.BoardPost.id, models.BoardPost.updated_at)
        .filter(models.BoardPost.is_private == False)  # noqa: E712
        .order_by(models.BoardPost.id.desc())
        .limit(2000)
        .all()
    )
    parts += [entry(f"{base}/board/{pid}", updated) for (pid, updated) in posts]

    # 블로그 홈
    handles = db.query(models.User.handle).filter(models.User.handle.isnot(None)).all()
    parts += [entry(f"{base}/@{h}") for (h,) in handles if h]

    # 실제 사용 중인 태그 피드
    tags = db.query(models.Tag.slug).filter(models.Tag.count > 0).order_by(models.Tag.count.desc()).all()
    parts += [entry(f"{base}/tags/{slug}") for (slug,) in tags if slug]

    body = '<?xml version="1.0" encoding="UTF-8"?>\n'
    body += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    body += "".join(parts)
    body += "</urlset>"
    return Response(content=body, media_type="application/xml")


@router.get("/posts/new")
def legacy_posts_new_redirect():
    """Redirect the old ``/posts/new`` URL to the editor at ``/board/new`` (307)."""
    return RedirectResponse("/board/new", status_code=307)


@router.get("/posts/{post_id}", response_class=HTMLResponse)
def read_post(
    request: Request,
    post_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user_optional),
):
    """Render a post at the legacy ``/posts/{post_id}`` URL.

    Args:
        request: The incoming request.
        post_id: Id of the post.
        db: Database session.
        current_user: The logged-in user, or None.

    Returns:
        The ``post_detail.html`` page; a 302 redirect home if the post does not
        exist, or a 303 redirect home if it is private and the viewer is not
        its author.
    """
    post = db.query(models.BoardPost).filter(models.BoardPost.id == post_id).first()
    if not post:
        return RedirectResponse("/", status_code=302)

    if post.is_private:
        if not current_user or post.user_id != current_user.id:
            return RedirectResponse("/", status_code=303)

    return templates.TemplateResponse(
        request,
        "post_detail.html",
        {
            "request": request,
            "post": post,
            "current_user": current_user,
        },
    )
