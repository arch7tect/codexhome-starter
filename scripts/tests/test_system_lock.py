from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from system_lock import LockDecisionInput, decide_lock_action, normalized_sha256  # noqa: E402


def assert_decision(expected: str, expected_disposition: str, **kwargs: str | None) -> None:
    decision = decide_lock_action(LockDecisionInput(**kwargs))
    if decision.action != expected:
        raise AssertionError(f"expected {expected}, got {decision.action}: {decision.reason}")
    if decision.disposition != expected_disposition:
        raise AssertionError(
            f"expected disposition {expected_disposition}, got {decision.disposition}: {decision.reason}"
        )


def test_hash_normalization() -> None:
    left = normalized_sha256(b"alpha\r\nbeta", "text")
    right = normalized_sha256(b"alpha\nbeta\n\n", "text")
    if left != right:
        raise AssertionError("text hash normalization should canonicalize line endings and trailing newline")

    binary_left = normalized_sha256(b"alpha\r\nbeta", "binary")
    binary_right = normalized_sha256(b"alpha\nbeta\n", "binary")
    if binary_left == binary_right:
        raise AssertionError("binary hash must not normalize line endings")


def test_decision_matrix() -> None:
    base = "base"
    local = "local"
    starter = "starter"

    assert_decision("noop", "noop", baseline_hash=base, local_hash=base, starter_hash=base)
    assert_decision("fast_forward", "apply", baseline_hash=base, local_hash=base, starter_hash=starter)
    assert_decision("keep_local", "report", baseline_hash=base, local_hash=local, starter_hash=base)
    assert_decision("conflict", "stop", baseline_hash=base, local_hash=local, starter_hash=starter)
    assert_decision("noop_update_lock", "report", baseline_hash=base, local_hash=starter, starter_hash=starter)
    assert_decision("stop_local_deleted", "stop", baseline_hash=base, local_hash=None, starter_hash=starter)
    assert_decision("prune_candidate", "report", baseline_hash=base, local_hash=base, starter_hash=None)
    assert_decision("safe_new", "apply", baseline_hash=None, local_hash=None, starter_hash=starter)
    assert_decision("conflict_existing_untracked", "stop", baseline_hash=None, local_hash=local, starter_hash=starter)
    assert_decision("noop", "noop", baseline_hash=None, local_hash=None, starter_hash=None)
    assert_decision("keep_local", "report", baseline_hash=None, local_hash=local, starter_hash=None)
    assert_decision("noop_removed", "noop", baseline_hash=base, local_hash=None, starter_hash=None)
    assert_decision("keep_local", "report", baseline_hash=base, local_hash=local, starter_hash=None)
    assert_decision(
        "stop_class_change",
        "stop",
        baseline_hash=base,
        local_hash=base,
        starter_hash=base,
        locked_class="managed",
        manifest_class="reserved_user",
    )
    assert_decision(
        "stop_content_type_change",
        "stop",
        baseline_hash=base,
        local_hash=base,
        starter_hash=base,
        locked_content_type="text",
        manifest_content_type="binary",
    )


def main() -> int:
    test_hash_normalization()
    test_decision_matrix()
    print("system_lock tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
