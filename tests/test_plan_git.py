"""``load_plan`` / ``load_live`` / ``detect_drift`` and ``phx plan`` on throwaway git repos."""

import json
from pathlib import Path

import pytest

from conftest import RepoFactory, git
from phx.cli import main
from phx.plan import (
    Gate,
    PlanError,
    Status,
    detect_drift,
    load_live,
    load_plan,
    locate_plan,
    next_eligible,
)

MINIMAL = (
    "## Phases\n| Phase | Phase Name | AI Model to Use | Depends on | Status | Prompt |\n"
    "|---|---|---|---|---|---|\n"
    "| 01 | One | Opus 5.5 | none | ✅ Complete | [p](prompts/X_phase-01.md) |\n"
    "| 02 | Two | Sonnet 5.5 | 01 | ⬜ Not started | [p](prompts/X_phase-02.md) |\n"
    "| 03 | Three | Haiku 5.5 | 01 | ⬜ Not started | [p](prompts/X_phase-03.md) |\n"
)
PROMPTS = {f"prompts/X_phase-0{i}.md": f"# X Phase 0{i}\n\n**Model:** Opus\n" for i in (1, 2, 3)}


# ---------------------------------------------------------------- the four real plans


@pytest.mark.parametrize(
    ("fixture", "plan_file", "next_id", "tests", "release", "open_ids"),
    [
        ("mm3", "MM3_IMPLEMENTATION_PLAN.md", "16", (), "16", []),
        ("cl", "CL_IMPLEMENTATION_PLAN.md", None, ("shellcheck lab/**/*.sh",), "13", []),
        ("occ", "OCC_IMPLEMENTATION_PLAN.md", "11", ("make check",), "12", ["9"]),
        (
            "ytpl2",
            "YTPL2_IMPLEMENTATION_PLAN.md",
            "03",
            ("make check",),
            "13",
            ["5", "6", "12", "14"],
        ),
    ],
)
def test_real_plans(
    make_repo: RepoFactory,
    fixture: str,
    plan_file: str,
    next_id: str | None,
    tests: tuple[str, ...],
    release: str,
    open_ids: list[str],
) -> None:
    plan = load_plan(make_repo(fixture))
    assert plan.plan_file == plan_file and plan.prefix == plan_file.split("_")[0]
    assert plan.contract is None  # not yet migrated (Phase 09)
    assert plan.test_commands == tests
    ids = [p.id for p in plan.phases]
    assert ids == sorted(ids, key=lambda i: (int(i[:2]), i[2:]))
    assert all(p.alias in {"opus", "sonnet"} for p in plan.phases)
    rel = plan.phase(release)
    assert (rel.gate, rel.gate_source) == (Gate.REVIEW, "inferred")
    assert [q.id for q in plan.questions if q.open] == open_ids
    e = next_eligible(plan)
    assert (e.next.id if e.next else None) == next_id
    assert e.resume == ()


def test_mm3_lettered_ids_and_long_dependency_list(make_repo: RepoFactory) -> None:
    plan = load_plan(make_repo("mm3"))
    assert [p.id for p in plan.phases][-15:] == [
        "15", "15a", "15b", "15c", "15d", "15e", "15f", "15g", "15h", "15i", "15j", "15k",
        "15l", "15m", "16",
    ]  # fmt: skip
    assert len(plan.phase("16").depends_on) == 14
    assert plan.phase("15g").depends_on == ("15d", "15e")
    q6 = next(q for q in plan.questions if q.id == "Q6")
    assert q6.needed_by == ("15a", "15b", "16")


def test_sample_plan(make_repo: RepoFactory) -> None:
    plan = load_plan(make_repo("sample"))
    assert plan.contract == 1 and plan.check_contract() == 1
    gates = {p.id: (p.gate, p.gate_source) for p in plan.phases}
    assert gates == {
        "00": (Gate.OWNER, "column"),
        "01": (Gate.AUTO, "column"),
        "01a": (Gate.REVIEW, "prompt"),
        "02": (Gate.REVIEW, "column"),
    }
    assert plan.phase("01a").alias == "haiku"
    assert plan.test_commands == ("test -f hello.txt",)
    assert plan.test_source == "shared-instructions"
    e = next_eligible(plan)
    assert e.next is not None and e.next.id == "01"
    assert e.reasons["02"].startswith("dependencies not complete: 01a")
    assert plan.problems == ()


