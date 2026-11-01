"""Live progress of one phase session: what it is doing and how it is going (Phase 12d).

Everything here is derived from stream-json events the runner already parses, at zero
token cost (ADR-0028): no model is ever asked for a status or an ETA. The tracker is
pure parsing over :meth:`ProgressTracker.feed` plus clock reads; it never raises on a
malformed event.

Counting choice (phase ADR): a step is a **completed** ``tool_result``, not a
``tool_use`` — one step means work actually finished, so a long-running command counts
once and a rejected call does not pad the count. The stage is a coarse label from the
tool trail: ``starting`` before the first tool, ``testing``/``finishing`` when the most
recent tool (or the last text) says so, ``working`` otherwise, ``unknown`` when the
trail gives nothing at all.

The ETA is always a range with its sample size — a ``~``-qualified median, widened to
``low to high`` when the sample is wide — or the explicit ``no estimate yet``. A wide or
missing estimate is correct behaviour; a confident wrong one is not.
"""

import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from phx.redact import redact_text

TOOL_BUCKETS: tuple[str, ...] = ("edit", "write", "bash", "read", "grep", "glob", "other")

_BUCKET_BY_TOOL: dict[str, str] = {
    "Edit": "edit",
    "MultiEdit": "edit",
    "NotebookEdit": "edit",
    "Write": "write",
    "Bash": "bash",
    "Read": "read",
    "Grep": "grep",
    "Glob": "glob",
}

_TEST_RE = re.compile(
    r"\b(?:pytest|tox|ruff|mypy|pyright|flake8|pylint|unittest|pre-commit|shellcheck|"
    r"npm\s+(?:test|run\s+\S*test)|yarn\s+(?:test|check)|jest|vitest|tsc|"
    r"make\s+(?:check|test|lint)|go\s+test|cargo\s+(?:test|check|clippy))\b",
    re.I,
)
_FINISH_RE = re.compile(
    r"\bgit\s+(?:commit|merge|push|rebase|tag|cherry-pick)\b|\bclose[- ]out\b", re.I
)
_CLOSE_OUT_RE = re.compile(r"\bclose[- ]out\b", re.I)

_TS = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}(?: [A-Z]{2,4})?"
_BULLET_START = re.compile(r"started (" + _TS + r")")
_BULLET_FINISH = re.compile(r"finished (" + _TS + r")")
_BULLET_BLOCKED = re.compile(r"blocked (" + _TS + r") to (" + _TS + r")")
_PHASE_HEADING = re.compile(r"^### .*: Phase \d+[a-z]?:")

DESC_LIMIT = 80
TEXT_LIMIT = 120


# --------------------------------------------------------------------------- formatting


def fmt_dur(seconds: float) -> str:
    """``45s`` / ``25m`` / ``1h 20m`` — one tidy duration string."""
    seconds = max(0.0, seconds)
    if seconds < 90:
        return f"{seconds:.0f}s"
    minutes = round(seconds / 60.0)
    if minutes < 100:
        return f"{minutes}m"
    return f"{minutes // 60}h {minutes % 60:02d}m"


