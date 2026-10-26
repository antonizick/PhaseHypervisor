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


def test_global_flags_parse(tmp_path: Path) -> None:
    assert main(["--state-dir", str(tmp_path), "--verbose", "status"]) == 0


def test_module_runs_without_uv() -> None:
    proc = subprocess.run(
        [sys.executable, "-I", "-m", "phx", "--version"],
        cwd=SRC,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0 and proc.stdout.strip() == f"phx {__version__}"
