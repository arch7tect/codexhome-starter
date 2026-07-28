from __future__ import annotations

import argparse
import os
import re
import subprocess
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
INCIDENTS = ROOT / "incidents"
CASE_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")
PUBLIC_RECIPIENT_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_STATUSES = {
    "open",
    "investigating",
    "explained",
    "reported",
    "knowledge-extracted",
    "closed",
    "inconclusive",
    "duplicate",
    "imported",
}
ALLOWED_CONFIDENCE = {"unreviewed", "observed", "probable", "speculative"}
ALLOWED_EVIDENCE_STATES = {"none", "local-only", "offloaded", "purged"}
ALLOWED_SUFFIXES = {".csv", ".json", ".jsonl", ".md", ".py", ".sh", ".svg", ".txt", ".yaml", ".yml"}
DENIED_SUFFIXES = {".env", ".html", ".jpeg", ".jpg", ".log", ".pcap", ".png", ".wav", ".xlsx", ".zip"}
MAX_FILE_BYTES = 256 * 1024
MAX_CASE_BYTES = 1024 * 1024
MAX_CASE_FILES = 25
SECRET_PATTERNS = {
    "developer-specific home path": re.compile(r"(?:/Users|/home|C:\\Users)[/\\][^\s`'\")]+"),
    "private key": re.compile(r"BEGIN (?:RSA|OPENSSH|EC) PRIVATE KEY"),
    "authorization header": re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    "secret assignment": re.compile(r"\b(?:TOKEN|PASSWORD|SECRET)=\S+", re.IGNORECASE),
    "common API credential": re.compile(r"\b(?:sk-|xox[baprs]-|AKIA)[A-Za-z0-9_-]{12,}"),
    "email address": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    "SIP URI": re.compile(r"\bsips?:[^\s\"']+", re.IGNORECASE),
    "international phone number": re.compile(r"(?<!\w)\+\d(?:[\s().-]*\d){8,14}(?!\w)"),
}


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a mapping")
    return value


