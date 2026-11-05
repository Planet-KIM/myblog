"""The site's Content-Security-Policy.

A second line of defence against cross-site scripting: even if markup got
past the sanitizer, the browser runs no inline script, no event-handler
attribute and no ``javascript:`` URL, and loads scripts only from this site
and the exact CDN packages the templates use. Inline *styles* stay allowed:
post bodies carry colours and sizes as ``style`` attributes, and styles
cannot run code.

When a template starts loading a script from another CDN path, add it to
``SCRIPT_SOURCES``. ``settings.CSP_REPORT_ONLY`` sends the policy as
``Content-Security-Policy-Report-Only`` (the browser only reports, in its
console) to try changes safely.
"""
from app.config import settings

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
    # 글 본문의 style 속성과 편집기가 넣는 스타일 때문에 인라인 스타일은 허용
    "style-src": ("'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net", "https://fonts.googleapis.com"),
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


def policy() -> str:
    """Return the policy as a header value."""
    return "; ".join(f"{name} {' '.join(sources)}" for name, sources in DIRECTIVES.items())


def header_name() -> str:
    """Return the header to send it in (report-only while trying changes)."""
    return "Content-Security-Policy-Report-Only" if settings.CSP_REPORT_ONLY else "Content-Security-Policy"
