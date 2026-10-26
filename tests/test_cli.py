import subprocess
import sys
from pathlib import Path

import pytest

from phx import __version__
from phx.cli import COMMANDS, main

SRC = Path(__file__).resolve().parent.parent / "src"


def test_help_lists_every_subcommand(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for name in COMMANDS:
        assert name in out


@pytest.mark.parametrize("name", [c for c in COMMANDS if c != "plan"])
def test_stubs_exit_2(name: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([name]) == 2
    assert "not implemented yet (Phase" in capsys.readouterr().err


def test_global_flags_parse() -> None:
    assert main(["--state-dir", "/x", "--verbose", "status"]) == 2


def test_module_runs_without_uv() -> None:
    proc = subprocess.run(
        [sys.executable, "-I", "-m", "phx", "--version"],
        cwd=SRC,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0 and proc.stdout.strip() == f"phx {__version__}"
