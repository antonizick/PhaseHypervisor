"""What to do after a phase session ends (spec R6, R9, R14; contract §4, §6).

:func:`handle_outcome` is the one entry point the supervisor (Phase 07) calls with a
:class:`phx.runner.SessionOutcome`: it repairs a missing ``⛔`` commit (the only repair
PHX makes), verifies the phase (:mod:`phx.verify`), applies the decision table in
:func:`decide`, asks for a triage summary when Nick will need one, and logs every step.
The decision table is documented in ``docs/PHX_ARCHITECTURE.md``.
"""

import os
import subprocess
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from phx.classify import Classification, ExitClass
from phx.logging import EventLog
from phx.paths import Config, sessions_dir
from phx.plan import MAIN, PlanError, Status, load_live, load_plan, set_status_cell, show_main
from phx.runner import SessionOutcome
from phx.verify import Baseline, Outcome, Verdict, verify_phase, wip_blocked

MAX_RECOVERIES = 2  # timeout/crash: one --resume of the same session, then one fresh session
BLOCKED_LABEL = "⛔ Blocked"
PUSH_TIMEOUT_S = 120


def phase_prompt(phase_id: str) -> str:
    return f"/phase {phase_id} --auto"


def continue_prompt(phase_id: str) -> str:
    """The prompt for ``--resume`` of an interrupted phase session."""
    return (
        f"Continue phase {phase_id} from where you stopped. Hands-off mode is still on "
        f"(PHX_AUTO=1): follow the /phase {phase_id} --auto rules, finish the close-out "
        "checklist, and end your final message with the PHX-RESULT line."
    )


class Action(StrEnum):
    NEXT_PHASE = "next_phase"
    PAUSE = "pause"
    WAIT = "wait"  # usage limit: Phase 07 waits, then --resume of the same session
    RESUME_SESSION = "resume_session"  # --resume <session_id> with continue_prompt
    FRESH_SESSION = "fresh_session"  # a new /phase NN --auto session


@dataclass(frozen=True)
class LiveProcess:
    pid: int
    cwd: str
    cmdline: str
    where: str  # "worktree" | "main checkout"
    started: float | None = None  # epoch seconds, from /proc/<pid>/stat
    headless: bool = False  # `claude -p "/phase …"`: a phase session, never an idle one


@dataclass(frozen=True)
class Decision:
    action: Action
    phase: str
    reason: str
    rule: str  # the decision-table row that fired
    notify: bool = False
    session_id: str | None = None
    prompt: str | None = None
    reset_at: datetime | None = None
    question_ids: tuple[str, ...] = ()
    verdict: Verdict | None = None
    repair: str | None = None  # commit hash of the ⛔ repair, if one was made
    summary: str | None = None  # triage summary
    live: tuple[LiveProcess, ...] = field(default_factory=tuple)

    def as_log(self) -> dict[str, Any]:
        return {
            "action": str(self.action),
            "rule": self.rule,
            "notify": self.notify,
            "session_id": self.session_id,
            "prompt": self.prompt,
            "reset_at": self.reset_at.isoformat() if self.reset_at else None,
            "question_ids": list(self.question_ids),
            "outcome": str(self.verdict.outcome) if self.verdict else None,
            "repair": self.repair,
            "summary": self.summary,
            "live": [p.__dict__ for p in self.live],
        }


# --------------------------------------------------------------------------- decision table

_RETRYABLE = (ExitClass.TIMEOUT, ExitClass.CRASH, ExitClass.NO_RESULT)


