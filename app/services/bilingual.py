"""Bilingual post text: ``{{한국어||English}}`` pairs written in a post body.

On the post page readers switch between the languages (static/js/bilingual.js).
Everywhere else a post shows one language, picked here: titles, card previews,
meta descriptions, digests and feed summaries use Korean, the default.
"""
from typing import Iterator

# {{ko||en}}; either side may contain inline markup but not another pair.
PAIR_OPEN, PAIR_SEPARATOR, PAIR_CLOSE = "{{", "||", "}}"

DEFAULT_LANGUAGE = "ko"


def _pairs(text: str) -> Iterator[tuple[int, int, int]]:
    """Find the ``{{ko||en}}`` pairs in ``text``, left to right.

    A pair runs from ``{{`` to the first ``||`` after it, then to the first
    ``}}`` after that: the pairs the lazy regex ``\\{\\{(.*?)\\|\\|(.*?)\\}\\}``
    matched. Each search starts where the previous one stopped, so the scan is
    linear in the text length; the regex retried from every ``{{`` and could
    run for minutes on a crafted post body.

    Args:
        text: Post text, HTML or Markdown.

    Yields:
        ``(start, separator, close)``: the indexes of the pair's ``{{``, ``||``
        and ``}}``.
    """
    pos = 0
    while True:
        start = text.find(PAIR_OPEN, pos)
        if start < 0:
            return
        separator = text.find(PAIR_SEPARATOR, start + len(PAIR_OPEN))
        if separator < 0:
            return
        close = text.find(PAIR_CLOSE, separator + len(PAIR_SEPARATOR))
        if close < 0:
            return
        yield start, separator, close
        pos = close + len(PAIR_CLOSE)


def has_pairs(text: str) -> bool:
    """Tell whether ``text`` contains at least one ``{{ko||en}}`` pair.

    Args:
        text: Post text, HTML or Markdown.

    Returns:
        True when a pair is present.
    """
    return bool(text) and next(_pairs(text), None) is not None


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
    text = text or ""
    parts, pos = [], 0
    for start, separator, close in _pairs(text):
        if lang == "en":
            side = text[separator + len(PAIR_SEPARATOR):close]
        else:
            side = text[start + len(PAIR_OPEN):separator]
        parts.append(text[pos:start])
        parts.append(side.strip())
        pos = close + len(PAIR_CLOSE)
    parts.append(text[pos:])
    return "".join(parts)
