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
  - 인라인 스타일은 CSSSanitizer로 색상/레이아웃 속성만 허용 (url()/behavior 등 제거),
    position 은 static/relative/absolute 만 (fixed·sticky 로 페이지를 덮지 못하게)
  - 링크/이미지 URL은 http(s)/상대경로/mailto/tel 만 허용 (javascript:/data: 차단)
  - data-* 는 에디터가 만드는 것만, 사이트 요소가 쓰는 id 는 제거
    (본문이 같은 문서의 페이지 요소·JS 동작 훅을 흉내 내지 못하게)
"""
from __future__ import annotations

import logging
import math
import re
from functools import lru_cache
from pathlib import Path

import bleach
import tinycss2
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

# 본문에 남기는 data-* 속성: 에디터(Milkdown/TipTap 번들, frontend/plugins)가 실제로 만드는 것만.
# 사이트 JS 는 data-* 를 동작 훅으로 쓰므로(data-detail-action, data-img-fallback-scope,
# data-confirm, data-src …) 모르는 data-* 는 본문에서 지운다.
_CONTENT_DATA_ATTRS = {
    "data-type", "data-show", "data-pm-slice", "data-spread", "data-role", "data-label",
    "data-index", "data-checked", "data-language", "data-tiptap-style", "data-text-color",
    "data-color", "data-list-type", "data-item-type", "data-is-header", "data-display-type",
    "data-content-dom", "data-colwidth", "data-value", "data-is-inline", "data-expanded",
    "data-direction", "data-placeholder", "data-page", "data-page-count", "data-height",
}

# 사이트가 쓰는 id 를 찾는 곳: 템플릿의 id="…", JS 의 getElementById('…')·querySelector('#…')
_APP_DIR = Path(__file__).resolve().parent.parent
_TEMPLATE_ID_RE = re.compile(r'\bid="([^"{}\s]+)"')
_SCRIPT_ID_RE = re.compile(
    r"""getElementById\(\s*['"]([^'"]+)['"]|querySelector(?:All)?\(\s*['"][^'"]*#([A-Za-z][\w-]*)"""
)

# URL 값에 들어가면 속성 경계를 깨거나 스킴 위장에 쓰일 수 있는 문자
_UNSAFE_URL_CHARS = set("\"'<>` \t\r\n")


@lru_cache(maxsize=1)
def page_ids() -> frozenset[str]:
    """Return the element ids the site's own templates and scripts use.

    A post body is rendered in the same document as the page, so a body
    element with one of these ids could stand in for the page's element
    (``getElementById`` returns the first match). The set is read from
    ``app/templates`` and ``app/static/js`` once, so it follows the code.

    Returns:
        The ids, as written in the sources.
    """
    ids: set[str] = set()
    for path in (_APP_DIR / "templates").rglob("*.html"):
        ids.update(_TEMPLATE_ID_RE.findall(path.read_text(encoding="utf-8", errors="ignore")))
    for path in (_APP_DIR / "static" / "js").glob("*.js"):
        for by_id, by_selector in _SCRIPT_ID_RE.findall(path.read_text(encoding="utf-8", errors="ignore")):
            ids.add(by_id or by_selector)
    return frozenset(ids)


def _allow_attribute(tag: str, name: str, value: str) -> bool:
    """Decide whether bleach keeps an attribute (its ``attributes`` callback).

    Keeps the global attributes, the tag's own attributes and the ``data-*``
    attributes the editors write (``_CONTENT_DATA_ATTRS``). Other ``data-*``
    attributes are dropped because the site's scripts use them as behavior
    hooks, and so is an ``id`` that one of the site's own elements uses
    (:func:`page_ids`).

    Args:
        tag: The element name.
        name: The attribute name.
        value: The attribute value.

    Returns:
        True to keep the attribute.
    """
    name = name.lower()
    if name == "id":
        return value not in page_ids()
    if name in _GLOBAL_ATTRS:
        return True
    if name.startswith("data-"):
        return name in _CONTENT_DATA_ATTRS
    return name in _TAG_ATTRS.get(tag, set())


# position 값: 매거진 읽기 HTML 이 쓰는 relative/absolute 까지만. fixed·sticky 는 요소를
# 화면에 붙여 페이지의 머리글·신고 버튼·댓글을 덮을 수 있다.
_ALLOWED_POSITIONS = frozenset({"static", "relative", "absolute"})


def _is_allowed_position(declaration) -> bool:
    """Tell whether a tinycss2 ``position`` declaration's value is allowed.

    The value must be a single keyword from ``_ALLOWED_POSITIONS`` (case and
    CSS escapes do not matter); comments, functions or several tokens fail.

    Args:
        declaration: A tinycss2 Declaration whose name is ``position``.

    Returns:
        True to keep the declaration.
    """
    tokens = [t for t in declaration.value if t.type not in ("whitespace", "comment")]
    return len(tokens) == 1 and tokens[0].type == "ident" and tokens[0].lower_value in _ALLOWED_POSITIONS


class _ContentCSSSanitizer(CSSSanitizer):
    """bleach's CSS sanitizer plus one value rule: ``position`` only takes ``_ALLOWED_POSITIONS``.

    bleach filters properties by name only, so ``position: fixed`` would pass
    the property allowlist.
    """

    def sanitize_css(self, style: str) -> str:
        """Sanitize a style attribute with bleach, then drop a disallowed ``position``.

        Args:
            style: The attribute value.

        Returns:
            The cleaned declarations.
        """
        cleaned = super().sanitize_css(style)
        if "position" not in cleaned.lower():
            return cleaned
        kept = [
            token for token in tinycss2.parse_declaration_list(cleaned)
            if not (token.type == "declaration" and token.lower_name == "position" and not _is_allowed_position(token))
        ]
        return tinycss2.serialize(kept).strip()


_css_sanitizer = _ContentCSSSanitizer(allowed_css_properties=ALLOWED_CSS_PROPERTIES)


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
