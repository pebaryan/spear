"""Security and HTTP configuration helpers for the API layer."""

from collections import defaultdict, deque
import logging
import os
import secrets
import threading
import time
from typing import Deque, Dict, List, Optional

from fastapi import Header, HTTPException, Request

logger = logging.getLogger(__name__)

_rate_limit_lock = threading.Lock()
_rate_limit_buckets: Dict[str, Deque[float]] = defaultdict(deque)


def _as_bool(value: Optional[str], default: bool = False) -> bool:
    """Parse a boolean-like environment variable value."""
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_positive_int(value: Optional[str], default: int) -> int:
    """Parse a positive integer environment variable."""
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def is_auth_enabled() -> bool:
    """Return whether API authentication is enabled."""
    return _as_bool(os.getenv("AUTH_ENABLED"), default=False)


def get_configured_api_key() -> str:
    """Return legacy single API key."""
    return os.getenv("API_KEY", "").strip()


def get_configured_api_keys() -> List[str]:
    """Return configured API keys from API_KEYS and legacy API_KEY."""
    configured: List[str] = []
    raw = os.getenv("API_KEYS", "")
    for key in raw.split(","):
        key = key.strip()
        if key and key not in configured:
            configured.append(key)

    legacy = get_configured_api_key()
    if legacy and legacy not in configured:
        configured.append(legacy)
    return configured


def get_allowed_origins() -> List[str]:
    """Return CORS origins from ALLOWED_ORIGINS."""
    raw = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost,http://127.0.0.1,http://localhost:3000,http://127.0.0.1:3000",
    )
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if not origins:
        return ["http://localhost", "http://127.0.0.1"]
    return origins


def get_cors_allow_credentials(origins: List[str]) -> bool:
    """Return whether CORS credentials should be enabled."""
    configured = _as_bool(os.getenv("CORS_ALLOW_CREDENTIALS"), default=False)
    if "*" in origins and configured:
        logger.warning(
            "CORS_ALLOW_CREDENTIALS ignored because ALLOWED_ORIGINS contains '*'."
        )
        return False
    return configured


def _extract_presented_api_key(
    x_api_key: Optional[str], authorization: Optional[str]
) -> Optional[str]:
    """Extract API key from X-API-Key or Bearer token header."""
    if x_api_key:
        return x_api_key.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


def is_rate_limit_enabled() -> bool:
    """Return whether API rate limiting is enabled."""
    return _as_bool(os.getenv("RATE_LIMIT_ENABLED"), default=False)


def get_rate_limit_requests() -> int:
    """Return max requests per window for API rate limiting."""
    return _as_positive_int(os.getenv("RATE_LIMIT_REQUESTS"), default=120)


def get_rate_limit_window_seconds() -> int:
    """Return rate-limit window size in seconds."""
    return _as_positive_int(os.getenv("RATE_LIMIT_WINDOW_SECONDS"), default=60)


def _get_rate_limit_client_key(request: Request) -> str:
    """Derive the client identifier used for rate limiting."""
    presented_key = _extract_presented_api_key(
        request.headers.get("X-API-Key"),
        request.headers.get("Authorization"),
    )
    if presented_key:
        return f"key:{presented_key}"

    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",", 1)[0].strip()
        if client_ip:
            return f"ip:{client_ip}"

    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


def _reset_rate_limiter_state_for_tests() -> None:
    """Reset in-memory rate-limiter state (tests only)."""
    with _rate_limit_lock:
        _rate_limit_buckets.clear()


async def enforce_rate_limit(request: Request) -> None:
    """
    Enforce in-memory per-client rate limiting when RATE_LIMIT_ENABLED=true.

    Controls:
    - RATE_LIMIT_ENABLED: true/false
    - RATE_LIMIT_REQUESTS: requests per window (default 120)
    - RATE_LIMIT_WINDOW_SECONDS: window size in seconds (default 60)
    """
    if not is_rate_limit_enabled():
        return

    limit = get_rate_limit_requests()
    window_seconds = get_rate_limit_window_seconds()
    now = time.monotonic()
    window_start = now - window_seconds
    client_key = _get_rate_limit_client_key(request)

    with _rate_limit_lock:
        bucket = _rate_limit_buckets[client_key]
        while bucket and bucket[0] <= window_start:
            bucket.popleft()

        if len(bucket) >= limit:
            retry_after = int(max(1, bucket[0] + window_seconds - now))
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )

        bucket.append(now)


async def require_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> None:
    """
    Enforce API key authentication when AUTH_ENABLED=true.

    Accepts either:
    - `X-API-Key: <key>`
    - `Authorization: Bearer <key>`
    """
    if not is_auth_enabled():
        return

    expected_keys = get_configured_api_keys()
    if not expected_keys:
        logger.error("AUTH_ENABLED=true but API_KEY/API_KEYS are not configured")
        raise HTTPException(
            status_code=500,
            detail="Authentication is enabled but no API keys are configured",
        )

    presented_key = _extract_presented_api_key(x_api_key, authorization)
    if not presented_key:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not any(
        secrets.compare_digest(presented_key, expected_key)
        for expected_key in expected_keys
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")
