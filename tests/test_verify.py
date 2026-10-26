import json
import os
from pathlib import Path

import pytest

from conftest import RepoFactory
from phx.classify import Classification, ExitClass, PhxResult
from phx.logging import EventLog
from phx.paths import Config
from phx.plan import load_plan, set_status_cell
from phx.verify import (
    Baseline,
    CheckStatus,
    Outcome,
    RepoState,
    UnsupportedCommand,
    capture_baseline,
    parse_command,
    phase_log_entries,
    run_command,
    run_tests,
    verify_phase,
    wip_blocked,
)
from scenarios import BLOCKED_LOG, BRANCH, PLAN, Scenario, git, render

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "plans"


def result(status: str, **kw: object) -> Classification:
    fields: dict[str, object] = {
        "contract": 1,
        "phase": "05",
        "status": status,
        "reason": "r",
        "merged": status == "complete",
        "pushed": False,
        "question_ids": ("6",) if status == "blocked" else (),
    }
    fields.update(kw)
    return Classification(ExitClass(status), "result line", result=PhxResult(**fields))  # type: ignore[arg-type]


def snapshot(repo: Path) -> tuple[str, str, str, str, str]:
    """Everything verification must leave alone in the user's main checkout."""
    return (
        git(repo, "rev-parse", "HEAD"),
        git(repo, "status", "--porcelain"),
        git(repo, "worktree", "list", "--porcelain"),
        git(repo, "branch", "--list"),
        (repo / PLAN).read_text(),
    )


@pytest.fixture
def sc(tmp_path: Path) -> Scenario:
    return Scenario(tmp_path)


# --- complete -----------------------------------------------------------------------


def test_complete_verified(sc: Scenario, tmp_path: Path) -> None:
    sc.claim().work().complete()
    log = EventLog(tmp_path / "state" / "run.jsonl")
    before = snapshot(sc.repo)
    v = verify_phase(sc.repo, "05", result("complete"), log=log)
    assert v.outcome is Outcome.COMPLETE and v.ok, v.report()
    assert v.state is RepoState.COMPLETE
    names = {c.name: c.status for c in v.checks}
    for name in (
        "status",
        "branch_merged",
        "branch_deleted",
        "worktree_removed",
        "phase_log",
        "main_checkout",
        "main_clean",
        "tests",
    ):
        assert names[name] is CheckStatus.PASS, name
    assert names["pushed"] is CheckStatus.SKIP
    assert "`test -f hello.txt`: pass" in v.check("tests").evidence  # type: ignore[union-attr]
    assert snapshot(sc.repo) == before  # verification never touches the main checkout
    record = json.loads((tmp_path / "state" / "run.jsonl").read_text().splitlines()[-1])
    assert record["event"] == "verify" and record["reason"] == "complete and verified"
    assert record["outcome"] == "complete" and record["session_class"] == "complete"


def test_tests_run_on_a_clean_clone_not_the_checkout(sc: Scenario) -> None:
    sc.claim().complete(merge=False, remove_worktree=False, delete_branch=False)
    # hello.txt exists only as an untracked file in the main checkout: the clone has none
    git(sc.repo, "merge", "-q", "--ff-only", BRANCH)
    git(sc.repo, "worktree", "remove", str(sc.worktree))
    git(sc.repo, "branch", "-q", "-d", BRANCH)
    (sc.repo / "hello.txt").write_text("untracked\n")
    v = verify_phase(sc.repo, "05", baseline=Baseline(None, frozenset({"?? hello.txt"})))
    tests = v.check("tests")
    assert tests is not None and tests.status is CheckStatus.FAIL
    assert "exit 1" in tests.evidence
    assert v.outcome is Outcome.FAILED
    assert (sc.repo / "hello.txt").read_text() == "untracked\n"


def test_complete_but_branch_and_worktree_left(sc: Scenario) -> None:
    sc.claim().work().complete(remove_worktree=False, delete_branch=False)
    v = verify_phase(sc.repo, "05")
    assert v.outcome is Outcome.FAILED
    failed = {c.name for c in v.failures}
    assert failed == {"branch_deleted", "worktree_removed"}
    assert BRANCH in v.check("branch_deleted").evidence  # type: ignore[union-attr]
    assert "verification failed: branch_deleted" in v.summary()


