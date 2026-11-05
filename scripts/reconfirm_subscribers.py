"""Send newsletter subscriptions back to "pending" so their owners confirm by mail.

Before the mail-only confirmation, a server that could not send mail showed
the confirmation link on the subscribe page itself. A subscription confirmed
that way proves nothing about the address: anyone could have typed someone
else's address and clicked the link. This script undoes that:

- every "confirmed" subscription becomes "pending" (confirmation time cleared);
- every confirmation token is cleared, so no link shown on a page can
  confirm anything any more.

Nobody gets mail from it. Once SMTP is set up, people who want the
newsletter subscribe again and confirm through the mail. Unsubscribed rows
stay as they are. Run it only while no subscription was ever confirmed by
mail (SMTP never configured), and back up the database first.

Usage:
    python3 scripts/reconfirm_subscribers.py            # dry run: show what would change
    python3 scripts/reconfirm_subscribers.py --apply    # change it
    # Docker (stack running):
    docker compose exec web python3 scripts/reconfirm_subscribers.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys

# 프로젝트 루트에서 실행한다고 가정하고 app 패키지를 import 할 수 있게 한다.
sys.path.insert(0, os.getcwd())

from app.database import SessionLocal  # noqa: E402
from app import models  # noqa: E402


def mask_email(email: str) -> str:
    """Return ``email`` with most of the local part hidden (``ab***@example.com``)."""
    local, _, domain = email.partition("@")
    return f"{local[:2]}***@{domain}" if domain else "***"


def reset_subscriptions(db, apply: bool) -> tuple[list[str], int]:
    """Find (and with ``apply``, reset) confirmed subscriptions and confirmation tokens.

    Args:
        db: Database session.
        apply: Commit the changes; otherwise nothing is written.

    Returns:
        The confirmed addresses (masked) that become pending, and how many
        rows hold a confirmation token that is cleared.
    """
    Subscriber = models.NewsletterSubscriber
    confirmed = db.query(Subscriber).filter(Subscriber.status == "confirmed").all()
    tokened = db.query(Subscriber).filter(Subscriber.verify_token.isnot(None)).all()
    if apply:
        for row in confirmed:
            row.status = "pending"
            row.confirmed_at = None
        for row in tokened:
            row.verify_token = None
        db.commit()
    return [mask_email(row.email) for row in confirmed], len(tokened)


def main() -> int:
    """Parse the command line, report and (with --apply) reset the subscriptions.

    Returns:
        The process exit code (always 0).
    """
    parser = argparse.ArgumentParser(description="Send confirmed newsletter subscriptions back to pending.")
    parser.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        confirmed, tokens = reset_subscriptions(db, args.apply)
    finally:
        db.close()
    verb = "되돌렸습니다" if args.apply else "되돌릴 예정"
    print(f"확정 → 확인 대기: {len(confirmed)}건 {verb}")
    for email in confirmed:
        print(f"  {email}")
    print(f"확인 토큰 삭제: {tokens}건 {'지웠습니다' if args.apply else '지울 예정'}")
    if not args.apply:
        print("변경하려면 --apply 를 붙여 다시 실행하세요 (먼저 DB 를 백업하세요).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
