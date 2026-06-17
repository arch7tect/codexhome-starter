from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from textwrap import dedent


ROOT = Path(__file__).resolve().parents[2]
GENERATED = ROOT / "scripts" / "tests" / ".generated"
BAD_FIXTURES = GENERATED / "wiki_lint_bad_fixtures"
STALE_ONLY = GENERATED / "wiki_lint_stale_only"


def write_fixture(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(body).lstrip(), encoding="utf-8")


def create_fixtures() -> None:
    generated_unsafe_path = "/" + "home/example/private-project"
    write_fixture(
        BAD_FIXTURES / "broken-link.md",
        """
        ---
        status: active
        updated: 2026-06-16
        confidence: verified
        expires: 2026-09-16
        sources:
          - AGENTS.md
        tags:
          - test-fixture
        ---

        # Broken Link

        [Missing page](missing.md)
        """,
    )
    write_fixture(
        BAD_FIXTURES / "missing-source.md",
        """
        ---
        status: active
        updated: 2026-06-16
        confidence: verified
        expires: 2026-09-16
        sources:
          - references/does-not-exist.md
        tags:
          - test-fixture
        ---

        # Missing Source

        This fixture has a missing source.
        """,
    )
    write_fixture(
        BAD_FIXTURES / "stale-page.md",
        """
        ---
        status: active
        updated: 2025-01-01
        confidence: verified
        expires: 2025-01-01
        sources:
          - AGENTS.md
        tags:
          - test-fixture
        ---

        # Stale Page

        This fixture is expired.
        """,
    )
    write_fixture(
        BAD_FIXTURES / "unsafe-path.md",
        f"""
        ---
        status: active
        updated: 2026-06-16
        confidence: verified
        expires: 2026-09-16
        sources:
          - AGENTS.md
        tags:
          - test-fixture
        ---

        # Unsafe Path

        This fixture contains `{generated_unsafe_path}`.
        """,
    )
    write_fixture(
        STALE_ONLY / "stale-page.md",
        """
        ---
        status: active
        updated: 2025-01-01
        confidence: verified
        expires: 2025-01-01
        sources:
          - AGENTS.md
        tags:
          - test-fixture
        ---

        # Stale Page

        This fixture is expired and should fail in autonomous profile.
        """,
    )


def main() -> int:
    create_fixtures()

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "wiki_lint.py"),
            "--wiki-dir",
            str(BAD_FIXTURES),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    output = result.stdout
    expected = [
        "broken markdown link",
        "source does not exist",
        "page expired",
        "developer-specific absolute home path",
    ]
    missing = [item for item in expected if item not in output]
    if result.returncode == 0:
        print(output)
        print("ERROR: wiki_lint.py succeeded on bad fixtures")
        return 1
    if missing:
        print(output)
        print(f"ERROR: missing expected findings: {', '.join(missing)}")
        return 1

    stale_result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "wiki_lint.py"),
            "--profile",
            "autonomous",
            "--wiki-dir",
            str(STALE_ONLY),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if stale_result.returncode == 0 or "page expired" not in stale_result.stdout:
        print(stale_result.stdout)
        print("ERROR: autonomous profile did not fail on stale-only fixture")
        return 1

    print("wiki_lint negative fixtures passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
