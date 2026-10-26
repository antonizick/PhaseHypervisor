"""End-to-end supervisor runs over the 3-phase sample plan, with the fakes (Phase 07).

The fake ``claude`` acts as a scripted phase agent (``tests/fakes/fake_agent.py``): it
claims, works in a worktree, merges, blocks with a question or hits a usage limit, so
the supervisor, verifier and recovery code all see real git state. Usage-limit waits run
on a fake clock. Each test also checks that ``run.jsonl`` explains the decisions.
"""

import io
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from conftest import RepoFactory, git
from phx.cli import answer_question
from phx.locks import RunLock, running
from phx.plan import Status, load_plan
from phx.state import RunStatus, load_state, save_state
from phx.supervisor import (
    BACKOFF_S,
    EXIT_ERROR,
    EXIT_FINISHED,
    EXIT_PAUSED,
    EXIT_STOPPED,
    RESET_MARGIN_S,
    RunOptions,
    Supervisor,
)

TESTS = Path(__file__).resolve().parent
FAKES = TESTS / "fakes"
SRC = TESTS.parent / "src"
PLAN = "SMP_IMPLEMENTATION_PLAN.md"
# The manual /phase check, verbatim from the contract (§8)
CONTRACT_CHECK = next(
    line
    for line in (TESTS.parent / "docs" / "PHX_AUTO_MODE_CONTRACT.md").read_text().splitlines()
    if line.startswith('f="${XDG_RUNTIME_DIR')
)


class FakeClock:
    def __init__(self, on_sleep: Callable[["FakeClock"], None] | None = None) -> None:
        self.start = self.t = time.time()
        self.on_sleep = on_sleep
        self.slept = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float, stop: threading.Event) -> None:
        self.t += seconds
        self.slept += seconds
        if self.on_sleep:
            self.on_sleep(self)


class H:
    """One sample repo plus everything a supervisor run needs, all under ``tmp_path``."""

    def __init__(self, tmp: Path, make_repo: RepoFactory, scenario: dict[str, list[str]]) -> None:
        self.tmp = tmp
        self.repo = make_repo("sample", name="work/SMP")
        self.scenario = tmp / "scenario.json"
        self.scenario.write_text(json.dumps(scenario))
        self.state_root = tmp / "state"
        self.proc = tmp / "proc"
        self.proc.mkdir()
        self.provider_file = tmp / "provider"
        self.env = dict(
            os.environ,
            PATH=f"{FAKES}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            HOME=str(tmp / "home"),
            XDG_RUNTIME_DIR=str(tmp / "run"),
            PHX_WORK_ROOT=str(tmp / "work"),
            PHX_FAKE_AGENT=str(self.scenario),
            PHX_FAKE_NOTIFY_LOG=str(tmp / "notify.jsonl"),
            PHX_FAKE_PROVIDER_FILE=str(self.provider_file),
            DISPLAY=":0",
            DBUS_SESSION_BUS_ADDRESS="unix:path=/nonexistent",
        )
        self.clock = FakeClock()
        self.out = io.StringIO()
        self.last: Supervisor | None = None

    # --- repo setup ---------------------------------------------------------------------

    def edit_plan(self, old: str, new: str) -> None:
        path = self.repo / PLAN
        text = path.read_text()
        assert old in text, old
        path.write_text(text.replace(old, new))
        git(self.repo, "commit", "-q", "-am", "test: edit plan")

    def all_auto(self) -> "H":
        text = (self.repo / PLAN).read_text().replace("| review |", "| auto |")
        text = text.replace("SMP_phase-01a-inserted.md) | |", "SMP_phase-01a-inserted.md) | auto |")
        (self.repo / PLAN).write_text(text)
        git(self.repo, "commit", "-q", "-am", "test: all gates auto")
        return self

    def decide_q1(self) -> "H":
        self.edit_plan("Open. Proposed default: blue", "Decided 2026-10-26 08:00 CDT: green")
        return self

    # --- running ------------------------------------------------------------------------

    def sup(self, **opts: Any) -> Supervisor:
        self.last = Supervisor(
            self.repo,
            options=RunOptions(**opts),
            state_root=self.state_root,
            env=self.env,
            clock=self.clock,
            out=self.out,
            proc_root=self.proc,
            lock_retry_s=0.2,
        )
        return self.last

    def run(self, **opts: Any) -> int:
        return self.sup(**opts).run()

    # --- observations -------------------------------------------------------------------

    def events(self, name: str | None = None) -> list[dict[str, Any]]:
        path = self.state_root / "SMP" / "run.jsonl"
        records = [json.loads(x) for x in path.read_text().splitlines()]
        return [r for r in records if name is None or r["event"] == name]

    def last_event(self, name: str) -> dict[str, Any]:
        return self.events(name)[-1]

    def calls(self, key: str | None = None) -> list[dict[str, Any]]:
        path = Path(f"{self.scenario}.calls.jsonl")
        if not path.exists():
            return []
        rows = [json.loads(x) for x in path.read_text().splitlines()]
        return [r for r in rows if key is None or r["key"] == key]

    def phase_calls(self) -> list[str]:
        return [c["key"] for c in self.calls() if c["key"] not in ("probe", "triage")]

    def status(self, phase: str) -> Status:
        return load_plan(self.repo).phase(phase).status

    def state(self) -> Any:
        return load_state(self.state_root / "SMP")

    def notes(self) -> list[str]:
        assert self.last is not None
        return [n.kind for n in self.last.notifier.sent]


