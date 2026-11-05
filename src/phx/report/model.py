"""Pure aggregation of the run logs: what was used, what it achieved, per period.

Definitions (the user guide repeats them):

- *Active time*: the sum of ``session_end.duration_s``.
- *Waiting*: usage-limit waits, from ``wait_end.waited_s`` (a wait a stop interrupted
  ends at its ``wait_stopped``). A wait still open at the end of the log is not counted.
- *Paused*: from a ``run_end`` with status ``paused`` to the project's next real
  ``run_start``. ``*_gate`` rules are gate pauses; the rest wait on a block or a repair.
- *Completion*: a ``verify`` with outcome ``complete``, or a ``session_dropped`` that found
  the phase already ✅ (its verification was interrupted, then the resume saw it done),
  after at least one session of that phase. Reporting it again with no session since adds
  none.
- *First-attempt completion*: a completion with exactly one session and no retry or
  timeout.
- *Non-completing spend*: the tokens, cost and time of sessions whose class is not
  ``complete``.

**Attribution (ADR-0033).** ``--resume`` keeps the session ID, and for such a session
Claude Code's ``cost_usd`` and per-model ``usage.models`` are running totals of the whole
chain, while the top-level token counts cover that run only, sometimes only its last
turns. So each ``session_end`` is charged the *increase* in the per-model totals over the
previous report in its chain. A run that left no usable totals (killed, or a limit that
reported zeros) is charged the tokens it summed from its messages with cost unknown;
those tokens are taken off the next increase, which contains them. Its cost cannot be
told apart, so it lands on the next run that reports one.

Unknown cost stays ``None`` and is counted (``sessions_without_cost``); it is never 0.
"""

import calendar
import statistics
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field, fields
from typing import Any

from phx.report.load import Event, Source
from phx.state import now_ts

PERIODS = ("month", "quarter", "year")
GATE_RULES = ("review_gate", "owner_gate")
_KINDS = ("input", "output", "cache_read", "cache_write")
_MODEL_KEYS = {
    "input": "inputTokens",
    "output": "outputTokens",
    "cache_read": "cacheReadInputTokens",
    "cache_write": "cacheCreationInputTokens",
}
_TOP_KEYS = {
    "input": "input_tokens",
    "output": "output_tokens",
    "cache_read": "cache_read_input_tokens",
    "cache_write": "cache_creation_input_tokens",
}
UNKNOWN_MODEL = "unknown"


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _count(value: Any) -> int:
    number = _number(value)
    return int(number) if number is not None and number > 0 else 0


@dataclass
class Tokens:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0

    @property
    def total(self) -> int:
        return self.input + self.output + self.cache_read + self.cache_write

    def add(self, other: "Tokens") -> None:
        for kind in _KINDS:
            setattr(self, kind, getattr(self, kind) + getattr(other, kind))


@dataclass(frozen=True)
class ModelShare:
    """What one session is charged for one model."""

    model: str
    tokens: Tokens
    cost_usd: float | None
    verified: bool  # the cost is a known list price (``costBasis`` list)


@dataclass
class Session:
    project: str
    phase: str
    epoch: float
    session_id: str
    cls: str
    duration_s: float
    alias: str | None = None
    provider: str | None = None
    idle_timeout_s: float | None = None
    wall_timeout_s: float | None = None
    timed_out: str | None = None  # "idle" or "wall" when PHX killed it for that
    shares: list[ModelShare] = field(default_factory=list)
    repeated_cost_usd: float = 0.0  # recorded cost already charged earlier in the chain

    @property
    def tokens(self) -> Tokens:
        out = Tokens()
        for share in self.shares:
            out.add(share.tokens)
        return out

    @property
    def cost_usd(self) -> float | None:
        costs = [s.cost_usd for s in self.shares if s.cost_usd is not None]
        return sum(costs) if costs else None

    @property
    def completing(self) -> bool:
        return self.cls == "complete"

    @property
    def primary_model(self) -> str:
        if not self.shares:
            return UNKNOWN_MODEL
        return max(self.shares, key=lambda s: (s.tokens.total, s.model)).model


@dataclass(frozen=True)
class Mark:
    """One counted thing that is not a session."""

    project: str
    phase: str | None
    epoch: float
    kind: str  # run, completed, first_attempt, retry, timeout, blocked, wait, gate_pause, pause
    seconds: float = 0.0
    start: float | None = None


