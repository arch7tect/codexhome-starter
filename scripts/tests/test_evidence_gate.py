from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from evidence_gate import validate_bundle  # noqa: E402


BASE = ROOT / "scripts" / "tests" / ".generated" / "evidence_gate"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_bundle(name: str, committed_body: str) -> Path:
    bundle = BASE / name
    (bundle / "canonical").mkdir(parents=True)
    (bundle / "local").mkdir()
    committed = bundle / "canonical" / "runs.jsonl"
    local = bundle / "local" / "transcripts.jsonl"
    committed.write_text(committed_body, encoding="utf-8")
    local.write_text('{"transcript":"private speech"}\n', encoding="utf-8")
    files = [
        {
            "path": "canonical/runs.jsonl",
            "role": "canonical-runs",
            "disposition": "committed",
            "privacy": "hash-only",
            "redaction": "none",
            "sha256": digest(committed),
            "bytes": committed.stat().st_size,
            "rows": 1,
        },
        {
            "path": "local/transcripts.jsonl",
            "role": "raw-transcripts",
            "disposition": "local",
            "privacy": "patient-derived",
            "redaction": "local-only",
            "sha256": digest(local),
            "bytes": local.stat().st_size,
            "rows": 1,
        },
    ]
    manifest = {
        "schema_version": 1,
        "bundle_id": name,
        "created": "2026-07-28",
        "retention": {
            "owner": "repository-maintainer",
            "expires": "2027-07-28",
        },
        "files": files,
    }
    (bundle / "MANIFEST.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    (bundle / "CHECKSUMS.sha256").write_text(
        f"{digest(committed)}  canonical/runs.jsonl\n",
        encoding="utf-8",
    )
    return bundle


def main() -> int:
    if BASE.exists():
        shutil.rmtree(BASE)
    BASE.mkdir(parents=True)

    valid = write_bundle(
        "2026-07-28-example-valid",
        '{"run_id":"one","transcript_sha256":"' + "a" * 64 + '"}\n',
    )
    findings = validate_bundle(valid)
    if findings:
        raise AssertionError(f"valid bundle failed: {findings}")

    transcript = write_bundle(
        "2026-07-28-example-transcript",
        '{"run_id":"one","transcript":"patient speech"}\n',
    )
    findings = validate_bundle(transcript)
    if not any("lacks maintainer review" in item for item in findings):
        raise AssertionError(f"unreviewed transcript was accepted: {findings}")

    mismatch = write_bundle(
        "2026-07-28-example-mismatch",
        '{"run_id":"one","transcript_sha256":"' + "b" * 64 + '"}\n',
    )
    (mismatch / "canonical" / "runs.jsonl").write_text('{"changed":true}\n', encoding="utf-8")
    findings = validate_bundle(mismatch)
    if not any("sha256 mismatch" in item for item in findings):
        raise AssertionError(f"checksum mismatch was accepted: {findings}")

    unsafe = write_bundle(
        "2026-07-28-example-unsafe",
        '{"run_id":"one","note":"person@example.com"}\n',
    )
    findings = validate_bundle(unsafe)
    if not any("email address" in item for item in findings):
        raise AssertionError(f"PII pattern was accepted: {findings}")

    crlf = write_bundle(
        "2026-07-28-example-crlf",
        '{"run_id":"one","transcript_sha256":"' + "c" * 64 + '"}\r\n',
    )
    findings = validate_bundle(crlf)
    if not any("must use LF line endings" in item for item in findings):
        raise AssertionError(f"CRLF content was accepted: {findings}")

    print("evidence gate tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
