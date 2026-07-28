from __future__ import annotations

import argparse
import fcntl
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import keyring
import pyrage
import yaml
import zstandard
from pyrage.x25519 import Identity, Recipient


ROOT = Path(__file__).resolve().parents[1]
INCIDENTS = ROOT / "incidents"
OFFLOAD_ROOT = INCIDENTS / ".local" / "offload"
PUBLIC_RECIPIENTS_PATH = INCIDENTS / "PUBLIC-AGE-RECIPIENTS.yaml"
KEYRING_SERVICE = "codexhome.incident-evidence"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SOURCE_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
RCLONE_DESTINATION_RE = re.compile(r"^[A-Za-z0-9_.@-]+:[^\s]*$")
PUBLIC_RECIPIENT_ROLES = {"primary", "escrow"}
PUBLIC_RECIPIENT_STATUSES = {"active", "retired", "compromised"}
CHUNK_BYTES = 1024 * 1024
MAX_MANIFEST_BYTES = 16 * 1024 * 1024


class EvidenceError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


class HashingReader:
    def __init__(self, source: Any) -> None:
        self.source = source
        self.digest = hashlib.sha256()

    def read(self, size: int = -1) -> bytes:
        content = self.source.read(size)
        self.digest.update(content)
        return content

    def hexdigest(self) -> str:
        return self.digest.hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EvidenceError(f"{path.name} must contain a mapping")
    return value


def load_public_recipient_registry(
    path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    path = path or PUBLIC_RECIPIENTS_PATH
    if not path.exists():
        return {}
    raw = path.read_bytes()
    if b"\r" in raw:
        raise EvidenceError(f"{path.name} must use LF line endings")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvidenceError(f"{path.name} must be UTF-8 text") from exc
    if "AGE-SECRET-KEY-" in text:
        raise EvidenceError(f"{path.name} contains a private age identity")
    try:
        value = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise EvidenceError(f"{path.name} contains invalid YAML") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"{path.name} must contain a mapping")
    allowed_top_fields = {"schema_version", "kind", "notice", "recipients"}
    unknown_top_fields = set(value) - allowed_top_fields
    if unknown_top_fields:
        raise EvidenceError(
            f"{path.name} has unsupported fields: {sorted(unknown_top_fields)}"
        )
    if value.get("schema_version") != 1:
        raise EvidenceError(f"{path.name} schema_version must be 1")
    if value.get("kind") != "public-age-recipient-registry":
        raise EvidenceError(
            f"{path.name} kind must be public-age-recipient-registry"
        )
    recipients = value.get("recipients")
    if not isinstance(recipients, list):
        raise EvidenceError(f"{path.name} recipients must be a list")

    registry: dict[str, dict[str, Any]] = {}
    public_values: set[str] = set()
    for index, item in enumerate(recipients):
        label = f"{path.name} recipient {index + 1}"
        if not isinstance(item, dict):
            raise EvidenceError(f"{label} must be a mapping")
        allowed_fields = {
            "id",
            "role",
            "public_age_recipient",
            "status",
            "owner",
            "custody",
            "introduced_at",
            "review_due",
        }
        unknown_fields = set(item) - allowed_fields
        if unknown_fields:
            raise EvidenceError(
                f"{label} has unsupported fields: {sorted(unknown_fields)}"
            )
        recipient_id = item.get("id")
        if not isinstance(recipient_id, str) or not SOURCE_ID_RE.fullmatch(
            recipient_id
        ):
            raise EvidenceError(f"{label} id must be lower-case kebab-case")
        if recipient_id in registry:
            raise EvidenceError(f"{path.name} has duplicate id: {recipient_id}")
        role = item.get("role")
        if role not in PUBLIC_RECIPIENT_ROLES:
            raise EvidenceError(
                f"{label} role must be one of {sorted(PUBLIC_RECIPIENT_ROLES)}"
            )
        status = item.get("status")
        if status not in PUBLIC_RECIPIENT_STATUSES:
            raise EvidenceError(
                f"{label} status must be one of {sorted(PUBLIC_RECIPIENT_STATUSES)}"
            )
        public_value = item.get("public_age_recipient")
        if not isinstance(public_value, str):
            raise EvidenceError(f"{label} public_age_recipient is required")
        try:
            public_value = str(Recipient.from_str(public_value))
        except Exception as exc:
            raise EvidenceError(
                f"{label} public_age_recipient is invalid"
            ) from exc
        if public_value in public_values:
            raise EvidenceError(
                f"{path.name} has a duplicate public_age_recipient"
            )
        public_values.add(public_value)
        for field in ("owner", "custody"):
            if not isinstance(item.get(field), str) or not item[field]:
                raise EvidenceError(f"{label} {field} is required")
        for field in ("introduced_at", "review_due"):
            try:
                datetime.fromisoformat(str(item.get(field)))
            except ValueError as exc:
                raise EvidenceError(f"{label} {field} must be ISO-8601") from exc
        registry[recipient_id] = {**item, "public_age_recipient": public_value}
    return registry


