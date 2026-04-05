"""
맞춤법 교정 Celery 태스크

== 구조 ==
  웹 서버(FastAPI)
      ↓  run_spellcheck.delay(text)  — Redis 큐로 전달
  Redis 브로커
      ↓
  Celery 워커 (이 파일)
      ↓  모델 추론 후 결과 Redis에 저장
  웹 서버
      ↓  AsyncResult(task_id).get(timeout=30)
      ↓
  클라이언트 응답

== 워커 실행 ==
  celery -A app.tasks worker --loglevel=info --concurrency=1 -Q spellcheck

== 메모리 제한 (M4 32GB 기준: 3GB) ==
  celery -A app.tasks worker --loglevel=info --concurrency=1 -Q spellcheck \\
         --max-memory-per-child=3145728
"""

from celery.signals import worker_process_init
from app.tasks import celery_app


@worker_process_init.connect
def preload_models(**kwargs):
    """
    Celery 워커 프로세스 시작 직후 모델을 미리 로드.
    첫 번째 태스크 실행 전에 완료되므로 태스크 지연 없음.

    MPS 강제 비활성화:
      Celery는 ForkPoolWorker(fork된 자식 프로세스)로 실행됨.
      macOS에서 fork 이후 MPS(Metal GPU)에 접근하면
      MTLCompilerService 연결이 차단되어 RuntimeError 발생.
      → SPELLCHECK_DEVICE=cpu 로 강제해서 CPU 추론 사용.
    """
    import os
    os.environ["SPELLCHECK_DEVICE"] = "cpu"
    print("[CeleryWorker] MPS 비활성화 (fork 프로세스 제한) → CPU 사용")

    try:
        from app.services.spellcheck import load_all
        print("[CeleryWorker] 맞춤법 모델 사전 로딩...")
        load_all()
        print("[CeleryWorker] 모델 로딩 완료 ✓")
    except Exception as e:
        print(f"[CeleryWorker] 모델 로딩 실패: {e}")


@celery_app.task(
    name="app.tasks.spellcheck_task.run_spellcheck",
    bind=True,
    max_retries=1,
    default_retry_delay=2,
)
def run_spellcheck(self, text: str) -> dict:
    """
    맞춤법 교정 태스크.

    bind=True : self로 태스크 인스턴스 접근 (재시도 등)
    max_retries=1 : 추론 오류 시 1회 재시도
    soft_time_limit=30s : 설정은 __init__.py에서 전역 적용

    반환값:
      {"original": str, "corrected": str, "lang": str, "model": str}
    """
    from app.services.spellcheck import correct, detect_lang, model_info
    try:
        lang = detect_lang(text)
        corrected = correct(text)
        return {
            "original": text,
            "corrected": corrected,
            "lang": lang,
            "model": model_info(text),
        }
    except Exception as exc:
        # 일시적 오류면 재시도, 아니면 그대로 예외 전파
        raise self.retry(exc=exc)