@dataclass
class Totals:
    """The same figures at every grouping, so every table adds up."""

    runs: int = 0
    sessions: int = 0
    sessions_without_cost: int = 0
    active_s: float = 0.0
    wait_s: float = 0.0
    waits: int = 0
    gate_pause_s: float = 0.0
    gate_pauses: int = 0
    other_pause_s: float = 0.0
    tokens: Tokens = field(default_factory=Tokens)
    cost_usd: float | None = None
    unverified_cost_usd: float = 0.0
    repeated_cost_usd: float = 0.0
    phases_completed: int = 0
    first_attempt: int = 0
    retries: int = 0
    timeouts: int = 0
    blocks: int = 0
    noncompleting_sessions: int = 0
    noncompleting_active_s: float = 0.0
    noncompleting_tokens: int = 0
    noncompleting_cost_usd: float = 0.0

    def add_share(self, share: ModelShare, *, completing: bool) -> None:
        self.tokens.add(share.tokens)
        if not completing:
            self.noncompleting_tokens += share.tokens.total
        if share.cost_usd is None:
            return
        self.cost_usd = (self.cost_usd or 0.0) + share.cost_usd
        if not share.verified:
            self.unverified_cost_usd += share.cost_usd
        if not completing:
            self.noncompleting_cost_usd += share.cost_usd

    def add_session_time(self, session: Session) -> None:
        self.sessions += 1
        self.active_s += session.duration_s
        self.repeated_cost_usd += session.repeated_cost_usd
        if session.cost_usd is None:
            self.sessions_without_cost += 1
        if not session.completing:
            self.noncompleting_sessions += 1
            self.noncompleting_active_s += session.duration_s

    def add_session(self, session: Session) -> None:
        self.add_session_time(session)
        for share in session.shares:
            self.add_share(share, completing=session.completing)

    def add_mark(self, mark: Mark) -> None:
        if mark.kind == "run":
            self.runs += 1
        elif mark.kind == "completed":
            self.phases_completed += 1
        elif mark.kind == "first_attempt":
            self.first_attempt += 1
        elif mark.kind == "retry":
            self.retries += 1
        elif mark.kind == "timeout":
            self.timeouts += 1
        elif mark.kind == "blocked":
            self.blocks += 1
        elif mark.kind == "wait":
            self.waits += 1
            self.wait_s += mark.seconds
        elif mark.kind == "gate_pause":
            self.gate_pauses += 1
            self.gate_pause_s += mark.seconds
        elif mark.kind == "pause":
            self.other_pause_s += mark.seconds

    @property
    def has_data(self) -> bool:
        return bool(self.sessions or self.phases_completed or self.waits or self.runs)

    @property
    def cost_per_phase(self) -> float | None:
        if self.cost_usd is None or not self.phases_completed:
            return None
        return self.cost_usd / self.phases_completed

    @property
    def tokens_per_phase(self) -> float | None:
        return self.tokens.total / self.phases_completed if self.phases_completed else None

    @property
    def active_h_per_phase(self) -> float | None:
        return self.active_s / 3600 / self.phases_completed if self.phases_completed else None

    @property
    def noncompleting_cost_share(self) -> float | None:
        return self.noncompleting_cost_usd / self.cost_usd if self.cost_usd else None

    @property
    def noncompleting_time_share(self) -> float | None:
        return self.noncompleting_active_s / self.active_s if self.active_s else None

    @property
    def cache_read_share(self) -> float | None:
        read = self.tokens.cache_read
        side = self.tokens.input + read + self.tokens.cache_write
        return read / side if side else None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {f.name: getattr(self, f.name) for f in fields(self)}
        out["tokens"] = {kind: getattr(self.tokens, kind) for kind in _KINDS}
        out["tokens"]["total"] = self.tokens.total
        for name in (
            "cost_per_phase",
            "tokens_per_phase",
            "active_h_per_phase",
            "noncompleting_cost_share",
            "noncompleting_time_share",
            "cache_read_share",
        ):
            out[name] = getattr(self, name)
        return out


