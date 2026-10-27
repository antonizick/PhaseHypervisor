"""Every row of the Phase 06 decision table, end to end with the Phase 05 fakes.

Each scenario builds a throwaway repo in the state a phase session would leave, runs a
real ``run_session`` against the fake ``claude`` replaying a stream fixture, then calls
``handle_outcome`` and asserts both the action and the reason logged in ``run.jsonl``.
"""

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

import pytest

from phx.classify import Classification, ExitClass
from phx.logging import EventLog
from phx.paths import Config
from phx.plan import load_live
from phx.recover import (
    MAX_RECOVERIES,
    Action,
    LiveProcess,
    check_resumable,
    continue_prompt,
    decide,
    find_claude_processes,
    handle_outcome,
    last_session_end,
    live_sessions,
    phase_activity,
    phase_prompt,
    repair_blocked,
)
from phx.runner import SessionOutcome, Timeouts, run_session
from phx.verify import Outcome
from scenarios import BLOCKED_LOG, BRANCH, OPEN, PLAN, Scenario, git, render

TESTS = Path(__file__).resolve().parent
FAKES = TESTS / "fakes"
STREAMS = TESTS / "fixtures" / "streams"


class Env:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.sc = Scenario(tmp_path)
        self.state = tmp_path / "state"
        self.log = EventLog(self.state / "run.jsonl")
        self.proc = tmp_path / "proc"  # an empty fake /proc: no live sessions
        self.proc.mkdir()
        self.base = {
            "PATH": f"{FAKES}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(tmp_path / "home"),
            "PHX_FAKE_ARGV_LOG": str(tmp_path / "argv.jsonl"),
        }

    def session(self, stream: str | None, **extra: str) -> SessionOutcome:
        env = dict(self.base, **extra)
        if stream:
            env["PHX_FAKE_STREAM"] = str(STREAMS / stream)
        return run_session(
            repo=self.sc.repo,
            state=self.state,
            phase="05",
            prompt="/phase 05 --auto",
            alias="haiku",
            log=self.log,
            env=env,
            timeouts=Timeouts(idle_s=0.5, wall_s=10, term_grace_s=0.5),
        )

    def handle(self, outcome: SessionOutcome, **kw: Any) -> Any:
        kw.setdefault("env", dict(self.base, PHX_FAKE_STREAM=str(STREAMS / "triage.jsonl")))
        kw.setdefault("proc_root", self.proc)
        return handle_outcome(self.sc.repo, outcome, state=self.state, log=self.log, **kw)

    def events(self, name: str | None = None) -> list[dict[str, Any]]:
        lines = (self.state / "run.jsonl").read_text().splitlines()
        records = [json.loads(x) for x in lines]
        return [r for r in records if name is None or r["event"] == name]

    def decision_log(self) -> dict[str, Any]:
        (record,) = self.events("decision")
        return record


@pytest.fixture
def e(tmp_path: Path) -> Env:
    return Env(tmp_path)


def assert_logged(e: Env, decision: Any, action: Action, rule: str, reason: str) -> None:
    assert decision.action is action
    assert decision.rule == rule
    assert reason in decision.reason
    record = e.decision_log()
    assert record["action"] == str(action) and record["rule"] == rule
    assert reason in record["reason"]


# --- complete -------------------------------------------------------------------------


def test_row_complete_verified_next_phase(e: Env) -> None:
    e.sc.claim().work().complete()
    d = e.handle(e.session("complete.jsonl"))
    assert_logged(e, d, Action.NEXT_PHASE, "complete", "phase 05 complete and verified")
    assert d.notify and d.summary is None
    assert e.events("verify")[0]["outcome"] == "complete"
    assert not e.events("triage")  # triage only on blocks and failures


# --- blocked ----------------------------------------------------------------------------