# ---------------------------------------------------------------- locating and reading main


def test_legacy_unprefixed_plan(make_repo: RepoFactory) -> None:
    repo = make_repo(
        files={
            "IMPLEMENTATION_PLAN.md": MINIMAL,
            "prompts/_shared-instructions.md": "- Tests, lint and type checks pass: `pytest`.\n",
            **PROMPTS,
        }
    )
    plan = load_plan(repo)
    assert plan.legacy and plan.prefix is None and plan.plan_file == "IMPLEMENTATION_PLAN.md"
    assert plan.test_commands == ("pytest",)


def test_reads_main_not_working_tree(make_repo: RepoFactory) -> None:
    repo = make_repo(files={"X_IMPLEMENTATION_PLAN.md": MINIMAL, **PROMPTS})
    (repo / "X_IMPLEMENTATION_PLAN.md").write_text(MINIMAL.replace("⬜ Not started", "✅ Complete"))
    git(repo, "switch", "-q", "-c", "other")
    git(repo, "commit", "-q", "-am", "edit on a branch")
    plan = load_plan(repo)
    assert plan.phase("02").status is Status.NOT_STARTED


def test_several_plans_use_claude_md_prefix(make_repo: RepoFactory) -> None:
    files = {"A_IMPLEMENTATION_PLAN.md": MINIMAL, "B_IMPLEMENTATION_PLAN.md": MINIMAL}
    repo = make_repo(files={**files, "CLAUDE.md": "- **Project prefix: `B`.** Docs…\n"})
    assert locate_plan(repo) == ("B_IMPLEMENTATION_PLAN.md", "B")
    bare = make_repo(files=files, name="bare")
    with pytest.raises(PlanError, match="several plans"):
        locate_plan(bare)


def test_no_plan_not_git_no_main(make_repo: RepoFactory, tmp_path: Path) -> None:
    with pytest.raises(PlanError, match="no <PREFIX>_IMPLEMENTATION_PLAN"):
        load_plan(make_repo(files={"README.md": "x"}))
    with pytest.raises(PlanError, match="not a git checkout"):
        load_plan(tmp_path)
    repo = make_repo(files={"X_IMPLEMENTATION_PLAN.md": MINIMAL}, name="trunk")
    git(repo, "branch", "-m", "main", "trunk")
    with pytest.raises(PlanError, match="git rev-parse"):
        load_plan(repo)


def test_config_override_and_errors(make_repo: RepoFactory) -> None:
    shared = {"prompts/X_shared-instructions.md": "Tests, lint and type checks pass: `make`.\n"}
    repo = make_repo(
        files={
            "X_IMPLEMENTATION_PLAN.md": MINIMAL,
            ".phx/config.toml": 'test_command = "just ci"\n',
            **shared,
            **PROMPTS,
        }
    )
    plan = load_plan(repo)
    assert (plan.test_commands, plan.test_source) == (("just ci",), "config")
    bad = make_repo(
        files={"X_IMPLEMENTATION_PLAN.md": MINIMAL, ".phx/config.toml": "nope = 1\n"}, name="bad"
    )
    with pytest.raises(PlanError, match=r"main:\.phx/config\.toml: unknown config keys"):
        load_plan(bad)
    empty = make_repo(
        files={
            "X_IMPLEMENTATION_PLAN.md": MINIMAL,
            ".phx/config.toml": "triage = false\n",
            **shared,
        },
        name="empty",
    )
    assert load_plan(empty).test_commands == ("make",)


