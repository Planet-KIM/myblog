"""기존 글에 태그를 백필하는 1회성 유지보수 스크립트.

태그가 비어 있는 공개 글에 대해, 의미 있는 후보 태그를 추론해 채운다:
  - 카테고리 이름 (단, normal/일반 같은 제네릭은 제외)
  - 본문 속 진짜 해시태그 (#여행 등). CSS 색상 코드(#000000)·숫자 전용은 제외

기본은 **dry-run**(미리보기)이며, 실제 반영은 ``--apply`` 를 줘야 한다.
태그가 이미 있는 글은 건너뛰므로 여러 번 돌려도 안전(멱등)하다.

사용:
    python3 scripts/backfill_tags.py            # 미리보기
    python3 scripts/backfill_tags.py --apply    # 실제 반영
    # Docker:
    docker compose exec web python3 scripts/backfill_tags.py --apply
"""
from __future__ import annotations

import os
import re
import sys

# 프로젝트 루트에서 실행한다고 가정하고 app 패키지를 import 할 수 있게 한다.
sys.path.insert(0, os.getcwd())

from app.database import SessionLocal  # noqa: E402
from app import models  # noqa: E402
from app.routers.api import process_post_tags  # noqa: E402

GENERIC_CATEGORIES = {"normal", "일반", "기타", "etc", "uncategorized", "미분류", "default"}
HASHTAG_RE = re.compile(r"#([0-9A-Za-z가-힣_]{2,30})")
HEX_RE = re.compile(r"^[0-9a-fA-F]{3,8}$")
MAX_TAGS_PER_POST = 5


def candidate_tags(post, category_name: str | None) -> list[str]:
    """Infer tags for a post from its category and the hashtags in its body.

    The category name (lower-cased) comes first unless it is a generic name
    from ``GENERIC_CATEGORIES``. Then come ``#hashtags`` found in ``content``
    and ``content_html``, skipping ones that look like hex colour codes or are
    all digits. Duplicates are dropped.

    Args:
        post: The ``BoardPost`` to inspect.
        category_name: Name of the post's category, or ``None``.

    Returns:
        Up to ``MAX_TAGS_PER_POST`` lower-cased tag names, possibly empty.
    """
    tags: list[str] = []
    # 1) 의미 있는 카테고리명
    if category_name:
        name = category_name.strip().lower()
        if name and name not in GENERIC_CATEGORIES:
            tags.append(name)
    # 2) 본문 속 진짜 해시태그 (색상코드/숫자 제외)
    source = (post.content or "") + " " + (post.content_html or "")
    for raw in HASHTAG_RE.findall(source):
        t = raw.strip().lower()
        if not t or HEX_RE.match(t) or t.isdigit():
            continue
        if t not in tags:
            tags.append(t)
    return tags[:MAX_TAGS_PER_POST]


def main() -> int:
    """Preview or apply tag backfilling for every untagged public post.

    Without ``--apply`` on the command line nothing is written; with it, tags
    are saved through ``process_post_tags`` (which commits). Posts that
    already have tags are skipped. Prints counts and up to 12 sample posts.

    Returns:
        The process exit code, always 0.
    """
    apply = "--apply" in sys.argv[1:]
    db = SessionLocal()
    posts = (
        db.query(models.BoardPost)
        .filter(models.BoardPost.is_private == False)  # noqa: E712
        .order_by(models.BoardPost.id.asc())
        .all()
    )

    scanned = skipped_tagged = planned = applied = 0
    samples: list[str] = []
    for post in posts:
        scanned += 1
        if post.tags:  # 이미 태그가 있으면 건너뜀 (멱등)
            skipped_tagged += 1
            continue
        cat_name = post.category.name if post.category else None
        cands = candidate_tags(post, cat_name)
        if not cands:
            continue
        planned += 1
        if len(samples) < 12:
            samples.append(f"  [{post.id}] {(post.title or 'Untitled')[:32]!r} -> {cands}")
        if apply:
            process_post_tags(db, post, cands)
            applied += 1

    db.close()
    mode = "APPLIED" if apply else "DRY-RUN (미리보기)"
    print(f"\n=== backfill_tags [{mode}] ===")
    print(f"공개 글 스캔: {scanned} · 이미 태그 있음(건너뜀): {skipped_tagged}")
    print(f"태그 대상: {planned}" + (f" · 실제 반영: {applied}" if apply else ""))
    if samples:
        print("예시:")
        print("\n".join(samples))
    if not apply and planned:
        print("\n반영하려면 --apply 를 붙여 다시 실행하세요.")
    if not planned:
        print("태그를 추론할 수 있는 글이 없습니다 (제네릭 카테고리·플레이스홀더 등).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
