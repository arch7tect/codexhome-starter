from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from sync_system import classify_path, iter_repo_files, load_manifest  # noqa: E402


EXPECTED_BOOTSTRAP_SCAFFOLDS = {
    ".env",
    "AGENTS.local.md",
    "README.local.md",
    "references/index.local.md",
    "projects/_template.md",
    "projects/index.local.md",
    "wiki/index.md",
}


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout)
    return result.stdout.strip()


def command(repo: Path, *args: str) -> str:
    result = subprocess.run(
        list(args),
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout)
    return result.stdout


def env_values(repo: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (repo / ".env").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def copy_managed_tree(destination: Path) -> None:
    manifest = load_manifest(ROOT / "system-manifest.toml", ROOT)
    for rel_path in iter_repo_files(ROOT):
        entry = classify_path(manifest, rel_path)
        if entry is None or entry.path_class != "managed":
            continue
        target = destination / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel_path, target)


def test_bootstrap_scaffold_sources_are_managed_and_present() -> None:
    manifest = load_manifest(ROOT / "system-manifest.toml", ROOT)
    for rel_path in EXPECTED_BOOTSTRAP_SCAFFOLDS:
        entry = classify_path(manifest, rel_path)
        if entry is None or entry.path_class != "scaffold_once":
            raise AssertionError(f"expected scaffold_once entry for {rel_path}: {entry}")
        if not entry.source:
            raise AssertionError(f"expected source for bootstrap scaffold {rel_path}")
        source_entry = classify_path(manifest, entry.source)
        if source_entry is None or source_entry.path_class != "managed":
            raise AssertionError(f"expected managed scaffold source for {rel_path}: {entry.source}")
        if not (ROOT / entry.source).is_file():
            raise AssertionError(f"missing scaffold source for {rel_path}: {entry.source}")

    instance_manifest = classify_path(manifest, "instance-manifest.toml")
    if instance_manifest is None or instance_manifest.source is not None:
        raise AssertionError("instance-manifest.toml must not be bootstrapped by default")


def test_bootstrap_instance_creates_expected_scaffolds_and_is_idempotent() -> None:
    base = ROOT / "scripts" / "tests" / ".generated" / "bootstrap_instance"
    if base.exists():
        shutil.rmtree(base)
    repo = base / "repo"
    repo.mkdir(parents=True)
    copy_managed_tree(repo)

    git(repo, "init")
    git(repo, "config", "user.name", "Bootstrap Test")
    git(repo, "config", "user.email", "bootstrap@example.invalid")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "starter")
    command(repo, sys.executable, "scripts/sync_system.py", "--adopt", "--from", ".", "--allow-local-adopt", "--managed-only-lock")
    git(repo, "add", "system-lock.toml")
    git(repo, "commit", "-m", "release lock")

    output = command(repo, sys.executable, "scripts/bootstrap_instance.py", "--from", ".")
    for rel_path in EXPECTED_BOOTSTRAP_SCAFFOLDS:
        if not (repo / rel_path).is_file():
            raise AssertionError(f"bootstrap did not create {rel_path}\n{output}")
    values = env_values(repo)
    if values.get("CODEX_HOME") != str(repo.resolve()):
        raise AssertionError("bootstrap should set CODEX_HOME to the current checkout")
    if values.get("PROJECTS_ROOT") != "/path/to/projects":
        raise AssertionError("bootstrap should leave PROJECTS_ROOT as a placeholder unless provided")
    if (repo / "instance-manifest.toml").exists():
        raise AssertionError("bootstrap should not create instance-manifest.toml by default")
    if "Next Steps" not in output:
        raise AssertionError(f"bootstrap should print next steps: {output}")
    if "Updated `CODEX_HOME` in `.env`." not in output:
        raise AssertionError(f"bootstrap should report CODEX_HOME configuration: {output}")

    projects_root = repo.parent / "projects-root"
    env_only_output = command(repo, sys.executable, "scripts/bootstrap_instance.py", "--env-only", "--projects-root", str(projects_root))
    values = env_values(repo)
    if values.get("PROJECTS_ROOT") != str(projects_root.resolve()):
        raise AssertionError("bootstrap should write PROJECTS_ROOT in env-only mode after scaffold creation")
    if "Updated `PROJECTS_ROOT` in `.env`." not in env_only_output:
        raise AssertionError(f"env-only mode should report PROJECTS_ROOT configuration: {env_only_output}")

    git(repo, "add", "AGENTS.local.md", "README.local.md", "references/index.local.md", "projects/_template.md", "projects/index.local.md", "wiki/index.md", "system-lock.toml")
    git(repo, "commit", "-m", "initialize")
    second_output = command(repo, sys.executable, "scripts/bootstrap_instance.py", "--from", ".")
    if "Written paths: 0" not in second_output or "Lockfile unchanged" not in second_output:
        raise AssertionError(f"bootstrap should be idempotent after committing scaffolds: {second_output}")
    if "Updated `CODEX_HOME` in `.env`." in second_output:
        raise AssertionError(f"bootstrap should not report CODEX_HOME changes when it is already current: {second_output}")

    env_path = repo / ".env"
    env_path.write_text(env_path.read_text(encoding="utf-8").replace(f"CODEX_HOME={repo.resolve()}", "CODEX_HOME=/old/path"), encoding="utf-8")
    stale_output = command(repo, sys.executable, "scripts/bootstrap_instance.py", "--from", ".")
    values = env_values(repo)
    if values.get("CODEX_HOME") != str(repo.resolve()):
        raise AssertionError("bootstrap should correct stale CODEX_HOME values")
    if "Updated `CODEX_HOME` in `.env`." not in stale_output:
        raise AssertionError(f"bootstrap should report stale CODEX_HOME correction: {stale_output}")

    alternate_projects_root = repo.parent / "alternate-projects-root"
    third_output = command(repo, sys.executable, "scripts/bootstrap_instance.py", "--from", ".", "--projects-root", str(alternate_projects_root))
    values = env_values(repo)
    if values.get("PROJECTS_ROOT") != str(alternate_projects_root.resolve()):
        raise AssertionError("bootstrap should write PROJECTS_ROOT when explicitly provided")
    if "Updated `PROJECTS_ROOT` in `.env`." not in third_output:
        raise AssertionError(f"bootstrap should report PROJECTS_ROOT configuration: {third_output}")

    empty_root = subprocess.run(
        [sys.executable, "scripts/bootstrap_instance.py", "--from", ".", "--projects-root", ""],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if empty_root.returncode == 0 or "--projects-root must not be empty" not in empty_root.stdout:
        raise AssertionError(f"empty --projects-root should fail: {empty_root.stdout}")

    empty_env_only_root = subprocess.run(
        [sys.executable, "scripts/bootstrap_instance.py", "--env-only", "--projects-root", ""],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if empty_env_only_root.returncode == 0 or "--projects-root must not be empty" not in empty_env_only_root.stdout:
        raise AssertionError(f"empty env-only --projects-root should fail: {empty_env_only_root.stdout}")


def main() -> int:
    test_bootstrap_scaffold_sources_are_managed_and_present()
    test_bootstrap_instance_creates_expected_scaffolds_and_is_idempotent()
    print("bootstrap_instance tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
