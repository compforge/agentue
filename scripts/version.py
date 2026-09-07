"""Generate package versions from VERSION; --check never writes project files."""

import argparse
import json
import re
import sys
from pathlib import Path

import tomllib

JSON_MANIFESTS = ("package.json", "sdks/typescript/package.json")
PYTHON_MANIFEST = "sdks/python/pyproject.toml"
PYTHON_LOCK = "sdks/python/uv.lock"


def sync_version(root: Path, *, check: bool) -> list[str]:
    version = (root / "VERSION").read_text().strip()
    if not version:
        raise ValueError("VERSION must not be empty")

    updates = {}
    for relative in JSON_MANIFESTS:
        path = root / relative
        manifest = json.loads(path.read_text())
        if manifest["version"] != version:
            manifest["version"] = version
            updates[relative] = (
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
            )

    text = (root / PYTHON_MANIFEST).read_text()
    manifest = tomllib.loads(text)
    if manifest["project"]["version"] != version:
        # Preserve TOML formatting and unrelated tool/dependency settings.
        text, count = re.subn(
            r'(?ms)(^\[project\]\s*\n(?:(?!^\[).)*?^version\s*=\s*)"[^"]*"',
            lambda match: match[1] + json.dumps(version),
            text,
            count=1,
        )
        if count != 1:
            raise ValueError(f"{PYTHON_MANIFEST}: cannot locate project.version")
        updates[PYTHON_MANIFEST] = text

    mismatches = list(updates)
    if check:
        lock = tomllib.loads((root / PYTHON_LOCK).read_text())
        package = next(p for p in lock["package"] if p["name"] == "agentue")
        if package["version"] != version:
            mismatches.append(PYTHON_LOCK)
    else:
        for relative, content in updates.items():
            (root / relative).write_text(content)
        # make version delegates lockfile changes to uv, never to this script.
    return mismatches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    paths = sync_version(Path(__file__).resolve().parents[1], check=args.check)
    if args.check and paths:
        print(
            "Version mismatch: " + ", ".join(paths) + "; run make version",
            file=sys.stderr,
        )
        return 1
    if not args.check and paths:
        print("Updated versions: " + ", ".join(paths))
    return 0


if __name__ == "__main__":
    sys.exit(main())