def decide(
    phase_id: str,
    classification: Classification,
    verdict: Verdict | None,
    *,
    session_id: str | None = None,
    recoveries: int = 0,
    live: Iterable[LiveProcess] = (),
) -> Decision:
    """The decision table (pure). ``recoveries`` counts timeout/crash recoveries so far."""
    cls = classification.cls
    live = tuple(live)

    def pause(rule: str, reason: str, **kw: Any) -> Decision:
        return Decision(Action.PAUSE, phase_id, reason, rule, True, verdict=verdict, **kw)

    if cls is ExitClass.AUTH_ERROR:
        return pause("auth_error", f"authentication failed: {classification.reason}; no retry")
    if cls is ExitClass.PROVIDER_ERROR:
        return pause(
            "provider_error",
            f"provider error ({classification.kind or 'unknown'}): {classification.reason}; "
            "no retry that could spend credit",
        )
    if verdict is None:
        return pause("unverified", "the phase could not be verified")
    if verdict.outcome is Outcome.NEEDS_REVIEW:
        return pause("needs_review", verdict.summary())
    if cls is ExitClass.REFUSED:
        why = classification.result.reason if classification.result else classification.reason
        return pause("refused", f"the session refused the phase: {why}; nothing repaired")
    if verdict.outcome is Outcome.FAILED:
        return pause("verification_failed", verdict.summary())
    if verdict.outcome is Outcome.COMPLETE:
        how = "" if cls is ExitClass.COMPLETE else f" (session ended as {cls})"
        return Decision(
            Action.NEXT_PHASE,
            phase_id,
            f"phase {phase_id} complete and verified{how}",
            "complete",
            True,
            verdict=verdict,
        )
    if verdict.outcome is Outcome.BLOCKED:
        qs = ", ".join(f"#{q}" for q in verdict.question_ids)
        return pause(
            "blocked",
            f"phase {phase_id} blocked on owner question {qs}",
            question_ids=verdict.question_ids,
        )
    if cls is ExitClass.USAGE_LIMIT:
        when = classification.reset_at.isoformat() if classification.reset_at else "unknown"
        return Decision(
            Action.WAIT,
            phase_id,
            f"usage limit ({classification.kind or 'unknown'}), resets {when}; "
            "wait, then resume the same session",
            "usage_limit",
            True,
            session_id=session_id,
            prompt=continue_prompt(phase_id),
            reset_at=classification.reset_at,
            verdict=verdict,
        )
    if cls in _RETRYABLE:
        if cls is ExitClass.NO_RESULT and verdict.outcome is Outcome.NOT_STARTED:
            return pause(
                "no_result_unclaimed",
                "the session ended without a result line and without claiming the phase",
            )
        if live:
            return pause("live_session", live_reason(phase_id, live[0]), live=live)
        stopped = f"session ended as {cls} ({classification.reason}), work in progress"
        if recoveries == 0 and session_id:
            return Decision(
                Action.RESUME_SESSION,
                phase_id,
                f"{stopped}; resuming the same session",
                "retry_resume",
                session_id=session_id,
                prompt=continue_prompt(phase_id),
                verdict=verdict,
            )
        if recoveries < MAX_RECOVERIES:
            return Decision(
                Action.FRESH_SESSION,
                phase_id,
                f"{stopped}; starting a fresh /phase {phase_id} --auto",
                "retry_fresh",
                prompt=phase_prompt(phase_id),
                verdict=verdict,
            )
        return pause(
            "retries_exhausted",
            f"{stopped}; already resumed and retried fresh, giving up",
        )
    return pause("unexpected", f"session ended as {cls} with the repo {verdict.state}")


# --------------------------------------------------------------------------- ⛔ repair


