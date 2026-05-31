from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import secrets
from typing import Optional


HOME_LAYOUT_STRATEGY_PER_REQUEST_RANDOM = "per_request_random"
HOME_LAYOUT_STRATEGY_DAILY_STABLE_BY_VIEWER = "daily_stable_by_viewer"

# 각 행의 col-span 합이 항상 3이 되도록 구성한 레이아웃 템플릿
# bento-full: 3칸, bento-2: 2칸, bento-1: 1칸
HOME_BENTO_LAYOUTS = [
    ["bento-full", "bento-2", "bento-1", "bento-1", "bento-1", "bento-1"],
    ["bento-full", "bento-1", "bento-1", "bento-1", "bento-2", "bento-1"],
    ["bento-2", "bento-1", "bento-full", "bento-1", "bento-1", "bento-1"],
    ["bento-2", "bento-1", "bento-2", "bento-1", "bento-2", "bento-1"],
    ["bento-2", "bento-1", "bento-1", "bento-1", "bento-1", "bento-full"],
    ["bento-1", "bento-1", "bento-1", "bento-full", "bento-2", "bento-1"],
    ["bento-1", "bento-1", "bento-1", "bento-2", "bento-1", "bento-full"],
]


def build_layout_viewer_key(raw_viewer_key: Optional[str]) -> str:
    """stable 전략에서 사용할 안전한 viewer key 생성"""
    return raw_viewer_key or "anon"


def select_home_card_sizes(
    posts_count: int,
    strategy: str = HOME_LAYOUT_STRATEGY_PER_REQUEST_RANDOM,
    viewer_key: Optional[str] = None,
    now: Optional[datetime] = None,
) -> list[str]:
    """
    홈 카드 레이아웃 클래스를 선택한다.

    strategy:
      - per_request_random: 매 요청마다 랜덤 선택
      - daily_stable_by_viewer: 사용자/날짜 기준으로 고정 선택
    """
    if posts_count <= 0:
        return []

    if strategy == HOME_LAYOUT_STRATEGY_PER_REQUEST_RANDOM:
        selected_layout = secrets.choice(HOME_BENTO_LAYOUTS)
    elif strategy == HOME_LAYOUT_STRATEGY_DAILY_STABLE_BY_VIEWER:
        dt = now or datetime.utcnow()
        day_key = dt.strftime("%Y-%m-%d")
        safe_viewer_key = build_layout_viewer_key(viewer_key)
        layout_seed = int(sha256(f"{day_key}:{safe_viewer_key}".encode("utf-8")).hexdigest(), 16)
        selected_layout = HOME_BENTO_LAYOUTS[layout_seed % len(HOME_BENTO_LAYOUTS)]
    else:
        raise ValueError(f"Unknown home layout strategy: {strategy}")

    card_sizes: list[str] = []
    while len(card_sizes) < posts_count:
        card_sizes.extend(selected_layout)
    return card_sizes[:posts_count]
