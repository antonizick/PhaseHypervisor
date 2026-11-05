"""``phx report`` project summaries: descriptions, the Phase Log, sanitising (Phase 12g)."""

import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import report_events as ev
from phx.cli import main
from phx.report import load as L
from phx.report import model as M
from phx.report import projects as P
from phx.report import render as R

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures" / "report"
READMES = FIXTURES / "readmes"
PLAN = FIXTURES / "plans" / "SAM_IMPLEMENTATION_PLAN.md"
TIMELINE_SCRIPT = HERE.parent / "scripts" / "phase_timeline.py"
SECRET = "not-a-real-value"  # pragma: allowlist secret
NOV_02_2026 = 1793577600.0  # 2026-11-02 00:00 UTC


def use_zone(monkeypatch: pytest.MonkeyPatch, zone: str) -> None:
    monkeypatch.setenv("TZ", zone)
    time.tzset()


@pytest.fixture(autouse=True)
def utc(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    use_zone(monkeypatch, "UTC")
    yield
    monkeypatch.undo()
    time.tzset()


@pytest.fixture
def chicago(monkeypatch: pytest.MonkeyPatch) -> None:
    use_zone(monkeypatch, "America/Chicago")


def readme(name: str) -> str:
    return (READMES / f"{name}.md").read_text(encoding="utf-8")


def hostile() -> str:
    text = readme("hostile").replace("{ESC}", "\x1b").replace("{BEL}", "\x07")
    return text.replace("{KEY}", f"MY_API_KEY={SECRET}")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def make_repo(root: Path, name: str, files: dict[str, str | bytes]) -> Path:
    repo = root / name
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    (repo / "keep").write_text("x")
    for path, content in files.items():
        if isinstance(content, bytes):
            (repo / path).write_bytes(content)
        else:
            (repo / path).write_text(content, encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "init")
    return repo


def standard(root: Path, name: str = "sample") -> Path:
    return make_repo(
        root,
        name,
        {
            "README.md": readme("quote-first"),
            "SAM_IMPLEMENTATION_PLAN.md": PLAN.read_text(encoding="utf-8"),
        },
    )


def write_log(state: Path, project: str, events: list[ev.Event]) -> None:
    (state / project).mkdir(parents=True)
    (state / project / "run.jsonl").write_text(ev.lines(events), encoding="utf-8")


def session(phase: str, epoch: float, sid: str = "s") -> list[ev.Event]:
    return [ev.launch(phase, epoch - 100, sid), ev.end(phase, epoch, sid)]


def build(events: list[ev.Event], project: str = "sample", **kw: Any) -> M.Report:
    return M.build([L.Source(project, events)], **kw)


def merged(report: M.Report, names: dict[str, str] | None = None) -> list[M.PhaseWork]:
    logged, _ = P.parse_phase_log(PLAN.read_text(encoding="utf-8"))
    start = M.parse_bound(report.since, end=False) if report.since else None
    stop = M.parse_bound(report.until, end=True) if report.until else None
    return P.merge_phases(report, "sample", logged, names or {}, start, stop)


# --- describe ------------------------------------------------------------------------


def test_tagline_outranks_prose_past_the_opening() -> None:
    assert describe_of("tagline-first") == "Turn a folder of notes into a tidy weekly digest."


def describe_of(name: str) -> str | None:
    return P.describe(readme(name))


def test_html_first_opening_reduces_markdown_to_text() -> None:
    text = describe_of("html-first")
    assert text is not None
    assert text.startswith("Drop in a folder. Sample Project reads each note, finds the themes")
    assert "`" not in text and "](" not in text and "*" not in text
    assert "snake" in text


def test_quote_first_opening_finds_the_paragraph() -> None:
    assert describe_of("quote-first") == (
        "Sample Project is a local web service for managing notes through a plain JSON API."
    )


def test_no_prose_is_none() -> None:
    assert describe_of("no-prose") is None
    assert P.describe("") is None


def test_tagline_is_the_fallback() -> None:
    assert P.describe("# T\n\n**Short and bold tagline line.**\n\n- x\n") == (
        "Short and bold tagline line."
    )


def test_prose_in_the_opening_beats_a_tagline() -> None:
    text = "# T\n\n**A tagline here.**\n\nThe real opening paragraph of this project.\n"
    assert P.describe(text) == "The real opening paragraph of this project."


def test_front_matter_comments_and_setext_are_skipped() -> None:
    text = (
        "---\ntitle: Not this one at all please\n---\n<!-- a comment\nspanning two lines -->\n"
        "A heading that is long enough\n---\n\nThe body paragraph is what we want here.\n"
    )
    assert P.describe(text) == "The body paragraph is what we want here."


def test_a_sentence_with_a_colon_is_prose() -> None:
    text = "A rather useful command line tool: it keeps your notes in order.\n"
    assert P.describe(text) == text.strip()


def test_bold_status_label_is_not_a_description() -> None:
    assert P.describe("**Status:** in use by a few people now\n") is None


def test_cap_on_a_word_boundary() -> None:
    text = P.describe("word " * 200)
    assert text is not None
    assert len(text) <= P.DESCRIPTION_CAP
    assert text.endswith("word…")


def test_cap_cuts_before_a_long_word() -> None:
    assert P.describe("# T\n\none two three four " + "x" * 400) == "one two three four…"


def test_a_secret_is_redacted_before_the_cap() -> None:
    token = "ghp_" + "a" * 36
    text = P.describe("word " * 56 + f"token {token} more words after that")
    assert text is not None
    assert "ghp_" not in text


def test_hostile_size_stays_quick() -> None:
    started = time.monotonic()
    P.describe("[" * 1_000_000)
    P.describe("a *b " * 200_000)
    assert time.monotonic() - started < 2


# --- Sanitising ----------------------------------------------------------------------


def test_clean_drops_escapes_controls_and_secrets() -> None:
    text = P.clean("a\x1b[31mb\x1b]0;t\x07c\x9b2Jd\x07e‮f\ng MY_API_KEY=abc")
    assert text == "abcdef g MY_API_KEY=[REDACTED]"


def test_inert_leaves_nothing_active() -> None:
    text = P.inert("[[x]] a|b # c <b> `d` %%e%% \\")
    assert "[[" not in text
    assert "<b>" not in text
    assert "\\|" in text and "\\#" in text and "\\`" in text
    assert "%%" not in text


def test_hostile_description_is_inert() -> None:
    text = P.describe(hostile())
    assert text is not None
    assert "\x1b" not in text and "\x07" not in text and "\n" not in text
    assert SECRET not in text and "<script" not in text
    assert "[[Planted Link]]" in text  # shown as written; Markdown is what escapes it


# --- Phase Log -----------------------------------------------------------------------


def logged() -> dict[str, P.LogPhase]:
    phases, _ = P.parse_phase_log(PLAN.read_text(encoding="utf-8"))
    return {p.phase: p for p in phases}


def local(text: str) -> float:
    return time.mktime(time.strptime(text, "%Y-%m-%d %H:%M"))


@pytest.mark.usefixtures("chicago")
def test_zones_on_both_sides_of_the_change() -> None:
    phase = logged()["02"]
    assert phase.started == local("2026-10-31 22:00")
    assert phase.finished == local("2026-11-02 09:00")
    assert phase.status == "complete"


@pytest.mark.usefixtures("chicago")
def test_cdt_and_cst_are_an_hour_apart() -> None:
    cdt = "## Phase Log\n### 2026-11-01 01:30 CDT: Phase 01: A (Complete)\n"
    cst = "## Phase Log\n### 2026-11-01 01:30 CST: Phase 01: A (Complete)\n"
    earlier = P.parse_phase_log(cdt)[0][0].started
    later = P.parse_phase_log(cst)[0][0].started
    assert later - earlier == 3600


def test_an_unknown_zone_falls_back_to_the_date_and_says_so() -> None:
    phases, unknown = P.parse_phase_log(PLAN.read_text(encoding="utf-8"))
    assert unknown == {"CDT", "CST"}
    by_id = {p.phase: p for p in phases}
    assert by_id["01"].started == local("2026-10-05 00:00")
    assert by_id["01"].finished == local("2026-10-05 23:59") + 59


@pytest.mark.usefixtures("chicago")
def test_open_entries_have_no_finish() -> None:
    phases = logged()
    assert phases["03"].status == "blocked"
    assert phases["03"].finished is None
    assert phases["04"].status is None
    assert phases["04"].finished is None


@pytest.mark.usefixtures("chicago")
def test_legacy_entry_uses_its_heading() -> None:
    phase = logged()["05"]
    assert phase.started == local("2026-11-04 00:00")
    assert phase.finished == local("2026-11-04 23:59") + 59


@pytest.mark.usefixtures("chicago")
def test_a_start_not_recorded_falls_back_to_the_finish() -> None:
    phase = logged()["06"]
    assert phase.started == phase.finished == local("2026-11-05 11:00")


def test_planning_phase_00_and_other_sections_are_skipped() -> None:
    assert sorted(logged()) == ["01", "02", "03", "04", "05", "06"]


def test_entries_of_one_phase_join_up() -> None:
    text = (
        "## Phase Log\n"
        "### 2026-11-01 10:00 UTC: Phase 01: A (⛔ Blocked)\n"
        "- **Timeline:** started 2026-11-01 09:00 UTC · blocked 2026-11-01 10:00 UTC to (open)\n"
        "### 2026-11-03 10:00 UTC: Phase 01: A (✅ Complete)\n"
        "- **Timeline:** started 2026-11-03 09:00 UTC · finished 2026-11-03 10:00 UTC\n"
    )
    (phase,) = P.parse_phase_log(text)[0]
    assert phase.started == local("2026-11-01 09:00")
    assert phase.finished == local("2026-11-03 10:00")
    assert phase.status == "complete"


def test_an_impossible_date_is_ignored() -> None:
    text = "## Phase Log\n### 2026-13-45 10:00 UTC: Phase 01: A (Interim)\n"
    assert P.parse_phase_log(text)[0] == []


def test_a_plan_without_a_phase_log() -> None:
    assert P.parse_phase_log("# Plan\n") == ([], set())


def test_agrees_with_the_timeline_generator() -> None:
    spec = importlib.util.spec_from_file_location("phase_timeline_12g", TIMELINE_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["phase_timeline_12g"] = module
    spec.loader.exec_module(module)
    text = PLAN.read_text(encoding="utf-8")
    titles = [e.title for e in module.parse_phase_log(text.splitlines())]
    theirs = {t.split()[1].rstrip(":") for t in titles if t.startswith("Phase ")} - {"00"}
    assert {p.phase for p in P.parse_phase_log(text)[0]} == theirs


# --- Window and merge ----------------------------------------------------------------


def ids(work: list[M.PhaseWork]) -> list[str]:
    return [w.phase for w in work]


@pytest.mark.usefixtures("chicago")
def test_window_keeps_a_phase_straddling_each_edge() -> None:
    # 02 runs from Oct 31 to Nov 2: it straddles the end of October and the start of November.
    october = merged(build([], since="2026-10", until="2026-10"))
    assert ids(october) == ["01", "02"]
    assert [w.finished_in_period for w in october] == [True, False]
    november = merged(build([], since="2026-11", until="2026-11"))
    assert ids(november)[0] == "02"
    assert november[0].finished_in_period is True


@pytest.mark.usefixtures("chicago")
def test_window_drops_a_phase_wholly_outside() -> None:
    assert "01" not in ids(merged(build([], since="2026-11")))
    assert ids(merged(build([], until="2026-09"))) == []


@pytest.mark.usefixtures("chicago")
def test_open_phases_stay_active_after_they_start() -> None:
    work = merged(build([], since="2027"))
    assert ids(work) == ["03", "04"]
    assert not any(w.finished_in_period for w in work)
    assert all(w.finished is None for w in work)


@pytest.mark.usefixtures("chicago")
def test_quarter_and_year_edges() -> None:
    assert ids(merged(build([], since="2026-Q3", until="2026-Q3"))) == []
    assert "02" in ids(merged(build([], since="2026-Q4", until="2026-Q4")))
    assert ids(merged(build([], since="2025", until="2025"))) == []


def test_phx_only_with_no_log_entry() -> None:
    work = merged(build(session("09", NOV_02_2026)), {"09": "From the plan"})
    assert [(w.source, w.name) for w in work if w.phase == "09"] == [("phx", "From the plan")]


def test_a_phase_with_both_is_phx_once() -> None:
    work = merged(build(session("01", local("2026-10-05 11:00"))))
    assert ids(work).count("01") == 1
    assert next(w for w in work if w.phase == "01").source == "phx"
    assert next(w for w in work if w.phase == "02").source == "manual"


def test_a_session_outside_the_window_leaves_the_phase_manual() -> None:
    work = merged(
        build(session("02", local("2026-10-01 11:00")), since="2026-11-01", until="2026-11-30")
    )
    assert next(w for w in work if w.phase == "02").source == "manual"


def test_a_missing_name_is_the_id_alone() -> None:
    work = merged(build([]), {"01": "Known"})
    assert work[0].name == "Known"
    assert all(w.name is None for w in work[1:])


def test_triage_folds_into_its_phase_and_probes_are_no_phase() -> None:
    events = session("03-triage", NOV_02_2026) + session("probe", NOV_02_2026 + 9, "p")
    work = merged(build(events, since="2026-11-02", until="2026-11-02"))
    phx = [w for w in work if w.source == "phx"]
    assert ids(phx) == ["03"]
    assert "probe" not in ids(work)


def test_a_verified_completion_marks_a_phx_phase_finished() -> None:
    day = NOV_02_2026
    events = [*session("09", day), ev.verify("09", day + 1)]
    work = [w for w in merged(build(events)) if w.phase == "09"]
    assert work[0].finished_in_period is True
    assert work[0].finished is not None


def test_order_is_by_start_then_id() -> None:
    work = merged(build([]))
    keys = [w.started for w in work]
    assert keys == sorted(keys)


# --- Repo lookup ---------------------------------------------------------------------


def source(project: str, repo: str | None = None) -> L.Source:
    return L.Source(project, [ev.run_start(1.0, repo=repo)] if repo else [])


def test_lookup_prefers_the_latest_run_start(tmp_path: Path) -> None:
    root = tmp_path / "work"
    old, new = standard(root, "old"), standard(root, "new")
    events = [ev.run_start(1.0, repo=str(old)), ev.run_start(2.0, repo=str(new))]
    found = P.find_repos([L.Source("p", events)], {"PHX_WORK_ROOT": str(root)})
    assert found.paths == {"p": new.resolve()}


def test_lookup_falls_back_to_the_work_root(tmp_path: Path) -> None:
    repo = standard(tmp_path, "sample")
    found = P.find_repos([source("sample")], {"PHX_WORK_ROOT": str(tmp_path)})
    assert found.paths == {"sample": repo.resolve()}


def test_lookup_falls_back_when_the_logged_path_is_gone(tmp_path: Path) -> None:
    repo = standard(tmp_path, "sample")
    gone = str(tmp_path / "moved" / "sample")
    found = P.find_repos([source("sample", gone)], {"PHX_WORK_ROOT": str(tmp_path)})
    assert found.paths == {"sample": repo.resolve()}


def test_lookup_home_default(tmp_path: Path) -> None:
    repo = standard(tmp_path / "Work", "sample")
    found = P.find_repos([source("sample")], {"HOME": str(tmp_path)})
    assert found.paths == {"sample": repo.resolve()}


def test_a_folder_that_is_no_repo_is_not_found(tmp_path: Path) -> None:
    (tmp_path / "plain").mkdir()
    found = P.find_repos([source("plain")], {"PHX_WORK_ROOT": str(tmp_path)})
    assert found.paths == {}
    assert found.notes == {"plain": "repo not found"}
    assert found.warnings == []


def test_a_repo_outside_the_root_is_skipped_with_a_warning(tmp_path: Path) -> None:
    outside = standard(tmp_path / "elsewhere", "sample")
    root = tmp_path / "work"
    root.mkdir()
    found = P.find_repos([source("sample", str(outside))], {"PHX_WORK_ROOT": str(root)})
    assert found.paths == {}
    assert found.notes == {"sample": "repo is outside the work root"}
    assert "is outside" in found.warnings[0]


def test_a_symlink_out_of_the_root_is_skipped(tmp_path: Path) -> None:
    outside = standard(tmp_path / "elsewhere", "target")
    root = tmp_path / "work"
    root.mkdir()
    (root / "sample").symlink_to(outside)
    found = P.find_repos([source("sample")], {"PHX_WORK_ROOT": str(root)})
    assert found.paths == {}
    assert len(found.warnings) == 1


def test_a_note_is_written_for_each_failure_and_others_still_report(tmp_path: Path) -> None:
    root = tmp_path / "work"
    good = standard(root, "good")
    make_repo(root, "no-plan", {"README.md": readme("quote-first")})
    make_repo(root, "no-readme", {"SAM_IMPLEMENTATION_PLAN.md": PLAN.read_text("utf-8")})
    make_repo(root, "binary", {"README.md": b"\xff\xfe\x00bad"})
    broken = "# P\n\n| Phase | Status |\n|---|---|\n| 01 | ✅ Complete |\n"
    make_repo(root, "broken", {"README.md": "# T\n", "SAM_IMPLEMENTATION_PLAN.md": broken})
    names = ["good", "no-plan", "no-readme", "binary", "broken", "missing"]
    sources = [source(n) for n in names]
    repos = P.find_repos(sources, {"PHX_WORK_ROOT": str(root)})
    summaries, warnings = P.gather(M.build(sources), repos)
    by_name = {s.project: s for s in summaries}
    assert by_name["good"].description is not None
    assert by_name["good"].phases
    assert by_name["no-readme"].description_note == "no readable README.md on main"
    assert by_name["binary"].description_note == "no readable README.md on main"
    assert by_name["broken"].description_note == "the README has no prose paragraph"
    assert by_name["missing"].repo_found is False
    assert by_name["missing"].description_note == "repo not found"
    text = "\n".join(warnings)
    assert "no-plan: phases not read" in text
    assert "broken: phases not read" in text
    assert "good: zone CDT, CST is not local" in text
    assert good.exists()


def test_a_repo_without_main_is_a_warning(tmp_path: Path) -> None:
    repo = tmp_path / "sample"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "other")
    sources = [source("sample")]
    summaries, warnings = P.gather(
        M.build(sources), P.find_repos(sources, {"PHX_WORK_ROOT": str(tmp_path)})
    )
    assert summaries[0].description_note == "no readable README.md on main"
    assert "phases not read" in warnings[0]


# --- CLI and output ------------------------------------------------------------------


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A work root and state root: ``sample`` ran one session of phase 02 on Nov 2."""
    use_zone(monkeypatch, "America/Chicago")
    root = tmp_path / "work"
    repo = standard(root)
    monkeypatch.setenv("PHX_WORK_ROOT", str(root))
    day = local("2026-11-02 08:00")
    events = [ev.run_start(day - 50, repo=str(repo)), *session("02", day), ev.verify("02", day + 1)]
    write_log(tmp_path / "state", "sample", events)
    return tmp_path / "state"


def run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str]:
    code = main(["report", *args])
    return code, capsys.readouterr().out


def test_terminal_section_comes_first(world: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, "--state-root", str(world))
    assert code == 0
    assert out.index("Projects\nsample\n") < out.index("\nTotals\n")
    assert "Sample Project is a local web service" in out
    assert "02  Across the change" in out
    assert "phx, finished in period" in out
    assert "manual, time only" in out
    assert "01  First phase" in out  # backticks gone
    assert "A manual phase has no phx session" in out


def test_top_limits_phases(world: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _, out = run(capsys, "--state-root", str(world), "--top", "2")
    assert "  and 4 more" in out
    _, out = run(capsys, "--state-root", str(world), "--markdown", "--top", "2")
    assert "- and 4 more" in out


def test_markdown_section(world: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _, out = run(capsys, "--state-root", str(world), "--markdown")
    assert "## Projects\n\n### sample\n\n**What it is:** Sample Project is" in out
    assert "- 02 Across the change (phx, finished in period)" in out
    assert "\\[\\[y\\]\\]" in out and "[[y]]" not in out


def test_json_key_is_additive(world: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _, out = run(capsys, "--state-root", str(world), "--json")
    data = json.loads(out)
    assert data["schema"] == 1
    (summary,) = data["project_summaries"]
    assert set(summary) == {"project", "repo_found", "description", "description_note", "phases"}
    assert summary["repo_found"] is True
    assert set(summary["phases"][0]) == {
        "phase",
        "name",
        "source",
        "started",
        "finished",
        "finished_in_period",
    }


def strip_repo_parts(payload: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in payload.items() if k != "project_summaries"}
    out["caveats"] = [c for c in out["caveats"] if not c.startswith("Projects:")]
    return out


def test_resource_figures_do_not_change(
    world: Path, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    with_repos = json.loads(run(capsys, "--state-root", str(world), "--json")[1])
    logs_only = json.loads(run(capsys, "--state-root", str(world), "--json", "--no-repos")[1])
    assert "project_summaries" not in logs_only
    assert strip_repo_parts(with_repos) == logs_only
    run(capsys, "--state-root", str(world), "--svg", str(tmp_path / "a"))
    run(capsys, "--state-root", str(world), "--svg", str(tmp_path / "b"), "--no-repos")
    charts = sorted(p.name for p in (tmp_path / "a").iterdir())
    assert charts
    for name in charts:
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_no_repos_matches_a_report_without_summaries(
    world: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*_args: object, **_kw: object) -> None:
        raise AssertionError("--no-repos opened a repo")

    monkeypatch.setattr(P, "find_repos", fail)
    _, out = run(capsys, "--state-root", str(world), "--no-repos")
    assert "\nProjects\n" not in out
    assert "A manual phase" not in out


def fingerprint(root: Path) -> dict[str, str]:
    files = sorted(p for p in root.rglob("*") if p.is_file())
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def test_repos_and_state_are_unchanged(
    world: Path, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    before = fingerprint(tmp_path)
    run(capsys, "--state-root", str(world))
    run(capsys, "--state-root", str(world), "--json")
    assert fingerprint(tmp_path) == before


def test_one_git_show_per_file(
    world: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    shown: list[str] = []
    real = P.show_main

    def spy(repo: Path, path: str) -> str | None:
        shown.append(path)
        return real(repo, path)

    monkeypatch.setattr(P, "show_main", spy)
    run(capsys, "--state-root", str(world))
    assert sorted(shown) == ["README.md", "SAM_IMPLEMENTATION_PLAN.md"]


def test_a_window_of_manual_phases_only(world: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(
        capsys, "--state-root", str(world), "--since", "2026-10-05", "--until", "2026-10-06"
    )
    assert code == 0
    assert "01  First phase  manual, time only, finished in period" in out
    assert "Sample Project is" in out
    data = json.loads(
        run(
            capsys,
            "--state-root",
            str(world),
            "--since",
            "2026-10-05",
            "--until",
            "2026-10-06",
            "--json",
        )[1]
    )
    assert data["totals"]["sessions"] == 0
    assert data["totals"]["cost_usd"] is None or data["totals"]["cost_usd"] == 0
    assert data["phases"] == []
    assert data["project_summaries"][0]["phases"][0]["phase"] == "01"


def test_a_project_with_nothing_in_the_window_says_so(
    world: Path, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    make_repo(tmp_path / "work", "quiet", {"README.md": readme("html-first")})
    write_log(world, "quiet", [ev.run_start(local("2026-11-02 07:00"), repo="/gone")])
    _, out = run(capsys, "--state-root", str(world), "--since", "2026-11", "--until", "2026-11")
    assert "quiet\n" in out
    assert "No recorded work in this period." in out


def test_a_truly_empty_window_still_says_no_runs(
    world: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out = run(capsys, "--state-root", str(world), "--since", "2020", "--until", "2020")
    assert "no recorded runs" in out


def test_hostile_readme_is_inert_in_every_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "work"
    bad_name = "| 01 | [[x]] <b>y</b> \x1b[2J | a | Opus 5.5 | none | ⬜ Not started | n/a | auto |"
    plan = (
        "| Phase | Phase name | Purpose | AI Model to Use | Depends on | Status | Prompt | Gate |\n"
    )
    plan += "|---|---|---|---|---|---|---|---|\n" + bad_name + "\n"
    plan += "\n## Phase Log\n### 2026-11-02 08:00 UTC: Phase 01: A (Interim)\n"
    repo = make_repo(root, "bad", {"README.md": hostile(), "BAD_IMPLEMENTATION_PLAN.md": plan})
    monkeypatch.setenv("PHX_WORK_ROOT", str(root))
    state = tmp_path / "state"
    write_log(state, "bad", [ev.run_start(NOV_02_2026, repo=str(repo))])
    safe_args = ["--state-root", str(state)]
    _, text = run(capsys, *safe_args)
    _, markdown = run(capsys, *safe_args, "--markdown")
    _, as_json = run(capsys, *safe_args, "--json")
    for out in (text, markdown):
        assert "\x1b" not in out and "\x07" not in out
        assert SECRET not in out
        assert "<script" not in out
    assert SECRET not in as_json and "\\u001b" not in as_json
    assert "[[" not in markdown
    assert "<b>" not in markdown
    headings = [line for line in markdown.splitlines() if line.startswith("#")]
    assert not any("forged" in line for line in headings)
    assert "\\#\\# Totals" in markdown
    assert sum(1 for line in markdown.splitlines() if line == "## Totals") == 1
    assert sum(1 for line in text.splitlines() if line == "Totals") == 1


def test_vault_note_links_found_repos_and_keeps_text_inert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = M.ProjectSummary("p", True, "A [[plant]] here", None, [])
    report = build([])
    report.summaries = [summary]
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Alpha.md").write_text("x")
    monkeypatch.setattr(R, "note_path", lambda _repo: vault / "Alpha.md")
    path, _ = R.write_vault(
        report,
        [],
        [],
        top=5,
        repos=P.Repos(paths={"p": tmp_path}),
        env={"PHX_VAULT_ROOT": str(vault)},
    )
    assert path is not None
    text = path.read_text(encoding="utf-8")
    assert "[[Alpha]]" in text
    assert "[[plant]]" not in text


def test_no_repos_vault_note_has_no_project_links(tmp_path: Path) -> None:
    path, _ = R.write_vault(
        build([]), [], [], top=5, repos=P.Repos(), env={"PHX_VAULT_ROOT": str(tmp_path)}
    )
    assert path is not None
    assert "Project notes" not in path.read_text(encoding="utf-8")


def test_a_manual_only_window_saves_with_empty_charts(
    world: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("PHX_VAULT_ROOT", str(vault))
    run(capsys, "--state-root", str(world), "--since", "2026-10-05", "--until", "2026-10-06")
    folder = vault / "04 Resources" / "PHX Reports"
    assert len(list(folder.glob("*.md"))) == 1
    (charts,) = [p for p in folder.iterdir() if p.is_dir()]
    assert len(list(charts.glob("*.svg"))) == 4
