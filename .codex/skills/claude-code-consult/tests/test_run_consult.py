import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch


RUNNER_PATH = Path(__file__).parents[1] / "scripts" / "run_consult.py"
SPEC = importlib.util.spec_from_file_location(
    "claude_code_consult_runner",
    RUNNER_PATH,
)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_existing_directory_resolves_directory(tmp_path):
    assert runner.existing_directory(str(tmp_path)) == tmp_path.resolve()


def test_existing_directory_rejects_file(tmp_path):
    file_path = tmp_path / "file.txt"
    file_path.write_text("not a directory")

    try:
        runner.existing_directory(str(file_path))
    except argparse.ArgumentTypeError as exc:
        assert "not an existing directory" in str(exc)
    else:
        raise AssertionError("file path was accepted as an additional directory")


def test_parse_args_accepts_repeated_add_dir(tmp_path):
    second = tmp_path / "second"
    third = tmp_path / "third"
    second.mkdir()
    third.mkdir()

    with patch.object(
        sys,
        "argv",
        ["run_consult.py", "--add-dir", str(second), "--add-dir", str(third)],
    ):
        args = runner.parse_args()

    assert args.add_dir == [second.resolve(), third.resolve()]


def test_validate_cli_requires_add_dir_only_for_multi_repository_call():
    help_result = subprocess.CompletedProcess(
        args=["claude", "--help"],
        returncode=0,
        stdout=" ".join(runner.REQUIRED_FLAGS),
        stderr="",
    )

    with patch.object(runner.subprocess, "run", return_value=help_result):
        runner.validate_cli_flags("claude")
        try:
            runner.validate_cli_flags(
                "claude",
                require_additional_directories=True,
            )
        except RuntimeError as exc:
            assert "--add-dir" in str(exc)
        else:
            raise AssertionError("missing --add-dir support was accepted")


def test_run_consult_forwards_directories_and_keeps_read_only_tools(tmp_path):
    second = tmp_path / "second"
    third = tmp_path / "third"
    second.mkdir()
    third.mkdir()
    process = Mock()
    process.communicate.return_value = ("review", "")
    process.returncode = 0

    with patch.object(runner.subprocess, "Popen", return_value=process) as popen:
        result = runner.run_consult(
            "claude",
            "Review this",
            3.0,
            [second, third],
        )

    assert result == 0
    command = popen.call_args.args[0]
    assert command.count("--add-dir") == 2
    assert command[command.index("--tools") + 1] == "Read,Grep,Glob"
    assert str(second) in command
    assert str(third) in command
