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

from celery.signals import worker_ready
from app.tasks import celery_app


@worker_ready.connect
def preload_models(**kwargs):
    """
    Celery 워커 준비 완료 시 모델 미리 로드.

    --pool=solo 사용 시 fork가 발생하지 않으므로:
      - worker_process_init 대신 worker_ready 시그널 사용
      - MPS fork 충돌 문제 없음 (단일 프로세스)
      - 그러나 macOS CPU를 명시 지정해 안전하게 실행

    == 왜 --pool=solo 를 쓰는가 ==
      prefork(기본값)는 요청마다 자식 프로세스를 fork함.
      fork 시 부모 메모리(모델 2.4GB)가 COW로 복사 시도 →
      여유 RAM 부족 시 OS가 SIGKILL.
      solo는 단일 프로세스에서 순차 실행 → fork 없음 → OOM 없음.
      맞춤법 워커는 concurrency=1 이므로 solo와 동일한 처리량.
    """
    import os
    os.environ["SPELLCHECK_DEVICE"] = "cpu"
    print("[CeleryWorker] CPU 모드 고정 (solo pool)")

    try:
        from app.services.spellcheck import load_all
        print("[CeleryWorker] 모든 맞춤법 모델 로딩 (ko + vennify + coedit)...")
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
def run_spellcheck(
    self,
    text: str,
    en_variant: str = "vennify",
    ko_variant: str = "et5",
) -> dict:
    """
    맞춤법 교정 태스크.
      en_variant: "vennify" (빠름) | "coedit" (고품질)
      ko_variant: "et5"    (빠름) | "pko"    (고품질)
    두 언어 4개 모델 모두 워커 시작 시 사전 로드됨.
    """
    from app.services.spellcheck import correct, detect_lang, model_info
    try:
        lang = detect_lang(text)
        corrected = correct(text, en_variant=en_variant, ko_variant=ko_variant)
        return {
            "original": text,
            "corrected": corrected,
            "lang": lang,
            "model": model_info(text, en_variant, ko_variant),
        }
    except Exception as exc:
        raise self.retry(exc=exc)