def recipient_usage_report(
    *,
    incidents_path: Path | None = None,
    registry_path: Path | None = None,
) -> dict[str, Any]:
    incidents_path = incidents_path or INCIDENTS
    registry = load_public_recipient_registry(registry_path)
    usage: dict[str, list[dict[str, str]]] = {
        recipient_id: [] for recipient_id in registry
    }
    for case_dir in sorted(incidents_path.iterdir()):
        case_path = case_dir / "case.yaml"
        if not case_dir.is_dir() or not case_path.is_file():
            continue
        case = load_yaml(case_path)
        evidence = case.get("evidence")
        offload = evidence.get("offload") if isinstance(evidence, dict) else None
        drills = offload.get("restore_drills") if isinstance(offload, dict) else None
        if not isinstance(drills, dict):
            continue
        case_id = case.get("case_id")
        case_uuid = case.get("uuid")
        if not isinstance(case_id, str) or not case_id:
            raise EvidenceError(f"{case_dir.name} has no case_id")
        try:
            case_uuid = str(uuid.UUID(str(case_uuid)))
        except ValueError as exc:
            raise EvidenceError(f"{case_dir.name} has an invalid UUID") from exc
        for role in ("primary", "escrow"):
            drill = drills.get(role)
            if not isinstance(drill, dict):
                continue
            recipient_id = drill.get("recipient_id")
            entry = registry.get(str(recipient_id))
            if entry is None:
                raise EvidenceError(
                    f"{case_dir.name} references unknown public recipient ID "
                    f"{recipient_id!r}"
                )
            if entry.get("role") != role:
                raise EvidenceError(
                    f"{case_dir.name} public recipient ID {recipient_id!r} "
                    f"has role {entry.get('role')!r}, expected {role!r}"
                )
            if entry.get("public_age_recipient") != drill.get("recipient"):
                raise EvidenceError(
                    f"{case_dir.name} public recipient ID {recipient_id!r} "
                    "does not match the restore receipt"
                )
            verified_at = drill.get("verified_at")
            if not isinstance(verified_at, str) or not verified_at:
                raise EvidenceError(
                    f"{case_dir.name} {role} restore drill has no verified_at"
                )
            usage[str(recipient_id)].append(
                {
                    "case_id": case_id,
                    "case_uuid": case_uuid,
                    "custody": role,
                    "verified_at": verified_at,
                }
            )
    return {
        "schema_version": 1,
        "source": "committed-restore-receipts",
        "recipients": [
            {
                "id": recipient_id,
                "role": entry["role"],
                "status": entry["status"],
                "case_count": len(usage[recipient_id]),
                "cases": usage[recipient_id],
            }
            for recipient_id, entry in registry.items()
        ],
    }


