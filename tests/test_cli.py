import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from conftest import RepoFactory
from phx import __version__
from phx.cli import (
    COMMANDS,
    main,
    status_report,
    watch_frame,
    watch_notice,
    watch_payload,
    watch_signature,
)
from phx.state import Progress, RunState, save_state

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


# --------------------------------------------------------------------------- status progress

NOW = 1_700_000_000.0


def progress_block(**over: Any) -> dict[str, Any]:
    block: dict[str, Any] = {
        "phase": "12d",
        "attempt": 1,
        "stage": "working",
        "activity": "editing src/phx/x.py",
        "last_tool": "Edit src/phx/x.py",
        "last_text": None,
        "steps": 3,
        "tools": {"edit": 2, "bash": 1},
        "tokens": 1_234_567,
        "cost_usd": 1.5,
        "since": NOW - 600,
        "last_event": NOW - 12,
        "elapsed_s": 600.0,
        "eta": "~20m of ~80m typical left (median of 9 phases)",
        "stall_after_s": 900.0,
        "in_flight": None,
    }
    block.update(over)
    return block


def write_state(sdir: Path, **over: Any) -> RunState:
    state = RunState(
        run_id="r",
        repo=str(sdir.parent),
        status="running",
        phase="12d",
        attempt=1,
        session_id="s",
        started="2026-10-31 10:00 CDT",
    )
    for key, value in over.items():
        setattr(state, key, value)
    save_state(sdir, state)
    return state


