"""Fail a release build when runtime data or likely credentials are present."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


FORBIDDEN_NAMES = {".env", ".env.local", ".env.production"}
FORBIDDEN_PARTS = {
    "state",
    "diagnostics",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
}

KNOWN_SECRET_PATTERNS = (
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{20,}"),
)
ASSIGNED_SECRET = re.compile(
    r"(?i)[\"']?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"client[_-]?secret|password|cookie)[\"']?\s*[:=]\s*[\"']([^\"'\s]{12,})"
)
PLACEHOLDER_MARKERS = (
    "example",
    "placeholder",
    "your-",
    "your_",
    "change-me",
    "changeme",
    "dummy",
    "test-only",
    "${",
    "<",
)


def find_privacy_violations(root: Path) -> tuple[str, ...]:
    package = Path(root).resolve()
    violations: set[str] = set()
    for path in package.rglob("*"):
        relative = path.relative_to(package)
        if path.name.lower() in FORBIDDEN_NAMES or any(
            part.lower() in FORBIDDEN_PARTS for part in relative.parts
        ):
            violations.add(f"runtime path: {relative.as_posix()}")
            continue
        if not path.is_file():
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            violations.add(f"unreadable file: {relative.as_posix()}")
            continue
        if b"\x00" in raw:
            continue
        text = raw.decode("utf-8", errors="ignore")
        if any(pattern.search(text) for pattern in KNOWN_SECRET_PATTERNS):
            violations.add(f"credential pattern: {relative.as_posix()}")
            continue
        for match in ASSIGNED_SECRET.finditer(text):
            value = match.group(1).lower()
            if not any(marker in value for marker in PLACEHOLDER_MARKERS):
                violations.add(f"assigned secret: {relative.as_posix()}")
                break
    return tuple(sorted(violations))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    violations = find_privacy_violations(args.root)
    if violations:
        print("Release privacy check failed:")
        for violation in violations:
            print(f"- {violation}")
        return 1
    print("release_privacy_check=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
