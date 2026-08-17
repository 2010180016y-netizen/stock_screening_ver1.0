"""Fail the build when a live-looking secret is committed to the repository.

This project has already leaked a production access token through documentation once
(see the 2026-08-17 entry in RELEASE_DECISION.md at the repository root). Placeholders are
allowed; anything that looks like a real key, token, or connection string is not.

Usage:
    python tools/secret_scan.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANNED_SUFFIXES = {".md", ".py", ".js", ".css", ".html", ".json", ".yml", ".yaml", ".toml", ".sql", ".txt", ".example"}
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    ".playwright-mcp",
    "market_cache",
    "market_universe",
}

# Kept deliberately short. Broad markers hide real leaks, so shape analysis in
# _looks_like_live_secret() does the real work of separating fixtures from secrets.
PLACEHOLDER_MARKERS = (
    "replace-with",
    "your-key",
    "your-secret",
    "example.com",
    "example.invalid",
    "<rotated",
    "changeme",
    "placeholder",
    "redacted",
    "user:password",
)

# This scanner and its test hold realistic secret shapes on purpose, so scanning them
# would always report their own fixtures.
SELF_REFERENTIAL_FILES = {"secret_scan.py", "test_secret_scan.py"}

# (label, pattern, check_value_shape). Rules with check_value_shape=True capture a
# candidate value in group 1 and only report it when it actually looks like a secret;
# the remaining rules match formats that are unambiguous on their own.
RULES: tuple[tuple[str, str, bool], ...] = (
    # No leading \b here on purpose: this project names its secrets VCB_ALT_WEB_ACCESS_TOKEN,
    # VCB_ALT_FINNHUB_API_KEY, and so on, where the keyword is preceded by an underscore.
    (
        "assigned secret",
        r"(?i)(?:api[_-]?key|secret|access[_-]?token|worker[_-]?token|auth[_-]?token|token|password)\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{16,})",
        True,
    ),
    ("query-string token", r"(?i)[?&](?:token|worker_token)=([A-Za-z0-9_\-]{16,})", True),
    ("openai key", r"\bsk-[A-Za-z0-9]{20,}\b", False),
    ("aws access key id", r"\bAKIA[0-9A-Z]{16}\b", False),
    ("github token", r"\bgh[pousr]_[A-Za-z0-9]{20,}\b", False),
    # A credential pointing at localhost cannot expose a hosted database, and CI service
    # containers legitimately carry one in plain text.
    (
        "postgres url with password",
        r"postgres(?:ql)?://[^\s:]+:[^\s@]{6,}@(?!localhost\b|127\.0\.0\.1\b)",
        False,
    ),
    ("private key block", r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", False),
)


def _looks_like_live_secret(value: str) -> bool:
    """Tell a real credential apart from a code identifier or a readable fixture.

    Real tokens carry entropy: a long run mixing letters and digits, or mixed case with
    digits. Identifiers like `web_access_token` and fixtures like `alpaca-secret-value`
    read as words and carry none.
    """
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value) and "_" in value:
        return False
    for run in re.findall(r"[A-Za-z0-9]{12,}", value):
        if re.search(r"[A-Za-z]", run) and re.search(r"\d", run):
            return True
    has_lower = re.search(r"[a-z]", value) is not None
    has_upper = re.search(r"[A-Z]", value) is not None
    has_digit = re.search(r"\d", value) is not None
    return has_lower and has_upper and has_digit


def is_placeholder(line: str) -> bool:
    lowered = line.lower()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def iter_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        if path.name in SELF_REFERENTIAL_FILES:
            continue
        if path.suffix.lower() not in SCANNED_SUFFIXES and path.name != ".env.example":
            continue
        files.append(path)
    return sorted(files)


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def scan_file(path: Path) -> list[str]:
    findings: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return findings
    # Test fixtures legitimately use token-shaped strings such as "1234567890abcdef",
    # so the keyword rules are muted there. Rules that match an unmistakable credential
    # format (provider keys, private keys, database URLs) still apply everywhere.
    keyword_rules_enabled = "tests" not in path.parts
    for number, line in enumerate(text.splitlines(), start=1):
        if is_placeholder(line):
            continue
        for label, pattern, check_value_shape in RULES:
            if check_value_shape and not keyword_rules_enabled:
                continue
            match = re.search(pattern, line)
            if match is None:
                continue
            if check_value_shape and not _looks_like_live_secret(match.group(1)):
                continue
            findings.append(f"{_display_path(path)}:{number}: possible {label}")
            break
    return findings


def main() -> int:
    findings: list[str] = []
    files = iter_files()
    for path in files:
        findings.extend(scan_file(path))
    if findings:
        print("secret scan found potential live credentials:")
        for finding in findings:
            print(f"  {finding}")
        print("\nIf the match is a placeholder, make it obviously fake (for example 'replace-with-...').")
        return 1
    print(f"secret scan ok ({len(files)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
