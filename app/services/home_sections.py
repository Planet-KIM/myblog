"""Which posts the portal home shows in each section, and what to call them.

Above the post list the home has three showcase sections: cover stories
(the most read posts that have an image), "요즘 많이 읽는 글" (the next most
read) and the magazine shelf (page-layout posts with an image). A post appears
in at most one of them, and the list below leaves out what they already show.

A post without a title of its own is labelled with the start of its body; a
post with neither a title nor any body text is left off the home altogether.
The title rules here are shared with the post pages, feeds and meta tags,
including whether a post page's header prints the title at all.
"""
import html
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, Sequence

from app.services.bilingual import pick_language
from app.services.content_blocks import first_heading_html, parse as parse_content_blocks
from app.services.plain_text import strip_tags

PLACEHOLDER_TITLES = {"untitled", "제목 없음"}
UNTITLED_LABEL = "제목 없음"
FALLBACK_TITLE_CHARS = 60
COVER_LIMIT = 3
POPULAR_LIMIT = 2
MAGAZINE_LIMIT = 3


class LabelledPost(Protocol):
    """A post as the home sees it once the router has decorated it."""

    id: int
    thumbnail: Optional[str]
    display_title: Optional[str]
    has_own_title: bool
    page_count: int


def own_title(title: Optional[str], show_title: Optional[bool] = True) -> Optional[str]:
    """Return the title the author gave the post, if there is a real one.

    Args:
        title: The stored title.
        show_title: False when the author hid the title on the post page.

    Returns:
        The trimmed title, or None when it is empty, hidden, or an editor
        placeholder such as "Untitled".
    """
    cleaned = (title or "").strip()
    if show_title is False or not cleaned or cleaned.lower() in PLACEHOLDER_TITLES:
        return None
    return cleaned


def strip_leading_title(text: str, title: Optional[str]) -> str:
    """Drop ``title`` from the start of ``text`` (magazine bodies open with their title).

    Args:
        text: Plain-text preview of the body.
        title: The post's title.

    Returns:
        ``text`` without the title and the separators after it, or ``text``
        unchanged when it does not start with the title.
    """
    if title and text.startswith(title):
        return text[len(title):].lstrip(" ·:—-")
    return text


def fallback_title(preview: str, limit: int = FALLBACK_TITLE_CHARS) -> Optional[str]:
    """Make a title from the start of the body for a post without one.

    Args:
        preview: Plain-text preview of the body.
        limit: Longest title to return, in characters, before cutting at a word.

    Returns:
        The text itself when short enough, else its first ``limit`` characters
        cut back to a word boundary with "…"; None when there is no text.
    """
    text = preview.rstrip(".").strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,·") + "…"


def title_label(title: Optional[str]) -> str:
    """Return the title to print for a post: its own title, else ``UNTITLED_LABEL``.

    Used where there is no body text to name the post after (navigation
    links, page titles, feeds), so a stored placeholder such as "Untitled"
    reads as "제목 없음" instead.
    """
    return own_title(title) or UNTITLED_LABEL


def _comparable_text(markup: str) -> str:
    """Return ``markup`` as plain text for comparing titles.

    Tags are removed, entities decoded, ``{{ko||en}}`` pairs reduced to one
    language, Hangul NFC-normalized, whitespace collapsed and case folded.
    """
    text = pick_language(html.unescape(strip_tags(markup)))
    return " ".join(unicodedata.normalize("NFC", text).split()).casefold()


def layout_opens_with_title(layout: Any, title: Optional[str]) -> bool:
    """Tell whether a magazine layout's first page opens with the post's title.

    Magazine covers usually print the title in a large heading block, so a
    header title above the viewer would show it twice in a row.

    Args:
        layout: The decoded content_blocks value the viewer draws, or None.
        title: The stored title.

    Returns:
        True when the topmost heading on the first page reads the same as the
        post's own title; False for placeholder titles or no heading.
    """
    own = own_title(title)
    heading = first_heading_html(layout) if layout is not None else ""
    return bool(own and heading) and _comparable_text(heading) == _comparable_text(own)


