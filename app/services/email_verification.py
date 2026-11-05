"""Email ownership: verification links and the actions that need a verified email.

Accounts can be opened with any address, so actions that cost the site or
other people something (public posts, comments and reports, uploads,
spell-check requests) need the account to prove it owns its email first.

Verification only applies while it can work: ``EMAIL_VERIFICATION_REQUIRED``
is on (the default) *and* mail can be sent (``NEWSLETTER_ENABLE_SEND`` with
an SMTP host). Without mail nobody could verify, so the checks pass. Admins
always pass, so a mail problem never locks the operator out.

A verification link carries a token signed with ``SECRET_KEY`` that names
the account and its email at sending time; it expires after
``EMAIL_VERIFY_TOKEN_TTL_HOURS`` and stops working if the email changes.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.services import newsletter

_TOKEN_SALT = "email-verify"


def verification_active() -> bool:
    """Return True if email verification is enforced now (required and mail can be sent)."""
    return bool(settings.EMAIL_VERIFICATION_REQUIRED) and newsletter.mail_ready()


def is_verified(user: Optional[models.User]) -> bool:
    """Return True if the account may do actions that need a verified email.

    Args:
        user: The account, or None for a guest.

    Returns:
        True for admins, verified accounts, and everyone while verification
        is not active; False for guests and unverified accounts otherwise.
    """
    if user is None:
        return False
    return bool(user.is_admin) or user.email_verified_at is not None or not verification_active()


def require_verified(user: models.User, action: str) -> None:
    """Refuse an action to an account whose email is not verified.

    Args:
        user: The logged-in account.
        action: What the user tried, for the message (e.g. "댓글을 쓸").

    Raises:
        HTTPException: 403 with a pointer to the verification page.
    """
    if not is_verified(user):
        raise HTTPException(
            status_code=403,
            detail=f"이메일 인증 후 {action} 수 있습니다. /auth/verify-email 에서 인증 메일을 받아주세요.",
        )


def _serializer() -> URLSafeTimedSerializer:
    """Return the signer for verification tokens."""
    return URLSafeTimedSerializer(settings.SECRET_KEY, salt=_TOKEN_SALT)


def make_token(user: models.User) -> str:
    """Return a signed token for ``user``'s current email."""
    return _serializer().dumps({"uid": user.id, "email": user.email})


def confirm_token(db: Session, token: str) -> Optional[models.User]:
    """Verify the account a token names, if the token is valid, and commit.

    Args:
        db: Database session.
        token: The token from the link.

    Returns:
        The verified account, or None when the token is forged, expired, or
        names an account that no longer has that email.
    """
    try:
        data = _serializer().loads(token or "", max_age=settings.EMAIL_VERIFY_TOKEN_TTL_HOURS * 3600)
    except BadSignature:   # SignatureExpired 포함
        return None
    if not isinstance(data, dict):
        return None
    user = db.query(models.User).filter_by(id=data.get("uid")).first()
    if user is None or user.email != data.get("email"):
        return None
    if user.email_verified_at is None:
        user.email_verified_at = models.now_kst().replace(tzinfo=None)
        db.commit()
    return user


def send_verification(user: models.User, base_url: str) -> tuple[bool, str]:
    """Mail ``user`` a verification link.

    Args:
        user: The account.
        base_url: Site URL the link starts with (``SITE_BASE_URL`` when set).

    Returns:
        The ``(ok, info)`` pair from the mailer.
    """
    link = f"{base_url.rstrip('/')}/auth/verify-email?token={make_token(user)}"
    return newsletter.send_account_verification_email(user.email, link)