@dataclass
class _Chain:
    """Running per-model totals of one session ID across its resumes."""

    seen: dict[str, tuple[Tokens, float]] = field(default_factory=dict)
    last_cost: float = 0.0
    carried: Tokens = field(default_factory=Tokens)  # charged already, inside the next totals


def _snapshot(models: Any) -> dict[str, tuple[Tokens, float | None, bool]]:
    """``usage.models`` as model -> (tokens, cost, verified), without malformed entries."""
    if not isinstance(models, dict):
        return {}
    out: dict[str, tuple[Tokens, float | None, bool]] = {}
    for name, entry in models.items():
        if not isinstance(name, str) or not isinstance(entry, dict):
            continue
        tokens = Tokens(**{k: _count(entry.get(key)) for k, key in _MODEL_KEYS.items()})
        basis = entry.get("costBasis")
        # Records from before Claude Code wrote costBasis: only its own models had a price.
        verified = basis == "list" or (basis is None and name.startswith("claude-"))
        out[name] = (tokens, _number(entry.get("costUSD")), verified)
    return out


def _take_carried(tokens: Tokens, chain: _Chain) -> None:
    """Remove from ``tokens`` what an earlier run of the chain was charged already."""
    for kind in _KINDS:
        taken = min(getattr(tokens, kind), getattr(chain.carried, kind))
        setattr(tokens, kind, getattr(tokens, kind) - taken)
        setattr(chain.carried, kind, getattr(chain.carried, kind) - taken)


def _unreported(session: Session) -> str:
    """The model row of a run that named no model: its alias, marked as one."""
    return f"{session.alias} (alias)" if session.alias else UNKNOWN_MODEL


def _charge(session: Session, record: Event, chain: _Chain) -> None:
    """Fill ``session.shares`` with this run's increase over its chain so far."""
    raw = record.get("usage")
    usage: dict[str, Any] = raw if isinstance(raw, dict) else {}
    top = Tokens(**{k: _count(usage.get(key)) for k, key in _TOP_KEYS.items()})
    snapshot = _snapshot(usage.get("models"))
    recorded = _number(record.get("cost_usd"))
    if not sum(tokens.total for tokens, _, _ in snapshot.values()):
        snapshot = {}  # a limit's placeholder entry: all zeros, whatever the run really used
    if not snapshot:
        if top.total or recorded is None or not recorded:
            chain.carried.add(top)
            session.shares = [ModelShare(_unreported(session), top, None, False)]
            return
        cost = max(0.0, recorded - chain.last_cost)
        session.repeated_cost_usd = recorded - cost
        chain.last_cost = max(chain.last_cost, recorded)
        session.shares = [ModelShare(_unreported(session), top, cost, False)]
        return
    repeated = 0.0
    for name in sorted(snapshot):
        tokens, reported, verified = snapshot[name]
        seen_tokens, seen_cost = chain.seen.get(name, (Tokens(), 0.0))
        delta = Tokens(**{k: max(0, getattr(tokens, k) - getattr(seen_tokens, k)) for k in _KINDS})
        _take_carried(delta, chain)
        charged = None if reported is None else max(0.0, reported - seen_cost)
        if reported is not None:
            repeated += min(reported, seen_cost)
        chain.seen[name] = (tokens, max(reported or 0.0, seen_cost))
        if delta.total or charged:
            session.shares.append(ModelShare(name, delta, charged, verified))
    if not session.shares:  # the run added nothing: keep it visible at a known zero
        name = sorted(snapshot)[0]
        session.shares = [ModelShare(name, Tokens(), 0.0, snapshot[name][2])]
    session.repeated_cost_usd = repeated
    chain.last_cost = max(chain.last_cost, recorded or 0.0)


def _alias(argv: Any) -> str | None:
    if isinstance(argv, list) and "--model" in argv:
        at = argv.index("--model") + 1
        alias = argv[at] if at < len(argv) else None
        return alias if isinstance(alias, str) else None
    return None


@dataclass
class Facts:
    """Everything counted, each with its time, before any window is applied."""

    sessions: list[Session] = field(default_factory=list)
    marks: list[Mark] = field(default_factory=list)
    open_spans: int = 0  # waits and pauses still running at the end of the log
    last_epoch: float | None = None


@dataclass
class _Attempt:
    sessions: int = 0
    troubled: bool = False


