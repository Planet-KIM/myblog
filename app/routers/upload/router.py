"""
Upload Router - 통합 파일 업로드 시스템
=========================================
모든 파일 타입(이미지, 문서, 텍스트, 코드, 아카이브, 동영상, 오디오)을
단일 엔드포인트(/api/upload)로 처리합니다.

폴더 구조:
  static/uploads/{user_id}/posts/{post_id}/{type_folder}/
  static/uploads/{user_id}/drafts/{draft_id}/{type_folder}/

엔드포인트:
  POST /api/upload             - 통합 파일 업로드
  POST /api/images             - 이미지 전용 (하위 호환)
  GET  /api/files/{post_id}    - 게시글 첨부파일 목록
  DELETE /api/files/{file_id}  - 파일 개별 삭제
"""

import shutil
from pathlib import Path
from typing import Optional, Tuple
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from starlette import status

from app.auth_utils import get_current_user, get_current_user_optional
from app import models
from app.database import get_db

router = APIRouter(prefix="/api", tags=["upload"])

# ── 경로 설정 ─────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent.parent.parent   # app/
STATIC_DIR = BASE_DIR / "static"
UPLOAD_ROOT = STATIC_DIR / "uploads"

# ── 파일 타입 분류 테이블 ──────────────────────────────────
# key        : 파일 타입명 (UploadedFile.file_type 에 저장)
# extensions : 허용 확장자 (소문자)
# max_mb     : 최대 파일 크기
# folder     : 저장 서브폴더명
FILE_TYPES = {
    "image": {
        "extensions": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".avif"},
        "max_mb": 10,
        "folder": "images",
    },
    "document": {
        "extensions": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".hwp"},
        "max_mb": 50,
        "folder": "documents",
    },
    "text": {
        "extensions": {".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml", ".toml"},
        "max_mb": 5,
        "folder": "files",
    },
    "code": {
        "extensions": {
            ".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp",
            ".sh", ".html", ".css", ".sql", ".rb", ".php", ".swift", ".kt",
        },
        "max_mb": 5,
        "folder": "files",
    },
    "archive": {
        "extensions": {".zip", ".tar", ".gz", ".7z", ".rar", ".bz2"},
        "max_mb": 100,
        "folder": "files",
    },
    "video": {
        "extensions": {".mp4", ".webm", ".mov", ".avi", ".mkv"},
        "max_mb": 500,
        "folder": "videos",
    },
    "audio": {
        "extensions": {".mp3", ".wav", ".ogg", ".m4a", ".flac"},
        "max_mb": 50,
        "folder": "audio",
    },
}

OTHER_CONFIG = {"max_mb": 20, "folder": "files"}


def _classify_file(suffix: str):
    """확장자로 파일 타입과 설정을 반환합니다."""
    for type_name, config in FILE_TYPES.items():
        if suffix in config["extensions"]:
            return type_name, config
    return "other", OTHER_CONFIG


def _get_upload_dir(
    user_id: int,
    type_folder: str,
    post_id: Optional[int] = None,
    draft_id: Optional[str] = None,
) -> Tuple[Path, str]:
    """
    저장 디렉토리와 서빙 URL prefix를 반환합니다.

    우선순위: post_id > draft_id > tmp
    """
    if post_id is not None:
        parts = [str(user_id), "posts", str(post_id), type_folder]
    elif draft_id is not None:
        parts = [str(user_id), "drafts", str(draft_id), type_folder]
    else:
        parts = [str(user_id), "drafts", "tmp", type_folder]

    target = UPLOAD_ROOT.joinpath(*parts)
    target.mkdir(parents=True, exist_ok=True)
    url_prefix = "/static/uploads/" + "/".join(parts)
    return target, url_prefix


