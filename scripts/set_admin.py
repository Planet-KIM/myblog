"""Grant, revoke or list admin rights from the command line.

The web app never makes anyone an admin: an email typed in at signup is not
verified, so it cannot be trusted. The operator runs this script on the server
for an account that already exists.

Usage:
    python3 scripts/set_admin.py me@example.com            # grant
    python3 scripts/set_admin.py me@example.com --revoke   # revoke
    python3 scripts/set_admin.py --list                    # list admins
    # Docker (stack running / not running):
    docker compose exec web python3 scripts/set_admin.py me@example.com
    docker compose run --rm --no-deps -e RUN_MIGRATIONS=0 web python3 scripts/set_admin.py me@example.com
"""
from __future__ import annotations

import argparse
import os
import sys

# 프로젝트 루트에서 실행한다고 가정하고 app 패키지를 import 할 수 있게 한다.
sys.path.insert(0, os.getcwd())

from app.database import SessionLocal  # noqa: E402
from app import models  # noqa: E402


def list_admins(db) -> list[str]:
    """Return the emails of every admin account, sorted.

    Args:
        db: Database session.

    Returns:
        Admin email addresses.
    """
    rows = db.query(models.User.email).filter(models.User.is_admin == True).all()  # noqa: E712
    return sorted(email for (email,) in rows)


def set_admin(db, email: str, is_admin: bool) -> bool:
    """Set the admin flag of the account with this email and commit.

    Args:
        db: Database session.
        email: The account's email; trimmed and lower-cased like at signup.
        is_admin: True to grant admin rights, False to revoke them.

    Returns:
        True if the account exists (and was updated), False otherwise.
    """
    user = db.query(models.User).filter(models.User.email == email.strip().lower()).first()
    if not user:
        return False
    user.is_admin = is_admin
    db.commit()
    return True


def main() -> int:
    """Parse the command line and grant, revoke or list admins.

    Returns:
        The process exit code: 0 on success, 1 when the account does not exist.
    """
    parser = argparse.ArgumentParser(description="Grant, revoke or list admin rights.")
    parser.add_argument("email", nargs="?", help="email of an existing account")
    parser.add_argument("--revoke", action="store_true", help="revoke instead of grant")
    parser.add_argument("--list", action="store_true", help="list admin accounts")
    args = parser.parse_args()
    if not args.list and not args.email:
        parser.error("an email or --list is required")

    db = SessionLocal()
    try:
        if args.list:
            for email in list_admins(db):
                print(email)
            return 0
        if not set_admin(db, args.email, not args.revoke):
            print(f"no account with email {args.email}", file=sys.stderr)
            return 1
        print(f"{args.email}: admin {'revoked' if args.revoke else 'granted'}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