def extract(source: Source) -> Facts:
    """One project's sessions and marks. All chain state lives here, before filtering."""
    facts = Facts()
    project = source.project
    chains: dict[str, _Chain] = {}
    launches: dict[str, Event] = {}
    attempts: dict[str, _Attempt] = {}
    killed: dict[str, str] = {}
    waits: dict[str, float] = {}
    stopped: dict[str, float] = {}
    paused: tuple[float, str] | None = None

    def mark(phase: str | None, epoch: float, kind: str, seconds: float = 0.0, **kw: Any) -> None:
        facts.marks.append(Mark(project, phase, epoch, kind, seconds, **kw))

    def completed(phase: str, epoch: float) -> None:
        attempt = attempts.pop(phase, None)
        if attempt is None or not attempt.sessions:
            return  # a re-verification, not a new completion
        mark(phase, epoch, "completed")
        if attempt.sessions == 1 and not attempt.troubled:
            mark(phase, epoch, "first_attempt")

    for event in source.events:
        name = event["event"]
        epoch = float(event["epoch"])
        raw_phase = event.get("phase")
        phase = raw_phase if isinstance(raw_phase, str) else None
        facts.last_epoch = epoch if facts.last_epoch is None else max(facts.last_epoch, epoch)
        if name == "launch":
            sid = event.get("session_id")
            if isinstance(sid, str):
                launches[sid] = event
        elif name == "session_end" and phase is not None:
            sid = str(event.get("session_id"))
            launch = launches.get(sid, {})
            session = Session(
                project,
                phase,
                epoch,
                sid,
                str(event.get("class")),
                _number(event.get("duration_s")) or 0.0,
                alias=_alias(launch.get("argv")),
                provider=launch.get("provider")
                if isinstance(launch.get("provider"), str)
                else None,
                idle_timeout_s=_number(launch.get("idle_timeout_s")),
                wall_timeout_s=_number(launch.get("wall_timeout_s")),
                timed_out=killed.pop(phase, None),
            )
            _charge(session, event, chains.setdefault(sid, _Chain()))
            facts.sessions.append(session)
            attempts.setdefault(phase, _Attempt()).sessions += 1
        elif name == "retry" and phase is not None:
            mark(phase, epoch, "retry")
            attempts.setdefault(phase, _Attempt()).troubled = True
        elif name == "timeout" and phase is not None:
            mark(phase, epoch, "timeout")
            reason = str(event.get("reason"))
            killed[phase] = "wall" if reason.startswith("wall") else "idle"
            attempts.setdefault(phase, _Attempt()).troubled = True
        elif name == "verify" and phase is not None:
            outcome = event.get("outcome")
            if outcome == "blocked":
                mark(phase, epoch, "blocked")
            elif outcome == "complete":
                completed(phase, epoch)
        elif name == "session_dropped" and phase is not None:
            if "✅" in str(event.get("reason")):
                completed(phase, epoch)
        elif name == "wait_start" and phase is not None:
            waits.setdefault(phase, epoch)
            stopped.pop(phase, None)
        elif name == "wait_stopped" and phase is not None:
            stopped[phase] = epoch
        elif name == "wait_end" and phase is not None:
            start = waits.pop(phase, None)
            stopped.pop(phase, None)
            waited = _number(event.get("waited_s"))
            if waited is None:
                waited = epoch - start if start is not None else 0.0
            mark(phase, epoch, "wait", waited, start=start)
        elif name == "run_start":
            mark(None, epoch, "run")
            if paused is not None:
                kind = "gate_pause" if paused[1] in GATE_RULES else "pause"
                mark(None, epoch, kind, max(0.0, epoch - paused[0]))
                paused = None
        elif name == "run_end" and event.get("status") == "paused":
            paused = (epoch, str(event.get("rule")))
    for phase, start in waits.items():
        if phase in stopped:
            mark(phase, stopped[phase], "wait", stopped[phase] - start, start=start)
        else:
            facts.open_spans += 1
    facts.open_spans += 1 if paused is not None else 0
    return facts


# --- Periods ------------------------------------------------------------------------


