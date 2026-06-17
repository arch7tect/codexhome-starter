from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from sync_system import classify_path, iter_repo_files, load_manifest  # noqa: E402


STARTER_URL = "https://github.com/arch7tect/codexhome-starter.git"


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


def command(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(args),
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(result.stdout)
    return result


def copy_managed_tree(destination: Path) -> None:
    manifest = load_manifest(ROOT / "system-manifest.toml", ROOT)
    for rel_path in iter_repo_files(ROOT):
        entry = classify_path(manifest, rel_path)
        if entry is None or entry.path_class != "managed":
            continue
        target = destination / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel_path, target)


def make_starter_repo(name: str, with_starter_origin: bool = True) -> Path:
    base = ROOT / "scripts" / "tests" / ".generated" / name
    if base.exists():
        shutil.rmtree(base)
    repo = base / "repo"
    repo.mkdir(parents=True)
    copy_managed_tree(repo)

    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Publish Test")
    git(repo, "config", "user.email", "publish@example.invalid")
    if with_starter_origin:
        git(repo, "remote", "add", "origin", STARTER_URL)
    git(repo, "add", ".")
    git(repo, "commit", "-m", "starter")
    command(repo, sys.executable, "scripts/sync_system.py", "--adopt", "--from", ".", "--allow-local-adopt", "--managed-only-lock")
    git(repo, "add", "system-lock.toml")
    git(repo, "commit", "-m", "release lock")
    return repo


def bootstrap(repo: Path) -> None:
    command(repo, sys.executable, "scripts/bootstrap_instance.py", "--from", ".")


def init_bare_remote(path: Path) -> Path:
    remote = path / "instance.git"
    remote.parent.mkdir(parents=True, exist_ok=True)
    git(remote.parent, "init", "--bare", remote.name)
    return remote


def test_publish_instance_dry_run_does_not_change_git_state() -> None:
    repo = make_starter_repo("publish_instance_dry_run")
    bootstrap(repo)
    before_head = git(repo, "rev-parse", "HEAD")
    before_origin = git(repo, "remote", "get-url", "origin")

    output = command(repo, sys.executable, "scripts/publish_instance.py", "--instance-remote", "git@example.com:user/instance.git", "--dry-run").stdout

    if "Publish Instance Plan" not in output:
        raise AssertionError(f"dry-run should print a plan: {output}")
    if git(repo, "rev-parse", "HEAD") != before_head:
        raise AssertionError("dry-run should not create commits")
    if git(repo, "remote", "get-url", "origin") != before_origin:
        raise AssertionError("dry-run should not change remotes")


def test_publish_instance_commits_and_pushes_to_empty_remote() -> None:
    repo = make_starter_repo("publish_instance_push")
    remote = init_bare_remote(repo.parent)
    bootstrap(repo)

    output = command(repo, sys.executable, "scripts/publish_instance.py", "--instance-remote", str(remote), "--push").stdout

    if "Commit created: yes" not in output:
        raise AssertionError(f"publish should create an instance commit: {output}")
    if git(repo, "remote", "get-url", "starter") != STARTER_URL:
        raise AssertionError("starter origin should be renamed to starter")
    if git(repo, "remote", "get-url", "origin") != str(remote):
        raise AssertionError("instance remote should become origin")
    if git(repo, "log", "-1", "--pretty=%s") != "Initialize local instance":
        raise AssertionError("publish should create the expected commit")
    if git(repo, "ls-files", ".env"):
        raise AssertionError(".env must not be tracked after publish")
    if git(repo, "status", "--short"):
        raise AssertionError("publish should leave the worktree clean except ignored files")
    if git(remote, "rev-parse", "refs/heads/main") != git(repo, "rev-parse", "HEAD"):
        raise AssertionError("publish should push main to the instance remote")


def test_publish_instance_rejects_tracked_env() -> None:
    repo = make_starter_repo("publish_instance_env")
    bootstrap(repo)
    git(repo, "add", "-f", ".env")

    result = command(repo, sys.executable, "scripts/publish_instance.py", "--instance-remote", "git@example.com:user/instance.git", check=False)

    if result.returncode == 0 or ".env must not be tracked" not in result.stdout:
        raise AssertionError(f"publish should reject tracked .env: {result.stdout}")


def test_publish_instance_rejects_nonstarter_origin() -> None:
    repo = make_starter_repo("publish_instance_nonstarter_origin", with_starter_origin=False)
    git(repo, "remote", "add", "origin", "git@example.com:user/existing-instance.git")
    bootstrap(repo)

    result = command(repo, sys.executable, "scripts/publish_instance.py", "--instance-remote", "git@example.com:user/new-instance.git", check=False)

    if result.returncode == 0 or "origin already exists" not in result.stdout:
        raise AssertionError(f"publish should reject a non-starter origin: {result.stdout}")


def test_publish_instance_rejects_local_paths_in_scaffolds() -> None:
    repo = make_starter_repo("publish_instance_local_paths")
    bootstrap(repo)
    readme = repo / "README.local.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\nLocal path: /Users/example/private\n", encoding="utf-8")

    result = command(repo, sys.executable, "scripts/publish_instance.py", "--instance-remote", "git@example.com:user/instance.git", check=False)

    if result.returncode == 0 or "local absolute paths found" not in result.stdout:
        raise AssertionError(f"publish should reject local paths in scaffolds: {result.stdout}")


def main() -> int:
    test_publish_instance_dry_run_does_not_change_git_state()
    test_publish_instance_commits_and_pushes_to_empty_remote()
    test_publish_instance_rejects_tracked_env()
    test_publish_instance_rejects_nonstarter_origin()
    test_publish_instance_rejects_local_paths_in_scaffolds()
    print("publish_instance tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
