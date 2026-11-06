"""Tree helpers for board categories: post-count roll-up, descendant lookup and ordering.

Categories form a parent/child tree through ``BoardCategory.parent_id``. Every
helper here tolerates broken data (a parent that no longer exists, or a cycle)
so that a bad row can never crash a page that lists categories.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping

from app import models


def _build_children_by_parent(
    categories: Iterable[models.BoardCategory],
) -> tuple[dict[int, models.BoardCategory], dict[int | None, list[int]]]:
    """Index categories by id and group child ids under their parent id.

    A category whose ``parent_id`` is missing or points to an id that is not in
    ``categories`` is treated as a root and filed under the ``None`` key.

    Args:
        categories: The categories to index. Consumed once.

    Returns:
        A ``(by_id, children_by_parent)`` pair: ``by_id`` maps each category id
        to its category, and ``children_by_parent`` maps a parent id (``None``
        for roots) to the ids of its children, sorted ascending.
    """
    category_list = list(categories)
    by_id = {category.id: category for category in category_list}
    children_by_parent: dict[int | None, list[int]] = defaultdict(list)

    for category in category_list:
        parent_id = category.parent_id if category.parent_id in by_id else None
        children_by_parent[parent_id].append(category.id)

    for child_ids in children_by_parent.values():
        child_ids.sort()

    return by_id, children_by_parent


def rollup_category_counts(
    categories: Iterable[models.BoardCategory],
    direct_counts: Mapping[int, int],
) -> dict[int, int]:
    """Add up post counts along the category tree, each category including its descendants.

    For example travel=0, bangkok=1, chiang-mai=0 (both under travel) gives
    travel=1. Walks with an explicit stack, so any depth works; in a cycle a
    category already on the current path adds only its own count.

    Args:
        categories: The categories of the tree.
        direct_counts: Posts filed directly in each category, by id.

    Returns:
        Total posts per category id, descendants included.
    """
    by_id, children_by_parent = _build_children_by_parent(categories)

    def direct(category_id: int) -> int:
        """The category's own post count."""
        return int(direct_counts.get(category_id, 0) or 0)

    # 재귀 대신 명시적 스택 (트리가 아무리 깊어도 RecursionError 없이 끝난다)
    memo: dict[int, int] = {}
    done = object()
    for start_id in sorted(by_id.keys()):
        if start_id in memo:
            continue
        stack = [(start_id, iter(children_by_parent.get(start_id, [])))]
        on_path = {start_id}
        totals = {start_id: direct(start_id)}
        while stack:
            node, children = stack[-1]
            child = next(children, done)
            if child is done:
                stack.pop()
                on_path.discard(node)
                memo[node] = totals.pop(node)
                if stack:
                    totals[stack[-1][0]] += memo[node]
            elif child in memo:
                totals[node] += memo[child]
            elif child in on_path:
                # 잘못된 순환 참조: 그 카테고리의 직계 글 수만 더한다
                totals[node] += direct(child)
            else:
                on_path.add(child)
                totals[child] = direct(child)
                stack.append((child, iter(children_by_parent.get(child, []))))
    return memo


def collect_descendant_category_ids(
    categories: Iterable[models.BoardCategory],
    root_category_id: int,
) -> list[int]:
    """
    선택된 카테고리 ID와 모든 하위 카테고리 ID를 함께 반환한다.
    예) travel 선택 시 [travel, bangkok, chiang-mai]
    """
    by_id, children_by_parent = _build_children_by_parent(categories)
    if root_category_id not in by_id:
        return [root_category_id]

    descendants: list[int] = []
    stack = [root_category_id]
    visited: set[int] = set()

    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        descendants.append(current)
        child_ids = children_by_parent.get(current, [])
        for child_id in reversed(child_ids):
            stack.append(child_id)

    return descendants


def order_categories_parent_first(
    categories: Iterable[models.BoardCategory],
) -> tuple[list[models.BoardCategory], dict[int, int]]:
    """Order categories parent first, each followed by its subtree (depth first, ids ascending).

    Categories no root reaches (a cycle) are placed afterwards at depth 0.

    Args:
        categories: The categories to order.

    Returns:
        ``(ordered_categories, depth_map)``: the categories in display order
        and each id's nesting depth (0 for a root).
    """
    by_id, children_by_parent = _build_children_by_parent(categories)
    ordered_ids: list[int] = []
    depth_map: dict[int, int] = {}

    def place(start_id: int) -> None:
        """Append ``start_id`` and then its subtree, depth first, to the ordering.

        Uses an explicit stack instead of recursion, so a tree of any depth is
        placed without RecursionError. Each id is placed once, which also stops
        a cycle at the repeated id.

        Args:
            start_id: A root (or an id no root reaches) placed at depth 0.
        """
        stack = [(start_id, 0)]
        while stack:
            category_id, depth = stack.pop()
            if category_id in depth_map:
                continue
            depth_map[category_id] = depth
            ordered_ids.append(category_id)
            for child_id in reversed(children_by_parent.get(category_id, [])):
                if child_id not in depth_map:
                    stack.append((child_id, depth + 1))

    for root_id in children_by_parent.get(None, []):
        place(root_id)

    # 순환 등으로 루트에서 도달 불가한 노드 fallback
    for category_id in sorted(by_id.keys()):
        if category_id not in depth_map:
            place(category_id)

    ordered_categories = [by_id[category_id] for category_id in ordered_ids]
    return ordered_categories, depth_map