def bucket(epoch: float, by: str) -> str:
    """The local-time period label of ``epoch``: ``2026-11``, ``2026-Q4`` or ``2026``."""
    t = time.localtime(epoch)
    if by == "year":
        return f"{t.tm_year}"
    if by == "quarter":
        return f"{t.tm_year}-Q{(t.tm_mon - 1) // 3 + 1}"
    return f"{t.tm_year}-{t.tm_mon:02d}"


def _labels(first: str, last: str, by: str) -> Iterator[str]:
    """Every period from ``first`` to ``last``, empty ones included."""

    def split(label: str) -> tuple[int, int]:
        year, _, rest = label.partition("-")
        return int(year), int(rest.lstrip("Q") or 1)

    size = {"month": 12, "quarter": 4, "year": 1}[by]
    year, part = split(first)
    end = split(last)
    while (year, part) <= end:
        if by == "year":
            yield f"{year}"
        elif by == "quarter":
            yield f"{year}-Q{part}"
        else:
            yield f"{year}-{part:02d}"
        part += 1
        if part > size:
            year, part = year + 1, 1


def parse_bound(text: str, *, end: bool) -> float:
    """``YYYY-MM-DD``, ``YYYY-MM``, ``YYYY-Qn`` or ``YYYY`` as a local epoch.

    ``end`` gives the first moment after that day or period, so ``--until`` is inclusive.
    """
    value = text.strip()
    parts = value.split("-")
    try:
        year = int(parts[0])
        if len(parts) == 1 and len(value) == 4:
            first, last = (year, 1, 1), (year, 12, 31)
        elif len(parts) == 2 and parts[1].upper().startswith("Q"):
            quarter = int(parts[1][1:])
            if not 1 <= quarter <= 4:
                raise ValueError
            month = quarter * 3
            first = (year, month - 2, 1)
            last = (year, month, calendar.monthrange(year, month)[1])
        elif len(parts) == 2:
            month = int(parts[1])
            first, last = (year, month, 1), (year, month, calendar.monthrange(year, month)[1])
        elif len(parts) == 3:
            first = last = (year, int(parts[1]), int(parts[2]))
        else:
            raise ValueError
        y, m, d = last if end else first
        day = calendar.monthrange(y, m)[1]
        if not 1 <= d <= day:
            raise ValueError
    except (ValueError, IndexError, calendar.IllegalMonthError):
        raise ValueError(f"bad date {text!r}: use YYYY-MM-DD, YYYY-MM, YYYY-Qn or YYYY") from None
    return time.mktime((y, m, d + (1 if end else 0), 0, 0, 0, 0, 0, -1))


# --- The report model ---------------------------------------------------------------

CHANGE_METRICS = (
    "cost_usd",
    "tokens",
    "active_s",
    "phases_completed",
    "cost_per_phase",
    "noncompleting_cost_share",
)


def _metric(totals: Totals, name: str) -> float | None:
    if name == "tokens":
        return float(totals.tokens.total)
    value = getattr(totals, name)
    return None if value is None else float(value)


def change(current: float | None, previous: float | None) -> float | None:
    """Fractional change, or ``None`` (n/a) with nothing or zero to compare against."""
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / previous


@dataclass
class Period:
    label: str
    totals: Totals
    change: dict[str, float | None]
    models: dict[str, float]  # model -> cost in this period


@dataclass
class PhaseUse:
    project: str
    phase: str
    alias: str | None
    model: str
    provider: str | None
    totals: Totals


@dataclass(frozen=True)
class PhaseWork:
    """One phase active in the report's window (Phase 12g)."""

    phase: str
    name: str | None  # from the plan; None if the plan has no such row
    source: str  # "phx", or "manual" with no ``phx`` session in the window: time only
    started: str
    finished: str | None
    finished_in_period: bool


@dataclass(frozen=True)
class ProjectSummary:
    """What a project is and what was worked on; apart from every resource figure."""

    project: str
    repo_found: bool
    description: str | None
    description_note: str | None  # why there is no description
    phases: list[PhaseWork]


@dataclass
class Report:
    by: str
    projects: list[str]
    since: str | None
    until: str | None
    data_through: float | None
    totals: Totals
    periods: list[Period]
    by_project: dict[str, Totals]
    by_model: dict[str, Totals]
    by_provider: dict[str, Totals]
    phases: list[PhaseUse]
    sessions: list[Session]
    marks: list[Mark]
    open_spans: int
    warnings: list[str] = field(default_factory=list)
    summaries: list[ProjectSummary] | None = None  # None: repos were not read (--no-repos)

    @property
    def as_of(self) -> str:
        """The newest record's time: output depends on the logs, not on the clock."""
        return now_ts(self.data_through) if self.data_through is not None else "no data"