@pytest.fixture
def h(tmp_path: Path, make_repo: RepoFactory) -> Callable[..., H]:
    def factory(**scenario: list[str]) -> H:
        return H(tmp_path, make_repo, scenario)

    return factory


# --------------------------------------------------------------------------- happy path


def test_sample_plan_completes_unattended(h: Callable[..., H]) -> None:
    x = h().all_auto().decide_q1()
    assert x.run() == EXIT_FINISHED
    assert [x.status(p) for p in ("01", "01a", "02")] == [Status.COMPLETE] * 3
    assert x.phase_calls() == ["01", "01a", "02"]
    assert [c["model"] for c in x.calls()] == ["haiku", "haiku", "sonnet"]
    assert all(c["auto"] == "1" and not c["resume"] for c in x.calls())
    selects = x.events("select")
    assert [s["phase"] for s in selects] == ["01", "01a", "02"]
    assert all(s["rule"] == "next_eligible" for s in selects)
    assert [d["rule"] for d in x.events("decision")] == ["complete"] * 3
    end = x.last_event("run_end")
    assert end["status"] == "finished" and end["reason"] == "every phase is ✅ Complete"
    assert end["tokens"] == 3 * 1200 and end["cost_usd"] == pytest.approx(0.03)
    assert x.notes() == ["phase_complete"] * 3 + ["finished"]
    state = x.state()
    assert state.status == RunStatus.FINISHED and state.completed == ["01", "01a", "02"]
    assert state.phases["02"].sessions == 1 and state.pause is None
    assert running(x.repo, x.env) is None  # locks released
    # a second run finds nothing to do
    assert x.run() == EXIT_FINISHED and x.phase_calls() == ["01", "01a", "02"]
    # notify-send got the silent hint
    sent = [json.loads(ln) for ln in (x.tmp / "notify.jsonl").read_text().splitlines()]
    assert all("--hint=boolean:suppress-sound:true" in argv for argv in sent)


def test_vault_summary_appended(h: Callable[..., H], tmp_path: Path) -> None:
    x = h().all_auto().decide_q1()
    note = tmp_path / "vault" / "SMP Implementation Plan.md"
    note.parent.mkdir()
    original = (
        "---\ntags: [x]\nupdated: 2026-01-01 00:00 CDT\n---\n# SMP\n\n"
        "## Log\n- **old:** entry\n\n## Other\nkeep\n"
    )
    note.write_text(original)
    (x.repo / "CLAUDE.md").write_text(f"6. The Obsidian project note `{note}`: update it.\n")
    git(x.repo, "add", "CLAUDE.md")
    git(x.repo, "commit", "-q", "-m", "claude md")
    assert x.run(until="01") == EXIT_FINISHED
    text = note.read_text()
    assert "updated: 2026-01-01" not in text and "\nupdated: 20" in text
    log_part = text.split("## Log")[1].split("## Other")[0]
    assert "- **old:** entry\n- **" in log_part and "PHX run `" in log_part
    assert "01 ✅ complete (1.2k tokens, $0.01, 1 session(s))" in log_part
    assert text.endswith("## Other\nkeep\n") and text.startswith("---\ntags: [x]\n")
    assert x.last_event("vault")["written"] is True


