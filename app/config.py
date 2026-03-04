from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "FastAPI Blog & Board"
    DATABASE_URL: str = "sqlite:///./app.db"
    SECRET_KEY: str  # .env에서 읽어옵니다. 값이 없으면 실행 시 에러 발생

    # Celery (현재 글쓰기에는 사용하지 않고, 나중에 heavy 작업용으로 활용 가능)
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
