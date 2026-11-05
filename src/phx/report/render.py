"""Terminal, Markdown and JSON forms of a report, plus the optional vault note.

Terminal and Markdown are two renderings of the same ``Section`` list, so they cannot
disagree. A default run saves a vault note and its charts (ADR-0035); otherwise only an
explicit PATH or ``--vault`` writes. Nothing is written under the state root.
"""

import json
import os
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from phx.progress import fmt_dur, fmt_tokens
from phx.report.model import Period, PhaseWork, ProjectSummary, Report, Totals
from phx.report.projects import Repos, inert
from phx.report.rules import (
    THRESHOLDS,
    Recommendation,
    completion_rate,
    count,
    money,
    percent,
)
from phx.report.svg import write_charts
from phx.state import now_ts
from phx.vault import note_path, vault_root

SCHEMA = 1
VAULT_FOLDER = Path("04 Resources") / "PHX Reports"


@dataclass
class Table:
    headers: list[str]
    rows: list[list[str]]
    right: frozenset[int] = frozenset()  # right-aligned columns


@dataclass
class Section:
    title: str
    lines: list[str] = field(default_factory=list)
    table: Table | None = None


def caveats(report: Report) -> list[str]:
    t = report.totals
    out = [
        "Measured: sessions launched by phx only. Manual /phase sessions leave no token or "
        "cost record, so they are not here and are not estimated.",
        "Cost is the list-price equivalent PHX recorded, not an invoice.",
    ]
    if t.unverified_cost_usd:
        out.append(
            f"{money(t.unverified_cost_usd)} of it has no known price (costBasis unknown, marked "
            "~): Claude Code's fallback rate for models it does not know, not what the provider "
            "charged."
        )
    if t.sessions_without_cost:
        out.append(
            f"{t.sessions_without_cost} session(s) have unknown cost, left out of cost figures "
            "and never counted as $0."
        )
    if t.repeated_cost_usd:
        out.append(
            f"A resumed session reports running totals, so each run is charged its increase: "
            f"{money(t.repeated_cost_usd)} that repeats earlier runs is left out here (and is "
            "still inside the totals in `phx status` and `run_end`)."
        )
    if report.summaries is not None:
        out.append(
            "Projects: descriptions are each README's opening on main. A manual phase has no "
            "phx session in the window; it comes from the plan and carries time only, in no "
            "figure below."
        )
    return out


def _cost(t: Totals) -> str:
    return f"~{money(t.cost_usd)}" if t.unverified_cost_usd else money(t.cost_usd)


def _arrow(value: float | None) -> str:
    if value is None:
        return "n/a"
    mark = "▲" if value > 0.005 else "▼" if value < -0.005 else "→"
    return f"{mark} {value * 100:+.0f}%"


def _opt_dur(hours: float | None) -> str:
    return "n/a" if hours is None else fmt_dur(hours * 3600)


def _totals_section(t: Totals) -> Section:
    rate = t.first_attempt / t.phases_completed if t.phases_completed else None
    rows = [
        ["Active session time", fmt_dur(t.active_s)],
        ["Usage-limit waiting", f"{fmt_dur(t.wait_s)} ({count(t.waits, 'waits')})"],
        ["Gate pauses", f"{fmt_dur(t.gate_pause_s)} ({t.gate_pauses})"],
        ["Other pauses", fmt_dur(t.other_pause_s)],
        ["Runs / sessions", f"{t.runs} / {t.sessions}"],
        [
            "Tokens",
            f"{fmt_tokens(t.tokens.total)} (input {fmt_tokens(t.tokens.input)}, output "
            f"{fmt_tokens(t.tokens.output)}, cache read {fmt_tokens(t.tokens.cache_read)}, "
            f"cache write {fmt_tokens(t.tokens.cache_write)})",
        ],
        ["Cost", _cost(t)],
        [
            "Phases completed",
            f"{t.phases_completed} ({t.first_attempt} first attempt, {percent(rate)})",
        ],
        ["Retries / timeouts / blocks", f"{t.retries} / {t.timeouts} / {t.blocks}"],
        ["Cost per completed phase", money(t.cost_per_phase)],
        [
            "Tokens per completed phase",
            fmt_tokens(int(t.tokens_per_phase)) if t.tokens_per_phase is not None else "n/a",
        ],
        ["Active time per completed phase", _opt_dur(t.active_h_per_phase)],
        [
            "Non-completing share",
            f"{percent(t.noncompleting_cost_share)} of cost, "
            f"{percent(t.noncompleting_time_share)} of active time",
        ],
        ["Cache-read share of input", percent(t.cache_read_share)],
    ]
    return Section("Totals", table=Table(["Measure", "Value"], rows))


