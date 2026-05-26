from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [ROOT / "vcb_alt", ROOT / "tests", ROOT / "tools"]
EXCLUDED_PARTS = {"__pycache__", ".venv", "venv", "build", "dist"}


def iter_python_files() -> list[Path]:
    files: list[Path] = []
    for target in TARGETS:
        if not target.exists():
            continue
        for path in target.rglob("*.py"):
            if any(part in EXCLUDED_PARTS for part in path.parts):
                continue
            files.append(path)
    return sorted(files)


def main() -> int:
    errors: list[str] = []
    for path in iter_python_files():
        text = path.read_text(encoding="utf-8")
        try:
            ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            errors.append(f"{path}: syntax error: {exc}")
        for index, line in enumerate(text.splitlines(), start=1):
            if line.rstrip() != line:
                errors.append(f"{path}:{index}: trailing whitespace")
            if "\t" in line:
                errors.append(f"{path}:{index}: tab character")
            if len(line) > 140:
                errors.append(f"{path}:{index}: line too long ({len(line)} > 140)")
    if errors:
        print("\n".join(errors))
        return 1
    print(f"lint ok ({len(iter_python_files())} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

