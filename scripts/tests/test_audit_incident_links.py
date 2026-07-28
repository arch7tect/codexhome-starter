from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_incident_links import references, safe_summary  # noqa: E402


def main() -> int:
    known = {
        "product-a:cases/44",
        "product-a:cases/example_001",
    }
    found = references(
        "Replay cases/44 and cases/example_001; ignore cases/examples.",
        "product-a",
        known,
    )
    if found != [
        "product-a:cases/44",
        "product-a:cases/example_001",
    ]:
        raise AssertionError(found)

    resolved = safe_summary(
        [
            {
                "scope": "product-repository",
                "family": "product-a",
                "alias": "product-a:cases/44",
                "resolved": True,
            }
        ]
    )
    if resolved["state"] != "resolved" or resolved["totals"]["unresolved"] != 0:
        raise AssertionError(resolved)

    unresolved = safe_summary(
        [
            {
                "scope": "product-repository",
                "family": "product-a",
                "alias": "product-a:cases/45",
                "resolved": False,
            }
        ]
    )
    if unresolved["state"] != "audit-complete-repair-pending":
        raise AssertionError(unresolved)

    print("incident link audit tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