def _period_row(p: Period) -> list[str]:
    t = p.totals
    if not t.has_data:
        return [p.label, "no data", "", "", "", "", "", "", ""]
    return [
        p.label,
        _cost(t),
        _arrow(p.change["cost_usd"]),
        fmt_tokens(t.tokens.total),
        fmt_dur(t.active_s),
        str(t.phases_completed),
        money(t.cost_per_phase),
        _arrow(p.change["cost_per_phase"]),
        percent(t.noncompleting_cost_share),
    ]


def _usage_rows(rows: Mapping[str, Totals], top: int) -> list[list[str]]:
    known = sum(t.cost_usd or 0.0 for t in rows.values())
    used = {k: t for k, t in rows.items() if t.sessions or t.tokens.total}
    ordered = sorted(used.items(), key=lambda kv: (-(kv[1].cost_usd or 0.0), kv[0]))
    return [
        [
            name,
            str(t.sessions),
            fmt_tokens(t.tokens.total),
            _cost(t),
            percent((t.cost_usd or 0.0) / known) if known and t.cost_usd is not None else "n/a",
            fmt_dur(t.active_s),
            str(t.phases_completed),
            percent(t.cache_read_share),
        ]
        for name, t in ordered[:top]
    ]


def _usage_table(name: str, rows: Mapping[str, Totals], top: int) -> Table:
    headers = [name, "Sessions", "Tokens", "Cost", "Cost share", "Active", "Done", "Cache read"]
    return Table(headers, _usage_rows(rows, top), frozenset(range(1, 8)))


def _recommendation_lines(rec: Recommendation) -> list[str]:
    return [
        f"[{rec.id} {rec.severity}] {rec.title}",
        *(f"  - {item}" for item in rec.evidence),
        f"  Action: {rec.action}",
        f"  Fired on: {rec.threshold}",
    ]


def _phase_state(work: PhaseWork) -> str:
    source = "phx" if work.source == "phx" else "manual, time only"
    finished = "finished in period" if work.finished_in_period else "not finished in period"
    return f"{source}, {finished}"


def _project_lines(summary: ProjectSummary, top: int, markdown: bool) -> list[str]:
    show = inert if markdown else str
    if summary.description is not None:
        about = show(summary.description)
    else:
        about = f"No description: {show(summary.description_note or 'none found')}."
    shown = summary.phases[:top]
    hidden = len(summary.phases) - len(shown)
    rows = [(show(w.phase), show(w.name) if w.name else "", _phase_state(w)) for w in shown]
    empty = "No recorded work in this period."
    more = f"and {hidden} more"
    if markdown:
        items = [f"- {pid}{f' {name}' if name else ''} ({state})" for pid, name, state in rows]
        return [
            f"### {show(summary.project)}",
            "",
            f"**What it is:** {about}",
            "",
            *(items or [empty]),
            *([f"- {more}"] if hidden else []),
            "",
        ]
    id_width = max((len(pid) for pid, _, _ in rows), default=0)
    name_width = max((len(name) for _, name, _ in rows), default=0)
    return [
        summary.project,
        f"  {about}",
        *(
            f"  {pid.ljust(id_width)}  {name.ljust(name_width)}  {state}"
            for pid, name, state in rows
        ),
        *([] if rows else [f"  {empty}"]),
        *([f"  {more}"] if hidden else []),
        "",
    ]


def _projects_section(summaries: list[ProjectSummary], top: int, markdown: bool) -> Section:
    lines = [line for s in summaries for line in _project_lines(s, top, markdown)]
    return Section("Projects", lines=lines[:-1])


