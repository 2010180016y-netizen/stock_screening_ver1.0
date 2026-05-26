from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Any


@dataclass
class InMemoryRateLimiter:
    window_seconds: int = 60
    buckets: dict[str, list[float]] = field(default_factory=dict)

    def allow(self, key: str, limit: int) -> bool:
        now = time()
        floor = now - self.window_seconds
        events = [stamp for stamp in self.buckets.get(key, []) if stamp >= floor]
        if len(events) >= limit:
            self.buckets[key] = events
            return False
        events.append(now)
        self.buckets[key] = events
        return True

    def reset(self) -> None:
        self.buckets.clear()


@dataclass
class DatabaseRateLimiter:
    window_seconds: int = 60

    def allow(self, conn: Any, key: str, limit: int) -> bool:
        now = time()
        floor = now - self.window_seconds
        # Durable limiter state lives in the database so multiple serverless
        # processes share one request budget instead of each process granting its own.
        if getattr(conn, "dialect", "") == "postgresql":
            # Serialize each bucket in PostgreSQL so concurrent serverless requests
            # cannot all observe the same pre-insert count and exceed the limit.
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(?))", (key,))
        conn.execute("DELETE FROM rate_limit_events WHERE bucket_key = ? AND created_at < ?", (key, floor))
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM rate_limit_events WHERE bucket_key = ? AND created_at >= ?",
            (key, floor),
        ).fetchone()
        count = int(row["count"])
        if count >= limit:
            conn.commit()
            return False
        conn.execute("INSERT INTO rate_limit_events (bucket_key, created_at) VALUES (?, ?)", (key, now))
        conn.commit()
        return True
