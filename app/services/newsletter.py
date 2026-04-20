from __future__ import annotations

import hashlib
import hmac
import html
import smtplib
import time
from email.message import EmailMessage

from app.config import settings


def _normalized_email(email: str) -> str:
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
    normalized = _normalized_email(email)
    if issued_at <= 0:
        return False

    if max_age_seconds is not None:
        now = int(time.time())
        if (now - issued_at) > max_age_seconds:
            return False

    expected_token, _ = build_unsubscribe_token(normalized, issued_at=issued_at)
    return hmac.compare_digest(expected_token, (token or "").strip())


def _smtp_config_ready() -> bool:
    return bool(
        settings.NEWSLETTER_ENABLE_SEND
        and settings.NEWSLETTER_SMTP_HOST.strip()
        and settings.NEWSLETTER_FROM_EMAIL.strip()
    )


def _send_email(subject: str, to_email: str, text_body: str, html_body: str | None = None) -> tuple[bool, str]:
    if not _smtp_config_ready():
        return False, "SMTP_NOT_CONFIGURED"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{settings.NEWSLETTER_FROM_NAME} <{settings.NEWSLETTER_FROM_EMAIL}>"
    msg["To"] = to_email
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
                server.send_message(msg)
        else:
            with smtplib.SMTP(host=host, port=port, timeout=timeout) as server:
                if settings.NEWSLETTER_SMTP_USE_TLS:
                    server.starttls()
                if username:
                    server.login(username, password)
                server.send_message(msg)
        return True, "SENT"
    except Exception as exc:
        return False, f"SEND_FAILED:{exc}"


def send_verification_email(to_email: str, verify_url: str) -> tuple[bool, str]:
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


def send_subscription_confirmed_email(to_email: str, unsubscribe_url: str) -> tuple[bool, str]:
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