def sections(
    report: Report,
    recommendations: list[Recommendation],
    notes: list[str],
    top: int,
    *,
    markdown: bool = False,
) -> list[Section]:
    t = report.totals
    out: list[Section] = []
    if report.summaries:
        out.append(_projects_section(report.summaries, top, markdown))
    out.append(_totals_section(t))
    out.append(
        Section(
            f"By {report.by}",
            table=Table(
                [
                    "Period",
                    "Cost",
                    "Change",
                    "Tokens",
                    "Active",
                    "Done",
                    "Cost/phase",
                    "Change",
                    "Lost",
                ],
                [_period_row(p) for p in report.periods],
                frozenset(range(1, 9)),
            ),
        )
    )
    out.append(Section("By model", table=_usage_table("Model", report.by_model, top)))
    providers = _usage_table("Provider", report.by_provider, top)
    providers.headers.append("Completed sessions")
    for row in providers.rows:
        row.append(percent(completion_rate(report.by_provider[row[0]])))
    providers.right = frozenset(range(1, 9))
    out.append(Section("By provider", table=providers))
    out.append(Section("By project", table=_usage_table("Project", report.by_project, top)))
    out.append(
        Section(
            f"Costliest phases (top {top})",
            table=Table(
                ["Project", "Phase", "Model", "Cost", "Sessions", "Active", "Result"],
                [
                    [
                        p.project,
                        p.phase,
                        p.model,
                        _cost(p.totals),
                        str(p.totals.sessions),
                        fmt_dur(p.totals.active_s),
                        "done" if p.totals.phases_completed else "not completed",
                    ]
                    for p in report.phases[:top]
                ],
                frozenset({3, 4, 5}),
            ),
        )
    )
    lines: list[str] = []
    for rec in recommendations:
        lines += [*_recommendation_lines(rec), ""]
    if not recommendations:
        lines.append("Nothing crossed a threshold.")
    out.append(Section("Recommendations", lines=[*lines, *notes]))
    if report.warnings:
        out.append(Section("Warnings", lines=list(report.warnings)))
    return out


def scope_line(report: Report) -> str:
    span = f"{report.since or 'start'} to {report.until or 'latest'}"
    data = f"data through {report.as_of}" if report.data_through is not None else "no run data"
    return f"{len(report.projects)} project(s), {span}, by {report.by}, {data}"


def to_text(
    report: Report,
    recommendations: list[Recommendation],
    notes: list[str],
    *,
    top: int = 10,
    color: bool = False,
) -> str:
    bold = ("\033[1m", "\033[0m") if color else ("", "")

    def table(tb: Table) -> list[str]:
        rows = [tb.headers, *tb.rows]
        widths = [max(len(r[i]) for r in rows) for i in range(len(tb.headers))]
        return [
            "  ".join(
                cell.rjust(widths[i]) if i in tb.right else cell.ljust(widths[i])
                for i, cell in enumerate(row)
            ).rstrip()
            for row in rows
        ]

    out = [f"{bold[0]}PHX report{bold[1]}: {scope_line(report)}", *caveats(report)]
    for section in sections(report, recommendations, notes, top):
        out += ["", f"{bold[0]}{section.title}{bold[1]}", *section.lines]
        if section.table:
            out += table(section.table)
    return "\n".join(out) + "\n"


def to_markdown(
    report: Report,
    recommendations: list[Recommendation],
    notes: list[str],
    *,
    top: int = 10,
    links: Mapping[str, str] | None = None,
    charts: Sequence[str] = (),
) -> str:
    def cell(text: str) -> str:
        return text.replace("|", "\\|")

    def table(tb: Table) -> list[str]:
        marks = ["---:" if i in tb.right else "---" for i in range(len(tb.headers))]
        return [
            "| " + " | ".join(tb.headers) + " |",
            "|" + "|".join(marks) + "|",
            *("| " + " | ".join(cell(c) for c in row) + " |" for row in tb.rows),
        ]

    out = [
        f"# PHX report, {report.as_of}",
        "",
        f"**Scope:** {scope_line(report)}",
        "",
        *(f"- {line}" for line in caveats(report)),
    ]
    if links:
        out += ["", "**Project notes:** " + ", ".join(f"[[{v}]]" for _, v in sorted(links.items()))]
    embeds = [f"![[{chart}]]" for chart in charts]
    for section in sections(report, recommendations, notes, top, markdown=True):
        if embeds and section.title != "Projects":
            out += ["", "## Charts", "", *embeds]
            embeds = []
        out += ["", f"## {section.title}", ""]
        if section.title == "Recommendations":
            out += _recommendations_md(section.lines)
        else:
            out += [*section.lines]
        if section.table:
            out += table(section.table)
    return "\n".join(out) + "\n"


def _recommendations_md(lines: list[str]) -> list[str]:
    out = []
    for line in lines:
        if line.startswith("["):
            out.append(f"**{line}**\n")
        elif line.startswith("  - "):
            out.append(line[2:])
        elif line.startswith("  "):
            out.append(f"\n{line.strip()}\n")
        elif line:
            out.append(f"{line}\n")
    return out


def _totals_rows(rows: Mapping[str, Totals], key: str) -> list[dict[str, Any]]:
    return [{key: name, **t.as_dict()} for name, t in sorted(rows.items())]


