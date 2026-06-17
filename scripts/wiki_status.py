from __future__ import annotations

import sys
from pathlib import Path
from collections import Counter

from wiki_common import WIKI_DIR, has_errors, lint_pages, load_pages


def main() -> int:
    wiki_dir = WIKI_DIR
    pages = load_pages(wiki_dir)
    findings = lint_pages(profile="autonomous", wiki_dir=wiki_dir)
    counts = Counter(f.level for f in findings)

    print("# Wiki Status")
    print()
    print(f"Pages: {len(pages)}")
    print(f"Wiki path: {WIKI_DIR.relative_to(WIKI_DIR.parents[0]).as_posix()}")
    print(f"Errors: {counts.get('error', 0)}")
    print(f"Warnings: {counts.get('warning', 0)}")
    print()

    if findings:
        print("## Findings")
        for finding in findings:
            print(f"- {finding.level.upper()}: {finding.path}: {finding.message}")
        print()

    if has_errors(findings):
        print("Next action: fix blockers before long wiki-assisted agent runs.")
        return 1

    print("Next action: wiki is ready for assisted work.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