def test_complete_but_not_merged(sc: Scenario) -> None:
    sc.claim().work()
    git(sc.worktree, "commit", "-q", "--allow-empty", "-m", "extra")
    # the ✅ reached main by hand while the branch still has unmerged commits
    sc.write_plan(
        sc.repo, render("✅ Complete", log=BLOCKED_LOG.replace("⛔ Blocked", "✅ Complete")), "x"
    )
    v = verify_phase(sc.repo, "05", result("complete"))
    assert v.check("branch_merged").status is CheckStatus.FAIL  # type: ignore[union-attr]
    assert v.outcome is Outcome.NEEDS_REVIEW  # merged:true contradicts the repo
    assert "agent said merged, but the phase branch is not merged" in v.disagreements


def test_complete_without_timeline(sc: Scenario) -> None:
    sc.claim().work().complete(
        log="\n### 2026-10-26 11:30 CDT: Phase 05: Thing (✅ Complete)\n- Built.\n"
    )
    v = verify_phase(sc.repo, "05")
    check = v.check("phase_log")
    assert check is not None and check.status is CheckStatus.FAIL
    assert "first bullet is not the Timeline" in check.evidence


def test_complete_without_log_entry(sc: Scenario) -> None:
    sc.claim().work().complete(log="")
    assert "no Phase Log entry" in verify_phase(sc.repo, "05").check("phase_log").evidence  # type: ignore[union-attr]


def test_main_dirty_fails_unless_preexisting(sc: Scenario) -> None:
    sc.claim().work().complete()
    (sc.repo / "notes.txt").write_text("mine\n")
    v = verify_phase(sc.repo, "05", run_test_commands=False)
    assert v.check("main_clean").status is CheckStatus.FAIL  # type: ignore[union-attr]
    assert "notes.txt" in v.check("main_clean").evidence  # type: ignore[union-attr]
    base = capture_baseline(sc.repo)
    v = verify_phase(sc.repo, "05", baseline=base, run_test_commands=False)
    assert v.check("main_clean").status is CheckStatus.PASS  # type: ignore[union-attr]
    assert "1 pre-existing" in v.check("main_clean").evidence  # type: ignore[union-attr]


def test_main_checkout_off_main(sc: Scenario) -> None:
    sc.claim().work().complete()
    git(sc.repo, "checkout", "-q", "-b", "elsewhere")
    v = verify_phase(sc.repo, "05", run_test_commands=False)
    assert v.check("main_checkout").status is CheckStatus.FAIL  # type: ignore[union-attr]


