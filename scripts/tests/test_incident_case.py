from __future__ import annotations

import shutil
import sys
import uuid
from copy import deepcopy
from datetime import date
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import evidence_offload  # noqa: E402
import incident_case  # noqa: E402
from incident_case import validate_case  # noqa: E402


BASE = ROOT / "scripts" / "tests" / ".generated" / "incident_case"


def write_case(
    name: str,
    *,
    status: str = "imported",
    privacy_review: str = "required",
    report: str | None = None,
    evidence: dict[str, object] | None = None,
) -> Path:
    case_dir = BASE / name
    (case_dir / "local").mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "case_id": name,
        "uuid": str(uuid.uuid4()),
        "title": "Example case",
        "kind": "investigation",
        "status": status,
        "confidence": "unreviewed" if status == "imported" else "observed",
        "opened_at": "2026-07-28",
        "systems": ["example"],
        "environments": ["test"],
        "owner": "repository-maintainer",
        "aliases": [],
        "privacy": {
            "classification": "restricted",
            "review": privacy_review,
        },
        "evidence": evidence
        or {
            "state": "local-only",
            "files": 1,
            "bytes": 4,
        },
        "retention": {
            "owner": "repository-maintainer",
            "review_due": "2026-10-26",
            "local_until": "2027-07-28",
        },
        "knowledge": {
            "status": "pending",
        },
    }
    if privacy_review == "passed":
        manifest["privacy"]["reviewed_by"] = "maintainer"
        manifest["privacy"]["reviewed_at"] = date.today().isoformat()
    (case_dir / "case.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    (case_dir / "local" / "raw.log").write_text("raw\n", encoding="utf-8")
    if report is not None:
        (case_dir / "report.md").write_text(report, encoding="utf-8")
    return case_dir


def main() -> int:
    if BASE.exists():
        shutil.rmtree(BASE)
    BASE.mkdir(parents=True)

    imported = write_case("2026-07-28-example-imported")
    findings = validate_case(imported)
    if findings:
        raise AssertionError(f"valid imported case failed: {findings}")

    unreviewed = write_case(
        "2026-07-28-example-unreviewed",
        status="reported",
        report="# Report\n",
    )
    findings = validate_case(unreviewed)
    if not any("requires recorded privacy review" in item for item in findings):
        raise AssertionError(f"unreviewed report was accepted: {findings}")

    crlf = write_case(
        "2026-07-28-example-crlf",
        status="reported",
        privacy_review="passed",
        report="# Report\r\n",
    )
    findings = validate_case(crlf)
    if not any("must use LF line endings" in item for item in findings):
        raise AssertionError(f"CRLF report was accepted: {findings}")

    closed = write_case(
        "2026-07-28-example-closed",
        status="closed",
        privacy_review="passed",
        report="# Report\n",
    )
    findings = validate_case(closed)
    if not any("requires knowledge.yaml" in item for item in findings):
        raise AssertionError(f"closed case without knowledge disposition was accepted: {findings}")

    invalid_offload = write_case(
        "2026-07-28-example-invalid-offload",
        evidence={"state": "offloaded"},
    )
    findings = validate_case(invalid_offload)
    if not any("requires evidence.offload" in item for item in findings):
        raise AssertionError(f"offloaded case without a receipt was accepted: {findings}")

    digest = "a" * 64
    escrow_digest = "b" * 64
    valid_offload = write_case(
        "2026-07-28-example-valid-offload",
        evidence={
            "state": "offloaded",
            "root_sha256": digest,
            "offload": {
                "schema_version": 1,
                "object_id": "drive-object-id",
                "archive_sha256": digest,
                "ciphertext_sha256": digest,
                "manifest_sha256": digest,
                "files": 1,
                "bytes": 4,
                "uploaded_at": "2026-07-28T12:00:00+00:00",
                "restore_drills": {
                    "primary": {
                        "verified_at": "2026-07-28T12:01:00+00:00",
                        "root_sha256": digest,
                        "recipient_id": "test-primary-v1",
                        "recipient": f"age1{digest}",
                    },
                    "escrow": {
                        "verified_at": "2026-07-28T12:02:00+00:00",
                        "root_sha256": digest,
                        "recipient_id": "test-escrow-v1",
                        "recipient": f"age1{escrow_digest}",
                    },
                },
                "source_deletion_authorized": False,
            },
        },
    )
    findings = validate_case(valid_offload)
    if findings:
        raise AssertionError(f"valid offloaded case failed: {findings}")

    mismatched_evidence = deepcopy(
        yaml.safe_load((valid_offload / "case.yaml").read_text(encoding="utf-8"))[
            "evidence"
        ]
    )
    mismatched_evidence["offload"]["restore_drills"]["escrow"]["root_sha256"] = (
        escrow_digest
    )
    mismatched_root = write_case(
        "2026-07-28-example-mismatched-root",
        evidence=mismatched_evidence,
    )
    findings = validate_case(mismatched_root)
    if not any("must match evidence.root_sha256" in item for item in findings):
        raise AssertionError(f"mismatched restore root was accepted: {findings}")

    original_root = incident_case.ROOT
    original_incidents = incident_case.INCIDENTS
    original_registry = evidence_offload.PUBLIC_RECIPIENTS_PATH
    empty_incidents = BASE / "empty-incidents"
    empty_incidents.mkdir()
    incident_case.ROOT = BASE
    incident_case.INCIDENTS = empty_incidents
    evidence_offload.PUBLIC_RECIPIENTS_PATH = BASE / "missing-registry.yaml"
    try:
        findings = incident_case.validate_all()
        if any("PUBLIC-AGE-RECIPIENTS.yaml" in item for item in findings):
            raise AssertionError(f"missing unconfigured registry should be accepted: {findings}")

        incident_case.INCIDENTS = BASE
        findings = incident_case.validate_all()
        unknown = [item for item in findings if "unknown public recipient ID" in item]
        if not any("test-primary-v1" in item for item in unknown):
            raise AssertionError(f"offload receipt without registry should fail: {findings}")
        if not any("test-escrow-v1" in item for item in unknown):
            raise AssertionError(f"escrow receipt without registry should fail: {findings}")

        malformed_registry = BASE / "malformed-registry.yaml"
        malformed_registry.write_text("schema_version: 1\nrecipients: []\n", encoding="utf-8")
        evidence_offload.PUBLIC_RECIPIENTS_PATH = malformed_registry
        incident_case.INCIDENTS = empty_incidents
        findings = incident_case.validate_all()
        if not any("kind must be public-age-recipient-registry" in item for item in findings):
            raise AssertionError(f"malformed registry should remain a hard error: {findings}")
    finally:
        incident_case.ROOT = original_root
        incident_case.INCIDENTS = original_incidents
        evidence_offload.PUBLIC_RECIPIENTS_PATH = original_registry

    print("incident case tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
