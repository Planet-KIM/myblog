"""HTTP routers for the app, one subpackage or module per feature area.

Re-exports the ``blog``, ``board``, ``admin``, ``auth``, ``upload`` and
``api`` modules; ``app.main`` mounts each one's ``router``.
"""
from . import blog, board, admin, auth, upload, api

__all__ = ["blog", "board", "admin", "auth", "upload", "api"]
