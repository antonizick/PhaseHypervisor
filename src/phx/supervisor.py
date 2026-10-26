"""The supervisor loop behind ``phx run`` / ``phx resume`` (spec §2, A6-A9, R10-R15).

One phase at a time: read the plan from ``main``, pick what to run (a pending
usage-limit wait, a ``🔄`` phase, a ``⛔`` phase whose questions are answered, or the
next eligible phase), apply its Gate, launch ``/phase NN --auto`` (Phase 05), hand the
outcome to :func:`phx.recover.handle_outcome` (Phase 06) and act on its decision.
Every choice goes to ``run.jsonl`` with its reason; ``state.json`` lets a later
supervisor carry on after a stop, crash or reboot. The supervisor never calls an LLM
itself; the only model calls are the phase sessions, the limit probe and triage.
"""

import os
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Collection, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from functools import partial
from pathlib import Path
from typing import Any, Protocol, TextIO

from phx import notify
from phx.classify import ExitClass
from phx.locks import LockBusy, RunLock, main_checkout
from phx.logging import EventLog
from phx.paths import Config, ensure_state_dirs, parse_config, state_dir
from phx.plan import (
    STATUS_LABELS,
    ContractError,
    Gate,
    Phase,
    Plan,
    PlanError,
    Status,
    UnknownModel,
    load_plan,
    next_eligible,
    phase_sort_key,
    show_main,
)
from phx.recover import (
    Action,
    Decision,
    TriageFn,
    check_resumable,
    continue_prompt,
    handle_outcome,
    phase_prompt,
)
from phx.runner import (
    Launcher,
    LauncherError,
    SessionOutcome,
    build_argv,
    find_launcher,
    probe,
    run_session,
)
from phx.state import Pause, RunState, RunStatus, Wait, load_state, now_ts, save_state
from phx.vault import append_summary
from phx.verify import UnsupportedCommand, capture_baseline, parse_command

EXIT_FINISHED = 0
EXIT_ERROR = 1
EXIT_PAUSED = 3
EXIT_STOPPED = 4

RESET_MARGIN_S = 120  # wake this long after the announced reset time (ADR-0006)
BACKOFF_S = (1800, 3600, 7200, 14400, 21600)  # no reset time given: 30 min … 6 h (spec R8)
WAKE_STEP_S = 60.0  # longest single sleep; the wall clock is re-read after each one
HEARTBEAT_S = 30.0  # how often a stream event refreshes state.json


class Clock(Protocol):
    def now(self) -> float: ...

    def sleep(self, seconds: float, stop: threading.Event) -> None: ...


class RealClock:
    """Wall clock. Sleeps are short and re-checked, so a suspend is noticed on wake."""

    def now(self) -> float:
        return time.time()

    def sleep(self, seconds: float, stop: threading.Event) -> None:
        stop.wait(max(0.0, seconds))


@dataclass(frozen=True)
class RunOptions:
    pause_after: str | None = None
    max_phases: int | None = None
    until: str | None = None
    dry_run: bool = False
    resume: bool = False  # `phx resume`: clear a pause first


class EndKind(StrEnum):
    FINISHED = "finished"
    PAUSED = "paused"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True)
class End:
    kind: EndKind
    reason: str
    rule: str
    phase: str | None = None
    decision: Decision | None = None
    question_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Selection:
    phase: Phase
    prompt: str
    resume: str | None  # session ID to --resume, or None for a fresh session
    why: str
    rule: str
    wait: Wait | None = None


def backoff_s(step: int) -> int:
    return BACKOFF_S[min(step, len(BACKOFF_S) - 1)]


def plan_config(repo: Path) -> Config:
    """``.phx/config.toml`` from ``main`` (the same source as the plan), or the defaults."""
    text = show_main(repo, ".phx/config.toml")
    return parse_config(text, "main:.phx/config.toml") if text else Config()


def _fmt_epoch(epoch: float) -> str:
    return now_ts(epoch)