# --------------------------------------------------------------------------- gates and options


def test_review_gates_pause_and_resume(h: Callable[..., H]) -> None:
    x = h().decide_q1()  # 01a: Gate review from its prompt; 02: Gate review in the table
    assert x.run() == EXIT_PAUSED
    assert x.phase_calls() == ["01", "01a"]
    end = x.last_event("run_end")
    assert end["rule"] == "review_gate" and "phase 01a has Gate review (prompt)" in end["reason"]
    assert x.state().pause.rule == "review_gate"
    assert x.notes()[-1] == "paused"
    # `phx run` does not clear a pause
    assert x.run() == EXIT_PAUSED and x.phase_calls() == ["01", "01a"]
    assert "`phx resume` clears the pause" in x.last_event("refused")["reason"]
    assert x.run(resume=True) == EXIT_PAUSED  # runs 02, which is review-gated too
    assert x.phase_calls() == ["01", "01a", "02"]
    assert "pause cleared: phase 01a has Gate review" in x.last_event("resume")["reason"]
    assert x.run(resume=True) == EXIT_FINISHED
    assert x.phase_calls() == ["01", "01a", "02"]


def test_owner_gate_is_never_started(h: Callable[..., H]) -> None:
    x = h()
    x.edit_plan(
        "[SMP_phase-01-hello.md](prompts/SMP_phase-01-hello.md) | auto |",
        "[SMP_phase-01-hello.md](prompts/SMP_phase-01-hello.md) | owner |",
    )
    assert x.run() == EXIT_PAUSED
    assert x.calls() == []
    end = x.last_event("run_end")
    assert end["rule"] == "owner_gate" and "PHX never starts it" in end["reason"]


def test_owner_gate_in_progress_says_finish_it(h: Callable[..., H]) -> None:
    """Phase 10 pilot: an owner phase claimed by hand must not say "PHX never starts it"."""
    x = h()
    x.edit_plan(
        "| 00 | ⬜ Not started | [SMP_phase-01-hello.md](prompts/SMP_phase-01-hello.md) | auto |",
        "| 00 | 🔄 In progress | [SMP_phase-01-hello.md](prompts/SMP_phase-01-hello.md) | owner |",
    )
    assert x.run() == EXIT_PAUSED
    end = x.last_event("run_end")
    assert end["rule"] == "owner_gate" and "is 🔄 In progress" in end["reason"]
    assert "finish it with /phase 01" in end["reason"] and x.calls() == []


def test_waiting_phases_are_summarised(h: Callable[..., H]) -> None:
    """Phase 10 pilot: the pause reason listed every phase waiting on dependencies."""
    x = h().all_auto()
    x.edit_plan(
        "| Favourite colour? | Open. Proposed default: blue | Phase 02 |",
        "| Favourite colour? | Open. Proposed default: blue | Phase 01 |",
    )
    assert x.run() == EXIT_PAUSED
    reason = x.last_event("run_end")["reason"]
    assert reason == (
        "no phase can start (01: open owner question: #1; 2 later phase(s) wait on dependencies)"
    )


def test_session_of_a_phase_finished_by_hand_is_dropped(h: Callable[..., H]) -> None:
    """Phase 10 pilot: 05 was stopped, then finished by hand; its session stayed recorded."""
    from phx.state import RunState

    x = h().all_auto().decide_q1()
    x.sup()  # creates the state dir
    save_state(
        x.state_root / "SMP",
        RunState(run_id="old", repo=str(x.repo), status=RunStatus.STOPPED, sessions={"00": "s"}),
    )
    assert x.run(until="01") == EXIT_FINISHED
    assert x.last_event("session_dropped")["phase"] == "00"
    assert "00" not in x.state().sessions


def test_pause_after(h: Callable[..., H]) -> None:
    x = h().all_auto().decide_q1()
    assert x.run(pause_after="01") == EXIT_PAUSED
    assert x.phase_calls() == ["01"]
    assert x.last_event("run_end")["rule"] == "pause_after"
    assert x.run(resume=True) == EXIT_FINISHED and x.phase_calls() == ["01", "01a", "02"]


