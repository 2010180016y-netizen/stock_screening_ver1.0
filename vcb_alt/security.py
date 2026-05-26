from __future__ import annotations

import re
from typing import Any

SECRET_KEYWORDS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASS")
SECRET_VALUE_RE = re.compile(r"(?i)(sk-[a-z0-9_-]{8,}|[a-z0-9_-]{24,})")


def redact_text(value: str) -> str:
    return SECRET_VALUE_RE.sub("[REDACTED]", value)


def redact_value(key: str, value: Any) -> Any:
    if any(keyword in key.upper() for keyword in SECRET_KEYWORDS):
        return "[REDACTED]" if value else value
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return redact_dict(value)
    if isinstance(value, list):
        return [redact_value(key, item) for item in value]
    return value


def redact_dict(values: dict[str, Any]) -> dict[str, Any]:
    return {key: redact_value(key, value) for key, value in values.items()}