def test_pushed_check_and_disagreement(sc: Scenario, tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(sc.repo, "remote", "add", "origin", str(remote))
    git(sc.repo, "push", "-q", "origin", "main")
    sc.claim().work().complete()
    v = verify_phase(sc.repo, "05", result("complete", pushed=True), run_test_commands=False)
    pushed = v.check("pushed")
    assert pushed is not None and pushed.status is CheckStatus.FAIL and not pushed.required
    assert v.outcome is Outcome.NEEDS_REVIEW
    git(sc.repo, "push", "-q", "origin", "main")
    v = verify_phase(sc.repo, "05", result("complete", pushed=True), run_test_commands=False)
    assert v.check("pushed").status is CheckStatus.PASS and v.outcome is Outcome.COMPLETE  # type: ignore[union-attr]


def test_pushed_without_tracking_ref(sc: Scenario, tmp_path: Path) -> None:
    git(sc.repo, "remote", "add", "origin", str(tmp_path / "nowhere.git"))
    sc.claim().work().complete()
    v = verify_phase(sc.repo, "05", run_test_commands=False)
    assert "no origin/main tracking ref" in v.check("pushed").evidence  # type: ignore[union-attr]


# --- blocked, in progress, not started, missing ---------------------------------------


def test_blocked_verified(sc: Scenario) -> None:
    sc.claim().block()
    v = verify_phase(sc.repo, "05", result("blocked"))
    assert v.outcome is Outcome.BLOCKED, v.report()
    assert v.question_ids == ("6",) and v.wip_blocked
    assert v.check("branch_kept").status is CheckStatus.PASS  # type: ignore[union-attr]
    assert v.summary() == "blocked on question #6"
    assert v.check("tests") is None  # tests run only for ✅


def test_blocked_without_question(sc: Scenario) -> None:
    sc.claim().block(question=False)
    v = verify_phase(sc.repo, "05", result("blocked"))
    assert v.outcome is Outcome.NEEDS_REVIEW  # the line names #6, which is not open
    v = verify_phase(sc.repo, "05")
    assert v.outcome is Outcome.FAILED
    assert {c.name for c in v.failures} == {"question_recorded"}


def test_blocked_log_needs_blocked_interval(sc: Scenario) -> None:
    sc.claim().block(log=BLOCKED_LOG.replace(" · blocked 2026-10-26 11:20 CDT to (open)", ""))
    v = verify_phase(sc.repo, "05")
    assert "no blocked interval" in v.check("phase_log").evidence  # type: ignore[union-attr]


def test_in_progress(sc: Scenario) -> None:
    sc.claim().work(commit=False)
    v = verify_phase(sc.repo, "05", Classification(ExitClass.CRASH, "no result event"))
    assert v.outcome is Outcome.IN_PROGRESS
    assert "1 uncommitted" in v.check("work_in_progress").evidence  # type: ignore[union-attr]


def test_in_progress_stale_claim(sc: Scenario) -> None:
    sc.write_plan(sc.repo, render("🔄 In progress"), "claim only")
    v = verify_phase(sc.repo, "05")
    wip = v.check("work_in_progress")
    assert wip is not None and wip.status is CheckStatus.FAIL and not wip.required
    assert v.outcome is Outcome.IN_PROGRESS


def test_said_complete_but_in_progress(sc: Scenario) -> None:
    sc.claim().work()
    v = verify_phase(sc.repo, "05", result("complete"))
    assert v.outcome is Outcome.NEEDS_REVIEW
    assert "agent said complete, repo shows in_progress" in v.disagreements
    assert "agent said: complete" in v.report() and "! agent said complete" in v.report()


def test_refused_unchanged_and_moved(sc: Scenario) -> None:
    base = capture_baseline(sc.repo)
    refused = result("refused")
    v = verify_phase(sc.repo, "05", refused, baseline=base)
    assert v.outcome is Outcome.NOT_STARTED and v.ok
    assert v.check("main_unchanged").status is CheckStatus.PASS  # type: ignore[union-attr]
    git(sc.repo, "commit", "-q", "--allow-empty", "-m", "sneaky")
    v = verify_phase(sc.repo, "05", refused, baseline=base)
    assert v.outcome is Outcome.NEEDS_REVIEW
    assert "agent said refused, but main moved since launch" in v.disagreements


def test_refused_while_in_progress(sc: Scenario) -> None:
    sc.claim()
    v = verify_phase(sc.repo, "05", result("refused"))
    assert "agent said refused, but the row is 🔄 In progress" in v.disagreements


def test_refused_complete_phase_runs_no_tests(sc: Scenario) -> None:
    sc.claim().work().complete()
    v = verify_phase(sc.repo, "05", result("refused"))
    assert v.check("tests") is None and v.outcome is Outcome.COMPLETE


def test_result_line_names_other_phase(sc: Scenario) -> None:
    sc.claim().work().complete()
    v = verify_phase(sc.repo, "05", result("complete", phase="07"), run_test_commands=False)
    assert "result line names phase 07, not 05" in v.disagreements


def test_missing_phase_and_plan(sc: Scenario, tmp_path: Path) -> None:
    v = verify_phase(sc.repo, "09")
    assert v.state is RepoState.MISSING and v.outcome is Outcome.FAILED
    assert "not in the table" in v.failures[0].evidence
    empty = tmp_path / "empty"
    empty.mkdir()
    git(empty, "init", "-q", "-b", "main")
    git(empty, "commit", "-q", "--allow-empty", "-m", "x")
    assert verify_phase(empty, "05").state is RepoState.MISSING


def test_no_test_command_is_skip(tmp_path: Path) -> None:
    sc = Scenario(tmp_path, test_command="")
    (sc.repo / "prompts/TST_shared-instructions.md").write_text("nothing here\n")
    git(sc.repo, "commit", "-q", "-am", "no tests")
    sc.claim().work().complete()
    v = verify_phase(sc.repo, "05")
    assert v.check("tests").status is CheckStatus.SKIP and v.outcome is Outcome.COMPLETE  # type: ignore[union-attr]


def test_config_test_command_and_timeout(tmp_path: Path) -> None:
    sc = Scenario(tmp_path)
    (sc.repo / ".phx").mkdir()
    (sc.repo / ".phx/config.toml").write_text('test_command = "sleep 5"\n')
    git(sc.repo, "add", "-A")
    git(sc.repo, "commit", "-q", "-m", "config")
    sc.claim().work().complete()
    v = verify_phase(sc.repo, "05", config=Config(test_timeout_s=1))
    tests = v.check("tests")
    assert tests is not None and tests.status is CheckStatus.FAIL
    assert "timed out after 1 s" in tests.evidence and "from config" in tests.evidence


def test_wip_blocked_detection(sc: Scenario) -> None:
    sc.claim().work()
    assert not wip_blocked(sc.repo, "05")
    sc.wip_blocked()
    assert wip_blocked(sc.repo, "05")
    assert not wip_blocked(sc.repo, "06")


def test_report_and_log_shape(sc: Scenario) -> None:
    sc.claim().work().complete(remove_worktree=False, delete_branch=False)
    v = verify_phase(sc.repo, "05", run_test_commands=False)
    text = v.report()
    assert text.startswith("Phase 05: verification failed")
    assert "✗ branch_deleted" in text and "✓ phase_log" in text and "(optional)" in text
    data = v.as_log()
    assert data["outcome"] == "failed" and any(
        c["name"] == "branch_deleted" for c in data["checks"]
    )
    json.dumps(data)


# --- Phase Log parsing ---------------------------------------------------------------


def test_phase_log_entries_on_real_plans() -> None:
    mm3 = (FIXTURES / "mm3" / "MM3_IMPLEMENTATION_PLAN.md").read_text()
    entries = phase_log_entries(mm3, "15m")
    assert entries and entries[-1].status == "✅ Complete" and entries[-1].has_timeline
    cl = (FIXTURES / "cl" / "CL_IMPLEMENTATION_PLAN.md").read_text()
    assert phase_log_entries(cl, "13")[-1].status == "✅ Complete"
    assert phase_log_entries(cl, "99") == []


def test_phase_log_heading_without_bullets() -> None:
    text = (
        "## Phase Log\n"
        "### 2026-10-26 10:00 CDT: Phase 05: X (✅ Complete)\n"
        "### 2026-10-26: Phase 06: Y\n"
    )
    (first,) = phase_log_entries(text, "05")
    assert first.first_bullet is None and not first.has_timeline
    assert phase_log_entries(text, "06")[0].status == ""


# --- set_status_cell (used by the ⛔ repair) -----------------------------------------


def test_set_status_cell_changes_only_that_cell() -> None:
    text = render("🔄 In progress")
    out = set_status_cell(text, "05", "⛔ Blocked")
    changed = [(a, b) for a, b in zip(text.splitlines(), out.splitlines(), strict=True) if a != b]
    assert len(changed) == 1
    assert changed[0][1].startswith("| 05 | Thing |") and "| ⛔ Blocked |" in changed[0][1]
    assert set_status_cell(text, "00", "x").count("| x |") == 1


def test_set_status_cell_missing_row() -> None:
    from phx.plan import PlanError

    with pytest.raises(PlanError):
        set_status_cell(render("⬜ Not started"), "42", "⛔ Blocked")
    with pytest.raises(PlanError):
        set_status_cell("no table\n", "05", "⛔ Blocked")


# --- test command interpreter (ADR-0015) ------------------------------------------------


def words(command: str) -> list[list[str]]:
    return [
        [w.text for w in s.argv] if s.cd is None else ["cd", s.cd] for s in parse_command(command)
    ]


def test_parse_simple_and_compound() -> None:
    assert words("uv run pytest") == [["uv", "run", "pytest"]]
    assert words("cd chessloop/backend && pytest -q") == [
        ["cd", "chessloop/backend"],
        ["pytest", "-q"],
    ]
    assert words("echo 'a b' \"c d\" e\\ f") == [["echo", "a b", "c d", "e f"]]
    steps = parse_command("FOO=1 BAR=x make check")
    assert steps[0].env == (("FOO", "1"), ("BAR", "x")) and words("FOO=1 make") == [["make"]]
    assert words('pytest -k "a*"')[0][2] == "a*"
    assert parse_command('pytest -k "a*"')[0].argv[2].pattern is None
    assert parse_command("shellcheck lab/**/*.sh")[0].argv[1].pattern == "lab/**/*.sh"
    assert parse_command("ls 'x*'*")[0].argv[1].pattern == "x[*]*"


@pytest.mark.parametrize(
    "command",
    [
        "a | b",
        "a; b",
        "a || b",
        "a > out",
        "a < in",
        "echo $HOME",
        'echo "$HOME"',
        "echo `id`",
        'echo "`id`"',
        "(a)",
        "a &",
        "ls ~/x",
        "ls {a,b}",
        "a && ",
        "&& a",
        "X=1",
        "cd",
        "cd a b",
        "cd a* ",
        "X=1 cd a",
        "echo 'open",
        'echo "open',
        "echo \\",
        "# comment",
    ],
)
def test_parse_refuses_shell_syntax(command: str) -> None:
    with pytest.raises(UnsupportedCommand):
        parse_command(command)


def test_comment_mid_command_is_refused() -> None:
    with pytest.raises(UnsupportedCommand):
        parse_command("go test ./... # note")


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    root = tmp_path / "checkout"
    (root / "lab" / "deep").mkdir(parents=True)
    (root / "lab" / "a.sh").write_text("x")
    (root / "lab" / "deep" / "b.sh").write_text("x")
    (root / "sub").mkdir()
    (root / "sub" / "marker").write_text("x")
    return root


ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}