def test_status_progress_lines_and_json(
    tmp_path: Path, make_repo: RepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo("sample", name="work/R")
    sdir = tmp_path / "state" / "R"
    state = write_state(sdir)
    state.progress = Progress(
        phase="12d",
        attempt=1,
        stage="working",
        activity="editing src/phx/x.py",
        last_tool="Edit src/phx/x.py",
        steps=3,
        tools={"edit": 2, "bash": 1},
        tokens=1_234_567,
        cost_usd=1.5,
        since=NOW - 600,
        last_event=time.time() - 12,
        elapsed_s=600.0,
        eta="~20m of ~80m typical left (median of 9 phases)",
        stall_after_s=900.0,
    )
    save_state(sdir, state)
    report = status_report(repo, tmp_path / "state")
    assert report["progress"] is not None
    assert report["progress"]["stage"] == "working"
    assert report["progress"]["stalled"] is False
    assert 0 <= report["progress"]["last_event_age_s"] < 60
    assert main(["--state-dir", str(tmp_path / "state"), "status", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "Doing:      editing src/phx/x.py (working) · 3 steps (2 edit, 1 bash)" in out
    assert "1.23M tokens, $1.50" in out
    assert "last event" in out and "~20m of ~80m typical left" in out
    assert main(["--state-dir", str(tmp_path / "state"), "status", str(repo), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["progress"]["steps"] == 3 and payload["progress"]["stalled"] is False


def test_status_with_an_old_state_file_prints_nothing_extra(
    tmp_path: Path, make_repo: RepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """A ``state.json`` written before this phase must load and print cleanly."""
    repo = make_repo("sample", name="work/R")
    sdir = tmp_path / "state" / "R"
    state = write_state(sdir, phase="05", attempt=2)
    state.progress = None
    save_state(sdir, state)
    data = json.loads((sdir / "state.json").read_text())
    data.pop("progress", None)
    data["phases"] = {"05": {"sessions": 1, "tokens": 10, "cost_usd": 0.1, "wait_s": 0.0}}
    (sdir / "state.json").write_text(json.dumps(data))
    report = status_report(repo, tmp_path / "state")
    assert report["progress"] is None
    assert main(["--state-dir", str(tmp_path / "state"), "status", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "Doing:" not in out and "Phase:      05 attempt 2" in out


# --------------------------------------------------------------------------- watch


def test_watch_frame_and_signature() -> None:
    state: dict[str, Any] = {
        "status": "running",
        "phase": "12d",
        "attempt": 1,
        "session_id": "s",
        "progress": progress_block(),
    }
    frame = watch_frame(state, None, NOW)
    assert frame.startswith(
        "12d attempt 1 · 10m elapsed · working · editing src/phx/x.py · 3 steps"
    )
    assert "1.23M tokens $1.50" in frame
    assert "evt 12s ago" in frame
    assert frame.endswith("~20m of ~80m typical left (median of 9 phases)")
    stalled = watch_frame(
        {
            "status": "running",
            "phase": "12d",
            "attempt": 1,
            "progress": progress_block(last_event=NOW - 1000),
        },
        None,
        NOW,
    )
    assert stalled.startswith("⚠ 12d attempt 1")
    assert watch_frame(None, None, NOW) == "no PHX run recorded yet"
    assert "pid 7" in watch_frame(None, {"pid": 7}, NOW)
    base = watch_signature(state, None, NOW)
    assert watch_signature(state, None, NOW) == base
    moved = dict(state, progress=progress_block(steps=4))
    assert watch_signature(moved, None, NOW) != base
    went_quiet = dict(state, progress=progress_block(last_event=NOW - 1000))
    assert watch_signature(went_quiet, None, NOW) != base  # going amber is a change
    no_run = watch_frame({"status": "waiting", "phase": "05", "attempt": 1}, None, NOW)
    assert no_run.startswith("05 attempt 1 · waiting")


def test_watch_payload_and_notices() -> None:
    state: dict[str, Any] = {
        "status": "running",
        "phase": "12d",
        "attempt": 1,
        "progress": progress_block(),
    }
    payload = watch_payload(state, {"pid": 7}, NOW)
    assert payload["status"] == "running" and payload["running"]["pid"] == 7
    assert payload["progress"]["stalled"] is False
    assert payload["frame"] == watch_frame(state, None, NOW)
    json.dumps(payload)  # --json must always be serialisable
    assert watch_notice(None, "/w/R") is None
    assert watch_notice({"status": "running"}, "/w/R") is None
    kind, lines = watch_notice(
        {"status": "paused", "pause": {"reason": "needs colour", "question_ids": ["6"]}},
        "/w/R",
    )
    assert kind == "paused" and "needs colour" in lines[0]
    assert 'phx answer /w/R 6 "…"' in lines[1] and "phx resume /w/R" in lines[1]
    kind, lines = watch_notice({"status": "paused", "pause": {"reason": "review"}}, "/w/R")
    assert kind == "paused" and lines[1] == "  when ready: phx resume /w/R"
    kind, lines = watch_notice(
        {"status": "waiting", "wait": {"reason": "usage limit", "until": NOW}}, "/w/R"
    )
    assert kind == "waiting" and "wakes" in lines[0]
    kind, lines = watch_notice({"status": "finished", "end_reason": "all done"}, "/w/R")
    assert kind == "finished" and lines == ["run finished: all done"]


def test_watch_exits_cleanly_on_a_terminal_run(
    tmp_path: Path,
    make_repo: RepoFactory,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = make_repo("sample", name="work/R")
    state = write_state(tmp_path / "state" / "R", status="finished", end_reason="every phase done")
    state.progress = None
    save_state(tmp_path / "state" / "R", state)

    def no_sleep(seconds: float) -> None:
        raise AssertionError("watch must exit before sleeping on a finished run")

    monkeypatch.setattr(time, "sleep", no_sleep)
    assert main(["--state-dir", str(tmp_path / "state"), "watch", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "run finished: every phase done" in out


def test_watch_no_run_and_ctrl_c_exit_zero(
    tmp_path: Path,
    make_repo: RepoFactory,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = make_repo("sample", name="work/R")

    def interrupt(seconds: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(time, "sleep", interrupt)
    assert main(["--state-dir", str(tmp_path / "none"), "watch", str(repo)]) == 0
    assert "no PHX run recorded yet" in capsys.readouterr().out


def test_watch_json_prints_one_object_per_change(
    tmp_path: Path,
    make_repo: RepoFactory,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = make_repo("sample", name="work/R")
    state = write_state(tmp_path / "state" / "R")
    state.progress = Progress(
        phase="12d",
        attempt=1,
        stage="working",
        activity="editing src/phx/x.py",
        steps=3,
        tools={"edit": 2, "bash": 1},
        tokens=1_234_567,
        cost_usd=1.5,
        elapsed_s=600.0,
        eta="~20m of ~80m typical left (median of 9 phases)",
        stall_after_s=900.0,
    )
    save_state(tmp_path / "state" / "R", state)

    def interrupt(seconds: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(time, "sleep", interrupt)
    assert main(["--state-dir", str(tmp_path / "state"), "watch", str(repo), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["status"] == "running"
    assert payload["progress"]["stage"] == "working"
    assert payload["frame"].startswith("12d attempt 1")


def test_run_help_lists_only(capsys: pytest.CaptureFixture[str]) -> None:
    """Lucent2 (ADR-0120) detects `--only` from this help text."""
    with pytest.raises(SystemExit):
        main(["run", "--help"])
    assert "--only NN" in capsys.readouterr().out


@pytest.mark.parametrize(
    "extra", [["--until", "02"], ["--max-phases", "1"], ["--pause-after", "01"]]
)
def test_only_excludes_the_other_bounds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], extra: list[str]
) -> None:
    code = main(["--state-dir", str(tmp_path), "run", str(tmp_path), "--only", "01", *extra])
    assert code == 1
    assert "--only runs one phase" in capsys.readouterr().err


def test_detach_forwards_only(tmp_path: Path) -> None:
    from phx.cli import _forward_args, build_parser

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    args = build_parser().parse_args(["run", str(tmp_path), "--detach", "--only", "20o"])
    assert _forward_args(args)[-2:] == ["--only", "20o"]
