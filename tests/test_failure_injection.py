"""Failure injection (Phase 11, task 3).

Each test breaks something underneath a supervisor run and checks that PHX ends in a
state Nick can understand and resume from: ``kill -9`` mid-phase and mid-state-write, a
full disk on the state directory, git lock contention, wall-clock jumps across a
suspend, and the plan edited by Nick while a run is going.
"""

import errno
import io
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from conftest import RepoFactory, git
from phx import recover
from phx.cli import answer_question
from phx.locks import running
from phx.logging import EventLog
from phx.plan import Status, load_plan
from phx.recover import find_claude_processes, repair_blocked
from phx.state import RunState, RunStatus, load_state, save_state
from phx.supervisor import EXIT_FINISHED, EXIT_PAUSED, RESET_MARGIN_S
from scenarios import Scenario
from test_supervisor import FAKES, PLAN, SRC, FakeClock, H


@pytest.fixture
def x(tmp_path: Path, make_repo: RepoFactory) -> H:
    return H(tmp_path, make_repo, {})


def scenario(x: H, **actions: list[str]) -> H:
    x.scenario.write_text(json.dumps(actions))
    return x


def wait_for(cond: Any, timeout: float = 20.0, what: str = "condition") -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return
        time.sleep(0.05)
    pytest.fail(f"timed out waiting for {what}")


# --------------------------------------------------------------------------- kill -9


def test_kill_9_mid_phase_then_resume(x: H) -> None:
    """The orphaned session keeps the phase; PHX pauses until it is gone, then resumes it."""
    scenario(x.all_auto().decide_q1(), **{"01": ["hang", "complete"]})
    proc = subprocess.Popen(
        [sys.executable, "-m", "phx", "--state-dir", str(x.state_root), "run", str(x.repo)],
        env=dict(x.env, PYTHONPATH=str(SRC)),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        transcript = x.state_root / "SMP" / "sessions" / "01-1.jsonl"
        wait_for(
            lambda: transcript.is_file() and transcript.read_text().strip(),
            what="phase 01 session to start streaming",
        )
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(10)
        assert running(x.repo, x.env) is None  # flock dies with the process
        state = x.state()
        assert (
            state.status == RunStatus.RUNNING
            and state.sessions["01"] == x.calls("01")[0]["session"]
        )
        assert not list((x.state_root / "SMP").glob(".state.json.*.tmp"))
        # The session survives in its own process group and still holds the phase (until
        # its next stdout write hits the dead pipe: a real session may end there too).
        orphans = find_claude_processes({str(x.repo): "main checkout"}, exclude=())
        assert orphans and orphans[0].headless
        x.proc = Path("/proc")
        assert x.run() == EXIT_PAUSED
        assert x.last_event("run_end")["rule"] == "live_session"
        assert "ended without cleanup" in x.last_event("previous_run")["reason"]
        assert len(x.calls("01")) == 1  # nothing launched next to the orphan
        for p in orphans:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
        wait_for(
            lambda: not find_claude_processes({str(x.repo): "main checkout"}, exclude=()),
            what="the orphan to exit",
        )
        assert x.run(resume=True, until="01") == EXIT_FINISHED
        second = x.calls("01")[1]
        assert second["resume"] and second["session"] == x.calls("01")[0]["session"]
        assert x.status("01") is Status.COMPLETE
    finally:
        if proc.poll() is None:
            proc.kill()


def test_kill_9_mid_state_write_keeps_the_last_good_state(x: H) -> None:
    state_dir = x.state_root / "SMP"
    good = RunState(run_id="good", repo=str(x.repo), status=RunStatus.RUNNING, phase="01")
    save_state(state_dir, good)
    # a supervisor killed between writing its temp file and the rename leaves this behind
    (state_dir / ".state.json.99999.tmp").write_text('{"run_id": "half", "status": "run')
    loaded = load_state(state_dir)
    assert loaded is not None and loaded.run_id == "good"
    save_state(state_dir, loaded)
    assert not list(state_dir.glob(".state.json.*.tmp"))


def test_unreadable_state_starts_fresh(x: H) -> None:
    """A truncated state.json (not produced by PHX's atomic write, but possible) is not fatal."""
    scenario(x.all_auto().decide_q1(), **{"01": ["crash", "complete"]})
    subprocess.run(
        [sys.executable, str(FAKES / "claude"), "-p", "/phase 01 --auto", "--session-id", "s-1"],
        cwd=x.repo,
        env=x.env,
        capture_output=True,
        check=False,
    )
    (x.state_root / "SMP").mkdir(parents=True)
    (x.state_root / "SMP" / "state.json").write_text('{"run_id": "x", "sessions": {"01": ')
    assert x.run(until="01") == EXIT_FINISHED
    assert x.events("select")[0]["rule"] == "resume_fresh"  # no session to trust
    assert x.status("01") is Status.COMPLETE


# --------------------------------------------------------------------------- full disk


class FullDisk:
    """An ``os`` stand-in whose writes to files under ``root`` fail with ENOSPC."""

    def __init__(self, root: Path) -> None:
        self.root = str(root)
        self.fds: set[int] = set()
        self.armed = True
        self.failures = 0

    def open(self, path: Any, flags: int, mode: int = 0o777) -> int:
        fd = os.open(path, flags, mode)
        if str(path).startswith(self.root):
            self.fds.add(fd)
        return fd

    def write(self, fd: int, data: Any) -> int:
        if self.armed and fd in self.fds:
            self.failures += 1
            raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))
        return os.write(fd, data)

    def close(self, fd: int) -> None:
        self.fds.discard(fd)
        os.close(fd)

    def __getattr__(self, name: str) -> Any:
        return getattr(os, name)


