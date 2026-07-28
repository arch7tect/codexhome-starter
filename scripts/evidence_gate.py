from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_SUFFIXES = {".csv", ".json", ".jsonl", ".md", ".py", ".txt", ".yaml"}
DENIED_SUFFIXES = {".env", ".html", ".pem", ".wav", ".xlsx", ".zip"}
MAX_FILE_BYTES = 512 * 1024
MAX_BUNDLE_BYTES = 2 * 1024 * 1024
TRANSCRIPT_FIELDS = {"hypothesis", "text", "transcript", "utterance"}
TEXT_PATTERNS = {
    "developer-specific home path": re.compile(r"(?:/Users|/home|C:\\Users)[/\\][^\s`'\")]+"),
    "private key": re.compile(r"BEGIN (?:RSA|OPENSSH|EC) PRIVATE KEY"),
    "authorization header": re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    "secret assignment": re.compile(r"\b(?:TOKEN|PASSWORD|SECRET)=\S+", re.IGNORECASE),
    "common API credential": re.compile(r"\b(?:sk-|xox[baprs]-|AKIA)[A-Za-z0-9_-]{12,}"),
    "email address": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    "SIP URI": re.compile(r"\bsips?:[^\s\"']+", re.IGNORECASE),
    "international phone number": re.compile(r"(?<!\w)\+\d(?:[\s().-]*\d){8,14}(?!\w)"),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def has_carriage_return(path: Path) -> bool:
    return b"\r" in path.read_bytes()


def row_count(path: Path) -> int | None:
    if path.suffix == ".jsonl":
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    if path.suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as handle:
            return max(0, sum(1 for _ in csv.reader(handle)) - 1)
    return None


def has_transcript_field(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key.lower() in TRANSCRIPT_FIELDS and nested not in (None, "", [], {}):
                return True
            if has_transcript_field(nested):
                return True
    elif isinstance(value, list):
        return any(has_transcript_field(item) for item in value)
    return False


def structured_transcript_present(path: Path) -> bool:
    if path.suffix == ".json":
        return has_transcript_field(json.loads(path.read_text(encoding="utf-8")))
    if path.suffix == ".jsonl":
        return any(
            has_transcript_field(json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    if path.suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return any((field or "").lower() in TRANSCRIPT_FIELDS for field in reader.fieldnames or [])
    return False


def scan_text(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [label for label, pattern in TEXT_PATTERNS.items() if pattern.search(text)]


def safe_relative_path(value: str) -> Path | None:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        return None
    return path


def git_output(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def validate_bundle(bundle: Path) -> list[str]:
    bundle = bundle.resolve()
    errors: list[str] = []
    if not bundle.is_dir():
        return [f"bundle does not exist: {bundle}"]
    if not BUNDLE_ID_RE.fullmatch(bundle.name):
        errors.append(f"invalid bundle id: {bundle.name}")

    manifest_path = bundle / "MANIFEST.yaml"
    checksums_path = bundle / "CHECKSUMS.sha256"
    if not manifest_path.exists():
        return errors + ["missing MANIFEST.yaml"]
    if not checksums_path.exists():
        return errors + ["missing CHECKSUMS.sha256"]
    for metadata_path in (manifest_path, checksums_path):
        if has_carriage_return(metadata_path):
            errors.append(f"{metadata_path.name}: committed text must use LF line endings")

    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return errors + [f"invalid MANIFEST.yaml: {exc}"]
    if not isinstance(manifest, dict):
        return errors + ["MANIFEST.yaml must contain a mapping"]
    if manifest.get("schema_version") != 1:
        errors.append("manifest schema_version must be 1")
    if manifest.get("bundle_id") != bundle.name:
        errors.append("manifest bundle_id does not match directory name")
    retention = manifest.get("retention")
    if not isinstance(retention, dict) or not retention.get("owner"):
        errors.append("manifest retention owner is required")
    else:
        try:
            date.fromisoformat(str(retention.get("expires")))
        except ValueError:
            errors.append("manifest retention expires must be YYYY-MM-DD")

    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        return errors + ["manifest files must be a non-empty list"]

    seen: set[str] = set()
    committed: dict[str, str] = {}
    committed_bytes = 0
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            errors.append(f"manifest file entry {index} must be a mapping")
            continue
        raw_path = entry.get("path")
        if not isinstance(raw_path, str):
            errors.append(f"manifest file entry {index} has no path")
            continue
        relative = safe_relative_path(raw_path)
        if relative is None:
            errors.append(f"unsafe manifest path: {raw_path}")
            continue
        normalized = relative.as_posix()
        if normalized in seen:
            errors.append(f"duplicate manifest path: {normalized}")
            continue
        seen.add(normalized)

        disposition = entry.get("disposition")
        if disposition not in {"committed", "local"}:
            errors.append(f"{normalized}: disposition must be committed or local")
            continue
        if disposition == "local" and relative.parts[0] != "local":
            errors.append(f"{normalized}: local evidence must be under local/")
        if disposition == "committed" and relative.parts[0] == "local":
            errors.append(f"{normalized}: committed evidence must not be under local/")

        path = bundle / relative
        if not path.is_file():
            errors.append(f"{normalized}: file is missing")
            continue
        expected_hash = entry.get("sha256")
        if not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(expected_hash):
            errors.append(f"{normalized}: invalid sha256")
        elif sha256_file(path) != expected_hash:
            errors.append(f"{normalized}: sha256 mismatch")
        expected_bytes = entry.get("bytes")
        if expected_bytes != path.stat().st_size:
            errors.append(f"{normalized}: byte count mismatch")
        expected_rows = entry.get("rows")
        actual_rows = row_count(path)
        if expected_rows is not None and expected_rows != actual_rows:
            errors.append(f"{normalized}: row count mismatch")

        if disposition == "committed":
            suffix = path.suffix.lower()
            if suffix in DENIED_SUFFIXES or suffix not in ALLOWED_SUFFIXES:
                errors.append(f"{normalized}: disallowed file type")
            committed_bytes += path.stat().st_size
            if path.stat().st_size > MAX_FILE_BYTES:
                errors.append(f"{normalized}: file exceeds {MAX_FILE_BYTES} bytes")
            if has_carriage_return(path):
                errors.append(f"{normalized}: committed text must use LF line endings")
            try:
                for finding in scan_text(path):
                    errors.append(f"{normalized}: possible {finding}")
                if structured_transcript_present(path):
                    reviewed = (
                        entry.get("redaction") == "maintainer-reviewed"
                        and bool(entry.get("reviewed_by"))
                        and bool(entry.get("reviewed_at"))
                    )
                    if not reviewed:
                        errors.append(f"{normalized}: transcript-like content lacks maintainer review")
            except (UnicodeDecodeError, csv.Error, json.JSONDecodeError) as exc:
                errors.append(f"{normalized}: cannot inspect structured text: {exc}")
            committed[normalized] = expected_hash
        else:
            tracked = git_output("ls-files", "--error-unmatch", str(path.relative_to(ROOT)))
            if tracked.returncode == 0:
                errors.append(f"{normalized}: local evidence is tracked by Git")
            ignored = git_output("check-ignore", "-q", str(path.relative_to(ROOT)))
            if ignored.returncode != 0:
                errors.append(f"{normalized}: local evidence is not gitignored")

    if committed_bytes > MAX_BUNDLE_BYTES:
        errors.append(f"committed bundle exceeds {MAX_BUNDLE_BYTES} bytes")

    actual_files = {
        path.relative_to(bundle).as_posix()
        for path in bundle.rglob("*")
        if path.is_file()
        and path.name not in {"CHECKSUMS.sha256", "MANIFEST.yaml"}
    }
    for path in sorted(actual_files - seen):
        errors.append(f"unlisted bundle file: {path}")
    for path in sorted(seen - actual_files):
        errors.append(f"manifest entry has no file: {path}")

    expected_checksums = "".join(
        f"{digest}  {path}\n" for path, digest in sorted(committed.items())
    )
    if checksums_path.read_text(encoding="utf-8") != expected_checksums:
        errors.append("CHECKSUMS.sha256 does not match committed manifest entries")
    for finding in scan_text(manifest_path):
        errors.append(f"MANIFEST.yaml: possible {finding}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a committed research evidence bundle.")
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    errors = validate_bundle(args.bundle)
    if errors:
        print("# Evidence Gate Failed")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"evidence gate passed: {args.bundle}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