def header_shows_title(title: Optional[str], show_title: Optional[bool], layout: Any = None) -> bool:
    """Decide whether a post page's header prints the title.

    The header keeps its ``<h1>`` either way (screen readers and search
    engines read it); this only decides whether readers see it.

    Args:
        title: The stored title.
        show_title: False when the author turned the title off.
        layout: The decoded layout the page's viewer draws, or None for a
            post shown as HTML.

    Returns:
        False when the author turned the title off or the layout's first page
        already opens with it, else True.
    """
    return show_title is not False and not layout_opens_with_title(layout, title)


@dataclass(frozen=True)
class CardLabel:
    """What a post card shows as its title and its preview line.

    Attributes:
        title: The post's own title, else the start of its body; None when
            it has neither.
        has_own_title: True when ``title`` is the author's title.
        preview: The body text without the title it opens with; "" when the
            title was made from the body (it would only repeat it).
    """

    title: Optional[str]
    has_own_title: bool
    preview: str


def label_card(title: Optional[str], show_title: Optional[bool], preview: str) -> CardLabel:
    """Decide a post card's title and preview line.

    Magazine bodies open with their title, so the preview drops it; a post
    without a real title is named after the start of its body instead.

    Args:
        title: The stored title.
        show_title: False when the author hid the title on the post page.
        preview: Plain-text preview of the body ("" when it has no text).

    Returns:
        The card's title, whether it is the author's, and its preview line.
    """
    own = own_title(title, show_title)
    if own:
        return CardLabel(own, True, strip_leading_title(preview, own))
    return CardLabel(fallback_title(preview), False, "")


def page_count(content_blocks: Optional[str]) -> int:
    """Count the pages of a magazine layout.

    Args:
        content_blocks: The stored layout JSON (v3 ``{"pages": [...]}``, an
            older single page, or a bare block list).

    Returns:
        The number of pages, 1 for the older single-page formats, and 0 when
        there is no layout or it cannot be decoded.
    """
    data = parse_content_blocks(content_blocks)
    if isinstance(data, dict) and isinstance(data.get("pages"), list):
        return len(data["pages"])
    if (isinstance(data, dict) and isinstance(data.get("blocks"), list)) or (isinstance(data, list) and data):
        return 1
    return 0


@dataclass
class HomeShowcase:
    """The posts picked for the home's showcase sections.

    Attributes:
        covers: Cover stories, shown as a carousel.
        popular: "요즘 많이 읽는 글".
        magazines: The magazine shelf.
    """

    covers: list = field(default_factory=list)
    popular: list = field(default_factory=list)
    magazines: list = field(default_factory=list)

    @property
    def shown_ids(self) -> set[int]:
        """Ids of every post the showcase sections show."""
        return {p.id for p in self.covers + self.popular + self.magazines}


def pick_showcase(most_read: Sequence[LabelledPost], magazines: Sequence[LabelledPost]) -> HomeShowcase:
    """Split candidate posts into the showcase sections, each post at most once.

    Args:
        most_read: Posts ordered by views, most read first.
        magazines: Magazine posts, newest first.

    Returns:
        Up to ``COVER_LIMIT`` covers (an image and a real title), then up to
        ``POPULAR_LIMIT`` of the next most read posts that have something to
        call them, then up to ``MAGAZINE_LIMIT`` magazines with an image.
    """
    covers = [p for p in most_read if p.thumbnail and p.has_own_title][:COVER_LIMIT]
    taken = {p.id for p in covers}
    popular = [p for p in most_read if p.id not in taken and p.display_title][:POPULAR_LIMIT]
    taken |= {p.id for p in popular}
    shelf = [
        p for p in magazines
        if p.id not in taken and p.thumbnail and p.display_title and p.page_count
    ][:MAGAZINE_LIMIT]
    return HomeShowcase(covers=covers, popular=popular, magazines=shelf)


def list_posts(candidates: Sequence[LabelledPost], skip_ids: set[int], limit: int) -> list:
    """Pick the posts for the home's list below the showcases.

    Args:
        candidates: Posts in the order the list should show them.
        skip_ids: Posts already shown above.
        limit: Most posts to return.

    Returns:
        Up to ``limit`` candidates that are not in ``skip_ids`` and have
        something to call them.
    """
    return [p for p in candidates if p.id not in skip_ids and p.display_title][:limit]
