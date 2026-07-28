from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

from incident_case import INCIDENTS, build_indexes, load_yaml, slugify, write_yaml


ROOT = Path(__file__).resolve().parents[1]
LOCAL_ROOT = INCIDENTS / ".local"
OBJECTS = LOCAL_ROOT / "objects"
MIGRATION_NAMESPACE = uuid.UUID("e87a11d0-32df-44bd-928f-ed48935ec56a")
LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1\n"


@dataclass(frozen=True)
class Source:
    family: str
    source_id: str
    cases_dir: Path
    repo_root: Path | None
    tracked: frozenset[str]


@dataclass(frozen=True)
class FileRecord:
    source_id: str
    family: str
    legacy_name: str
    relative_path: str
    sha256: str
    bytes: int
    tracked: bool
    lfs_pointer: bool
    lfs_oid: str | None
    symlink_target: str | None


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def digest_records(records: list[FileRecord]) -> str:
    digest = hashlib.sha256()
    for record in sorted(records, key=lambda item: item.relative_path):
        digest.update(record.relative_path.encode())
        digest.update(b"\0")
        digest.update(record.sha256.encode())
        digest.update(b"\0")
        digest.update(str(record.bytes).encode())
        digest.update(b"\0")
        digest.update((record.symlink_target or "").encode())
        digest.update(b"\n")
    return digest.hexdigest()


def run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def resolve_source(family: str, source_id: str, raw_path: str) -> Source:
    cases_dir = Path(raw_path).expanduser().resolve()
    if not cases_dir.is_dir():
        raise ValueError(f"missing cases directory: {cases_dir}")
    if slugify(family) != family or slugify(source_id) != source_id:
        raise ValueError("family and source id must be lowercase kebab-case")

    root_result = run_git(cases_dir, "rev-parse", "--show-toplevel")
    repo_root: Path | None = None
    tracked: frozenset[str] = frozenset()
    if root_result.returncode == 0:
        repo_root = Path(root_result.stdout.decode().strip()).resolve()
        cases_relative = cases_dir.relative_to(repo_root).as_posix()
        tracked_result = run_git(repo_root, "ls-files", "-z", "--", cases_relative)
        tracked = frozenset(
            item.decode()
            for item in tracked_result.stdout.split(b"\0")
            if item
        )
    return Source(family, source_id, cases_dir, repo_root, tracked)


def case_id(opened: date, family: str, legacy_name: str) -> str:
    key = f"{family}:{legacy_name}"
    suffix = hashlib.sha256(key.encode()).hexdigest()[:8]
    return (
        f"{opened.isoformat()}-legacy-{slugify(family)}-"
        f"{slugify(legacy_name)[:40]}-{suffix}"
    )


def lfs_oid(path: Path) -> tuple[bool, str | None]:
    if path.stat().st_size > 1024:
        return False, None
    content = path.read_bytes()
    if not content.startswith(LFS_POINTER_PREFIX):
        return False, None
    for line in content.decode().splitlines():
        if line.startswith("oid sha256:"):
            return True, line.removeprefix("oid sha256:")
    return True, None


def ensure_object(source_path: Path, sha256: str) -> Path:
    object_path = OBJECTS / sha256[:2] / sha256
    object_path.parent.mkdir(parents=True, exist_ok=True)
    if object_path.exists():
        if digest_file(object_path) != sha256:
            raise RuntimeError(f"corrupt local object: {sha256}")
        return object_path
    temporary = object_path.with_suffix(".tmp")
    shutil.copy2(source_path, temporary)
    if digest_file(temporary) != sha256:
        temporary.unlink()
        raise RuntimeError(f"copy verification failed: {source_path}")
    temporary.replace(object_path)
    object_path.chmod(0o440)
    return object_path


