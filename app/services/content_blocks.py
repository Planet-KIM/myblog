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
    v1, one page of bare blocks: ``[block, ...]``.
"""
import json
from typing import Any, Iterator, Optional


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
