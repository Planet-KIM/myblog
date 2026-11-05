"""Who may use spell check, and which models.

Spell check runs large models on the server's CPU and memory, so it is
granted per account by an admin (admin page or ``scripts/set_spellcheck.py``):

    0  no spell check (the default for every account)
    1  the fast models: et5 (Korean) and vennify (English)
    2  the large models too: pko (Korean) and coedit (English), about 3.5 GB
       of memory each

Admins always have level 2. ``POST /api/spellcheck`` enforces the level and
the daily quotas (:func:`daily_quotas`); the editor only hides the buttons a
user cannot use. Users ask for a level at ``/spellcheck/access``
(``app/services/spellcheck_requests.py``).
"""
from __future__ import annotations

from fastapi import HTTPException

from app.config import settings

LEVEL_NONE = 0
LEVEL_BASIC = 1
LEVEL_FULL = 2
LEVEL_LABELS = {
    LEVEL_NONE: "사용 안 함",
    LEVEL_BASIC: "기본 모델",
    LEVEL_FULL: "고품질 모델까지",
}

# 등급 2가 필요한 대형 모델 (app/services/spellcheck.py 의 variant 이름)
LARGE_VARIANTS = frozenset({"pko", "coedit"})


def effective_level(user) -> int:
    """Return the spell-check level a user has.

    Args:
        user: A ``models.User``, or None for a guest.

    Returns:
        ``LEVEL_FULL`` for admins, else the stored level limited to 0..2
        (0 for a guest).
    """
    if user is None:
        return LEVEL_NONE
    if user.is_admin:
        return LEVEL_FULL
    return min(max(int(user.spellcheck_level or 0), LEVEL_NONE), LEVEL_FULL)


def required_level(text: str, en_variant: str, ko_variant: str) -> int:
    """Return the level needed for a request: the model it will really use decides.

    The spell checker picks the Korean or the English model from the text's
    language, so only that model's variant counts (the editor always sends
    both).

    Args:
        text: The text to correct.
        en_variant: Requested English variant.
        ko_variant: Requested Korean variant.

    Returns:
        ``LEVEL_FULL`` when the model used is a large one, else ``LEVEL_BASIC``.
    """
    from app.services.spellcheck import detect_lang   # 지연 임포트: 모델 코드는 필요할 때만

    variant = ko_variant if detect_lang(text) == "ko" else en_variant
    return LEVEL_FULL if variant in LARGE_VARIANTS else LEVEL_BASIC


def ensure_spellcheck_allowed(user, text: str, en_variant: str, ko_variant: str) -> int:
    """Refuse a spell-check request the user's level does not cover.

    Args:
        user: The logged-in ``models.User``.
        text: The text to correct.
        en_variant: Requested English variant.
        ko_variant: Requested Korean variant.

    Returns:
        The level the request needs (``LEVEL_FULL`` when it uses a large model).

    Raises:
        HTTPException: 403 when the user has no spell-check access, or asks
            for a large model with level 1.
    """
    level = effective_level(user)
    if level == LEVEL_NONE:
        raise HTTPException(status_code=403, detail="맞춤법 검사 권한이 없습니다. 신청 페이지(/spellcheck/access)에서 신청해주세요.")
    needed = required_level(text, en_variant, ko_variant)
    if needed > level:
        raise HTTPException(status_code=403, detail="고품질 모델 사용 권한이 없습니다. 빠른 모델을 선택해주세요.")
    return needed


def daily_quotas(user, needed_level: int) -> list[tuple[str, int, str]]:
    """Return the 24-hour quota buckets a request counts against.

    Every request counts toward ``SPELLCHECK_DAILY_LIMIT``; a large-model
    request also toward ``SPELLCHECK_LARGE_DAILY_LIMIT``. Admins have none.
    The buckets are keyed by user id, so an approved account cannot spend
    more by changing IP.

    Args:
        user: The logged-in ``models.User``.
        needed_level: What :func:`ensure_spellcheck_allowed` returned.

    Returns:
        ``(key, limit, message)`` per bucket.
    """
    if user.is_admin:
        return []
    quotas = [(f"spellcheck_day:{user.id}", settings.SPELLCHECK_DAILY_LIMIT,
               f"오늘 맞춤법 검사 횟수({settings.SPELLCHECK_DAILY_LIMIT}회)를 모두 썼습니다. 내일 다시 시도해주세요.")]
    if needed_level >= LEVEL_FULL:
        quotas.append((f"spellcheck_day_large:{user.id}", settings.SPELLCHECK_LARGE_DAILY_LIMIT,
                       f"오늘 고품질 모델 사용 횟수({settings.SPELLCHECK_LARGE_DAILY_LIMIT}회)를 모두 썼습니다. "
                       "빠른 모델을 쓰거나 내일 다시 시도해주세요."))
    return quotas
