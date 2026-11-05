"""
HTML 정제 (XSS 방어)
====================
사용자가 작성한 본문 HTML을 화면에 출력하기 전에 안전한 태그/속성/스타일만
남기고 나머지를 제거한다. bleach(allowlist 기반) 사용.

대상:
  - content_html        : Milkdown 렌더 결과 등 저장된 HTML
  - content_blocks(JSON) : TipTap 블록 에디터. 각 블록의 content(HTML)와 src(URL)를
                           정제하고, <script> 태그 안에 안전하게 삽입할 수 있도록
                           '<', '>', '&' 를 유니코드 이스케이프한 JSON 문자열을 반환.

설계 원칙:
  - 허용 목록(allowlist) 방식: 모르는 것은 전부 제거(strip=True)
  - 인라인 스타일은 CSSSanitizer로 색상/레이아웃 속성만 허용 (url()/behavior 등 제거)
  - 링크/이미지 URL은 http(s)/상대경로/mailto/tel 만 허용 (javascript:/data: 차단)
"""
from __future__ import annotations

import logging
import math
import re

import bleach
from bleach.css_sanitizer import CSSSanitizer

from app.services import content_blocks
from app.services.plain_text import drop_elements

logger = logging.getLogger(__name__)

# script/style/template 등은 bleach가 태그를 제거해도 내부 '텍스트'가 남을 수 있어
# bleach 적용 전에 내용째 통째로 제거한다. (실제 본문엔 등장하지 않음)
_DANGEROUS_ELEMENTS = ("script", "style", "template", "noscript", "title")

# ── 허용 태그 ──────────────────────────────────────────────
ALLOWED_TAGS = {
    "p", "br", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "b", "em", "i", "u", "s", "del", "ins", "mark", "sub", "sup", "small",
    "a", "ul", "ol", "li", "blockquote", "pre", "code",
    "span", "div", "img",
    "table", "thead", "tbody", "tr", "td", "th", "caption",
    "figure", "figcaption",
}

# ── 허용 URL 스킴 ──────────────────────────────────────────
ALLOWED_PROTOCOLS = {"http", "https", "mailto", "tel"}

# ── 허용 CSS 속성 (색상 + 레이아웃만. url()/behavior/expression 등은 제외) ──
ALLOWED_CSS_PROPERTIES = [
    "color", "background-color",
    "text-align", "text-decoration", "text-transform",
    "font-weight", "font-style", "font-size", "line-height", "letter-spacing",
    "font-family",
    "width", "height", "max-width", "min-width", "max-height", "min-height",
    "position", "top", "left", "right", "bottom",
    "overflow", "box-sizing", "display", "vertical-align",
    "padding", "padding-top", "padding-bottom", "padding-left", "padding-right",
    "margin", "margin-top", "margin-bottom", "margin-left", "margin-right",
    "object-fit", "object-position",
    "border", "border-radius", "border-width", "border-color", "border-style",
    "border-left", "border-right", "border-top", "border-bottom",
]

# ── 속성 허용 규칙 ─────────────────────────────────────────
_GLOBAL_ATTRS = {"class", "id", "style", "title", "role", "aria-label"}
_TAG_ATTRS = {
    "a": {"href", "target", "rel"},
    "img": {"src", "alt", "width", "height"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
}

# URL 값에 들어가면 속성 경계를 깨거나 스킴 위장에 쓰일 수 있는 문자
_UNSAFE_URL_CHARS = set("\"'<>` \t\r\n")


def _allow_attribute(tag: str, name: str, value: str) -> bool:
    """bleach attributes 콜백: 전역 속성 + data-* + 태그별 속성만 허용."""
    name = name.lower()
    if name in _GLOBAL_ATTRS:
        return True
    if name.startswith("data-"):
        return True
    return name in _TAG_ATTRS.get(tag, set())


_css_sanitizer = CSSSanitizer(allowed_css_properties=ALLOWED_CSS_PROPERTIES)


def sanitize_html(html: str | None) -> str:
    """Return user HTML with everything outside the allowlists removed.

    Script-like elements are first dropped with their contents (in linear
    time; a lazy regex here was quadratic in the body length), then bleach
    keeps only the allowed tags, attributes, URL schemes and CSS properties.

    Args:
        html: User HTML. ``None`` is treated as empty.

    Returns:
        Safe HTML.
    """
    if not html:
        return ""
    html = drop_elements(html, _DANGEROUS_ELEMENTS, "")
    return bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=_allow_attribute,
        protocols=ALLOWED_PROTOCOLS,
        css_sanitizer=_css_sanitizer,
        strip=True,
        strip_comments=True,
    )


def safe_url(src: str | None) -> str:
    """Check a URL taken from user content (an image source, a link).

    Args:
        src: The URL. ``None`` is treated as empty.

    Returns:
        The URL stripped of surrounding spaces when it is a site path or an
        http(s)/mailto/tel URL without quote, angle-bracket or space
        characters; otherwise an empty string.
    """
    if not src:
        return ""
    s = src.strip()
    if not s or any(c in _UNSAFE_URL_CHARS for c in s):
        return ""
    low = s.lower()
    if low.startswith(("javascript:", "data:", "vbscript:", "file:")):
        return ""
    if s.startswith("/") or low.startswith(("http://", "https://", "mailto:", "tel:")):
        return s
    return ""


