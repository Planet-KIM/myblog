"""
프로필/핸들 검증 유틸
=====================
- handle: URL(/@handle)에 노출되는 블로그 식별자. 라우트/시스템 경로 위장을 막기 위해
  형식(영소문자/숫자/_/-, 2~30자) + 예약어를 강하게 제한한다.
- avatar_url: 외부 이미지 URL. javascript:/data: 등 위험 스킴 차단(sanitize.safe_url 재사용).
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

from app import models
from app.services.sanitize import safe_url

HANDLE_RE = re.compile(r"^[a-z0-9_-]{2,30}$")

# 라우트/시스템 경로와 충돌하거나 사칭에 쓰일 수 있는 핸들 차단
RESERVED_HANDLES = {
    "admin", "administrator", "api", "auth", "board", "blog", "static",
    "me", "main", "new", "login", "logout", "signup", "signin", "settings",
    "profile", "posts", "post", "categories", "category", "drafts", "draft",
    "about", "help", "support", "tags", "tag", "search", "feed", "rss",
    "home", "user", "users", "null", "undefined", "root", "system",
    "favicon.ico", "robots.txt", "sitemap.xml", "assets", "uploads",
}


def validate_handle(raw: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """(정규화된 handle, error) 반환. error가 None이면 통과."""
    handle = (raw or "").strip().lower()
    if not handle:
        return None, "핸들(블로그 주소)을 입력해주세요."
    if not HANDLE_RE.match(handle):
        return None, "핸들은 영문 소문자·숫자·_·- 로 2~30자여야 합니다."
    if handle in RESERVED_HANDLES:
        return None, "사용할 수 없는 핸들입니다. 다른 값을 입력해주세요."
    return handle, None


ACCENT_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def validate_accent_color(raw: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """(정규화된 #rrggbb 또는 None, error) 반환. 빈 값은 (None, None)."""
    value = (raw or "").strip().lower()
    if not value:
        return None, None
    if not ACCENT_RE.match(value):
        return None, "강조색은 #rrggbb 형식의 HEX여야 합니다. (예: #0ea5e9)"
    return value, None


def validate_avatar_url(raw: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """(안전한 url 또는 None, error) 반환. 빈 값은 (None, None)."""
    value = (raw or "").strip()
    if not value:
        return None, None
    safe = safe_url(value)
    if not safe:
        return None, "이미지 URL이 올바르지 않습니다. (http/https 또는 내부 경로만 허용)"
    return safe, None


def generate_unique_handle(db, email: Optional[str]) -> str:
    """가입 시 이메일 기반으로 유니크한 handle 자동 생성."""
    base = re.sub(r"[^a-z0-9_-]", "", (email or "").split("@")[0].lower()).strip("-_")
    base = base[:24] or "user"
    if base in RESERVED_HANDLES:
        base = f"u{base}"[:30]
    candidate = base
    n = 1
    while len(candidate) < 2 or candidate in RESERVED_HANDLES or \
            db.query(models.User).filter(models.User.handle == candidate).first():
        n += 1
        candidate = f"{base}{n}"[:30]
    return candidate