def test_gate_precedence_and_problems(make_repo: RepoFactory) -> None:
    plan_text = (
        "| Phase | Phase Name | AI Model to Use | Depends on | Status | Prompt | Gate |\n"
        "|---|---|---|---|---|---|---|\n"
        "| 01 | Col | Opus 5.5 | none | ⬜ Not started | [p](prompts/p1.md) | owner |\n"
        "| 02 | Prompt | Opus 5.5 | none | ⬜ Not started | [p](prompts/p2.md) | |\n"
        "| 03 | Infer | Opus 5.5 | none | ⬜ Not started | [p](prompts/p3.md) | |\n"
        "| 04 | Missing | Opus 5.5 | none | ⬜ Not started | [p](prompts/p4.md) | |\n"
        "| 05 | Done | Opus 5.5 | none | ✅ Complete | [p](prompts/p5.md) | |\n"
    )
    repo = make_repo(
        files={
            "X_IMPLEMENTATION_PLAN.md": plan_text,
            "prompts/p1.md": "# P1\n**Gate:** auto\nmake the repo public\n",
            "prompts/p2.md": "# P2\n**Model:** Opus · **Gate:** `auto`\npublish a GitHub release\n",
            "prompts/p3.md": "# P3\nAt the end, publish a GitHub release.\n",
        }
    )
    plan = load_plan(repo)
    got = {p.id: (p.gate, p.gate_source) for p in plan.phases}
    assert got == {
        "01": (Gate.OWNER, "column"),
        "02": (Gate.AUTO, "prompt"),
        "03": (Gate.REVIEW, "inferred"),
        "04": (Gate.AUTO, "default"),
        "05": (Gate.AUTO, "default"),
    }
    assert plan.problems == ("phase 04: prompt prompts/p4.md not found on main",)


def test_bad_gate_cell_names_the_line(make_repo: RepoFactory) -> None:
    text = MINIMAL.replace(
        "| Prompt |\n|---|---|---|---|---|---|", "| Prompt | Gate |\n|---|---|---|---|---|---|---|"
    )
    text = text.replace("X_phase-02.md) |", "X_phase-02.md) | later |")
    with pytest.raises(PlanError, match=r"line 5: phase 02: unknown gate 'later'"):
        load_plan(make_repo(files={"X_IMPLEMENTATION_PLAN.md": text, **PROMPTS}))


# ---------------------------------------------------------------- live state and drift

DRIFT_PLAN = (
    "| Phase | Phase Name | AI Model to Use | Depends on | Status | Prompt |\n"
    "|---|---|---|---|---|---|\n"
    "| 01 | Done | Opus 5.5 | none | ✅ Complete | x |\n"
    "| 02 | Claimed | Opus 5.5 | 01 | 🔄 In progress | x |\n"
    "| 03 | Stale | Opus 5.5 | 01 | 🔄 In progress | x |\n"
    "| 04 | Unclaimed | Opus 5.5 | 01 | ⬜ Not started | x |\n"
    "| 05 | Blocked | Opus 5.5 | 01 | ⛔ Blocked | x |\n"
    "| 06 | Fine | Opus 5.5 | 01 | ⬜ Not started | x |\n"
)


def test_live_state_and_drift(make_repo: RepoFactory, tmp_path: Path) -> None:
    repo = make_repo(files={"X_IMPLEMENTATION_PLAN.md": DRIFT_PLAN}, name="X")
    # 02: properly claimed, worktree with one uncommitted file
    git(repo, "worktree", "add", "-q", str(tmp_path / "X-phase-02"), "-b", "phase-02-claimed")
    (tmp_path / "X-phase-02" / "wip.txt").write_text("x")
    # 04: worktree without a claim; 01: leftover branch after completion
    git(repo, "worktree", "add", "-q", str(tmp_path / "X-phase-04"), "-b", "phase-04-unclaimed")
    git(repo, "branch", "phase-01-done")
    # 05: blocked keeps its branch on purpose; 09: not in the table
    git(repo, "branch", "phase-05-blocked")
    git(repo, "branch", "phase-09-ghost")
    # a detached worktree named like a phase, and an unrelated one
    git(repo, "worktree", "add", "-q", "--detach", str(tmp_path / "X-phase-06"))
    git(repo, "worktree", "add", "-q", "--detach", str(tmp_path / "scratch"))

    live = load_live(repo)
    assert live.branches == {
        "phase-01-done": "01",
        "phase-02-claimed": "02",
        "phase-04-unclaimed": "04",
        "phase-05-blocked": "05",
        "phase-09-ghost": "09",
    }
    trees = {w.phase: w for w in live.worktrees}
    assert set(trees) == {"02", "04", "06"}
    assert trees["02"].uncommitted == 1 and trees["02"].branch == "phase-02-claimed"
    assert trees["04"].uncommitted == 0 and trees["04"].last_commit
    assert trees["06"].branch is None

    plan = load_plan(repo)
    drift = {(d.phase, d.kind) for d in detect_drift(plan, live)}
    assert drift == {
        ("09", "unknown-phase"),
        ("01", "unclaimed"),
        ("03", "stale-claim"),
        ("04", "unclaimed"),
        ("06", "unclaimed"),
    }


