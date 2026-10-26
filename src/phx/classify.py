"""Exit classification for one Claude Code session (spec R8, ADR-0009).

Pure functions over what the runner saw: the exit code, the stream-json ``result``
event, the last events and the tail of stderr. No I/O, so every class is testable
from fixtures. Evidence for the usage-limit shapes is in ADR-0009 and
``tests/fixtures/streams/README.md``.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ExitClass(StrEnum):
    COMPLETE = "complete"
    BLOCKED = "blocked"
    REFUSED = "refused"
    NO_RESULT = "no_result"  # ended cleanly without a valid PHX-RESULT line
    USAGE_LIMIT = "usage_limit"
    AUTH_ERROR = "auth_error"
    PROVIDER_ERROR = "provider_error"
    TIMEOUT = "timeout"
    CRASH = "crash"


@dataclass(frozen=True)
class PhxResult:
    """A parsed ``PHX-RESULT`` line (contract §6)."""

    contract: int
    phase: str | None
    status: str
    reason: str
    merged: bool
    pushed: bool
    question_ids: tuple[str, ...]


@dataclass(frozen=True)
class Classification:
    cls: ExitClass
    reason: str
    reset_at: datetime | None = None  # usage_limit only, local time, aware
    kind: str | None = None  # provider_error kind, or the limit type for usage_limit
    result: PhxResult | None = None
    api_error: dict[str, Any] = field(default_factory=dict)

    def as_log(self) -> dict[str, Any]:
        """JSON-ready fields for ``run.jsonl``."""
        return {
            "class": str(self.cls),
            "class_reason": self.reason,
            "reset_at": self.reset_at.isoformat() if self.reset_at else None,
            "kind": self.kind,
            "result_line": None if self.result is None else self.result.__dict__,
            "api_error": self.api_error or None,
        }


# --- PHX-RESULT line (contract §6) -------------------------------------------------

RESULT_LINE = re.compile(r"^PHX-RESULT: (\{.*\})$")
_RESULT_STATUSES = ("complete", "blocked", "refused")


def parse_result_line(text: str | None) -> PhxResult | None:
    """The last ``PHX-RESULT`` line in ``text``, or ``None`` if missing or malformed.

    The last matching line wins; if that line is malformed there is no result line
    (an earlier valid one is not used).
    """
    if not text:
        return None
    last: str | None = None
    for line in text.splitlines():
        match = RESULT_LINE.match(line.strip())
        if match:
            last = match.group(1)
    if last is None:
        return None
    try:
        data = json.loads(last)
    except ValueError:
        return None
    return _validate_result(data)


def _validate_result(data: Any) -> PhxResult | None:
    if not isinstance(data, dict):
        return None
    contract = data.get("contract")
    phase = data.get("phase")
    status = data.get("status")
    reason = data.get("reason")
    merged = data.get("merged")
    pushed = data.get("pushed")
    qids = data.get("question_ids")
    if not (isinstance(contract, int) and not isinstance(contract, bool)):
        return None
    if not (phase is None or isinstance(phase, str)):
        return None
    if status not in _RESULT_STATUSES or not isinstance(reason, str):
        return None
    if not (isinstance(merged, bool) and isinstance(pushed, bool)):
        return None
    if not (isinstance(qids, list) and all(isinstance(q, str) for q in qids)):
        return None
    return PhxResult(contract, phase, status, reason, merged, pushed, tuple(qids))


# --- Reset times ------------------------------------------------------------------

# Claude Code 2.1.310 composes "You've hit your <limit>[ · resets <when>][ · progress saved]"
# where <when> is "7:40pm", "10pm", "Oct 28, 9am" or "Jan 2, 2027, 9:30am", optionally
# followed by " (America/Chicago)"; the fast-mode variant says "resets in 3h 20m".
LIMIT_TEXT = re.compile(r"You've hit your ([^·\n]+?)\s*(?:·|$)", re.MULTILINE)
_RESETS = re.compile(r"resets\s+(?P<when>[^·\n(]+?)\s*(?:\((?P<tz>[A-Za-z0-9_+\-/]+)\))?\s*(?:·|$)")
_IN = re.compile(r"^in\s+(?P<spec>(?:\d+\s*[dhms]\s*)+)$", re.IGNORECASE)
_PART = re.compile(r"(\d+)\s*([dhms])", re.IGNORECASE)
_CLOCK = r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>[ap]m)"
_TIME_ONLY = re.compile(rf"^{_CLOCK}$", re.IGNORECASE)
_DATE = re.compile(
    rf"^(?P<mon>[A-Za-z]{{3}})\s+(?P<day>\d{{1,2}})(?:,\s*(?P<year>\d{{4}}))?(?:,\s*{_CLOCK})?$",
    re.IGNORECASE,
)
_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
    )
}


def _zone(name: str | None) -> ZoneInfo | None:
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def parse_reset(text: str, now: datetime | None = None) -> datetime | None:
    """Parse the reset time from a limit message, as an aware local datetime.

    ``now`` must be aware if given. A time without a date is the next occurrence; a
    date without a year that is more than a day in the past rolls to next year.
    """
    now = now or datetime.now(UTC)
    match = _RESETS.search(text)
    if not match:
        return None
    when = match.group("when").strip().rstrip(",")
    tz = _zone(match.group("tz"))
    local_now = now.astimezone(tz) if tz else now.astimezone()
    zone = local_now.tzinfo

    rel = _IN.match(when)
    if rel:
        units = {"d": "days", "h": "hours", "m": "minutes", "s": "seconds"}
        delta = timedelta()
        for amount, unit in _PART.findall(rel.group("spec")):
            delta += timedelta(**{units[unit.lower()]: int(amount)})
        return (now + delta).astimezone()

    clock = _TIME_ONLY.match(when)
    if clock:
        hour, minute = _hour_minute(clock)
        cand = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if cand < local_now - timedelta(minutes=1):
            cand = (cand + timedelta(days=1)).replace(hour=hour, minute=minute)
        return cand.astimezone()

    date = _DATE.match(when)
    if date:
        month = _MONTHS.get(date.group("mon").lower())
        if month is None:
            return None
        hour, minute = _hour_minute(date) if date.group("hour") else (0, 0)
        year = int(date.group("year")) if date.group("year") else local_now.year
        try:
            cand = datetime(year, month, int(date.group("day")), hour, minute, tzinfo=zone)
        except ValueError:
            return None
        if not date.group("year") and cand < local_now - timedelta(days=1):
            cand = cand.replace(year=year + 1)
        return cand.astimezone()
    return None


def _hour_minute(match: re.Match[str]) -> tuple[int, int]:
    hour = int(match.group("hour")) % 12
    if match.group("ampm").lower() == "pm":
        hour += 12
    return hour, int(match.group("minute") or 0)


def epoch_to_local(value: Any) -> datetime | None:
    """``resetsAt`` from a ``rate_limit_event``: epoch seconds (milliseconds tolerated)."""
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        return None
    seconds = value / 1000 if value > 1e11 else value
    return datetime.fromtimestamp(seconds, UTC).astimezone()


# --- Classifier -------------------------------------------------------------------

_AUTH_TEXT = re.compile(
    r"/login|invalid api key|oauth token|authentication[_ ]?(?:failed|error)|"
    r"not logged in|invalid x-api-key|401\b",
    re.IGNORECASE,
)
_CREDIT_TEXT = re.compile(r"\b402\b|more credits|insufficient credits|add credits", re.IGNORECASE)


def _api_error(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The last synthetic API-error assistant message in ``events``."""
    for event in reversed(events):
        if event.get("type") != "assistant":
            continue
        if (
            event.get("error")
            or event.get("is_api_error_message")
            or event.get("isApiErrorMessage")
        ):
            content = (event.get("message") or {}).get("content") or []
            text = " ".join(
                c.get("text", "")
                for c in content
                if isinstance(c, dict) and c.get("type") == "text"
            )
            return {"error": event.get("error"), "text": text}
        return None  # a normal assistant message came last
    return None


