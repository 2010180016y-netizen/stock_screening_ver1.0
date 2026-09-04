"""Check that a deployed site is running the code in this checkout.

Twenty-two commits once sat in the default branch for four days while production kept
serving the build from before them. Nothing was broken, nothing alerted, and the site
answered every request - the only visible symptom was that a config response was missing
settings that had been added since. This turns that accident into a command.

Two independent signals, because either can be unavailable:

  commit   /api/version reports the build's own commit. Exact, but needs a build stamp.
  surface  /api/config's key set is compared against this checkout's. Coarser, but it
           needs no build metadata at all, and it is what actually caught the drift.

Usage:
    python tools/check_deploy.py https://example.vercel.app
    python tools/check_deploy.py https://example.vercel.app --token "$VCB_ALT_WEB_ACCESS_TOKEN"

Exits non-zero when the deployment is behind, so CI or a release step can gate on it.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vcb_alt.build_info import COMMIT_LENGTH  # noqa: E402
from vcb_alt.config import doctor_report, load_config  # noqa: E402

TIMEOUT_SECONDS = 20

# handle_api adds this to the /api/config response after doctor_report builds it.
EXTRA_CONFIG_KEYS = {"scan_pipeline"}


def fetch(base: str, path: str, token: str) -> dict[str, object] | None:
    request = urllib.request.Request(f"{base.rstrip('/')}{path}")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        print(f"  {path}: unreachable ({exc})")
        return None
    data = body.get("data")
    return data if isinstance(data, dict) else None


def local_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return completed.stdout.strip()[:COMMIT_LENGTH] if completed.returncode == 0 else ""


def check_commit(base: str, token: str) -> list[str]:
    data = fetch(base, "/api/version", token)
    if data is None:
        return [
            "the deployment has no /api/version endpoint, which means it predates this "
            "check - it is already behind"
        ]
    deployed = str(data.get("commit") or "unknown")
    expected = local_commit()
    if not expected:
        print("  commit: skipped (this is not a git checkout)")
        return []
    if deployed == "unknown":
        print(f"  commit: deployed build reports no commit (source: {data.get('commit_source')})")
        return []
    print(f"  commit: deployed {deployed}, local {expected}")
    if deployed != expected:
        return [f"deployment runs commit {deployed}, this checkout is at {expected}"]
    return []


def check_surface(base: str, token: str) -> list[str]:
    data = fetch(base, "/api/config", token)
    if data is None:
        return ["/api/config did not return a configuration report"]
    expected = set(doctor_report(load_config()).keys()) | EXTRA_CONFIG_KEYS
    missing = sorted(expected - set(data.keys()))
    print(f"  surface: {len(data)} settings deployed, {len(expected)} in this checkout")
    if missing:
        return [f"the deployed build is missing {len(missing)} setting(s): {', '.join(missing)}"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("base_url", help="Base URL of the deployment, e.g. https://example.vercel.app")
    parser.add_argument("--token", default="", help="Shared access token, if the site requires one.")
    args = parser.parse_args()

    print(f"checking {args.base_url}")
    problems = check_commit(args.base_url, args.token) + check_surface(args.base_url, args.token)
    if problems:
        print(f"\ndeployment is out of step with this checkout ({len(problems)} problem(s)):")
        for problem in problems:
            print(f"  {problem}")
        print("\nredeploy, then run this again.")
        return 1
    print("\ndeployment matches this checkout")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
