"""Application settings loaded from the environment and ``.env``.

Import the ready-made ``settings`` instance rather than building ``Settings``
again.
"""
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 예시·흔한 값의 SECRET_KEY 는 거부한다 (세션 쿠키와 구독 해지·이메일 인증 토큰을 위조할 수 있게 된다)
_EXAMPLE_SECRET_KEYS = {"replace_with_long_random_secret", "change-me", "changeme", "secret", "secret-key", "dev", "test"}
MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    """Typed configuration for the whole app, read from env vars and ``.env``.

    Every field can be overridden by an environment variable of the same name.
    ``SECRET_KEY`` has no default, so the app fails to start without it, and
    an example value or one shorter than ``MIN_SECRET_KEY_LENGTH`` characters
    is refused too.

    Attributes:
        PROJECT_NAME: Title of the FastAPI app.
        DATABASE_URL: SQLAlchemy database URL.
        SECRET_KEY: Key that signs the session cookie (required).
        ADMIN_EMAILS: Unused. Admin rights are granted with
            ``scripts/set_admin.py``; the field stays so that existing
            ``.env`` files that still set it keep loading.
        TRUSTED_PROXY_HOPS: Number of reverse proxies in front of the
            bundled nginx that append the client address to
            ``X-Forwarded-For`` (0 when visitors connect to nginx directly).
        SESSION_COOKIE_SECURE: Mark the session cookie ``Secure`` (set it to
            true once the site is served over HTTPS, never before: browsers
            would not send the cookie over plain HTTP and nobody could log in).
        CSP_ENABLED, CSP_REPORT_ONLY: Send the Content-Security-Policy
            (``app/services/csp.py``), and only as report-only while trying
            a change.
        EMAIL_VERIFICATION_REQUIRED: Whether public posts, comments and
            reports, uploads and spell-check requests need a verified email;
            enforced only while mail can be sent (see
            ``app/services/email_verification.py``).
        EMAIL_VERIFY_TOKEN_TTL_HOURS, EMAIL_VERIFY_RESEND_LIMIT: Lifetime of a
            verification link, and links a user may request per hour.
        CORS_ORIGINS: Comma-separated origins (``https://example.com``)
            that may call the API from another site with the visitor's
            cookies. Empty (the default) turns CORS off: the site's own
            pages are same-origin and need none.
        TRUSTED_ORIGINS: Comma-separated extra origins whose pages may send
            POST/PUT/PATCH/DELETE requests (besides the site's own host).
        SIGNUP_RATE_LIMIT, LOGIN_RATE_LIMIT, COMMENT_RATE_LIMIT: Maximum
            requests per sliding window for each action, per client IP.
        SIGNUP_RATE_WINDOW, LOGIN_RATE_WINDOW, COMMENT_RATE_WINDOW: Length of
            those windows in seconds.
        LOGIN_ACCOUNT_RATE_LIMIT, LOGIN_ACCOUNT_RATE_WINDOW: Login attempts
            allowed per account (email) from all IPs together, and the window.
        LAYOUT_TEMPLATE_LIMIT: Most saved magazine templates per user.
        LAYOUT_STORAGE_BUDGET_CHARS: Most layout JSON, in characters, a user
            may keep in posts and templates together.
        LAYOUT_COPY_RATE_LIMIT, LAYOUT_COPY_RATE_WINDOW: Server-side layout
            copies (save as template, new post from a template or starter)
            per user, and the window.
        CATEGORY_MAX_DEPTH, CATEGORY_MAX_PER_USER: Most levels in a user's
            category tree (a top-level category is level 1) and most
            categories per user.
        CATEGORY_NAME_MAX_CHARS, CATEGORY_DESCRIPTION_MAX_CHARS: Longest
            category name and description, in characters after NFC
            normalization (a Hangul syllable counts once, like a Latin letter).
        UPLOAD_MAX_IMAGE_PIXELS: Largest uploaded image, in pixels.
        UPLOAD_USER_QUOTA_MB, UPLOAD_RATE_LIMIT, UPLOAD_DRAFT_TTL_DAYS: Storage
            per user, uploads per user per hour, and days before uploads that
            never joined a post are deleted (at server start).
        CELERY_BROKER_URL, CELERY_RESULT_BACKEND, REDIS_URL: Redis endpoints
            for Celery and the app.
        BOARD_MAX_BODY_SIZE: Largest accepted request body in bytes.
        SPELLCHECK_*: Concurrency, rate limit, input size, default English
            model and worker memory cap for the spell checker; the daily
            quotas per user (all requests, and large-model requests); and the
            access-request rules (account age or a public post first, one
            pending request, a cooldown after a rejection, a cap on pending
            requests site-wide, and submissions per user per day).
        NEWSLETTER_*: Sender identity, SMTP connection, token lifetimes,
            the subscribe rate limits (per client and per address) and the
            longest a subscribe request waits for its mail, and (development
            only) ``NEWSLETTER_SHOW_VERIFY_LINK`` to show the confirmation
            link when no mail can be sent; nothing is sent unless
            ``NEWSLETTER_ENABLE_SEND`` is true.
        SITE_BASE_URL: Absolute site URL used where no request exists (the
            weekly digest).
        DIGEST_ENABLE: Whether the weekly digest is sent.
        GITHUB_*: Repository, token and request options for the GitHub
            Issues dashboard tab.
    """

    PROJECT_NAME: str = "FastAPI Blog & Board"
    DATABASE_URL: str = "sqlite:///./app.db"
    SECRET_KEY: str  # .env에서 읽어옵니다. 값이 없으면 실행 시 에러 발생

    # 더 이상 쓰지 않음: 입력한 이메일 문자열만으로 관리자가 되는 문제가 있어 제거.
    # 관리자 지정은 scripts/set_admin.py 로 한다. 기존 .env 호환을 위해 필드만 남김.
    ADMIN_EMAILS: str = ""

    # nginx 앞단 프록시 수 (Cloudflare, 호스트 nginx/Caddy 등). 없으면 0.
    # X-Forwarded-For 에서 방문자 IP 를 읽을 위치를 정한다 (레이트리밋 키).
    TRUSTED_PROXY_HOPS: int = 0

    # HTTPS 로 서비스할 때 True: 세션 쿠키에 Secure 를 붙여 평문 HTTP 로는 보내지 않게 한다
    SESSION_COOKIE_SECURE: bool = False

    # Content-Security-Policy (app/services/csp.py). REPORT_ONLY 는 막지 않고 브라우저 콘솔에 보고만
    CSP_ENABLED: bool = True
    CSP_REPORT_ONLY: bool = False

    # 이메일 인증: 메일을 보낼 수 있을 때(NEWSLETTER_ENABLE_SEND + SMTP)만 실제로 요구된다
    EMAIL_VERIFICATION_REQUIRED: bool = True
    EMAIL_VERIFY_TOKEN_TTL_HOURS: int = 48
    EMAIL_VERIFY_RESEND_LIMIT: int = 3          # 사용자별 시간당 재발송

    # 다른 사이트에서 쿠키와 함께 API 를 부를 수 있는 출처 (쉼표 구분). 비우면 CORS 끔
    CORS_ORIGINS: str = ""
    # 쓰기 요청(POST 등)을 보내도 되는 다른 출처 (쉼표 구분). 자기 호스트는 항상 허용
    TRUSTED_ORIGINS: str = ""

    # ── 남용 방지 레이트리밋 (IP/유저 기준 슬라이딩 윈도우) ──
    SIGNUP_RATE_LIMIT: int = 5
    SIGNUP_RATE_WINDOW: int = 3600
    LOGIN_RATE_LIMIT: int = 10
    LOGIN_RATE_WINDOW: int = 300
    # 계정(이메일)별 로그인 시도: IP 를 바꿔 가며 한 계정을 노리는 경우 대비.
    # IP 한도보다 넉넉히 둬서, 남이 일부러 막아도 본인이 곧 다시 시도할 수 있게 한다.
    LOGIN_ACCOUNT_RATE_LIMIT: int = 30
    LOGIN_ACCOUNT_RATE_WINDOW: int = 900
    COMMENT_RATE_LIMIT: int = 10
    COMMENT_RATE_WINDOW: int = 60

    # ── 매거진 레이아웃 저장 한도 (사용자별) ──
    LAYOUT_TEMPLATE_LIMIT: int = 30
    LAYOUT_STORAGE_BUDGET_CHARS: int = 64 * 1024 * 1024  # 글자 수 (글 + 템플릿 합계)
    LAYOUT_COPY_RATE_LIMIT: int = 30
    LAYOUT_COPY_RATE_WINDOW: int = 3600

    # ── 카테고리 트리 한도 (사용자별). 이름·설명은 NFC 정규화 뒤 글자 수로 센다
    # (한글 한 글자 = 영문 한 글자). 영어 이름이 더 길어지는 것을 감안해 이름은 60자
    CATEGORY_MAX_DEPTH: int = 5
    CATEGORY_MAX_PER_USER: int = 100
    CATEGORY_NAME_MAX_CHARS: int = 60
    CATEGORY_DESCRIPTION_MAX_CHARS: int = 300

    # 업로드 이미지 최대 픽셀 수 (가로×세로). 압축 해제 폭탄 방지
    UPLOAD_MAX_IMAGE_PIXELS: int = 40_000_000
    # 업로드: 사용자별 저장 용량(MB), 시간당 업로드 수, 글에 붙지 않은 업로드를 지우기까지 일수
    UPLOAD_USER_QUOTA_MB: int = 1024
    UPLOAD_RATE_LIMIT: int = 120
    UPLOAD_DRAFT_TTL_DAYS: int = 14

    # Redis / Celery
    # 로컬 개발: redis://localhost:6379/x
    # Docker:   redis://redis:6379/x
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    REDIS_URL: str = "redis://localhost:6379/2"

    # ── 글 본문 크기 제한 ────────────────────────────────────
    # HTTP form body 최대 크기 (bytes)
    # content_blocks JSON + content_html 합산 기준
    # 기본 50MB: 이미지 없는 순수 텍스트 기준 수백만 자 수용 가능
    BOARD_MAX_BODY_SIZE: int = 50 * 1024 * 1024  # 50MB

    # ── 맞춤법 검사 리소스 제어 ──────────────────────────────
    # M4 32GB 기준으로 설정됨. 메모리/CPU가 다르면 조정 필요.

    # 동시 추론 최대 수 (asyncio Semaphore)
    # M4 32GB: 3 이상도 가능하지만 2로 보수적 설정
    SPELLCHECK_MAX_CONCURRENT: int = 2

    # 유저별 분당 최대 요청 수 (슬라이딩 윈도우 레이트 리미터)
    SPELLCHECK_RATE_LIMIT: int = 20

    # 레이트 리미터 윈도우 (초)
    SPELLCHECK_RATE_WINDOW: int = 60

    # 요청당 최대 글자 수
    SPELLCHECK_MAX_CHARS: int = 10000

    # 승인 뒤 남용 방지: 사용자별 24시간 사용량 (관리자는 제외)
    SPELLCHECK_DAILY_LIMIT: int = 200          # 전체 요청
    SPELLCHECK_LARGE_DAILY_LIMIT: int = 50     # 고품질(대형) 모델 요청

    # 사용 신청 규칙
    SPELLCHECK_REQUEST_MIN_ACCOUNT_DAYS: int = 7   # 가입 후 이 기간이 지나거나 공개 글이 있어야 신청 가능
    SPELLCHECK_REQUEST_COOLDOWN_DAYS: int = 7      # 거절된 뒤 다시 신청하기까지
    SPELLCHECK_REQUEST_PENDING_CAP: int = 100      # 사이트 전체 대기 신청 수 상한
    SPELLCHECK_REQUEST_DAILY_LIMIT: int = 5        # 사용자별 하루 신청·취소 횟수

    # 영어 교정 모델 — 두 모델 모두 시작 시 로드, 요청마다 선택 가능
    # vennify : vennify/t5-base-grammar-correction (~250M, 빠름)
    # coedit  : grammarly/coedit-large             (~780M, 고품질)
    SPELLCHECK_EN_DEFAULT_VARIANT: str = "vennify"  # API 요청에 variant 미지정 시 기본값

    # Celery 워커 메모리 상한 (KB 단위)
    # 한국어 모델 1.2GB + 영어 모델 0.4GB + 여유 → 3GB
    # M4 32GB에선 넉넉하게 설정
    SPELLCHECK_WORKER_MEMORY_KB: int = 3_145_728  # 3 GB

    # ── Newsletter / Email ───────────────────────────────────
    # 실제 발송을 사용하려면 SMTP 설정을 채우고 ENABLE_SEND=true로 둡니다.
    NEWSLETTER_ENABLE_SEND: bool = False
    NEWSLETTER_FROM_EMAIL: str = "no-reply@example.com"
    NEWSLETTER_FROM_NAME: str = "Planet KIM"
    NEWSLETTER_SMTP_HOST: str = ""
    NEWSLETTER_SMTP_PORT: int = 587
    NEWSLETTER_SMTP_USERNAME: str = ""
    NEWSLETTER_SMTP_PASSWORD: str = ""
    NEWSLETTER_SMTP_USE_TLS: bool = True
    NEWSLETTER_SMTP_USE_SSL: bool = False
    NEWSLETTER_SMTP_TIMEOUT_SECONDS: int = 10
    # 개발용: 메일을 못 보낼 때 구독 확인 링크를 응답에 보여 줄지 (운영에서는 꼭 False)
    NEWSLETTER_SHOW_VERIFY_LINK: bool = False
    NEWSLETTER_VERIFY_TOKEN_TTL_HOURS: int = 24
    NEWSLETTER_UNSUBSCRIBE_TOKEN_TTL_HOURS: int = 24 * 30
    # 구독 요청 한도: 클라이언트(IP)별, 주소별
    NEWSLETTER_SUBSCRIBE_RATE_LIMIT: int = 5
    NEWSLETTER_ADDRESS_RATE_LIMIT: int = 3
    NEWSLETTER_SUBSCRIBE_RATE_WINDOW: int = 3600
    # 구독 요청이 확인 메일 발송을 기다리는 최대 시간 (초). 넘으면 응답부터 보냄
    NEWSLETTER_SEND_DEADLINE_SECONDS: int = 15

    # 주간 다이제스트: Celery beat(요청 없음)에서 절대 URL 생성에 사용
    SITE_BASE_URL: str = ""
    DIGEST_ENABLE: bool = False

    # ── GitHub Issues (My Dashboard 탭) ─────────────────────
    # 공개 저장소는 토큰 없이도 조회 가능하지만 rate limit가 낮습니다.
    # private 저장소 또는 높은 호출 빈도에는 token 사용 권장.
    GITHUB_REPO: str = "Planet-KIM/myblog"  # owner/repo
    GITHUB_TOKEN: str = ""
    GITHUB_ISSUES_DEFAULT_STATE: str = "open"  # open | closed | all
    GITHUB_ISSUES_PER_PAGE: int = 20
    GITHUB_ISSUES_TIMEOUT_SECONDS: int = 8

    model_config = SettingsConfigDict(env_file=".env")

    @field_validator("SECRET_KEY")
    @classmethod
    def _strong_secret_key(cls, value: str) -> str:
        """Refuse an example or short ``SECRET_KEY``.

        The key signs the session cookie and the unsubscribe and email
        verification tokens; with a guessable key anyone could forge them.

        Args:
            value: The configured key.

        Returns:
            The key, unchanged.

        Raises:
            ValueError: The key is a known example value or shorter than
                ``MIN_SECRET_KEY_LENGTH`` characters (the app does not start).
        """
        if value.strip().lower() in _EXAMPLE_SECRET_KEYS or len(value.strip()) < MIN_SECRET_KEY_LENGTH:
            raise ValueError(
                f"SECRET_KEY 가 예시 값이거나 {MIN_SECRET_KEY_LENGTH}자보다 짧습니다. 새로 만드세요: "
                "python3 -c 'import secrets; print(secrets.token_urlsafe(48))'"
            )
        return value


settings = Settings()
