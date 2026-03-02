"""Helpers for masking sensitive values before persistence or display."""

from __future__ import annotations

import os
import re
from typing import Any

REDACTED = "[REDACTED]"

_BALANCED_KEY_PATTERN = (
    r"api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password|passwd|authorization"
)
_STRICT_KEY_PATTERN = (
    _BALANCED_KEY_PATTERN
    + r"|client[_-]?secret|id[_-]?token|session(?:id)?|cookie|credential|private[_-]?key|bearer"
)

_ENV_ASSIGN_RE = re.compile(
    r"\b([A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD|PASSWD|AUTH)[A-Z0-9_]*)\s*=\s*([^\s]+)"
)
_JSON_DQ_RE = re.compile(
    r'("?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password|passwd|authorization)"?\s*:\s*")([^"]*)(")',
    re.IGNORECASE,
)
_JSON_SQ_RE = re.compile(
    r"('?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password|passwd|authorization)'?\s*:\s*')([^']*)(')",
    re.IGNORECASE,
)
_BEARER_RE = re.compile(r"(?i)(authorization\s*:\s*bearer\s+)([^\s'\"`]+)")
_OPENAI_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9]{16,}\b")
_AWS_KEY_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_URL_QUERY_SECRET_RE = re.compile(
    r"(?i)([?&](?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password|passwd|authorization|id[_-]?token)=)([^&#\s]+)"
)
_COOKIE_RE = re.compile(r"(?i)(cookie\s*:\s*)([^\r\n]+)")
_PRIVATE_KEY_BLOCK_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
    re.IGNORECASE,
)


def _redaction_profile() -> str:
    profile = str(os.getenv("SPEAR_REDACTION_PROFILE", "balanced") or "").strip().lower()
    if profile in {"off", "balanced", "strict"}:
        return profile
    return "balanced"


def _sensitive_key_re(profile: str) -> re.Pattern[str]:
    base = _STRICT_KEY_PATTERN if profile == "strict" else _BALANCED_KEY_PATTERN
    extra = str(os.getenv("SPEAR_REDACTION_EXTRA_KEYS", "") or "").strip()
    extras = [re.escape(item.strip()) for item in extra.split(",") if item.strip()]
    if extras:
        base = f"{base}|{'|'.join(extras)}"
    return re.compile(rf"({base})", re.IGNORECASE)


def is_sensitive_key(key: Any) -> bool:
    profile = _redaction_profile()
    if profile == "off":
        return False
    return bool(_sensitive_key_re(profile).search(str(key or "")))


def redact_text(text: str) -> str:
    """Mask likely secret/token values in plain text."""
    if text is None:
        return ""
    value = str(text)
    profile = _redaction_profile()
    if profile == "off":
        return value

    value = _BEARER_RE.sub(r"\1" + REDACTED, value)
    value = _ENV_ASSIGN_RE.sub(r"\1=" + REDACTED, value)
    value = _JSON_DQ_RE.sub(r"\1" + REDACTED + r"\3", value)
    value = _JSON_SQ_RE.sub(r"\1" + REDACTED + r"\3", value)
    value = _OPENAI_KEY_RE.sub(REDACTED, value)
    value = _AWS_KEY_RE.sub(REDACTED, value)
    if profile == "strict":
        value = _URL_QUERY_SECRET_RE.sub(r"\1" + REDACTED, value)
        value = _COOKIE_RE.sub(r"\1" + REDACTED, value)
        value = _PRIVATE_KEY_BLOCK_RE.sub(REDACTED, value)
    return value


def redact_object(value: Any) -> Any:
    """Recursively mask sensitive payloads in dict/list/text structures."""
    if _redaction_profile() == "off":
        return value
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if is_sensitive_key(key):
                result[key] = REDACTED
            else:
                result[key] = redact_object(item)
        return result
    if isinstance(value, list):
        return [redact_object(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_object(item) for item in value)
    if isinstance(value, str):
        return redact_text(value)
    return value
