"""Cache-busting versions for files under ``app/static``."""
from pathlib import Path

STATIC_DIR = Path("app/static")


def asset_version(path: str) -> int:
    """Return a version number for a static file, for ``?v=`` cache busting.

    Templates use it as ``asset_ver('css/home.css')``: the number changes when
    the file is edited or rebuilt, so browsers fetch the new copy.

    Args:
        path: Path relative to ``app/static``.

    Returns:
        The file's modification time in whole seconds, or 0 if it is missing.
    """
    try:
        return int((STATIC_DIR / path).stat().st_mtime)
    except OSError:
        return 0
