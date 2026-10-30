"""Links between posts: post cards in a post body and the post picker's search.

A Markdown post shows a card for every paragraph that holds nothing but one
link to a post on this site (``/board/<id>``, or that URL with this site's
host); a link inside a sentence stays a plain link. A magazine post places a
card as its own block (``type: "postcard"`` with ``postId``) whose ``content``
is replaced with the current card on every view.

Cards only show posts the viewer may read (public, or the viewer's own);
anything else is rendered as an unavailable card by the caller.

The other direction, "이 글을 언급한 글" (backlinks), lists the readable posts
that link to a post: by a card, a card block or a plain link in a sentence.
"""
import html as html_module
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable, Iterator, Optional
from urllib.parse import urlsplit

from sqlalchemy import case, or_
from sqlalchemy.orm import Query, Session, joinedload

from app import models
from app.services.bilingual import has_pairs
from app.services.plain_text import markdown_to_plain
from app.services.post_media import extract_first_image
from app.services.reading_time import estimate_reading_minutes
from app.services.sanitize import safe_url

CARD_BLOCK_TYPE = "postcard"
CARD_PREVIEW_CHARS = 160
PICKER_LIMIT = 8
BACKLINK_LIMIT = 6
BACKLINK_SCAN = 100   # 후보(본문에 /board/<id> 가 들어간 글)를 최신순으로 이만큼만 살핀다

_POST_PATH = re.compile(r"^/board/(\d+)/?$")
_POST_PATH_ANYWHERE = re.compile(r"/board/(\d+)")
# 링크 하나만 담은 문단 (링크 앞뒤 공백, 끝의 <br> 하나는 허용)
_CARD_PARAGRAPH = re.compile(
    r"<p\b[^>]*>\s*<a\b(?P<attrs>[^>]*)>(?:(?!</a>).)*</a>\s*(?:<br\s*/?>\s*)?</p>",
    re.S | re.I,
)
_HREF = re.compile(r"""\bhref\s*=\s*["']([^"']*)["']""", re.I)
_MARKDOWN_LINK = re.compile(r"\]\(\s*<?([^)\s>]+)")


@dataclass
class PostCard:
    """What a post card shows about a linked post.

    Attributes:
        id: The linked post.
        title: Its title (Korean side for bilingual posts).
        title_en: English title of a bilingual post, else None.
        preview: Start of its body text.
        preview_en: English preview of a bilingual post, else None.
        thumbnail: Its first image URL (checked), or "".
        author: Author name to show.
        date: When it was written.
        reading_minutes: Reading time in the default language.
        is_private: Whether only its author can read it.
    """

    id: int
    title: str
    title_en: Optional[str]
    preview: str
    preview_en: Optional[str]
    thumbnail: str
    author: str
    date: datetime
    reading_minutes: int
    is_private: bool


def post_id_from_href(href: str, hosts: Iterable[str]) -> Optional[int]:
    """Tell which post a link points to.

    Args:
        href: Link target as written (HTML entities allowed).
        hosts: Host names (no port) that count as this site.

    Returns:
        The post id for ``/board/<id>`` (a query or fragment is ignored), or
        for that path on an http(s) URL whose host name is in ``hosts`` (any
        port); else None.
    """
    parts = urlsplit(html_module.unescape(href or "").strip())
    if parts.scheme and parts.scheme not in ("http", "https"):
        return None
    if parts.netloc and parts.hostname not in {h.lower() for h in hosts if h}:
        return None
    match = _POST_PATH.match(parts.path)
    return int(match.group(1)) if match else None


def _paragraph_post_id(match: re.Match, hosts: Iterable[str]) -> Optional[int]:
    """Post id of a link-only paragraph matched by _CARD_PARAGRAPH, or None."""
    href = _HREF.search(match.group("attrs"))
    return post_id_from_href(href.group(1), hosts) if href else None


def card_paragraph_ids(html: str, hosts: Iterable[str]) -> list[int]:
    """List the posts that link-only paragraphs in ``html`` point to.

    Args:
        html: Post body HTML.
        hosts: Host names that count as this site.

    Returns:
        Post ids in order of first appearance, without repeats.
    """
    ids = (_paragraph_post_id(m, hosts) for m in _CARD_PARAGRAPH.finditer(html or ""))
    return list(dict.fromkeys(i for i in ids if i is not None))


