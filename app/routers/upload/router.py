from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from starlette import status

from app.auth_utils import get_current_user
from app import models

router = APIRouter(prefix="/api", tags=["upload"])

# app/
BASE_DIR = Path(__file__).resolve().parent.parent
# app/static
STATIC_DIR = BASE_DIR / "static"
# app/static/uploads
UPLOAD_ROOT = STATIC_DIR / "uploads"


def _ensure_upload_dir(user_id: int, post_id: Optional[int] = None) -> Path:
    """
    업로드 저장 디렉토리 보장:
    - /app/static/uploads/<user_id>/
    - /app/static/uploads/<user_id>/<post_id>/ (post_id 있을 때)
    """
    if post_id is None:
        target = UPLOAD_ROOT / str(user_id)
    else:
        target = UPLOAD_ROOT / str(user_id) / str(post_id)

    target.mkdir(parents=True, exist_ok=True)
    return target


@router.post("/images")
async def upload_image(
    file: UploadFile = File(...),
    post_id: Optional[int] = Form(None),
    current_user: models.User = Depends(get_current_user),
):
    """
    Milkdown 에디터에서 사용하는 이미지 업로드 엔드포인트.
    - 프론트: /api/images 로 POST
    - 응답: {"url": "/static/uploads/<user_id>/<post_id?>/<filename>"}
    """

    # 1) 이미지 확장자 검사 (보안 강화)
    ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    suffix = Path(file.filename).suffix.lower()
    
    if suffix not in ALLOWED_EXTENSIONS or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only valid image files (.jpg, .png, .gif, .webp) are allowed.",
        )

    # 2) 저장 디렉토리 생성
    save_dir = _ensure_upload_dir(current_user.id, post_id)

    # 3) 파일명 생성
    filename = f"{uuid4().hex}{suffix}"
    save_path = save_dir / filename

    # 4) 실제 파일 저장
    with save_path.open("wb") as buffer:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            buffer.write(chunk)

    # 5) 브라우저에 돌려줄 URL 생성
    parts = [str(current_user.id)]
    if post_id is not None:
        parts.append(str(post_id))
    parts.append(filename)

    url = "/static/uploads/" + "/".join(parts)
    return {"url": url}
