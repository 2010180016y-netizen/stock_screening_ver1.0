from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from .config import AppConfig
from .security import redact_dict, redact_text


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def append_file_log(config: AppConfig, level: str, message: str, metadata: dict[str, Any] | None = None) -> None:
    config.log_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": utc_now(),
        "level": level.upper(),
        "message": redact_text(message),
        "metadata": redact_dict(metadata or {}),
    }
    with (config.log_dir / "app.log").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