def test_max_phases_and_until(h: Callable[..., H]) -> None:
    x = h().all_auto().decide_q1()
    assert x.run(max_phases=1) == EXIT_FINISHED
    assert x.phase_calls() == ["01"] and x.last_event("run_end")["rule"] == "max_phases"
    assert x.run(until="01a") == EXIT_FINISHED
    assert x.phase_calls() == ["01", "01a"] and x.last_event("run_end")["rule"] == "until"


def test_dry_run_spends_nothing(h: Callable[..., H]) -> None:
    x = h().decide_q1()
    assert x.run(dry_run=True) == EXIT_FINISHED
    assert x.calls() == []
    assert not (x.state_root / "SMP" / "state.json").exists()
    assert not list((x.state_root / "SMP" / "sessions").glob("*"))
    out = x.out.getvalue()
    assert "01  Hello file  [haiku, gate auto]" in out and "01a  Inserted phase" in out
    assert "02" not in out.split("Then:")[0].split("01a")[1]
    assert "-p /phase 01 --auto --model haiku --permission-mode bypassPermissions" in out
    assert "Then: paused (phase 01a has Gate review" in out
    event = x.last_event("dry_run")
    assert [s["phase"] for s in event["steps"]] == ["01", "01a"] and event["end"] == "review_gate"
    assert [x.status(p) for p in ("01", "01a")] == [Status.NOT_STARTED] * 2


# --------------------------------------------------------------------------- blocks and answers


def test_block_answer_resume(h: Callable[..., H], monkeypatch: pytest.MonkeyPatch) -> None:
    x = h(**{"01": ["block:5", "complete"]})
    assert x.run(until="01") == EXIT_PAUSED
    assert x.status("01") is Status.BLOCKED
    end = x.last_event("run_end")
    assert end["rule"] == "blocked" and "blocked on owner question #5" in end["reason"]
    assert x.state().pause.question_ids == ["5"]
    assert "favourite colour" in (x.state().pause.summary or "")  # haiku triage
    assert x.notes()[-1] == "blocked" and x.calls("triage")
    assert x.run(resume=True, until="01") == EXIT_PAUSED  # still open: pause again, no launch
    assert x.phase_calls() == ["01"]
    assert "⛔ Blocked on open owner question #5" in x.last_event("run_end")["reason"]

    monkeypatch.setenv("XDG_RUNTIME_DIR", x.env["XDG_RUNTIME_DIR"])
    report = answer_question(x.repo, "5", "green | bright")
    assert report.startswith("answered #5 in ")
    q5 = next(q for q in load_plan(x.repo).questions if q.id == "5")
    assert q5.status.startswith("Answered 20") and q5.status.endswith(": green | bright")
    assert ": green \\| bright |" in (x.repo / PLAN).read_text()  # escaped in the table
    assert git(x.repo, "log", "-1", "--format=%s").strip() == "docs(plan): answer owner question 5"

    assert x.run(resume=True, until="01") == EXIT_FINISHED
    assert x.status("01") is Status.COMPLETE
    assert x.phase_calls() == ["01", "01"] and x.calls("01")[1]["prompt"] == "/phase 01 --auto"
    assert x.last_event("select")["rule"] == "resume_blocked"


def test_open_question_holds_the_next_phase(
    h: Callable[..., H], monkeypatch: pytest.MonkeyPatch
) -> None:
    x = h().all_auto()  # question 1 (needed by 02) is still open
    assert x.run() == EXIT_PAUSED
    assert x.phase_calls() == ["01", "01a"]
    end = x.last_event("run_end")
    assert end["rule"] == "nothing_eligible" and "02: open owner question: #1" in end["reason"]
    monkeypatch.setenv("XDG_RUNTIME_DIR", x.env["XDG_RUNTIME_DIR"])
    answer_question(x.repo, "1", "green")
    assert x.run(resume=True) == EXIT_FINISHED and x.phase_calls() == ["01", "01a", "02"]