def test_row_blocked_question_recorded_pause_with_triage(e: Env) -> None:
    e.sc.claim().block()
    head = e.sc.head()
    d = e.handle(e.session("blocked.jsonl"))
    assert_logged(e, d, Action.PAUSE, "blocked", "phase 05 blocked on owner question #6")
    assert d.notify and d.question_ids == ("6",) and d.repair is None
    assert e.sc.head() == head  # nothing to repair: ⛔ already on main
    assert d.summary and "favourite colour" in d.summary
    (triage,) = e.events("triage")
    assert triage["cost_usd"] == pytest.approx(0.0009) and triage["summary"] == d.summary
    assert e.decision_log()["summary"] == d.summary
    # the triage session was tool-less, one turn, haiku, outside the repo, not hands-off
    calls = [json.loads(x) for x in (e.tmp / "argv.jsonl").read_text().splitlines()]
    argv, env, cwd = calls[-1]["argv"], calls[-1]["env"], calls[-1]["cwd"]
    assert argv[argv.index("--tools") + 1] == "" and argv[argv.index("--max-turns") + 1] == "1"
    assert argv[argv.index("--model") + 1] == "haiku"
    assert argv[argv.index("--permission-mode") + 1] == "default"
    assert env["PHX_AUTO"] is None and Path(cwd) == e.state


def test_row_blocked_triage_off(e: Env) -> None:
    e.sc.claim().block()
    d = e.handle(e.session("blocked.jsonl"), config=Config(triage=False))
    assert d.action is Action.PAUSE and d.summary is None and not e.events("triage")


def test_repair_blocked_from_result_line(e: Env) -> None:
    """The agent blocked (result line) but committed neither ⛔ nor the question to main."""
    e.sc.claim().wip_blocked()
    before = e.sc.head()
    d = e.handle(e.session("blocked.jsonl"))
    (repair,) = e.events("repair")
    assert repair["reason"] == "committed ⛔ Blocked to main (recorded by phx)"
    assert repair["evidence"] == "result line says blocked" and d.repair == repair["commit"]
    assert (
        git(e.sc.repo, "log", "-1", "--format=%s")
        == "chore(plan): phase 05 blocked (recorded by phx)"
    )
    assert git(e.sc.repo, "rev-parse", "HEAD~1") == before
    assert git(e.sc.repo, "show", "--name-only", "--format=", "HEAD") == PLAN
    diff = git(e.sc.repo, "diff", "HEAD~1", "HEAD", "--unified=0")
    assert diff.count("\n-|") == 1 and "+| 05 | Thing |" in diff and "⛔ Blocked" in diff
    assert git(e.sc.repo, "status", "--porcelain") == ""
    # ⛔ now on main, but no question was recorded: pause for Nick with a report
    assert d.action is Action.PAUSE and d.rule == "needs_review"
    assert "agent named question(s) #6, which are not open" in d.reason
    assert d.summary  # triage ran for needs_review


def test_repair_blocked_from_wip_commit_after_crash(e: Env) -> None:
    e.sc.claim().wip_blocked()
    # the agent recorded the question on main but died before committing ⛔
    e.sc.write_plan(
        e.sc.repo,
        render("🔄 In progress", question=OPEN, log=BLOCKED_LOG),
        "docs(plan): question 6",
    )
    d = e.handle(e.session("truncated.jsonl"))
    (repair,) = e.events("repair")
    assert "wip(phase-05): blocked commit" in repair["evidence"]
    assert_logged(e, d, Action.PAUSE, "blocked", "blocked on owner question #6")


