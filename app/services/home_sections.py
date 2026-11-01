"""Which posts the portal home shows in each section, and what to call them.

Above the post list the home has three showcase sections: cover stories
(the most read posts that have an image), "요즘 많이 읽는 글" (the next most
read) and the magazine shelf (page-layout posts with an image). A post appears
in at most one of them, and the list below leaves out what they already show.

A post without a title of its own is labelled with the start of its body; a
post with neither a title nor any body text is left off the home altogether.
"""
import json
from dataclasses import dataclass, field
from typing import Optional, Protocol, Sequence

PLACEHOLDER_TITLES = {"untitled", "제목 없음"}
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


def page_count(content_blocks: Optional[str]) -> int:
    """Count the pages of a magazine layout.

    Args:
        content_blocks: The stored layout JSON (v3 ``{"pages": [...]}``, an
            older single page, or a bare block list).

    Returns:
        The number of pages, 1 for the older single-page formats, and 0 when
        there is no layout or it is not valid JSON.
    """
    try:
        data = json.loads(content_blocks or "")
    except (TypeError, ValueError):
        return 0
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
