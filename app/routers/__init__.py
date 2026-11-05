"""HTTP routers for the app, one subpackage or module per feature area.

Re-exports the ``blog``, ``board``, ``admin``, ``auth``, ``upload``, ``api``
and ``spellcheck`` modules; ``app.main`` mounts each one's ``router``.
"""
from . import blog, board, admin, auth, upload, api, spellcheck

__all__ = ["blog", "board", "admin", "auth", "upload", "api", "spellcheck"]
