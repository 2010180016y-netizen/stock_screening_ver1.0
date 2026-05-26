from __future__ import annotations

import importlib
import inspect
import pkgutil
import sys
import typing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import vcb_alt


def iter_modules() -> list[str]:
    package_names = [vcb_alt.__name__]
    package_path = vcb_alt.__path__
    for module_info in pkgutil.walk_packages(package_path, prefix=f"{vcb_alt.__name__}."):
        package_names.append(module_info.name)
    return sorted(package_names)


def main() -> int:
    errors: list[str] = []
    checked = 0
    for module_name in iter_modules():
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            errors.append(f"{module_name}: import failed: {exc}")
            continue
        for _, obj in inspect.getmembers(module):
            if getattr(obj, "__module__", None) != module.__name__:
                continue
            if inspect.isfunction(obj) or inspect.isclass(obj):
                try:
                    typing.get_type_hints(obj)
                    checked += 1
                except Exception as exc:
                    errors.append(f"{module_name}.{getattr(obj, '__name__', obj)}: type hints failed: {exc}")
            if inspect.isclass(obj):
                for method_name, method in inspect.getmembers(obj, inspect.isfunction):
                    if getattr(method, "__module__", None) != module.__name__:
                        continue
                    try:
                        typing.get_type_hints(method)
                        checked += 1
                    except Exception as exc:
                        errors.append(f"{module_name}.{obj.__name__}.{method_name}: type hints failed: {exc}")
    if errors:
        print("\n".join(errors))
        return 1
    print(f"type hints ok ({checked} objects)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
