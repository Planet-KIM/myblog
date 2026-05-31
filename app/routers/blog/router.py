from typing import Optional, List, Dict
from datetime import datetime, timedelta
import re
import html as html_module
import markdown
import copy

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_, func
from sqlalchemy.orm import Session, joinedload
from fastapi.templating import Jinja2Templates

from app import models
from app.config import settings
from app.database import get_db
from app.auth_utils import get_current_user_optional
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
from app.services.recommendations import get_curated_home_recommendations
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
    plain = markdown_to_plain(text or "", max_len=10000)
    char_count = len(re.sub(r"\s+", "", plain))
    return max(1, round(char_count / 350))


def count_toc_headings(text: str) -> int:
    if not text:
        return 0
    markdown_headings = re.findall(r"^\s{0,3}#{1,6}\s+.+$", text, flags=re.MULTILINE)
    html_headings = re.findall(r"<h[1-6][^>]*>.*?</h[1-6]>", text, flags=re.IGNORECASE | re.DOTALL)
    return len(markdown_headings) + len(html_headings)


def detect_post_type(text: str) -> str:
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
    plain = markdown_to_plain(text or "", max_len=3000)
    sentences = re.split(r"(?<=[\.\!\?。！？])\s+", plain)
    for sentence in sentences:
        cleaned = sentence.strip()
        if len(cleaned) >= 24:
            return cleaned
    return plain[:120].strip()


def extract_series_label(post: models.BoardPost) -> Optional[str]:
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

    HOME_LIMIT = 6
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

    visible_post_total = (
        visible_posts_query(with_options=False)
        .with_entities(func.count(models.BoardPost.id))
        .scalar()
        or 0
    )

    def enrich_post(post: models.BoardPost):
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
    for item in posts + board_posts:
        if item.id in seen_ids:
            continue
        enrich_post(item)
        seen_ids.add(item.id)

    viewer_key = str(current_user.id) if current_user else (request.client.host if request.client else "anon")
    available_layout_strategies = {
        "random": HOME_LAYOUT_STRATEGY_PER_REQUEST_RANDOM,
        "stable": HOME_LAYOUT_STRATEGY_DAILY_STABLE_BY_VIEWER,
    }
    layout_mode = request.query_params.get("layout", "random").strip().lower()
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
    curated_recommendations = get_curated_home_recommendations()

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "posts": posts,
            "board_posts": board_posts,
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
            "curated_recommendations": curated_recommendations,
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


@router.get("/posts/new")
def legacy_posts_new_redirect():
    return RedirectResponse("/board/new", status_code=307)


@router.get("/posts/{post_id}", response_class=HTMLResponse)
def read_post(
    request: Request,
    post_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user_optional),
):
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
