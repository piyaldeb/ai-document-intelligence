"""API-key authentication, per-client rate limiting and security headers."""

from __future__ import annotations

import hmac
import time

import redis
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_redis: redis.Redis | None = None


def _redis_client() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(get_settings().redis_url, socket_timeout=1, socket_connect_timeout=1)
    return _redis


def require_api_key(request: Request, key: str | None = Depends(api_key_header)) -> str:
    keys = get_settings().api_key_set
    if not keys:
        return "anonymous"  # auth disabled (local development)
    if not key or not any(hmac.compare_digest(key, k) for k in keys):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API key",
                            headers={"WWW-Authenticate": "ApiKey"})
    return key


def rate_limit(request: Request, key: str = Depends(require_api_key)) -> None:
    """Fixed-window limit per API key / client IP, shared across API replicas via Redis."""
    limit = get_settings().rate_limit_per_minute
    if limit <= 0:
        return
    client = key if key != "anonymous" else (request.client.host if request.client else "unknown")
    bucket = f"rl:{client[-12:]}:{int(time.time() // 60)}"
    try:
        r = _redis_client()
        count = r.incr(bucket)
        if count == 1:
            r.expire(bucket, 70)
    except redis.RedisError:
        return  # fail open: availability over strictness if Redis is briefly unavailable
    if count > limit:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded", headers={"Retry-After": "60"})


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        return response
