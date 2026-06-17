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


def local_path_value(value: str) -> str:
    return str(Path(value).expanduser().resolve())


def update_env_value(lines: list[str], key: str, value: str, replace_only: set[str] | None = None) -> tuple[list[str], bool]:
    prefix = f"{key}="
    updated = False
    found = False
    new_lines: list[str] = []
    for line in lines:
        if line.startswith(prefix):
            found = True
            current = line[len(prefix) :].strip()
            if replace_only is None or current in replace_only:
                replacement = f"{prefix}{value}\n"
                new_lines.append(replacement)
                if line != replacement:
                    updated = True
            else:
                new_lines.append(line)
            continue
        new_lines.append(line)
    if not found:
        new_lines.append(f"{prefix}{value}\n")
        updated = True
    return new_lines, updated


def configure_env(projects_root: str | None) -> list[str]:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return []

    lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)
    changes: list[str] = []
    lines, updated_codex_home = update_env_value(
        lines,
        "CODEX_HOME",
        local_path_value(str(ROOT)),
        replace_only=None,
    )
    if updated_codex_home:
        changes.append("CODEX_HOME")

    if projects_root is not None:
        lines, updated_projects_root = update_env_value(
            lines,
            "PROJECTS_ROOT",
            local_path_value(projects_root),
            replace_only=None,
        )
        if updated_projects_root:
            changes.append("PROJECTS_ROOT")

    if changes:
        env_path.write_text("".join(lines), encoding="utf-8")
    return changes


def print_env_changes(changes: list[str]) -> None:
    print()
    print("# Local Environment")
    if not changes:
        print("- No `.env` changes needed.")
        return
    for key in changes:
        print(f"- Updated `{key}` in `.env`.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize a CodexHome instance from the starter scaffold.")
    parser.add_argument("--manifest", default="system-manifest.toml", help="Path to system manifest.")
    parser.add_argument("--from", dest="starter_source", help="Starter tag, commit, or local path. Defaults to manifest starter_version when available.")
    parser.add_argument("--dry-run", action="store_true", help="Show the bootstrap sync plan without writing files.")
    parser.add_argument("--projects-root", help="Explicit PROJECTS_ROOT value to write into .env after bootstrap.")
    parser.add_argument("--env-only", action="store_true", help="Only update .env values without running starter sync.")
    args = parser.parse_args()

    if args.projects_root is not None and not args.projects_root.strip():
        print("ERROR: --projects-root must not be empty", file=sys.stderr)
        return 1
    if args.env_only:
        if args.dry_run:
            print("ERROR: --env-only cannot be combined with --dry-run", file=sys.stderr)
            return 1
        if not (ROOT / ".env").exists():
            print("ERROR: .env does not exist; run bootstrap first", file=sys.stderr)
            return 1
        print_env_changes(configure_env(args.projects_root))
        return 0

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

    env_changes = configure_env(args.projects_root)
    if env_changes:
        print_env_changes(env_changes)

    print()
    print("# Next Steps")
    print()
    print("1. Review `.env`; bootstrap sets `CODEX_HOME` to this checkout and writes `PROJECTS_ROOT` only when `--projects-root` is provided.")
    print("2. Create your first project profile from `projects/_template.md`.")
    print("3. Review `git status` and commit the initialized local scaffolds.")
    print("4. Start Codex in this checkout and ask it to read `AGENTS.md`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
