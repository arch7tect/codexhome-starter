from __future__ import annotations

import json
import io
import shutil
import sys
import tarfile
import uuid
from copy import deepcopy
from pathlib import Path

import yaml
import pyrage
import zstandard
from pyrage.x25519 import Identity


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import evidence_offload  # noqa: E402


BASE = ROOT / "scripts" / "tests" / ".generated" / "evidence_offload"


def create_case() -> Path:
    case_dir = BASE / "incidents" / "2026-07-28-example-offload"
    local = case_dir / "local" / "legacy" / "example-active"
    local.mkdir(parents=True)
    files = {
        "nested/events.log": b"one\ntwo\n",
        "recording.wav": b"RIFF-test-evidence",
    }
    records = []
    for relative, content in files.items():
        path = local / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        records.append(
            {
                "source_id": "example-active",
                "family": "example",
                "legacy_name": "offload",
                "relative_path": relative,
                "sha256": evidence_offload.sha256_file(path),
                "bytes": len(content),
                "tracked": False,
                "lfs_pointer": False,
                "lfs_oid": None,
                "symlink_target": (
                    "../events.log" if relative == "nested/events.log" else None
                ),
            }
        )
    with (case_dir / "local" / "import-manifest.jsonl").open(
        "w", encoding="utf-8"
    ) as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    variants = [
        {
            "source_id": "example-active",
            "tree_sha256": evidence_offload.digest_records(records),
        }
    ]
    manifest = {
        "schema_version": 1,
        "case_id": case_dir.name,
        "uuid": str(uuid.uuid4()),
        "evidence": {
            "state": "local-only",
            "root_sha256": evidence_offload.aggregate_root(variants),
        },
    }
    (case_dir / "case.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    return case_dir


def create_unsafe_bundle(path: Path, identity: Identity) -> None:
    tar_path = path.with_suffix(".tar")
    compressed_path = path.with_suffix(".tar.zst")
    with tarfile.open(tar_path, mode="w") as archive:
        manifest = b"{}\n"
        manifest_info = tarfile.TarInfo("manifest.json")
        manifest_info.size = len(manifest)
        archive.addfile(manifest_info, io.BytesIO(manifest))
        unsafe = b"escape"
        unsafe_info = tarfile.TarInfo("../escape")
        unsafe_info.size = len(unsafe)
        archive.addfile(unsafe_info, io.BytesIO(unsafe))
    compressor = zstandard.ZstdCompressor()
    with tar_path.open("rb") as source, compressed_path.open("wb") as destination:
        compressor.copy_stream(source, destination)
    with compressed_path.open("rb") as source, path.open("wb") as destination:
        pyrage.encrypt_io(source, destination, [identity.to_public()])


def main() -> int:
    if BASE.exists():
        shutil.rmtree(BASE)
    BASE.mkdir(parents=True)
    evidence_offload.INCIDENTS = BASE / "incidents"
    evidence_offload.OFFLOAD_ROOT = BASE / "offload"
    evidence_offload.PUBLIC_RECIPIENTS_PATH = BASE / "missing-registry.yaml"

    case_dir = create_case()
    primary = Identity.generate()
    escrow = Identity.generate()
    registry_path = BASE / "PUBLIC-AGE-RECIPIENTS.yaml"
    registry_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "kind": "public-age-recipient-registry",
                "recipients": [
                    {
                        "id": "test-primary-v1",
                        "role": "primary",
                        "public_age_recipient": str(primary.to_public()),
                        "status": "active",
                        "owner": "test-owner",
                        "custody": "test-keychain",
                        "introduced_at": "2026-07-28",
                        "review_due": "2027-01-28",
                    },
                    {
                        "id": "test-escrow-v1",
                        "role": "escrow",
                        "public_age_recipient": str(escrow.to_public()),
                        "status": "active",
                        "owner": "test-owner",
                        "custody": "test-vault",
                        "introduced_at": "2026-07-28",
                        "review_due": "2027-01-28",
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    resolved, recipient_ids = evidence_offload.resolve_public_recipient_ids(
        ["test-primary-v1", "test-escrow-v1"],
        path=registry_path,
    )
    if set(resolved) != {str(primary.to_public()), str(escrow.to_public())}:
        raise AssertionError("public recipient IDs resolved incorrectly")
    if evidence_offload.load_public_recipient_registry() != {}:
        raise AssertionError("a missing public recipient registry should be unconfigured")
    empty_registry = BASE / "EMPTY.yaml"
    empty_registry.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "kind": "public-age-recipient-registry",
                "recipients": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    if evidence_offload.load_public_recipient_registry(empty_registry) != {}:
        raise AssertionError("an empty public recipient registry should be unconfigured")
    empty_usage = evidence_offload.recipient_usage_report(
        incidents_path=BASE / "incidents",
        registry_path=empty_registry,
    )
    if empty_usage["recipients"]:
        raise AssertionError(f"unconfigured recipient usage should be empty: {empty_usage}")
    try:
        evidence_offload.active_public_recipient_ids()
    except evidence_offload.EvidenceError as exc:
        if "expected exactly one active public recipient ID" not in str(exc):
            raise AssertionError(f"unexpected unconfigured registry error: {exc}") from exc
    else:
        raise AssertionError("an unconfigured registry was accepted for offload")
    state = evidence_offload.build_bundle(
        case_dir,
        resolved,
        recipient_ids=recipient_ids,
    )
    if state["recipient_ids"] != recipient_ids:
        raise AssertionError("public recipient IDs were not recorded in local state")
    plan = evidence_offload.run_batch(
        case_values=[str(case_dir)],
        destination=None,
        primary_keyring=None,
        escrow_keyring=None,
        limit=None,
        dry_run=True,
        continue_on_error=False,
    )
    if plan["selected"] != 1 or plan["cases"] != [case_dir.name]:
        raise AssertionError(f"batch dry run selected the wrong cases: {plan}")
    bundle = Path(state["bundle_path"])
    if not bundle.is_file():
        raise AssertionError("encrypted bundle was not created")
    if state["archive_sha256"] in bundle.name:
        raise AssertionError("bundle name leaks the plaintext archive hash")
    try:
        evidence_offload.build_bundle(
            case_dir,
            [str(primary.to_public()), str(primary.to_public())],
        )
    except evidence_offload.EvidenceError as exc:
        if "distinct age recipients" not in str(exc):
            raise AssertionError(f"unexpected recipient error: {exc}") from exc
    else:
        raise AssertionError("duplicate recipients were accepted")

    private_registry = registry_path.with_name("PRIVATE.yaml")
    private_registry.write_text(
        registry_path.read_text(encoding="utf-8")
        + f"\nprivate_identity: {primary}\n",
        encoding="utf-8",
    )
    try:
        evidence_offload.load_public_recipient_registry(private_registry)
    except evidence_offload.EvidenceError as exc:
        if "private age identity" not in str(exc):
            raise AssertionError(f"unexpected private identity error: {exc}") from exc
    else:
        raise AssertionError("private age identity was accepted in the public registry")
    empty_private_registry = empty_registry.with_name("EMPTY-PRIVATE.yaml")
    empty_private_registry.write_text(
        empty_registry.read_text(encoding="utf-8")
        + "\n# AGE-SECRET-KEY-1EXAMPLE\n",
        encoding="utf-8",
    )
    try:
        evidence_offload.load_public_recipient_registry(empty_private_registry)
    except evidence_offload.EvidenceError as exc:
        if "private age identity" not in str(exc):
            raise AssertionError(f"unexpected empty private registry error: {exc}") from exc
    else:
        raise AssertionError("private identity marker was accepted in an empty registry")

    legacy_registry = registry_path.with_name("LEGACY.yaml")
    legacy_value = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    legacy_value["recipients"][0]["verified_case_uuids"] = []
    legacy_registry.write_text(
        yaml.safe_dump(legacy_value, sort_keys=False),
        encoding="utf-8",
    )
    try:
        evidence_offload.load_public_recipient_registry(legacy_registry)
    except evidence_offload.EvidenceError as exc:
        if "unsupported fields" not in str(exc):
            raise AssertionError(f"unexpected legacy registry error: {exc}") from exc
    else:
        raise AssertionError("legacy recipient usage list was accepted")

    retired_registry = registry_path.with_name("RETIRED.yaml")
    retired_value = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    retired_value["recipients"][0]["status"] = "retired"
    retired_registry.write_text(
        yaml.safe_dump(retired_value, sort_keys=False),
        encoding="utf-8",
    )
    try:
        evidence_offload.resolve_public_recipient_ids(
            ["test-primary-v1", "test-escrow-v1"],
            path=retired_registry,
        )
    except evidence_offload.EvidenceError as exc:
        if "not active" not in str(exc):
            raise AssertionError(f"unexpected retired recipient error: {exc}") from exc
    else:
        raise AssertionError("retired recipient was accepted for a new bundle")

    restore_dir = BASE / "restore-primary"
    restored = evidence_offload.decrypt_bundle(bundle, primary, restore_dir)
    if restored["root_sha256"] != state["case_root_sha256"]:
        raise AssertionError("restored root does not match source root")
    restored_file = (
        Path(restored["restored_root"])
        / "example-active"
        / "nested"
        / "events.log"
    )
    if restored_file.read_bytes() != b"one\ntwo\n":
        raise AssertionError("restored evidence content differs")

    escrow_restore = evidence_offload.decrypt_bundle(
        bundle,
        escrow,
        BASE / "restore-escrow",
    )
    if escrow_restore["manifest_sha256"] != state["manifest_sha256"]:
        raise AssertionError("escrow restore has the wrong manifest")

    case = evidence_offload.load_yaml(case_dir / "case.yaml")
    same_key_state = deepcopy(state)
    same_key_state["remote"] = {"roundtrip_ciphertext_verified": True}
    common_receipt = {
        "source": "remote",
        "recipient": str(primary.to_public()),
        "root_sha256": state["case_root_sha256"],
        "files": state["files"],
        "bytes": state["bytes"],
        "verified_at": "2026-07-28T12:00:00+00:00",
    }
    same_key_state["drills"] = [
        {**common_receipt, "custody": "primary"},
        {**common_receipt, "custody": "escrow"},
    ]
    try:
        evidence_offload.finalization_drills(case, same_key_state)
    except evidence_offload.EvidenceError as exc:
        if "distinct recipients" not in str(exc):
            raise AssertionError(f"unexpected custody error: {exc}") from exc
    else:
        raise AssertionError("one key was accepted for primary and escrow custody")

    distinct_state = deepcopy(same_key_state)
    distinct_state["drills"][1]["recipient"] = str(escrow.to_public())
    evidence_offload.finalization_drills(case, distinct_state)

    identity_file = BASE / "escrow-identity.txt"
    identity_file.write_text(
        "# created: 2026-07-28T12:00:00Z\n"
        f"# public key: {escrow.to_public()}\n"
        f"{escrow}\n",
        encoding="utf-8",
    )
    loaded_identity = evidence_offload.load_identity(
        keyring_label=None,
        identity_file=identity_file,
    )
    if str(loaded_identity.to_public()) != str(escrow.to_public()):
        raise AssertionError("standard age identity file did not load")

    corrupt = BASE / "corrupt.age"
    content = bytearray(bundle.read_bytes())
    content[-1] ^= 1
    corrupt.write_bytes(content)
    try:
        evidence_offload.decrypt_bundle(corrupt, primary, BASE / "restore-corrupt")
    except evidence_offload.EvidenceError as exc:
        if "decryption failed" not in str(exc):
            raise AssertionError(f"unexpected corruption error: {exc}") from exc
    else:
        raise AssertionError("corrupt ciphertext was accepted")

    try:
        evidence_offload.safe_relative_path("../escape", label="test path")
    except evidence_offload.EvidenceError:
        pass
    else:
        raise AssertionError("unsafe restore path was accepted")

    try:
        evidence_offload.safe_symlink_target("/absolute", label="test target")
    except evidence_offload.EvidenceError:
        pass
    else:
        raise AssertionError("absolute symlink metadata was accepted")

    unsafe_bundle = BASE / "unsafe.age"
    create_unsafe_bundle(unsafe_bundle, primary)
    try:
        evidence_offload.decrypt_bundle(
            unsafe_bundle,
            primary,
            BASE / "restore-unsafe",
        )
    except evidence_offload.EvidenceError as exc:
        if "unsafe archive member" not in str(exc):
            raise AssertionError(f"unexpected unsafe archive error: {exc}") from exc
    else:
        raise AssertionError("archive traversal member was accepted")

    receipt_case = BASE / "incidents" / "2026-07-28-example-receipt"
    receipt_case.mkdir()
    receipt_uuid = str(uuid.uuid4())
    (receipt_case / "case.yaml").write_text(
        yaml.safe_dump(
            {
                "uuid": receipt_uuid,
                "case_id": receipt_case.name,
                "evidence": {
                    "offload": {
                        "restore_drills": {
                            "primary": {
                                "recipient_id": "test-primary-v1",
                                "recipient": str(primary.to_public()),
                                "verified_at": "2026-07-28T12:01:00+00:00",
                            },
                            "escrow": {
                                "recipient_id": "test-escrow-v1",
                                "recipient": str(escrow.to_public()),
                                "verified_at": "2026-07-28T12:02:00+00:00",
                            },
                        }
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    try:
        evidence_offload.recipient_usage_report(
            incidents_path=BASE / "incidents",
            registry_path=empty_registry,
        )
    except evidence_offload.EvidenceError as exc:
        if "unknown public recipient ID" not in str(exc):
            raise AssertionError(f"unexpected unconfigured receipt error: {exc}") from exc
    else:
        raise AssertionError("a receipt referencing an unconfigured registry was accepted")
    usage = evidence_offload.recipient_usage_report(
        incidents_path=BASE / "incidents",
        registry_path=registry_path,
    )
    if usage["source"] != "committed-restore-receipts":
        raise AssertionError("recipient usage has the wrong source")
    for entry in usage["recipients"]:
        if entry["case_count"] != 1:
            raise AssertionError(f"recipient usage has the wrong count: {entry}")
        case = entry["cases"][0]
        if case["case_uuid"] != receipt_uuid or case["case_id"] != receipt_case.name:
            raise AssertionError(f"recipient usage has the wrong case: {case}")

    print("evidence offload tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