# ============================================================
# ★ 통합 파일 업로드
# ============================================================
@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    post_id: Optional[int] = Form(None),
    draft_id: Optional[str] = Form(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    모든 파일 타입을 처리하는 통합 업로드 엔드포인트.
    - 파일 타입을 자동 감지하여 적절한 폴더에 저장합니다.
    - 업로드 기록을 DB(uploaded_files)에 저장합니다.
    - 응답: {"url": "...", "file_type": "...", "size_bytes": ...}
    """
    suffix = Path(file.filename or "unknown").suffix.lower()
    file_type, type_config = _classify_file(suffix)

    # 파일 내용 읽기 (크기 검사 포함)
    content = await file.read()
    size_bytes = len(content)
    max_bytes = type_config["max_mb"] * 1024 * 1024

    if size_bytes > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"파일이 너무 큽니다. 최대 허용: {type_config['max_mb']}MB",
        )

    if size_bytes == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="빈 파일은 업로드할 수 없습니다.",
        )

    # 저장 디렉토리 결정
    save_dir, url_prefix = _get_upload_dir(
        current_user.id, type_config["folder"], post_id, draft_id
    )

    # 파일명: uuid + 원본 확장자
    stored_name = f"{uuid4().hex}{suffix}"
    save_path = save_dir / stored_name

    # 디스크 저장
    save_path.write_bytes(content)

    url = f"{url_prefix}/{stored_name}"

    # DB 기록
    record = models.UploadedFile(
        user_id=current_user.id,
        post_id=post_id,
        draft_id=draft_id,
        file_type=file_type,
        original_name=file.filename or stored_name,
        stored_name=stored_name,
        file_path=str(save_path),
        url=url,
        size_bytes=size_bytes,
        mime_type=file.content_type or "application/octet-stream",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {"url": url, "file_type": file_type, "size_bytes": size_bytes, "file_id": record.id}


# ============================================================
# ★ 이미지 전용 엔드포인트 (하위 호환 유지)
#   기존 빌드된 board_new.js / board_edit.js 가 이 경로를 사용
# ============================================================
@router.post("/images")
async def upload_image_compat(
    file: UploadFile = File(...),
    post_id: Optional[int] = Form(None),
    draft_id: Optional[str] = Form(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    /api/images 하위 호환 엔드포인트.
    내부적으로 /api/upload 와 동일한 로직을 실행합니다.
    이미지가 아닌 파일이 오면 거부합니다.
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in FILE_TYPES["image"]["extensions"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이미지 파일만 허용됩니다 (.jpg, .png, .gif, .webp 등)",
        )
    return await upload_file(file, post_id, draft_id, current_user, db)


# ============================================================
# ★ 게시글 첨부파일 목록 조회
# ============================================================
@router.get("/files/{post_id}")
def get_post_files(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user_optional),
):
    """게시글에 첨부된 모든 파일 목록을 반환합니다."""
    files = (
        db.query(models.UploadedFile)
        .filter(models.UploadedFile.post_id == post_id)
        .order_by(models.UploadedFile.created_at.asc())
        .all()
    )
    return [
        {
            "id": f.id,
            "original_name": f.original_name,
            "url": f.url,
            "file_type": f.file_type,
            "size_bytes": f.size_bytes,
            "mime_type": f.mime_type,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in files
    ]


# ============================================================
# ★ 파일 개별 삭제
# ============================================================
@router.delete("/files/{file_id}")
def delete_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """파일을 디스크와 DB에서 모두 삭제합니다. 본인 파일만 삭제 가능합니다."""
    record = (
        db.query(models.UploadedFile)
        .filter(
            models.UploadedFile.id == file_id,
            models.UploadedFile.user_id == current_user.id,
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")

    # 디스크에서 삭제
    path = Path(record.file_path)
    if path.exists():
        path.unlink()

    db.delete(record)
    db.commit()
    return {"status": "deleted", "file_id": file_id}


# ============================================================
# ★ draft → post 파일 이관 (내부 유틸, 라우터 아님)
# ============================================================
def relocate_draft_files(post: models.BoardPost, draft_id: str, db: Session) -> None:
    """
    draft에 임시 저장된 파일들을 post 폴더로 이동하고
    DB 레코드 및 콘텐츠 URL을 업데이트합니다.

    신규 구조: uploads/{user_id}/drafts/{draft_id}/ → uploads/{user_id}/posts/{post_id}/
    구버전 구조(YYYY/MM/draft_id/): board/router.py의 relocate_draft_images() 가 처리
    """
    import re

    # ── 신규 구조 처리 ─────────────────────────────────────
    draft_base = UPLOAD_ROOT / str(post.user_id) / "drafts" / str(draft_id)
    post_base  = UPLOAD_ROOT / str(post.user_id) / "posts"  / str(post.id)

    url_mapping: dict[str, str] = {}

    if draft_base.exists():
        for type_folder in draft_base.iterdir():
            if not type_folder.is_dir():
                continue
            dest_dir = post_base / type_folder.name
            dest_dir.mkdir(parents=True, exist_ok=True)

            for src_file in type_folder.iterdir():
                if not src_file.is_file():
                    continue
                dest_file = dest_dir / src_file.name

                old_url = (
                    f"/static/uploads/{post.user_id}/drafts/{draft_id}"
                    f"/{type_folder.name}/{src_file.name}"
                )
                new_url = (
                    f"/static/uploads/{post.user_id}/posts/{post.id}"
                    f"/{type_folder.name}/{src_file.name}"
                )

                src_file.rename(dest_file)
                url_mapping[old_url] = new_url

        # 빈 draft 폴더 정리
        shutil.rmtree(draft_base, ignore_errors=True)

    # ── DB 레코드 업데이트 ─────────────────────────────────
    draft_records = (
        db.query(models.UploadedFile)
        .filter(
            models.UploadedFile.draft_id == draft_id,
            models.UploadedFile.post_id.is_(None),
        )
        .all()
    )
    for record in draft_records:
        if record.url in url_mapping:
            new_url = url_mapping[record.url]
            new_path = str(UPLOAD_ROOT / new_url.replace("/static/uploads/", ""))
            record.url       = new_url
            record.file_path = new_path
        record.post_id  = post.id
        record.draft_id = None

    # ── 콘텐츠 URL 치환 ────────────────────────────────────
    if url_mapping and post.content:
        raw_content  = post.content  or ""
        raw_html     = post.content_html or ""
        raw_blocks   = post.content_blocks or ""
        for old, new in sorted(url_mapping.items(), key=lambda kv: len(kv[0]), reverse=True):
            raw_content = raw_content.replace(old, new)
            raw_html    = raw_html.replace(old, new)
            raw_blocks  = raw_blocks.replace(old, new)
        post.content        = raw_content
        post.content_html   = raw_html
        post.content_blocks = raw_blocks

    db.commit()