def median(values: Iterable[float]) -> float | None:
    items = list(values)
    return statistics.median(items) if items else None


def build(
    sources: list[Source],
    *,
    by: str = "month",
    since: str | None = None,
    until: str | None = None,
    warnings: list[str] | None = None,
) -> Report:
    start = parse_bound(since, end=False) if since else None
    stop = parse_bound(until, end=True) if until else None
    if start is not None and stop is not None and start >= stop:
        raise ValueError(f"--since {since} is after --until {until}")

    def inside(epoch: float) -> bool:
        return (start is None or epoch >= start) and (stop is None or epoch < stop)

    sessions: list[Session] = []
    marks: list[Mark] = []
    open_spans = 0
    last: float | None = None
    for source in sources:
        facts = extract(source)
        sessions += [s for s in facts.sessions if inside(s.epoch)]
        marks += [m for m in facts.marks if inside(m.epoch)]
        open_spans += facts.open_spans
    epochs = [s.epoch for s in sessions] + [m.epoch for m in marks]
    last = max(epochs) if epochs else None

    totals = Totals()
    by_project: dict[str, Totals] = {s.project: Totals() for s in sources}
    by_model: dict[str, Totals] = {}
    by_provider: dict[str, Totals] = {}
    rows: dict[str, Totals] = {}
    if epochs:
        first_label, last_label = bucket(min(epochs), by), bucket(max(epochs), by)
        rows = {label: Totals() for label in _labels(first_label, last_label, by)}
    costs: dict[str, dict[str, float]] = {label: {} for label in rows}
    groups: dict[tuple[str, str], list[Session]] = {}
    for session in sessions:
        label = bucket(session.epoch, by)
        totals.add_session(session)
        by_project[session.project].add_session(session)
        rows[label].add_session(session)
        provider = session.provider or "unknown"
        by_provider.setdefault(provider, Totals()).add_session(session)
        by_model.setdefault(session.primary_model, Totals()).add_session_time(session)
        for share in session.shares:
            by_model.setdefault(share.model, Totals()).add_share(
                share, completing=session.completing
            )
            if share.cost_usd:
                bucket_costs = costs[label]
                bucket_costs[share.model] = bucket_costs.get(share.model, 0.0) + share.cost_usd
        groups.setdefault((session.project, session.phase), []).append(session)

    phases: dict[tuple[str, str], PhaseUse] = {}
    for key, runs in groups.items():
        use = Totals()
        for session in runs:
            use.add_session(session)
        lead = max(runs, key=lambda s: s.tokens.total)
        phases[key] = PhaseUse(
            key[0], key[1], runs[0].alias, lead.primary_model, lead.provider, use
        )

    for item in marks:
        totals.add_mark(item)
        by_project[item.project].add_mark(item)
        rows[bucket(item.epoch, by)].add_mark(item)
        use_row = phases.get((item.project, item.phase)) if item.phase else None
        if use_row is not None:
            use_row.totals.add_mark(item)
            by_model.setdefault(use_row.model, Totals()).add_mark(item)
            by_provider.setdefault(use_row.provider or "unknown", Totals()).add_mark(item)

    periods: list[Period] = []
    previous: Totals | None = None
    for label, row in rows.items():
        moved = {
            name: change(_metric(row, name), _metric(previous, name)) if previous else None
            for name in CHANGE_METRICS
        }
        if not row.has_data:
            moved = dict.fromkeys(CHANGE_METRICS)
        periods.append(Period(label, row, moved, costs[label]))
        previous = row if row.has_data else None

    return Report(
        by,
        [s.project for s in sources],
        since,
        until,
        last,
        totals,
        periods,
        by_project,
        by_model,
        by_provider,
        sorted(
            phases.values(),
            key=lambda p: (-(p.totals.cost_usd or 0.0), p.project, p.phase),
        ),
        sessions,
        marks,
        open_spans,
        warnings or [],
    )
