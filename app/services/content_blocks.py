"""Read a magazine post's content_blocks JSON without ever raising.

content_blocks is stored as the browser sent it, so it can hold any JSON, or
text that is not JSON at all. Every reader decodes it with ``parse`` (None
instead of an exception, also for JSON nested too deeply for the decoder) and
walks it with ``iter_pages`` and ``iter_blocks``, which visit every place a
page or a block can sit in any stored format. The sanitizer therefore covers
every block that the post page's viewer (static/js/board_detail_magazine.js)
or the editor may draw, whichever format they pick.

Formats:
    v3, what the editor saves: ``{"v": 3, "pages": [{"cw", "ch", "blocks"}, ...]}``.
    v2, one page: ``{"v": 2, "cw", "ch", "blocks": [...]}``. The viewer also
        draws a document's top-level ``blocks`` when its ``pages`` is empty.
    v1, one page of bare blocks: ``[block, ...]``, saved without a canvas size
        (``legacy_canvas`` derives one from the blocks).
"""
import json
import math
from typing import Any, Iterator, Optional

# v1 레이아웃(캔버스 크기 없이 블록만 저장)의 캔버스: 가장 아래 블록 밑 여백 (v2 에디터가 남기던 값)
LEGACY_BOTTOM_MARGIN = 40


def parse(raw: Optional[str]) -> Any:
    """Decode content_blocks JSON.

    Args:
        raw: The stored JSON text.

    Returns:
        The decoded value, or None when ``raw`` is empty, not valid JSON or
        nested too deeply to decode.
    """
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError, RecursionError):
        return None


def dumps(data: Any) -> Optional[str]:
    """Encode a decoded content_blocks value back to compact JSON.

    A value that decoded fine can still be nested too deeply to encode when
    the call stack is already deeper, so that case returns None too.

    Args:
        data: A decoded content_blocks value.

    Returns:
        The JSON text (non-ASCII kept as is), or None when it cannot be encoded.
    """
    try:
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError, RecursionError):
        return None


def iter_pages(data: Any) -> Iterator[dict]:
    """Yield every dict that some reader may treat as a page.

    That is each dict in ``pages``, the top-level document itself (a v2 page,
    or the viewer's fallback when ``pages`` is empty) and, for a top-level
    list, each dict in it.

    Args:
        data: A decoded content_blocks value.

    Yields:
        Page dicts, in document order.
    """
    if isinstance(data, list):
        candidates = data
    elif isinstance(data, dict):
        pages = data.get("pages")
        candidates = (pages if isinstance(pages, list) else []) + [data]
    else:
        return
    for page in candidates:
        if isinstance(page, dict):
            yield page


def iter_block_lists(data: Any) -> Iterator[list]:
    """Yield every list that holds blocks.

    That is a top-level list (v1) and the ``blocks`` list of every page from
    ``iter_pages``; a ``blocks`` value that is not a list is skipped.

    Args:
        data: A decoded content_blocks value.

    Yields:
        The lists themselves, so callers may change them in place.
    """
    if isinstance(data, list):
        yield data
    for page in iter_pages(data):
        blocks = page.get("blocks")
        if isinstance(blocks, list):
            yield blocks


def _coordinate(value: Any) -> float:
    """Return a block coordinate as a finite float; numeric text is read, anything else is 0."""
    if isinstance(value, bool):
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def legacy_canvas(blocks: list) -> tuple[float, float]:
    """Return the canvas size of a v1 layout, which was saved without one.

    The same rule as legacyPage() in static/js/board_detail_magazine.js: the
    leftmost block's left margin is repeated right of the rightmost block,
    and ``LEGACY_BOTTOM_MARGIN`` is left below the lowest block (the editor
    of that time framed blocks the same way).

    Args:
        blocks: The v1 block list; entries that are not dicts are ignored.

    Returns:
        ``(width, height)``, with 0 for a side the blocks give no size for.
    """
    items = [b for b in blocks if isinstance(b, dict)]
    if not items:
        return 0.0, 0.0
    left = max(0.0, min(_coordinate(b.get("x")) for b in items))
    right = max(_coordinate(b.get("x")) + _coordinate(b.get("w")) for b in items)
    bottom = max(_coordinate(b.get("y")) + _coordinate(b.get("h")) for b in items)
    width = right + left
    return (width if width > 0 else 0.0), (bottom + LEGACY_BOTTOM_MARGIN if bottom > 0 else 0.0)


def has_layout(data: Any) -> bool:
    """Tell whether the post page's viewer draws ``data`` as pages.

    Mirrors the format check of static/js/board_detail_magazine.js: a v3
    document with at least one page, a v2 page (``v`` 2 or a ``cw``) with a
    ``blocks`` list, or a non-empty v1 block list. Anything else, such as an
    early TipTap document (``{"type": "doc", ...}``), draws nothing, so the
    post page shows the HTML body instead.

    Args:
        data: A decoded content_blocks value, as sanitized for the page.

    Returns:
        True when the viewer has pages to draw.
    """
    if isinstance(data, list):
        return bool(data)
    if not isinstance(data, dict):
        return False
    pages = data.get("pages")
    if data.get("v") == 3 and isinstance(pages, list) and pages:
        return True
    return (data.get("v") == 2 or bool(data.get("cw"))) and isinstance(data.get("blocks"), list)


def iter_blocks(data: Any) -> Iterator[dict]:
    """Yield every block dict in any stored format (see ``iter_block_lists``).

    Args:
        data: A decoded content_blocks value.

    Yields:
        Block dicts; entries that are not dicts are skipped.
    """
    for blocks in iter_block_lists(data):
        for block in blocks:
            if isinstance(block, dict):
                yield block