def _rejected_limit(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in reversed(events):
        if event.get("type") == "rate_limit_event":
            info = event.get("rate_limit_info") or {}
            return info if info.get("status") == "rejected" else None
    return None


def classify(
    exit_code: int | None,
    result: dict[str, Any] | None,
    last_events: list[dict[str, Any]],
    stderr_tail: str = "",
    *,
    timed_out: str | None = None,
    provider: str | None = None,
    expect_result_line: bool = True,
    now: datetime | None = None,
) -> Classification:
    """Classify how a session ended.

    ``timed_out`` is ``"idle"``, ``"wall"`` or ``"stopped"`` (``phx stop``) when the
    runner killed the session.
    ``provider`` (``anthropic``/``openrouter``) separates a Pro limit from an
    OpenRouter 429. With ``expect_result_line=False`` (the limit probe) a clean
    result counts as ``complete``.
    """
    if timed_out:
        if timed_out == "stopped":
            return Classification(ExitClass.TIMEOUT, "stopped by phx stop", kind=timed_out)
        what = "no stream events" if timed_out == "idle" else "wall-clock cap reached"
        return Classification(ExitClass.TIMEOUT, f"killed after timeout ({what})", kind=timed_out)

    api = _api_error(last_events)
    status = result.get("api_error_status") if result else None
    ended_in_error = result is None or bool(result.get("is_error"))
    limit_info = _rejected_limit(last_events)

    if ended_in_error and (api or status or limit_info or result is not None):
        text = (api or {}).get("text") or (str(result.get("result") or "") if result else "")
        kind = (api or {}).get("error")
        detail = {"error": kind, "status": status, "text": text[:300]}
        limit = LIMIT_TEXT.search(text)
        if limit_info or limit:
            reset = epoch_to_local((limit_info or {}).get("resetsAt")) or parse_reset(text, now)
            limit_type = (limit_info or {}).get("rateLimitType") or (
                limit.group(1).strip() if limit else None
            )
            when = f", resets {reset:%Y-%m-%d %H:%M %Z}" if reset else ", no reset time given"
            return Classification(
                ExitClass.USAGE_LIMIT,
                f"usage limit ({limit_type or 'unknown'}){when}",
                reset_at=reset,
                kind=limit_type,
                api_error=detail,
            )
        if kind == "rate_limit" or status == 429:
            if provider == "openrouter":
                return Classification(
                    ExitClass.PROVIDER_ERROR,
                    f"provider rate limit: {text}",
                    kind="rate_limited",
                    api_error=detail,
                )
            return Classification(
                ExitClass.USAGE_LIMIT,
                f"rate limited, no reset time given: {text}",
                api_error=detail,
            )
        if (
            kind == "authentication_failed"
            or status in (401, 403)
            or (text and _AUTH_TEXT.search(text) and not status)
        ):
            return Classification(
                ExitClass.AUTH_ERROR, f"authentication failed: {text}", api_error=detail
            )
        subtype = result.get("subtype") if result else None
        if subtype == "error_max_budget_usd":
            return Classification(
                ExitClass.PROVIDER_ERROR,
                "stopped at --max-budget-usd",
                kind="budget",
                api_error=detail,
            )
        if kind == "billing_error" or status == 402 or _CREDIT_TEXT.search(text):
            return Classification(
                ExitClass.PROVIDER_ERROR, f"out of credit: {text}", kind="credits", api_error=detail
            )
        if kind == "server_error" or (isinstance(status, int) and status >= 500):
            return Classification(
                ExitClass.PROVIDER_ERROR,
                f"provider/server error: {text}",
                kind="server",
                api_error=detail,
            )
        if kind in ("invalid_request", "max_output_tokens") or status == 400:
            return Classification(
                ExitClass.PROVIDER_ERROR,
                f"request rejected: {text}",
                kind=kind or "invalid_request",
                api_error=detail,
            )
        if api or status:
            return Classification(
                ExitClass.PROVIDER_ERROR,
                f"API error: {text}",
                kind=kind or "unknown",
                api_error=detail,
            )
        # Only an error result without any API signal is left here.
        return Classification(
            ExitClass.CRASH,
            f"session ended with {subtype or 'an error'}: {text[:200]}".rstrip(": "),
            kind=subtype,
        )

    if result is not None:
        line = parse_result_line(str(result.get("result") or ""))
        if not expect_result_line:
            return Classification(ExitClass.COMPLETE, "session answered", result=line)
        if line is None:
            return Classification(
                ExitClass.NO_RESULT,
                "session ended without a valid PHX-RESULT line; verification decides",
            )
        return Classification(ExitClass(line.status), line.reason or line.status, result=line)

    # No result event at all: the stream was cut short.
    tail = stderr_tail.strip().splitlines()
    last = tail[-1] if tail else ""
    if stderr_tail and _AUTH_TEXT.search(stderr_tail):
        return Classification(ExitClass.AUTH_ERROR, f"authentication failed: {last}")
    if exit_code is not None and exit_code < 0:
        return Classification(ExitClass.CRASH, f"killed by signal {-exit_code}; no result event")
    return Classification(
        ExitClass.CRASH,
        f"stream ended without a result event (exit {exit_code}){': ' + last if last else ''}",
    )
