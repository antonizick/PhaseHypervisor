"""What each project is and what was worked on in the report's window (Phase 12g, ADR-0034).

Descriptions come from the opening of ``README.md`` on ``main``, and phases from the run
logs and the plan's Phase Log. All of it is repo text, so it is untrusted: ``clean`` makes
it safe for a terminal and JSON, and the Markdown renderer adds ``inert``. Nothing here
reaches a shell, a total, a rule or a chart, and repos are only read with ``git show``.
"""

import html
import re
import time
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from phx.paths import env_root
from phx.plan import PlanError, locate_plan, parse_phase_table, show_main
from phx.redact import redact_text
from phx.report.load import Source
from phx.report.model import PhaseWork, ProjectSummary, Report, parse_bound
from phx.state import now_ts

DESCRIPTION_CAP = 300
_MAX_README = 64 * 1024  # the opening is all that is used
_MAX_BLOCK = 2000  # bounds the inline patterns on hostile text; far above the cap
_MIN_WORDS = 4
_NEW_SECTION = ""  # in the block list: the opening has ended at a ``##`` heading
_DAY_S = 86400

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_SKIPPED_LINE = re.compile(
    r"^ {0,3}(?:#{1,6}(?:\s|$)"  # heading
    r"|>"  # blockquote
    r"|(?:[-*+]|\d+[.)])\s"  # list item
    r"|(?:[-*_]\s*){3,}$"  # rule
    r"|\|"  # table row
    r"|\[[^\]]+\]:)"  # link reference definition
)
_SETEXT = re.compile(r"^ {0,3}(?:=+|-+)\s*$")
_TABLE_RULE = re.compile(r"^[\s|:-]*\|[\s|:-]*$")
_IMAGE = re.compile(r"!\[[^\]]*\](?:\([^)]*\)|\[[^\]]*\])?")
_LINK = re.compile(r"\[([^\]]*)\](?:\([^)]*\)|\[[^\]]*\])")
_TAG = re.compile(r"<!--.*?-->|</?[A-Za-z][^>]*>", re.DOTALL)
_EMPHASIS = (
    re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*"),
    re.compile(r"(?<!\w)__(?=\S)(.+?)(?<=\S)__(?!\w)"),
    re.compile(r"\*(?=\S)(.+?)(?<=\S)\*"),
    re.compile(r"(?<!\w)_(?=\S)(.+?)(?<=\S)_(?!\w)"),
    re.compile(r"`+(.+?)`+"),
)
_BOLD_LINE = re.compile(r"(\*\*|__)(?=\S).+(?<=\S)\1")
_LABEL_LINE = re.compile(r"(?:\*\*|__)?[A-Za-z]+(?: [A-Za-z]+)?(?:\*\*|__)?:")  # "Status: …"
_SUBHEADING = re.compile(r"^ {0,3}#{2,6}(?:\s|$)")
_WORD = re.compile(r"[^\W\d_]{2,}")

