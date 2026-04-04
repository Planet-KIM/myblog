"""
migrate_uploads.py
==================
기존 업로드 폴더 구조를 새 구조로 마이그레이션합니다.

기존 구조:
  static/uploads/{user_id}/{YYYY}/{MM}/{post_id}/{filename}

새 구조:
  static/uploads/{user_id}/posts/{post_id}/images/{filename}

실행 방법:
  python migrate_uploads.py [--dry-run]

  --dry-run : 실제로 파일을 이동하지 않고 변경 내용만 출력합니다.

주의:
  - 반드시 백업 후 실행하세요.
  - 이 스크립트는 멱등(idempotent)합니다. 이미 이전된 파일은 건너뜁니다.
  - 실행 후 앱을 재시작하면 새 URL로 서빙됩니다.
"""

import sys
import re
import shutil
from pathlib import Path

# ── 경로 설정 ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "app" / "static"
UPLOAD_ROOT = STATIC_DIR / "uploads"

DRY_RUN = "--dry-run" in sys.argv

# 기존 연도/월 구조 패턴: {user_id}/{YYYY}/{MM}/{post_id}/{filename}
OLD_PATTERN = re.compile(r"^(\d+)/(\d{4})/(\d{2})/(\d+)/(.+)$")


def migrate():
    moved = 0
    skipped = 0
    errors = 0

    if not UPLOAD_ROOT.exists():
        print(f"[ERROR] uploads 폴더가 없습니다: {UPLOAD_ROOT}")
        return

    # user_id 폴더 순회
    for user_dir in sorted(UPLOAD_ROOT.iterdir()):
        if not user_dir.is_dir():
            continue

        user_id = user_dir.name

        # 숫자가 아닌 폴더(posts/, drafts/ 등)는 새 구조 → 건너뜀
        if not user_id.isdigit():
            continue

        # {YYYY} 폴더 순회
        for year_dir in sorted(user_dir.iterdir()):
            if not year_dir.is_dir() or not year_dir.name.isdigit() or len(year_dir.name) != 4:
                continue  # posts/, drafts/ 등 건너뜀

            # {MM} 폴더 순회
            for month_dir in sorted(year_dir.iterdir()):
                if not month_dir.is_dir():
                    continue

                # {post_id} 폴더 순회 (draft_ 폴더는 제외)
                for post_dir in sorted(month_dir.iterdir()):
                    if not post_dir.is_dir():
                        continue
                    if post_dir.name.startswith("draft_"):
                        print(f"  [SKIP] draft 폴더 건너뜀: {post_dir.relative_to(UPLOAD_ROOT)}")
                        skipped += 1
                        continue

                    post_id = post_dir.name
                    if not post_id.isdigit():
                        continue

                    # 파일 순회
                    for src_file in sorted(post_dir.iterdir()):
                        if not src_file.is_file():
                            continue

                        dest_dir = UPLOAD_ROOT / user_id / "posts" / post_id / "images"
                        dest_file = dest_dir / src_file.name

                        rel_src = src_file.relative_to(UPLOAD_ROOT)
                        rel_dst = dest_file.relative_to(UPLOAD_ROOT)

                        if dest_file.exists():
                            print(f"  [SKIP] 이미 존재: {rel_dst}")
                            skipped += 1
                            continue

                        print(f"  [MOVE] {rel_src}  →  {rel_dst}")

                        if not DRY_RUN:
                            try:
                                dest_dir.mkdir(parents=True, exist_ok=True)
                                src_file.rename(dest_file)
                                moved += 1
                            except Exception as e:
                                print(f"  [ERROR] {e}")
                                errors += 1
                        else:
                            moved += 1

                    # 빈 post 폴더 정리
                    if not DRY_RUN:
                        remaining = list(post_dir.iterdir())
                        if not remaining:
                            post_dir.rmdir()

                # 빈 month 폴더 정리
                if not DRY_RUN:
                    remaining = list(month_dir.iterdir())
                    if not remaining:
                        month_dir.rmdir()

            # 빈 year 폴더 정리
            if not DRY_RUN:
                remaining = list(year_dir.iterdir())
                if not remaining:
                    year_dir.rmdir()

    print()
    print("=" * 50)
    if DRY_RUN:
        print(f"[DRY-RUN] 이동될 파일: {moved}개, 건너뜀: {skipped}개")
        print("실제로 적용하려면 --dry-run 없이 실행하세요.")
    else:
        print(f"완료: 이동 {moved}개, 건너뜀 {skipped}개, 오류 {errors}개")


def update_db_urls():
    """
    DB의 content/content_html 에 박힌 기존 URL을 새 URL로 치환합니다.
    uploads 마이그레이션 후에 실행하세요.
    """
    import os
    sys.path.insert(0, str(BASE_DIR))
    os.chdir(BASE_DIR)

    from app.database import SessionLocal
    from app import models

    db = SessionLocal()
    try:
        posts = db.query(models.BoardPost).all()
        updated = 0

        # 기존 URL 패턴: /static/uploads/{uid}/{YYYY}/{MM}/{post_id}/{file}
        old_url_pattern = re.compile(
            r"/static/uploads/(\d+)/(\d{4})/(\d{2})/(\d+)/([^)\s\"']+)"
        )

        for post in posts:
            changed = False

            def replace_url(m):
                uid, yyyy, mm, pid, fname = m.groups()
                return f"/static/uploads/{uid}/posts/{pid}/images/{fname}"

            if post.content:
                new_content = old_url_pattern.sub(replace_url, post.content)
                if new_content != post.content:
                    post.content = new_content
                    changed = True

            if post.content_html:
                new_html = old_url_pattern.sub(replace_url, post.content_html)
                if new_html != post.content_html:
                    post.content_html = new_html
                    changed = True

            if changed:
                updated += 1
                print(f"  [UPDATE] post #{post.id}: {post.title}")

        if DRY_RUN:
            print(f"\n[DRY-RUN] DB 업데이트될 게시글: {updated}개")
            db.rollback()
        else:
            db.commit()
            print(f"\nDB URL 업데이트 완료: {updated}개 게시글")

    finally:
        db.close()


if __name__ == "__main__":
    print(f"{'[DRY-RUN] ' if DRY_RUN else ''}업로드 폴더 마이그레이션 시작...\n")
    migrate()

    print("\nDB URL 업데이트 시작...")
    try:
        update_db_urls()
    except Exception as e:
        print(f"[ERROR] DB 업데이트 실패: {e}")
        print("앱 환경(venv, DATABASE_URL 등)을 확인 후 update_db_urls()를 별도 실행하세요.")
