"""Report which build is actually running.

A deploy that silently did not happen looks exactly like one that did: the site answers,
every route works, and only a careful reading of a config response reveals that the code
is weeks old. That is not hypothetical here - twenty-two commits sat in the default
branch for days while production kept serving the build from before them, and it was
found by chance rather than by any check.

So the running build says its own name. tools/check_deploy.py compares that against the
local checkout and fails when they differ.
"""

from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path

from . import __version__

ROOT = Path(__file__).resolve().parents[1]

# Build stamps in the order they are trusted. A serverless bundle ships no .git directory,
# so the platform's own variable is the only identity it has.
COMMIT_ENV_VARS = ("VCB_ALT_BUILD_COMMIT", "VERCEL_GIT_COMMIT_SHA", "GITHUB_SHA")

# Enough to identify a commit, short enough not to hand a reader the full object name.
COMMIT_LENGTH = 12


@lru_cache(maxsize=1)
def build_info() -> dict[str, str]:
    """Version and commit of the running code. Cached: the answer cannot change."""
    commit, source = _resolve_commit()
    return {"version": __version__, "commit": commit, "commit_source": source}


def _resolve_commit() -> tuple[str, str]:
    for name in COMMIT_ENV_VARS:
        value = os.environ.get(name, "").strip()
        if value:
            return value[:COMMIT_LENGTH], name
    if not (ROOT / ".git").exists():
        return "unknown", "unavailable"
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown", "unavailable"
    if completed.returncode != 0:
        return "unknown", "unavailable"
    return completed.stdout.strip()[:COMMIT_LENGTH], "git"
