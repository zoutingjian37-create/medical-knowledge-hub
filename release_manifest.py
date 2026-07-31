"""Build the privacy-safe file list used by the Windows release script."""

import argparse
import subprocess
from pathlib import Path


INCLUDED_FILES = {
    ".dockerignore",
    ".gitattributes",
    ".gitignore",
    "CONTRIBUTORS.md",
    "Dockerfile",
    "LICENSE",
    "README.md",
    "THIRD_PARTY_NOTICES.md",
    "app.py",
    "build-release.ps1",
    "docker-compose.yml",
    "env.example",
    "install-platform-engines.ps1",
    "install.ps1",
    "launch.ps1",
    "release_manifest.py",
    "requirements-wechat-ui.txt",
    "requirements.txt",
    "start.bat",
    "start.sh",
    "status.sh",
}
INCLUDED_PREFIXES = (
    "assets/",
    "docs/",
    "extensions/",
    "routes/",
    "routes_ext/",
    "skills/",
    "static/",
)
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", "node_modules"}


def build_manifest(root: Path) -> tuple[str, ...]:
    project = Path(root).resolve()
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        cwd=project,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    selected = []
    for raw in result.stdout.splitlines():
        relative = raw.replace("\\", "/").strip()
        parts = set(Path(relative).parts)
        if not relative or parts.intersection(EXCLUDED_PARTS):
            continue
        if relative in INCLUDED_FILES or relative.startswith(INCLUDED_PREFIXES):
            selected.append(relative)
    return tuple(sorted(set(selected)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    for path in build_manifest(args.root):
        print(path)


if __name__ == "__main__":
    main()
