"""Delete uploaded files that no saved post or template uses (one-off cleanup).

Posts now delete their unused uploads whenever they are saved; this script
does the same once for every existing post, for files left behind before
that. A file is unused when the saved post does not show it and no other
post (hidden ones included) or saved template mentions it.

The default is a **dry run** that only lists the files; ``--apply`` deletes
them from disk and from the database.

Usage:
    python3 scripts/prune_uploads.py            # list
    python3 scripts/prune_uploads.py --apply    # delete
    # Docker (stack running / not running):
    docker compose exec web python3 scripts/prune_uploads.py --apply
    docker compose run --rm --no-deps -e RUN_MIGRATIONS=0 web python3 scripts/prune_uploads.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys

# 프로젝트 루트에서 실행한다고 가정하고 app 패키지를 import 할 수 있게 한다.
sys.path.insert(0, os.getcwd())

from app.database import SessionLocal  # noqa: E402
from app import models  # noqa: E402
from app.routers.upload.router import delete_uploads, find_unused_uploads  # noqa: E402


def main() -> int:
    """List, or with ``--apply`` delete, every post's unused uploads.

    Returns:
        The process exit code (always 0).
    """
    parser = argparse.ArgumentParser(description="Delete uploads no saved post or template uses.")
    parser.add_argument("--apply", action="store_true", help="delete instead of listing")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        posts = db.query(models.BoardPost).execution_options(include_hidden=True).all()
        total = 0
        for post in posts:
            unused = find_unused_uploads(db, post)
            for record in unused:
                print(f"[post {post.id}] {record.url}")
            total += len(unused)
            if args.apply:
                delete_uploads(db, unused)
        print(f"\n{'deleted' if args.apply else 'unused (dry run)'}: {total} file(s)")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
