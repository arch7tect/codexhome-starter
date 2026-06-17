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
    if (repo / ".env").read_text(encoding="utf-8") != (repo / ".env.template").read_text(encoding="utf-8"):
        raise AssertionError("bootstrap should create .env from .env.template without filling local values")
    if (repo / "instance-manifest.toml").exists():
        raise AssertionError("bootstrap should not create instance-manifest.toml by default")
    if "Next Steps" not in output:
        raise AssertionError(f"bootstrap should print next steps: {output}")
    if "bootstrap leaves placeholder values" not in output:
        raise AssertionError(f"bootstrap should tell users that .env placeholders are not auto-filled: {output}")

    git(repo, "add", "AGENTS.local.md", "README.local.md", "references/index.local.md", "projects/_template.md", "projects/index.local.md", "wiki/index.md", "system-lock.toml")
    git(repo, "commit", "-m", "initialize")
    second_output = command(repo, sys.executable, "scripts/bootstrap_instance.py", "--from", ".")
    if "Written paths: 0" not in second_output or "Lockfile unchanged" not in second_output:
        raise AssertionError(f"bootstrap should be idempotent after committing scaffolds: {second_output}")


def main() -> int:
    test_bootstrap_scaffold_sources_are_managed_and_present()
    test_bootstrap_instance_creates_expected_scaffolds_and_is_idempotent()
    print("bootstrap_instance tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
