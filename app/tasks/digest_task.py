"""주간 다이제스트 발송 Celery 태스크 (beat 스케줄)."""
from app.tasks import celery_app


@celery_app.task(name="app.tasks.digest_task.send_weekly_digest")
def send_weekly_digest():
    from app.config import settings
    from app.database import SessionLocal
    from app.services.digest import send_weekly_digest as _run

    if not settings.DIGEST_ENABLE or not settings.SITE_BASE_URL.strip():
        return {"sent": 0, "skipped": True, "reason": "DIGEST_DISABLED_OR_NO_URL"}

    db = SessionLocal()
    try:
        return _run(db, settings.SITE_BASE_URL)
    finally:
        db.close()