def test_answer_refusals(h: Callable[..., H], monkeypatch: pytest.MonkeyPatch) -> None:
    x = h()
    monkeypatch.setenv("XDG_RUNTIME_DIR", x.env["XDG_RUNTIME_DIR"])
    with pytest.raises(ValueError, match="not in the plan"):
        answer_question(x.repo, "7", "x")
    with pytest.raises(ValueError, match="empty"):
        answer_question(x.repo, "1", "  ")
    (x.repo / PLAN).write_text((x.repo / PLAN).read_text() + "\nlocal edit\n")
    with pytest.raises(ValueError, match="uncommitted changes"):
        answer_question(x.repo, "1", "green")
    git(x.repo, "checkout", "--", PLAN)
    with (
        RunLock(x.repo, started="now", env=x.env),
        pytest.raises(ValueError, match="a supervisor is running"),
    ):
        answer_question(x.repo, "1", "green")
    answer_question(x.repo, "1", "green")
    with pytest.raises(ValueError, match="is not open"):
        answer_question(x.repo, "1", "blue")
    assert answer_question(x.repo, "1", "blue", force=True).startswith("answered #1")


def test_refused_session_pauses(h: Callable[..., H]) -> None:
    x = h(**{"01": ["refuse"]})
    assert x.run() == EXIT_PAUSED
    assert x.last_event("run_end")["rule"] == "refused"
    assert x.status("01") is Status.NOT_STARTED


# --------------------------------------------------------------------------- usage limits


def test_usage_limit_with_reset_time(h: Callable[..., H]) -> None:
    x = h(**{"01": ["limit:3600", "complete"], "probe": ["ok"]})
    assert x.run(until="01") == EXIT_FINISHED
    first, second = x.calls("01")
    assert not first["resume"] and second["resume"] and second["session"] == first["session"]
    assert second["prompt"].startswith("Continue phase 01")
    assert len(x.calls("probe")) == 1
    start = x.last_event("wait_start")
    assert "usage limit (five_hour)" in start["reason"] and "reset time" in start["reason"]
    assert start["until_epoch"] == pytest.approx(x.clock.start + 3600 + RESET_MARGIN_S, abs=5)
    assert x.clock.slept >= 3600 + RESET_MARGIN_S - 5
    assert len(x.events("provider_check")) >= 3600 // 300
    assert x.last_event("wait_end")["reason"] == "capacity is back"
    assert [d["rule"] for d in x.events("decision")] == ["usage_limit", "complete"]
    state = x.state()
    assert state.phases["01"].wait_s >= 3600 and state.phases["01"].sessions == 2
    assert state.recoveries == 0 and state.wait is None
    assert "waiting" in x.notes()


def test_usage_limit_without_reset_time_backs_off(h: Callable[..., H]) -> None:
    x = h(**{"01": ["limit", "complete"], "probe": ["limit", "ok"]})
    assert x.run(until="01") == EXIT_FINISHED
    assert "back-off 30 min" in x.last_event("wait_start")["reason"]
    extend = x.last_event("wait_extend")
    assert "back-off 60 min" in extend["reason"] and extend["backoff_step"] == 1
    assert len(x.calls("probe")) == 2
    assert x.clock.slept == pytest.approx(BACKOFF_S[0] + BACKOFF_S[1], abs=1)
    assert x.status("01") is Status.COMPLETE


def test_provider_switch_during_wait_resumes_at_once(h: Callable[..., H]) -> None:
    x = h(**{"01": ["limit:36000", "complete"]})

    def toggle(clock: FakeClock) -> None:
        if clock.slept >= 600:
            x.provider_file.write_text("openrouter\n")

    x.clock.on_sleep = toggle
    assert x.run(until="01") == EXIT_FINISHED
    assert x.calls("probe") == []  # no probe after a provider switch
    assert x.clock.slept < 1000
    switch = x.last_event("provider_switch")
    assert "provider is now openrouter (was anthropic)" in switch["reason"]
    assert "provider_switch" in x.notes()
    assert x.calls("01")[1]["resume"]


def test_probe_auth_error_pauses(h: Callable[..., H]) -> None:
    x = h(**{"01": ["limit:60"], "probe": ["auth"]})
    assert x.run(until="01") == EXIT_PAUSED
    assert x.last_event("run_end")["rule"] == "auth_error"


