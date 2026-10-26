"""Bilingual post text: ``{{한국어||English}}`` pairs written in a post body.

On the post page readers switch between the languages (static/js/bilingual.js).
Everywhere else a post shows one language, picked here: titles, card previews,
meta descriptions, digests and feed summaries use Korean, the default.
"""
import re

# {{ko||en}}; either side may contain inline markup but not another pair.
PAIR_PATTERN = re.compile(r"\{\{(.*?)\|\|(.*?)\}\}", re.DOTALL)

DEFAULT_LANGUAGE = "ko"


def has_pairs(text: str) -> bool:
    """Tell whether ``text`` contains at least one ``{{ko||en}}`` pair.

    Args:
        text: Post text, HTML or Markdown.

    Returns:
        True when a pair is present.
    """
    return bool(text) and PAIR_PATTERN.search(text) is not None


def pick_language(text: str, lang: str = DEFAULT_LANGUAGE) -> str:
    """Replace every ``{{ko||en}}`` pair in ``text`` with one of its sides.

    Whitespace just inside the braces and around ``||`` is dropped, so
    ``{{ 가중치 || weights }}`` reads as ``가중치``.

    Args:
        text: Post text, HTML or Markdown. ``None`` is treated as empty.
        lang: ``"ko"`` keeps the Korean side, ``"en"`` the English side.

    Returns:
        The text with each pair reduced to one language.
    """
    side = 2 if lang == "en" else 1
    return PAIR_PATTERN.sub(lambda m: m.group(side).strip(), text or "")