def test_run_command_glob_and_cd(tree: Path) -> None:
    r = run_command("ls lab/**/*.sh", tree, ENV, timeout=10, missing_is_skip=False)
    assert r.status is CheckStatus.PASS, r
    r = run_command("cd sub && test -f marker", tree, ENV, timeout=10, missing_is_skip=False)
    assert r.status is CheckStatus.PASS
    r = run_command("cd sub && test -f nothing", tree, ENV, timeout=10, missing_is_skip=False)
    assert r.status is CheckStatus.FAIL and r.exit_code == 1
    r = run_command(
        'FOO=bar python3 -c \'import os,sys; sys.exit(os.environ["FOO"] != "bar")\'',
        tree,
        ENV,
        timeout=10,
        missing_is_skip=False,
    )
    assert r.status is CheckStatus.PASS


def test_run_command_missing_paths(tree: Path) -> None:
    for command in ("shellcheck nope/**/*.sh", "cd missing && make", "./scripts/ci.sh"):
        skip = run_command(command, tree, ENV, timeout=10, missing_is_skip=True)
        assert skip.status is CheckStatus.SKIP and "another repo" in skip.detail, command
        fail = run_command(command, tree, ENV, timeout=10, missing_is_skip=False)
        assert fail.status is CheckStatus.FAIL, command


