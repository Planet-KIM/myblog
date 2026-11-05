"""Plain text of a post body (Markdown, HTML or both) for previews and reading time.

These helpers run on stored post bodies on every page view, so every step is
linear in the body length. Python-Markdown is not used: its link and image
parsing is quadratic in the number of ``[`` characters (16,000 of them took
34 s), and plain text needs only the words, not the rendered HTML. Each regex
below leaves its own delimiters out of its character classes, so a failed
match stops at the next delimiter instead of rescanning the rest of the text.
"""
import functools
import html as html_module
import re

from app.services.bilingual import DEFAULT_LANGUAGE, pick_language

# Elements whose contents are code or markup, not prose.
CODE_ELEMENTS = ("script", "style", "pre", "code")
_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})")
_CODE_SPAN = re.compile(r"`[^`\n]*`")

_IMAGE = re.compile(r"!\[[^\[\]\n]*\]\([^()\n]*\)")
_LINK = re.compile(r"\[([^\[\]\n]*)\]\([^()\n]*\)")
_REFERENCE_LINK = re.compile(r"\[([^\[\]\n]*)\]\[[^\[\]\n]*\]")
_REFERENCE_DEFINITION = re.compile(r"\[[^\[\]\n]+\]:\s")
_AUTOLINK = re.compile(r"<((?:https?|mailto):[^<>\s]*)>")
# Emphasis and strikethrough markers next to text; intraword underscores stay.
_EMPHASIS = re.compile(
    r"\*{1,3}(?=\S)|(?<=\S)\*{1,3}|~~(?=\S)|(?<=\S)~~|(?<!\w)_{1,3}(?=\S)|(?<=\S)_{1,3}(?!\w)"
)

_QUOTE_MARKERS = re.compile(r"(?:>\s?)+")
_HEADING_MARKER = re.compile(r"#{1,6}(?:\s+|$)")
_LIST_MARKER = re.compile(r"(?:[-*+]|\d{1,9}[.)])\s+")
_RULE_CHARS = ({"-"}, {"*"}, {"_"}, {"="})
_TABLE_RULE_CHARS = set("|:- \t")

_TAG = re.compile(r"<[^<>]+>")
_LINE_BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)
_BLOCK_NAMES = r"h[1-6]|p|div|li|blockquote|section|article|header|footer|tr|td|th"
_BLOCK_CLOSE = re.compile(rf"</({_BLOCK_NAMES})>", re.IGNORECASE)
_BLOCK_OPEN = re.compile(rf"<({_BLOCK_NAMES})[^<>]*>", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")


@functools.lru_cache(maxsize=None)
def _element_patterns(names: tuple[str, ...]) -> tuple[re.Pattern, dict[str, re.Pattern]]:
    """Compile the opening-tag pattern for ``names`` and a closing-tag pattern per name."""
    opening = re.compile(rf"<({'|'.join(names)})\b[^<>]*>", re.IGNORECASE)
    closing = {name: re.compile(rf"</{name}\s*>", re.IGNORECASE) for name in names}
    return opening, closing


def drop_elements(html: str, names: tuple[str, ...] = CODE_ELEMENTS, replacement: str = " ") -> str:
    """Remove every element with one of ``names``, tags and contents together.

    An element whose closing tag never comes is kept, as the lazy
    ``<name ...>.*?</name>`` regexes this replaces did. Each search starts where
    the last one stopped and a name found without its closing tag is not looked
    for again, so the cost is linear in the length of ``html``.

    Args:
        html: HTML, or Markdown with HTML in it.
        names: Lowercase tag names.
        replacement: What each removed element becomes.

    Returns:
        The text without those elements.
    """
    opening_pattern, closing_patterns = _element_patterns(names)
    parts, pos, search_from, unclosed = [], 0, 0, set()
    while True:
        opening = opening_pattern.search(html, search_from)
        if not opening:
            break
        name = opening.group(1).lower()
        closing = None if name in unclosed else closing_patterns[name].search(html, opening.end())
        if not closing:
            unclosed.add(name)
            search_from = opening.end()
            continue
        parts.append(html[pos:opening.start()])
        parts.append(replacement)
        pos = search_from = closing.end()
    parts.append(html[pos:])
    return "".join(parts)


def block_html_to_lines(html: str, tag_replacement: str = " ") -> str:
    """Turn HTML into text with a line per block, in linear time.

    ``<br>`` and the end of each block element (headings, paragraphs, list
    items, table cells, ...) become line breaks, and every other tag is
    replaced. Entities are left as they are.

    Args:
        html: HTML text.
        tag_replacement: What each remaining tag becomes.

    Returns:
        The text with line breaks at block boundaries.
    """
    text = _LINE_BREAK.sub("\n", html)
    text = _BLOCK_CLOSE.sub("\n", text)
    text = _BLOCK_OPEN.sub("", text)
    return _TAG.sub(tag_replacement, text)


def _drop_fenced_code(text: str) -> str:
    """Remove fenced code blocks (``` or ~~~ fences) line by line.

    A fence closes on a line of at least as many of the same character with
    nothing after it. As in CommonMark, a fence that never closes runs to the
    end of the text.

    Args:
        text: Markdown text.

    Returns:
        The text without the fenced blocks.
    """
    kept, fence = [], None
    for line in text.split("\n"):
        match = _FENCE.match(line)
        if fence is None:
            if match:
                fence = match.group(1)
            else:
                kept.append(line)
        elif (match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence)
              and not line[match.end():].strip()):
            fence = None
    return "\n".join(kept)


