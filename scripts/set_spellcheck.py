"""Grant or revoke spell-check access from the command line.

Levels: 0 none, 1 the fast models (et5, T5-base), 2 the large models too
(pko, CoEdIT). Admins always have level 2. The admin page (/admin/) does the
same for one account at a time.

Usage:
    python3 scripts/set_spellcheck.py writer@example.com 1   # fast models
    python3 scripts/set_spellcheck.py writer@example.com 0   # revoke
    python3 scripts/set_spellcheck.py --list                 # accounts with access
    # Docker (stack running / not running):
    docker compose exec web python3 scripts/set_spellcheck.py writer@example.com 1
    docker compose run --rm --no-deps -e RUN_MIGRATIONS=0 web python3 scripts/set_spellcheck.py writer@example.com 1
"""
from __future__ import annotations

import argparse
import os
import sys

# 프로젝트 루트에서 실행한다고 가정하고 app 패키지를 import 할 수 있게 한다.
sys.path.insert(0, os.getcwd())

from app.database import SessionLocal  # noqa: E402
from app import models  # noqa: E402
from app.services.spellcheck_access import LEVEL_LABELS, effective_level  # noqa: E402


def list_access(db) -> list[tuple[str, int, bool]]:
    """Return the accounts that can use spell check.

    Args:
        db: Database session.

    Returns:
        ``(email, level, is_admin)`` for every account whose effective level
        is above 0, sorted by email.
    """
    users = db.query(models.User).all()
    rows = [(u.email, effective_level(u), bool(u.is_admin)) for u in users]
    return sorted(r for r in rows if r[1] > 0)


def set_level(db, email: str, level: int) -> bool:
    """Store an account's spell-check level and commit.

    Args:
        db: Database session.
        email: The account's email; trimmed and lower-cased like at signup.
        level: A key of ``LEVEL_LABELS``.

    Returns:
        True if the account exists (and was updated), False otherwise.
    """
    user = db.query(models.User).filter(models.User.email == email.strip().lower()).first()
    if not user:
        return False
    user.spellcheck_level = level
    db.commit()
    return True


def main() -> int:
    """Parse the command line and set or list spell-check access.

    Returns:
        The process exit code: 0 on success, 1 when the account does not exist.
    """
    parser = argparse.ArgumentParser(description="Grant or revoke spell-check access.")
    parser.add_argument("email", nargs="?", help="email of an existing account")
    parser.add_argument("level", nargs="?", type=int, choices=sorted(LEVEL_LABELS), help="0 none, 1 fast models, 2 large models too")
    parser.add_argument("--list", action="store_true", help="list accounts with access")
    args = parser.parse_args()
    if not args.list and (args.email is None or args.level is None):
        parser.error("an email and a level, or --list, are required")

    db = SessionLocal()
    try:
        if args.list:
            for email, level, is_admin in list_access(db):
                print(f"{email}\t{level} ({LEVEL_LABELS[level]}){' [admin]' if is_admin else ''}")
            return 0
        if not set_level(db, args.email, args.level):
            print(f"no account with email {args.email}", file=sys.stderr)
            return 1
        print(f"{args.email}: spell check level {args.level} ({LEVEL_LABELS[args.level]})")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
