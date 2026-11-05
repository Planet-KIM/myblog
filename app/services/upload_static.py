"""The ``/static`` file server, with user uploads served so they cannot run as pages.

Uploads live under ``static/uploads`` on the blog's own origin. A file a
browser opens as a document there (an SVG, an XML/XSLT file, HTML) could run
script with the reader's session. Every upload is therefore sent with a
sandbox CSP and ``nosniff``, and anything other than an image, video or audio
file is sent as a download. nginx.conf applies the same rules where it serves
``/static/uploads/`` itself.
"""
from pathlib import Path

from fastapi.staticfiles import StaticFiles

from app.routers.upload.router import INLINE_MEDIA_EXTENSIONS, UPLOAD_ROOT

_UPLOAD_ROOT = UPLOAD_ROOT.resolve()

# 업로드 미디어의 Content-Type 고정 표 (nginx.conf 의 types 블록과 같음).
# 시스템 mimetypes 에 webp/avif 등이 빠져 있어도 같은 값으로 나가게 한다.
_MEDIA_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif",
    ".webp": "image/webp", ".avif": "image/avif",
    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
    ".avi": "video/x-msvideo", ".mkv": "video/x-matroska",
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".flac": "audio/flac",
}


def is_user_upload(full_path: str) -> bool:
    """Return True if the file on disk is inside the uploads folder.

    Args:
        full_path: The file system path the static server resolved.

    Returns:
        Whether it lies under ``static/uploads`` (after resolving links and ``..``).
    """
    try:
        return Path(full_path).resolve().is_relative_to(_UPLOAD_ROOT)
    except (OSError, ValueError):
        return False


class UploadSafeStaticFiles(StaticFiles):
    """``StaticFiles`` that adds the upload safety headers under ``static/uploads``."""

    def file_response(self, full_path, stat_result, scope, status_code=200):
        """Build the file response, then harden it when the file is a user upload.

        Uploads get ``Content-Security-Policy: sandbox`` and ``nosniff``.
        Images, video and audio (``INLINE_MEDIA_EXTENSIONS``) get their type
        from a fixed table; everything else is sent as
        ``application/octet-stream`` with ``Content-Disposition: attachment``.

        Args:
            full_path: The resolved file path.
            stat_result: Its ``os.stat`` result.
            scope: The ASGI scope.
            status_code: The response status.

        Returns:
            The (possibly hardened) response.
        """
        response = super().file_response(full_path, stat_result, scope, status_code)
        if is_user_upload(full_path):
            response.headers["Content-Security-Policy"] = "sandbox"
            response.headers["X-Content-Type-Options"] = "nosniff"
            suffix = Path(full_path).suffix.lower()
            if suffix in INLINE_MEDIA_EXTENSIONS:
                response.headers["Content-Type"] = _MEDIA_TYPES.get(suffix, "application/octet-stream")
            else:
                response.headers["Content-Type"] = "application/octet-stream"
                response.headers["Content-Disposition"] = "attachment"
        return response
