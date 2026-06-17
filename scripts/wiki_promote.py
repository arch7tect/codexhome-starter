from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

from wiki_common import ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a draft wiki promotion report from session notes.")
    parser.add_argument("session_note", help="Path to a session note or sanitized fixture.")
    parser.add_argument("--draft", action="store_true", help="Write a draft report under wiki/drafts/.")
    args = parser.parse_args()

    source = (ROOT / args.session_note).resolve()
    if not source.exists():
        print(f"ERROR: session note does not exist: {args.session_note}", file=sys.stderr)
        return 1

    title = source.stem
    today = date.today().isoformat()
    expires = (date.today() + timedelta(days=30)).isoformat()

    draft = f"""---
status: draft
updated: {today}
confidence: observed
expires: {expires}
sources:
  - {source.relative_to(ROOT).as_posix()}
tags:
  - llm-wiki
  - promotion-draft
---

# Promotion Draft: {title}

## Source

- `{source.relative_to(ROOT).as_posix()}`

## Proposed Additions

- TBD

## Proposed Updates

- TBD

## Proposed Archive Actions

- TBD

## Rejected Notes

- TBD

## Required Sources

- TBD

## Open Questions

- TBD

## Source Excerpt

```text
Source excerpt intentionally omitted. Inspect the source note directly during maintainer review.
```
"""

    if args.draft:
        drafts_dir = ROOT / "wiki" / "drafts"
        drafts_dir.mkdir(parents=True, exist_ok=True)
        output = drafts_dir / f"{today}-{title}-promotion.md"
        output.write_text(draft, encoding="utf-8")
        print(output.relative_to(ROOT).as_posix())
        return 0

    print(draft)
    return 0


if __name__ == "__main__":
    sys.exit(main())