def materialize(object_path: Path, destination: Path, sha256: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not destination.is_file() or digest_file(destination) != sha256:
            raise RuntimeError(f"destination collision: {destination}")
        return
    try:
        os.link(object_path, destination)
    except OSError:
        shutil.copy2(object_path, destination)
    if digest_file(destination) != sha256:
        destination.unlink()
        raise RuntimeError(f"materialization verification failed: {destination}")


def tracked_path(source: Source, file_path: Path) -> bool:
    if source.repo_root is None:
        return False
    return file_path.relative_to(source.repo_root).as_posix() in source.tracked


def scan_variant(source: Source, legacy_dir: Path) -> list[FileRecord]:
    records: list[FileRecord] = []
    for file_path in sorted(path for path in legacy_dir.rglob("*") if path.is_file() or path.is_symlink()):
        symlink_target: str | None = None
        if file_path.is_symlink():
            resolved_target = file_path.resolve()
            if not resolved_target.is_file() or not resolved_target.is_relative_to(source.cases_dir):
                raise RuntimeError(f"unsafe or missing symlink target: {file_path}")
            symlink_target = os.readlink(file_path)
        relative = file_path.relative_to(legacy_dir).as_posix()
        file_digest = digest_file(file_path)
        is_pointer, pointer_oid = lfs_oid(file_path)
        records.append(
            FileRecord(
                source_id=source.source_id,
                family=source.family,
                legacy_name=legacy_dir.name,
                relative_path=relative,
                sha256=file_digest,
                bytes=file_path.stat().st_size,
                tracked=tracked_path(source, file_path),
                lfs_pointer=is_pointer,
                lfs_oid=pointer_oid,
                symlink_target=symlink_target,
            )
        )
    return records


def safe_summary(
    *,
    migration_run: str,
    opened: date,
    sources: list[Source],
    records: list[FileRecord],
    groups: dict[tuple[str, str], list[FileRecord]],
) -> dict[str, Any]:
    source_rows = []
    for source in sources:
        source_records = [record for record in records if record.source_id == source.source_id]
        source_rows.append(
            {
                "source_id": source.source_id,
                "family": source.family,
                "cases": len({record.legacy_name for record in source_records}),
                "files": len(source_records),
                "bytes": sum(record.bytes for record in source_records),
                "tracked_files": sum(record.tracked for record in source_records),
                "lfs_pointers": sum(record.lfs_pointer for record in source_records),
            }
        )
    unique_objects: dict[str, int] = {}
    for record in records:
        unique_objects.setdefault(record.sha256, record.bytes)
    return {
        "schema_version": 1,
        "migration_run": migration_run,
        "created": opened.isoformat(),
        "state": "verified-local-copy",
        "source_deletion_authorized": False,
        "sources": source_rows,
        "totals": {
            "canonical_cases": len(groups),
            "source_files": len(records),
            "source_bytes": sum(record.bytes for record in records),
            "unique_objects": len(unique_objects),
            "unique_bytes": sum(unique_objects.values()),
            "lfs_pointers": sum(record.lfs_pointer for record in records),
        },
        "cutover_gates": [
            "privacy review of committed case reports",
            "second durable copy or approved private object store",
            "legacy cross-reference repair",
            "product replay and regression fixture extraction",
            "restore drill and explicit source-deletion approval",
        ],
    }


def write_local_inventory(
    *,
    migration_run: str,
    records: list[FileRecord],
    sources: list[Source],
) -> Path:
    run_dir = LOCAL_ROOT / "migrations" / migration_run
    run_dir.mkdir(parents=True, exist_ok=True)
    source_paths = {source.source_id: str(source.cases_dir) for source in sources}
    (run_dir / "sources.json").write_text(
        json.dumps(source_paths, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (run_dir / "inventory.jsonl").open("w", encoding="utf-8") as handle:
        for record in sorted(
            records,
            key=lambda item: (item.family, item.legacy_name, item.source_id, item.relative_path),
        ):
            handle.write(
                json.dumps(
                    {
                        **record.__dict__,
                        "disposition": "case-local",
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    return run_dir


def write_case(
    *,
    opened: date,
    owner: str,
    migration_run: str,
    family: str,
    legacy_name: str,
    records: list[FileRecord],
) -> Path:
    canonical_id = case_id(opened, family, legacy_name)
    canonical_dir = INCIDENTS / canonical_id
    canonical_dir.mkdir(parents=True, exist_ok=True)

    variants: list[dict[str, Any]] = []
    local_manifest: list[dict[str, Any]] = []
    for source_id in sorted({record.source_id for record in records}):
        source_records = [record for record in records if record.source_id == source_id]
        variant_root = canonical_dir / "local" / "legacy" / source_id
        for record in source_records:
            object_path = OBJECTS / record.sha256[:2] / record.sha256
            materialize(
                object_path,
                variant_root / record.relative_path,
                record.sha256,
            )
            local_manifest.append(record.__dict__)
        variants.append(
            {
                "source_id": source_id,
                "tree_sha256": digest_records(source_records),
                "files": len(source_records),
                "bytes": sum(record.bytes for record in source_records),
                "tracked_files": sum(record.tracked for record in source_records),
                "lfs_pointers": sum(record.lfs_pointer for record in source_records),
            }
        )

    manifest_path = canonical_dir / "case.yaml"
    existing: dict[str, Any] = {}
    if manifest_path.exists():
        existing = load_yaml(manifest_path)
        expected_alias = f"{family}:cases/{legacy_name}"
        if expected_alias not in existing.get("aliases", []):
            raise RuntimeError(f"existing case does not match legacy alias: {canonical_dir}")

    aggregate = hashlib.sha256()
    for variant in variants:
        aggregate.update(variant["source_id"].encode())
        aggregate.update(b"\0")
        aggregate.update(variant["tree_sha256"].encode())
        aggregate.update(b"\n")
    unique_objects: dict[str, int] = {}
    for record in records:
        unique_objects.setdefault(record.sha256, record.bytes)

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "case_id": canonical_id,
        "uuid": existing.get("uuid") or str(uuid.uuid5(MIGRATION_NAMESPACE, f"{family}:{legacy_name}")),
        "title": f"Legacy {family} case {legacy_name}",
        "kind": "investigation",
        "status": "imported",
        "confidence": "unreviewed",
        "opened_at": opened.isoformat(),
        "systems": [family],
        "environments": ["unknown"],
        "owner": owner,
        "aliases": [f"{family}:cases/{legacy_name}"],
        "privacy": {
            "classification": "restricted",
            "review": "required",
        },
        "evidence": {
            "state": "local-only",
            "root_sha256": aggregate.hexdigest(),
            "files": len(records),
            "bytes": sum(record.bytes for record in records),
            "unique_objects": len(unique_objects),
            "unique_bytes": sum(unique_objects.values()),
            "variants": variants,
        },
        "retention": {
            "owner": owner,
            "review_due": (opened + timedelta(days=90)).isoformat(),
            "local_until": (opened + timedelta(days=365)).isoformat(),
        },
        "knowledge": {
            "status": "pending",
        },
        "provenance": {
            "migration_run": migration_run,
            "verified": True,
        },
    }
    write_yaml(manifest_path, manifest)
    local_manifest_path = canonical_dir / "local" / "import-manifest.jsonl"
    local_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with local_manifest_path.open("w", encoding="utf-8") as handle:
        for item in sorted(
            local_manifest,
            key=lambda value: (str(value["source_id"]), str(value["relative_path"])),
        ):
            handle.write(json.dumps(item, sort_keys=True) + "\n")
    return canonical_dir


def build_compatibility_view(
    *,
    opened: date,
    groups: dict[tuple[str, str], list[FileRecord]],
) -> None:
    compat_root = LOCAL_ROOT / "compat"
    for (family, legacy_name), records in sorted(groups.items()):
        source_ids = sorted({record.source_id for record in records})
        if not source_ids:
            continue
        active = [source_id for source_id in source_ids if source_id.endswith("-active")]
        source_id = active[0] if active else source_ids[0]
        canonical_dir = INCIDENTS / case_id(opened, family, legacy_name)
        target = canonical_dir / "local" / "legacy" / source_id
        link = compat_root / family / "cases" / legacy_name
        link.parent.mkdir(parents=True, exist_ok=True)
        relative_target = os.path.relpath(target, link.parent)
        if link.is_symlink():
            if os.readlink(link) != relative_target:
                raise RuntimeError(f"compatibility link mismatch: {link}")
            continue
        if link.exists():
            raise RuntimeError(f"compatibility path collision: {link}")
        link.symlink_to(relative_target, target_is_directory=True)


def migrate(args: argparse.Namespace) -> dict[str, Any]:
    opened = date.fromisoformat(args.date)
    migration_run = args.run_id or f"{opened.isoformat()}-legacy-case-centralization"
    sources = [
        resolve_source(family, source_id, raw_path)
        for family, source_id, raw_path in args.source
    ]
    records: list[FileRecord] = []
    groups: dict[tuple[str, str], list[FileRecord]] = defaultdict(list)

    for source in sources:
        for legacy_dir in sorted(path for path in source.cases_dir.iterdir() if path.is_dir()):
            variant_records = scan_variant(source, legacy_dir)
            records.extend(variant_records)
            groups[(source.family, legacy_dir.name)].extend(variant_records)

    summary = safe_summary(
        migration_run=migration_run,
        opened=opened,
        sources=sources,
        records=records,
        groups=groups,
    )
    if not args.apply:
        print(yaml.safe_dump(summary, sort_keys=False), end="")
        return summary
    if summary["totals"]["lfs_pointers"]:
        raise RuntimeError(
            "LFS pointer files detected; hydrate LFS objects before applying migration"
        )

    for source in sources:
        for legacy_dir in sorted(path for path in source.cases_dir.iterdir() if path.is_dir()):
            for file_path in sorted(path for path in legacy_dir.rglob("*") if path.is_file()):
                ensure_object(file_path, digest_file(file_path))

    write_local_inventory(
        migration_run=migration_run,
        records=records,
        sources=sources,
    )
    for (family, legacy_name), group_records in sorted(groups.items()):
        write_case(
            opened=opened,
            owner=args.owner,
            migration_run=migration_run,
            family=family,
            legacy_name=legacy_name,
            records=group_records,
        )
    build_compatibility_view(opened=opened, groups=groups)

    migrations_dir = INCIDENTS / "migrations"
    migrations_dir.mkdir(exist_ok=True)
    write_yaml(migrations_dir / f"{migration_run}.yaml", summary)
    build_indexes()
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Hash, deduplicate, and copy legacy incident cases into CodexHome."
    )
    parser.add_argument(
        "--source",
        nargs=3,
        action="append",
        metavar=("FAMILY", "SOURCE_ID", "CASES_DIR"),
        required=True,
    )
    parser.add_argument("--owner", required=True)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--run-id")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        summary = migrate(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"migration failed: {exc}")
        return 1
    if args.apply:
        print(
            "migrated "
            f"{summary['totals']['canonical_cases']} cases, "
            f"{summary['totals']['source_files']} source files, "
            f"{summary['totals']['source_bytes']} source bytes"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
