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

import json
import logging
import re

import bleach
from bleach.css_sanitizer import CSSSanitizer

logger = logging.getLogger(__name__)

# script/style/template 등은 bleach가 태그를 제거해도 내부 '텍스트'가 남을 수 있어
# bleach 적용 전에 내용째 통째로 제거한다. (실제 본문엔 등장하지 않음)
_DANGEROUS_BLOCK_RE = re.compile(
    r"(?is)<(script|style|template|noscript|title)\b[^>]*>.*?</\1\s*>"
)

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
    """사용자 HTML에서 허용 목록 외 요소를 제거한 안전한 HTML을 반환."""
    if not html:
        return ""
    html = _DANGEROUS_BLOCK_RE.sub("", html)
    return bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=_allow_attribute,
        protocols=ALLOWED_PROTOCOLS,
        css_sanitizer=_css_sanitizer,
        strip=True,
        strip_comments=True,
    )


def _safe_url(src: str | None) -> str:
    """이미지 등 URL 값 검증. 안전하지 않으면 빈 문자열 반환."""
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


def _sanitize_block(block: dict) -> None:
    """content_blocks 내 단일 블록을 제자리(in-place)에서 정제."""
    content = block.get("content")
    if isinstance(content, str):
        block["content"] = sanitize_html(content)
    src = block.get("src")
    if isinstance(src, str):
        block["src"] = _safe_url(src)


def sanitize_content_blocks(raw: str | None) -> str:
    """
    content_blocks(JSON 문자열)를 정제한다.
    - 각 블록의 content(HTML)/src(URL)를 정제
    - 구조(페이지/블록/지오메트리)는 그대로 보존
    - <script type="application/json"> 안에 안전 삽입되도록 '<','>','&' 이스케이프
    파싱 실패 시 빈 문자열 반환(원문을 그대로 내보내지 않음).
    """
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning("content_blocks JSON 파싱 실패 — 빈 값으로 대체")
        return ""

    def walk_page(page) -> None:
        if not isinstance(page, dict):
            return
        for block in page.get("blocks", []) or []:
            if isinstance(block, dict):
                _sanitize_block(block)

    if isinstance(data, list):
        for page in data:
            walk_page(page)
    elif isinstance(data, dict) and data.get("v") == 3 and isinstance(data.get("pages"), list):
        for page in data["pages"]:
            walk_page(page)
    else:
        walk_page(data)

    out = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # 스크립트 태그 탈출 방지: 구조 문자가 아닌 string 값 내부의 < > & 만 영향받음
    return out.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