def test_wait_survives_a_stop_and_continues(h: Callable[..., H]) -> None:
    x = h(**{"01": ["limit:7200", "complete"], "probe": ["ok"]})

    def stop_soon(clock: FakeClock) -> None:
        if clock.slept >= 300 and x.last is not None:
            x.last.request_stop("test stop")

    x.clock.on_sleep = stop_soon
    assert x.run(until="01") == EXIT_STOPPED
    state = x.state()
    assert state.status == RunStatus.STOPPED and state.wait is not None
    assert "continues on the next phx run" in x.last_event("wait_stopped")["reason"]
    x.clock.on_sleep = None
    assert x.run(until="01") == EXIT_FINISHED
    assert x.events("select")[-1]["rule"] == "pending_wait"
    assert x.calls("01")[1]["resume"] and x.status("01") is Status.COMPLETE


# --------------------------------------------------------------------------- crashes and resume


def test_session_crash_resumes_same_session(h: Callable[..., H]) -> None:
    x = h(**{"01": ["crash", "complete"]})
    assert x.run(until="01") == EXIT_FINISHED
    first, second = x.calls("01")
    assert second["resume"] and second["session"] == first["session"]
    assert [d["rule"] for d in x.events("decision")] == ["retry_resume", "complete"]
    assert x.last_event("retry")["recoveries"] == 1


def test_crash_ladder_gives_up(h: Callable[..., H]) -> None:
    x = h(**{"01": ["crash"]})
    assert x.run(until="01") == EXIT_PAUSED
    assert [d["rule"] for d in x.events("decision")] == [
        "retry_resume",
        "retry_fresh",
        "retries_exhausted",
    ]
    assert len(x.calls("01")) == 3


def test_supervisor_crash_resumes_recorded_session(h: Callable[..., H]) -> None:
    x = h(**{"01": ["crash", "complete"]})
    # A supervisor that died mid-phase: the agent claimed 01, state.json says running.
    x.sup()  # creates the state dir
    subprocess.run(
        [sys.executable, str(FAKES / "claude"), "-p", "/phase 01 --auto", "--session-id", "s-1"],
        cwd=x.repo,
        env=x.env,
        capture_output=True,
        check=False,
    )
    assert x.status("01") is Status.IN_PROGRESS
    from phx.state import RunState

    save_state(
        x.state_root / "SMP",
        RunState(
            run_id="old",
            repo=str(x.repo),
            status=RunStatus.RUNNING,
            phase="01",
            sessions={"01": "s-1"},
        ),
    )
    assert x.run(until="01") == EXIT_FINISHED
    assert "ended without cleanup" in x.last_event("previous_run")["reason"]
    sel = x.events("select")[0]
    assert sel["rule"] == "resume_recorded" and sel["resume"] == "s-1"
    assert x.calls("01")[-1]["resume"] and x.calls("01")[-1]["session"] == "s-1"
    assert x.last_event("resume_check")["resumable"] is True


def test_in_progress_without_session_resumes_fresh(h: Callable[..., H]) -> None:
    x = h(**{"01": ["crash", "complete"]})
    subprocess.run(
        [sys.executable, str(FAKES / "claude"), "-p", "/phase 01 --auto", "--session-id", "s-1"],
        cwd=x.repo,
        env=x.env,
        capture_output=True,
        check=False,
    )
    assert x.run(until="01") == EXIT_FINISHED
    assert x.events("select")[0]["rule"] == "resume_fresh"
    assert x.calls("01")[1]["prompt"] == "/phase 01 --auto" and not x.calls("01")[1]["resume"]


def test_live_session_blocks_resume(h: Callable[..., H]) -> None:
    x = h(**{"01": ["crash"]})
    subprocess.run(
        [sys.executable, str(FAKES / "claude"), "-p", "/phase 01 --auto", "--session-id", "s-1"],
        cwd=x.repo,
        env=x.env,
        capture_output=True,
        check=False,
    )
    fake = x.proc / "4242"
    fake.mkdir()
    (fake / "comm").write_text("claude\n")
    (fake / "cmdline").write_text("claude\0--resume\0")
    (fake / "cwd").symlink_to(x.repo)
    assert x.run() == EXIT_PAUSED
    end = x.last_event("run_end")
    assert end["rule"] == "live_session" and "pid 4242" in end["reason"]
    assert len(x.calls("01")) == 1  # only the setup call


# --------------------------------------------------------------------------- locks and stop


