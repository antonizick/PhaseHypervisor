"""``state.json``: the supervisor's run state, written atomically (spec R10, R14).

It answers "where is the run and why" for ``phx status`` and lets a new supervisor pick
up after a stop, crash or reboot: the current phase, its last session ID (resumed with
``--resume`` when PHX started it, R14), a pending usage-limit wait, a pause and the
token and cost totals.
"""

import json
import os
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from phx.progress import ProgressSnapshot

STATE_FILE = "state.json"


class RunStatus:
    RUNNING = "running"  # a phase session is (or is about to be) running
    WAITING = "waiting"  # usage-limit wait
    PAUSED = "paused"  # needs Nick; cleared by `phx resume`
    STOPPED = "stopped"  # `phx stop` or a signal; the phase stays resumable
    FINISHED = "finished"  # nothing left to run, or --until / --max-phases reached
    FAILED = "failed"  # the supervisor itself could not continue (plan unreadable…)


@dataclass
class PhaseTotals:
    """Per-phase accounting for this run."""

    sessions: int = 0
    tokens: int = 0
    cost_usd: float = 0.0
    wait_s: float = 0.0
    outcome: str | None = None  # last decision rule: complete, blocked, usage_limit, …
    wall_s: float = 0.0  # session wall time (the ETA fallback sample, Phase 12d)


@dataclass
class Pause:
    reason: str
    rule: str
    phase: str | None = None
    at: str | None = None
    question_ids: list[str] = field(default_factory=list)
    summary: str | None = None


@dataclass
class Wait:
    """A usage-limit wait that a later supervisor must finish before resuming."""

    phase: str
    session_id: str | None
    prompt: str | None
    until: float  # wall-clock epoch to wake at (before the probe)
    reason: str
    reset_at: str | None = None
    backoff_step: int = 0  # index into the no-reset-time back-off schedule
    provider: str | None = None  # provider when the limit hit
    started: float = 0.0


@dataclass
class Progress:
    """What the current session is doing, refreshed through the heartbeat (Phase 12d).

    Optional on :class:`RunState`: a ``state.json`` written before Phase 12d simply
    has none. Ages (``last_event``, ``since``) are epochs so ``phx status`` and
    ``phx watch`` compute "how long ago" at read time.
    """

    phase: str | None = None
    attempt: int = 0
    stage: str = "unknown"  # starting | working | testing | finishing | unknown | waiting
    activity: str | None = None  # "editing src/phx/supervisor.py", or the wait message
    last_tool: str | None = None
    last_text: str | None = None
    steps: int = 0
    tools: dict[str, int] = field(default_factory=dict)
    tokens: int = 0
    cost_usd: float | None = None
    since: float | None = None  # session start, wall epoch
    last_event: float | None = None  # last stream event, wall epoch
    elapsed_s: float = 0.0
    eta: str = ""
    stall_after_s: float = 0.0  # quiet seconds before the line is suspicious
    in_flight: str | None = None

    @classmethod
    def from_snapshot(cls, snap: "ProgressSnapshot") -> "Progress":
        return cls(
            phase=snap.phase,
            attempt=snap.attempt,
            stage=snap.stage,
            activity=snap.activity,
            last_tool=snap.last_tool,
            last_text=snap.last_text,
            steps=snap.steps,
            tools=dict(snap.tools),
            tokens=snap.tokens,
            cost_usd=snap.cost_usd,
            since=snap.since_wall,
            last_event=snap.last_event_wall,
            elapsed_s=snap.elapsed_s,
            eta=snap.eta,
            stall_after_s=snap.stall_after_s,
            in_flight=snap.in_flight,
        )


@dataclass
class RunState:
    run_id: str = ""
    repo: str = ""
    status: str = RunStatus.FINISHED
    pid: int | None = None
    unit: str | None = None
    started: str | None = None
    updated: str | None = None
    phase: str | None = None
    attempt: int = 0  # launches for the current phase in this run (resumes included)
    recoveries: int = 0  # timeout/crash recoveries of the current phase (Phase 06)
    session_id: str | None = None
    classification: str | None = None  # class of the last session
    provider: str | None = None  # provider at the last launch
    last_event: str | None = None  # time of the last stream event (heartbeat)
    wait: Wait | None = None
    pause: Pause | None = None
    progress: Progress | None = None  # live session activity (Phase 12d)
    sessions: dict[str, str] = field(default_factory=dict)  # phase -> last PHX session ID
    phases: dict[str, PhaseTotals] = field(default_factory=dict)
    tokens: int = 0
    cost_usd: float = 0.0
    completed: list[str] = field(default_factory=list)  # phases completed in this run
    end_reason: str | None = None

    def totals(self, phase: str) -> PhaseTotals:
        return self.phases.setdefault(phase, PhaseTotals())

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "RunState":
        known = {f.name for f in fields(cls)}
        values = {k: v for k, v in data.items() if k in known}
        if isinstance(values.get("wait"), dict):
            values["wait"] = _build(Wait, values["wait"])
        if isinstance(values.get("pause"), dict):
            values["pause"] = _build(Pause, values["pause"])
        if isinstance(values.get("progress"), dict):
            values["progress"] = _build(Progress, values["progress"])
        values["phases"] = {
            k: _build(PhaseTotals, v)
            for k, v in (values.get("phases") or {}).items()
            if isinstance(v, dict)
        }
        return cls(**values)


def _build[T](cls: type[T], data: dict[str, Any]) -> T:
    known = {f.name for f in fields(cls)}  # type: ignore[arg-type]
    return cls(**{k: v for k, v in data.items() if k in known})


def now_ts(epoch: float | None = None) -> str:
    """``YYYY-MM-DD HH:MM TZ`` (the project's timestamp format)."""
    return time.strftime("%Y-%m-%d %H:%M %Z", time.localtime(epoch))


def state_path(state_dir: Path) -> Path:
    return state_dir / STATE_FILE


def load_state(state_dir: Path) -> RunState | None:
    """The saved state, or ``None`` if there is none or it is unreadable."""
    path = state_path(state_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return RunState.from_json(data)
    except TypeError:
        return None


def save_state(state_dir: Path, state: RunState) -> None:
    """Write ``state.json`` atomically: temp file, fsync, rename.

    A failed write (full disk) removes its temp file and raises ``OSError``; the old
    ``state.json`` stays intact. A temp file left by a supervisor killed mid-write
    (``kill -9``) is never read and is removed by the next successful save.
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    state.updated = now_ts()
    path = state_path(state_dir)
    tmp = path.with_name(f".{STATE_FILE}.{os.getpid()}.tmp")
    data = (json.dumps(state.to_json(), ensure_ascii=False, indent=2) + "\n").encode()
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view) :]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    for stale in state_dir.glob(f".{STATE_FILE}.*.tmp"):
        stale.unlink(missing_ok=True)
