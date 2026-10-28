"""Reading-time estimates for posts, shared by the home cards and the post pages.

Only the body text counts (markup, images and code are dropped), and a
bilingual post is estimated per language. Korean is counted in characters and
everything else in words: a Korean word (eojeol) packs several syllables, so
words would undercount it, while counting English by characters would make it
look about three times longer than the same text in Korean.
"""
import re

from app.services.bilingual import DEFAULT_LANGUAGE
from app.services.plain_text import markdown_to_plain

KOREAN_CHARS_PER_MINUTE = 350
WORDS_PER_MINUTE = 200

# 한글 음절·자모 (호환 자모 포함)
_HANGUL = re.compile(r"[ᄀ-ᇿ㄰-㆏가-힣]")


def minutes_for_text(plain: str) -> int:
    """Estimate the reading time of plain text.

    Args:
        plain: Plain text, Korean, English or mixed.

    Returns:
        Hangul characters at KOREAN_CHARS_PER_MINUTE plus the remaining words
        at WORDS_PER_MINUTE, rounded, never less than 1.
    """
    hangul = len(_HANGUL.findall(plain))
    words = len(_HANGUL.sub(" ", plain).split())
    return max(1, round(hangul / KOREAN_CHARS_PER_MINUTE + words / WORDS_PER_MINUTE))


def estimate_reading_minutes(text: str, lang: str = DEFAULT_LANGUAGE) -> int:
    """Estimate the reading time of a post body in one language.

    Args:
        text: Markdown or HTML body.
        lang: ``"ko"`` or ``"en"``; bilingual ``{{ko||en}}`` pairs count only
            this side.

    Returns:
        Whole minutes, never less than 1.
    """
    return minutes_for_text(markdown_to_plain(text, max_len=None, lang=lang))