def to_json(report: Report, recommendations: list[Recommendation], notes: list[str]) -> str:
    """The stable ``schema: 1`` document (fields are documented in the user guide)."""
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "scope": {
            "projects": report.projects,
            "by": report.by,
            "since": report.since,
            "until": report.until,
            "data_through": report.as_of if report.data_through is not None else None,
            "open_spans": report.open_spans,
        },
        "caveats": caveats(report),
        "totals": report.totals.as_dict(),
        "periods": [
            {
                "period": p.label,
                "has_data": p.totals.has_data,
                **p.totals.as_dict(),
                "change": p.change,
                "cost_by_model": dict(sorted(p.models.items())),
            }
            for p in report.periods
        ],
        "models": _totals_rows(report.by_model, "model"),
        "providers": _totals_rows(report.by_provider, "provider"),
        "projects": _totals_rows(report.by_project, "project"),
        "phases": [
            {
                "project": p.project,
                "phase": p.phase,
                "alias": p.alias,
                "model": p.model,
                "provider": p.provider,
                **p.totals.as_dict(),
            }
            for p in report.phases
        ],
        "recommendations": [asdict(r) for r in recommendations],
        "not_enough_data": notes,
        "thresholds": {k: asdict(v) for k, v in THRESHOLDS.items()},
        "warnings": report.warnings,
    }
    if report.summaries is not None:
        payload["project_summaries"] = [asdict(s) for s in report.summaries]
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def project_links(repos: Mapping[str, Path], root: Path) -> dict[str, str]:
    """Project -> note name, for each named note that exists inside the vault."""
    links: dict[str, str] = {}
    for project, repo in repos.items():
        try:
            path = note_path(repo)
            if path is not None and path.resolve().is_relative_to(root) and path.is_file():
                links[project] = path.stem
        except OSError:
            continue
    return links


def write_vault(
    report: Report,
    recommendations: list[Recommendation],
    notes: list[str],
    *,
    top: int,
    repos: Repos,
    env: Mapping[str, str] | None = None,
    now: float | None = None,
    charts: Sequence[str] = (),
) -> tuple[Path | None, str]:
    """A new timestamped note under the vault; it never replaces an existing file."""
    root = vault_root(env).resolve()
    if not root.is_dir():
        return None, f"no vault at {root} (set PHX_VAULT_ROOT); note skipped"
    links = project_links(repos.paths, root)
    text = to_markdown(report, recommendations, notes, top=top, links=links, charts=charts)
    stamp = now_ts(now)
    folder = root / VAULT_FOLDER
    name = f"PHX Report {stamp[:10]} {stamp[11:16].replace(':', '')}"
    updated = f"---\ntags: [phx, report]\nupdated: {stamp}\n---\n\n"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for n in range(1, 100):
            path = folder / (f"{name}.md" if n == 1 else f"{name} ({n}).md")
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            except FileExistsError:
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(updated + text)
            return path, f"wrote {path}"
    except OSError as exc:
        return None, f"note not written: {type(exc).__name__}"
    return None, f"note not written: too many reports named {name}"


def reserve_chart_folder(parent: Path, now: float) -> Path:
    """A new ``charts<YYYY-MM-DD-HHMM>`` folder under ``parent``; it never reuses one."""
    stamp = now_ts(now)
    name = f"charts{stamp[:10]}-{stamp[11:16].replace(':', '')}"
    parent.mkdir(parents=True, exist_ok=True)
    for n in range(1, 100):
        folder = parent / (name if n == 1 else f"{name}-{n}")
        try:
            folder.mkdir()
        except FileExistsError:
            continue
        return folder
    raise FileExistsError(name)


def save_report(
    report: Report,
    recommendations: list[Recommendation],
    notes: list[str],
    *,
    top: int,
    repos: Repos,
    env: Mapping[str, str] | None = None,
    now: float | None = None,
) -> list[str]:
    """The default run's charts and note, sharing one time stamp (ADR-0035); returns messages.

    Either can fail alone: charts that were not written are not embedded, and a note that
    was not written leaves its charts in place.
    """
    root = vault_root(env).resolve()
    if not root.is_dir():
        return [f"no vault at {root} (set PHX_VAULT_ROOT); report not saved"]
    moment = time.time() if now is None else now
    messages: list[str] = []
    embeds: list[str] = []
    try:
        folder = reserve_chart_folder(root / VAULT_FOLDER, moment)
        embeds = [f"{folder.name}/{path.name}" for path in write_charts(report, folder)]
        messages.append(f"wrote {folder}")
    except OSError as exc:
        messages.append(f"charts not written: {type(exc).__name__}")
    _path, message = write_vault(
        report, recommendations, notes, top=top, repos=repos, env=env, now=moment, charts=embeds
    )
    return [*messages, message]
