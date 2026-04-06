"""
Celery 앱 인스턴스

== 워커 실행 방법 ==
  celery -A app.tasks worker --loglevel=info --concurrency=1

== 메모리 제한 (macOS / Linux) ==
  # Linux: --max-memory-per-child=3145728  (3GB, KB 단위)
  # macOS: ulimit으로 OS 레벨 제한
  celery -A app.tasks worker --loglevel=info --concurrency=1 \\
         --max-memory-per-child=3145728

== 설계 원칙 ==
  - concurrency=1 : 맞춤법 워커는 모델을 공유하므로 단일 프로세스
  - 웹 서버(FastAPI)와 완전히 분리된 별도 프로세스
  - 모델은 worker_process_init 시그널에서 한 번만 로드
"""

from celery import Celery
from app.config import settings

celery_app = Celery(
    "spellcheck_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.spellcheck_task"],
)

celery_app.conf.update(
    # 직렬화
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # 타임존
    timezone="Asia/Seoul",
    enable_utc=True,

    # 결과 보존 시간: 10분 (맞춤법 결과는 짧게 유지)
    result_expires=600,

    # 태스크 타임아웃
    # coedit(780M) 첫 추론은 60~90초 소요 가능 (모델 워밍업)
    # 이후 요청은 10~20초 수준
    task_soft_time_limit=120,
    task_time_limit=130,

    # 워커당 처리 후 프로세스 재시작 (메모리 누수 방지)
    # 100개 처리 후 워커 프로세스 재시작
    worker_max_tasks_per_child=100,

    # 큐 설정 — 맞춤법 전용 큐 분리
    task_routes={
        "app.tasks.spellcheck_task.run_spellcheck": {"queue": "spellcheck"},
    },
    task_default_queue="default",
)