_ANSI = re.compile(
    r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?|(?:\x1b\[|\x9b)[0-?]*[ -/]*[@-~]?|\x1b.?", re.DOTALL
)
_MD_SPECIAL = re.compile(r"[\\`\[\]|#]")


def clean(text: str) -> str:
    """One line of ``text`` with no escapes, control or format characters, and no secrets."""
    bare = _ANSI.sub("", text)
    kept = "".join(c for c in bare if c.isspace() or not unicodedata.category(c).startswith("C"))
    return redact_text(" ".join(kept.split()))


def inert(text: str) -> str:
    """``text`` (already ``clean``) as Markdown that shows as written and links nothing."""
    escaped = _MD_SPECIAL.sub(lambda m: f"\\{m.group()}", text)
    escaped = escaped.replace("<", "&lt;").replace(">", "&gt;")
    return escaped.replace("%%", "\\%\\%")  # an Obsidian comment would hide the rest


# --- Description ---------------------------------------------------------------------


def _front_matter_end(lines: list[str]) -> int:
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                return i + 1
    return 0


def _paragraphs(text: str) -> list[str]:
    """The text blocks of a README: not headings, HTML, quotes, code, tables or lists.

    A ``##`` heading adds ``_NEW_SECTION``, so a tagline can outrank prose past the opening.
    """
    out: list[str] = []
    current: list[str] = []
    fence: str | None = None
    in_comment = False
    in_html = False

    def flush() -> None:
        if current:
            out.append(" ".join(current))
            current.clear()

    lines = text.splitlines()
    for line in lines[_front_matter_end(lines) :]:
        bare = line.strip()
        if fence is not None:
            if bare.startswith(fence):
                fence = None
        elif in_comment:
            in_comment = "-->" not in line
        elif in_html:
            in_html = bool(bare)
        elif match := _FENCE.match(line):
            flush()
            fence = match.group(1)
        elif bare.startswith("<!--"):
            flush()
            in_comment = "-->" not in line
        elif bare.startswith("<"):
            flush()
            in_html = True
        elif not bare:
            flush()
        elif current and _SETEXT.match(line):
            current.clear()  # the lines above were a heading
        elif current and _TABLE_RULE.match(line):
            current.clear()  # the line above was a table header
        elif _SKIPPED_LINE.match(line):
            flush()
            if _SUBHEADING.match(line):
                out.append(_NEW_SECTION)
        elif not current and line.startswith(("    ", "\t")):
            continue  # indented code
        else:
            current.append(bare)
    flush()
    return out


def plain(markdown: str) -> str:
    """Inline Markdown reduced to its text: link labels kept, emphasis and HTML dropped."""
    text = html.unescape(markdown)
    text = _LINK.sub(r"\1", _IMAGE.sub("", text))
    text = _TAG.sub("", text)
    for pattern in _EMPHASIS:
        text = pattern.sub(r"\1", text)
    return " ".join(text.split())


def _links_only(block: str) -> bool:
    return not _WORD.search(_LINK.sub("", _IMAGE.sub("", block)))


def _cap(text: str) -> str:
    if len(text) <= DESCRIPTION_CAP:
        return text
    return text[: DESCRIPTION_CAP - 1].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"


def describe(readme: str) -> str | None:
    """The README's first prose paragraph, else its bold tagline, else ``None``.

    A tagline in the opening outranks a paragraph under a later ``##`` heading, since that
    one belongs to a section, not to the project. The text is cleaned before the cap, so a
    cut cannot leave half a secret unredacted.
    """
    tagline: str | None = None
    for block in _paragraphs(readme[:_MAX_README]):
        block = block[:_MAX_BLOCK]
        if block == _NEW_SECTION:
            if tagline:
                break
        elif _BOLD_LINE.fullmatch(block):
            tagline = tagline or clean(plain(block))
        elif _LABEL_LINE.match(block) or _links_only(block):
            continue
        else:
            text = clean(plain(block))
            if len(_WORD.findall(text)) >= _MIN_WORDS:
                return _cap(text)
    return _cap(tagline) if tagline else None


# --- Phase Log -----------------------------------------------------------------------

_LOG_START = re.compile(r"^##\s+Phase Log")
_SECTION = re.compile(r"^##\s")
_ENTRY = re.compile(r"^###\s+(\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2}(?: \S+)?)?)\s*:\s*(.+)$")
_PHASE_TITLE = re.compile(r"Phase\s+(\d{2}[a-z]?)\s*:")
_TIMELINE = re.compile(r"^\s*[-*]\s+\*\*Timeline:?\*\*:?\s*(.*)$")
_STAMP = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?: (\d{2}):(\d{2})(?: ([A-Za-z]{2,6}))?)?")
_FIELD = re.compile(r"(started|finished|merged)\b(.*)")
_COMPLETE = re.compile(r"✅|\(complete\b", re.IGNORECASE)
_SESSION_PHASE = re.compile(r"(\d{2}[a-z]?)(?:-|$)")  # "03", or "03-triage" for its summary


@dataclass(frozen=True)
class LogPhase:
    """One phase's span across all its Phase Log entries."""

    phase: str
    status: str | None  # "complete", "blocked" or None, from the newest entry that says
    started: float
    finished: float | None  # None: the log shows no end yet


def _is_dst(zone: str) -> int | None:
    """``tm_isdst`` for a zone abbreviation of the local zone, else ``None``."""
    standard, daylight = time.tzname
    if zone == standard:
        return 0
    return 1 if time.daylight and zone == daylight else None