def _strip_block_markers(line: str) -> str:
    """Remove the Markdown block syntax at the start of one line.

    Drops quote markers, a heading's ``#`` marks and a list marker, and turns
    the cell separators of a table row into spaces. Horizontal rules, setext
    underlines, table separator rows and reference link definitions become
    empty.

    Args:
        line: One line of Markdown.

    Returns:
        The line's text.
    """
    text = line.strip()
    compact = text.replace(" ", "")
    if len(compact) >= 3 and set(compact) in _RULE_CHARS:
        return ""
    if "-" in text and set(text) <= _TABLE_RULE_CHARS:
        return ""
    if _REFERENCE_DEFINITION.match(text):
        return ""
    text = text[_QUOTE_MARKERS.match(text).end():] if text.startswith(">") else text
    for marker in (_HEADING_MARKER, _LIST_MARKER):
        match = marker.match(text)
        if match:
            text = text[match.end():]
    if text.startswith("|"):
        text = text.replace("|", " ")
    return text


def strip_inline_markdown(text: str) -> str:
    """Reduce inline Markdown to its text.

    Images are dropped, links keep their text and autolinks their address,
    and emphasis and strikethrough markers and code-span backticks are removed.

    Args:
        text: Markdown text.

    Returns:
        The text without inline Markdown syntax (HTML tags are left as they are).
    """
    text = _IMAGE.sub(" ", text)
    text = _LINK.sub(r"\1", text)
    text = _REFERENCE_LINK.sub(r"\1", text)
    text = _AUTOLINK.sub(r"\1", text)
    text = _CODE_SPAN.sub(lambda m: m.group(0)[1:-1], text)
    return _EMPHASIS.sub("", text)


def markdown_line_text(line: str) -> str:
    """Text of one line of Markdown, without its block or inline syntax.

    Args:
        line: One line of Markdown (a title line, for example).

    Returns:
        The line's text; HTML tags and entities are left as they are.
    """
    return strip_inline_markdown(_strip_block_markers(line))


def strip_tags(html: str, replacement: str = " ") -> str:
    """Remove HTML tags.

    Args:
        html: HTML text.
        replacement: What each tag becomes.

    Returns:
        The text with every ``<...>`` tag replaced.
    """
    return _TAG.sub(replacement, html)


def markdown_to_plain(text: str, max_len: int | None = 180, lang: str = DEFAULT_LANGUAGE) -> str:
    """Turn a Markdown/HTML post body into one line of plain text.

    Images, code blocks and inline code are dropped, and each ``{{ko||en}}``
    pair keeps only the ``lang`` side. Runs in time linear in the body length.

    Args:
        text: Markdown or HTML body. ``None`` is treated as empty.
        max_len: Cut the result to this many characters and add ``...``;
            ``None`` keeps all of it.
        lang: ``"ko"`` or ``"en"``, the side of bilingual pairs to keep.

    Returns:
        The text with tags removed, entities decoded and whitespace collapsed.
    """
    text = (text or "").strip()
    if not text:
        return ""

    # 1) 코드 블록·인라인 코드·스크립트/스타일 제거 (카드 미리보기 노이즈 방지)
    text = drop_elements(_drop_fenced_code(text))
    text = _CODE_SPAN.sub(" ", text)
    text = pick_language(text, lang)  # 이중 언어 {{ko||en}} 은 한쪽만

    # 2) Markdown 문법 제거 (블록 기호 → 이미지·링크·강조)
    text = strip_inline_markdown("\n".join(_strip_block_markers(line) for line in text.split("\n")))

    # 3) 태그 제거 -> 엔티티 복원 -> 잔재 태그 재제거
    plain = strip_tags(text)
    plain = html_module.unescape(plain)
    plain = strip_tags(plain)

    # 4) 남아있는 꺾쇠 제거 (엔티티 복원 후 생긴 태그 조각 방어)
    plain = plain.replace("<", " ").replace(">", " ")

    # 5) 줄바꿈/연속 공백 정리
    plain = _WHITESPACE.sub(" ", plain).strip()

    # 6) 최대 길이 제한
    if max_len is not None and len(plain) > max_len:
        plain = plain[:max_len] + '...'
    return plain
