from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping

from app import models


def _build_children_by_parent(
    categories: Iterable[models.BoardCategory],
) -> tuple[dict[int, models.BoardCategory], dict[int | None, list[int]]]:
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
    """
    카테고리 계층(parent -> children)을 따라 하위 카테고리 글 수까지 합산한다.

    direct_counts:
      - {category_id: 직계 글 수}
      - 예) bangkok=1, chiang-mai=0, travel=0

    반환값:
      - {category_id: 하위 포함 총 글 수}
      - 예) travel=1 (bangkok+chiang-mai 포함)
    """
    by_id, children_by_parent = _build_children_by_parent(categories)
    category_ids = sorted(by_id.keys())

    memo: dict[int, int] = {}

    def dfs(category_id: int, visiting: set[int]) -> int:
        if category_id in memo:
            return memo[category_id]

        # 잘못된 순환 참조가 있어도 서버가 죽지 않게 안전장치
        if category_id in visiting:
            return int(direct_counts.get(category_id, 0) or 0)

        total = int(direct_counts.get(category_id, 0) or 0)
        visiting.add(category_id)
        for child_id in children_by_parent.get(category_id, []):
            total += dfs(child_id, visiting)
        visiting.remove(category_id)

        memo[category_id] = total
        return total

    return {category_id: dfs(category_id, set()) for category_id in category_ids}


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
    """
    부모 카테고리를 먼저, 각 부모 아래에 자식을 depth 순으로 정렬한다.
    반환:
      - ordered_categories: 정렬된 카테고리 리스트
      - depth_map: {category_id: depth}
    """
    by_id, children_by_parent = _build_children_by_parent(categories)
    ordered_ids: list[int] = []
    depth_map: dict[int, int] = {}
    visiting: set[int] = set()

    def walk(category_id: int, depth: int) -> None:
        if category_id in depth_map:
            return
        if category_id in visiting:
            depth_map[category_id] = depth
            ordered_ids.append(category_id)
            return

        visiting.add(category_id)
        depth_map[category_id] = depth
        ordered_ids.append(category_id)
        for child_id in children_by_parent.get(category_id, []):
            walk(child_id, depth + 1)
        visiting.remove(category_id)

    for root_id in children_by_parent.get(None, []):
        walk(root_id, 0)

    # 순환 등으로 루트에서 도달 불가한 노드 fallback
    for category_id in sorted(by_id.keys()):
        if category_id not in depth_map:
            walk(category_id, 0)

    ordered_categories = [by_id[category_id] for category_id in ordered_ids]
    return ordered_categories, depth_map