def test_lock_contention(h: Callable[..., H], tmp_path: Path, make_repo: RepoFactory) -> None:
    x = h()
    with RunLock(x.repo, started="now", env=x.env):
        assert x.run() == EXIT_ERROR
    assert x.calls() == []
    assert "another phx supervisor holds" in x.last_event("lock_busy")["reason"]
    other = make_repo("sample", name="work/OTHER")
    with RunLock(other, started="now", env=x.env):  # machine-wide: one supervisor at a time
        assert x.run() == EXIT_ERROR
    assert "machine-wide" in x.last_event("lock_busy")["reason"]


def test_stop_mid_phase_leaves_it_resumable(h: Callable[..., H]) -> None:
    x = h(**{"01": ["hang", "complete"]})
    sup = x.sup(until="01")
    codes: list[int] = []
    thread = threading.Thread(target=lambda: codes.append(sup.run()))
    thread.start()
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and not (
        x.calls("01") and x.status("01") is Status.IN_PROGRESS
    ):
        time.sleep(0.05)
    holder = running(x.repo, x.env)
    assert holder is not None and holder.phase == "01" and holder.pid == os.getpid()
    sup.request_stop("test stop")
    thread.join(30)
    assert codes == [EXIT_STOPPED]
    assert x.status("01") is Status.IN_PROGRESS
    state = x.state()
    session = x.calls("01")[0]["session"]
    assert state.status == RunStatus.STOPPED and state.sessions["01"] == session
    assert x.last_event("stop")["reason"].startswith("stop requested")
    assert "stays 🔄 and resumes with session" in x.last_event("run_end")["reason"]
    assert running(x.repo, x.env) is None
    assert x.run(until="01") == EXIT_FINISHED
    assert x.calls("01")[1]["resume"] and x.calls("01")[1]["session"] == session