def test_full_state_disk_does_not_stop_the_run(
    x: H, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario(x.all_auto().decide_q1())
    disk = FullDisk(x.state_root)
    for module in ("phx.logging", "phx.state", "phx.runner"):
        monkeypatch.setattr(f"{module}.os", disk)
    assert x.run() == EXIT_FINISHED
    assert [x.status(p) for p in ("01", "01a", "02")] == [Status.COMPLETE] * 3
    assert disk.failures > 10
    err = capsys.readouterr().err
    assert "not written (No space left on device)" in err
    assert '"event": "state_write_failed"' in err
    assert '"event": "transcript_write_failed"' in err and "the session continues" in err
    assert '"event": "run_end"' in err and '"status": "finished"' in err
    state_dir = x.state_root / "SMP"
    assert not (state_dir / "state.json").exists()
    assert not list(state_dir.glob(".state.json.*.tmp"))
    # space is back: the next run writes again and finds nothing left to do
    disk.armed = False
    assert x.run() == EXIT_FINISHED
    assert x.state().status == RunStatus.FINISHED


def test_state_write_recovers_after_space_returns(
    x: H, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario(x.all_auto().decide_q1())
    disk = FullDisk(x.state_root / "SMP" / "state")  # only state.json's temp files
    monkeypatch.setattr("phx.state.os", disk)
    real = SimpleNamespace(saves=0)

    def free_space_later(*args: Any, **kwargs: Any) -> Any:
        real.saves += 1
        disk.armed = real.saves < 3
        return save_state(*args, **kwargs)

    monkeypatch.setattr("phx.supervisor.save_state", free_space_later)
    disk.root = str(x.state_root / "SMP" / ".state.json")
    assert x.run(until="01") == EXIT_FINISHED
    assert len(x.events("state_write_failed")) == 1
    assert len(x.events("state_write_recovered")) == 1
    assert x.state().status == RunStatus.FINISHED


def test_event_log_short_write_goes_to_stderr(tmp_path: Path, monkeypatch: Any) -> None:
    mirror = io.StringIO()
    log = EventLog(tmp_path / "run.jsonl", mirror=mirror)

    class Short(FullDisk):
        def write(self, fd: int, data: Any) -> int:
            return os.write(fd, data[:5])

    monkeypatch.setattr("phx.logging.os", Short(tmp_path))
    log.event("hello", reason="world")
    assert log.write_errors == 1 and '"event": "hello"' in mirror.getvalue()


# --------------------------------------------------------------------------- git lock contention


def test_git_index_lock_blocks_repair_cleanly(tmp_path: Path) -> None:
    s = Scenario(tmp_path).claim().work()
    (s.repo / ".git" / "index.lock").write_text("")
    log = EventLog(tmp_path / "run.jsonl")
    assert repair_blocked(s.repo, "05", evidence="test", log=log) is None
    event = json.loads((tmp_path / "run.jsonl").read_text().splitlines()[-1])
    assert event["event"] == "repair_skipped" and "git commit failed" in event["reason"]
    assert "index.lock" in event["reason"]
    # the plan file is back as it was on main, so a later repair or a human is not confused
    assert git(s.repo, "status", "--porcelain", "--", "TST_IMPLEMENTATION_PLAN.md") == ""
    (s.repo / ".git" / "index.lock").unlink()
    assert repair_blocked(s.repo, "05", evidence="test", log=log) is not None


def test_git_index_lock_blocks_answer_cleanly(x: H, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", x.env["XDG_RUNTIME_DIR"])
    (x.repo / ".git" / "index.lock").write_text("")
    before = (x.repo / PLAN).read_text()
    with pytest.raises(ValueError, match=r"git commit failed.*index\.lock"):
        answer_question(x.repo, "1", "green")
    assert (x.repo / PLAN).read_text() == before
    (x.repo / ".git" / "index.lock").unlink()
    assert answer_question(x.repo, "1", "green").startswith("answered #1")


def test_push_timeout_in_repair_is_logged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    s = Scenario(tmp_path).claim().work()
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    git(s.repo, "remote", "add", "origin", str(bare))
    real = recover._run_git

    def slow_push(repo: Path, *args: str, timeout: float | None = None) -> Any:
        if args[:1] == ("push",):
            raise subprocess.TimeoutExpired(["git", "push"], timeout or 0)
        return real(repo, *args, timeout=timeout)

    monkeypatch.setattr(recover, "_run_git", slow_push)
    log = EventLog(tmp_path / "run.jsonl")
    assert repair_blocked(s.repo, "05", evidence="test", log=log) is not None
    event = json.loads((tmp_path / "run.jsonl").read_text().splitlines()[-1])
    assert event["event"] == "repair" and event["push"] == "push timed out"


# --------------------------------------------------------------------------- clock jumps


def test_suspend_during_a_wait_wakes_late_and_resumes(x: H) -> None:
    scenario(x, **{"01": ["limit:3600", "complete"], "probe": ["ok"]})

    def suspend(clock: FakeClock) -> None:
        if clock.slept and not getattr(clock, "jumped", False):
            clock.jumped = True  # type: ignore[attr-defined]
            clock.t += 5 * 3600  # the laptop slept through the reset

    x.clock.on_sleep = suspend
    assert x.run(until="01") == EXIT_FINISHED
    wake = x.last_event("wake")
    assert "late (suspend?)" in wake["reason"] and wake["late_s"] > 3600
    assert len(x.calls("probe")) == 1 and x.calls("01")[1]["resume"]
    assert x.clock.slept < 600  # it did not wait the hour again after waking


def test_wall_clock_going_backwards_does_not_wake_early(x: H) -> None:
    scenario(x, **{"01": ["limit:3600", "complete"], "probe": ["ok"]})
    until = x.clock.start + 3600 + RESET_MARGIN_S
    seen: list[float] = []

    def ntp_step_back(clock: FakeClock) -> None:
        if clock.slept and not seen:
            clock.t -= 1800  # the clock is corrected backwards half an hour
        seen.append(clock.t)

    x.clock.on_sleep = ntp_step_back
    assert x.run(until="01") == EXIT_FINISHED
    assert x.clock.t >= x.last_event("wait_start")["until_epoch"]  # woke only once it passed
    assert x.clock.slept >= 3600 + RESET_MARGIN_S + 1800 - 5  # waited the lost half hour too
    assert x.last_event("wait_start")["until_epoch"] == pytest.approx(until, abs=5)
    assert len(x.calls("probe")) == 1


# --------------------------------------------------------------------------- plan edited mid-run


def _edit_after(x: H, monkeypatch: pytest.MonkeyPatch, phase: str, old: str, new: str) -> None:
    """Nick edits the plan on ``main`` while ``phase``'s session is finishing."""
    real = recover.handle_outcome

    def edit_then_handle(repo: Path, outcome: Any, **kw: Any) -> Any:
        if outcome.phase == phase:
            x.edit_plan(old, new)
        return real(repo, outcome, **kw)

    monkeypatch.setattr("phx.supervisor.handle_outcome", edit_then_handle)


def test_plan_edit_mid_run_owner_gate_is_respected(x: H, monkeypatch: pytest.MonkeyPatch) -> None:
    scenario(x.all_auto().decide_q1())
    _edit_after(
        x,
        monkeypatch,
        "01",
        "SMP_phase-01a-inserted.md) | auto |",
        "SMP_phase-01a-inserted.md) | owner |",
    )
    assert x.run() == EXIT_PAUSED
    assert x.phase_calls() == ["01"]
    end = x.last_event("run_end")
    assert end["phase"] == "01a" and "owner" in end["reason"]
    assert x.status("01a") is Status.NOT_STARTED


def test_plan_edit_mid_run_reopened_question_holds_the_phase(
    x: H, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario(x.all_auto().decide_q1())
    _edit_after(
        x,
        monkeypatch,
        "01a",
        "Decided 2026-10-26 08:00 CDT: green",
        "Open. Proposed default: blue",
    )
    assert x.run() == EXIT_PAUSED
    assert x.phase_calls() == ["01", "01a"]
    assert "#1" in x.last_event("run_end")["reason"]
    assert load_plan(x.repo).phase("02").status is Status.NOT_STARTED


def test_git_index_lock_blocks_preflight_record_cleanly(x: H) -> None:
    from phx.preflight import PREFLIGHT_FILE, PreflightRefused, record

    (x.repo / ".git" / "index.lock").write_text("")
    with pytest.raises(PreflightRefused, match="git commit failed"):
        record(x.repo, env=x.env)
    assert not (x.repo / PREFLIGHT_FILE).exists()
    (x.repo / ".git" / "index.lock").unlink()
    first = record(x.repo, env=x.env)
    # a second record over an existing one: the old file comes back on failure
    (x.repo / ".git" / "index.lock").write_text("")
    with pytest.raises(PreflightRefused):
        record(x.repo, env=x.env)
    assert git(x.repo, "status", "--porcelain") == "" and first.commit
