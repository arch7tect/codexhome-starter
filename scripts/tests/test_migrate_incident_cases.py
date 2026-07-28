from __future__ import annotations

import shutil
import sys
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import incident_case  # noqa: E402
import migrate_incident_cases as migration  # noqa: E402


BASE = ROOT / "scripts" / "tests" / ".generated" / "migrate_incident_cases"


def main() -> int:
    if BASE.exists():
        shutil.rmtree(BASE)
    source_a = BASE / "source-a" / "cases" / "01"
    source_b = BASE / "source-b" / "cases" / "01"
    source_a.mkdir(parents=True)
    source_b.mkdir(parents=True)
    (source_a / "shared.txt").write_text("same\n", encoding="utf-8")
    (source_a / "only-a.txt").write_text("a\n", encoding="utf-8")
    (source_b / "shared.txt").write_text("same\n", encoding="utf-8")
    (source_b / "only-b.txt").write_text("b\n", encoding="utf-8")
    (source_b / "shared-link.txt").symlink_to("shared.txt")

    destination = BASE / "incidents"
    destination.mkdir(parents=True)
    migration.INCIDENTS = destination
    migration.LOCAL_ROOT = destination / ".local"
    migration.OBJECTS = migration.LOCAL_ROOT / "objects"
    incident_case.INCIDENTS = destination

    args = Namespace(
        source=[
            ["example", "source-a", str(source_a.parent)],
            ["example", "source-b", str(source_b.parent)],
        ],
        owner="repository-maintainer",
        date="2026-07-28",
        run_id="test-import",
        apply=True,
    )
    summary = migration.migrate(args)
    if summary["totals"]["canonical_cases"] != 1:
        raise AssertionError(summary)
    if summary["totals"]["source_files"] != 5:
        raise AssertionError(summary)
    if summary["totals"]["unique_objects"] != 3:
        raise AssertionError(summary)

    cases = [
        path
        for path in destination.iterdir()
        if path.is_dir() and incident_case.CASE_ID_RE.fullmatch(path.name)
    ]
    if len(cases) != 1:
        raise AssertionError(cases)
    findings = incident_case.validate_case(cases[0], check_git=False)
    if findings:
        raise AssertionError(findings)
    local_files = list((cases[0] / "local" / "legacy").rglob("*.txt"))
    if len(local_files) != 5:
        raise AssertionError(local_files)
    compat = destination / ".local" / "compat" / "example" / "cases" / "01"
    if not compat.is_symlink() or not (compat / "shared.txt").is_file():
        raise AssertionError(compat)

    rerun = migration.migrate(args)
    if rerun != summary:
        raise AssertionError("migration is not idempotent")

    safe_summary = (destination / "migrations" / "test-import.yaml").read_text(encoding="utf-8")
    if str(BASE) in safe_summary:
        raise AssertionError("safe migration summary leaked a local path")

    print("incident case migration tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