def test_phx_stop_command_against_a_real_process(
    h: Callable[..., H], monkeypatch: pytest.MonkeyPatch
) -> None:
    x = h(**{"01": ["hang"]})
    env = dict(x.env, PYTHONPATH=str(SRC))
    proc = subprocess.Popen(
        [sys.executable, "-m", "phx", "--state-dir", str(x.state_root), "run", str(x.repo)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            holder = running(x.repo, x.env)
            if holder and holder.phase == "01" and x.calls("01"):
                break
            time.sleep(0.1)
        else:
            pytest.fail("supervisor did not start phase 01")
        # the contract's shell check (§8) sees the lock held by locks.py
        check = subprocess.run(
            ["bash", "-c", CONTRACT_CHECK],
            cwd=x.repo,
            env=x.env,
            capture_output=True,
            text=True,
            check=False,
        )
        line = check.stdout.strip()
        assert line.startswith("PHX-RUNNING {")
        body = json.loads(line.removeprefix("PHX-RUNNING "))
        assert body["pid"] == proc.pid and body["phase"] == "01" and body["repo"] == str(x.repo)
        from phx.cli import main

        monkeypatch.setenv("XDG_RUNTIME_DIR", x.env["XDG_RUNTIME_DIR"])
        assert main(["--state-dir", str(x.state_root), "stop", str(x.repo), "--timeout", "30"]) == 0
        assert proc.wait(30) == EXIT_STOPPED
    finally:
        if proc.poll() is None:
            proc.kill()
    assert "received SIGTERM" in x.last_event("run_end")["reason"]
    assert x.status("01") is Status.IN_PROGRESS
    # after the stop the lock file is stale: the shell check prints nothing
    check = subprocess.run(
        ["bash", "-c", CONTRACT_CHECK + "; echo done"],
        env=x.env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert "PHX-RUNNING" not in check.stdout and check.stdout.strip().endswith("done")


def test_unexpected_error_is_logged_and_ends_the_run(
    h: Callable[..., H], monkeypatch: pytest.MonkeyPatch
) -> None:
    x = h()

    def boom(*_a: Any, **_k: Any) -> Any:
        raise OSError("disk full")

    monkeypatch.setattr("phx.supervisor.capture_baseline", boom)
    assert x.run() == EXIT_ERROR
    assert "OSError: disk full" in x.last_event("supervisor_error")["reason"]
    assert x.last_event("run_end")["rule"] == "supervisor_error"
    assert x.state().status == RunStatus.FAILED and running(x.repo, x.env) is None


def test_limit_before_claim_wait_survives_restart(h: Callable[..., H]) -> None:
    x = h(**{"probe": ["ok"]})
    from phx.state import RunState, Wait

    save_state(
        x.state_root / "SMP",
        RunState(
            run_id="old",
            repo=str(x.repo),
            status=RunStatus.WAITING,
            phase="01",
            wait=Wait("01", "s-0", "Continue phase 01", x.clock.now() + 600, "limit"),
        ),
    )
    assert x.run(until="01") == EXIT_FINISHED
    assert x.events("select")[0]["rule"] == "pending_wait"
    assert x.calls("01")[0]["resume"] and x.calls("01")[0]["session"] == "s-0"
    assert x.clock.slept >= 600


# --------------------------------------------------------------------------- refusals


def test_repo_outside_work_root_refused(h: Callable[..., H]) -> None:
    x = h()
    x.env["PHX_WORK_ROOT"] = str(x.tmp / "elsewhere")
    assert x.run() == EXIT_ERROR
    assert "outside" in x.last_event("refused")["reason"] and x.calls() == []


def test_unmigrated_repo_fails(h: Callable[..., H]) -> None:
    x = h()
    (x.repo / ".claude" / "commands" / "phase.md").write_text("no contract\n")
    git(x.repo, "commit", "-q", "-am", "drop contract")
    assert x.run() == EXIT_ERROR
    end = x.last_event("run_end")
    assert end["rule"] == "contract" and "not yet migrated" in end["reason"]
    assert x.calls() == []


# --------------------------------------------------------------------------- preflight (Phase 08)


def test_missing_preflight_warns_and_runs(h: Callable[..., H]) -> None:
    x = h().all_auto().decide_q1()
    assert x.run() == EXIT_FINISHED
    (warn,) = [w for w in x.events("warning") if w.get("rule") == "preflight_missing"]
    assert "no preflight recorded" in warn["reason"] and "phx preflight" in warn["reason"]
    assert "phx: warning: no preflight recorded" in x.out.getvalue()
    # the run finished, so a second run has nothing left to check
    assert x.run() == EXIT_FINISHED
    assert len([w for w in x.events("warning") if w.get("rule") == "preflight_missing"]) == 1


def test_require_preflight_refuses_before_any_launch(h: Callable[..., H]) -> None:
    x = h().all_auto().decide_q1()
    assert x.run(require_preflight=True) == EXIT_ERROR
    end = x.last_event("run_end")
    assert end["rule"] == "preflight_missing" and "--require-preflight" in end["reason"]
    assert x.phase_calls() == [] and x.state().pause is None


def test_fresh_preflight_then_stale_after_a_phase_is_added(h: Callable[..., H]) -> None:
    from phx.preflight import record

    x = h().all_auto().decide_q1()
    record(x.repo, env=x.env)
    assert x.run(require_preflight=True, max_phases=1) == EXIT_FINISHED
    assert x.last_event("preflight")["reason"].endswith("covers the plan")
    assert not [w for w in x.events("warning") if str(w.get("rule")).startswith("preflight")]
    # phase 01 completed: still fresh; a new row makes it stale
    x.edit_plan(
        "(prompts/SMP_phase-02-colour.md) | auto |",
        "(prompts/SMP_phase-02-colour.md) | auto |\n"
        "| 03 | Added | x | Haiku 5.5 | 02 | ⬜ Not started | n/a | auto |",
    )
    assert x.run(require_preflight=True) == EXIT_ERROR
    end = x.last_event("run_end")
    assert end["rule"] == "preflight_stale" and "phase(s) added: 03" in end["reason"]
    assert x.phase_calls() == ["01"]


def test_dry_run_reports_preflight(h: Callable[..., H]) -> None:
    x = h().all_auto().decide_q1()
    assert x.run(dry_run=True) == EXIT_FINISHED
    assert "phx: warning: no preflight recorded" in x.out.getvalue()
    assert x.run(dry_run=True, require_preflight=True) == EXIT_ERROR
    assert "would refuse: no preflight recorded" in x.out.getvalue()
    assert x.last_event("dry_run")["end"] == "preflight_missing"
