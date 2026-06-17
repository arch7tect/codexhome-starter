from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def manifest_starter_version(manifest_path: Path) -> str:
    data = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    version = data.get("starter_version")
    if not isinstance(version, str) or not version:
        raise ValueError("manifest starter_version must be a non-empty string")
    return version


def git_has_tag(root: Path, tag: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}"],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def source_is_local_path(source: str) -> bool:
    return Path(source).expanduser().exists()


def default_source(root: Path, manifest_path: Path) -> tuple[str, bool]:
    version = manifest_starter_version(manifest_path)
    if git_has_tag(root, version):
        return version, False
    return ".", True


def run_sync(mode: str, source: str, manifest: str, allow_local: bool) -> int:
    command = [sys.executable, str(ROOT / "scripts" / "sync_system.py"), "--manifest", manifest, "--from", source, mode]
    if mode == "--apply" and allow_local:
        command.append("--allow-local-apply")
    return subprocess.run(command, cwd=ROOT, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize a CodexHome instance from the starter scaffold.")
    parser.add_argument("--manifest", default="system-manifest.toml", help="Path to system manifest.")
    parser.add_argument("--from", dest="starter_source", help="Starter tag, commit, or local path. Defaults to manifest starter_version when available.")
    parser.add_argument("--dry-run", action="store_true", help="Show the bootstrap sync plan without writing files.")
    args = parser.parse_args()

    manifest_path = ROOT / args.manifest
    try:
        if args.starter_source:
            source = args.starter_source
            allow_local = source_is_local_path(source)
        else:
            source, allow_local = default_source(ROOT, manifest_path)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    mode = "--dry-run" if args.dry_run else "--apply"
    result = run_sync(mode, source, args.manifest, allow_local)
    if result != 0:
        return result

    if args.dry_run:
        return 0

    print()
    print("# Next Steps")
    print()
    print("1. Edit `.env` manually and fill local paths; bootstrap leaves placeholder values unless you explicitly provide real paths.")
    print("2. Create your first project profile from `projects/_template.md`.")
    print("3. Review `git status` and commit the initialized local scaffolds.")
    print("4. Start Codex in this checkout and ask it to read `AGENTS.md`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