def write_yaml(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(value, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise ValueError("slug must contain an ASCII letter or digit")
    return slug


def git_output(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def git_ignored(paths: list[str]) -> set[str]:
    if not paths:
        return set()
    result = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        cwd=ROOT,
        text=True,
        input="\n".join(paths) + "\n",
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return {line for line in result.stdout.splitlines() if line}


def case_directories() -> list[Path]:
    return sorted(
        path
        for path in INCIDENTS.iterdir()
        if path.is_dir() and CASE_ID_RE.fullmatch(path.name)
    )


def committed_files(case_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in case_dir.rglob("*")
        if path.is_file()
        and path.name != ".DS_Store"
        and not {"local", ".local"}.intersection(path.relative_to(case_dir).parts)
        and "artifacts" not in path.relative_to(case_dir).parts
    )


def scan_text(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [label for label, pattern in SECRET_PATTERNS.items() if pattern.search(text)]


def validate_case(case_dir: Path, *, check_git: bool = True) -> list[str]:
    case_dir = case_dir.resolve()
    errors: list[str] = []
    if not case_dir.is_dir():
        return [f"case does not exist: {case_dir}"]
    if not CASE_ID_RE.fullmatch(case_dir.name):
        errors.append(f"invalid case id: {case_dir.name}")

    manifest_path = case_dir / "case.yaml"
    if not manifest_path.is_file():
        return errors + ["missing case.yaml"]
    if b"\r" in manifest_path.read_bytes():
        errors.append("case.yaml: committed text must use LF line endings")
    try:
        manifest = load_yaml(manifest_path)
    except (UnicodeDecodeError, yaml.YAMLError, ValueError) as exc:
        return errors + [f"invalid case.yaml: {exc}"]

    if manifest.get("schema_version") != 1:
        errors.append("case.yaml schema_version must be 1")
    if manifest.get("case_id") != case_dir.name:
        errors.append("case.yaml case_id does not match directory name")
    try:
        uuid.UUID(str(manifest.get("uuid")))
    except (ValueError, TypeError, AttributeError):
        errors.append("case.yaml uuid must be a UUID")
    status = manifest.get("status")
    if status not in ALLOWED_STATUSES:
        errors.append(f"case.yaml status must be one of {sorted(ALLOWED_STATUSES)}")
    if manifest.get("confidence") not in ALLOWED_CONFIDENCE:
        errors.append(f"case.yaml confidence must be one of {sorted(ALLOWED_CONFIDENCE)}")
    systems = manifest.get("systems")
    if not isinstance(systems, list) or not systems or not all(isinstance(item, str) and item for item in systems):
        errors.append("case.yaml systems must be a non-empty string list")
    if not manifest.get("owner"):
        errors.append("case.yaml owner is required")

    privacy = manifest.get("privacy")
    if not isinstance(privacy, dict) or privacy.get("review") not in {"required", "passed"}:
        errors.append("case.yaml privacy.review must be required or passed")
        privacy = {}
    evidence = manifest.get("evidence")
    if not isinstance(evidence, dict) or evidence.get("state") not in ALLOWED_EVIDENCE_STATES:
        errors.append(f"case.yaml evidence.state must be one of {sorted(ALLOWED_EVIDENCE_STATES)}")
        evidence = {}
    if evidence.get("state") == "offloaded":
        evidence_root = str(evidence.get("root_sha256", ""))
        if not SHA256_RE.fullmatch(evidence_root):
            errors.append("offloaded evidence requires a root_sha256")
        offload = evidence.get("offload")
        if not isinstance(offload, dict) or offload.get("schema_version") != 1:
            errors.append("offloaded evidence requires evidence.offload schema_version 1")
        else:
            if not isinstance(offload.get("object_id"), str) or not offload["object_id"]:
                errors.append("case.yaml evidence.offload.object_id is required")
            for field in ("archive_sha256", "ciphertext_sha256", "manifest_sha256"):
                if not SHA256_RE.fullmatch(str(offload.get(field, ""))):
                    errors.append(f"case.yaml evidence.offload.{field} must be a SHA-256")
            for field in ("files", "bytes"):
                if not isinstance(offload.get(field), int) or offload[field] <= 0:
                    errors.append(
                        f"case.yaml evidence.offload.{field} must be a positive integer"
                    )
            try:
                datetime.fromisoformat(str(offload.get("uploaded_at")))
            except ValueError:
                errors.append("case.yaml evidence.offload.uploaded_at must be ISO-8601")
            drills = offload.get("restore_drills")
            if not isinstance(drills, dict):
                errors.append("offloaded evidence requires primary and escrow restore drills")
            else:
                drill_recipients: set[str] = set()
                for role in ("primary", "escrow"):
                    drill = drills.get(role)
                    if not isinstance(drill, dict):
                        errors.append(f"offloaded evidence requires a {role} restore drill")
                        continue
                    if not SHA256_RE.fullmatch(str(drill.get("root_sha256", ""))):
                        errors.append(
                            f"case.yaml evidence.offload.restore_drills.{role}.root_sha256 "
                            "must be a SHA-256"
                        )
                    elif drill["root_sha256"] != evidence_root:
                        errors.append(
                            f"case.yaml evidence.offload.restore_drills.{role}.root_sha256 "
                            "must match evidence.root_sha256"
                        )
                    recipient = drill.get("recipient")
                    if not isinstance(recipient, str) or not recipient.startswith("age1"):
                        errors.append(
                            f"case.yaml evidence.offload.restore_drills.{role}.recipient "
                            "must be an age recipient"
                        )
                    else:
                        drill_recipients.add(recipient)
                    recipient_id = drill.get("recipient_id")
                    if (
                        not isinstance(recipient_id, str)
                        or not PUBLIC_RECIPIENT_ID_RE.fullmatch(recipient_id)
                    ):
                        errors.append(
                            f"case.yaml evidence.offload.restore_drills.{role}."
                            "recipient_id must be lower-case kebab-case"
                        )
                    try:
                        datetime.fromisoformat(str(drill.get("verified_at")))
                    except ValueError:
                        errors.append(
                            f"case.yaml evidence.offload.restore_drills.{role}.verified_at "
                            "must be ISO-8601"
                        )
                if len(drill_recipients) != 2:
                    errors.append(
                        "offloaded evidence requires distinct primary and escrow recipients"
                    )
            if not isinstance(offload.get("source_deletion_authorized"), bool):
                errors.append(
                    "case.yaml evidence.offload.source_deletion_authorized must be boolean"
                )
    retention = manifest.get("retention")
    if not isinstance(retention, dict) or not retention.get("owner"):
        errors.append("case.yaml retention.owner is required")
    else:
        for field in ("review_due", "local_until"):
            try:
                date.fromisoformat(str(retention.get(field)))
            except ValueError:
                errors.append(f"case.yaml retention.{field} must be YYYY-MM-DD")

    files = committed_files(case_dir)
    if len(files) > MAX_CASE_FILES:
        errors.append(f"committed case exceeds {MAX_CASE_FILES} files")
    total_bytes = sum(path.stat().st_size for path in files)
    if total_bytes > MAX_CASE_BYTES:
        errors.append(f"committed case exceeds {MAX_CASE_BYTES} bytes")
    for path in files:
        relative = path.relative_to(case_dir).as_posix()
        suffix = path.suffix.lower()
        if suffix in DENIED_SUFFIXES or suffix not in ALLOWED_SUFFIXES:
            errors.append(f"{relative}: disallowed committed file type")
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            errors.append(f"{relative}: file exceeds {MAX_FILE_BYTES} bytes")
        if b"\r" in path.read_bytes():
            errors.append(f"{relative}: committed text must use LF line endings")
        try:
            for finding in scan_text(path):
                errors.append(f"{relative}: possible {finding}")
        except UnicodeDecodeError as exc:
            errors.append(f"{relative}: committed file is not UTF-8 text: {exc}")

    if status in {"reported", "knowledge-extracted", "closed", "inconclusive"}:
        if not (case_dir / "report.md").is_file():
            errors.append(f"{status} case requires report.md")
        if privacy.get("review") != "passed" or not privacy.get("reviewed_by") or not privacy.get("reviewed_at"):
            errors.append(f"{status} case requires recorded privacy review")
    if status in {"knowledge-extracted", "closed"}:
        knowledge_path = case_dir / "knowledge.yaml"
        if not knowledge_path.is_file():
            errors.append(f"{status} case requires knowledge.yaml")
        else:
            try:
                knowledge = load_yaml(knowledge_path)
                dispositions = knowledge.get("dispositions")
                if not isinstance(dispositions, list) or not dispositions:
                    errors.append("knowledge.yaml dispositions must be a non-empty list")
            except (UnicodeDecodeError, yaml.YAMLError, ValueError) as exc:
                errors.append(f"invalid knowledge.yaml: {exc}")

    for local_dir in (case_dir / "local", case_dir / ".local"):
        if local_dir.exists() and check_git:
            relative = local_dir.relative_to(ROOT)
            tracked = git_output("ls-files", "--", str(relative))
            if tracked.stdout.strip():
                errors.append(f"{relative}: local evidence is tracked by Git")
            if git_output("check-ignore", "-q", str(relative)).returncode != 0:
                errors.append(f"{relative}: local evidence is not gitignored")
    return errors


def validate_all() -> list[str]:
    errors: list[str] = []
    aliases: dict[str, str] = {}
    uuids: dict[str, str] = {}
    public_recipients: dict[str, dict[str, Any]] = {}
    try:
        from evidence_offload import load_public_recipient_registry

        public_recipients = load_public_recipient_registry()
    except (ImportError, OSError, ValueError, RuntimeError) as exc:
        errors.append(f"PUBLIC-AGE-RECIPIENTS.yaml: {exc}")
    cases = case_directories()
    for case_dir in cases:
        for error in validate_case(case_dir, check_git=False):
            errors.append(f"{case_dir.name}: {error}")
        try:
            manifest = load_yaml(case_dir / "case.yaml")
        except (OSError, UnicodeDecodeError, yaml.YAMLError, ValueError):
            continue
        case_uuid = str(manifest.get("uuid"))
        previous_uuid = uuids.get(case_uuid)
        if previous_uuid and previous_uuid != case_dir.name:
            errors.append(f"{case_dir.name}: duplicate uuid also used by {previous_uuid}")
        uuids[case_uuid] = case_dir.name
        evidence = manifest.get("evidence")
        offload = evidence.get("offload") if isinstance(evidence, dict) else None
        drills = offload.get("restore_drills") if isinstance(offload, dict) else None
        if isinstance(drills, dict):
            for role in ("primary", "escrow"):
                drill = drills.get(role)
                if not isinstance(drill, dict):
                    continue
                recipient_id = drill.get("recipient_id")
                if not isinstance(recipient_id, str) or not recipient_id:
                    errors.append(
                        f"{case_dir.name}: {role} restore drill has no public recipient ID"
                    )
                    continue
                entry = public_recipients.get(recipient_id)
                if entry is None:
                    errors.append(
                        f"{case_dir.name}: unknown public recipient ID {recipient_id!r}"
                    )
                    continue
                if entry.get("role") != role:
                    errors.append(
                        f"{case_dir.name}: public recipient ID {recipient_id!r} "
                        f"has role {entry.get('role')!r}, expected {role!r}"
                    )
                if entry.get("public_age_recipient") != drill.get("recipient"):
                    errors.append(
                        f"{case_dir.name}: public recipient ID {recipient_id!r} "
                        "does not match the restore receipt"
                    )
        for alias in manifest.get("aliases", []):
            if not isinstance(alias, str) or not alias:
                errors.append(f"{case_dir.name}: aliases must contain non-empty strings")
                continue
            previous_alias = aliases.get(alias)
            if previous_alias and previous_alias != case_dir.name:
                errors.append(f"{case_dir.name}: alias {alias!r} also used by {previous_alias}")
            aliases[alias] = case_dir.name

    tracked = git_output("ls-files", "--", "incidents").stdout.splitlines()
    for path in tracked:
        if {"local", ".local"}.intersection(Path(path).parts):
            errors.append(f"{path}: local evidence is tracked by Git")
    local_paths = [
        (case_dir / "local").relative_to(ROOT).as_posix()
        for case_dir in cases
        if (case_dir / "local").exists()
    ]
    global_local = INCIDENTS / ".local"
    if global_local.exists():
        local_paths.append(global_local.relative_to(ROOT).as_posix())
    ignored = git_ignored(local_paths)
    for path in local_paths:
        if path not in ignored:
            errors.append(f"{path}: local evidence is not gitignored")
    return errors


def next_case_id(opened: date, system: str, slug: str) -> str:
    base = f"{opened.isoformat()}-{slugify(system)}-{slugify(slug)}"
    candidate = base
    suffix = 2
    while (INCIDENTS / candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def create_case(args: argparse.Namespace) -> Path:
    opened = date.fromisoformat(args.date)
    case_id = next_case_id(opened, args.system, args.slug)
    case_dir = INCIDENTS / case_id
    local_dir = case_dir / "local"
    local_dir.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "case_id": case_id,
        "uuid": str(uuid.uuid4()),
        "title": args.title,
        "kind": args.kind,
        "status": "open",
        "confidence": "unreviewed",
        "opened_at": opened.isoformat(),
        "systems": [slugify(args.system)],
        "environments": [args.environment],
        "owner": args.owner,
        "aliases": [],
        "privacy": {
            "classification": "restricted",
            "review": "required",
        },
        "evidence": {
            "state": "local-only",
            "files": 0,
            "bytes": 0,
        },
        "retention": {
            "owner": args.owner,
            "review_due": (opened + timedelta(days=90)).isoformat(),
            "local_until": (opened + timedelta(days=365)).isoformat(),
        },
        "knowledge": {
            "status": "pending",
        },
    }
    write_yaml(case_dir / "case.yaml", manifest)
    (local_dir / "problem.md").write_text(
        "# Problem\n\n"
        f"Title: {args.title}\n"
        f"System: {slugify(args.system)}\n"
        f"Environment: {args.environment}\n\n"
        "## Complaint\n\n"
        "<Record the verbatim complaint here. Keep secrets out.>\n\n"
        "## Identifiers\n\n"
        "<Keep session, tenant, bot, communication, and external issue identifiers here.>\n\n"
        "## Scope\n\n"
        "<Describe the diagnostic scope and exclusions.>\n",
        encoding="utf-8",
    )
    return case_dir


def build_indexes() -> None:
    rows: list[tuple[str, str, str, str, list[str]]] = []
    aliases: list[tuple[str, str, str]] = []
    for case_dir in case_directories():
        try:
            manifest = load_yaml(case_dir / "case.yaml")
        except (OSError, UnicodeDecodeError, yaml.YAMLError, ValueError):
            continue
        case_id = case_dir.name
        title = str(manifest.get("title", "Untitled"))
        status = str(manifest.get("status", "unknown"))
        systems = [str(item) for item in manifest.get("systems", [])]
        case_uuid = str(manifest.get("uuid", ""))
        rows.append((case_id, title, status, case_uuid, systems))
        for alias in manifest.get("aliases", []):
            if isinstance(alias, str):
                aliases.append((alias, case_id, case_uuid))

    index_lines = [
        "# Incident Index",
        "",
        "Generated by `uv run python scripts/incident_case.py index`.",
        "",
        "| Case | Status | Systems | UUID |",
        "|---|---|---|---|",
    ]
    for case_id, title, status, case_uuid, systems in rows:
        index_lines.append(
            f"| [{title}]({case_id}/) | {status} | {', '.join(systems)} | `{case_uuid}` |"
        )
    (INCIDENTS / "index.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")

    alias_lines = [
        "# Legacy Incident Case Map",
        "",
        "Generated by `uv run python scripts/incident_case.py index`.",
        "",
        "| Legacy alias | Canonical case | UUID |",
        "|---|---|---|",
    ]
    for alias, case_id, case_uuid in sorted(aliases):
        alias_lines.append(f"| `{alias}` | [{case_id}]({case_id}/) | `{case_uuid}` |")
    (INCIDENTS / "LEGACY-MAP.md").write_text("\n".join(alias_lines) + "\n", encoding="utf-8")


def build_compatibility_view() -> int:
    count = 0
    compat_root = INCIDENTS / ".local" / "compat"
    for case_dir in case_directories():
        manifest = load_yaml(case_dir / "case.yaml")
        evidence = manifest.get("evidence", {})
        variants = evidence.get("variants", []) if isinstance(evidence, dict) else []
        source_ids = sorted(
            str(variant["source_id"])
            for variant in variants
            if isinstance(variant, dict) and variant.get("source_id")
        )
        if not source_ids:
            continue
        active = [source_id for source_id in source_ids if source_id.endswith("-active")]
        source_id = active[0] if active else source_ids[0]
        target = case_dir / "local" / "legacy" / source_id
        if not target.is_dir():
            continue
        for alias in manifest.get("aliases", []):
            if not isinstance(alias, str) or ":cases/" not in alias:
                continue
            family, legacy_name = alias.split(":cases/", 1)
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
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Create, validate, and index CodexHome incident cases.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--system", required=True)
    create_parser.add_argument("--slug", required=True)
    create_parser.add_argument("--title", required=True)
    create_parser.add_argument("--owner", required=True)
    create_parser.add_argument("--environment", default="unknown")
    create_parser.add_argument("--kind", choices=["incident", "investigation", "request", "drill"], default="incident")
    create_parser.add_argument("--date", default=date.today().isoformat())

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("case", nargs="?", type=Path)
    subparsers.add_parser("index")
    subparsers.add_parser("compat")

    args = parser.parse_args()
    if args.command == "create":
        case_dir = create_case(args)
        print(case_dir)
        return 0
    if args.command == "index":
        build_indexes()
        print(f"indexed {len(case_directories())} incident cases")
        return 0
    if args.command == "compat":
        count = build_compatibility_view()
        print(f"created {count} compatibility links")
        return 0

    errors = validate_case(args.case) if args.case else validate_all()
    if errors:
        print("# Incident Case Validation Failed")
        for error in errors:
            print(f"- {error}")
        return 1
    target = args.case or INCIDENTS
    print(f"incident case validation passed: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