class Supervisor:
    def __init__(
        self,
        repo: Path,
        *,
        options: RunOptions | None = None,
        state_root: Path | None = None,
        env: Mapping[str, str] | None = None,
        clock: Clock | None = None,
        notifier: notify.Notifier | None = None,
        unit: str | None = None,
        verbose: bool = False,
        out: TextIO | None = None,
        proc_root: Path = Path("/proc"),
        exclude: Collection[int] | None = None,
        triage: TriageFn | None = None,
        vault: bool = True,
        lock_retry_s: float | None = None,
    ) -> None:
        self.repo = main_checkout(repo)
        self.options = options or RunOptions()
        self.env = dict(os.environ if env is None else env)
        self.state_dir = state_dir(self.repo, state_root)
        ensure_state_dirs(self.state_dir)
        self.log = EventLog(self.state_dir / "run.jsonl", verbose=verbose)
        self.notifier = notifier or notify.Notifier(
            self.log, env=self.env, repo_label=self.repo.name
        )
        self.clock: Clock = clock or RealClock()
        self.unit = unit
        self.out = out or sys.stdout
        self.proc_root = proc_root
        self.exclude = exclude
        self.triage = triage
        self.vault = vault
        self.lock_retry_s = lock_retry_s
        self.stop_event = threading.Event()
        self.stop_reason = ""
        self.state = RunState()
        self.config = Config()
        self.launcher: Launcher | None = None
        self.lock: RunLock | None = None
        self._last_beat = 0.0

    # ------------------------------------------------------------------ public

    def request_stop(self, reason: str = "stop requested") -> None:
        """Ask the loop to stop (signal handlers call this); the phase stays resumable."""
        if not self.stop_event.is_set():
            self.stop_reason = reason
            self.stop_event.set()

    def work_root(self) -> Path:
        """Repos PHX may run in (spec S1): ``$PHX_WORK_ROOT``, else ``~/Work``."""
        root = self.env.get("PHX_WORK_ROOT")
        home = self.env.get("HOME")
        return Path(root) if root else (Path(home) if home else Path.home()) / "Work"

    def run(self) -> int:
        if self.options.dry_run:
            return self._dry_run()
        root = self.work_root().resolve()
        if not self.repo.is_relative_to(root):
            reason = f"{self.repo} is outside {root}; PHX runs only repos under it (spec S1)"
            self.log.event("refused", reason=reason)
            self._say(f"phx: {reason}")
            return EXIT_ERROR
        started = now_ts()
        kwargs: dict[str, Any] = {"started": started, "unit": self.unit, "env": self.env}
        if self.lock_retry_s is not None:
            kwargs["retry_s"] = self.lock_retry_s
        try:
            self.lock = RunLock(self.repo, **kwargs).acquire()
        except LockBusy as exc:
            self.log.event("lock_busy", reason=str(exc))
            self._say(f"phx: {exc}")
            return EXIT_ERROR
        try:
            return self._run_locked(started)
        finally:
            self.lock.release()
            self.lock = None

    # ------------------------------------------------------------------ output helpers

    def _say(self, text: str) -> None:
        print(text, file=self.out, flush=True)

    def _save(self) -> None:
        save_state(self.state_dir, self.state)

    # ------------------------------------------------------------------ main loop

    def _run_locked(self, started: str) -> int:
        prev = load_state(self.state_dir)
        if prev and prev.pause and not self.options.resume:
            self.log.event(
                "refused",
                phase=prev.pause.phase,
                reason=f"run is paused ({prev.pause.reason}); `phx resume` clears the pause",
                rule=prev.pause.rule,
            )
            self._say(
                f"phx: run is paused: {prev.pause.reason}\n"
                f"     fix what it needs, then: phx resume {self.repo}"
            )
            return EXIT_PAUSED
        self.state = RunState(
            run_id=time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6],
            repo=str(self.repo),
            status=RunStatus.RUNNING,
            pid=os.getpid(),
            unit=self.unit,
            started=started,
        )
        if prev:
            self.state.sessions = dict(prev.sessions)
            self.state.wait = prev.wait
            self.state.phase = prev.phase
            self.state.recoveries = prev.recoveries
            if prev.status in (RunStatus.RUNNING, RunStatus.WAITING):
                self.log.event(
                    "previous_run",
                    phase=prev.phase,
                    reason=(
                        f"run {prev.run_id} ended without cleanup (crash, kill or reboot) "
                        f"while {prev.status}; carrying on from state.json"
                    ),
                    previous_status=prev.status,
                )
        self.log.event(
            "run_start",
            reason="phx resume" if self.options.resume else "phx run",
            run_id=self.state.run_id,
            repo=str(self.repo),
            pid=os.getpid(),
            unit=self.unit,
            options=self.options.__dict__,
        )
        if self.options.resume:
            cleared = prev.pause.reason if prev and prev.pause else None
            self.log.event(
                "resume",
                phase=prev.pause.phase if prev and prev.pause else None,
                reason=f"pause cleared: {cleared}" if cleared else "nothing was paused",
            )
        self._save()
        end = self._loop()
        return self._finish(end)

    def _loop(self) -> End:
        first = True
        while True:
            if self.stop_event.is_set():
                return End(EndKind.STOPPED, self.stop_reason, "stop", self.state.phase)
            try:
                plan = load_plan(self.repo)
                plan.check_contract()
            except ContractError as exc:
                return End(EndKind.FAILED, f"{exc}; PHX will not run this repo", "contract")
            except PlanError as exc:
                return End(EndKind.FAILED, f"plan unreadable: {exc}", "plan_error")
            if first:
                first = False
                try:
                    self.config = plan_config(self.repo)
                except ValueError as exc:
                    return End(EndKind.FAILED, str(exc), "config_error")
                self._check_test_commands(plan)
                try:
                    self.launcher = find_launcher(self.env)
                except LauncherError as exc:
                    return End(EndKind.FAILED, str(exc), "no_launcher")
            limit = self._limits_reached()
            if limit:
                return limit
            choice = self._select(plan, live_check=True)
            if isinstance(choice, End):
                return choice
            gate_end = self._gate_before(choice.phase)
            if gate_end:
                return gate_end
            try:
                alias = choice.phase.require_alias()
            except UnknownModel as exc:
                return End(EndKind.PAUSED, str(exc), "unknown_model", choice.phase.id)
            self.log.event(
                "select",
                phase=choice.phase.id,
                reason=choice.why,
                rule=choice.rule,
                prompt=choice.prompt,
                resume=choice.resume,
                alias=alias,
                gate=str(choice.phase.gate),
                gate_source=choice.phase.gate_source,
            )
            result = self._run_phase(choice, alias)
            if result is not None:
                return result
            after = self._gate_after(choice.phase)
            if after:
                return after

    def _check_test_commands(self, plan: Plan) -> None:
        for command in plan.test_commands:
            try:
                parse_command(command)
            except UnsupportedCommand as exc:
                self.log.event(
                    "warning",
                    reason=(
                        f"test command `{command}` cannot run without a shell ({exc}); "
                        "verification will fail. Set test_command in .phx/config.toml "
                        "to a script (ADR-0015)"
                    ),
                    test_source=plan.test_source,
                )
                self._say(f"phx: warning: test command `{command}` is unsupported: {exc}")

    def _limits_reached(self) -> End | None:
        n = self.options.max_phases
        if n is not None and len(self.state.completed) >= n:
            return End(
                EndKind.FINISHED, f"--max-phases {n} reached", "max_phases", self.state.phase
            )
        return None

    # ------------------------------------------------------------------ choosing a phase

    def _select(self, plan: Plan, *, live_check: bool) -> Selection | End:
        elig = next_eligible(plan)
        self.log.event(
            "plan",
            reason=f"next eligible: {elig.next.id if elig.next else 'none'}",
            next=elig.next.id if elig.next else None,
            resume=[p.id for p in elig.resume],
            reasons=elig.reasons,
            open_questions=[q.id for q in plan.questions if q.open],
        )
        choice = self._choose(plan, elig.next, elig.resume, live_check=live_check)
        until = self.options.until
        if (
            isinstance(choice, Selection)
            and until is not None
            and phase_sort_key(choice.phase.id) > phase_sort_key(until)
        ):
            return End(
                EndKind.FINISHED,
                f"--until {until} reached (next would be {choice.phase.id})",
                "until",
                choice.phase.id,
            )
        return choice

    def _choose(
        self,
        plan: Plan,
        nxt: Phase | None,
        resume: tuple[Phase, ...],
        *,
        live_check: bool,
    ) -> Selection | End:
        wait = self.state.wait
        if wait is not None:
            try:
                row = plan.phase(wait.phase)
            except KeyError:
                row = None
            if row is not None and row.status is Status.IN_PROGRESS:
                return Selection(
                    row,
                    wait.prompt or continue_prompt(row.id),
                    wait.session_id,
                    f"a usage-limit wait for phase {row.id} is pending "
                    f"(wake {_fmt_epoch(wait.until)}); finishing it, then resuming",
                    "pending_wait",
                    wait,
                )
            self.log.event(
                "wait_dropped",
                phase=wait.phase,
                reason=(
                    f"pending wait dropped: phase {wait.phase} is "
                    f"{STATUS_LABELS[row.status] if row else 'not in the plan'}"
                ),
            )
            self.state.wait = None

        if len(resume) > 1:
            listed = ", ".join(p.id for p in resume)
            return End(
                EndKind.PAUSED,
                f"several phases are 🔄 In progress ({listed}); PHX runs one at a time "
                "(ADR-0007). Finish or reset all but one",
                "several_in_progress",
                resume[0].id,
            )
        if resume:
            p = resume[0]
            if p.gate is Gate.OWNER:
                return self._owner_gate(p)
            if live_check:
                r = check_resumable(self.repo, p.id, proc_root=self.proc_root, exclude=self.exclude)
                self.log.event("resume_check", phase=p.id, reason=r.reason, resumable=r.resumable)
                if not r.resumable:
                    return End(EndKind.PAUSED, r.reason, "live_session", p.id)
            sid = self.state.sessions.get(p.id)
            if sid:
                return Selection(
                    p,
                    continue_prompt(p.id),
                    sid,
                    f"phase {p.id} is 🔄 In progress and PHX recorded its session {sid}; "
                    "resuming that session (R14)",
                    "resume_recorded",
                )
            return Selection(
                p,
                phase_prompt(p.id),
                None,
                f"phase {p.id} is 🔄 In progress with no PHX session recorded; "
                "a fresh /phase --auto session resumes it (R14)",
                "resume_fresh",
            )

        for p in plan.phases:
            if p.status is not Status.BLOCKED:
                continue
            open_qs = plan.open_questions_for(p.id)
            if open_qs:
                ids = tuple(q.id for q in open_qs)
                return End(
                    EndKind.PAUSED,
                    f"phase {p.id} is ⛔ Blocked on open owner question "
                    + ", ".join(f"#{q}" for q in ids),
                    "blocked",
                    p.id,
                    question_ids=ids,
                )
            if p.gate is Gate.OWNER:
                return self._owner_gate(p)
            return Selection(
                p,
                phase_prompt(p.id),
                None,
                f"phase {p.id} is ⛔ Blocked and its questions are answered; "
                "/phase --auto resumes it (contract §4.3)",
                "resume_blocked",
            )

        if nxt is not None:
            return Selection(
                nxt,
                phase_prompt(nxt.id),
                None,
                f"phase {nxt.id} is the next eligible phase (⬜, dependencies ✅)",
                "next_eligible",
            )

        remaining = [p for p in plan.phases if p.status is not Status.COMPLETE]
        if not remaining:
            return End(EndKind.FINISHED, "every phase is ✅ Complete", "all_complete")
        reasons = next_eligible(plan).reasons
        why = "; ".join(f"{p.id}: {reasons.get(p.id, STATUS_LABELS[p.status])}" for p in remaining)
        open_ids = tuple(q.id for q in plan.questions if q.open)
        return End(
            EndKind.PAUSED,
            f"no phase can start ({why})",
            "nothing_eligible",
            remaining[0].id,
            question_ids=open_ids,
        )

    def _owner_gate(self, p: Phase) -> End:
        return End(
            EndKind.PAUSED,
            f"phase {p.id} has Gate owner: PHX never starts it (R12). Run it yourself "
            f"with /phase {p.id}, then phx resume",
            "owner_gate",
            p.id,
        )

    def _gate_before(self, p: Phase) -> End | None:
        if p.gate is Gate.OWNER:
            return self._owner_gate(p)
        return None

    def _gate_after(self, p: Phase) -> End | None:
        if p.gate is Gate.REVIEW:
            return End(
                EndKind.PAUSED,
                f"phase {p.id} has Gate review ({p.gate_source}): review it, then phx resume",
                "review_gate",
                p.id,
            )
        if self.options.pause_after == p.id:
            return End(EndKind.PAUSED, f"--pause-after {p.id}", "pause_after", p.id)
        if self.options.until == p.id:
            return End(EndKind.FINISHED, f"--until {p.id} reached", "until", p.id)
        return self._limits_reached()

    # ------------------------------------------------------------------ running one phase

    def _run_phase(self, choice: Selection, alias: str) -> End | None:
        """Drive one phase until it completes (``None``) or the run must end."""
        p = choice.phase
        if self.state.phase != p.id:
            self.state.recoveries = 0
        self.state.phase = p.id
        self.state.attempt = 0
        if self.lock:
            self.lock.update(phase=p.id)
        prompt, resume = choice.prompt, choice.resume
        if choice.wait is not None:
            waited = self._wait(choice.wait)
            if waited is not None:
                return waited
        while True:
            if self.stop_event.is_set():
                return End(EndKind.STOPPED, self.stop_reason, "stop", p.id)
            baseline = capture_baseline(self.repo)
            self.state.attempt += 1
            self.state.status = RunStatus.RUNNING
            self.state.session_id = resume
            self._save()
            outcome = run_session(
                repo=self.repo,
                state=self.state_dir,
                phase=p.id,
                prompt=prompt,
                alias=alias,
                log=self.log,
                config=self.config,
                resume=resume,
                launcher=self.launcher,
                env=self.env,
                cancel=self.stop_event,
                on_start=partial(self._session_started, p.id),
                on_event=self._heartbeat,
            )
            self._account(outcome)
            if self.stop_event.is_set():
                self.state.totals(p.id).outcome = "stopped"
                return End(
                    EndKind.STOPPED,
                    f"{self.stop_reason}; phase {p.id} stays 🔄 and resumes with session "
                    f"{outcome.session_id}",
                    "stop",
                    p.id,
                )
            decision = handle_outcome(
                self.repo,
                outcome,
                state=self.state_dir,
                log=self.log,
                recoveries=self.state.recoveries,
                baseline=baseline,
                config=self.config,
                env=self.env,
                proc_root=self.proc_root,
                exclude=self.exclude,
                triage=self.triage,
            )
            self.state.totals(p.id).outcome = decision.rule
            self._save()
            if decision.action is Action.NEXT_PHASE:
                self.state.completed.append(p.id)
                self.state.recoveries = 0
                self.state.sessions.pop(p.id, None)
                self._save()
                t = self.state.totals(p.id)
                self.notifier.send(
                    notify.phase_complete(
                        p.id,
                        f"{decision.reason}. {t.tokens} tokens, ${t.cost_usd:.2f}, "
                        f"{t.sessions} session(s).",
                    ),
                    phase=p.id,
                )
                return None
            if decision.action is Action.PAUSE:
                return End(
                    EndKind.PAUSED,
                    decision.reason,
                    decision.rule,
                    p.id,
                    decision,
                    decision.question_ids,
                )
            if decision.action is Action.WAIT:
                wait = self._new_wait(p.id, decision, outcome)
                waited = self._wait(wait)
                if waited is not None:
                    return waited
                prompt = decision.prompt or continue_prompt(p.id)
                resume = decision.session_id
                if resume is None:
                    prompt = phase_prompt(p.id)
                continue
            # RESUME_SESSION / FRESH_SESSION: a timeout/crash recovery (Phase 06 ladder)
            self.state.recoveries += 1
            prompt = decision.prompt or phase_prompt(p.id)
            resume = decision.session_id if decision.action is Action.RESUME_SESSION else None
            self.log.event(
                "retry",
                phase=p.id,
                reason=decision.reason,
                action=str(decision.action),
                recoveries=self.state.recoveries,
                resume=resume,
            )

    def _session_started(self, phase: str, session_id: str) -> None:
        self.state.session_id = session_id
        self.state.sessions[phase] = session_id
        self._save()

    def _heartbeat(self, _event: dict[str, Any]) -> None:
        now = time.monotonic()
        if now - self._last_beat >= HEARTBEAT_S:
            self._last_beat = now
            self.state.last_event = now_ts()
            self._save()

    def _account(self, outcome: SessionOutcome) -> None:
        t = self.state.totals(outcome.phase)
        t.sessions += 1
        t.tokens += outcome.usage.total_tokens
        t.cost_usd += outcome.usage.cost_usd or 0.0
        self.state.tokens += outcome.usage.total_tokens
        self.state.cost_usd += outcome.usage.cost_usd or 0.0
        self.state.session_id = outcome.session_id
        self.state.sessions[outcome.phase] = outcome.session_id
        self.state.classification = str(outcome.classification.cls)
        self.state.provider = outcome.provider.provider
        self._save()

    # ------------------------------------------------------------------ usage-limit wait

    def _new_wait(self, phase: str, decision: Decision, outcome: SessionOutcome) -> Wait:
        now = self.clock.now()
        if decision.reset_at is not None:
            until = max(now, decision.reset_at.timestamp() + RESET_MARGIN_S)
            how = f"reset time {decision.reset_at:%Y-%m-%d %H:%M %Z} + {RESET_MARGIN_S // 60} min"
        else:
            until = now + backoff_s(0)
            how = f"no reset time given; back-off {backoff_s(0) // 60} min"
        return Wait(
            phase=phase,
            session_id=decision.session_id,
            prompt=decision.prompt,
            until=until,
            reason=f"{decision.reason} ({how})",
            reset_at=decision.reset_at.isoformat() if decision.reset_at else None,
            provider=outcome.provider.provider,
            started=now,
        )

    def _provider_now(self) -> str | None:
        if self.launcher is None or self.launcher.ai_provider is None:
            return None
        try:
            got = subprocess.run(
                [self.launcher.ai_provider, "get"],
                capture_output=True,
                text=True,
                timeout=15,
                env=self.env,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        value = got.stdout.strip()
        return value if got.returncode == 0 and value else None

    def _wait(self, wait: Wait) -> End | None:
        """Wait out a usage limit (ADR-0006). ``None`` means: resume now."""
        self.state.wait = wait
        self.state.status = RunStatus.WAITING
        self._save()
        resume_at = _fmt_epoch(wait.until)
        self.log.event(
            "wait_start",
            phase=wait.phase,
            reason=wait.reason,
            until=resume_at,
            until_epoch=wait.until,
            reset_at=wait.reset_at,
            provider=wait.provider,
            session_id=wait.session_id,
            poll_interval_s=self.config.poll_interval_s,
        )
        self.notifier.send(notify.waiting(wait.phase, wait.reason, resume_at), phase=wait.phase)
        poll = float(self.config.poll_interval_s)
        next_check = self.clock.now()  # check the provider at once, then every poll_interval_s
        outcome = "ready"
        while True:
            if self.stop_event.is_set():
                self.log.event(
                    "wait_stopped",
                    phase=wait.phase,
                    reason=f"{self.stop_reason}; the wait is kept in state.json and "
                    "continues on the next phx run/resume",
                )
                return End(EndKind.STOPPED, self.stop_reason, "stop", wait.phase)
            now = self.clock.now()
            if now >= next_check:
                provider = self._provider_now()
                self.log.event("provider_check", phase=wait.phase, reason=str(provider))
                if provider == "openrouter" and wait.provider != "openrouter":
                    self.log.event(
                        "provider_switch",
                        phase=wait.phase,
                        reason=f"provider is now {provider} (was {wait.provider}); "
                        "resuming at once without a probe (ADR-0006)",
                    )
                    self.notifier.send(
                        notify.provider_switch(wait.phase, provider), phase=wait.phase
                    )
                    outcome = "provider_switch"
                    break
                next_check = now + poll
            if now >= wait.until:
                late = now - wait.until
                self.log.event(
                    "wake",
                    phase=wait.phase,
                    reason=(
                        f"wait over; woke {late / 60:.0f} min late (suspend?)"
                        if late > 2 * WAKE_STEP_S
                        else "wait over"
                    ),
                    late_s=round(late, 1),
                )
                cls = probe(
                    state=self.state_dir, log=self.log, launcher=self.launcher, env=self.env
                )
                self.log.event("probe", phase=wait.phase, reason=cls.reason, **cls.as_log())
                if cls.cls is ExitClass.COMPLETE:
                    break
                if cls.cls is ExitClass.AUTH_ERROR:
                    self._clear_wait(wait)
                    return End(
                        EndKind.PAUSED,
                        f"probe after the wait: authentication failed ({cls.reason})",
                        "auth_error",
                        wait.phase,
                    )
                now = self.clock.now()
                if cls.cls is ExitClass.USAGE_LIMIT and cls.reset_at is not None:
                    wait.until = max(
                        now + self.config.limit_poll_interval_s,
                        cls.reset_at.timestamp() + RESET_MARGIN_S,
                    )
                    how = f"new reset time {cls.reset_at:%H:%M %Z}"
                elif wait.reset_at is not None:
                    wait.until = now + self.config.limit_poll_interval_s
                    how = f"reset time passed; probing every {self.config.limit_poll_interval_s}s"
                else:
                    wait.backoff_step += 1
                    wait.until = now + backoff_s(wait.backoff_step)
                    how = f"back-off {backoff_s(wait.backoff_step) // 60} min"
                self._save()
                self.log.event(
                    "wait_extend",
                    phase=wait.phase,
                    reason=f"still limited ({cls.cls}): {how}",
                    until=_fmt_epoch(wait.until),
                    until_epoch=wait.until,
                    backoff_step=wait.backoff_step,
                )
                continue
            sleep = min(WAKE_STEP_S, wait.until - now, max(0.0, next_check - now))
            self.clock.sleep(max(sleep, 0.0), self.stop_event)
        self._clear_wait(wait)
        self.log.event(
            "wait_end",
            phase=wait.phase,
            reason="capacity is back" if outcome == "ready" else "provider switched",
            waited_s=round(self.clock.now() - wait.started, 1),
        )
        return None

    def _clear_wait(self, wait: Wait) -> None:
        self.state.totals(wait.phase).wait_s += max(0.0, self.clock.now() - wait.started)
        self.state.wait = None
        self.state.status = RunStatus.RUNNING
        self._save()

    # ------------------------------------------------------------------ ending a run

    def _finish(self, end: End) -> int:
        status = {
            EndKind.FINISHED: RunStatus.FINISHED,
            EndKind.PAUSED: RunStatus.PAUSED,
            EndKind.STOPPED: RunStatus.STOPPED,
            EndKind.FAILED: RunStatus.FAILED,
        }[end.kind]
        self.state.status = status
        self.state.end_reason = end.reason
        summary = end.decision.summary if end.decision else None
        if end.kind is EndKind.PAUSED:
            self.state.pause = Pause(
                end.reason, end.rule, end.phase, now_ts(), list(end.question_ids), summary
            )
        self._save()
        self.log.event(
            "run_end",
            phase=end.phase,
            reason=end.reason,
            status=status,
            rule=end.rule,
            run_id=self.state.run_id,
            completed=self.state.completed,
            tokens=self.state.tokens,
            cost_usd=round(self.state.cost_usd, 6),
            phases={k: v.__dict__ for k, v in self.state.phases.items()},
        )
        self._notify_end(end, summary)
        if self.vault and (self.state.phases or end.kind is not EndKind.FAILED):
            append_summary(self.repo, self.state, self.log)
        self._say(f"phx: run {status}: {end.reason}")
        if end.kind is EndKind.PAUSED:
            self._say(f"     when ready: phx resume {self.repo}")
        return {
            EndKind.FINISHED: EXIT_FINISHED,
            EndKind.PAUSED: EXIT_PAUSED,
            EndKind.STOPPED: EXIT_STOPPED,
            EndKind.FAILED: EXIT_ERROR,
        }[end.kind]

    def _notify_end(self, end: End, summary: str | None) -> None:
        repo = str(self.repo)
        if end.kind is EndKind.STOPPED:
            return  # Nick asked for it
        if end.kind is EndKind.FINISHED:
            done = ", ".join(self.state.completed) or "none"
            note = notify.finished(
                f"{end.reason}. Phases completed: {done}. "
                f"{self.state.tokens} tokens, ${self.state.cost_usd:.2f}."
            )
        elif end.kind is EndKind.FAILED:
            note = notify.verification_failed(end.phase or "-", end.reason, None)
        elif end.rule == "blocked":
            note = notify.blocked(repo, end.phase or "?", end.question_ids, end.reason, summary)
        elif end.rule in ("verification_failed", "needs_review"):
            note = notify.verification_failed(end.phase or "?", end.reason, summary)
        else:
            note = notify.paused(repo, end.phase, end.reason, summary)
        self.notifier.send(note, phase=end.phase)

    # ------------------------------------------------------------------ dry run

    def _dry_run(self) -> int:
        """Print what would run, in order, assuming each phase completes. Spends nothing."""
        try:
            plan = load_plan(self.repo)
            plan.check_contract()
            self.config = plan_config(self.repo)
        except (PlanError, ValueError) as exc:
            self._say(f"phx: {exc}")
            self.log.event("dry_run", reason=f"cannot run: {exc}")
            return EXIT_ERROR
        self._check_test_commands(plan)
        try:
            launcher: Launcher | None = find_launcher(self.env)
        except LauncherError as exc:
            launcher = None
            self._say(f"phx: warning: {exc}")
        prev = load_state(self.state_dir)
        if prev:
            self.state = RunState(sessions=dict(prev.sessions), wait=prev.wait)
        if prev and prev.pause and not self.options.resume:
            self._say(f"phx: run is paused: {prev.pause.reason} (phx resume clears it)")
        self._say(f"Dry run for {self.repo} ({plan.plan_file}); nothing is launched.")
        steps: list[dict[str, Any]] = []
        end = self._simulate(plan, launcher, steps)
        self._say(f"Then: {end.kind} ({end.reason})")
        self.log.event(
            "dry_run",
            reason=f"would run {len(steps)} phase(s), then {end.kind}: {end.reason}",
            steps=steps,
            end=end.rule,
        )
        return EXIT_FINISHED

    def _simulate(self, plan: Plan, launcher: Launcher | None, steps: list[dict[str, Any]]) -> End:
        """Walk the plan as if each chosen phase completes; append each step to ``steps``."""
        sim = plan
        while True:
            if self.options.max_phases is not None and len(steps) >= self.options.max_phases:
                return End(
                    EndKind.FINISHED, f"--max-phases {self.options.max_phases}", "max_phases"
                )
            elig = next_eligible(sim)
            choice = self._choose(sim, elig.next, elig.resume, live_check=False)
            if isinstance(choice, End):
                return choice
            p = choice.phase
            until = self.options.until
            if until is not None and phase_sort_key(p.id) > phase_sort_key(until):
                return End(EndKind.FINISHED, f"--until {until} reached", "until")
            gate = self._gate_before(p)
            if gate:
                return gate
            try:
                alias = p.require_alias()
            except UnknownModel as exc:
                return End(EndKind.PAUSED, str(exc), "unknown_model", p.id)
            argv: list[str] = []
            if launcher is not None:
                argv = build_argv(
                    launcher,
                    choice.prompt,
                    alias,
                    session_id=None if choice.resume else "<new uuid>",
                    resume=choice.resume,
                )
            steps.append(
                {
                    "phase": p.id,
                    "why": choice.why,
                    "alias": alias,
                    "gate": str(p.gate),
                    "argv": argv,
                }
            )
            self._say(f"  {p.id}  {p.name}  [{alias}, gate {p.gate}]  {choice.why}")
            if argv:
                self._say(f"      {' '.join(argv)}")
            self.state.wait = None
            after = self._gate_after(p)
            if after and after.rule != "max_phases":
                return after
            sim = replace(
                sim,
                phases=tuple(
                    replace(q, status=Status.COMPLETE) if q.id == p.id else q for q in sim.phases
                ),
            )
