from datetime import datetime
from .celery_app import celery_app


@celery_app.task
def send_new_post_notification(post_id: int, title: str):
    # 현재는 사용하지 않음. 나중에 무거운 작업/알림용으로 사용 가능.
    print(f"[{datetime.utcnow().isoformat()}] New post created: {post_id} - {title}")
    return {"post_id": post_id, "title": title}