def replace_card_paragraphs(html: str, hosts: Iterable[str], render: Callable[[int], str]) -> str:
    """Replace every link-only paragraph that points to a post with its card.

    Args:
        html: Post body HTML (already sanitized; the cards are not).
        hosts: Host names that count as this site.
        render: Returns the card HTML for a post id.

    Returns:
        The HTML with those paragraphs replaced; other paragraphs untouched.
    """
    def card_or_paragraph(match: re.Match) -> str:
        """The card for a matched paragraph, or the paragraph itself."""
        post_id = _paragraph_post_id(match, hosts)
        return render(post_id) if post_id is not None else match.group(0)

    return _CARD_PARAGRAPH.sub(card_or_paragraph, html or "")


def _blocks(data) -> Iterator[dict]:
    """Yield every block dict of a content_blocks structure (v3, a page list or one page)."""
    if isinstance(data, dict) and isinstance(data.get("pages"), list):
        pages = data["pages"]
    elif isinstance(data, list):
        pages = data
    else:
        pages = [data]
    for page in pages:
        if isinstance(page, dict):
            for block in page.get("blocks") or []:
                if isinstance(block, dict):
                    yield block


def _card_block_id(block: dict) -> Optional[int]:
    """Post id of a magazine card block, or None for any other block."""
    if block.get("type") != CARD_BLOCK_TYPE:
        return None
    try:
        return int(block.get("postId"))
    except (TypeError, ValueError):
        return None


def card_block_ids(raw: str) -> list[int]:
    """List the posts that a magazine post's card blocks point to.

    Args:
        raw: content_blocks JSON.

    Returns:
        Post ids in order, without repeats; empty when the JSON is invalid.
    """
    try:
        data = json.loads(raw or "")
    except (TypeError, ValueError):
        return []
    ids = (_card_block_id(b) for b in _blocks(data))
    return list(dict.fromkeys(i for i in ids if i is not None))


def refresh_card_blocks(raw: str, render: Callable[[int], str]) -> str:
    """Put the current card into every card block of a magazine post.

    Args:
        raw: content_blocks JSON.
        render: Returns the card HTML for a post id.

    Returns:
        The JSON with each card block's ``content`` replaced (other blocks
        untouched), or ``raw`` itself when it is not valid JSON.
    """
    try:
        data = json.loads(raw or "")
    except (TypeError, ValueError):
        return raw
    for block in _blocks(data):
        post_id = _card_block_id(block)
        if post_id is not None:
            block["content"] = render(post_id)
    return json.dumps(data, ensure_ascii=False)


def visible_posts(db: Session, viewer: Optional[models.User]) -> Query:
    """Query the posts ``viewer`` may read: public ones and their own.

    Args:
        db: Database session.
        viewer: The logged-in user, or None.

    Returns:
        A BoardPost query (hidden posts are already left out by the model).
    """
    query = db.query(models.BoardPost)
    if viewer:
        return query.filter(or_(models.BoardPost.is_private == False, models.BoardPost.user_id == viewer.id))  # noqa: E712
    return query.filter(models.BoardPost.is_private == False)  # noqa: E712


def _author_name(post: models.BoardPost) -> str:
    """Name to show for a post's author: display name, @handle or the e-mail's local part."""
    user = post.user
    if user and (user.display_name or user.handle):
        return user.display_name or f"@{user.handle}"
    return (post.author or "").split("@")[0]


def _preview(source: str, title: Optional[str], lang: str = "ko") -> str:
    """Start of the body text, without the title when the body opens with it (magazine posts do)."""
    text = markdown_to_plain(source, max_len=None, lang=lang)
    if title and text.startswith(title):
        text = text[len(title):].lstrip(" ·:—-")
    return text[:CARD_PREVIEW_CHARS] + ("..." if len(text) > CARD_PREVIEW_CHARS else "")


def build_post_card(post: models.BoardPost, title_en: Optional[str] = None) -> PostCard:
    """Collect what a card shows about ``post``.

    Args:
        post: The linked post (its ``user`` is read).
        title_en: English title when the card should carry both languages;
            the English preview is added only then.

    Returns:
        The card data.
    """
    source = post.content_html or post.content or ""
    preview = _preview(source, post.title)
    preview_en = None
    if title_en and has_pairs(source):
        preview_en = _preview(source, title_en, "en")
    return PostCard(
        id=post.id,
        title=post.title or "제목 없음",
        title_en=title_en if title_en and title_en != post.title else None,
        preview=preview,
        preview_en=preview_en if preview_en != preview else None,
        thumbnail=safe_url(extract_first_image(source)),
        author=_author_name(post),
        date=post.created_at,
        reading_minutes=estimate_reading_minutes(source),
        is_private=bool(post.is_private),
    )