def test_run_command_refusals(tree: Path) -> None:
    out = run_command("cd .. && ls", tree, ENV, timeout=10, missing_is_skip=True)
    assert out.status is CheckStatus.FAIL and "leaves the checkout" in out.detail
    (tree.parent / "sibling").write_text("x")
    out = run_command("ls ../*", tree, ENV, timeout=10, missing_is_skip=True)
    assert out.status is CheckStatus.FAIL and "outside the checkout" in out.detail
    out = run_command("a | b", tree, ENV, timeout=10, missing_is_skip=True)
    assert out.status is CheckStatus.FAIL and "config.toml" in out.detail
    out = run_command("definitely-not-a-command-phx", tree, ENV, timeout=10, missing_is_skip=True)
    assert out.status is CheckStatus.FAIL and "command not found" in out.detail


def test_run_command_output_is_redacted(tree: Path) -> None:
    key = "sk-or-v1-" + "e" * 40
    out = run_command(
        f"python3 -c 'print(\"{key}\"); raise SystemExit(3)'",
        tree,
        ENV,
        timeout=10,
        missing_is_skip=False,
    )
    assert out.exit_code == 3 and key not in out.output_tail and "[REDACTED]" in out.output_tail


def test_cl_style_plan_is_skipped(make_repo: RepoFactory) -> None:
    repo = make_repo("cl")
    plan = load_plan(repo)
    assert plan.test_commands == ("shellcheck lab/**/*.sh",)
    check = run_tests(plan, git(repo, "rev-parse", "main"), timeout=30)
    assert check.status is CheckStatus.SKIP
    assert "another repo (ADR-0013)" in check.evidence


def test_run_tests_env_strips_secrets(tmp_path: Path) -> None:
    sc = Scenario(
        tmp_path,
        test_command="python3 -c 'import os,sys; "
        'sys.exit("PHX_AUTO" in os.environ or "ANTHROPIC_AUTH_TOKEN" in os.environ)\'',
    )
    sc.claim().work().complete()
    env = {**ENV, "PHX_AUTO": "1", "ANTHROPIC_AUTH_TOKEN": "x", "HOME": str(tmp_path)}
    v = verify_phase(sc.repo, "05", env=env)
    assert v.check("tests").status is CheckStatus.PASS, v.report()  # type: ignore[union-attr]


def test_run_tests_clone_failure(make_repo: RepoFactory) -> None:
    repo = make_repo("sample")
    plan = load_plan(repo)
    check = run_tests(plan, "0" * 40, timeout=10)
    assert check.status is CheckStatus.FAIL and "could not clone" in check.evidence
