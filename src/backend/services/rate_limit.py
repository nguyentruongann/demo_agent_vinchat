from __future__ import annotations

from functools import lru_cache
import hashlib
import logging
import time

from fastapi import HTTPException
import redis

from src.backend.config import get_settings


logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _client():
    url = str(get_settings().redis_url or "").strip()
    return redis.from_url(
        url,
        socket_connect_timeout=2,
        socket_timeout=2,
        decode_responses=True,
    ) if url else None


def enforce_rate_limit(*, bucket: str, identity: str, limit: int, window_seconds: int) -> None:
    """Apply a Redis fixed-window limit without storing the raw identity."""
    if limit <= 0 or window_seconds <= 0:
        return
    client = _client()
    if client is None:
        return
    digest = hashlib.sha256(str(identity or "anonymous").encode("utf-8")).hexdigest()[:24]
    window = int(time.time()) // window_seconds
    key = f"vinchat:rate:{bucket}:{digest}:{window}"
    try:
        value = int(client.incr(key))
        if value == 1:
            client.expire(key, window_seconds + 5)
    except Exception as exc:  # Keep chat available during a transient Redis incident.
        logger.warning("rate_limit_unavailable bucket=%s error=%s", bucket, type(exc).__name__)
        return
    if value > limit:
        raise HTTPException(
            status_code=429,
            detail="Bạn đang gửi yêu cầu quá nhanh. Vui lòng thử lại sau.",
            headers={"Retry-After": str(window_seconds)},
        )