def test_repair_pushes_when_a_remote_exists(e: Env, tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(e.sc.repo, "remote", "add", "origin", str(remote))
    e.sc.claim().wip_blocked()
    sha = repair_blocked(e.sc.repo, "05", evidence="test", log=e.log)
    assert sha and git(remote, "rev-parse", "main") == sha
    assert e.events("repair")[0]["push"] == "pushed"


@pytest.mark.parametrize(
    ("setup", "reason"),
    [
        ("dirty", "has uncommitted changes in the main checkout"),
        ("off-main", "not main"),
        ("not-claimed", "row is not 🔄 In progress"),
        ("unknown", "plan unreadable"),
    ],
)
def test_repair_skipped_when_unsafe(e: Env, setup: str, reason: str) -> None:
    phase = "05"
    if setup != "not-claimed":
        e.sc.claim().wip_blocked()
    if setup == "dirty":
        (e.sc.repo / PLAN).write_text(render("⛔ Blocked"))  # the agent's uncommitted edit
    elif setup == "off-main":
        git(e.sc.repo, "checkout", "-q", "-b", "elsewhere")
    elif setup == "unknown":
        phase = "42"
    head = e.sc.head()
    assert repair_blocked(e.sc.repo, phase, evidence="test", log=e.log) is None
    (skipped,) = e.events("repair_skipped")
    assert reason in skipped["reason"]
    assert e.sc.head() == head


def test_repair_skipped_when_checkout_differs_from_main(e: Env) -> None:
    e.sc.claim()
    git(e.sc.repo, "update-index", "--assume-unchanged", PLAN)
    (e.sc.repo / PLAN).write_text("hidden edit\n")
    assert repair_blocked(e.sc.repo, "05", evidence="test", log=e.log) is None
    assert "differs from main" in e.events("repair_skipped")[0]["reason"]


# --- refused ----------------------------------------------------------------------------


def test_row_refused_pause_no_repair(e: Env) -> None:
    head = e.sc.head()
    d = e.handle(e.session("refused.jsonl"), baseline=None)
    assert_logged(e, d, Action.PAUSE, "refused", "dependency 04 not complete; nothing repaired")
    assert not e.events("repair") and e.sc.head() == head and d.summary is None


# --- no_result ----------------------------------------------------------------------------


def test_row_no_result_repo_complete(e: Env) -> None:
    e.sc.claim().work().complete()
    d = e.handle(e.session("no_result.jsonl"))
    assert_logged(
        e, d, Action.NEXT_PHASE, "complete", "complete and verified (session ended as no_result)"
    )


def test_row_no_result_repo_blocked(e: Env) -> None:
    e.sc.claim().block()
    d = e.handle(e.session("no_result.jsonl"))
    assert_logged(e, d, Action.PAUSE, "blocked", "blocked on owner question #6")


def test_row_no_result_work_in_progress(e: Env) -> None:
    e.sc.claim().work()
    out = e.session("no_result.jsonl")
    d = e.handle(out)
    assert_logged(e, d, Action.RESUME_SESSION, "retry_resume", "resuming the same session")
    assert d.session_id == out.session_id and d.prompt == continue_prompt("05")


def test_row_no_result_unclaimed(e: Env) -> None:
    d = e.handle(e.session("no_result.jsonl"))
    assert_logged(e, d, Action.PAUSE, "no_result_unclaimed", "without claiming the phase")


# --- usage limit ----------------------------------------------------------------------------


def test_row_usage_limit_wait_then_resume(e: Env) -> None:
    e.sc.claim().work()
    out = e.session("usage_limit_session.jsonl")
    d = e.handle(out)
    assert_logged(e, d, Action.WAIT, "usage_limit", "wait, then resume the same session")
    assert d.reset_at is not None and d.session_id == out.session_id
    assert d.prompt == continue_prompt("05")
    assert e.decision_log()["reset_at"] == d.reset_at.isoformat()


def test_usage_limit_after_the_phase_completed(e: Env) -> None:
    e.sc.claim().work().complete()
    d = e.handle(e.session("usage_limit_session.jsonl"))
    assert d.action is Action.NEXT_PHASE and "session ended as usage_limit" in d.reason


# --- timeout / crash ladder -------------------------------------------------------------------


def test_row_timeout_resume_then_fresh_then_pause(e: Env) -> None:
    e.sc.claim().work(commit=False)
    out = e.session("complete.jsonl", PHX_FAKE_HANG="5")  # stream ends, process hangs: idle timeout
    assert out.classification.cls is ExitClass.TIMEOUT
    d = e.handle(out)
    assert_logged(e, d, Action.RESUME_SESSION, "retry_resume", "session ended as timeout")
    assert d.session_id == out.session_id

    d = decide("05", out.classification, d.verdict, session_id=out.session_id, recoveries=1)
    assert d.action is Action.FRESH_SESSION and d.rule == "retry_fresh"
    assert d.prompt == phase_prompt("05") == "/phase 05 --auto" and d.session_id is None

    d = decide(
        "05", out.classification, d.verdict, session_id=out.session_id, recoveries=MAX_RECOVERIES
    )
    assert d.action is Action.PAUSE and d.rule == "retries_exhausted" and d.notify


@pytest.mark.parametrize("recoveries", [1, 2])
def test_row_crash_ladder_logged(e: Env, recoveries: int) -> None:
    e.sc.claim().work()
    d = e.handle(e.session("truncated.jsonl"), recoveries=recoveries)
    if recoveries == 1:
        assert_logged(
            e, d, Action.FRESH_SESSION, "retry_fresh", "starting a fresh /phase 05 --auto"
        )
    else:
        assert_logged(e, d, Action.PAUSE, "retries_exhausted", "giving up")
    assert e.decision_log()["recoveries"] == recoveries


def test_crash_before_claim_retries(e: Env) -> None:
    d = e.handle(e.session("truncated.jsonl"))
    assert d.action is Action.RESUME_SESSION  # nothing claimed yet; the same session may finish


def test_crash_with_live_session_pauses(e: Env, tmp_path: Path) -> None:
    e.sc.claim().work()
    fake_proc(e.proc, 4242, comm="claude", argv=["claude", "-n", "x"], cwd=e.sc.worktree)
    d = e.handle(e.session("truncated.jsonl"))
    assert_logged(
        e, d, Action.PAUSE, "live_session", "another session is running phase 05 (pid 4242"
    )
    assert e.decision_log()["live"][0]["pid"] == 4242


# --- auth / provider -----------------------------------------------------------------------------


def test_row_auth_error_pause_no_verify(e: Env) -> None:
    e.sc.claim().work()
    d = e.handle(e.session("auth_expired.jsonl"))
    assert_logged(e, d, Action.PAUSE, "auth_error", "authentication failed")
    assert d.verdict is None and not e.events("verify") and not e.events("triage")


def test_row_provider_error_pause_no_retry(e: Env) -> None:
    e.sc.claim().work()
    d = e.handle(e.session("openrouter_402.jsonl", PHX_FAKE_PROVIDER="openrouter"))
    assert_logged(e, d, Action.PAUSE, "provider_error", "provider error (credits)")
    assert "no retry that could spend credit" in d.reason and not e.events("verify")


# --- verification failed / needs review --------------------------------------------------------


def test_row_verification_failed_pause_with_report(e: Env) -> None:
    e.sc.claim().complete()  # ✅ merged, but hello.txt was never written: tests fail
    d = e.handle(e.session("complete.jsonl"))
    assert_logged(e, d, Action.PAUSE, "verification_failed", "verification failed: tests")
    assert d.verdict.outcome is Outcome.FAILED and d.summary
    verify = e.events("verify")[0]
    assert any(c["name"] == "tests" and c["status"] == "fail" for c in verify["checks"])


def test_row_needs_review_both_shown(e: Env) -> None:
    e.sc.claim().work()  # agent says complete, row still 🔄
    d = e.handle(e.session("complete.jsonl"))
    assert_logged(e, d, Action.PAUSE, "needs_review", "agent said complete, repo shows in_progress")
    assert "agent said: complete (all checks passed)" in d.verdict.report()


def test_unverifiable_and_unexpected() -> None:
    limit = Classification(ExitClass.USAGE_LIMIT, "limit")
    d = decide("05", limit, None)
    assert d.action is Action.PAUSE and d.rule == "unverified"


def test_verification_never_touches_main_checkout(e: Env) -> None:
    """Acceptance: only the documented ⛔ repair writes to the main checkout."""
    e.sc.claim().work().complete()
    (e.sc.repo / "scratch.txt").write_text("mine\n")
    from phx.verify import capture_baseline

    base = capture_baseline(e.sc.repo)
    snap = (e.sc.head(), git(e.sc.repo, "status", "--porcelain"), (e.sc.repo / PLAN).read_text())
    d = e.handle(e.session("complete.jsonl"), baseline=base)
    assert d.action is Action.NEXT_PHASE
    assert snap == (
        e.sc.head(),
        git(e.sc.repo, "status", "--porcelain"),
        (e.sc.repo / PLAN).read_text(),
    )
    assert git(e.sc.repo, "worktree", "list").count("\n") == 0 and BRANCH not in git(
        e.sc.repo, "branch"
    )


# --- live-process detection (mocked /proc) ------------------------------------------------------


def fake_proc(
    root: Path,
    pid: int,
    *,
    comm: str,
    argv: list[str],
    cwd: Path | None,
    ppid: int = 1,
    started: float | None = None,
) -> None:
    d = root / str(pid)
    d.mkdir(parents=True)
    (d / "comm").write_text(comm + "\n")
    (d / "cmdline").write_text("\0".join(argv) + "\0")
    if started is None:
        (d / "stat").write_text(f"{pid} ({comm}) S {ppid} 0 0\n")
    else:  # starttime is field 22: ticks after the boot time in <root>/stat
        btime = int(started) - 1000
        (root / "stat").write_text(f"cpu  1 2 3\nbtime {btime}\n")
        ticks = round((started - btime) * os.sysconf("SC_CLK_TCK"))
        rest = " ".join(["0"] * 15)
        (d / "stat").write_text(f"{pid} ({comm}) S {ppid} 0 0 {rest} {ticks} 0 0\n")
    if cwd is not None:
        (d / "cwd").symlink_to(cwd)


def test_find_claude_processes(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    work = tmp_path / "work"
    (work / "sub").mkdir(parents=True)
    other = tmp_path / "other"
    other.mkdir()
    fake_proc(proc, 10, comm="claude", argv=["/x/claude", "-n", "s"], cwd=work / "sub")
    fake_proc(proc, 11, comm="bash", argv=["bash"], cwd=work)
    fake_proc(proc, 12, comm="claude", argv=["claude"], cwd=other)
    fake_proc(proc, 13, comm="claude", argv=["claude"], cwd=None)  # cwd unreadable
    fake_proc(proc, 14, comm="node", argv=["node", "/usr/lib/claude-code/cli.js"], cwd=work)
    fake_proc(proc, 15, comm="MainThread", argv=["/opt/claude", "--resume", "x"], cwd=work)
    (proc / "self").mkdir()
    found = find_claude_processes({str(work): "worktree"}, proc_root=proc, exclude=())
    assert [p.pid for p in found] == [10, 14, 15]
    assert found[0].where == "worktree" and found[0].cwd == str(work / "sub")
    assert (
        find_claude_processes({str(work): "worktree"}, proc_root=proc, exclude={10, 14})[0].pid
        == 15
    )
    assert find_claude_processes({str(work): "w"}, proc_root=tmp_path / "missing") == []


def test_own_ancestors_are_not_rivals(tmp_path: Path) -> None:
    """`phx` started from inside a Claude Code session must not pause on its own parent."""
    proc = tmp_path / "proc"
    work = tmp_path / "work"
    work.mkdir()
    fake_proc(proc, 500, comm="claude", argv=["claude"], cwd=work)
    fake_proc(proc, os.getpid(), comm="python3", argv=["python3"], cwd=work, ppid=500)
    assert find_claude_processes({str(work): "main checkout"}, proc_root=proc) == []


def test_live_sessions_and_check_resumable(e: Env) -> None:
    e.sc.claim().work(commit=False)
    assert check_resumable(e.sc.repo, "05", proc_root=e.proc, exclude=()).resumable
    fake_proc(e.proc, 77, comm="claude", argv=["claude"], cwd=e.sc.repo)
    r = check_resumable(e.sc.repo, "05", proc_root=e.proc, exclude=())
    assert not r.resumable and "open in the main checkout; it may be running phase 05" in r.reason
    fake_proc(e.proc, 78, comm="claude", argv=["claude"], cwd=e.sc.worktree)
    live = live_sessions(e.sc.repo, "05", proc_root=e.proc, exclude=())
    assert [p.where for p in live] == ["worktree", "main checkout"]
    r = check_resumable(e.sc.repo, "05", proc_root=e.proc, exclude=())
    assert r.reason.startswith("another session is running phase 05 (pid 78")


def test_pty_host_and_start_time(tmp_path: Path) -> None:
    """Phase 10 pilot: a `claude bg-pty-host` wrapper is not a session; start time is read."""
    proc = tmp_path / "proc"
    work = tmp_path / "work"
    work.mkdir()
    host = ["claude bg-pty-host", "--bg-pty-host", "/tmp/x.sock", "124", "60", "--", "/x/claude"]
    fake_proc(proc, 20, comm="claude", argv=host, cwd=work)  # real 2.1.310 cmdline
    fake_proc(proc, 23, comm="claude", argv=["claude", "bg-pty-host", "/s"], cwd=work)
    fake_proc(proc, 21, comm="claude", argv=["claude"], cwd=work, started=1_800_000_000.0)
    fake_proc(proc, 22, comm="claude", argv=["claude", "-p", "/phase 05 --auto"], cwd=work)
    found = find_claude_processes({str(work): "main checkout"}, proc_root=proc, exclude=())
    assert [p.pid for p in found] == [21, 22]
    assert found[0].started == pytest.approx(1_800_000_000.0, abs=0.02)
    assert not found[0].headless and found[1].headless and found[1].started is None


def test_idle_main_checkout_session_is_not_a_rival(e: Env) -> None:
    """Phase 10 pilot: Nick's idle Claude Code in the main checkout blocked every resume."""
    e.sc.claim().work(commit=False)
    now = time.time()
    fake_proc(e.proc, 81, comm="claude", argv=["claude"], cwd=e.sc.repo, started=now + 60)
    r = check_resumable(e.sc.repo, "05", proc_root=e.proc, exclude=())
    assert r.resumable and "ignored idle session(s) in the main checkout, pid 81" in r.reason
    # PHX's own last session ended after the work: an older session is idle too.
    shutil.rmtree(e.proc)
    fake_proc(e.proc, 82, comm="claude", argv=["claude"], cwd=e.sc.repo, started=now - 600)
    assert not check_resumable(e.sc.repo, "05", proc_root=e.proc, exclude=()).resumable
    assert check_resumable(e.sc.repo, "05", since=now + 60, proc_root=e.proc, exclude=()).resumable
    # Work after both: a manual /phase 05 in that session. It counts.
    (e.sc.worktree / "later.txt").write_text("x")
    os.utime(e.sc.worktree / "later.txt", (now + 120, now + 120))
    r = check_resumable(e.sc.repo, "05", since=now + 60, proc_root=e.proc, exclude=())
    assert not r.resumable and "open in the main checkout" in r.reason
    # A headless phase session in the main checkout always counts.
    shutil.rmtree(e.proc)
    argv = ["claude", "-p", "/phase 05 --auto"]
    fake_proc(e.proc, 83, comm="claude", argv=argv, cwd=e.sc.repo, started=now + 600)
    assert not check_resumable(
        e.sc.repo, "05", since=now + 600, proc_root=e.proc, exclude=()
    ).resumable


def test_claim_commit_alone_counts_as_activity(e: Env) -> None:
    """ADR-0019 review (Phase 11): a hand claim with no branch or file yet is still seen."""
    now = time.time()
    fake_proc(e.proc, 91, comm="claude", argv=["claude"], cwd=e.sc.repo, started=now - 600)
    e.sc.write_plan(e.sc.repo, render("🔄 In progress"), "chore(plan): start phase 05")
    assert load_live(e.sc.repo).for_phase("05") == ([], [])  # no branch, no worktree yet
    assert phase_activity(e.sc.repo, "05") == pytest.approx(now, abs=5)
    r = check_resumable(e.sc.repo, "05", proc_root=e.proc, exclude=())
    assert not r.resumable and "pid 91" in r.reason
    # a session started after the claim (Nick opening Claude Code to look) is not a rival
    shutil.rmtree(e.proc)
    fake_proc(e.proc, 92, comm="claude", argv=["claude"], cwd=e.sc.repo, started=now + 60)
    assert check_resumable(e.sc.repo, "05", proc_root=e.proc, exclude=()).resumable
    # another phase's claim commit is not this phase's activity
    assert phase_activity(e.sc.repo, "5") is None and phase_activity(e.sc.repo, "05a") is None


def test_last_session_end(tmp_path: Path) -> None:
    assert last_session_end(tmp_path, "05") is None
    (tmp_path / "sessions").mkdir()
    for n, t in ((1, 100.0), (2, 300.0)):
        f = tmp_path / "sessions" / f"05-{n}.jsonl"
        f.write_text("")
        os.utime(f, (t, t))
    (tmp_path / "sessions" / "05a-1.jsonl").write_text("")
    assert last_session_end(tmp_path, "05") == 300.0


def test_decide_live_in_main_checkout_reason() -> None:
    crash = Classification(ExitClass.CRASH, "no result event")
    from phx.verify import RepoState, Verdict

    v = Verdict("05", RepoState.IN_PROGRESS, Outcome.IN_PROGRESS, ())
    d = decide("05", crash, v, live=[LiveProcess(9, "/r", "claude", "main checkout")])
    assert d.rule == "live_session" and "open in the main checkout" in d.reason
    d = decide("05", crash, v, session_id=None)
    assert d.action is Action.FRESH_SESSION  # no session ID to resume


def test_custom_triage_function(e: Env) -> None:
    e.sc.claim().block()
    calls: list[dict[str, Any]] = []

    def fake(**kw: Any) -> Any:
        calls.append(kw)
        return None  # no summary

    d = e.handle(e.session("blocked.jsonl"), triage=fake)
    assert calls and calls[0]["phase"] == "05" and calls[0]["verdict"] is d.verdict
    assert d.action is Action.PAUSE and d.summary is None
