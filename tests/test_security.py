# Tests for API auth/CORS security helpers.

import asyncio
import pytest
from fastapi import HTTPException

from src.api.security import (
    get_configured_api_keys,
    get_allowed_origins,
    get_cors_allow_credentials,
    require_api_key,
)


def test_require_api_key_allows_when_auth_disabled(monkeypatch):
    """Auth dependency should no-op when AUTH_ENABLED is false."""
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("API_KEYS", raising=False)

    asyncio.run(require_api_key(None, None))


def test_require_api_key_rejects_missing_key_when_enabled(monkeypatch):
    """Auth dependency should reject requests without API key when enabled."""
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("API_KEY", "topsecret")
    monkeypatch.delenv("API_KEYS", raising=False)

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(require_api_key(None, None))

    assert excinfo.value.status_code == 401


def test_require_api_key_accepts_x_api_key(monkeypatch):
    """Auth dependency should accept X-API-Key header."""
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("API_KEY", "topsecret")
    monkeypatch.delenv("API_KEYS", raising=False)

    asyncio.run(require_api_key("topsecret", None))


def test_require_api_key_accepts_bearer_token(monkeypatch):
    """Auth dependency should accept Bearer token as API key."""
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("API_KEY", "topsecret")
    monkeypatch.delenv("API_KEYS", raising=False)

    asyncio.run(require_api_key(None, "Bearer topsecret"))


def test_require_api_key_fails_when_enabled_but_not_configured(monkeypatch):
    """Auth dependency should fail closed if AUTH_ENABLED=true and API_KEY is missing."""
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("API_KEYS", raising=False)

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(require_api_key(None, None))

    assert excinfo.value.status_code == 500


def test_get_configured_api_keys_combines_api_keys_and_legacy(monkeypatch):
    """Configured key list should include API_KEYS and legacy API_KEY."""
    monkeypatch.setenv("API_KEYS", "k1, k2")
    monkeypatch.setenv("API_KEY", "k3")

    assert get_configured_api_keys() == ["k1", "k2", "k3"]


def test_require_api_key_accepts_any_key_from_api_keys(monkeypatch):
    """Auth dependency should accept any configured key from API_KEYS."""
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("API_KEYS", "alpha,beta")
    monkeypatch.delenv("API_KEY", raising=False)

    asyncio.run(require_api_key("beta", None))


def test_require_api_key_rejects_unknown_api_keys_entry(monkeypatch):
    """Auth dependency should reject keys not in API_KEYS."""
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("API_KEYS", "alpha,beta")
    monkeypatch.delenv("API_KEY", raising=False)

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(require_api_key("gamma", None))

    assert excinfo.value.status_code == 401


def test_get_allowed_origins_from_env(monkeypatch):
    """Allowed origins should be parsed from ALLOWED_ORIGINS."""
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://a.example, https://b.example")

    origins = get_allowed_origins()
    assert origins == ["https://a.example", "https://b.example"]


def test_get_cors_allow_credentials_forces_false_for_wildcard(monkeypatch):
    """Credentials must be disabled if wildcard origin is configured."""
    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "true")

    allow_credentials = get_cors_allow_credentials(["*"])
    assert allow_credentials is False
