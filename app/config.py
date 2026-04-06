from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "FastAPI Blog & Board"
    DATABASE_URL: str = "sqlite:///./app.db"
    SECRET_KEY: str  # .env에서 읽어옵니다. 값이 없으면 실행 시 에러 발생

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

    # 영어 교정 모델 — 두 모델 모두 시작 시 로드, 요청마다 선택 가능
    # vennify : vennify/t5-base-grammar-correction (~250M, 빠름)
    # coedit  : grammarly/coedit-large             (~780M, 고품질)
    SPELLCHECK_EN_DEFAULT_VARIANT: str = "vennify"  # API 요청에 variant 미지정 시 기본값

    # Celery 워커 메모리 상한 (KB 단위)
    # 한국어 모델 1.2GB + 영어 모델 0.4GB + 여유 → 3GB
    # M4 32GB에선 넉넉하게 설정
    SPELLCHECK_WORKER_MEMORY_KB: int = 3_145_728  # 3 GB

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
