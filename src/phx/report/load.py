"""Read every ``run.jsonl`` under the state root, tolerating damage (Phase 12f).

One bad line or file never stops a report: it becomes a warning and the rest is
reported. Symlinks are skipped so a link in the state root cannot pull in a file from
outside it. Session transcripts are never opened (ADR-0032).
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LOG_FILE = "run.jsonl"
PILOT = "phx-pilot"  # the Phase 10 sandbox: left out unless named

Event = dict[str, Any]


@dataclass
class Source:
    """One project's usable events, in file order."""

    project: str
    events: list[Event]


@dataclass
class Loaded:
    sources: list[Source] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def projects(root: Path) -> list[str]:
    """Project names under ``root``: real directories holding a real ``run.jsonl``."""
    try:
        entries = sorted(root.iterdir(), key=lambda p: p.name)
    except OSError:
        return []
    return [
        p.name
        for p in entries
        if p.is_dir()
        and not p.is_symlink()
        and (p / LOG_FILE).exists()
        and not (p / LOG_FILE).is_symlink()
    ]


def _usable(record: Any) -> bool:
    return (
        isinstance(record, dict)
        and isinstance(record.get("event"), str)
        and isinstance(record.get("epoch"), int | float)
        and not isinstance(record.get("epoch"), bool)
    )


def parse_lines(lines: list[str], project: str) -> tuple[list[Event], list[str]]:
    """The usable records of ``lines``, without rehearsals, plus warnings."""
    events: list[Event] = []
    bad = 0
    truncated = False
    rehearsal = False
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            if n == len(lines):
                truncated = True
            else:
                bad += 1
            continue
        if not _usable(record):
            bad += 1
            continue
        name = record["event"]
        if name == "dry_run":
            continue
        if name == "run_start":
            options = record.get("options")
            rehearsal = isinstance(options, dict) and options.get("dry_run") is True
        if rehearsal:  # everything inside a rehearsal, its own run_end included
            if name == "run_end":
                rehearsal = False
            continue
        events.append(record)
    warnings = []
    if bad:
        warnings.append(f"{project}: skipped {bad} unreadable line(s)")
    if truncated:
        warnings.append(f"{project}: ignored a truncated last line")
    return events, warnings


def load(root: Path, names: list[str]) -> Loaded:
    """Load ``names``; a file that cannot be read is a warning, not a failure."""
    loaded = Loaded()
    for name in names:
        try:
            directory = root / name
            path = directory / LOG_FILE
            if directory.is_symlink() or path.is_symlink():
                loaded.warnings.append(f"{name}: skipped, {LOG_FILE} is reached through a symlink")
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            loaded.warnings.append(f"{name}: {LOG_FILE} not read ({type(exc).__name__})")
            continue
        events, warnings = parse_lines(text.splitlines(), name)
        loaded.warnings.extend(warnings)
        loaded.sources.append(Source(name, events))
    return loaded
