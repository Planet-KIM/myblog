"""The site's Content-Security-Policy.

A second line of defence against cross-site scripting: even if markup got
past the sanitizer, the browser runs no inline script, no event-handler
attribute and no ``javascript:`` URL, and loads scripts only from this site
and the exact CDN packages the templates use. Inline style *attributes*
stay allowed: post bodies carry colours and sizes as ``style`` attributes,
the magazine viewer places blocks with them, and styles cannot run code.
``<style>`` *elements* are not (``style-src-elem``): stylesheets come only
from this site and the CDNs, so markup that got past the sanitizer could not
restyle the page with selectors. Browsers without ``style-src-elem`` and
``style-src-attr`` (Safari before 15.4, Firefox before 108) fall back to
``style-src``, which still allows both.

Editor pages are the exception (:func:`mark_editor_page`): TipTap and the
code blocks of the Markdown editor (CodeMirror) write their base styles into
``<style>`` elements, so ``style-src-elem`` also allows inline there. Those
pages show only the signed-in author's own post.

When a template starts loading a script from another CDN path, add it to
``SCRIPT_SOURCES``. ``settings.CSP_REPORT_ONLY`` sends the policy as
``Content-Security-Policy-Report-Only`` (the browser only reports, in its
console) to try changes safely.
"""
from app.config import settings

# 스타일시트를 불러오는 곳 (사이트 파일, Bootstrap·아이콘·폰트 CDN)
STYLE_SOURCES = ("'self'", "https://cdn.jsdelivr.net", "https://fonts.googleapis.com")

# 템플릿이 실제로 불러오는 스크립트 (버전까지 고정한 경로만)
SCRIPT_SOURCES = (
    "'self'",
    "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/",
    "https://cdn.jsdelivr.net/npm/chart.js@4.4.4/",
    "https://cdn.jsdelivr.net/npm/fuse.js@6.6.2/",
    "https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/",
    "https://cdn.jsdelivr.net/npm/tom-select@2.3.1/",
    "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/",
)

DIRECTIVES = {
    "default-src": ("'self'",),
    "script-src": SCRIPT_SOURCES,
    # style-src-elem/attr 를 모르는 브라우저용 (예전처럼 인라인 스타일 전부 허용)
    "style-src": STYLE_SOURCES + ("'unsafe-inline'",),
    # <style> 요소·<link rel=stylesheet>: 파일만 (인라인 <style> 차단)
    "style-src-elem": STYLE_SOURCES,
    # style="" 속성: 글 본문의 색·크기, 매거진 뷰어의 블록 위치
    "style-src-attr": ("'unsafe-inline'",),
    "font-src": ("'self'", "data:", "https://cdn.jsdelivr.net", "https://fonts.gstatic.com"),
    # 글에는 외부 이미지 주소도 들어간다
    "img-src": ("'self'", "data:", "blob:", "https:", "http:"),
    "media-src": ("'self'", "blob:", "https:"),
    "connect-src": ("'self'",),
    "frame-src": ("'none'",),
    "object-src": ("'none'",),
    "base-uri": ("'self'",),
    "form-action": ("'self'",),
    "frame-ancestors": ("'self'",),
}


# 편집기 페이지: TipTap·CodeMirror 가 기본 스타일을 <style> 로 넣으므로 인라인 <style> 도 허용
EDITOR_DIRECTIVES = {**DIRECTIVES, "style-src-elem": STYLE_SOURCES + ("'unsafe-inline'",)}


def policy(editor: bool = False) -> str:
    """Return the policy as a header value.

    Args:
        editor: Build the editor-page variant (inline ``<style>`` allowed).

    Returns:
        The directives joined as one header value.
    """
    directives = EDITOR_DIRECTIVES if editor else DIRECTIVES
    return "; ".join(f"{name} {' '.join(sources)}" for name, sources in directives.items())


def mark_editor_page(request) -> None:
    """Make this request's response use the editor-page policy (see :func:`policy`).

    Args:
        request: The request of an editor page handler.
    """
    request.state.csp_editor_page = True


def is_editor_page(request) -> bool:
    """Tell whether the handler marked this request with :func:`mark_editor_page`."""
    return bool(getattr(request.state, "csp_editor_page", False))


def header_name() -> str:
    """Return the header to send it in (report-only while trying changes)."""
    return "Content-Security-Policy-Report-Only" if settings.CSP_REPORT_ONLY else "Content-Security-Policy"
