from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from incident_case import case_directories, load_yaml


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_RE = re.compile(r"(?<![A-Za-z0-9_])cases/([A-Za-z0-9_.-]+)")
TEXT_SUFFIXES = {".cpp", ".h", ".hpp", ".json", ".md", ".py", ".sh", ".txt", ".yaml", ".yml"}
PLACEHOLDERS = {"N", "NN", "NNN", "case", "example"}


def aliases() -> set[str]:
    result: set[str] = set()
    for case_dir in case_directories():
        manifest = load_yaml(case_dir / "case.yaml")
        result.update(alias for alias in manifest.get("aliases", []) if isinstance(alias, str))
    return result


def references(text: str, family: str, known_aliases: set[str]) -> list[str]:
    result: list[str] = []
    for match in REFERENCE_RE.finditer(text):
        legacy_name = match.group(1)
        alias = f"{family}:cases/{legacy_name}"
        if legacy_name in PLACEHOLDERS:
            continue
        if alias not in known_aliases and not any(character.isdigit() for character in legacy_name):
            continue
        result.append(alias)
    return result


def tracked_files(repo: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    return [
        repo / item.decode()
        for item in result.stdout.split(b"\0")
        if item and (repo / item.decode()).suffix.lower() in TEXT_SUFFIXES
    ]


def scan_product_repo(
    family: str,
    source_id: str,
    repo: Path,
    known_aliases: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in tracked_files(repo):
        if not path.is_file() or "cases" in path.relative_to(repo).parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for alias in references(text, family, known_aliases):
            rows.append(
                {
                    "scope": "product-repository",
                    "source_id": source_id,
                    "family": family,
                    "path": path.relative_to(repo).as_posix(),
                    "alias": alias,
                    "resolved": alias in known_aliases,
                }
            )
    return rows


def scan_migrated_reports(known_aliases: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for case_dir in case_directories():
        manifest = load_yaml(case_dir / "case.yaml")
        systems = manifest.get("systems", [])
        if not systems:
            continue
        family = str(systems[0])
        local_dir = case_dir / "local"
        if not local_dir.exists():
            continue
        for path in sorted(local_dir.rglob("*")):
            if not path.is_file() or path.name not in {"report.md", "problem.md", "problem.txt"}:
                continue
            content = path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            key = (family, digest)
            if key in seen:
                continue
            seen.add(key)
            try:
                text = content.decode()
            except UnicodeDecodeError:
                continue
            for alias in references(text, family, known_aliases):
                rows.append(
                    {
                        "scope": "legacy-case-text",
                        "source_id": "migrated-local",
                        "family": family,
                        "case_id": case_dir.name,
                        "path": path.relative_to(case_dir).as_posix(),
                        "alias": alias,
                        "resolved": alias in known_aliases,
                    }
                )
    return rows


def safe_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_scope: dict[str, Counter[str]] = {}
    by_family: dict[str, Counter[str]] = {}
    for row in rows:
        scope = str(row["scope"])
        family = str(row["family"])
        by_scope.setdefault(scope, Counter())["total"] += 1
        by_scope[scope]["resolved" if row["resolved"] else "unresolved"] += 1
        by_family.setdefault(family, Counter())["total"] += 1
        by_family[family]["resolved" if row["resolved"] else "unresolved"] += 1
    unresolved_aliases = {str(row["alias"]) for row in rows if not row["resolved"]}
    link_note = (
        "Unresolved legacy references must be repaired or explicitly waived before source cleanup."
        if unresolved_aliases
        else "The legacy cross-reference repair gate is complete."
    )
    return {
        "schema_version": 1,
        "state": "audit-complete-repair-pending" if unresolved_aliases else "resolved",
        "totals": {
            "references": len(rows),
            "resolved": sum(bool(row["resolved"]) for row in rows),
            "unresolved": sum(not bool(row["resolved"]) for row in rows),
            "unresolved_aliases": len(unresolved_aliases),
        },
        "by_scope": {key: dict(value) for key, value in sorted(by_scope.items())},
        "by_family": {key: dict(value) for key, value in sorted(by_family.items())},
        "notes": [
            "Detailed paths and aliases are retained only in the gitignored local audit.",
            link_note,
            "Other source-cleanup gates remain independent of this audit.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit legacy incident case cross-references.")
    parser.add_argument(
        "--repo",
        nargs=3,
        action="append",
        metavar=("FAMILY", "SOURCE_ID", "REPO"),
        default=[],
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--local-output", type=Path, required=True)
    args = parser.parse_args()

    known_aliases = aliases()
    rows = scan_migrated_reports(known_aliases)
    for family, source_id, raw_repo in args.repo:
        rows.extend(
            scan_product_repo(
                family,
                source_id,
                Path(raw_repo).expanduser().resolve(),
                known_aliases,
            )
        )
    args.local_output.parent.mkdir(parents=True, exist_ok=True)
    with args.local_output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(safe_summary(rows), sort_keys=False),
        encoding="utf-8",
    )
    print(f"audited {len(rows)} incident case references")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
