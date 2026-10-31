"""The visual timeline generator (``scripts/phase_timeline.py``, Phase 12b)."""

from __future__ import annotations

import ast
import importlib.util
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType

import pytest

from phx import plan as phx_plan
from phx import verify as phx_verify

REPO = Path(__file__).resolve().parent.parent
SKILL_SCRIPT = REPO / "plugins/phased-project/skills/phased-project/scripts/phase_timeline.py"
REPO_SCRIPT = REPO / "scripts" / "phase_timeline.py"
FIXTURES = Path(__file__).parent / "fixtures" / "timeline"
GOLDEN = FIXTURES / "golden"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("phase_timeline", SKILL_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["phase_timeline"] = mod
    spec.loader.exec_module(mod)
    return mod


pt = _load()
CDT = timezone(timedelta(hours=-5))
CST = timezone(timedelta(hours=-6))


class GitRepo:
    """A throwaway repo whose commits carry chosen committer times."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.invalid")
        self.git("config", "user.name", "T")
        self.git("config", "commit.gpgsign", "false")

    def git(self, *args: str, env: dict[str, str] | None = None) -> str:
        return subprocess.run(
            ["git", "-C", str(self.root), *args],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, **(env or {})},
        ).stdout

    def commit(self, message: str, when: str, files: dict[str, str] | None = None) -> str:
        for name, text in (files or {"log.txt": f"{message}\n"}).items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if name == "log.txt" and path.exists():
                text = path.read_text() + text
            path.write_text(text)
            self.git("add", name)
        env = {"GIT_COMMITTER_DATE": when, "GIT_AUTHOR_DATE": when}
        self.git("commit", "-q", "--allow-empty", "-m", message, env=env)
        return self.git("rev-parse", "--short", "HEAD").strip()

    def merge(self, branch: str, message: str, when: str) -> str:
        env = {"GIT_COMMITTER_DATE": when, "GIT_AUTHOR_DATE": when}
        self.git("merge", "-q", "--no-ff", "-m", message, branch, env=env)
        return self.git("rev-parse", "--short", "HEAD").strip()


def plan_text(rows: list[tuple[str, str, str]], log: str = "", block: bool = True) -> str:
    table = "\n".join(
        f"| {pid} | {name} | x | Opus 5.5 | none | {status} | n/a | auto |"
        for pid, name, status in rows
    )
    markers = f"\n## Timeline\n{pt.START_MARKER}\n{pt.END_MARKER}\n" if block else "\n"
    return (
        "# ABC: Plan\n\n## Phases\n"
        "| Phase | Phase Name | Phase Purpose | AI Model to Use | Depends on | Status "
        "| Prompt | Gate |\n"
        "|---|---|---|---|---|---|---|---|\n"
        f"{table}\n{markers}\n## Owner questions\n\n## Phase Log\n{log}"
    )


def build(root: Path) -> pt.Timeline:  # type: ignore[name-defined]
    return pt.build_timeline(root)[0]


def rec(tl: pt.Timeline, pid: str) -> pt.PhaseRecord:  # type: ignore[name-defined]
    return next(p for p in tl.phases if p.id == pid)


def at(text: str, tz: timezone = CDT) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=tz)


# --- parsing every Timeline grammar ------------------------------------------------------


def test_modern_grammars(tmp_path: Path) -> None:
    (tmp_path / "XYZ_IMPLEMENTATION_PLAN.md").write_text((FIXTURES / "modern.md").read_text())
    tl = build(tmp_path)  # no git: Timeline bullets only
    assert tl.prefix == "XYZ"
    p01 = rec(tl, "01")
    assert p01.start and p01.start.moment.at == at("2026-10-20 20:10")
    assert p01.claim == "1111111" and not p01.start.approx
    assert p01.merged and p01.merged.moment.at == at("2026-10-20 20:14")
    assert rec(tl, "02").claim == "2222222"  # backticks stripped
    paused = rec(tl, "03").waits
    assert [(w.kind, w.end is not None) for w in paused] == [("paused", True)]
    p03a = rec(tl, "03a")  # the later entry closes the interval of the earlier one
    assert len(p03a.waits) == 1 and p03a.waits[0].end is not None
    assert p03a.waits[0].end.moment.at == at("2026-10-21 10:15")
    p04 = rec(tl, "04")
    assert p04.waits[0].end is None  # open ⛔ interval
    assert "05" in tl.not_shown  # 🔄 but no Phase Log entry and no git
    labels = [it.label for it in tl.planning]
    assert labels == ["00", "plan", "+03a"]


def test_legacy_grammars_without_git(tmp_path: Path) -> None:
    (tmp_path / "ABC_IMPLEMENTATION_PLAN.md").write_text((FIXTURES / "legacy_dates.md").read_text())
    tl = build(tmp_path)
    assert tl.phases == []
    assert {"00", "01", "02"} <= set(tl.not_shown)
    assert any(s.startswith("planning 2026-10-12") for s in tl.not_shown)
    assert tl.not_started == ["03"]
    assert tl.as_of is None
    assert "No phase or planning session" in pt.render_svg(tl, 60)


# --- git fallbacks --------------------------------------------------------------------------


def _legacy_repo(tmp_path: Path) -> GitRepo:
    g = GitRepo(tmp_path)
    plan = (FIXTURES / "legacy_dates.md").read_text()
    g.commit("docs: bootstrap", "2026-10-11T10:00:00-05:00", {"ABC_IMPLEMENTATION_PLAN.md": plan})
    g.commit("chore(plan): start phase 01", "2026-10-11T10:30:00-05:00")
    g.git("checkout", "-q", "-b", "phase-01-x")
    g.commit("feat: thing (phase 01)", "2026-10-11T11:00:00-05:00")
    g.commit("docs(plan): complete phase 01", "2026-10-11T11:20:00-05:00")
    g.git("checkout", "-q", "main")
    g.merge("phase-01-x", "Merge phase 01: thing", "2026-10-11T12:00:00-05:00")
    g.commit("docs: Phase 03 prompt notes", "2026-10-12T09:00:00-05:00")  # not phase work
    g.commit("chore(plan): start phase 02", "2026-10-16T09:00:00-05:00")
    g.commit("feat: a", "2026-10-16T09:40:00-05:00")
    g.commit("feat: b", "2026-10-16T10:30:00-05:00")
    g.commit("feat: c, much later", "2026-10-16T15:00:00-05:00")
    return g


def test_git_fallbacks(tmp_path: Path) -> None:
    _legacy_repo(tmp_path)
    tl = build(tmp_path)
    p01 = rec(tl, "01")
    assert p01.start and p01.start.source == "git" and not p01.start.approx  # claim commit
    assert p01.merged and p01.merged.moment.at == at("2026-10-11 12:00") and not p01.merged.approx
    assert p01.finish and p01.finish.approx  # merged branch tip
    assert p01.finish.moment.at == at("2026-10-11 11:20")
    p02 = rec(tl, "02")  # no merge, no work mention: end of the commit burst
    assert p02.finish and p02.finish.approx and p02.finish.moment.at == at("2026-10-16 10:30")
    assert tl.not_started == ["03"]  # a prompt-edit commit never starts a ⬜ phase
    p00 = tl.planning[0]
    assert p00.label == "00" and p00.marker and p00.start and p00.start.approx
    assert {z for z in tl.zones} == {"CDT"}  # zone name from the plan text


def test_blocked_and_resume_commits(tmp_path: Path) -> None:
    g = GitRepo(tmp_path)
    rows = [("01", "One", "✅ Complete"), ("02", "Two", "⛔ Blocked")]
    g.commit("init", "2026-10-01T08:00:00-05:00", {"ABC_IMPLEMENTATION_PLAN.md": plan_text(rows)})
    g.commit("chore(plan): start phase 01", "2026-10-01T09:00:00-05:00")
    g.commit("chore(plan): phase 01 blocked", "2026-10-01T09:10:00-05:00")
    g.commit("chore(plan): resume phase 01", "2026-10-01T09:40:00-05:00")
    g.commit("docs(plan): phase 01 complete", "2026-10-01T09:50:00-05:00")
    g.commit("chore(plan): start phase 02", "2026-10-01T10:00:00-05:00")
    g.commit("chore(plan): phase 02 blocked", "2026-10-01T10:20:00-05:00")
    tl = build(tmp_path)
    w1 = rec(tl, "01").waits
    assert len(w1) == 1 and w1[0].end and w1[0].end.moment.at == at("2026-10-01 09:40")
    assert pt.active_time(rec(tl, "01"), tl.as_of.at) == (
        timedelta(minutes=20),
        timedelta(minutes=30),
    )
    w2 = rec(tl, "02").waits
    assert len(w2) == 1 and w2[0].end is None
    assert w2[0].start.moment.at == at("2026-10-01 10:20")


# --- open bars, parallel phases, zones -------------------------------------------------------


def test_open_bars_end_at_as_of(tmp_path: Path) -> None:
    log = (
        "### 2026-10-01 09:00 CDT: Phase 01: One (✅ Complete)\n"
        "- **Timeline:** started 2026-10-01 08:00 CDT · finished 2026-10-01 09:00 CDT · "
        "merged 2026-10-01 09:00 CDT\n\n"
        "### 2026-10-01 09:30 CDT: Phase 02: Two (⛔ Blocked)\n"
        "- **Timeline:** started 2026-10-01 08:30 CDT · blocked 2026-10-01 09:30 CDT to (open)\n"
    )
    rows = [
        ("01", "One", "✅ Complete"),
        ("02", "Two", "⛔ Blocked"),
        ("03", "Three", "🔄 In progress"),
    ]
    g = GitRepo(tmp_path)
    g.commit(
        "init", "2026-10-01T07:00:00-05:00", {"ABC_IMPLEMENTATION_PLAN.md": plan_text(rows, log)}
    )
    g.commit("chore(plan): start phase 03", "2026-10-01T08:45:00-05:00")
    g.commit("unrelated later commit", "2026-10-02T08:45:00-05:00")
    tl = build(tmp_path)
    assert tl.as_of and tl.as_of.at == at("2026-10-01 09:30")  # never HEAD's time or now()
    assert pt.phase_end(rec(tl, "03"), tl.as_of.at) == tl.as_of.at
    active, waited = pt.active_time(rec(tl, "02"), tl.as_of.at)
    assert (active, waited) == (timedelta(hours=1), timedelta(0))
    # parallel: 01, 02 and 03 overlap in time, so they are one session
    segs = pt.sessions(pt.activity(tl, timedelta(minutes=60)), timedelta(minutes=60))
    assert len(segs) == 1
    svg = pt.render_svg(tl, 60)
    assert 'id="tl-p02-w1"' in svg and "url(#tl-hatch)" in svg


def test_dst_change_cdt_to_cst(tmp_path: Path) -> None:
    log = (
        "### 2026-11-01 01:50 CDT: Phase 01: One (✅ Complete)\n"
        "- **Timeline:** started 2026-11-01 01:20 CDT (claim commit CLAIM1) · "
        "finished 2026-11-01 01:50 CDT\n\n"
        "### 2026-11-01 01:40 CST: Phase 02: Two (✅ Complete)\n"
        "- **Timeline:** started 2026-11-01 01:10 CST (claim commit CLAIM2) · "
        "finished 2026-11-01 01:40 CST\n"
    )
    rows = [("01", "One", "✅ Complete"), ("02", "Two", "✅ Complete")]
    g = GitRepo(tmp_path)
    g.commit("init", "2026-10-31T23:00:00-05:00", {"ABC_IMPLEMENTATION_PLAN.md": "x"})
    c1 = g.commit("chore(plan): start phase 01", "2026-11-01T01:20:00-05:00")
    c2 = g.commit("chore(plan): start phase 02", "2026-11-01T01:10:00-06:00")
    text = plan_text(rows, log.replace("CLAIM1", c1).replace("CLAIM2", c2))
    (tmp_path / "ABC_IMPLEMENTATION_PLAN.md").write_text(text)
    tl = build(tmp_path)
    s1, s2 = rec(tl, "01").start, rec(tl, "02").start
    assert s1 and s2 and s2.moment.at - s1.moment.at == timedelta(minutes=50)  # 01:10 CST is later
    assert s2.moment.stamp() == "2026-11-01 01:10 CST"
    assert set(tl.zones) == {"CDT", "CST"}


def test_gap_collapsing_threshold() -> None:
    base = at("2026-10-01 08:00")
    spans = [pt.Span(base, base + timedelta(minutes=10))]
    exactly = [*spans, pt.Span(base + timedelta(minutes=70), base + timedelta(minutes=80))]
    over = [*spans, pt.Span(base + timedelta(minutes=71), base + timedelta(minutes=80))]
    assert len(pt.sessions(exactly, timedelta(minutes=60))) == 1
    assert len(pt.sessions(over, timedelta(minutes=60))) == 2


def test_late_merge_does_not_join_sessions(tmp_path: Path) -> None:
    log = (
        "### 2026-10-01 09:00 CDT: Phase 01: One (✅ Complete)\n"
        "- **Timeline:** started 2026-10-01 08:50 CDT · finished 2026-10-01 09:00 CDT · "
        "merged 2026-10-01 15:00 CDT\n\n"
        "### 2026-10-01 16:00 CDT: Phase 02: Two (✅ Complete)\n"
        "- **Timeline:** started 2026-10-01 15:30 CDT · finished 2026-10-01 16:00 CDT · "
        "merged 2026-10-01 16:00 CDT\n"
    )
    (tmp_path / "ABC_IMPLEMENTATION_PLAN.md").write_text(
        plan_text([("01", "One", "✅ Complete"), ("02", "Two", "✅ Complete")], log)
    )
    tl = build(tmp_path)
    assert len(pt.sessions(pt.activity(tl, timedelta(hours=1)), timedelta(hours=1))) == 2
    assert "merged 15:00" in pt.render_svg(tl, 60)


# --- Markdown ---------------------------------------------------------------------------------


def test_mermaid_escaping() -> None:
    assert pt.mermaid_text("a: b # c; d `e`") == "a - b No. c, d e"
    assert ":" not in pt.mermaid_text("x:y") and ";" not in pt.mermaid_text(";")


def test_block_contents(tmp_path: Path) -> None:
    (tmp_path / "XYZ_IMPLEMENTATION_PLAN.md").write_text((FIXTURES / "modern.md").read_text())
    tl = build(tmp_path)
    block = pt.render_block(tl, 60, "docs/XYZ_TIMELINE.svg")
    assert block.startswith("![XYZ timeline](docs/XYZ_TIMELINE.svg)")
    assert block.count("```mermaid") == len(
        pt.sessions(pt.activity(tl, timedelta(hours=1)), timedelta(hours=1))
    )
    assert ":crit," in block and ":done," in block
    header = next(ln for ln in block.splitlines() if ln.startswith("| Phase |"))
    assert "Status" not in header
    assert "**Totals:**" in block and "**Not shown (no usable times):** 05." in block
    assert "## " not in block and "### " not in block
    assert "![" not in pt.render_block(tl, 60, None)


# --- files: markers, atomic write, check, determinism -------------------------------------------


def _phx_repo(tmp_path: Path) -> Path:
    g = GitRepo(tmp_path)
    plan = (FIXTURES / "modern.md").read_text()
    g.commit(
        "docs(plan): bootstrap", "2026-10-20T19:28:00-05:00", {"XYZ_IMPLEMENTATION_PLAN.md": plan}
    )
    g.commit("chore(plan): start phase 05", "2026-10-21T12:00:00-05:00")
    return tmp_path


def run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--repo", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_write_check_and_determinism(tmp_path: Path) -> None:
    root = _phx_repo(tmp_path)
    plan = root / "XYZ_IMPLEMENTATION_PLAN.md"
    before = plan.read_text()
    assert run(root, "--check").returncode == 1
    first = run(root, "--write")
    assert first.returncode == 0, first.stderr
    svg = root / "docs" / "XYZ_TIMELINE.svg"
    snapshot = (plan.read_text(), svg.read_text())
    second = run(root, "--write")
    assert "up to date" in second.stdout
    assert (plan.read_text(), svg.read_text()) == snapshot  # byte-identical
    assert run(root, "--check").returncode == 0
    # text outside the markers is untouched
    after = plan.read_text()
    s, e = after.index(pt.START_MARKER), after.index(pt.END_MARKER)
    bs, be = before.index(pt.START_MARKER), before.index(pt.END_MARKER)
    assert after[:s] == before[:bs] and after[e:] == before[be:]
    # a real change makes it stale
    plan.write_text(after.replace("| 05 | Phase five", "| 05 | Phase 5"))
    stale = run(root, "--check")
    assert stale.returncode == 1 and "timeline stale" in stale.stderr


def test_print_mode(tmp_path: Path) -> None:
    root = _phx_repo(tmp_path)
    out = run(root, "--print")
    assert out.returncode == 0 and out.stdout.startswith("![XYZ timeline]")
    assert not (root / "docs").exists()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda t: t.replace(pt.START_MARKER + "\n", ""),
        lambda t: t.replace(pt.END_MARKER + "\n", ""),
        lambda t: t + "\n" + pt.START_MARKER + "\n" + pt.END_MARKER + "\n",
    ],
)
def test_marker_errors_exit_2(tmp_path: Path, mutate: object) -> None:
    root = _phx_repo(tmp_path)
    plan = root / "XYZ_IMPLEMENTATION_PLAN.md"
    plan.write_text(mutate(plan.read_text()))  # type: ignore[operator]
    before = plan.read_bytes()
    out = run(root, "--write")
    assert out.returncode == 2 and "phase_timeline:" in out.stderr
    assert plan.read_bytes() == before


def test_block_before_phase_table_refused(tmp_path: Path) -> None:
    text = plan_text([("01", "One", "✅ Complete")], block=False)
    text = text.replace("## Phases", f"{pt.START_MARKER}\n{pt.END_MARKER}\n\n## Phases")
    (tmp_path / "ABC_IMPLEMENTATION_PLAN.md").write_text(text)
    out = run(tmp_path, "--write")
    assert out.returncode == 2 and "after the phase table" in out.stderr


def test_missing_plan_exit_2(tmp_path: Path) -> None:
    out = run(tmp_path, "--check")
    assert out.returncode == 2 and "IMPLEMENTATION_PLAN.md" in out.stderr


def test_vault_note_and_final_report(tmp_path: Path) -> None:
    root = _phx_repo(tmp_path)
    (root / "docs").mkdir()
    report = root / "docs" / "XYZ_FINAL-REPORT.md"
    report.write_text(f"# Report\n\n## 5. Timeline\n{pt.START_MARKER}\n{pt.END_MARKER}\n\nEnd.\n")
    note = tmp_path / "note.md"
    note.write_text(f"---\nx: 1\n---\n## Timeline\n{pt.START_MARKER}\n{pt.END_MARKER}\n")
    assert run(root, "--write", "--vault-note", str(note)).returncode == 0
    assert "![XYZ timeline](XYZ_TIMELINE.svg)" in report.read_text()
    assert report.read_text().endswith("\n\nEnd.\n")
    assert "```mermaid" in note.read_text() and "![" not in note.read_text()
    missing = run(root, "--check", "--vault-note", str(tmp_path / "nope.md"))
    assert missing.returncode == 2


def test_atomic_write_failure_keeps_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "f.md"
    target.write_text("original\n")

    def boom(src: str, dst: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(pt.os, "replace", boom)
    with pytest.raises(OSError):
        pt.atomic_write(target, "new\n")
    assert target.read_text() == "original\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["f.md"]


def test_phx_parsers_unaffected(tmp_path: Path) -> None:
    root = _phx_repo(tmp_path)
    plan = root / "XYZ_IMPLEMENTATION_PLAN.md"
    before = plan.read_text()
    assert run(root, "--write").returncode == 0
    after = plan.read_text()
    assert phx_plan.parse_phase_table(before) == phx_plan.parse_phase_table(after)
    for pid in ("01", "03a", "04"):
        old = [
            (e.heading, e.status, e.first_bullet) for e in phx_verify.phase_log_entries(before, pid)
        ]
        new = [
            (e.heading, e.status, e.first_bullet) for e in phx_verify.phase_log_entries(after, pid)
        ]
        assert old == new


# --- SVG ---------------------------------------------------------------------------------------


def test_svg_is_static_and_accessible(tmp_path: Path) -> None:
    root = _phx_repo(tmp_path)
    assert run(root, "--write").returncode == 0
    text = (root / "docs" / "XYZ_TIMELINE.svg").read_text()
    tree = ET.fromstring(text)
    ns = "{http://www.w3.org/2000/svg}"
    assert tree.get("role") == "img"
    assert tree.find(f"{ns}title") is not None and tree.find(f"{ns}desc") is not None
    assert "Phase 03 Phase three" in (tree.find(f"{ns}desc").text or "")  # type: ignore[union-attr]
    tags = {el.tag.removeprefix(ns) for el in tree.iter()}
    assert not tags & {"script", "foreignObject", "image"}
    assert "prefers-color-scheme: dark" in text and "http" not in text.replace(
        "http://www.w3.org/2000/svg", ""
    )


def test_golden_files(tmp_path: Path) -> None:
    """Golden SVG and block for the ``modern.md`` fixture repo (``UPDATE_GOLDEN=1`` to refresh)."""
    root = _phx_repo(tmp_path)
    assert run(root, "--write").returncode == 0
    svg = (root / "docs" / "XYZ_TIMELINE.svg").read_text()
    plan = (root / "XYZ_IMPLEMENTATION_PLAN.md").read_text()
    block = plan[plan.index(pt.START_MARKER) : plan.index(pt.END_MARKER) + len(pt.END_MARKER)]
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.mkdir(parents=True, exist_ok=True)
        (GOLDEN / "XYZ_TIMELINE.svg").write_text(svg)
        (GOLDEN / "XYZ_block.md").write_text(block + "\n")
    assert svg == (GOLDEN / "XYZ_TIMELINE.svg").read_text()
    assert block + "\n" == (GOLDEN / "XYZ_block.md").read_text()


# --- packaging -----------------------------------------------------------------------------------


def test_repo_copy_matches_skill_copy() -> None:
    assert REPO_SCRIPT.read_bytes() == SKILL_SCRIPT.read_bytes()


def test_python39_syntax_and_header() -> None:
    source = SKILL_SCRIPT.read_text()
    ast.parse(source, feature_version=(3, 9))
    assert "SPDX-License-Identifier: MIT" in source
    assert re.search(r"^TIMELINE_FORMAT = 1$", source, re.M)
    imports = {
        n.names[0].name.split(".")[0]
        if isinstance(n, ast.Import)
        else (n.module or "").split(".")[0]
        for n in ast.walk(ast.parse(source))
        if isinstance(n, ast.Import | ast.ImportFrom)
    }
    assert imports <= set(sys.stdlib_module_names) | {"__future__"}
    assert "datetime.now" not in source and "time.time" not in source


def test_bootstrap_from_templates_shows_phase00(tmp_path: Path) -> None:
    """A new project from the skill templates has the script, the markers and a Phase 00 bar."""
    from plugin_render import TEMPLATES, render, settings_values

    text = render((TEMPLATES / "IMPLEMENTATION_PLAN.md").read_text(), settings_values(None))
    fills = {
        "PREFIX": "NEW",
        "PHASE00_STARTED": "2026-10-01 09:00 CDT",
        "TIMESTAMP": "2026-10-01 09:30 CDT",
        "PHASE_ROWS": "| 01 | First | x | Sonnet 5.5 | 00 | ⬜ Not started | n/a | auto |",
        "PLANNING_MODEL": "Opus 5.5",
    }
    text = re.sub(r"\{\{([A-Z0-9_]+)\}\}", lambda m: fills.get(m.group(1), "x"), text)
    g = GitRepo(tmp_path)
    (tmp_path / "NEW_IMPLEMENTATION_PLAN.md").write_text(text)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "phase_timeline.py").write_bytes(SKILL_SCRIPT.read_bytes())
    out = subprocess.run(
        [sys.executable, "scripts/phase_timeline.py", "--write"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.returncode == 0, out.stderr
    g.git("add", "-A")
    g.commit("docs(plan): phase 00 planning", "2026-10-01T09:31:00-05:00")
    svg = (tmp_path / "docs" / "NEW_TIMELINE.svg").read_text()
    assert 'id="tl-p00"' in svg and "Not started: 01." in svg
    check = subprocess.run(
        [sys.executable, "scripts/phase_timeline.py", "--check"], cwd=tmp_path, check=False
    )
    assert check.returncode == 0
