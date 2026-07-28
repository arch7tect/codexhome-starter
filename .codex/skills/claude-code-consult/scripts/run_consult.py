#!/usr/bin/env python3

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


TIMEOUT_SECONDS = 600
TERMINATE_GRACE_SECONDS = 5
DEFAULT_BUDGET_USD = 10.0
REQUIRED_FLAGS = (
    "--no-session-persistence",
    "--permission-mode",
    "--tools",
    "--max-budget-usd",
)
ADDITIONAL_DIRECTORY_FLAG = "--add-dir"


def bounded_budget(value: str) -> float:
    budget = float(value)
    if budget <= 0 or budget > DEFAULT_BUDGET_USD:
        raise argparse.ArgumentTypeError(
            f"budget must be greater than zero and at most {DEFAULT_BUDGET_USD:g}"
        )
    return budget


def existing_directory(value: str) -> Path:
    directory = Path(value).expanduser().resolve()
    if not directory.is_dir():
        raise argparse.ArgumentTypeError(
            f"path is not an existing directory: {value}"
        )
    return directory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a bounded read-only Claude Code consultation."
    )
    parser.add_argument(
        "--max-budget-usd",
        type=bounded_budget,
        default=DEFAULT_BUDGET_USD,
        help="Cost ceiling; may be lowered but cannot exceed 10 USD.",
    )
    parser.add_argument(
        "--add-dir",
        action="append",
        default=[],
        type=existing_directory,
        help="Additional repository directory Claude may inspect; repeat as needed.",
    )
    return parser.parse_args()


def resolve_cli() -> str:
    configured = os.environ.get("CLAUDE_CODE_CLI", "").strip()
    if configured:
        return configured
    resolved = shutil.which("claude")
    if not resolved:
        raise RuntimeError("Claude Code CLI is unavailable in this shell")
    return resolved


def validate_cli_flags(
    cli: str,
    require_additional_directories: bool = False,
) -> None:
    try:
        result = subprocess.run(
            [cli, "--help"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"cannot inspect Claude Code CLI flags: {exc}") from exc
    help_text = f"{result.stdout}\n{result.stderr}"
    missing = [flag for flag in REQUIRED_FLAGS if flag not in help_text]
    if (
        require_additional_directories
        and ADDITIONAL_DIRECTORY_FLAG not in help_text
    ):
        missing.append(ADDITIONAL_DIRECTORY_FLAG)
    if result.returncode != 0 or missing:
        details = ", ".join(missing) if missing else f"exit code {result.returncode}"
        raise RuntimeError(
            f"Claude Code CLI does not support the required safety flags: {details}"
        )


def emit_output(stdout: str, stderr: str) -> None:
    if stdout:
        sys.stdout.write(stdout)
    if stderr:
        sys.stderr.write(stderr)


def run_consult(
    cli: str,
    prompt: str,
    budget_usd: float,
    additional_directories: list[Path],
) -> int:
    command = [
        cli,
        "-p",
        "--no-session-persistence",
        "--permission-mode",
        "dontAsk",
        "--tools",
        "Read,Grep,Glob",
    ]
    for directory in additional_directories:
        command.extend([ADDITIONAL_DIRECTORY_FLAG, str(directory)])
    command.extend(
        [
            "--max-budget-usd",
            f"{budget_usd:g}",
        ]
    )
    try:
        process = subprocess.Popen(
            command,
            cwd=Path.cwd(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        raise RuntimeError(f"cannot start Claude Code CLI: {exc}") from exc

    try:
        stdout, stderr = process.communicate(prompt, timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=TERMINATE_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
        emit_output(stdout, stderr)
        print(
            f"Claude Code consultation timed out after {TIMEOUT_SECONDS} seconds",
            file=sys.stderr,
        )
        return 124

    emit_output(stdout, stderr)
    return process.returncode


def main() -> int:
    args = parse_args()
    prompt = sys.stdin.read()
    if not prompt.strip():
        print("Consultation prompt is empty", file=sys.stderr)
        return 2
    try:
        cli = resolve_cli()
        validate_cli_flags(
            cli,
            require_additional_directories=bool(args.add_dir),
        )
        return run_consult(
            cli,
            prompt,
            args.max_budget_usd,
            args.add_dir,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
