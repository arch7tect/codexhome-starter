from __future__ import annotations

import argparse
import fnmatch
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterator, Literal

from system_lock import ContentType, LockDecision, LockDecisionInput, decide_lock_action, file_sha256


ROOT = Path(__file__).resolve().parents[1]
VALID_CLASSES = {"managed", "scaffold_once", "reserved_user"}
VALID_CONTENT_TYPES = {"text", "binary"}
SEMVER_TAG_PATTERN = re.compile(r"^v\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
FULL_COMMIT_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
PathClass = Literal["managed", "scaffold_once", "reserved_user"]


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    path_class: PathClass
    content: str | None = None
    source: str | None = None
    generated: bool = False
    note: str | None = None


@dataclass(frozen=True)
class Manifest:
    schema_version: int
    starter_version: str
    default_class: PathClass
    matching: str
    entries: list[ManifestEntry]
    verification_commands: list[str]
    local_reservations: list[ManifestEntry] = field(default_factory=list)


@dataclass(frozen=True)
class LockEntry:
    path: str
    path_class: PathClass
    content: ContentType
    sha256: str


@dataclass(frozen=True)
class SyncPlanItem:
    path: str
    path_class: PathClass
    action: str
    disposition: str
    reason: str


@dataclass(frozen=True)
class SyncPlan:
    safe_updates: list[SyncPlanItem]
    new_managed_files: list[SyncPlanItem]
    adopt_candidates: list[SyncPlanItem]
    scaffold_once_creations: list[SyncPlanItem]
    conflicts: list[SyncPlanItem]
    skipped_user_paths: list[SyncPlanItem]
    prune_candidates: list[SyncPlanItem]
    reported_managed_changes: list[SyncPlanItem]
    skipped_generated_paths: list[SyncPlanItem]
    noop_count: int
    lock_entry_count: int
    dirty: list[str]


@dataclass(frozen=True)
class ApplyTransaction:
    operations: list[SyncPlanItem]
    lock_updates: list[SyncPlanItem]
    blockers: list[str]
    clean_recheck_required: bool = True
    lockfile_update_last: bool = True


@dataclass(frozen=True)
class ApplyResult:
    written_paths: list[str]
    lock_updated_paths: list[str]
    lockfile_updated: bool


@dataclass(frozen=True)
class ResolvedStarterSource:
    path: Path
    label: str
    is_local_path: bool


def parse_manifest_entries(data: dict[str, Any], root: Path, allow_sources: bool = True) -> list[ManifestEntry]:
    entries: list[ManifestEntry] = []
    seen: set[str] = set()
    for index, item in enumerate(data.get("paths", []), start=1):
        entry_path = item.get("path")
        if not isinstance(entry_path, str) or not entry_path:
            raise ValueError(f"manifest entry {index} has invalid path")
        if entry_path in seen:
            raise ValueError(f"duplicate manifest path: {entry_path}")
        seen.add(entry_path)

        path_class = item.get("class")
        if path_class not in VALID_CLASSES:
            raise ValueError(f"manifest entry {entry_path} has invalid class: {path_class}")

        content = item.get("content")
        if path_class in {"managed", "scaffold_once"}:
            if content not in VALID_CONTENT_TYPES:
                raise ValueError(f"manifest entry {entry_path} has invalid content type: {content}")
        elif content is not None and content not in VALID_CONTENT_TYPES:
            raise ValueError(f"manifest entry {entry_path} has invalid content type: {content}")

        source = item.get("source")
        if source is not None:
            if not allow_sources:
                raise ValueError(f"manifest entry {entry_path} must not define source")
            if not (root / source).exists():
                raise ValueError(f"manifest entry {entry_path} source does not exist: {source}")

        entries.append(
            ManifestEntry(
                path=entry_path,
                path_class=path_class,
                content=content,
                source=source,
                generated=bool(item.get("generated", False)),
                note=item.get("note"),
            )
        )
    return entries


def load_instance_reservations(root: Path) -> list[ManifestEntry]:
    path = root / "instance-manifest.toml"
    if not path.exists():
        return []

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    schema_version = data.get("schema_version")
    if schema_version not in {None, 1}:
        raise ValueError(f"unsupported instance manifest schema_version: {schema_version}")

    entries = parse_manifest_entries(data, root, allow_sources=False)
    for entry in entries:
        if entry.path_class != "reserved_user":
            raise ValueError(f"instance manifest entry must be reserved_user: {entry.path}")
    return entries


def load_manifest(path: Path, root: Path = ROOT) -> Manifest:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    schema_version = data.get("schema_version")
    if schema_version != 1:
        raise ValueError(f"unsupported manifest schema_version: {schema_version}")

    starter_version = data.get("starter_version")
    if not isinstance(starter_version, str) or not starter_version:
        raise ValueError("manifest starter_version must be a non-empty string")

    default_class = data.get("default_class", "reserved_user")
    if default_class not in VALID_CLASSES:
        raise ValueError(f"invalid default_class: {default_class}")

    matching = data.get("matching", "specific_before_glob")
    if matching != "specific_before_glob":
        raise ValueError(f"unsupported matching strategy: {matching}")

    verification = data.get("verification", {})
    commands = verification.get("commands", []) if isinstance(verification, dict) else []
    if not isinstance(commands, list) or not all(isinstance(command, str) for command in commands):
        raise ValueError("verification.commands must be a list of strings")

    return Manifest(
        schema_version=schema_version,
        starter_version=starter_version,
        default_class=default_class,
        matching=matching,
        entries=parse_manifest_entries(data, root),
        verification_commands=commands,
        local_reservations=load_instance_reservations(root),
    )


def split_path(path: str) -> list[str]:
    return [part for part in path.split("/") if part]


def specificity(pattern: str) -> tuple[int, int, int]:
    parts = split_path(pattern)
    literal_chars = sum(1 for char in pattern if char not in "*?[]")
    wildcard_count = sum(1 for char in pattern if char in "*?[")
    return (literal_chars, len(parts), -wildcard_count)


def matches(pattern: str, rel_path: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        return rel_path == prefix or rel_path.startswith(prefix + "/")
    return fnmatch.fnmatchcase(rel_path, pattern)


def classify_path(manifest: Manifest, rel_path: str) -> ManifestEntry | None:
    reserved_entries = [entry for entry in manifest.local_reservations if matches(entry.path, rel_path)]
    if reserved_entries:
        return max(reserved_entries, key=lambda entry: specificity(entry.path))

    matching_entries = [entry for entry in manifest.entries if matches(entry.path, rel_path)]
    if not matching_entries:
        return None
    return max(matching_entries, key=lambda entry: specificity(entry.path))


def is_git_worktree(root: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0 and Path(result.stdout.strip()).resolve() == root.resolve()


def iter_files_without_git(root: Path) -> list[str]:
    ignored_dirs = {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
    rel_paths: list[str] = []
    for path in root.rglob("*"):
        rel_parts = path.relative_to(root).parts
        if any(part in ignored_dirs for part in rel_parts):
            continue
        if path.is_file() or path.is_symlink():
            rel_paths.append(path.relative_to(root).as_posix())
    return sorted(rel_paths)


def iter_repo_files(root: Path = ROOT) -> list[str]:
    if not is_git_worktree(root):
        return iter_files_without_git(root)

    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stdout.strip() or "git ls-files failed")
    return sorted(line for line in result.stdout.splitlines() if line.strip())


def git_status(root: Path = ROOT) -> list[str]:
    if not is_git_worktree(root):
        return []

    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stdout.strip() or "git status failed")
    return [line for line in result.stdout.splitlines() if line.strip()]


def check_manifest(manifest: Manifest) -> dict[str, Any]:
    counts = {"managed": 0, "scaffold_once": 0, "reserved_user": 0, "default_reserved": 0}
    missing_sources: list[str] = []
    missing_managed: list[str] = []

    for entry in manifest.entries:
        counts[entry.path_class] += 1
        if entry.source and not (ROOT / entry.source).exists():
            missing_sources.append(f"{entry.path} <- {entry.source}")
        if entry.path_class == "managed" and not entry.generated and not any(char in entry.path for char in "*?["):
            if not (ROOT / entry.path).exists():
                missing_managed.append(entry.path)

    classified_files: dict[str, int] = {"managed": 0, "scaffold_once": 0, "reserved_user": 0, "default_reserved": 0}
    for rel_path in iter_repo_files():
        entry = classify_path(manifest, rel_path)
        if entry is None:
            classified_files["default_reserved"] += 1
        else:
            classified_files[entry.path_class] += 1

    return {
        "entry_counts": counts,
        "file_counts": classified_files,
        "missing_sources": missing_sources,
        "missing_managed": missing_managed,
        "dirty": git_status(ROOT),
    }


def print_check(manifest: Manifest, result: dict[str, Any]) -> None:
    print("# System Sync Check")
    print()
    print(f"Manifest: schema {manifest.schema_version}, starter {manifest.starter_version}")
    print(f"Matching: {manifest.matching}")
    print(f"Default class: {manifest.default_class}")
    print()

    print("## Manifest Entries")
    for key, value in result["entry_counts"].items():
        print(f"- {key}: {value}")
    print()

    print("## Existing Files")
    for key, value in result["file_counts"].items():
        print(f"- {key}: {value}")
    print()

    if result["missing_sources"]:
        print("## Missing Scaffold Sources")
        for item in result["missing_sources"]:
            print(f"- {item}")
        print()

    if result["missing_managed"]:
        print("## Missing Explicit Managed Paths")
        for item in result["missing_managed"]:
            print(f"- {item}")
        print()

    if result["dirty"]:
        print("## Worktree")
        print("Dirty worktree detected; check mode is read-only and did not modify files.")
        for line in result["dirty"]:
            print(f"- {line}")
        print()
    else:
        print("## Worktree")
        print("Clean.")
        print()

    print("Verification commands declared:")
    for command in manifest.verification_commands:
        print(f"- {command}")


def is_sha256_hex(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdefABCDEF" for char in value)


def load_lockfile(path: Path) -> dict[str, LockEntry]:
    if not path.exists():
        return {}

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    raw_entries: list[tuple[str | None, dict[str, Any]]] = []
    if isinstance(data.get("paths"), list):
        raw_entries.extend((None, item) for item in data["paths"] if isinstance(item, dict))
    if isinstance(data.get("files"), dict):
        raw_entries.extend((key, item) for key, item in data["files"].items() if isinstance(item, dict))

    entries: dict[str, LockEntry] = {}
    for fallback_path, item in raw_entries:
        rel_path = item.get("path", fallback_path)
        if not isinstance(rel_path, str) or not rel_path:
            raise ValueError("lockfile entry has invalid path")

        path_class = item.get("class", item.get("path_class", "managed"))
        if path_class not in VALID_CLASSES:
            raise ValueError(f"lockfile entry {rel_path} has invalid class: {path_class}")

        content = item.get("content", item.get("content_type", "text"))
        if content not in VALID_CONTENT_TYPES:
            raise ValueError(f"lockfile entry {rel_path} has invalid content type: {content}")

        digest = item.get("sha256", item.get("hash"))
        if isinstance(digest, str) and digest.startswith("sha256:"):
            digest = digest.removeprefix("sha256:")
        if not isinstance(digest, str) or not is_sha256_hex(digest):
            raise ValueError(f"lockfile entry {rel_path} has invalid sha256")

        entries[rel_path] = LockEntry(rel_path, path_class, content, digest)
    return entries


def has_glob(pattern: str) -> bool:
    return any(char in pattern for char in "*?[")


def entry_source_rel_path(entry: ManifestEntry, rel_path: str) -> str:
    if entry.source is not None:
        return entry.source
    if has_glob(entry.path):
        return rel_path
    return entry.path


def safe_rel_path(rel_path: str) -> Path:
    path = Path(rel_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe relative path: {rel_path}")
    return path


def safe_join(root: Path, rel_path: str) -> Path:
    root = root.resolve()
    path = root
    for part in safe_rel_path(rel_path).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f"symlinks are not supported by starter sync: {rel_path}")
    return path


def hash_optional_file(root: Path, rel_path: str, content: ContentType) -> str | None:
    path = safe_join(root, rel_path)
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink():
        raise ValueError(f"symlinks are not supported by starter sync: {rel_path}")
    if not path.is_file():
        raise ValueError(f"starter sync expects a regular file: {rel_path}")
    return file_sha256(path, content)


def manifest_target_paths(manifest: Manifest, local_root: Path, starter_root: Path) -> set[str]:
    paths = set(iter_repo_files(local_root)) | set(iter_repo_files(starter_root))
    for entry in manifest.entries:
        if has_glob(entry.path):
            continue
        paths.add(entry.path)
    return paths


def append_decision(plan: dict[str, list[SyncPlanItem]], item: SyncPlanItem, decision: LockDecision) -> int:
    if decision.action == "fast_forward":
        plan["safe_updates"].append(item)
    elif decision.action == "safe_new":
        plan["new_managed_files"].append(item)
    elif decision.action == "prune_candidate":
        plan["prune_candidates"].append(item)
    elif decision.disposition == "stop":
        plan["conflicts"].append(item)
    elif decision.disposition == "report":
        plan["reported_managed_changes"].append(item)
    elif decision.disposition == "noop":
        return 1
    else:
        plan["reported_managed_changes"].append(item)
    return 0


def build_sync_plan(local_root: Path, starter_root: Path, manifest_path: str, require_clean: bool = True) -> SyncPlan:
    local_manifest = load_manifest(local_root / manifest_path, local_root)
    load_manifest(starter_root / manifest_path, starter_root)
    lock_entries = load_lockfile(local_root / "system-lock.toml")
    dirty = git_status(local_root)
    if dirty and require_clean:
        return SyncPlan([], [], [], [], [], [], [], [], [], 0, len(lock_entries), dirty)

    plan: dict[str, list[SyncPlanItem]] = {
        "safe_updates": [],
        "new_managed_files": [],
        "adopt_candidates": [],
        "scaffold_once_creations": [],
        "conflicts": [],
        "skipped_user_paths": [],
        "prune_candidates": [],
        "reported_managed_changes": [],
        "skipped_generated_paths": [],
    }
    noop_count = 0

    for rel_path in sorted(manifest_target_paths(local_manifest, local_root, starter_root)):
        entry = classify_path(local_manifest, rel_path)
        if entry is None:
            if (local_root / rel_path).exists() or (starter_root / rel_path).exists():
                plan["skipped_user_paths"].append(
                    SyncPlanItem(
                        rel_path,
                        local_manifest.default_class,
                        "skip_default_reserved",
                        "report",
                        "path is not listed in manifest",
                    )
                )
            continue

        if entry.generated:
            plan["skipped_generated_paths"].append(
                SyncPlanItem(rel_path, entry.path_class, "skip_generated", "report", "generated path is updated by its owner command")
            )
            continue

        content = entry.content or "text"
        if entry.path_class == "reserved_user":
            if (local_root / rel_path).exists() or (starter_root / rel_path).exists():
                plan["skipped_user_paths"].append(
                    SyncPlanItem(
                        rel_path,
                        entry.path_class,
                        "skip_reserved_user",
                        "report",
                        "reserved-user path is never modified by sync",
                    )
                )
            continue

        starter_rel_path = entry_source_rel_path(entry, rel_path)
        local_hash = hash_optional_file(local_root, rel_path, content)
        starter_hash = hash_optional_file(starter_root, starter_rel_path, content)

        if entry.path_class == "scaffold_once":
            locked = lock_entries.get(rel_path)
            if local_hash is None and locked is not None:
                plan["skipped_user_paths"].append(
                    SyncPlanItem(rel_path, entry.path_class, "skip_deleted_scaffold_once", "report", "scaffold-once path was already created")
                )
            elif local_hash is None and starter_hash is not None:
                plan["scaffold_once_creations"].append(
                    SyncPlanItem(rel_path, entry.path_class, "create_scaffold_once", "apply", f"create from {starter_rel_path}")
                )
            elif local_hash is not None:
                plan["skipped_user_paths"].append(
                    SyncPlanItem(rel_path, entry.path_class, "skip_existing_scaffold_once", "report", "scaffold-once path already exists locally")
                )
            continue

        locked = lock_entries.get(rel_path)
        if locked is None and local_hash is not None and local_hash == starter_hash:
            plan["adopt_candidates"].append(
                SyncPlanItem(
                    rel_path,
                    entry.path_class,
                    "adopt_baseline",
                    "report",
                    "local and starter managed content match but no lockfile baseline exists",
                )
            )
            continue

        state = LockDecisionInput(
            baseline_hash=None if locked is None else locked.sha256,
            local_hash=local_hash,
            starter_hash=starter_hash,
            locked_class=entry.path_class if locked is None else locked.path_class,
            manifest_class=entry.path_class,
            locked_content_type=content if locked is None else locked.content,
            manifest_content_type=content,
        )
        decision = decide_lock_action(state)
        item = SyncPlanItem(rel_path, entry.path_class, decision.action, decision.disposition, decision.reason)
        noop_count += append_decision(plan, item, decision)

    return SyncPlan(
        safe_updates=plan["safe_updates"],
        new_managed_files=plan["new_managed_files"],
        adopt_candidates=plan["adopt_candidates"],
        scaffold_once_creations=plan["scaffold_once_creations"],
        conflicts=plan["conflicts"],
        skipped_user_paths=plan["skipped_user_paths"],
        prune_candidates=plan["prune_candidates"],
        reported_managed_changes=plan["reported_managed_changes"],
        skipped_generated_paths=plan["skipped_generated_paths"],
        noop_count=noop_count,
        lock_entry_count=len(lock_entries),
        dirty=dirty,
    )


def print_items(title: str, items: list[SyncPlanItem], limit: int = 50) -> None:
    print(f"## {title} ({len(items)})")
    if not items:
        print("- none")
        print()
        return
    for item in items[:limit]:
        print(f"- {item.path} [{item.action}]: {item.reason}")
    if len(items) > limit:
        print(f"- ... {len(items) - limit} more")
    print()


def dry_run_blockers(plan: SyncPlan) -> list[str]:
    return build_apply_transaction(plan).blockers


def print_dry_run(starter_source: str, plan: SyncPlan) -> None:
    print("# System Sync Dry Run")
    print()
    print(f"Starter source: {starter_source}")
    print(f"Lock entries: {plan.lock_entry_count}")
    print(f"No-op managed paths: {plan.noop_count}")
    print()
    print_items("Safe Updates", plan.safe_updates)
    print_items("New Managed Files", plan.new_managed_files)
    print_items("Adopt Candidates", plan.adopt_candidates)
    print_items("Scaffold-Once Creations", plan.scaffold_once_creations)
    print_items("Conflicts", plan.conflicts)
    print_items("Skipped User Paths", plan.skipped_user_paths)
    print_items("Prune Candidates", plan.prune_candidates)
    print_items("Reported Managed Changes", plan.reported_managed_changes)
    print_items("Skipped Generated Paths", plan.skipped_generated_paths)

    blockers = dry_run_blockers(plan)
    if blockers:
        print("Dry-run result: apply is blocked until these issues are resolved:")
        for blocker in blockers:
            print(f"- {blocker}")
    else:
        print("Dry-run result: no apply blockers detected.")


def build_apply_transaction(plan: SyncPlan) -> ApplyTransaction:
    blockers: list[str] = []
    lock_updates = [item for item in plan.reported_managed_changes if item.action == "noop_update_lock"]
    reported_blockers = [item for item in plan.reported_managed_changes if item.action != "noop_update_lock"]
    if plan.dirty:
        blockers.append("worktree must be clean before apply")
    if plan.conflicts:
        blockers.append("conflicts require explicit review before apply")
    if plan.adopt_candidates:
        blockers.append("adopt candidates require lockfile baseline before apply")
    if reported_blockers:
        blockers.append("reported managed changes require explicit review before apply")

    operations = [
        *plan.safe_updates,
        *plan.new_managed_files,
        *plan.scaffold_once_creations,
    ]
    if blockers:
        operations = []
        lock_updates = []
    return ApplyTransaction(operations=operations, lock_updates=lock_updates, blockers=blockers)


def atomic_copy_file(source: Path, destination: Path) -> None:
    if destination.is_symlink():
        raise ValueError(f"destination symlink is not supported: {destination}")
    if destination.exists() and not destination.is_file():
        raise ValueError(f"destination is not a regular file: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=f".{destination.name}.", delete=False) as temp_file:
        temp_path = Path(temp_file.name)
        temp_file.write(source.read_bytes())
    try:
        os.replace(temp_path, destination)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def apply_sync_plan(local_root: Path, starter_root: Path, manifest_path: str, source_label: str) -> ApplyResult:
    plan = build_sync_plan(local_root, starter_root, manifest_path)
    transaction = build_apply_transaction(plan)
    if transaction.blockers:
        raise ValueError("; ".join(transaction.blockers))

    dirty = git_status(local_root)
    if dirty:
        raise ValueError("worktree changed before apply")

    manifest = load_manifest(local_root / manifest_path, local_root)
    lock_entries = load_lockfile(local_root / "system-lock.toml")
    written_paths: list[str] = []
    lock_updated_paths: list[str] = []
    lock_changed = False

    for item in transaction.operations:
        entry = classify_path(manifest, item.path)
        if entry is None:
            raise ValueError(f"operation path is not in manifest: {item.path}")
        content = entry.content or "text"
        source_rel = entry_source_rel_path(entry, item.path)
        source_path = safe_join(starter_root, source_rel)
        destination_path = safe_join(local_root, item.path)
        if source_path.is_symlink() or not source_path.is_file():
            raise ValueError(f"starter source is not a regular file: {source_rel}")
        atomic_copy_file(source_path, destination_path)
        written_paths.append(item.path)

        if item.path_class in {"managed", "scaffold_once"}:
            digest = scaffold_creation_hash(item.path) if item.path_class == "scaffold_once" else file_sha256(destination_path, content)
            lock_entries[item.path] = LockEntry(item.path, item.path_class, content, digest)
            lock_updated_paths.append(item.path)
            lock_changed = True

    for item in transaction.lock_updates:
        entry = classify_path(manifest, item.path)
        if entry is None:
            raise ValueError(f"lock update path is not in manifest: {item.path}")
        if item.path_class != "managed" or entry.path_class != "managed":
            raise ValueError(f"lock-only update is only supported for managed paths: {item.path}")
        content = entry.content or "text"
        local_hash = hash_optional_file(local_root, item.path, content)
        if local_hash is None:
            raise ValueError(f"lock-only update path does not exist: {item.path}")
        starter_hash = hash_optional_file(starter_root, entry_source_rel_path(entry, item.path), content)
        if local_hash != starter_hash:
            raise ValueError(f"lock-only update no longer matches starter content: {item.path}")
        lock_entries[item.path] = LockEntry(item.path, item.path_class, content, local_hash)
        lock_updated_paths.append(item.path)
        lock_changed = True

    if lock_changed:
        lockfile = local_root / "system-lock.toml"
        lockfile.write_text(
            lockfile_text(sorted(lock_entries.values(), key=lambda entry: entry.path), manifest.starter_version, source_label),
            encoding="utf-8",
        )
    return ApplyResult(written_paths=written_paths, lock_updated_paths=lock_updated_paths, lockfile_updated=lock_changed)


def lockfile_text(entries: list[LockEntry], starter_version: str, source: str) -> str:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    lines = [
        "schema_version = 1",
        f'starter_version = "{starter_version}"',
        f'generated_at = "{generated_at}"',
        f'source = "{source}"',
        "",
    ]
    for entry in sorted(entries, key=lambda item: item.path):
        lines.extend(
            [
                "[[paths]]",
                f'path = "{entry.path}"',
                f'class = "{entry.path_class}"',
                f'content = "{entry.content}"',
                f'sha256 = "{entry.sha256}"',
                "",
            ]
        )
    return "\n".join(lines)


def lock_source_label(local_root: Path, starter_root: Path) -> str:
    try:
        relative = starter_root.resolve().relative_to(local_root.resolve())
    except ValueError:
        return starter_root.name
    label = relative.as_posix()
    return "." if label == "." else label


def scaffold_creation_hash(rel_path: str) -> str:
    return sha256(f"scaffold_once_created:{rel_path}".encode("utf-8")).hexdigest()


def is_trusted_starter_ref(source: str) -> bool:
    return bool(SEMVER_TAG_PATTERN.fullmatch(source) or FULL_COMMIT_PATTERN.fullmatch(source))


def git_output(args: list[str], root: Path = ROOT) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(result.stdout.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def resolve_git_commit(source: str, root: Path = ROOT) -> str:
    if SEMVER_TAG_PATTERN.fullmatch(source):
        return git_output(["rev-parse", "--verify", f"refs/tags/{source}^{{commit}}"], root)
    if FULL_COMMIT_PATTERN.fullmatch(source):
        commit = git_output(["rev-parse", "--verify", f"{source}^{{commit}}"], root)
        if commit.lower() != source.lower():
            raise ValueError(f"commit did not resolve to the pinned source: {source}")
        return commit
    raise ValueError("starter source must be a local directory, semver tag, or full 40-character commit")


def safe_extract_archive(archive_path: Path, destination: Path) -> None:
    destination = destination.resolve()
    with tarfile.open(archive_path, mode="r") as archive:
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            try:
                target.relative_to(destination)
            except ValueError as exc:
                raise ValueError(f"archive member escapes destination: {member.name}") from exc
            if member.issym() or member.islnk():
                raise ValueError(f"archive links are not supported: {member.name}")
            if not member.isfile() and not member.isdir():
                raise ValueError(f"archive special files are not supported: {member.name}")
        archive.extractall(destination)


def export_git_source(source: str, destination: Path, root: Path = ROOT) -> tuple[Path, str]:
    commit = resolve_git_commit(source, root)
    starter_root = destination / "starter"
    starter_root.mkdir(parents=True)
    archive_path = destination / "starter.tar"
    git_output(["archive", "--format=tar", f"--output={archive_path}", commit], root)
    safe_extract_archive(archive_path, starter_root)
    return starter_root, f"{source}@{commit[:12]}"


def collect_adopt_entries(
    local_root: Path, starter_root: Path, manifest_path: str, include_scaffold_once: bool = True
) -> list[LockEntry]:
    local_manifest = load_manifest(local_root / manifest_path, local_root)
    load_manifest(starter_root / manifest_path, starter_root)
    lock_entries = load_lockfile(local_root / "system-lock.toml")
    entries: list[LockEntry] = []

    for rel_path in sorted(manifest_target_paths(local_manifest, local_root, starter_root)):
        entry = classify_path(local_manifest, rel_path)
        if entry is None or entry.path_class not in {"managed", "scaffold_once"} or entry.generated:
            continue
        content = entry.content or "text"
        starter_rel_path = entry_source_rel_path(entry, rel_path)
        local_hash = hash_optional_file(local_root, rel_path, content)
        locked = lock_entries.get(rel_path)

        if entry.path_class == "scaffold_once":
            if not include_scaffold_once:
                continue
            if local_hash is not None and locked is None:
                entries.append(LockEntry(rel_path, entry.path_class, content, scaffold_creation_hash(rel_path)))
            continue

        starter_hash = hash_optional_file(starter_root, starter_rel_path, content)
        if local_hash is not None and local_hash == starter_hash and (locked is None or locked.sha256 != local_hash):
            entries.append(LockEntry(rel_path, entry.path_class, content, local_hash))
    return entries


def adopt_lockfile(
    local_root: Path,
    starter_root: Path,
    manifest_path: str,
    source_label: str | None = None,
    include_scaffold_once: bool = True,
) -> tuple[SyncPlan, list[LockEntry]]:
    plan = build_sync_plan(local_root, starter_root, manifest_path)
    if plan.dirty or plan.conflicts:
        return plan, []

    manifest = load_manifest(local_root / manifest_path, local_root)
    existing_entries = load_lockfile(local_root / "system-lock.toml")
    if not include_scaffold_once:
        existing_entries = {path: entry for path, entry in existing_entries.items() if entry.path_class == "managed"}
    adopt_entries = collect_adopt_entries(local_root, starter_root, manifest_path, include_scaffold_once=include_scaffold_once)
    merged_entries = {**existing_entries, **{entry.path: entry for entry in adopt_entries}}
    (local_root / "system-lock.toml").write_text(
        lockfile_text(sorted(merged_entries.values(), key=lambda entry: entry.path), manifest.starter_version, source_label or lock_source_label(local_root, starter_root)),
        encoding="utf-8",
    )
    return plan, adopt_entries


@contextmanager
def resolve_starter_source(source: str | None, root: Path = ROOT) -> Iterator[ResolvedStarterSource]:
    if source is None:
        raise ValueError("sync mode requires --from <local-starter-path>")
    path = Path(source).expanduser().resolve()
    if path.exists():
        if not path.is_dir():
            raise ValueError(f"starter source is not a directory: {source}")
        yield ResolvedStarterSource(path, path.as_posix(), True)
        return

    if not is_trusted_starter_ref(source):
        raise ValueError("starter source must be a local directory, semver tag, or full 40-character commit")

    with tempfile.TemporaryDirectory(prefix="codexhome-starter-") as temp_dir:
        starter_root, label = export_git_source(source, Path(temp_dir), root)
        yield ResolvedStarterSource(starter_root, label, False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check CodexHome starter sync manifest state.")
    parser.add_argument("--manifest", default="system-manifest.toml", help="Path to system manifest.")
    parser.add_argument("--check", action="store_true", help="Run read-only manifest and coverage checks.")
    parser.add_argument("--from", dest="starter_source", help="Local starter checkout/path for dry-run sync.")
    parser.add_argument("--dry-run", action="store_true", help="Plan starter sync without writing files.")
    parser.add_argument("--adopt", action="store_true", help="Write lockfile baselines for matching managed paths.")
    parser.add_argument(
        "--managed-only-lock",
        action="store_true",
        help="With --adopt, write only managed entries for a clean starter release baseline.",
    )
    parser.add_argument("--allow-local-adopt", action="store_true", help="Allow adopt from a local directory bootstrap source.")
    parser.add_argument("--apply", action="store_true", help="Apply safe starter sync operations.")
    parser.add_argument("--allow-local-apply", action="store_true", help="Allow apply from a local directory development source.")
    args = parser.parse_args()

    selected_modes = sum(1 for selected in [args.check, args.dry_run, args.adopt, args.apply] if selected)
    if selected_modes != 1:
        print("ERROR: choose exactly one mode: --check, --dry-run, --adopt, or --apply", file=sys.stderr)
        return 2

    try:
        if args.check:
            manifest = load_manifest((ROOT / args.manifest).resolve(), ROOT)
            result = check_manifest(manifest)
            print_check(manifest, result)
            return 1 if result["missing_sources"] or result["missing_managed"] else 0

        with resolve_starter_source(args.starter_source) as starter_source:
            starter_root = starter_source.path
            starter_label = starter_source.label
            lock_source = lock_source_label(ROOT, starter_root) if starter_source.is_local_path else starter_label
            if args.adopt and starter_source.is_local_path and not args.allow_local_adopt:
                print("ERROR: --adopt requires a semver tag or full commit; use --allow-local-adopt for bootstrap.", file=sys.stderr)
                return 1
            if args.apply and starter_source.is_local_path and not args.allow_local_apply:
                print("ERROR: --apply requires a semver tag or full commit; use --allow-local-apply for development.", file=sys.stderr)
                return 1
            if args.adopt:
                plan, adopted = adopt_lockfile(
                    ROOT,
                    starter_root,
                    args.manifest,
                    lock_source,
                    include_scaffold_once=not args.managed_only_lock,
                )
            elif args.apply:
                result = apply_sync_plan(ROOT, starter_root, args.manifest, lock_source)
                print("# System Sync Apply")
                print()
                print(f"Starter source: {starter_label}")
                print(f"Written paths: {len(result.written_paths)}")
                for rel_path in result.written_paths:
                    print(f"- {rel_path}")
                print(f"Lock-updated paths: {len(result.lock_updated_paths)}")
                for rel_path in result.lock_updated_paths:
                    print(f"- {rel_path}")
                print("Lockfile updated." if result.lockfile_updated else "Lockfile unchanged.")
                return 0
            else:
                plan = build_sync_plan(ROOT, starter_root, args.manifest)
                adopted = []

            if plan.dirty:
                print("ERROR: dirty worktree detected; dry-run requires a clean worktree.", file=sys.stderr)
                for line in plan.dirty:
                    print(f"- {line}", file=sys.stderr)
                return 1

            if args.adopt:
                if plan.conflicts:
                    print_dry_run(starter_label, plan)
                    print("ERROR: adopt refused because conflicts require explicit review.", file=sys.stderr)
                    return 1
                print("# System Lock Adopt")
                print()
                print(f"Starter source: {starter_label}")
                print(f"Adopted entries: {len(adopted)}")
                print(f"Lockfile: {ROOT / 'system-lock.toml'}")
                return 0

            print_dry_run(starter_label, plan)
            return 1 if dry_run_blockers(plan) else 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