def load_linked_posts(db: Session, ids: Iterable[int], viewer: Optional[models.User]) -> dict[int, models.BoardPost]:
    """Load the linked posts that ``viewer`` may read.

    Args:
        db: Database session.
        ids: Post ids from cards.
        viewer: The logged-in user, or None.

    Returns:
        Post id -> post (with its user loaded); unreadable or missing posts
        are left out.
    """
    ids = list(ids)
    if not ids:
        return {}
    posts = (
        visible_posts(db, viewer)
        .options(joinedload(models.BoardPost.user))
        .filter(models.BoardPost.id.in_(ids))
        .all()
    )
    return {p.id: p for p in posts}


def linked_post_ids(post: models.BoardPost, hosts: Iterable[str]) -> set[int]:
    """Every post that ``post`` links to: cards, card blocks and plain links.

    Args:
        post: The linking post (its HTML body, Markdown body and content_blocks
            are read).
        hosts: Host names that count as this site.

    Returns:
        The linked post ids, without ``post`` itself.
    """
    hrefs = _HREF.findall(post.content_html or "") + _HREF.findall(post.content or "")
    hrefs += _MARKDOWN_LINK.findall(post.content or "")
    ids = {post_id_from_href(h, hosts) for h in hrefs} | set(card_block_ids(post.content_blocks))
    ids.discard(None)
    ids.discard(post.id)
    return ids


def linking_posts(
    db: Session,
    post_id: int,
    viewer: Optional[models.User],
    hosts: Iterable[str],
    limit: int = BACKLINK_LIMIT,
) -> list[models.BoardPost]:
    """Find the posts that link to ``post_id`` ("이 글을 언급한 글").

    A text search narrows the candidates; each is then checked link by link
    (so ``/board/42`` does not count for ``/board/4``).

    Args:
        db: Database session.
        post_id: The post being read.
        viewer: The reader; only posts they may read are listed.
        hosts: Host names that count as this site.
        limit: Maximum number of posts.

    Returns:
        Linking posts (with their user loaded), newest first.
    """
    needle = f"%/board/{post_id}%"
    candidates = (
        visible_posts(db, viewer)
        .options(joinedload(models.BoardPost.user))
        .filter(models.BoardPost.id != post_id)
        .filter(
            or_(
                models.BoardPost.content_html.like(needle),
                models.BoardPost.content.like(needle),
                models.BoardPost.content_blocks.like(needle),
                models.BoardPost.content_blocks.like(f'%"postId":{post_id}%'),
                models.BoardPost.content_blocks.like(f'%"postId": {post_id}%'),
            )
        )
        .order_by(models.BoardPost.created_at.desc())
        .limit(BACKLINK_SCAN)
        .all()
    )
    return [p for p in candidates if post_id in linked_post_ids(p, hosts)][:limit]


def search_link_targets(
    db: Session,
    viewer: models.User,
    q: str = "",
    exclude_id: Optional[int] = None,
    limit: int = PICKER_LIMIT,
) -> list[dict]:
    """Find posts to link to, for the editors' post picker.

    Args:
        db: Database session.
        viewer: The writer (only posts they may read are offered).
        q: Search text matched in title or body; a pasted post URL or
            ``/board/<id>`` finds that post. Empty lists the writer's own
            latest posts.
        exclude_id: Post being edited, left out of the results.
        limit: Maximum number of results.

    Returns:
        Posts whose title matches first, then newest first; dicts with
        ``id``, ``title``, ``author``, ``date`` (YYYY.MM.DD), ``private`` and
        ``mine``.
    """
    query = visible_posts(db, viewer).options(joinedload(models.BoardPost.user))
    if exclude_id:
        query = query.filter(models.BoardPost.id != exclude_id)
    q = (q or "").strip()
    linked = _POST_PATH_ANYWHERE.search(q)
    order = [models.BoardPost.created_at.desc()]
    if linked:
        query = query.filter(models.BoardPost.id == int(linked.group(1)))
    elif q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                models.BoardPost.title.ilike(like),
                models.BoardPost.content.ilike(like),
                models.BoardPost.content_html.ilike(like),
            )
        )
        order.insert(0, case((models.BoardPost.title.ilike(like), 0), else_=1))   # 제목에 들어간 글 먼저
    else:
        query = query.filter(models.BoardPost.user_id == viewer.id)
    posts = query.order_by(*order).limit(limit).all()
    return [
        {
            "id": p.id,
            "title": p.title or "제목 없음",
            "author": _author_name(p),
            "date": p.created_at.strftime("%Y.%m.%d"),
            "private": bool(p.is_private),
            "mine": p.user_id == viewer.id,
        }
        for p in posts
    ]
