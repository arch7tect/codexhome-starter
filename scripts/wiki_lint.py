from __future__ import annotations

import argparse
import sys
from pathlib import Path

from wiki_common import has_errors, lint_pages, print_findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint LLM wiki pages.")
    parser.add_argument("--profile", choices=["normal", "autonomous"], default="normal")
    parser.add_argument("--wiki-dir", default="wiki", help="Wiki directory to scan.")
    args = parser.parse_args()

    findings = lint_pages(profile=args.profile, wiki_dir=Path(args.wiki_dir))
    print_findings(findings)
    return 1 if has_errors(findings) else 0


if __name__ == "__main__":
    sys.exit(main())
