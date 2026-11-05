"""Newsletter email delivery and signed unsubscribe tokens.

Sends the double-opt-in verification and confirmation emails over SMTP
(settings ``NEWSLETTER_*``) and creates/verifies HMAC unsubscribe tokens keyed
by ``SECRET_KEY``. Sending is a no-op that reports ``SMTP_NOT_CONFIGURED`` when
SMTP is disabled or incomplete.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import re
import smtplib
import time
from email.message import EmailMessage

from app.config import settings

# 주소 하나(addr-spec)만 허용: 쉼표·세미콜론·꺾쇠·따옴표·공백이 있으면 여러 수신자가 될 수 있다
_SINGLE_EMAIL_RE = re.compile(
    r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+"
)
_MAX_EMAIL_LENGTH = 254


def normalize_single_email(raw: str | None) -> str | None:
    """Return one lower-cased email address, or None when ``raw`` is not exactly one.

    Address lists, display names (``Name <a@b>``), quotes, whitespace inside
    the address and anything longer than 254 characters are rejected, so an
    address can never expand into several SMTP recipients.

    Args:
        raw: The address as typed; surrounding whitespace is ignored.

    Returns:
        The normalized address, or None.
    """
    email = (raw or "").strip().lower()
    if len(email) > _MAX_EMAIL_LENGTH or not _SINGLE_EMAIL_RE.fullmatch(email):
        return None
    return email


def _normalized_email(email: str) -> str:
    """Return ``email`` trimmed and lower-cased (``""`` for ``None``)."""
    return (email or "").strip().lower()


def build_unsubscribe_token(email: str, issued_at: int | None = None) -> tuple[str, int]:
    """
    이메일+발급시각 기반 HMAC 토큰 생성.
    반환: (token, issued_at_unix_seconds)
    """
    normalized = _normalized_email(email)
    issued = int(issued_at or time.time())
    payload = f"{normalized}:{issued}"
    digest = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest, issued


def verify_unsubscribe_token(
    email: str,
    token: str,
    issued_at: int,
    max_age_seconds: int | None = None,
) -> bool:
    """Check an unsubscribe token made by :func:`build_unsubscribe_token`.

    The comparison is constant-time and the email is normalized first, so
    case and surrounding whitespace do not matter.

    Args:
        email: Subscriber email the token claims to belong to.
        token: Hex HMAC token from the unsubscribe link.
        issued_at: Unix timestamp the token was issued at (``ts`` in the link).
        max_age_seconds: Reject tokens older than this many seconds; ``None``
            means tokens never expire.

    Returns:
        True if the token matches and has not expired, False otherwise
        (including when ``issued_at`` is not positive).
    """
    normalized = _normalized_email(email)
    if issued_at <= 0:
        return False

    if max_age_seconds is not None:
        now = int(time.time())
        if (now - issued_at) > max_age_seconds:
            return False

    expected_token, _ = build_unsubscribe_token(normalized, issued_at=issued_at)
    return hmac.compare_digest(expected_token, (token or "").strip())


def mail_ready() -> bool:
    """Return True if mail can be sent (sending enabled, SMTP host and sender set)."""
    return _smtp_config_ready()


def _smtp_config_ready() -> bool:
    """Return True if sending is enabled and an SMTP host and sender address are set."""
    return bool(
        settings.NEWSLETTER_ENABLE_SEND
        and settings.NEWSLETTER_SMTP_HOST.strip()
        and settings.NEWSLETTER_FROM_EMAIL.strip()
    )


def _send_email(subject: str, to_email: str, text_body: str, html_body: str | None = None) -> tuple[bool, str]:
    """Send one email through the configured SMTP server.

    Uses implicit SSL or plain SMTP with optional STARTTLS, and logs in only
    when a username is configured. Errors are caught and reported, never raised.
    The recipient must be exactly one address (see
    :func:`normalize_single_email`), and the SMTP envelope is given that one
    address explicitly, so the mail cannot fan out to a list. This blocks for
    the whole SMTP exchange; async code must call it off the event loop.

    Args:
        subject: Subject line.
        to_email: Recipient address.
        text_body: Plain-text body.
        html_body: Optional HTML alternative body.

    Returns:
        A ``(ok, info)`` pair: ``(True, "SENT")`` on success,
        ``(False, "SMTP_NOT_CONFIGURED")`` when SMTP is not set up,
        ``(False, "INVALID_RECIPIENT")`` when ``to_email`` is not exactly one
        address, or ``(False, "SEND_FAILED:<error>")`` when sending failed.
    """
    if not _smtp_config_ready():
        return False, "SMTP_NOT_CONFIGURED"
    recipient = normalize_single_email(to_email)
    if not recipient:
        return False, "INVALID_RECIPIENT"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{settings.NEWSLETTER_FROM_NAME} <{settings.NEWSLETTER_FROM_EMAIL}>"
    msg["To"] = recipient
    msg.set_content(text_body)

    if html_body:
        msg.add_alternative(html_body, subtype="html")

    host = settings.NEWSLETTER_SMTP_HOST
    port = settings.NEWSLETTER_SMTP_PORT
    timeout = settings.NEWSLETTER_SMTP_TIMEOUT_SECONDS
    username = settings.NEWSLETTER_SMTP_USERNAME.strip()
    password = settings.NEWSLETTER_SMTP_PASSWORD

    try:
        if settings.NEWSLETTER_SMTP_USE_SSL:
            with smtplib.SMTP_SSL(host=host, port=port, timeout=timeout) as server:
                if username:
                    server.login(username, password)
                server.send_message(msg, to_addrs=[recipient])
        else:
            with smtplib.SMTP(host=host, port=port, timeout=timeout) as server:
                if settings.NEWSLETTER_SMTP_USE_TLS:
                    server.starttls()
                if username:
                    server.login(username, password)
                server.send_message(msg, to_addrs=[recipient])
        return True, "SENT"
    except Exception as exc:
        return False, f"SEND_FAILED:{exc}"


def send_verification_email(to_email: str, verify_url: str) -> tuple[bool, str]:
    """Email a new subscriber the link that confirms their subscription.

    Args:
        to_email: Address that asked to subscribe.
        verify_url: Absolute confirmation URL; HTML-escaped in the HTML body.

    Returns:
        The ``(ok, info)`` pair from :func:`_send_email`.
    """
    safe_verify_url = html.escape(verify_url)
    subject = "[Planet KIM's Travel] 이메일 구독 확인"
    text_body = (
        "안녕하세요.\n\n"
        "아래 링크를 열어 뉴스레터 구독을 완료해주세요.\n"
        f"{verify_url}\n\n"
        "이 요청을 본인이 하지 않았다면 이 메일을 무시해주세요.\n"
    )
    html_body = (
        "<p>안녕하세요.</p>"
        "<p>아래 버튼을 눌러 뉴스레터 구독을 완료해주세요.</p>"
        f"<p><a href=\"{safe_verify_url}\">구독 확인하기</a></p>"
        "<p>이 요청을 본인이 하지 않았다면 이 메일을 무시해주세요.</p>"
    )
    return _send_email(subject=subject, to_email=to_email, text_body=text_body, html_body=html_body)


def send_account_verification_email(to_email: str, verify_url: str) -> tuple[bool, str]:
    """Email an account the link that verifies its address.

    Args:
        to_email: The account's address.
        verify_url: Absolute verification URL; HTML-escaped in the HTML body.

    Returns:
        The ``(ok, info)`` pair from :func:`_send_email`.
    """
    safe_verify_url = html.escape(verify_url)
    subject = "[Planet KIM] 이메일 인증"
    text_body = (
        "안녕하세요.\n\n"
        "아래 링크를 열어 이메일 주소를 인증해주세요.\n"
        f"{verify_url}\n\n"
        "가입하지 않았다면 이 메일을 무시해주세요.\n"
    )
    html_body = (
        "<p>안녕하세요.</p>"
        "<p>아래 버튼을 눌러 이메일 주소를 인증해주세요.</p>"
        f"<p><a href=\"{safe_verify_url}\">이메일 인증하기</a></p>"
        "<p>가입하지 않았다면 이 메일을 무시해주세요.</p>"
    )
    return _send_email(subject=subject, to_email=to_email, text_body=text_body, html_body=html_body)


def send_already_subscribed_email(to_email: str, unsubscribe_url: str) -> tuple[bool, str]:
    """Tell a confirmed subscriber that someone asked to subscribe their address again.

    The subscribe form answers the same for every address, so only the
    address owner learns that it is already subscribed.

    Args:
        to_email: The confirmed subscriber's address.
        unsubscribe_url: Absolute signed unsubscribe URL; HTML-escaped in the
            HTML body.

    Returns:
        The ``(ok, info)`` pair from :func:`_send_email`.
    """
    safe_unsubscribe_url = html.escape(unsubscribe_url)
    subject = "[Planet KIM's Travel] 이미 구독 중입니다"
    text_body = (
        "이 주소는 이미 뉴스레터를 구독하고 있습니다.\n"
        "직접 요청하지 않았다면 이 메일은 무시하셔도 됩니다.\n\n"
        "구독 해지:\n"
        f"{unsubscribe_url}\n"
    )
    html_body = (
        "<p>이 주소는 이미 뉴스레터를 구독하고 있습니다.</p>"
        "<p>직접 요청하지 않았다면 이 메일은 무시하셔도 됩니다.</p>"
        f"<p><a href=\"{safe_unsubscribe_url}\">구독 해지</a></p>"
    )
    return _send_email(subject=subject, to_email=to_email, text_body=text_body, html_body=html_body)


def send_subscription_confirmed_email(to_email: str, unsubscribe_url: str) -> tuple[bool, str]:
    """Email a subscriber that their subscription is active, with an unsubscribe link.

    Args:
        to_email: The confirmed subscriber's address.
        unsubscribe_url: Absolute signed unsubscribe URL; HTML-escaped in the
            HTML body.

    Returns:
        The ``(ok, info)`` pair from :func:`_send_email`.
    """
    safe_unsubscribe_url = html.escape(unsubscribe_url)
    subject = "[Planet KIM's Travel] 구독이 완료되었습니다"
    text_body = (
        "구독이 완료되었습니다.\n"
        "새 글 소식을 이메일로 받아보실 수 있습니다.\n\n"
        "구독 해지:\n"
        f"{unsubscribe_url}\n"
    )
    html_body = (
        "<p>구독이 완료되었습니다.</p>"
        "<p>새 글 소식을 이메일로 받아보실 수 있습니다.</p>"
        f"<p><a href=\"{safe_unsubscribe_url}\">구독 해지</a></p>"
    )
    return _send_email(subject=subject, to_email=to_email, text_body=text_body, html_body=html_body)
