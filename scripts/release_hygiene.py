from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from sync_system import classify_path, iter_repo_files, load_lockfile, load_manifest


def read_text_if_possible(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def deny_matches(root: Path, deny_terms: list[str], deny_regexes: list[str]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    term_matches = {term: [] for term in deny_terms if term}
    compiled_regexes = [re.compile(pattern) for pattern in deny_regexes]
    regex_matches = {pattern.pattern: [] for pattern in compiled_regexes}
    for rel_path in iter_repo_files(root):
        path = root / rel_path
        if not path.is_file():
            continue
        text = read_text_if_possible(path)
        if text is None:
            continue
        for term, matches in term_matches.items():
            if term in text:
                matches.append(rel_path)
        for pattern in compiled_regexes:
            if pattern.search(text):
                regex_matches[pattern.pattern].append(rel_path)
    return term_matches, regex_matches


def validate_deny_terms(root: Path, deny_terms: list[str], deny_regexes: list[str]) -> list[str]:
    term_matches, regex_matches = deny_matches(root, deny_terms, deny_regexes)
    violations: list[str] = []
    for term, matches in term_matches.items():
        if not matches:
            violations.append(f"deny term did not match validation tree: {term}")
    for pattern, matches in regex_matches.items():
        if not matches:
            violations.append(f"deny regex did not match validation tree: {pattern}")
    return violations


def release_hygiene(root: Path, deny_terms: list[str], deny_regexes: list[str]) -> list[str]:
    manifest = load_manifest(root / "system-manifest.toml", root)
    lock_entries = load_lockfile(root / "system-lock.toml")
    violations: list[str] = []

    for rel_path in iter_repo_files(root):
        entry = classify_path(manifest, rel_path)
        path_class = "default_reserved" if entry is None else entry.path_class
        if path_class != "managed":
            violations.append(f"tracked non-managed path: {rel_path} [{path_class}]")

    scaffold_lock_paths = sorted(path for path, entry in lock_entries.items() if entry.path_class == "scaffold_once")
    for rel_path in scaffold_lock_paths:
        violations.append(f"release lockfile contains scaffold-once marker: {rel_path}")

    term_matches, regex_matches = deny_matches(root, deny_terms, deny_regexes)
    for term, paths in term_matches.items():
        for rel_path in paths:
            violations.append(f"deny term found in {rel_path}: {term}")
    for pattern, paths in regex_matches.items():
        for rel_path in paths:
            violations.append(f"deny regex matched in {rel_path}: {pattern}")

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate that a tree is safe to publish as a clean starter release.")
    parser.add_argument("--root", default=".", help="Release tree root to inspect.")
    parser.add_argument("--deny-term", action="append", default=[], help="Literal text that must not appear in tracked files.")
    parser.add_argument("--deny-regex", action="append", default=[], help="Regex that must not match tracked files.")
    parser.add_argument(
        "--validate-deny-terms",
        action="store_true",
        help="Validate that each deny term or regex matches this tree at least once, without running release ownership checks.",
    )
    args = parser.parse_args()

    try:
        root = Path(args.root).resolve()
        if args.validate_deny_terms:
            violations = validate_deny_terms(root, args.deny_term, args.deny_regex)
        else:
            violations = release_hygiene(root, args.deny_term, args.deny_regex)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if violations:
        print("# Release Hygiene Failed")
        print()
        for violation in violations:
            print(f"- {violation}")
        return 1

    print("deny term validation passed" if args.validate_deny_terms else "release hygiene passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