def fmt_tokens(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 10_000:
        return f"{value / 1_000:.0f}k"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return str(value)


def median(values: Sequence[float]) -> float | None:
    """The middle sample (mean of the two middles for even counts); ``None`` when empty."""
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _quantile(ordered: Sequence[float], q: float) -> float:
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    pos = q * (len(ordered) - 1)
    low = int(pos)
    frac = pos - low
    if low + 1 >= len(ordered):
        return ordered[low]
    return ordered[low] + frac * (ordered[low + 1] - ordered[low])


def eta_text(durations: Sequence[float], elapsed_s: float, stage: str = "") -> str:
    """``~25m of ~80m typical left (median of 9 phases)``, or an honest admission.

    ``durations`` are the wall times of phases already completed in this plan. The
    spread of the sample widens the range; ``testing``/``finishing`` add a plain-language
    hint instead of shrinking the number (ADR-0028).
    """
    typical = median(durations)
    if typical is None:
        return "no estimate yet (first phase in this plan)"
    if typical < 90.0:
        # a sample of seconds (a synthetic or interrupted run) says nothing about a phase
        return "no useful estimate yet (completed phases are too short to compare)"
    ordered = sorted(durations)
    left = max(0.0, typical - elapsed_s)
    low = max(0.0, _quantile(ordered, 0.25) - elapsed_s)
    high = max(0.0, _quantile(ordered, 0.75) - elapsed_s)
    if high - low >= max(300.0, low * 0.5):
        span = f"~{fmt_dur(low)} to ~{fmt_dur(high)}"
    else:
        span = f"~{fmt_dur(left)}"
    text = (
        f"{span} of ~{fmt_dur(typical)} typical left "
        f"(median of {len(durations)} phase{'s' if len(durations) != 1 else ''})"
    )
    if stage == "testing":
        text += " · testing now, usually near the end"
    elif stage == "finishing":
        text += " · finishing, usually near the end"
    return text


# --------------------------------------------------------------------------- plan timings


def _parse_ts(text: str) -> float | None:
    """Epoch of a ``YYYY-MM-DD HH:MM TZ`` stamp (the zone is ignored: pairs share it)."""
    try:
        return time.mktime(time.strptime(text[:16], "%Y-%m-%d %H:%M"))
    except ValueError:
        return None


def plan_durations(text: str) -> list[float]:
    """Active wall seconds of completed phases, from the plan's Phase Log Timeline bullets.

    Only ``### …: Phase NN:`` entries count (not planning entries); a bullet needs both
    ``started`` and ``finished``; blocked spans are subtracted, like the timeline's
    "Active" column. This is the same source the timeline generator reads.
    """
    durations: list[float] = []
    is_phase = False
    for line in text.splitlines():
        if line.startswith("### "):
            is_phase = bool(_PHASE_HEADING.match(line))
            continue
        if not is_phase or "**Timeline:**" not in line:
            continue
        start, finish = _BULLET_START.search(line), _BULLET_FINISH.search(line)
        if not start or not finish:
            continue
        t0, t1 = _parse_ts(start.group(1)), _parse_ts(finish.group(1))
        if t0 is None or t1 is None:
            continue
        blocked = 0.0
        for b0, b1 in _BULLET_BLOCKED.findall(line):
            a, b = _parse_ts(b0), _parse_ts(b1)
            if a is not None and b is not None:
                blocked += max(0.0, b - a)
        span = t1 - t0 - blocked
        if span > 0:
            durations.append(span)
    return durations


def eta_durations(plan_text: str | None, completed_wall_s: Sequence[float] = ()) -> list[float]:
    """The ETA sample: the plan's Phase Log bullets, else phases completed in this run."""
    from_log = plan_durations(plan_text or "")
    return from_log or [s for s in completed_wall_s if s > 0]


# --------------------------------------------------------------------------- snapshots


@dataclass(frozen=True)
class ProgressSnapshot:
    """What one session is doing right now, as far as the stream shows."""

    phase: str
    attempt: int = 1
    stage: str = "unknown"
    tool_name: str | None = None
    tool_desc: str | None = None  # redacted, truncated to DESC_LIMIT
    last_text: str | None = None  # redacted, truncated to TEXT_LIMIT
    steps: int = 0
    tools: Mapping[str, int] = field(default_factory=dict)
    tokens: int = 0
    cost_usd: float | None = None
    since_wall: float = 0.0
    last_event_wall: float | None = None
    elapsed_s: float = 0.0
    eta: str = ""
    stalled_for_s: float | None = None
    stall_after_s: float = 0.0
    in_flight: str | None = None  # e.g. "running uv run pytest (6m)"

    @property
    def last_tool(self) -> str | None:
        if self.tool_name is None:
            return None
        return f"{self.tool_name} {self.tool_desc}".strip()

    @property
    def activity(self) -> str:
        return activity_line(self)


def activity_line(snap: ProgressSnapshot) -> str:
    """``editing src/phx/supervisor.py`` — what the session is on right now."""
    if snap.tool_name is not None:
        verb = {
            "edit": "editing",
            "write": "writing",
            "bash": "running",
            "read": "reading",
            "grep": "searching",
            "glob": "searching",
        }.get(_BUCKET_BY_TOOL.get(snap.tool_name, "other"), "using")
        return (
            f"{verb} {snap.tool_desc}".strip() if snap.tool_desc else f"{verb} ({snap.tool_name})"
        )
    if snap.last_text:
        return f"writing: {snap.last_text}"
    return "no activity yet"


def progress_reason(snap: ProgressSnapshot) -> str:
    """One self-contained line for ``phx log`` (ADR-0028)."""
    counts = ", ".join(f"{n} {b}" for b in TOOL_BUCKETS if (n := snap.tools.get(b)))
    steps = f"{snap.steps} steps ({counts})" if counts else f"{snap.steps} steps"
    money = f"{fmt_tokens(snap.tokens)} tokens"
    if snap.cost_usd is not None:
        money += f", ${snap.cost_usd:.2f}"
    return " · ".join(
        (
            f"phase {snap.phase} attempt {snap.attempt}, {fmt_dur(snap.elapsed_s)} elapsed",
            snap.activity,
            steps,
            money,
            snap.eta,
        )
    )


def progress_fields(snap: ProgressSnapshot) -> dict[str, Any]:
    """The structured half of the ``progress`` event (``phx log --json``)."""
    age = None
    if snap.last_event_wall is not None:
        age = round(max(0.0, time.time() - snap.last_event_wall), 1)
    return {
        "attempt": snap.attempt,
        "stage": snap.stage,
        "last_tool": snap.last_tool,
        "last_text": snap.last_text,
        "steps": snap.steps,
        "tools": dict(snap.tools),
        "tokens": snap.tokens,
        "cost_usd": snap.cost_usd,
        "elapsed_s": round(snap.elapsed_s, 1),
        "last_event_age_s": age,
        "eta": snap.eta,
        "stalled_for_s": snap.stalled_for_s,
    }


# --------------------------------------------------------------------------- tracker


class ProgressTracker:
    """Derives :class:`ProgressSnapshot` from stream events. Never raises."""

    def __init__(
        self,
        *,
        phase: str,
        attempt: int = 1,
        started_wall: float | None = None,
        durations: Sequence[float] = (),
        idle_timeout_s: float = 1800.0,
        interval_s: float = 300.0,
        monotonic: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
    ) -> None:
        self.phase = phase
        self.attempt = attempt
        self.durations = list(durations)
        self.idle_timeout_s = idle_timeout_s
        self.stall_after_s = max(1.0, idle_timeout_s / 2.0)  # half the idle timeout
        self.interval_s = max(0.001, interval_s)
        self._mono = monotonic
        self._wall = wall
        self._started_wall = started_wall if started_wall is not None else wall()
        self._started_mono = monotonic()
        self._last_event_mono: float | None = None
        self._last_event_wall: float | None = None
        self._events = 0
        self._steps = 0
        self._tools: dict[str, int] = dict.fromkeys(TOOL_BUCKETS, 0)
        self._usage: dict[str, Mapping[str, Any]] = {}
        self._cost: float | None = None
        self._pending: dict[str, tuple[str, str, float]] = {}
        self._last_tool: tuple[str, str] | None = None
        self._last_tool_seq = -1
        self._last_text: str | None = None
        self._last_text_seq = -1
        self._seq = 0
        self._warned = False

    # --- feeding ----------------------------------------------------------------------

    def feed(self, event: Mapping[str, Any]) -> None:
        """Fold one stream event in. A malformed event is ignored, never fatal."""
        try:
            self._feed(event)
        except Exception:  # observability must never break a run
            return

    def _feed(self, event: Mapping[str, Any]) -> None:
        self._seq += 1
        self._events += 1
        self._last_event_mono = self._mono()
        self._last_event_wall = self._wall()
        self._warned = False  # a new quiet spell may warn again
        kind = event.get("type")
        if kind == "result":
            cost = event.get("total_cost_usd")
            if isinstance(cost, int | float) and not isinstance(cost, bool):
                self._cost = float(cost)
            return
        if kind == "assistant":
            message = event.get("message")
            if not isinstance(message, dict):
                return
            usage = message.get("usage")
            if isinstance(usage, dict):
                self._usage[str(message.get("id"))] = usage
            content = message.get("content")
            if isinstance(content, list):
                for block in content:
                    self._assistant_block(block)
            return
        if kind == "user":
            message = event.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, list):
                for block in content:
                    self._user_block(block)

    def _assistant_block(self, block: Any) -> None:
        if not isinstance(block, dict):
            return
        btype = block.get("type")
        if btype == "tool_use":
            name = str(block.get("name") or "unknown")
            desc = _tool_description(name, block.get("input"))
            self._pending[str(block.get("id") or f"anon-{self._seq}")] = (name, desc, self._mono())
            self._last_tool = (name, desc)
            self._last_tool_seq = self._seq
        elif btype in ("text", "thinking"):
            raw = block.get("text") if btype == "text" else block.get("thinking")
            if isinstance(raw, str) and raw.strip():
                self._last_text = redact_text(" ".join(raw.split()))[:TEXT_LIMIT]
                self._last_text_seq = self._seq

    def _user_block(self, block: Any) -> None:
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            return
        name, _desc, _at = self._pending.pop(
            str(block.get("tool_use_id") or ""), ("other", "", 0.0)
        )
        self._tools[_BUCKET_BY_TOOL.get(name, "other")] += 1
        self._steps += 1

    # --- derived state ------------------------------------------------------------------

    @property
    def tokens(self) -> int:
        """Per-message usage summed and deduped by message id, like ``Usage.from_messages``."""

        def total(key: str) -> int:
            return sum(
                v for u in self._usage.values() if isinstance(v := u.get(key), int) and v >= 0
            )

        return (
            total("input_tokens")
            + total("output_tokens")
            + total("cache_creation_input_tokens")
            + total("cache_read_input_tokens")
        )

    @property
    def stage(self) -> str:
        if self._last_tool is not None:
            desc = self._last_tool[1]
            if (
                self._last_text_seq > self._last_tool_seq
                and self._last_text
                and _CLOSE_OUT_RE.search(self._last_text)
            ):
                return "finishing"
            if _FINISH_RE.search(desc):
                return "finishing"
            if _TEST_RE.search(desc):
                return "testing"
            return "working"
        if self._last_text is None:
            return "unknown"
        return "finishing" if _CLOSE_OUT_RE.search(self._last_text) else "starting"

    def _in_flight(self) -> tuple[str, float] | None:
        for name, desc, at in self._pending.values():
            return (f"running {desc}".strip() if desc else f"running {name}", at)
        return None

    def snapshot(self) -> ProgressSnapshot:
        now_mono = self._mono()
        quiet = max(0.0, now_mono - (self._last_event_mono or self._started_mono))
        tool = self._last_tool
        flight = self._in_flight()
        in_flight = None
        if flight is not None:
            label, at = flight
            in_flight = f"{label} ({fmt_dur(now_mono - at)})"
        return ProgressSnapshot(
            phase=self.phase,
            attempt=self.attempt,
            stage=self.stage,
            tool_name=tool[0] if tool else None,
            tool_desc=tool[1] if tool else None,
            last_text=self._last_text,
            steps=self._steps,
            tools=dict(self._tools),
            tokens=self.tokens,
            cost_usd=self._cost,
            since_wall=self._started_wall,
            last_event_wall=self._last_event_wall,
            elapsed_s=max(0.0, now_mono - self._started_mono),
            eta=eta_text(self.durations, now_mono - self._started_mono, self.stage),
            stalled_for_s=round(quiet, 1) if quiet >= self.stall_after_s else None,
            stall_after_s=self.stall_after_s,
            in_flight=in_flight,
        )

    # --- stall warning ------------------------------------------------------------------

    def stall_warning(self) -> dict[str, Any] | None:
        """Once per quiet spell: the fields and ``reason`` of a ``warning`` event.

        Returns ``None`` while events flow. Fires at half the idle timeout — well before
        the timeout kills the session — and names the tool in flight so a long test
        command is not mistaken for a hang (ADR-0028).
        """
        if self._warned:
            return None
        quiet = self._mono() - (self._last_event_mono or self._started_mono)
        if quiet < self.stall_after_s:
            return None
        self._warned = True
        flight = self._in_flight()
        if flight is not None:
            reason = (
                f"{flight[0]} ({fmt_dur(self._mono() - flight[1])}) — no event for {fmt_dur(quiet)}"
            )
        else:
            reason = (
                f"no event for {fmt_dur(quiet)} "
                f"(idle timeout at {fmt_dur(self.idle_timeout_s)} will kill the session)"
            )
        return {
            "reason": reason,
            "stalled_for_s": round(quiet, 1),
            "stall_after_s": round(self.stall_after_s, 1),
            "idle_timeout_s": round(self.idle_timeout_s, 1),
            "tool": flight[0] if flight else None,
        }


def _tool_description(name: str, raw: Any) -> str:
    """A short, redacted one-liner for the tool call: the file or the command."""
    key = {
        "Edit": "file_path",
        "MultiEdit": "file_path",
        "NotebookEdit": "notebook_path",
        "Write": "file_path",
        "Read": "file_path",
        "Grep": "pattern",
        "Glob": "pattern",
        "Bash": "command",
    }.get(name)
    text = ""
    if key and isinstance(raw, dict):
        value = raw.get(key)
        if isinstance(value, str):
            text = value
    elif isinstance(raw, dict):
        text = str(raw.get("description") or "")
    text = redact_text(" ".join(text.split()))
    return text[:DESC_LIMIT]