def resolve_public_recipient_ids(
    recipient_ids: list[str],
    *,
    path: Path | None = None,
) -> tuple[list[str], dict[str, str]]:
    registry = load_public_recipient_registry(path)
    if len(recipient_ids) != len(set(recipient_ids)):
        raise EvidenceError("public recipient IDs must be distinct")
    selected: dict[str, str] = {}
    roles: set[str] = set()
    for recipient_id in recipient_ids:
        entry = registry.get(recipient_id)
        if entry is None:
            raise EvidenceError(f"unknown public recipient ID: {recipient_id}")
        if entry["status"] != "active":
            raise EvidenceError(
                f"public recipient ID is not active: {recipient_id}"
            )
        selected[recipient_id] = str(entry["public_age_recipient"])
        roles.add(str(entry["role"]))
    if roles != PUBLIC_RECIPIENT_ROLES:
        raise EvidenceError(
            "select active public recipient IDs for primary and escrow roles"
        )
    return list(selected.values()), selected


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(content)
    try:
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def write_yaml(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = yaml.safe_dump(value, allow_unicode=True, sort_keys=False)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(content)
    try:
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def resolve_case(value: str) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = INCIDENTS / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(INCIDENTS.resolve())
    except ValueError as exc:
        raise EvidenceError("case must be inside the incidents directory") from exc
    if not candidate.is_dir() or not (candidate / "case.yaml").is_file():
        raise EvidenceError(f"incident case does not exist: {candidate}")
    return candidate


def safe_relative_path(value: str, *, label: str) -> PurePosixPath:
    if "\0" in value or "\\" in value:
        raise EvidenceError(f"unsafe {label}: {value!r}")
    path = PurePosixPath(value)
    if not value or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise EvidenceError(f"unsafe {label}: {value!r}")
    return path


def safe_symlink_target(value: Any, *, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or "\0" in value or "\\" in value:
        raise EvidenceError(f"unsafe {label}")
    if PurePosixPath(value).is_absolute():
        raise EvidenceError(f"unsafe {label}")
    return value


def validate_sha256(value: Any, *, label: str) -> str:
    text = str(value)
    if not SHA256_RE.fullmatch(text):
        raise EvidenceError(f"invalid {label}")
    return text


def digest_records(records: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for record in sorted(records, key=lambda item: str(item["relative_path"])):
        digest.update(str(record["relative_path"]).encode())
        digest.update(b"\0")
        digest.update(str(record["sha256"]).encode())
        digest.update(b"\0")
        digest.update(str(record["bytes"]).encode())
        digest.update(b"\0")
        digest.update(str(record.get("symlink_target") or "").encode())
        digest.update(b"\n")
    return digest.hexdigest()


def aggregate_root(variants: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for variant in sorted(variants, key=lambda item: str(item["source_id"])):
        digest.update(str(variant["source_id"]).encode())
        digest.update(b"\0")
        digest.update(str(variant["tree_sha256"]).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def load_import_records(case_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    manifest_path = case_dir / "local" / "import-manifest.jsonl"
    if not manifest_path.is_file():
        raise EvidenceError(
            "case has no local/import-manifest.jsonl; offload currently requires a "
            "hash-first migrated case"
        )

    records: list[dict[str, Any]] = []
    seen_paths: set[tuple[str, str]] = set()
    with manifest_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EvidenceError(
                    f"invalid import manifest line {line_number}: {exc}"
                ) from exc
            if not isinstance(record, dict):
                raise EvidenceError(f"invalid import manifest line {line_number}")
            source_id = str(record.get("source_id", ""))
            if not SOURCE_ID_RE.fullmatch(source_id):
                raise EvidenceError(f"invalid source_id on line {line_number}")
            relative = safe_relative_path(
                str(record.get("relative_path", "")),
                label=f"relative path on line {line_number}",
            ).as_posix()
            key = (source_id, relative)
            if key in seen_paths:
                raise EvidenceError(f"duplicate imported path: {source_id}/{relative}")
            seen_paths.add(key)
            sha256 = validate_sha256(
                record.get("sha256"),
                label=f"sha256 on line {line_number}",
            )
            try:
                size = int(record["bytes"])
            except (KeyError, TypeError, ValueError) as exc:
                raise EvidenceError(f"invalid byte count on line {line_number}") from exc
            if size < 0:
                raise EvidenceError(f"invalid byte count on line {line_number}")
            symlink_target = safe_symlink_target(
                record.get("symlink_target"),
                label=f"symlink target on line {line_number}",
            )

            source_path = case_dir / "local" / "legacy" / source_id / relative
            if source_path.is_symlink() or not source_path.is_file():
                raise EvidenceError(f"missing regular evidence file: {source_id}/{relative}")
            if source_path.stat().st_size != size:
                raise EvidenceError(f"evidence size mismatch: {source_id}/{relative}")
            if sha256_file(source_path) != sha256:
                raise EvidenceError(f"evidence hash mismatch: {source_id}/{relative}")
            records.append(
                {
                    "source_id": source_id,
                    "relative_path": relative,
                    "sha256": sha256,
                    "bytes": size,
                    "symlink_target": symlink_target,
                }
            )

    variants: list[dict[str, Any]] = []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record["source_id"])].append(record)
    for source_id, source_records in sorted(grouped.items()):
        variants.append(
            {
                "source_id": source_id,
                "tree_sha256": digest_records(source_records),
                "files": len(source_records),
                "bytes": sum(int(item["bytes"]) for item in source_records),
            }
        )
    return records, variants


def deterministic_tar_info(name: str, size: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = size
    info.mtime = 0
    info.mode = 0o400
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    return info


def add_bytes(archive: tarfile.TarFile, name: str, content: bytes) -> None:
    archive.addfile(deterministic_tar_info(name, len(content)), io.BytesIO(content))


def state_path(case_uuid: str) -> Path:
    return OFFLOAD_ROOT / case_uuid / "state.json"


def load_state(case_uuid: str) -> dict[str, Any]:
    path = state_path(case_uuid)
    if not path.is_file():
        raise EvidenceError("no local offload state; create a bundle first")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EvidenceError("invalid local offload state")
    return value


@contextmanager
def locked_state(case_uuid: str):
    lock_path = state_path(case_uuid).with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a", encoding="utf-8") as handle:
        os.chmod(lock_path, 0o600)
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def build_bundle(
    case_dir: Path,
    recipient_strings: list[str],
    *,
    recipient_ids: dict[str, str] | None = None,
) -> dict[str, Any]:
    try:
        recipients_by_public = {
            str(recipient): recipient
            for recipient in (
                Recipient.from_str(value) for value in recipient_strings
            )
        }
    except Exception as exc:
        raise EvidenceError(f"invalid age recipient: {exc}") from exc
    if len(recipients_by_public) < 2:
        raise EvidenceError("at least two distinct age recipients are required")
    if recipient_ids is not None and set(recipient_ids.values()) != set(
        recipients_by_public
    ):
        raise EvidenceError("public recipient IDs do not match bundle recipients")
    recipients = list(recipients_by_public.values())

    case = load_yaml(case_dir / "case.yaml")
    case_uuid = str(case.get("uuid", ""))
    evidence = case.get("evidence")
    if not case_uuid or not isinstance(evidence, dict):
        raise EvidenceError("case.yaml is missing UUID or evidence metadata")
    expected_root = validate_sha256(
        evidence.get("root_sha256"),
        label="case evidence root_sha256",
    )
    records, variants = load_import_records(case_dir)
    if not records:
        raise EvidenceError("cannot offload an empty evidence inventory")
    calculated_root = aggregate_root(variants)
    if calculated_root != expected_root:
        raise EvidenceError(
            f"case evidence root mismatch: expected {expected_root}, got {calculated_root}"
        )

    manifest = {
        "schema_version": 1,
        "format": "codexhome-incident-evidence",
        "case_id": case_dir.name,
        "case_uuid": case_uuid,
        "created_from_root_sha256": calculated_root,
        "files": len(records),
        "bytes": sum(int(item["bytes"]) for item in records),
        "variants": variants,
        "records": sorted(
            records,
            key=lambda item: (str(item["source_id"]), str(item["relative_path"])),
        ),
    }
    manifest_bytes = (
        json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode() + b"\n"
    )
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()

    output_dir = OFFLOAD_ROOT / case_uuid
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(dir=output_dir, prefix=".bundle-") as temporary_name:
        temporary = Path(temporary_name)
        tar_path = temporary / "bundle.tar"
        compressed_path = temporary / "bundle.tar.zst"
        encrypted_path = temporary / "bundle.age"

        with tarfile.open(tar_path, mode="w", format=tarfile.PAX_FORMAT) as archive:
            add_bytes(archive, "manifest.json", manifest_bytes)
            objects: dict[str, Path] = {}
            for record in records:
                objects.setdefault(
                    str(record["sha256"]),
                    case_dir
                    / "local"
                    / "legacy"
                    / str(record["source_id"])
                    / str(record["relative_path"]),
                )
            for sha256, source_path in sorted(objects.items()):
                info = deterministic_tar_info(
                    f"objects/{sha256[:2]}/{sha256}",
                    source_path.stat().st_size,
                )
                with source_path.open("rb") as source:
                    hashing_source = HashingReader(source)
                    archive.addfile(info, hashing_source)
                    if hashing_source.hexdigest() != sha256:
                        raise EvidenceError(
                            f"evidence changed while bundling: {source_path.name}"
                        )

        compressor = zstandard.ZstdCompressor(level=9, threads=0)
        with tar_path.open("rb") as source, compressed_path.open("wb") as destination:
            compressor.copy_stream(source, destination)
        archive_sha256 = sha256_file(compressed_path)

        with compressed_path.open("rb") as source, encrypted_path.open("wb") as destination:
            pyrage.encrypt_io(source, destination, recipients)
        ciphertext_sha256 = sha256_file(encrypted_path)
        bundle_name = f"{ciphertext_sha256}.tar.zst.age"
        bundle_path = output_dir / bundle_name
        if bundle_path.exists():
            if sha256_file(bundle_path) != ciphertext_sha256:
                raise EvidenceError(f"bundle collision: {bundle_path.name}")
        else:
            encrypted_path.replace(bundle_path)
            os.chmod(bundle_path, 0o600)

    state = {
        "schema_version": 1,
        "case_uuid": case_uuid,
        "case_root_sha256": calculated_root,
        "manifest_sha256": manifest_sha256,
        "archive_sha256": archive_sha256,
        "ciphertext_sha256": ciphertext_sha256,
        "bundle_name": bundle_name,
        "bundle_path": str(bundle_path),
        "recipients": sorted(recipients_by_public),
        "recipient_ids": recipient_ids or {},
        "files": len(records),
        "bytes": sum(int(item["bytes"]) for item in records),
        "created_at": utc_now(),
        "remote": None,
        "drills": [],
        "offloaded": False,
    }
    write_json(state_path(case_uuid), state)
    for previous_bundle in output_dir.glob("*.tar.zst.age"):
        if previous_bundle != bundle_path:
            previous_bundle.unlink()
    return state


def load_identity(*, keyring_label: str | None, identity_file: Path | None) -> Identity:
    if bool(keyring_label) == bool(identity_file):
        raise EvidenceError("select exactly one identity source")
    if keyring_label:
        value = keyring.get_password(KEYRING_SERVICE, keyring_label)
        if not value:
            raise EvidenceError(f"age identity not found in keyring: {keyring_label}")
    else:
        assert identity_file is not None
        identity_lines = [
            line.strip()
            for line in identity_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        secret_lines = [
            line for line in identity_lines if line.startswith("AGE-SECRET-KEY-1")
        ]
        if len(secret_lines) != 1:
            raise EvidenceError("identity file must contain exactly one age identity")
        value = secret_lines[0]
    try:
        return Identity.from_str(value)
    except Exception as exc:
        raise EvidenceError("invalid age identity") from exc


def decrypt_bundle(bundle_path: Path, identity: Identity, destination: Path) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=False)
    os.chmod(destination, 0o700)
    compressed_path = destination / "bundle.tar.zst"
    tar_path = destination / "bundle.tar"
    try:
        with bundle_path.open("rb") as source, compressed_path.open("wb") as output:
            pyrage.decrypt_io(source, output, [identity])
    except Exception as exc:
        raise EvidenceError("age decryption failed") from exc

    decompressor = zstandard.ZstdDecompressor()
    try:
        with compressed_path.open("rb") as source, tar_path.open("wb") as output:
            decompressor.copy_stream(source, output)
    except zstandard.ZstdError as exc:
        raise EvidenceError("zstd decompression failed") from exc

    object_root = destination / "objects"
    restored_root = destination / "restored"
    object_root.mkdir()
    restored_root.mkdir()
    with tarfile.open(tar_path, mode="r:") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        if len(names) != len(set(names)):
            raise EvidenceError("archive contains duplicate member names")
        if not members or members[0].name != "manifest.json":
            raise EvidenceError("archive manifest is missing or not first")
        for member in members:
            safe_relative_path(member.name, label="archive member")
            if not member.isfile():
                raise EvidenceError(f"archive contains a non-regular member: {member.name}")

        manifest_member = archive.extractfile(members[0])
        if manifest_member is None:
            raise EvidenceError("archive manifest cannot be read")
        if members[0].size > MAX_MANIFEST_BYTES:
            raise EvidenceError("archive manifest exceeds the size limit")
        manifest_bytes = manifest_member.read()
        try:
            manifest = json.loads(manifest_bytes)
        except json.JSONDecodeError as exc:
            raise EvidenceError("archive manifest is invalid JSON") from exc
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema_version") != 1
            or manifest.get("format") != "codexhome-incident-evidence"
        ):
            raise EvidenceError("unsupported archive manifest")

        records = manifest.get("records")
        if not isinstance(records, list):
            raise EvidenceError("archive manifest records must be a list")
        expected_objects: dict[str, int] = {}
        for record in records:
            if not isinstance(record, dict):
                raise EvidenceError("archive manifest contains an invalid record")
            source_id = str(record.get("source_id", ""))
            if not SOURCE_ID_RE.fullmatch(source_id):
                raise EvidenceError("archive manifest contains an invalid source_id")
            safe_relative_path(str(record.get("relative_path", "")), label="record path")
            sha256 = validate_sha256(record.get("sha256"), label="record sha256")
            try:
                size = int(record["bytes"])
            except (KeyError, TypeError, ValueError) as exc:
                raise EvidenceError("archive manifest contains an invalid byte count") from exc
            if size < 0:
                raise EvidenceError("archive manifest contains an unsupported record")
            safe_symlink_target(
                record.get("symlink_target"),
                label="archive record symlink target",
            )
            previous_size = expected_objects.setdefault(sha256, size)
            if previous_size != size:
                raise EvidenceError(f"object size conflict: {sha256}")

        archive_objects = {
            member.name.removeprefix("objects/"): member
            for member in members[1:]
            if member.name.startswith("objects/")
        }
        if len(archive_objects) != len(members) - 1:
            raise EvidenceError("archive contains an unexpected member")
        expected_names = {f"{sha256[:2]}/{sha256}" for sha256 in expected_objects}
        if set(archive_objects) != expected_names:
            raise EvidenceError("archive object set does not match the manifest")

        for object_name, member in sorted(archive_objects.items()):
            sha256 = object_name.split("/")[-1]
            if member.size != expected_objects[sha256]:
                raise EvidenceError(f"archive object size mismatch: {sha256}")
            source = archive.extractfile(member)
            if source is None:
                raise EvidenceError(f"archive object cannot be read: {sha256}")
            object_path = object_root / sha256
            digest = hashlib.sha256()
            with object_path.open("wb") as output:
                while chunk := source.read(CHUNK_BYTES):
                    digest.update(chunk)
                    output.write(chunk)
            if digest.hexdigest() != sha256:
                raise EvidenceError(f"archive object hash mismatch: {sha256}")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        source_id = str(record["source_id"])
        relative = safe_relative_path(str(record["relative_path"]), label="record path")
        target = restored_root / source_id / Path(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        source = object_root / str(record["sha256"])
        shutil.copyfile(source, target)
        grouped[source_id].append(record)

    variants = [
        {
            "source_id": source_id,
            "tree_sha256": digest_records(source_records),
            "files": len(source_records),
            "bytes": sum(int(item["bytes"]) for item in source_records),
        }
        for source_id, source_records in sorted(grouped.items())
    ]
    root_sha256 = aggregate_root(variants)
    if root_sha256 != manifest.get("created_from_root_sha256"):
        raise EvidenceError("restored evidence root does not match the archive manifest")
    if len(records) != manifest.get("files"):
        raise EvidenceError("restored file count does not match the archive manifest")
    if sum(int(item["bytes"]) for item in records) != manifest.get("bytes"):
        raise EvidenceError("restored byte count does not match the archive manifest")
    return {
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "root_sha256": root_sha256,
        "files": len(records),
        "bytes": sum(int(item["bytes"]) for item in records),
        "restored_root": str(restored_root),
    }


def run_rclone(*args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["rclone", *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise EvidenceError(f"rclone failed: {detail}")
    return result


def download_remote(remote_path: str, destination: Path) -> None:
    run_rclone("copyto", "--", remote_path, str(destination))


def remote_objects(parent: str, name: str) -> list[dict[str, Any]]:
    result: subprocess.CompletedProcess[str] | None = None
    for delay in (0, 1, 2, 4, 8):
        if delay:
            time.sleep(delay)
        try:
            result = run_rclone("lsjson", "--files-only", "--", parent)
            break
        except EvidenceError as exc:
            if "directory not found" not in str(exc).lower() or delay == 8:
                raise
    assert result is not None
    try:
        listing = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise EvidenceError("rclone returned invalid JSON while listing objects") from exc
    if not isinstance(listing, list) or not all(
        isinstance(item, dict) for item in listing
    ):
        raise EvidenceError("rclone returned an invalid object listing")
    return [item for item in listing if item.get("Name") == name]


def unique_remote_object(parent: str, name: str) -> dict[str, Any]:
    matches = remote_objects(parent, name)
    if len(matches) != 1:
        raise EvidenceError(
            f"expected one remote object named {name}, found {len(matches)}"
        )
    object_id = matches[0].get("ID")
    if not isinstance(object_id, str) or not object_id:
        raise EvidenceError("remote object has no stable provider ID")
    return matches[0]


def upload_bundle(case_dir: Path, destination: str) -> dict[str, Any]:
    if not RCLONE_DESTINATION_RE.fullmatch(destination):
        raise EvidenceError("destination must be an rclone remote path")
    case = load_yaml(case_dir / "case.yaml")
    case_uuid = str(case["uuid"])
    state = load_state(case_uuid)
    bundle_path = Path(str(state["bundle_path"]))
    expected_ciphertext = str(state["ciphertext_sha256"])
    if not bundle_path.is_file() or sha256_file(bundle_path) != expected_ciphertext:
        raise EvidenceError("local encrypted bundle is missing or corrupt")

    parent = f"{destination.rstrip('/')}/{case_uuid}"
    remote_path = f"{parent}/{state['bundle_name']}"
    run_rclone("mkdir", "--", parent)
    matches = remote_objects(parent, str(state["bundle_name"]))
    if len(matches) > 1:
        raise EvidenceError("remote contains duplicate objects with the bundle name")
    if matches:
        with tempfile.TemporaryDirectory(prefix="codexhome-roundtrip-") as temporary:
            downloaded = Path(temporary) / "bundle.age"
            download_remote(remote_path, downloaded)
            if sha256_file(downloaded) != expected_ciphertext:
                raise EvidenceError("remote object collision with different ciphertext")
    else:
        run_rclone("copyto", "--immutable", "--", str(bundle_path), remote_path)

    with tempfile.TemporaryDirectory(prefix="codexhome-roundtrip-") as temporary:
        downloaded = Path(temporary) / "bundle.age"
        download_remote(remote_path, downloaded)
        if sha256_file(downloaded) != expected_ciphertext:
            raise EvidenceError("uploaded ciphertext failed round-trip verification")

    object_id = str(
        unique_remote_object(parent, str(state["bundle_name"]))["ID"]
    )
    state["remote"] = {
        "provider": "rclone",
        "object_id": object_id,
        "parent": parent,
        "remote_path": remote_path,
        "uploaded_at": utc_now(),
        "roundtrip_ciphertext_verified": True,
    }
    state["drills"] = []
    state["offloaded"] = False
    write_json(state_path(case_uuid), state)
    return state


def verify_remote_object(state: dict[str, Any]) -> None:
    remote = state.get("remote")
    if not isinstance(remote, dict):
        raise EvidenceError("no uploaded remote object is recorded")
    parent = str(remote.get("parent", ""))
    remote_path = str(remote.get("remote_path", ""))
    object_id = str(remote.get("object_id", ""))
    bundle_name = str(state.get("bundle_name", ""))
    if not parent or not remote_path or not object_id or not bundle_name:
        raise EvidenceError("remote object state is incomplete")
    current = unique_remote_object(parent, bundle_name)
    if current["ID"] != object_id:
        raise EvidenceError("remote object ID changed after upload")
    with tempfile.TemporaryDirectory(prefix="codexhome-finalize-") as temporary:
        downloaded = Path(temporary) / "bundle.age"
        download_remote(remote_path, downloaded)
        if sha256_file(downloaded) != state.get("ciphertext_sha256"):
            raise EvidenceError("remote ciphertext changed after the restore drills")


def select_bundle(
    state: dict[str, Any],
    *,
    from_remote: bool,
    temporary: Path,
) -> Path:
    if not from_remote:
        return Path(str(state["bundle_path"]))
    remote = state.get("remote")
    if not isinstance(remote, dict) or not remote.get("remote_path"):
        raise EvidenceError("no uploaded remote object is recorded")
    bundle_path = temporary / "remote-bundle.age"
    download_remote(str(remote["remote_path"]), bundle_path)
    return bundle_path


def drill(
    case_dir: Path,
    *,
    custody: str,
    keyring_label: str | None,
    identity_file: Path | None,
    from_remote: bool,
) -> dict[str, Any]:
    if custody not in {"primary", "escrow", "pilot-primary", "pilot-escrow"}:
        raise EvidenceError("unsupported custody role")
    case = load_yaml(case_dir / "case.yaml")
    case_uuid = str(case["uuid"])
    state = load_state(case_uuid)
    identity = load_identity(keyring_label=keyring_label, identity_file=identity_file)
    recipient = str(identity.to_public())
    if recipient not in state.get("recipients", []):
        raise EvidenceError("selected identity is not an encrypted bundle recipient")
    with tempfile.TemporaryDirectory(prefix="codexhome-restore-") as temporary_name:
        temporary = Path(temporary_name)
        bundle_path = select_bundle(state, from_remote=from_remote, temporary=temporary)
        if sha256_file(bundle_path) != state["ciphertext_sha256"]:
            raise EvidenceError("ciphertext hash mismatch")
        restore = decrypt_bundle(bundle_path, identity, temporary / "restore")
        if sha256_file(temporary / "restore" / "bundle.tar.zst") != state["archive_sha256"]:
            raise EvidenceError("decrypted archive hash mismatch")
        if restore["manifest_sha256"] != state["manifest_sha256"]:
            raise EvidenceError("restored manifest hash mismatch")
        if restore["root_sha256"] != state["case_root_sha256"]:
            raise EvidenceError("restored case root mismatch")

    receipt = {
        "custody": custody,
        "source": "remote" if from_remote else "local",
        "recipient": recipient,
        "verified_at": utc_now(),
        "root_sha256": restore["root_sha256"],
        "files": restore["files"],
        "bytes": restore["bytes"],
    }
    recipient_ids = state.get("recipient_ids", {})
    if isinstance(recipient_ids, dict):
        matching_ids = [
            recipient_id
            for recipient_id, public_value in recipient_ids.items()
            if public_value == recipient
        ]
        if len(matching_ids) == 1:
            receipt["recipient_id"] = matching_ids[0]
    with locked_state(case_uuid):
        current_state = load_state(case_uuid)
        if current_state.get("ciphertext_sha256") != state.get("ciphertext_sha256"):
            raise EvidenceError("offload state changed during the restore drill")
        drills = [
            item
            for item in current_state.get("drills", [])
            if not (
                isinstance(item, dict)
                and item.get("custody") == custody
                and item.get("source") == receipt["source"]
            )
        ]
        drills.append(receipt)
        current_state["drills"] = drills
        write_json(state_path(case_uuid), current_state)
    return receipt


def finalization_drills(
    case: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    remote = state.get("remote")
    if not isinstance(remote, dict) or not remote.get("roundtrip_ciphertext_verified"):
        raise EvidenceError("remote ciphertext round trip has not passed")
    remote_drills = {
        str(item.get("custody")): item
        for item in state.get("drills", [])
        if isinstance(item, dict) and item.get("source") == "remote"
    }
    if not {"primary", "escrow"}.issubset(remote_drills):
        raise EvidenceError(
            "remote restore drills must pass independently for primary and escrow custody"
        )
    evidence = case.get("evidence")
    if not isinstance(evidence, dict) or evidence.get("state") != "local-only":
        raise EvidenceError("only local-only evidence can be finalized as offloaded")
    if state.get("case_root_sha256") != evidence.get("root_sha256"):
        raise EvidenceError("local offload state no longer matches case.yaml")
    if int(state.get("files", 0)) <= 0:
        raise EvidenceError("empty evidence cannot be finalized")
    recipients = [
        str(remote_drills[role].get("recipient", ""))
        for role in ("primary", "escrow")
    ]
    if len(set(recipients)) != 2:
        raise EvidenceError("primary and escrow drills must use distinct recipients")
    if any(recipient not in state.get("recipients", []) for recipient in recipients):
        raise EvidenceError("restore drill recipient is not part of the encrypted bundle")
    for role in ("primary", "escrow"):
        receipt = remote_drills[role]
        if receipt.get("root_sha256") != state.get("case_root_sha256"):
            raise EvidenceError(f"{role} restore drill has the wrong case root")
        if receipt.get("files") != state.get("files"):
            raise EvidenceError(f"{role} restore drill has the wrong file count")
        if receipt.get("bytes") != state.get("bytes"):
            raise EvidenceError(f"{role} restore drill has the wrong byte count")
    return remote_drills


def finalize(case_dir: Path) -> dict[str, Any]:
    case_path = case_dir / "case.yaml"
    original_text = case_path.read_text(encoding="utf-8")
    case = load_yaml(case_path)
    case_uuid = str(case["uuid"])
    state = load_state(case_uuid)
    remote_drills = finalization_drills(case, state)
    registry = load_public_recipient_registry()
    for role in ("primary", "escrow"):
        recipient_id = remote_drills[role].get("recipient_id")
        entry = registry.get(str(recipient_id))
        if (
            entry is None
            or entry.get("status") != "active"
            or entry.get("role") != role
            or entry.get("public_age_recipient")
            != remote_drills[role].get("recipient")
        ):
            raise EvidenceError(
                f"{role} restore drill does not match an active public recipient ID"
            )
    verify_remote_object(state)
    remote = state["remote"]

    evidence = case["evidence"]
    evidence["state"] = "offloaded"
    evidence["offload"] = {
        "schema_version": 1,
        "provider": "encrypted-object-store",
        "object_id": remote["object_id"],
        "archive_sha256": state["archive_sha256"],
        "ciphertext_sha256": state["ciphertext_sha256"],
        "manifest_sha256": state["manifest_sha256"],
        "files": state["files"],
        "bytes": state["bytes"],
        "uploaded_at": remote["uploaded_at"],
        "restore_drills": {
            role: {
                "verified_at": remote_drills[role]["verified_at"],
                "root_sha256": remote_drills[role]["root_sha256"],
                "recipient_id": remote_drills[role].get("recipient_id"),
                "recipient": remote_drills[role]["recipient"],
            }
            for role in ("primary", "escrow")
        },
        "source_deletion_authorized": False,
    }
    case_path.write_text(
        yaml.safe_dump(case, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    from incident_case import validate_case

    errors = validate_case(case_dir)
    if errors:
        case_path.write_text(original_text, encoding="utf-8")
        raise EvidenceError(
            "finalized case failed validation: " + "; ".join(errors)
        )
    state["offloaded"] = True
    write_json(state_path(case_uuid), state)
    return evidence["offload"]


def keygen(label: str) -> str:
    if keyring.get_password(KEYRING_SERVICE, label):
        raise EvidenceError(f"keyring identity already exists: {label}")
    identity = Identity.generate()
    keyring.set_password(KEYRING_SERVICE, label, str(identity))
    return str(identity.to_public())


def key_import(label: str, identity_file: Path) -> str:
    if keyring.get_password(KEYRING_SERVICE, label):
        raise EvidenceError(f"keyring identity already exists: {label}")
    identity = load_identity(keyring_label=None, identity_file=identity_file)
    keyring.set_password(KEYRING_SERVICE, label, str(identity))
    return str(identity.to_public())


def active_public_recipient_ids() -> dict[str, str]:
    registry = load_public_recipient_registry()
    active_by_role: dict[str, list[str]] = defaultdict(list)
    for recipient_id, entry in registry.items():
        if entry["status"] == "active":
            active_by_role[str(entry["role"])].append(recipient_id)
    selected: dict[str, str] = {}
    for role in sorted(PUBLIC_RECIPIENT_ROLES):
        ids = active_by_role.get(role, [])
        if len(ids) != 1:
            raise EvidenceError(
                f"expected exactly one active public recipient ID for {role}, "
                f"found {len(ids)}"
            )
        selected[role] = ids[0]
    return selected


def batch_case_directories(case_values: list[str] | None) -> list[Path]:
    if case_values:
        return [resolve_case(value) for value in case_values]
    return sorted(
        path
        for path in INCIDENTS.iterdir()
        if path.is_dir() and (path / "case.yaml").is_file()
    )


def append_batch_event(run_id: str, value: dict[str, Any]) -> None:
    journal = OFFLOAD_ROOT / "batch-runs" / f"{run_id}.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with journal.open("a", encoding="utf-8") as handle:
        os.chmod(journal, 0o600)
        handle.write(
            json.dumps(
                {"recorded_at": utc_now(), **value},
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        )


def reusable_batch_state(
    case_dir: Path,
    *,
    recipient_ids: dict[str, str],
) -> dict[str, Any] | None:
    case = load_yaml(case_dir / "case.yaml")
    case_uuid = str(case["uuid"])
    path = state_path(case_uuid)
    if not path.is_file():
        return None
    state = load_state(case_uuid)
    expected_ids = {
        recipient_id: public_value
        for recipient_id, public_value in recipient_ids.items()
    }
    compatible = (
        state.get("case_root_sha256") == case.get("evidence", {}).get("root_sha256")
        and state.get("recipient_ids") == expected_ids
    )
    if compatible:
        return state
    if state.get("remote"):
        raise EvidenceError(
            "partial remote offload uses different evidence or public recipient IDs"
        )
    return None


def batch_remote_drill_exists(
    state: dict[str, Any],
    *,
    custody: str,
    recipient_id: str,
) -> bool:
    return any(
        isinstance(item, dict)
        and item.get("custody") == custody
        and item.get("source") == "remote"
        and item.get("recipient_id") == recipient_id
        and item.get("root_sha256") == state.get("case_root_sha256")
        for item in state.get("drills", [])
    )


def offload_batch_case(
    case_dir: Path,
    *,
    destination: str,
    primary_keyring: str,
    escrow_keyring: str,
    role_ids: dict[str, str],
    recipient_values: list[str],
    recipient_ids: dict[str, str],
    run_id: str,
) -> list[str]:
    stages: list[str] = []
    state = reusable_batch_state(case_dir, recipient_ids=recipient_ids)
    if state is None:
        state = build_bundle(
            case_dir,
            recipient_values,
            recipient_ids=recipient_ids,
        )
        stages.append("bundled")
        append_batch_event(
            run_id,
            {"case_id": case_dir.name, "stage": "bundled", "status": "passed"},
        )

    remote = state.get("remote")
    if not isinstance(remote, dict):
        state = upload_bundle(case_dir, destination)
        stages.append("uploaded")
        append_batch_event(
            run_id,
            {"case_id": case_dir.name, "stage": "uploaded", "status": "passed"},
        )

    keyrings = {"primary": primary_keyring, "escrow": escrow_keyring}
    for role in ("primary", "escrow"):
        state = load_state(str(load_yaml(case_dir / "case.yaml")["uuid"]))
        if batch_remote_drill_exists(
            state,
            custody=role,
            recipient_id=role_ids[role],
        ):
            continue
        drill(
            case_dir,
            custody=role,
            keyring_label=keyrings[role],
            identity_file=None,
            from_remote=True,
        )
        stages.append(f"{role}-restored")
        append_batch_event(
            run_id,
            {
                "case_id": case_dir.name,
                "stage": f"{role}-restored",
                "status": "passed",
            },
        )

    finalize(case_dir)
    stages.append("finalized")
    append_batch_event(
        run_id,
        {"case_id": case_dir.name, "stage": "finalized", "status": "passed"},
    )
    return stages


def run_batch(
    *,
    case_values: list[str] | None,
    destination: str | None,
    primary_keyring: str | None,
    escrow_keyring: str | None,
    limit: int | None,
    dry_run: bool,
    continue_on_error: bool,
) -> dict[str, Any]:
    if limit is not None and limit <= 0:
        raise EvidenceError("batch limit must be positive")

    candidates: list[Path] = []
    skipped: list[dict[str, str]] = []
    for case_dir in batch_case_directories(case_values):
        case = load_yaml(case_dir / "case.yaml")
        state = case.get("evidence", {}).get("state")
        if state == "offloaded":
            skipped.append({"case_id": case_dir.name, "reason": "already-offloaded"})
            continue
        if state != "local-only":
            skipped.append({"case_id": case_dir.name, "reason": f"state-{state}"})
            continue
        if not (case_dir / "local" / "import-manifest.jsonl").is_file():
            skipped.append({"case_id": case_dir.name, "reason": "no-import-manifest"})
            continue
        candidates.append(case_dir)
    if limit is not None:
        candidates = candidates[:limit]

    result: dict[str, Any] = {
        "schema_version": 1,
        "dry_run": dry_run,
        "selected": len(candidates),
        "skipped": skipped,
        "completed": [],
        "failed": [],
    }
    if dry_run:
        result["cases"] = [case_dir.name for case_dir in candidates]
        return result
    role_ids = active_public_recipient_ids()
    recipient_values, recipient_ids = resolve_public_recipient_ids(
        [role_ids["primary"], role_ids["escrow"]]
    )
    if not destination:
        raise EvidenceError(
            "batch destination is required through --destination or "
            "INCIDENT_EVIDENCE_RCLONE_DESTINATION"
        )
    if not primary_keyring or not escrow_keyring:
        raise EvidenceError(
            "batch primary and escrow keyring labels are required"
        )

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    result["run_id"] = run_id
    for index, case_dir in enumerate(candidates, start=1):
        print(f"[{index}/{len(candidates)}] {case_dir.name}: starting", flush=True)
        try:
            stages = offload_batch_case(
                case_dir,
                destination=destination,
                primary_keyring=primary_keyring,
                escrow_keyring=escrow_keyring,
                role_ids=role_ids,
                recipient_values=recipient_values,
                recipient_ids=recipient_ids,
                run_id=run_id,
            )
        except (EvidenceError, OSError, KeyError, json.JSONDecodeError) as exc:
            failure = {"case_id": case_dir.name, "error": str(exc)}
            result["failed"].append(failure)
            append_batch_event(
                run_id,
                {
                    "case_id": case_dir.name,
                    "stage": "batch",
                    "status": "failed",
                    "error": str(exc),
                },
            )
            print(f"[{index}/{len(candidates)}] {case_dir.name}: failed", flush=True)
            if not continue_on_error:
                break
            continue
        result["completed"].append({"case_id": case_dir.name, "stages": stages})
        print(f"[{index}/{len(candidates)}] {case_dir.name}: finalized", flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Encrypt, offload, and restore hash-first incident evidence."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    keygen_parser = subparsers.add_parser("keygen")
    keygen_parser.add_argument("--label", required=True)

    import_parser = subparsers.add_parser("key-import")
    import_parser.add_argument("--label", required=True)
    import_parser.add_argument("--identity-file", required=True, type=Path)

    subparsers.add_parser("recipients")
    subparsers.add_parser("recipient-usage")

    bundle_parser = subparsers.add_parser("bundle")
    bundle_parser.add_argument("--case", required=True)
    bundle_parser.add_argument("--recipient-id", action="append", required=True)

    upload_parser = subparsers.add_parser("upload")
    upload_parser.add_argument("--case", required=True)
    upload_parser.add_argument("--destination", required=True)

    drill_parser = subparsers.add_parser("drill")
    drill_parser.add_argument("--case", required=True)
    drill_parser.add_argument("--custody", required=True)
    identity_group = drill_parser.add_mutually_exclusive_group(required=True)
    identity_group.add_argument("--identity-keyring")
    identity_group.add_argument("--identity-file", type=Path)
    drill_parser.add_argument("--from-remote", action="store_true")

    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--case", required=True)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--case", required=True)

    batch_parser = subparsers.add_parser("batch")
    batch_parser.add_argument("--case", action="append")
    batch_parser.add_argument(
        "--destination",
        default=os.environ.get("INCIDENT_EVIDENCE_RCLONE_DESTINATION"),
    )
    batch_parser.add_argument(
        "--primary-keyring",
        default=os.environ.get("INCIDENT_EVIDENCE_PRIMARY_KEY_LABEL"),
    )
    batch_parser.add_argument(
        "--escrow-keyring",
        default=os.environ.get("INCIDENT_EVIDENCE_ESCROW_KEY_LABEL"),
    )
    batch_parser.add_argument("--limit", type=int)
    batch_parser.add_argument("--dry-run", action="store_true")
    batch_parser.add_argument("--continue-on-error", action="store_true")

    args = parser.parse_args()
    try:
        if args.command == "keygen":
            print(keygen(args.label))
            return 0
        if args.command == "key-import":
            print(key_import(args.label, args.identity_file))
            return 0
        if args.command == "recipients":
            registry = load_public_recipient_registry()
            print(
                yaml.safe_dump(
                    {"public_age_recipients": list(registry.values())},
                    sort_keys=False,
                ),
                end="",
            )
            return 0
        if args.command == "recipient-usage":
            print(
                yaml.safe_dump(
                    recipient_usage_report(),
                    sort_keys=False,
                ),
                end="",
            )
            return 0
        if args.command == "batch":
            value = run_batch(
                case_values=args.case,
                destination=args.destination,
                primary_keyring=args.primary_keyring,
                escrow_keyring=args.escrow_keyring,
                limit=args.limit,
                dry_run=args.dry_run,
                continue_on_error=args.continue_on_error,
            )
            print(yaml.safe_dump(value, sort_keys=False), end="")
            return 1 if value["failed"] else 0

        case_dir = resolve_case(args.case)
        case_uuid = str(load_yaml(case_dir / "case.yaml")["uuid"])
        if args.command == "bundle":
            recipients, recipient_ids = resolve_public_recipient_ids(
                args.recipient_id
            )
            value = build_bundle(
                case_dir,
                recipients,
                recipient_ids=recipient_ids,
            )
        elif args.command == "upload":
            value = upload_bundle(case_dir, args.destination)
        elif args.command == "drill":
            value = drill(
                case_dir,
                custody=args.custody,
                keyring_label=args.identity_keyring,
                identity_file=args.identity_file,
                from_remote=args.from_remote,
            )
        elif args.command == "finalize":
            value = finalize(case_dir)
        else:
            value = load_state(case_uuid)
        print(yaml.safe_dump(value, sort_keys=False), end="")
        return 0
    except (EvidenceError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"evidence offload failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