def _run_git(
    repo: Path, *args: str, timeout: float | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def repair_blocked(
    repo: Path, phase_id: str, *, evidence: str, log: EventLog, push: bool = True
) -> str | None:
    """Commit ``⛔ Blocked`` for a phase the agent blocked without recording it on ``main``.

    The only repair PHX makes (spec R6). Like the claim protocol, it needs the main
    checkout on ``main`` with the plan file unchanged; it edits only the row's Status
    cell and commits only the plan file. Returns the commit hash, or ``None`` (logged)
    when it is not safe to repair.
    """
    repo = repo.resolve()

    def skip(reason: str) -> None:
        log.event("repair_skipped", phase=phase_id, reason=reason, evidence=evidence)

    try:
        plan = load_plan(repo)
        phase = plan.phase(phase_id)
    except (PlanError, KeyError) as exc:
        skip(f"plan unreadable: {exc}")
        return None
    if phase.status is not Status.IN_PROGRESS:
        skip(f"row is not 🔄 In progress ({phase.status})")
        return None
    branch = _run_git(repo, "branch", "--show-current").stdout.strip()
    if branch != MAIN:
        skip(f"the main checkout is on {branch or 'a detached HEAD'}, not {MAIN}")
        return None
    if _run_git(repo, "status", "--porcelain", "--", plan.plan_file).stdout.strip():
        skip(f"{plan.plan_file} has uncommitted changes in the main checkout")
        return None
    text = show_main(repo, plan.plan_file)
    assert text is not None
    path = repo / plan.plan_file
    if path.read_text(encoding="utf-8") != text:
        skip(f"{plan.plan_file} in the main checkout differs from {MAIN}")
        return None
    path.write_text(set_status_cell(text, phase_id, BLOCKED_LABEL), encoding="utf-8")
    message = (
        f"chore(plan): phase {phase_id} blocked (recorded by phx)\n\n"
        f"The session blocked but did not commit the status to {MAIN}.\nEvidence: {evidence}\n"
    )
    commit = _run_git(repo, "commit", "-q", "-m", message, "--", plan.plan_file)
    if commit.returncode != 0:
        # Restore the text itself: `git checkout` fails too while index.lock is held.
        path.write_text(text, encoding="utf-8")
        skip(f"git commit failed: {commit.stderr.strip()}")
        return None
    sha = _run_git(repo, "rev-parse", "HEAD").stdout.strip()
    pushed: str | None = None
    if push and _run_git(repo, "config", "--get", "remote.origin.url").returncode == 0:
        try:
            got = _run_git(repo, "push", "-q", "origin", MAIN, timeout=PUSH_TIMEOUT_S)
            pushed = "pushed" if got.returncode == 0 else f"push failed: {got.stderr.strip()}"
        except subprocess.TimeoutExpired:
            pushed = "push timed out"
    log.event(
        "repair",
        phase=phase_id,
        reason=f"committed {BLOCKED_LABEL} to {MAIN} (recorded by phx)",
        commit=sha,
        evidence=evidence,
        push=pushed,
    )
    return sha


# --------------------------------------------------------------------------- live sessions (R14)


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _is_claude(comm: str, argv: list[str]) -> bool:
    names = [os.path.basename(a) for a in argv[:2]]
    if comm.strip() == "claude" or "claude" in names:
        return True
    return bool(argv) and names[0] in ("node", "bun") and any("claude-code" in a for a in argv[1:2])


def _is_pty_host(argv: list[str]) -> bool:
    """``claude bg-pty-host …`` only hosts a background session; that session is its own process."""
    # Real cmdline (2.1.310): "claude bg-pty-host" as one argv entry, then --bg-pty-host …
    return (
        "--bg-pty-host" in argv
        or "bg-pty-host" in argv[:2]
        or (bool(argv) and argv[0].endswith(" bg-pty-host"))
    )


def _is_headless_phase(argv: list[str]) -> bool:
    return any(a in ("-p", "--print") for a in argv) and any(a.startswith("/phase") for a in argv)


def _start_time(proc_root: Path, stat: str | None) -> float | None:
    """Process start as epoch seconds (``starttime`` ticks after ``btime``), or None."""
    btime = next(
        (
            line.split()[1]
            for line in (_read(proc_root / "stat") or "").splitlines()
            if line.startswith("btime ")
        ),
        None,
    )
    if not stat or ")" not in stat or btime is None:
        return None
    try:
        ticks = int(stat.rsplit(")", 1)[1].split()[19])
        return int(btime) + ticks / os.sysconf("SC_CLK_TCK")
    except (IndexError, ValueError, OSError):
        return None


def _ancestors(proc_root: Path) -> set[int]:
    """This process and its parents (a `phx` started from inside Claude Code is not a rival)."""
    pids: set[int] = set()
    pid = os.getpid()
    while pid > 1 and pid not in pids:
        pids.add(pid)
        stat = _read(proc_root / str(pid) / "stat")
        if not stat or ")" not in stat:
            break
        try:
            pid = int(stat.rsplit(")", 1)[1].split()[1])
        except (IndexError, ValueError):
            break
    return pids


def find_claude_processes(
    places: Mapping[str, str],
    *,
    proc_root: Path = Path("/proc"),
    exclude: Collection[int] | None = None,
) -> list[LiveProcess]:
    """Live ``claude`` processes whose cwd is inside one of ``places`` (``{path: label}``).

    Scans ``/proc`` (``comm``, ``cmdline``, ``cwd``); other users' processes and ones
    that exit mid-scan are skipped. ``exclude`` defaults to this process and its parents.
    """
    skip = _ancestors(proc_root) if exclude is None else set(exclude)
    roots = [(Path(p).resolve(), label) for p, label in places.items()]
    found: list[LiveProcess] = []
    try:
        entries = sorted(e for e in os.listdir(proc_root) if e.isdigit())
    except OSError:
        return found
    for entry in entries:
        pid = int(entry)
        if pid in skip:
            continue
        base = proc_root / entry
        raw = _read(base / "cmdline")
        if raw is None:
            continue
        argv = [a for a in raw.split("\0") if a]
        if not _is_claude(_read(base / "comm") or "", argv) or _is_pty_host(argv):
            continue
        try:
            cwd = Path(os.readlink(base / "cwd"))
        except OSError:
            continue
        for root, label in roots:
            if cwd == root or cwd.is_relative_to(root):
                found.append(
                    LiveProcess(
                        pid,
                        str(cwd),
                        " ".join(argv)[:200],
                        label,
                        _start_time(proc_root, _read(base / "stat")),
                        _is_headless_phase(argv),
                    )
                )
                break
    found.sort(key=lambda p: (p.where != "worktree", p.pid))
    return found


def phase_activity(repo: Path, phase_id: str) -> float | None:
    """Latest sign of work on a phase: its branch tip's commit time or a changed file's mtime."""
    branches, trees = load_live(repo).for_phase(phase_id)
    times: list[float] = []
    for branch in branches:
        out = _run_git(repo, "log", "-1", "--format=%ct", branch, "--").stdout.strip()
        if out.isdigit():
            times.append(float(out))
    for tree in trees:
        status = _run_git(Path(tree.path), "status", "--porcelain", "-z", "--untracked-files=all")
        for entry in status.stdout.split("\0"):
            if len(entry) > 3:
                try:
                    times.append((Path(tree.path) / entry[3:]).stat().st_mtime)
                except OSError:
                    continue
    return max(times, default=None)


def live_sessions(
    repo: Path,
    phase_id: str,
    *,
    since: float | None = None,
    proc_root: Path = Path("/proc"),
    exclude: Collection[int] | None = None,
    ignored: list[LiveProcess] | None = None,
) -> list[LiveProcess]:
    """Claude processes that may be running ``phase_id``.

    A process in the phase's worktree always counts. One in the main checkout counts too,
    because Claude Code keeps its process cwd where it started while its tools work in
    the worktree, but only when it is a headless ``/phase`` session or the phase's branch
    or worktree changed after the process started and after ``since`` (when PHX's own last
    session for the phase ended). An idle interactive session, or the one driving ``phx``,
    is not a rival (Phase 10 pilot, ADR-0019); those go to ``ignored`` when given.
    """
    repo = repo.resolve()
    _branches, trees = load_live(repo).for_phase(phase_id)
    places = {w.path: "worktree" for w in trees}
    places[str(repo)] = "main checkout"
    found = find_claude_processes(places, proc_root=proc_root, exclude=exclude)
    if all(p.where == "worktree" or p.headless for p in found):
        return found
    activity = phase_activity(repo, phase_id)
    live: list[LiveProcess] = []
    for p in found:
        after = max(since or 0.0, p.started or 0.0)
        if p.where == "worktree" or p.headless or (activity is not None and activity > after):
            live.append(p)
        elif ignored is not None:
            ignored.append(p)
    return live


def live_reason(phase_id: str, process: LiveProcess) -> str:
    if process.where == "worktree":
        return f"another session is running phase {phase_id} (pid {process.pid} in {process.cwd})"
    return (
        f"a Claude session (pid {process.pid}) is open in the main checkout; "
        f"it may be running phase {phase_id}"
    )


def last_session_end(state: Path, phase_id: str) -> float | None:
    """When PHX's last session for a phase ended: its transcript's mtime."""
    times = []
    for path in sessions_dir(state).glob(f"{phase_id}-*.jsonl"):
        try:
            times.append(path.stat().st_mtime)
        except OSError:
            continue
    return max(times, default=None)


@dataclass(frozen=True)
class Resumability:
    resumable: bool
    reason: str
    live: tuple[LiveProcess, ...] = ()


def check_resumable(
    repo: Path,
    phase_id: str,
    *,
    since: float | None = None,
    proc_root: Path = Path("/proc"),
    exclude: Collection[int] | None = None,
) -> Resumability:
    """R14: may PHX resume a ``🔄`` phase? Not while a Claude process may hold it."""
    ignored: list[LiveProcess] = []
    live = tuple(
        live_sessions(
            repo, phase_id, since=since, proc_root=proc_root, exclude=exclude, ignored=ignored
        )
    )
    if live:
        return Resumability(False, live_reason(phase_id, live[0]), live)
    reason = f"no live Claude process in phase {phase_id}'s worktree or the main checkout"
    if ignored:
        pids = ", ".join(str(p.pid) for p in ignored)
        reason += (
            f" (ignored idle session(s) in the main checkout, pid {pids}: "
            f"no work on phase {phase_id} since they started or PHX's last session)"
        )
    return Resumability(True, reason)


# --------------------------------------------------------------------------- orchestration

TriageFn = Callable[..., Any]
_TRIAGE_ON = (Outcome.BLOCKED, Outcome.NEEDS_REVIEW, Outcome.FAILED)


def handle_outcome(
    repo: Path,
    outcome: SessionOutcome,
    *,
    state: Path,
    log: EventLog,
    recoveries: int = 0,
    baseline: Baseline | None = None,
    config: Config | None = None,
    env: Mapping[str, str] | None = None,
    proc_root: Path = Path("/proc"),
    exclude: Collection[int] | None = None,
    triage: TriageFn | None = None,
) -> Decision:
    """Repair, verify, decide, triage and log one finished phase session.

    Verification only reads the repo; the only write is :func:`repair_blocked`.
    ``triage`` defaults to :func:`phx.triage.summarize`; it runs only when
    ``config.triage`` is on and the phase blocked, needs review or failed verification.
    """
    repo = repo.resolve()
    config = config or Config()
    phase_id = outcome.phase
    cls = outcome.classification
    verdict: Verdict | None = None
    repair: str | None = None

    if cls.cls not in (ExitClass.AUTH_ERROR, ExitClass.PROVIDER_ERROR):
        said_blocked = cls.result is not None and cls.result.status == "blocked"
        try:
            row = load_plan(repo).phase(phase_id).status
        except (PlanError, KeyError):
            row = None
        if row is Status.IN_PROGRESS and (said_blocked or wip_blocked(repo, phase_id)):
            evidence = (
                "result line says blocked"
                if said_blocked
                else f"wip(phase-{phase_id}): blocked commit on the phase branch"
            )
            repair = repair_blocked(repo, phase_id, evidence=evidence, log=log)
        verdict = verify_phase(
            repo, phase_id, cls, baseline=baseline, config=config, env=env, log=log
        )

    live: list[LiveProcess] = []
    if (
        verdict is not None
        and cls.cls in _RETRYABLE
        and verdict.outcome in (Outcome.IN_PROGRESS, Outcome.NOT_STARTED)
    ):
        live = live_sessions(
            repo,
            phase_id,
            since=last_session_end(state, phase_id),
            proc_root=proc_root,
            exclude=exclude,
        )

    decision = decide(
        phase_id,
        cls,
        verdict,
        session_id=outcome.session_id,
        recoveries=recoveries,
        live=live,
    )
    decision = replace(decision, repair=repair)

    if (
        config.triage
        and verdict is not None
        and decision.action is Action.PAUSE
        and verdict.outcome in _TRIAGE_ON
    ):
        if triage is None:
            from phx.triage import summarize

            triage = summarize
        result = triage(
            phase=phase_id,
            verdict=verdict,
            transcript=outcome.transcript,
            state=state,
            log=log,
            env=env,
        )
        decision = replace(decision, summary=getattr(result, "summary", None))

    log.event(
        "decision",
        phase=phase_id,
        reason=decision.reason,
        session_class=str(cls.cls),
        recoveries=recoveries,
        **decision.as_log(),
    )
    return decision