def test_missing_worktree_path(make_repo: RepoFactory, tmp_path: Path) -> None:
    repo = make_repo(files={"X_IMPLEMENTATION_PLAN.md": DRIFT_PLAN}, name="X")
    wt = tmp_path / "X-phase-02"
    git(repo, "worktree", "add", "-q", str(wt), "-b", "phase-02-claimed")
    for f in wt.iterdir():
        f.unlink()
    wt.rmdir()
    (tree,) = load_live(repo).worktrees
    assert (tree.phase, tree.last_commit, tree.uncommitted) == ("02", None, None)


# ---------------------------------------------------------------- phx plan


def test_phx_plan_human(make_repo: RepoFactory, capsys: pytest.CaptureFixture[str]) -> None:
    repo = make_repo("ytpl2")
    head = git(repo, "rev-parse", "HEAD")
    assert main(["plan", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "Next: 03" in out
    assert "review (inferred)" in out
    assert "Open question #14 (needed by 04)" in out
    assert "Contract: repo not yet migrated" in out
    assert "Test command (shared-instructions): make check" in out
    assert git(repo, "rev-parse", "HEAD") == head and git(repo, "status", "--porcelain") == ""


def test_phx_plan_drift_and_resume(
    make_repo: RepoFactory, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(files={"X_IMPLEMENTATION_PLAN.md": DRIFT_PLAN}, name="X")
    git(repo, "worktree", "add", "-q", str(tmp_path / "X-phase-02"), "-b", "phase-02-claimed")
    assert main(["plan", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "Resume candidates (🔄): 02, 03" in out
    assert "⚠️  drift 03 (stale-claim)" in out
    assert "X-phase-02, phase-02-claimed" in out
    assert "Test command: none" in out
    assert "Next: 04" in out and "  06: eligible, after 04" in out


def test_phx_plan_json(make_repo: RepoFactory, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["plan", str(make_repo("sample")), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["next"] == "01" and data["contract"] == {"version": 1, "error": None}
    assert data["phases"][2]["id"] == "01a" and data["phases"][2]["gate"] == "review"
    assert data["open_questions"][0]["id"] == "1"
    assert data["drift"] == [] and data["problems"] == []


def test_phx_plan_problems_and_errors(
    make_repo: RepoFactory, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = MINIMAL.replace("Haiku 5.5", "GPT-9")
    assert main(["plan", str(make_repo(files={"X_IMPLEMENTATION_PLAN.md": text, **PROMPTS}))]) == 0
    out = capsys.readouterr().out
    assert "⚠️  phase 03: unknown model 'GPT-9'" in out
    assert main(["plan", str(tmp_path / "nowhere")]) == 1
    assert "phx plan: " in capsys.readouterr().err


def test_bare_repo_has_no_phase_worktrees(tmp_path: Path) -> None:
    bare = tmp_path / "b.git"
    bare.mkdir()
    git(bare, "init", "-q", "--bare", "-b", "main")
    live = load_live(bare)
    assert live.branches == {} and live.worktrees == ()
