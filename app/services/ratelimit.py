"""
간단한 슬라이딩 윈도우 레이트리밋 (동기 엔드포인트용).
Redis 가능 시 Redis, 아니면 프로세스 내 in-memory 폴백.

가입/로그인/댓글 같은 공개 쓰기 동작의 남용(스팸·무차별 대입)을 완화한다.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

from app.config import settings

_mem: dict[str, list[float]] = defaultdict(list)
_lock = threading.Lock()


def _mem_allowed(key: str, limit: int, window: int) -> bool:
    now = time.time()
    with _lock:
        recent = [t for t in _mem[key] if now - t < window]
        if len(recent) >= limit:
            _mem[key] = recent
            return False
        recent.append(now)
        _mem[key] = recent
        return True


def _allow(key: str, limit: int, window: int) -> bool:
    """허용이면 True, 초과면 False."""
    try:
        import redis

        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        now = time.time()
        rk = f"rl:{key}"
        pipe = r.pipeline()
        pipe.zremrangebyscore(rk, 0, now - window)
        pipe.zadd(rk, {repr(now): now})
        pipe.zcard(rk)
        pipe.expire(rk, window)
        count = pipe.execute()[2]
        try:
            r.close()
        except Exception:
            pass
        return count <= limit
    except Exception:
        # Redis 미가용 → in-memory 폴백 (단일 노드 기준 충분)
        return _mem_allowed(key, limit, window)


def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce(
    request: Request,
    action: str,
    limit: int,
    window: int,
    *,
    subject: str | None = None,
    message: str = "요청이 너무 많습니다. 잠시 후 다시 시도해주세요.",
) -> None:
    """초과 시 429 발생. subject 미지정 시 클라이언트 IP 기준."""
    key = f"{action}:{subject or client_ip(request)}"
    if not _allow(key, limit, window):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=message)
