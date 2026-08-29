"""Fail the build when the documentation and the code disagree.

Documentation drifts silently: a setting is renamed, a command is removed, an endpoint
moves, and the file that told an operator what to type keeps saying the old thing. Every
check here has already caught a real mismatch in this repository - links pointing at a
directory that never existed, a README claiming the watchlist could not drive a scan
after it could, and specification documents naming CLI commands that were never built.

The numbered design documents under docs/ are exempt from the command and endpoint
checks: they describe the original "VCB-Alt v3.0" target rather than the build, and each
one says so in a banner. They are still checked for broken links.

Usage:
    python tools/check_docs.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Original specifications, not descriptions of the build. See the banner in each file.
DESIGN_DOCS = {
    "00_Master_Index.md",
    "01_PRD.md",
    "02_Tech_Architecture.md",
    "03_Data_Schema.md",
    "04_API_Spec.md",
    "05_Algorithm_Spec.md",
    "06_to_11_Combined.md",
    "AUDIT_REPORT.md",
}

# Settings named by forward-looking plans that nothing reads yet. Each entry is a promise
# that the plan still describes future work; delete it when the setting is implemented.
PLANNED_SETTINGS = {
    "ALERT_WEBHOOK_URL",  # MONITORING_ALERTING_PLAN.md
    "AUTH_PROVIDER",  # AUTH_MFA_RBAC_PLAN.md
}

LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def tracked_markdown() -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    return [ROOT / name for name in output]


def check_links(paths: list[Path]) -> list[str]:
    problems: list[str] = []
    for path in paths:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for target in LINK.findall(line):
                target = target.split()[0].strip()
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                resolved = (path.parent / target.split("#", 1)[0]).resolve()
                if not resolved.exists():
                    problems.append(f"{_rel(path)}:{number}: broken link -> {target}")
    return problems


def check_settings(paths: list[Path]) -> list[str]:
    # Settings are read in two places: config.py builds AppConfig, and a few are read
    # directly by tests and tools (VCB_ALT_TEST_DATABASE_URL gates the PostgreSQL suite).
    sources = list((ROOT / "vcb_alt").glob("*.py")) + list((ROOT / "tests").glob("*.py"))
    sources += list((ROOT / "tools").glob("*.py")) + list((ROOT / "api").glob("*.py"))
    implemented: set[str] = set()
    for source in sources:
        text = source.read_text(encoding="utf-8")
        implemented |= set(re.findall(r'get\("([A-Z_0-9]+)"', text))
        implemented |= set(re.findall(r'VCB_ALT_([A-Z_0-9]+)', text))
    problems: list[str] = []
    for path in paths:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for name in re.findall(r"VCB_ALT_([A-Z_0-9]+)", line):
                if name in implemented or name in PLANNED_SETTINGS:
                    continue
                problems.append(f"{_rel(path)}:{number}: VCB_ALT_{name} is documented but never read")
    return problems


def check_commands(paths: list[Path]) -> list[str]:
    cli = (ROOT / "vcb_alt" / "cli.py").read_text(encoding="utf-8")
    commands = set(re.findall(r'add_parser\("([a-z-]+)"', cli))
    problems: list[str] = []
    for path in paths:
        if path.name in DESIGN_DOCS:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for command in re.findall(r"python -m vcb_alt ([a-z-]+)", line):
                if command not in commands:
                    problems.append(f"{_rel(path)}:{number}: '{command}' is not a CLI command")
    return problems


def check_endpoints(paths: list[Path]) -> list[str]:
    source = "".join(
        (ROOT / "vcb_alt" / name).read_text(encoding="utf-8") for name in ("web_api.py", "web.py")
    )
    exact = set(re.findall(r'path == "(/api/[a-z0-9/_-]+)"', source))
    prefixes = set(re.findall(r'path\.startswith\("(/api/[a-z0-9/_-]+)"', source))
    problems: list[str] = []
    for path in paths:
        if path.name in DESIGN_DOCS:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for endpoint in re.findall(r"(/api/[a-z0-9/_-]+)", line):
                # Prose writes patterns like `/api/user/*` and `/api/user/...`; the regex
                # stops at the wildcard, leaving a trailing slash. Those are not routes.
                if endpoint.endswith("/"):
                    continue
                if endpoint in exact or any(endpoint.startswith(prefix) for prefix in prefixes):
                    continue
                problems.append(f"{_rel(path)}:{number}: {endpoint} is not a served route")
    return problems


def _rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def main() -> int:
    paths = tracked_markdown()
    problems: list[str] = []
    for check in (check_links, check_settings, check_commands, check_endpoints):
        problems.extend(check(paths))
    if problems:
        print(f"documentation is out of step with the code ({len(problems)} problems):")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(f"docs ok ({len(paths)} files: links, settings, commands, endpoints)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