def _moment(text: str, unknown: set[str], *, late: bool = False) -> float | None:
    """The first timestamp in ``text``; with no usable time, ``late`` picks that day's end."""
    match = _STAMP.search(text)
    if match is None:
        return None
    y, m, d = (int(g) for g in match.group(1, 2, 3))
    try:
        date(y, m, d)
    except ValueError:
        return None
    hour, minute, zone = match.group(4), match.group(5), match.group(6)
    if hour is not None and int(hour) < 24 and int(minute) < 60:
        if zone is None:
            return time.mktime((y, m, d, int(hour), int(minute), 0, 0, 0, -1))
        isdst = _is_dst(zone)
        if isdst is not None:
            return time.mktime((y, m, d, int(hour), int(minute), 0, 0, 0, isdst))
        unknown.add(zone)
    midnight = time.mktime((y, m, d, 0, 0, 0, 0, 0, -1))
    return midnight + _DAY_S - 1 if late else midnight


def _timeline_fields(timeline: str, unknown: set[str]) -> dict[str, float]:
    found: dict[str, float] = {}
    for segment in re.split(r"\s+·\s+", timeline):
        match = _FIELD.match(segment.strip())
        if match:
            name = match.group(1)
            epoch = _moment(match.group(2), unknown, late=name != "started")
            if epoch is not None:
                found[name] = epoch
    return found


def _entries(text: str) -> list[tuple[str, str, str | None]]:
    """``(heading timestamp, title, Timeline text)`` of each Phase Log entry."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if _LOG_START.match(line)), None)
    if start is None:
        return []
    out: list[tuple[str, str, str | None]] = []
    for line in lines[start + 1 :]:
        if _SECTION.match(line):
            break
        if match := _ENTRY.match(line):
            out.append((match.group(1), match.group(2).strip(), None))
        elif out and out[-1][2] is None and (bullet := _TIMELINE.match(line)):
            out[-1] = (out[-1][0], out[-1][1], bullet.group(1).strip())
    return out


def parse_phase_log(text: str) -> tuple[list[LogPhase], set[str]]:
    """Each phase's span, in first-seen order, and any zone names that fell back to a date.

    Planning entries and phase 00 are skipped. A start that was not recorded falls back to
    the finish, then the heading. A complete entry with no finish ends at its heading, so
    it does not stay open for ever; any other entry with none leaves the phase open.
    """
    unknown: set[str] = set()
    phases: dict[str, LogPhase] = {}
    for stamp, title, timeline in _entries(text):
        match = _PHASE_TITLE.match(title)
        if match is None or match.group(1) == "00":
            continue
        pid = match.group(1)
        marks = _timeline_fields(timeline or "", unknown)
        status = "complete" if _COMPLETE.search(title) else "blocked" if "⛔" in title else None
        end = marks.get("finished", marks.get("merged"))
        start = marks.get("started", end)
        if end is None and status == "complete":
            end = _moment(stamp, unknown, late=True)
        if start is None:
            start = _moment(stamp, unknown)
        if start is None:  # pragma: no cover - the heading pattern guarantees a date shape
            continue
        seen = phases.get(pid)
        if seen is not None:
            start = min(start, seen.started)
            if seen.finished is not None:
                end = max(end, seen.finished) if end is not None else seen.finished
            status = status or seen.status
        phases[pid] = LogPhase(pid, status, start, end)
    return list(phases.values()), unknown


# --- Repos ---------------------------------------------------------------------------


@dataclass
class Repos:
    """Where each project's repo is, and why for those it is not."""

    paths: dict[str, Path] = field(default_factory=dict)
    notes: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _logged_repo(source: Source) -> Path | None:
    for event in reversed(source.events):
        if event.get("event") == "run_start" and isinstance(event.get("repo"), str):
            return Path(event["repo"])
    return None


def find_repos(sources: list[Source], env: Mapping[str, str]) -> Repos:
    """Each project's repo: the latest ``run_start.repo``, else ``$PHX_WORK_ROOT/<project>``.

    A log's path is still checked: it must exist, and one outside the work root is skipped
    with a warning.
    """
    root = env_root(env, "PHX_WORK_ROOT", "Work").resolve()
    found = Repos()
    for source in sources:
        project = source.project
        logged = _logged_repo(source)
        if logged is not None and logged.exists():
            candidate = logged
        elif (root / project / ".git").exists():
            candidate = root / project
        else:
            found.notes[project] = "repo not found"
            continue
        resolved = candidate.resolve()
        if resolved.is_relative_to(root):
            found.paths[project] = resolved
        else:
            found.notes[project] = "repo is outside the work root"
            found.warnings.append(f"{project}: repo {resolved} is outside {root}; not read")
    return found


