"""Limits on a user's category tree: how many, how deep, and how long the texts.

Without them one account could nest thousands of categories or store huge
names, and every guest page that lists categories would carry the cost. The
checks take the user's own categories (at most ``CATEGORY_MAX_PER_USER``
rows), walk the tree with loops rather than recursion (any stored depth is
safe), and return a message for the page, or None when the change is allowed.

Names and descriptions are compared and measured after NFC normalization:
Hangul typed or pasted on macOS can arrive decomposed (NFD), one syllable as
two or three code points, so without it a Korean name would hit the length
limit early and could duplicate an existing name that looks the same.
"""
from __future__ import annotations

import unicodedata
from collections import defaultdict
from typing import Iterable, Optional

from app import models
from app.config import settings


def clean_category_text(value: Optional[str]) -> str:
    """Return ``value`` NFC-normalized and stripped ("" for None)."""
    return unicodedata.normalize("NFC", value or "").strip()


def category_text_limits() -> dict[str, int]:
    """Return the name and description limits in characters (for form ``maxlength``)."""
    return {"name": settings.CATEGORY_NAME_MAX_CHARS, "description": settings.CATEGORY_DESCRIPTION_MAX_CHARS}


def category_text_error(name: str, description: str = "") -> Optional[str]:
    """Check a cleaned name and description against the length limits.

    Args:
        name: The name, already passed through :func:`clean_category_text`.
        description: The description, cleaned the same way ("" when none).

    Returns:
        A message when one of them is too long, else None.
    """
    if len(name) > settings.CATEGORY_NAME_MAX_CHARS:
        return f"카테고리 이름은 {settings.CATEGORY_NAME_MAX_CHARS}자까지 쓸 수 있습니다."
    if len(description) > settings.CATEGORY_DESCRIPTION_MAX_CHARS:
        return f"카테고리 설명은 {settings.CATEGORY_DESCRIPTION_MAX_CHARS}자까지 쓸 수 있습니다."
    return None


def category_count_error(existing: int) -> Optional[str]:
    """Return a message when a user who has ``existing`` categories may not add another."""
    if existing >= settings.CATEGORY_MAX_PER_USER:
        return f"카테고리는 {settings.CATEGORY_MAX_PER_USER}개까지 만들 수 있습니다."
    return None


def _level(parent_of: dict[int, Optional[int]], category_id: int) -> int:
    """Return the level of ``category_id`` (a top-level category is 1).

    Follows parents with a loop; a parent that is not in ``parent_of`` (another
    user's or deleted) or a cycle ends the walk.
    """
    level, seen, current = 0, set(), category_id
    while current is not None and current in parent_of and current not in seen:
        seen.add(current)
        level += 1
        current = parent_of[current]
    return level


def _subtree_levels(children: dict[int, list[int]], category_id: int) -> int:
    """Return how many levels the subtree under ``category_id`` spans (1 for a leaf)."""
    levels, frontier, seen = 0, [category_id], set()
    while frontier:
        levels += 1
        seen.update(frontier)
        frontier = [child for node in frontier for child in children.get(node, ()) if child not in seen]
    return levels


def category_placement_error(
    categories: Iterable[models.BoardCategory],
    category_id: Optional[int],
    new_parent_id: Optional[int],
) -> Optional[str]:
    """Check that a category and its subtree fit under a parent within ``CATEGORY_MAX_DEPTH``.

    Args:
        categories: All of the user's categories.
        category_id: The category being moved, or None for a new one (a
            subtree of one level).
        new_parent_id: The parent to place it under, or None for top level.

    Returns:
        A message when the tree would get deeper than allowed, else None.
    """
    parent_of: dict[int, Optional[int]] = {}
    children: dict[int, list[int]] = defaultdict(list)
    for category in categories:
        parent_of[category.id] = category.parent_id
        if category.parent_id is not None:
            children[category.parent_id].append(category.id)
    above = _level(parent_of, new_parent_id) if new_parent_id is not None else 0
    height = _subtree_levels(children, category_id) if category_id is not None else 1
    if above + height > settings.CATEGORY_MAX_DEPTH:
        return f"카테고리는 {settings.CATEGORY_MAX_DEPTH}단계까지 만들 수 있습니다."
    return None
