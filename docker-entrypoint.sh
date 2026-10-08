#!/bin/sh
# ============================================================
# 컨테이너 시작 훅
#   RUN_MIGRATIONS=1 인 서비스(web)에서만 DB 마이그레이션을 먼저 적용하고,
#   그다음 원래 커맨드(gunicorn / celery …)를 실행한다.
#   alembic upgrade head 는 멱등(이미 최신이면 no-op)이라 매번 떠도 안전.
# ============================================================
set -e

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  echo "[entrypoint] DB 마이그레이션 적용: alembic upgrade head"
  alembic upgrade head
  echo "[entrypoint] 마이그레이션 완료 (head)"
fi

exec "$@"