_OVERLAY_POSITIONS = ("bottom", "center", "top")
_OVERLAY_TONES = ("band-dark", "band-light", "plain")
# 사진 필터 — 에디터(frontend/board_*_tiptap.js FILTERS)와 같은 값
_IMG_FILTERS = ("none", "bw", "duotone")
_COLOR_RE = re.compile(r"#[0-9A-Fa-f]{3,8}")
# 뷰어가 속성·CSS 값에 그대로 쓰는 크기·위치 값: 유한한 숫자만 허용
_BLOCK_NUMBER_KEYS = ("x", "y", "w", "h", "borderWidth", "borderRadius", "imgOffsetX", "imgOffsetY")
_PAGE_NUMBER_KEYS = ("cw", "ch")


def _finite_number(value) -> float | int | None:
    """Return ``value`` as a finite number, or None when it is not one.

    Numeric text such as ``"120"`` is converted (the viewer used to coerce it
    in arithmetic, so older layouts may hold it); booleans are not numbers.
    """
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return value


def _normalize_numbers(obj: dict, keys: tuple[str, ...]) -> None:
    """Make each of ``keys`` in ``obj`` a finite number, in place.

    Numeric text becomes a number and anything else is removed, so readers
    use their defaults for it.

    Args:
        obj: A page or block dict.
        keys: The keys that must hold numbers.
    """
    for key in keys:
        if key in obj:
            number = _finite_number(obj[key])
            if number is None:
                del obj[key]
            else:
                obj[key] = number


def _sanitize_block(block: dict) -> None:
    """Sanitize one content_blocks block in place.

    The HTML fields (``content`` and a photo's ``overlay`` text) are cleaned,
    and ``src`` must be a safe URL; any of the three that is not a string
    becomes "" (the viewer would turn a list into markup). Values the viewer
    writes into attributes and styles are checked: geometry and border sizes
    must be finite numbers (numeric text is converted, anything else is
    removed), the border colour a #hex colour (else black) and the photo
    filter a known name (else none). The overlay's
    position and tone (class names on the post page) are limited to the known
    values, and a post card's ``postId`` must be an integer (else None).

    Args:
        block: One block dict from content_blocks.
    """
    for key in ("content", "overlay"):
        if key in block:
            value = block[key]
            block[key] = sanitize_html(value) if isinstance(value, str) else ""
    if "src" in block:
        src = block["src"]
        block["src"] = safe_url(src) if isinstance(src, str) else ""
    _normalize_numbers(block, _BLOCK_NUMBER_KEYS)
    color = block.get("borderColor")
    if "borderColor" in block and not (isinstance(color, str) and _COLOR_RE.fullmatch(color)):
        block["borderColor"] = "#000000"
    if "imgFilter" in block and block["imgFilter"] not in _IMG_FILTERS:
        block["imgFilter"] = "none"
    if "overlayPos" in block and block["overlayPos"] not in _OVERLAY_POSITIONS:
        block["overlayPos"] = "bottom"
    if "overlayTone" in block and block["overlayTone"] not in _OVERLAY_TONES:
        block["overlayTone"] = "band-dark"
    if "postId" in block:
        try:
            block["postId"] = int(block["postId"])
        except (TypeError, ValueError, OverflowError):
            block["postId"] = None


def _sanitize_page(page: dict) -> None:
    """Sanitize one page's own fields in place.

    The canvas size must be finite numbers (numeric text is converted,
    anything else is removed so readers use their default), and a ``blocks``
    value that is not a list becomes empty.

    Args:
        page: A page dict (or the top-level document of a single-page layout).
    """
    _normalize_numbers(page, _PAGE_NUMBER_KEYS)
    if "blocks" in page and not isinstance(page["blocks"], list):
        page["blocks"] = []


def sanitize_content_blocks(raw: str | None) -> str:
    """Sanitize a magazine post's content_blocks JSON for the post and edit pages.

    Every block that the post page's viewer or the editor may draw is
    cleaned, in every stored format at once (content_blocks.iter_blocks walks
    them all), so a reader that picks another format than the sanitizer
    expected still gets clean blocks. Page and block lists keep only dict
    entries. The structure is otherwise kept, and '<', '>' and '&' are
    escaped so the JSON can sit inside ``<script type="application/json">``.

    Args:
        raw: The stored JSON text.

    Returns:
        The cleaned JSON, or "" when ``raw`` is empty or cannot be decoded or
        encoded (the stored text is never passed through).
    """
    data = content_blocks.parse(raw)
    if data is None:
        if raw:
            logger.warning("content_blocks JSON 파싱 실패 — 빈 값으로 대체")
        return ""
    if isinstance(data, dict) and isinstance(data.get("pages"), list):
        data["pages"] = [page for page in data["pages"] if isinstance(page, dict)]
    for page in content_blocks.iter_pages(data):
        _sanitize_page(page)
    for blocks in content_blocks.iter_block_lists(data):
        blocks[:] = [block for block in blocks if isinstance(block, dict)]
        for block in blocks:
            _sanitize_block(block)

    out = content_blocks.dumps(data)
    if out is None:
        return ""
    # 스크립트 태그 탈출 방지: 구조 문자가 아닌 string 값 내부의 < > & 만 영향받음
    return out.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
