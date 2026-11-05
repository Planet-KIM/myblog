"""Cross-site request check for state-changing requests (CSRF defense).

The session cookie is ``SameSite=Lax``, which keeps it off cross-site POSTs,
but that does not stop every forged request: a cross-site form can still log
the visitor in to the attacker's account (login needs no cookie), and sites
on the same host with another port count as "same-site" for cookies. Every
browser sends ``Origin`` on POST, PUT, PATCH and DELETE, so those requests
are accepted only from the site's own host or an origin listed in
``settings.TRUSTED_ORIGINS``. Requests without ``Origin`` or ``Referer``
(curl, server-to-server) are not cross-site browser requests and pass.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from starlette.requests import Request

from app.config import settings

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _host_of(origin: str) -> str | None:
    """Return the ``host[:port]`` of an origin or URL, lower-cased, or None if it has none."""
    netloc = urlsplit(origin.strip()).netloc
    return netloc.lower() or None


def trusted_hosts(request: Request) -> set[str]:
    """Return the hosts a state-changing request may come from.

    Args:
        request: The incoming request.

    Returns:
        The request's own ``Host`` (as nginx passes it on) plus the hosts of
        ``settings.TRUSTED_ORIGINS``.
    """
    hosts = {h for h in (_host_of(o) for o in settings.TRUSTED_ORIGINS.split(",") if o.strip()) if h}
    own = request.headers.get("host", "").strip().lower()
    if own:
        hosts.add(own)
    return hosts


def is_cross_site(request: Request) -> bool:
    """Return True if a state-changing request was sent by another site's page.

    Only POST, PUT, PATCH and DELETE are checked. The request's ``Origin``
    header is compared with :func:`trusted_hosts` (``Referer`` when there is
    no ``Origin``). ``Origin: null`` (sandboxed frames, some redirects) is
    treated as cross-site.

    Args:
        request: The incoming request.

    Returns:
        True to refuse the request.
    """
    if request.method not in UNSAFE_METHODS:
        return False
    origin = request.headers.get("origin")
    if origin is None:
        origin = request.headers.get("referer")
        if origin is None:
            return False
    if origin.strip().lower() == "null":
        return True
    host = _host_of(origin)
    return host is None or host not in trusted_hosts(request)