# --- Summaries -----------------------------------------------------------------------


def _show(repo: Path, path: str) -> str | None:
    try:
        return show_main(repo, path)
    except (OSError, UnicodeDecodeError):  # not text, or git could not run
        return None


def _description(repo: Path) -> tuple[str | None, str | None]:
    readme = _show(repo, "README.md")
    if readme is None:
        return None, "no readable README.md on main"
    text = describe(readme)
    return (text, None) if text else (None, "the README has no prose paragraph")


def _plan_text(repo: Path) -> tuple[str | None, str | None]:
    try:
        name, _prefix = locate_plan(repo)
    except PlanError as exc:
        return None, str(exc)
    text = _show(repo, name)
    return (text, None) if text is not None else (None, f"{name} is not readable")


def _phase_names(text: str) -> tuple[dict[str, str], str | None]:
    try:
        rows, _problems = parse_phase_table(text)
    except PlanError as exc:
        return {}, str(exc)
    return {phase.id: clean(plain(phase.name)) for phase, _gate in rows}, None


def merge_phases(
    report: Report,
    project: str,
    logged: list[LogPhase],
    names: Mapping[str, str],
    start: float | None,
    stop: float | None,
) -> list[PhaseWork]:
    """Phases active in ``[start, stop)``: ``phx`` where a session ran, else ``manual``."""

    def inside(epoch: float) -> bool:
        return (start is None or epoch >= start) and (stop is None or epoch < stop)

    first: dict[str, float] = {}
    for session in report.sessions:
        match = _SESSION_PHASE.match(session.phase)
        if session.project == project and match:  # a usage-limit probe is no phase
            pid, began = match.group(1), session.epoch - session.duration_s
            first[pid] = min(began, first.get(pid, began))
    done = {
        mark.phase: mark.epoch
        for mark in report.marks
        if mark.project == project and mark.kind == "completed" and mark.phase
    }
    log = {p.phase: p for p in logged}
    rows: list[tuple[float, str, PhaseWork]] = []

    def add(pid: str, source: str, began: float, ended: float | None) -> None:
        finished = ended is not None and inside(ended)
        rows.append(
            (
                began,
                pid,
                PhaseWork(
                    clean(pid),
                    names.get(pid),
                    source,
                    now_ts(began),
                    now_ts(ended) if ended is not None else None,
                    finished,
                ),
            )
        )

    for pid, began in first.items():
        entry = log.get(pid)
        ended = done.get(pid, entry.finished if entry else None)
        add(pid, "phx", entry.started if entry else began, ended)
    for entry in logged:
        overlaps = (stop is None or entry.started < stop) and (
            start is None or entry.finished is None or entry.finished >= start
        )
        if entry.phase not in first and overlaps:
            add(entry.phase, "manual", entry.started, entry.finished)
    return [work for _, _, work in sorted(rows, key=lambda row: row[:2])]


def gather(report: Report, repos: Repos) -> tuple[list[ProjectSummary], list[str]]:
    """One summary per project in scope, plus warnings; a failure only affects its project."""
    start = parse_bound(report.since, end=False) if report.since else None
    stop = parse_bound(report.until, end=True) if report.until else None
    warnings = list(repos.warnings)
    out: list[ProjectSummary] = []
    for project in report.projects:
        repo = repos.paths.get(project)
        logged: list[LogPhase] = []
        names: dict[str, str] = {}
        note: str | None
        if repo is None:
            description, note = None, repos.notes.get(project, "repo not found")
        else:
            description, note = _description(repo)
            text, problem = _plan_text(repo)
            if text is not None:
                names, table_problem = _phase_names(text)
                problem = problem or table_problem
                logged, unknown = parse_phase_log(text)
                if unknown:
                    zones = ", ".join(sorted(clean(z) for z in unknown))
                    warnings.append(f"{project}: zone {zones} is not local; used the date only")
            if problem is not None:
                warnings.append(f"{project}: phases not read from the plan ({clean(problem)})")
        phases = merge_phases(report, project, logged, names, start, stop)
        out.append(ProjectSummary(project, repo is not None, description, note, phases))
    return out, warnings
