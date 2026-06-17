from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PUBLISH_PATHS = [
    "AGENTS.local.md",
    "README.local.md",
    "projects/_template.md",
    "projects/index.local.md",
    "references/index.local.md",
    "wiki/index.md",
    "system-lock.toml",
]
REQUIRED_INITIALIZED_PATHS = [".env", *PUBLISH_PATHS]
STARTER_REMOTE_MARKER = "codexhome-starter"
LOCAL_PATH_PATTERNS = [
    re.compile(r"/Users/[^\s`'\"<>]+"),
    re.compile(r"/home/[^\s`'\"<>]+"),
    re.compile(r"[A-Za-z]:\\Users\\[^\s`'\"<>]+"),
]


class PublishError(Exception):
    pass


def git(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if check and result.returncode != 0:
        raise PublishError(result.stdout.strip() or f"git {' '.join(args)} failed")
    return result


def git_stdout(args: list[str]) -> str:
    return git(args).stdout.strip()


def remote_url(name: str) -> str | None:
    result = git(["remote", "get-url", name], check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def is_starter_remote(url: str) -> bool:
    return STARTER_REMOTE_MARKER in url.lower()


def status_paths() -> list[str]:
    paths: list[str] = []
    for line in git(["status", "--porcelain=v1", "--untracked-files=all"]).stdout.splitlines():
        if not line:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path)
    return paths


def staged_paths() -> list[str]:
    output = git_stdout(["diff", "--cached", "--name-only"])
    return [line for line in output.splitlines() if line]


def ensure_initialized() -> None:
    missing = [rel_path for rel_path in REQUIRED_INITIALIZED_PATHS if not (ROOT / rel_path).exists()]
    if missing:
        raise PublishError("repository is not initialized; missing: " + ", ".join(missing))


def ensure_env_safe() -> None:
    if git(["ls-files", "--error-unmatch", ".env"], check=False).returncode == 0:
        raise PublishError(".env must not be tracked")
    if ".env" in staged_paths():
        raise PublishError(".env must not be staged")
    if git(["check-ignore", "-q", ".env"], check=False).returncode != 0:
        raise PublishError(".env must be ignored by git before publishing")


def ensure_status_safe() -> None:
    allowed = set(PUBLISH_PATHS)
    unexpected = sorted(path for path in status_paths() if path not in allowed)
    if unexpected:
        raise PublishError("unexpected worktree changes: " + ", ".join(unexpected))

    unexpected_staged = sorted(path for path in staged_paths() if path not in allowed)
    if unexpected_staged:
        raise PublishError("unexpected staged changes: " + ", ".join(unexpected_staged))


def ensure_no_local_paths() -> None:
    violations: list[str] = []
    for rel_path in PUBLISH_PATHS:
        path = ROOT / rel_path
        if not path.exists() or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in LOCAL_PATH_PATTERNS:
            if pattern.search(text):
                violations.append(rel_path)
                break
    if violations:
        raise PublishError("local absolute paths found in publish files: " + ", ".join(sorted(violations)))


def ensure_branch() -> str:
    branch = git_stdout(["branch", "--show-current"])
    if not branch:
        raise PublishError("cannot publish from a detached HEAD")
    return branch


def ensure_remote_empty(remote: str) -> None:
    result = git(["ls-remote", "--heads", remote], check=False)
    if result.returncode != 0:
        raise PublishError(f"cannot inspect instance remote: {result.stdout.strip()}")
    if result.stdout.strip():
        raise PublishError("instance remote is not empty; publish to an empty private repository")


def remote_plan(instance_remote: str) -> list[str]:
    origin = remote_url("origin")
    starter = remote_url("starter")
    actions: list[str] = []
    if origin is None:
        actions.append(f"add origin {instance_remote}")
        return actions
    if origin == instance_remote:
        actions.append("keep existing origin")
        return actions
    if is_starter_remote(origin):
        if starter is None:
            actions.append("rename origin to starter")
        elif starter == origin:
            actions.append("remove duplicate starter origin")
        else:
            raise PublishError("starter remote already exists with a different URL")
        actions.append(f"add origin {instance_remote}")
        return actions
    raise PublishError("origin already exists and does not look like codexhome-starter")


def configure_remotes(instance_remote: str) -> None:
    origin = remote_url("origin")
    starter = remote_url("starter")
    if origin is None:
        git(["remote", "add", "origin", instance_remote])
        return
    if origin == instance_remote:
        return
    if is_starter_remote(origin):
        if starter is None:
            git(["remote", "rename", "origin", "starter"])
        elif starter == origin:
            git(["remote", "remove", "origin"])
        else:
            raise PublishError("starter remote already exists with a different URL")
        git(["remote", "add", "origin", instance_remote])
        return
    raise PublishError("origin already exists and does not look like codexhome-starter")


def stage_publish_paths() -> None:
    git(["add", "--", *PUBLISH_PATHS])


def has_staged_changes() -> bool:
    return git(["diff", "--cached", "--quiet"], check=False).returncode != 0


def commit_if_needed() -> bool:
    if not has_staged_changes():
        return False
    git(["commit", "-m", "Initialize local instance"])
    return True


def publish(instance_remote: str, push: bool, dry_run: bool) -> None:
    ensure_initialized()
    ensure_env_safe()
    ensure_status_safe()
    ensure_no_local_paths()
    branch = ensure_branch()
    actions = remote_plan(instance_remote)

    print("# Publish Instance Plan")
    print()
    for action in actions:
        print(f"- Remote: {action}")
    print("- Stage initialized scaffold files and system-lock.toml")
    print("- Commit: Initialize local instance")
    print(f"- Push: {'yes' if push else 'no'}")

    if dry_run:
        return

    if push:
        ensure_remote_empty(instance_remote)
    configure_remotes(instance_remote)
    stage_publish_paths()
    ensure_env_safe()
    ensure_status_safe()
    ensure_no_local_paths()
    committed = commit_if_needed()
    print(f"Commit created: {'yes' if committed else 'no'}")
    if push:
        git(["push", "-u", "origin", branch])
        print(f"Pushed {branch} to origin.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish an initialized CodexHome instance to a private Git remote.")
    parser.add_argument("--instance-remote", required=True, help="Empty private Git remote URL for this initialized instance.")
    parser.add_argument("--push", action="store_true", help="Push the current branch to the instance remote after committing.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print the publish plan without changing git state.")
    args = parser.parse_args()

    try:
        publish(args.instance_remote, push=args.push, dry_run=args.dry_run)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
