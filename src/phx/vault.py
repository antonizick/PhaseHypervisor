"""Append a run summary to the project's Obsidian note (spec R10, task 8 of Phase 07).

The note's path comes from the repo's ``CLAUDE.md`` on ``main`` (the line naming "The
Obsidian project note `…`" that every phased-project repo carries). Only two things in
the note change: the ``updated:`` frontmatter field and one new line at the end of its
``## Log`` section. A note without either is left alone (logged).
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path

from phx.logging import EventLog
from phx.plan import show_main
from phx.state import RunState, now_ts

_NOTE = re.compile(r"Obsidian project note\s+`([^`\n]+\.md)`", re.IGNORECASE)
_UPDATED = re.compile(r"^updated:.*$", re.MULTILINE)
_LOG_HEADING = re.compile(r"^##\s+Log\s*$", re.MULTILINE)


@dataclass(frozen=True)
class VaultResult:
    path: Path | None
    written: bool
    reason: str


def note_path(repo: Path) -> Path | None:
    """The project note named in ``CLAUDE.md`` on ``main``, or ``None``."""
    text = show_main(repo, "CLAUDE.md")
    match = _NOTE.search(text or "")
    return Path(match.group(1)).expanduser() if match else None


def _money(value: float) -> str:
    return f"${value:.2f}"


def _tokens(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1000:
        return f"{value / 1000:.1f}k"
    return str(value)


def _duration(seconds: float) -> str:
    minutes = round(seconds / 60)
    return f"{minutes // 60}h {minutes % 60:02d}m" if minutes >= 60 else f"{minutes}m"


_ICON = {
    "complete": "✅",
    "blocked": "⛔",
    "usage_limit": "⏳",
    "stopped": "⏹",
}


def summary_line(state: RunState, ts: str | None = None) -> str:
    """One Log bullet for the run: outcome, then each phase with tokens, cost and waits."""
    parts = []
    for pid, t in state.phases.items():
        icon = _ICON.get(t.outcome or "", "⚠️")
        detail = f"{_tokens(t.tokens)} tokens, {_money(t.cost_usd)}, {t.sessions} session(s)"
        if t.wait_s:
            detail += f", waited {_duration(t.wait_s)}"
        parts.append(f"{pid} {icon} {t.outcome or 'unknown'} ({detail})")
    phases = "; ".join(parts) if parts else "no phase run"
    end = state.status
    if state.end_reason:
        end += f": {state.end_reason}"
    return (
        f"- **{ts or now_ts()}:** PHX run `{state.run_id}` ended {end}. Phases: {phases}. "
        f"Total {_tokens(state.tokens)} tokens, {_money(state.cost_usd)}."
    )


def append_line(text: str, line: str, ts: str) -> str | None:
    """``text`` with ``line`` added to the end of its Log section and ``updated:`` set.

    ``None`` if the note has no ``## Log`` section.
    """
    heading = _LOG_HEADING.search(text)
    if heading is None:
        return None
    nxt = re.search(r"^##\s", text[heading.end() :], re.MULTILINE)
    end = heading.end() + nxt.start() if nxt else len(text)
    section = text[:end].rstrip("\n")
    rest = text[end:]
    out = section + "\n" + line + "\n" + ("\n" + rest if rest else "")
    if text.startswith("---\n"):
        close = out.find("\n---", 4)
        if close != -1:
            front = _UPDATED.sub(f"updated: {ts}", out[:close], count=1)
            out = front + out[close:]
    return out


def append_summary(repo: Path, state: RunState, log: EventLog) -> VaultResult:
    path = note_path(repo)

    def done(written: bool, reason: str) -> VaultResult:
        log.event("vault", reason=reason, path=str(path) if path else None, written=written)
        return VaultResult(path, written, reason)

    if path is None:
        return done(False, "CLAUDE.md on main names no Obsidian project note")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return done(False, f"note unreadable: {type(exc).__name__}")
    ts = now_ts()
    new = append_line(text, summary_line(state, ts), ts)
    if new is None:
        return done(False, "the note has no '## Log' section; left unchanged")
    tmp = path.with_name(f".{path.name}.phx.tmp")
    try:
        tmp.write_text(new, encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        return done(False, f"note not written: {type(exc).__name__}")
    return done(True, "run summary appended to the note's Log section")
