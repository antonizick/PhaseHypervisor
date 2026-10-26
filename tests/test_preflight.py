"""``phx preflight`` (Phase 08): fingerprints, freshness, leads, prompt assembly, launch
argv, the scripted interactive session and the record. No tokens: the session is the
fake ``claude``, started through the fake ``ai-provider``."""

import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

from conftest import RepoFactory, git
from phx.cli import main
from phx.locks import RunLock
from phx.logging import EventLog
from phx.plan import Gate, Phase, Status, load_plan
from phx.preflight import (
    KICKOFF,
    PREFLIGHT_ALIAS,
    PREFLIGHT_FILE,
    Fresh,
    PreflightRefused,
    assemble_prompt,
    base_prompt,
    build_record,
    check_can_start,
    check_freshness,
    freshness,
    gather_facts,
    launch,
    phase_fingerprint,
    prepare,
    record,
    relevant_questions,
    remaining,
    scan_leads,
    suggest_gate,
)
from phx.runner import find_launcher

TESTS = Path(__file__).resolve().parent
FAKES = TESTS / "fakes"
PLAN = "SMP_IMPLEMENTATION_PLAN.md"


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    return dict(
        os.environ,
        PATH=f"{FAKES}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        XDG_RUNTIME_DIR=str(tmp_path / "run"),
        ANTHROPIC_MODEL="sonnet",
        PHX_AUTO="1",
    )


@pytest.fixture
def sample(make_repo: RepoFactory) -> Path:
    return make_repo("sample", name="work/SMP")


def edit(repo: Path, old: str, new: str, path: str = PLAN) -> None:
    file = repo / path
    text = file.read_text()
    assert old in text, old
    file.write_text(text.replace(old, new))
    git(repo, "commit", "-q", "-am", "test: edit")


def record_json(repo: Path, **kw: Any) -> str:
    return json.dumps(
        build_record(
            load_plan(repo), ts="2026-10-26 17:00 CDT", session_id=None, unresolved=(), **kw
        )
    )


# --------------------------------------------------------------------------- fingerprints


def _phase(**kw: Any) -> Phase:
    base: dict[str, Any] = dict(
        id="01",
        name="Hello",
        model="Haiku 5.5",
        alias="haiku",
        depends_on=("00",),
        status=Status.NOT_STARTED,
        prompt="prompts/x.md",
        gate=Gate.AUTO,
        gate_source="column",
        line=10,
    )
    return Phase(**(base | kw))


def test_fingerprint_ignores_status_and_line() -> None:
    a = phase_fingerprint(_phase())
    assert a == phase_fingerprint(_phase(status=Status.COMPLETE, line=99))


@pytest.mark.parametrize(
    "change",
    [
        {"name": "Other"},
        {"model": "Opus 5.5"},
        {"depends_on": ("00", "02")},
        {"prompt": "prompts/y.md"},
        {"gate": Gate.REVIEW},
    ],
)
def test_fingerprint_follows_the_definition(change: dict[str, Any]) -> None:
    assert phase_fingerprint(_phase()) != phase_fingerprint(_phase(**change))


def test_fingerprint_ignores_inferred_and_default_gates() -> None:
    inferred = _phase(gate=Gate.REVIEW, gate_source="inferred")
    default = _phase(gate=Gate.AUTO, gate_source="default")
    assert phase_fingerprint(inferred) == phase_fingerprint(default)


# --------------------------------------------------------------------------- freshness


def test_freshness_missing_invalid_and_fresh(sample: Path) -> None:
    plan = load_plan(sample)
    missing = check_freshness(plan, None)
    assert missing.state is Fresh.MISSING and missing.rule == "preflight_missing"
    assert "not on main" in missing.describe()
    for bad in ("{", "[]", json.dumps({"version": 9}), json.dumps({"version": 1})):
        got = check_freshness(plan, bad)
        assert got.state is Fresh.INVALID and got.rule == "preflight_invalid", bad
    wrong_types = json.dumps({"version": 1, "phases": [], "questions": {}})
    assert check_freshness(plan, wrong_types).state is Fresh.INVALID
    fresh = check_freshness(plan, record_json(sample, base_commit=None))
    assert fresh.ok and fresh.recorded == "2026-10-26 17:00 CDT"
    assert fresh.describe() == "preflight 2026-10-26 17:00 CDT covers the plan"


def test_completing_phases_and_answering_keep_it_fresh(sample: Path) -> None:
    text = record_json(sample, base_commit=None)
    edit(
        sample,
        "| 01 | Hello file | Create `hello.txt` containing `hi` | Haiku 5.5 | 00 | ⬜ Not started",
        "| 01 | Hello file | Create `hello.txt` containing `hi` | Haiku 5.5 | 00 | ✅ Complete",
    )
    edit(sample, "Open. Proposed default: blue", "Answered 2026-10-26 17:05 CDT: green")
    assert check_freshness(load_plan(sample), text).ok


def test_stale_reasons(sample: Path) -> None:
    text = record_json(sample, base_commit=None)
    edit(sample, "| 02 | Colour file |", "| 02 | Colour file (renamed) |")
    row_02_end = "(prompts/SMP_phase-02-colour.md) | review |"
    edit(
        sample,
        row_02_end,
        row_02_end + "\n| 03 | Added later | x | Haiku 5.5 | 02 | ⬜ Not started | n/a | auto |",
    )
    edit(
        sample,
        "| 1 | Favourite colour? | Open. Proposed default: blue | Phase 02 |",
        "| 1 | Favourite colour? | Open. Proposed default: blue | Phase 02 |\n"
        "| 2 | Font? | Open. Proposed default: serif | Phase 03 |",
    )
    got = check_freshness(load_plan(sample), text)
    assert got.state is Fresh.STALE and got.rule == "preflight_stale"
    assert got.reasons == (
        "phase(s) added: 03",
        "phase row(s) changed: 02",
        "owner question(s) opened since: #2",
    )
    assert got.describe().startswith("preflight (2026-10-26 17:00 CDT) is stale: phase(s) added")


def test_stale_on_removed_phase_and_renamed_plan(sample: Path) -> None:
    data = json.loads(record_json(sample, base_commit=None))
    data["phases"]["09"] = "0" * 16
    data["plan_file"] = "IMPLEMENTATION_PLAN.md"
    got = check_freshness(load_plan(sample), json.dumps(data))
    assert got.reasons == (
        f"plan file was IMPLEMENTATION_PLAN.md, now {PLAN}",
        "phase(s) removed: 09",
    )


# --------------------------------------------------------------------------- leads


def test_leads_join_wrapped_lines_and_rank_publishing_first() -> None:
    prompt = (
        "# Phase 16: Release\n"
        "\n"
        "## Goal\n"
        "Ship it. Check the README by hand before tagging.\n"
        "Publishing images carries GPL obligations for the packages in\n"
        "them; decide with Nick how sources are offered.\n"
        "\n"
        "1. Set `OPENROUTER_API_KEY` in the environment.\n"
        "2. Plain step without anything.\n"
        "3. **Only after he explicitly confirms:** `gh repo create`.\n"
        "4. Check the README by hand before tagging.\n"
    )
    leads = scan_leads("16", prompt)
    assert [(lead.kinds, lead.line) for lead in leads] == [
        (("publishing", "ask"), 5),
        (("publishing", "ask"), 10),
        (("credential",), 8),
        (("manual",), 4),
    ]
    assert leads[0].text.startswith("Publishing images") and leads[0].text.endswith("offered.")
    assert leads[3].text == "Check the README by hand before tagging."  # deduplicated (line 11)
    assert all(lead.phase == "16" for lead in leads)


def test_long_sentence_is_clipped_around_the_match() -> None:
    sentence = "Filler words " * 40 + "and then ask Nick about it " + "more filler " * 40 + "."
    (lead,) = scan_leads("05", sentence)
    assert "ask Nick" in lead.text and len(lead.text) <= 240
    assert lead.text.startswith("…") and lead.text.endswith("…")


def test_no_leads_in_plain_prompt() -> None:
    assert scan_leads("01", "Create `hello.txt` containing `hi`.\n") == []


@pytest.mark.parametrize(
    ("gate", "source", "kinds", "expected"),
    [
        (Gate.OWNER, "column", ("publishing",), (Gate.OWNER, "already owner")),
        (Gate.AUTO, "column", ("publishing",), (Gate.REVIEW, "publishing")),
        (Gate.REVIEW, "inferred", (), (Gate.REVIEW, "publishing")),
        (Gate.REVIEW, "column", (), (Gate.REVIEW, "already review (column)")),
        (Gate.AUTO, "default", ("manual",), (Gate.REVIEW, "manual check?")),
        (Gate.AUTO, "default", ("spend",), (Gate.REVIEW, "spending?")),
        (Gate.AUTO, "default", ("credential",), (Gate.AUTO, "no lead")),
    ],
)
def test_suggest_gate(
    gate: Gate, source: str, kinds: tuple[str, ...], expected: tuple[Gate, str]
) -> None:
    from phx.preflight import Lead

    leads = [Lead("01", kinds, 1, "x")] if kinds else []
    assert suggest_gate(_phase(gate=gate, gate_source=source), leads) == expected


# --------------------------------------------------------------------------- questions


def test_relevant_questions_open_and_deferred(make_repo: RepoFactory) -> None:
    repo = make_repo("mm3", name="work/MM3")
    rows = relevant_questions(load_plan(repo))
    assert [r[0] for r in rows] == ["Q3", "Q5"]  # deferred to Phase 16; Q1, Q2, Q4, Q6 decided
    assert all(r[3] == "16" for r in rows)


def test_relevant_questions_skip_completed_phases(sample: Path) -> None:
    assert [r[0] for r in relevant_questions(load_plan(sample))] == ["1"]
    edit(sample, "Open. Proposed default: blue | Phase 02", "Deferred: later | Phase 00")
    assert relevant_questions(load_plan(sample)) == []


# --------------------------------------------------------------------------- prompt


def test_base_prompt_carries_the_rules() -> None:
    text = base_prompt()
    for needle in (
        "AskUserQuestion",
        "at most **4 questions per call**",
        "(Recommended)",
        "Option | Pros | Cons",
        "never pre-approved",
        "`review`",
        "`owner`",
        "docs(plan): phx preflight <TS>",
        "Never print, read, copy or `cat` their contents",
        "Only phases not yet `✅ Complete`",
    ):
        assert needle in text, needle


def test_mm3_acceptance_publication_caught(make_repo: RepoFactory) -> None:
    """Acceptance: the preflight for MM3's remaining phase 16 asks about publication and
    proposes Gate review (dry review of the generated prompt, no session)."""
    repo = make_repo("mm3", name="work/MM3")
    plan = load_plan(repo)
    assert [p.id for p in remaining(plan)] == ["16"]
    prompts = {"16": (repo / "prompts/MM3_phase-16-release.md").read_text()}
    text = assemble_prompt(
        plan,
        base=base_prompt(),
        prompts=prompts,
        fresh=freshness(plan),
        record_cmd="phx preflight --record",
        facts=["`gh auth status`: logged in"],
        ts="2026-10-26 17:00 CDT",
    )
    row = next(line for line in text.splitlines() if line.startswith("| 16 |"))
    assert "| review (column) | review (publishing) |" in row
    assert "| Q3 | GitHub owner, repo name, visibility | **Deferred:**" in text
    assert "| Q5 |" in text
    leads = text.split("#### Phase 16", 1)[1].split("###", 1)[0]
    confirm = next(line for line in leads.splitlines() if "explicitly confirms" in line)
    assert confirm.startswith("- [publishing, ask] line 39:") and "gh repo create" in confirm
    assert "decide with Nick how sources are offered" in leads  # GHCR GPL question
    assert "Firefox click-through" in leads  # a manual check: Gate, not a question
    assert "repo not yet migrated" not in text  # MM3 was migrated in Phase 09
    # the instructions turn those into a confirmed review Gate and no pre-approval
    assert "Use it for publishing, spending and manual-check phases" in text
    assert "never pre-approved here" in text


def test_assemble_sample_context(sample: Path) -> None:
    plan = load_plan(sample)
    text = assemble_prompt(
        plan,
        base="BASE",
        prompts={"01": None, "01a": "Append `there`.", "02": "Nick must choose a colour."},
        fresh=check_freshness(plan, record_json(sample, base_commit=None)),
        record_cmd="RECORD-CMD",
        ts="TS",
    )
    assert text.startswith("BASE\n\n## Context for this run")
    assert "- Hands-off contract: version 1" in text
    assert "- Specification: not found on main" in text
    assert "Previous preflight: preflight 2026-10-26 17:00 CDT covers the plan" in text
    assert "(not found on main)" in text  # 01's prompt was given as missing
    assert "| 02 | Colour file | Sonnet 5.5 | ⬜ Not started | 01a | review (column) |" in text
    assert "| 1 | Favourite colour? | Open. Proposed default: blue | 02 |" in text
    assert "- [ask] line 1: «Nick must choose a colour.»" in text
    assert "- nothing" in text and "```\nRECORD-CMD\n```" in text


def test_assemble_without_questions_or_leads(sample: Path) -> None:
    edit(sample, "Open. Proposed default: blue", "Decided 2026-10-26 08:00 CDT: green")
    plan = load_plan(sample)
    text = assemble_prompt(
        plan, base="B", prompts={}, fresh=freshness(plan), record_cmd="R", facts=["f"]
    )
    assert "\nNone.\n" in text and "None found." in text and "- f" in text


def test_lead_cap(sample: Path) -> None:
    plan = load_plan(sample)
    many = "\n\n".join(f"Ask Nick about item {i}." for i in range(25))
    text = assemble_prompt(
        plan, base="B", prompts={"02": many}, fresh=freshness(plan), record_cmd="R"
    )
    assert "- … 5 more; read the prompt" in text


def test_gather_facts(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("git", "gh"):
        exe = bin_dir / tool
        exe.write_text("#!/bin/sh\nexit 1\n")
        exe.chmod(0o755)
    facts = gather_facts({"PATH": str(bin_dir)})
    assert facts[0] == f"`git`: {bin_dir / 'git'}"
    assert "`uv`: not found on PATH" in facts
    assert facts[-1] == "`gh auth status`: NOT logged in"

    def boom(*_a: Any, **_k: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired("gh", 20)

    assert gather_facts({"PATH": str(bin_dir)}, run=boom)[-1] == (
        "`gh auth status`: could not run (TimeoutExpired)"
    )
    assert not any("gh auth" in f for f in gather_facts({"PATH": str(tmp_path)}))


# --------------------------------------------------------------------------- start checks


def test_refuses_in_progress_phase(sample: Path, env: dict[str, str]) -> None:
    edit(
        sample,
        "| 00 | ⬜ Not started | [SMP_phase-01-hello",
        "| 00 | 🔄 In progress | [SMP_phase-01-hello",
    )
    with pytest.raises(PreflightRefused, match=r"phase 01 is 🔄 In progress.*phx status"):
        check_can_start(sample, load_plan(sample), env)


def test_refuses_when_everything_is_complete(sample: Path, env: dict[str, str]) -> None:
    text = (sample / PLAN).read_text().replace("⬜ Not started", "✅ Complete")
    (sample / PLAN).write_text(text)
    git(sample, "commit", "-q", "-am", "done")
    with pytest.raises(PreflightRefused, match="nothing to preflight"):
        check_can_start(sample, load_plan(sample), env)


def test_refuses_off_main_and_with_a_supervisor(sample: Path, env: dict[str, str]) -> None:
    plan = load_plan(sample)
    git(sample, "checkout", "-q", "-b", "side")
    with pytest.raises(PreflightRefused, match="on side, not main"):
        check_can_start(sample, plan, env)
    git(sample, "checkout", "-q", "main")
    with (
        RunLock(sample, started="now", unit=None, env=env),
        pytest.raises(PreflightRefused, match="a supervisor is running"),
    ):
        check_can_start(sample, plan, env)
    check_can_start(sample, plan, env)  # lock released: fine


# --------------------------------------------------------------------------- launch


def test_prepare_builds_an_interactive_launch(
    sample: Path, env: dict[str, str], tmp_path: Path
) -> None:
    state = tmp_path / "state" / "SMP"
    prep = prepare(sample / "prompts", launcher=find_launcher(env), state=state, env=env, facts=[])
    assert prep.plan.repo == sample
    argv = prep.argv
    assert argv[:2] == [str(FAKES / "ai-provider"), "run"]
    assert "-p" not in argv and "--output-format" not in argv
    assert "--permission-mode" not in argv  # Nick is present: his own settings apply
    assert argv[argv.index("--model") + 1] == PREFLIGHT_ALIAS == "opus"
    assert argv[argv.index("--session-id") + 1] == prep.session_id
    assert argv[argv.index("--name") + 1] == "phx preflight SMP"
    assert argv[argv.index("--append-system-prompt-file") + 1] == str(prep.prompt_file)
    assert argv[-1] == KICKOFF
    assert "PHX_AUTO" not in prep.env and "ANTHROPIC_MODEL" not in prep.env  # interactive
    assert prep.prompt_file.parent == state / "preflight"
    assert stat.S_IMODE(prep.prompt_file.stat().st_mode) == 0o600
    text = prep.prompt_file.read_text()
    assert text.startswith(base_prompt().rstrip())
    assert f"--record --session-id {prep.session_id}" in text
    assert prep.freshness.state is Fresh.MISSING and prep.leads >= 1 and prep.notes == ()


def test_prepare_notes_unmigrated_repo(
    make_repo: RepoFactory, env: dict[str, str], tmp_path: Path
) -> None:
    repo = make_repo("mm3", name="work/MM3")
    cmd = repo / ".claude/commands/phase.md"
    cmd.write_text(cmd.read_text().replace("PHX-CONTRACT: 1\n", ""))  # an older, unmigrated repo
    git(repo, "commit", "-q", "-am", "unmigrate")
    prep = prepare(repo, launcher=find_launcher(env), state=tmp_path / "s", env=env, facts=[])
    assert any("not yet migrated" in n for n in prep.notes)


def test_scripted_session_sees_expected_questions_and_records(
    sample: Path, env: dict[str, str], tmp_path: Path
) -> None:
    """The fake session asserts the question list in its prompt, then records like the
    real agent would; afterwards the preflight is fresh."""
    expect = tmp_path / "expect.json"
    expect.write_text(
        json.dumps(
            [
                "| 1 | Favourite colour? | Open. Proposed default: blue | 02 |",
                "| 02 | Colour file |",
                "| 01a | Inserted phase |",
                "- [ask] line 5: «Before any task, you need Nick to choose a colour;",
            ]
        )
    )
    argv_log = tmp_path / "argv.jsonl"
    env |= {
        "PHX_FAKE_EXPECT": str(expect),
        "PHX_FAKE_PREFLIGHT_RECORD": "1",
        "PHX_FAKE_ARGV_LOG": str(argv_log),
    }
    state_root = tmp_path / "state"
    log = EventLog(state_root / "SMP" / "run.jsonl")
    prep = prepare(
        sample,
        launcher=find_launcher(env),
        state=state_root / "SMP",
        env=env,
        state_root=state_root,
        facts=[],
    )
    code, after = launch(prep, log=log)
    assert code == 0 and after.ok
    call = json.loads(argv_log.read_text().splitlines()[0])
    assert call["cwd"] == str(sample) and call["env"]["PHX_AUTO"] is None
    assert call["env"]["ANTHROPIC_MODEL"] is None
    data = json.loads(git(sample, "show", f"main:{PREFLIGHT_FILE}"))
    assert data["covered"] == ["01", "01a", "02"] and data["session_id"] == prep.session_id
    assert data["unresolved"] == ["phase 02: fake item"]
    assert git(sample, "log", "-1", "--format=%s").startswith("chore(phx): record preflight ")
    events = [json.loads(x) for x in (state_root / "SMP" / "run.jsonl").read_text().splitlines()]
    assert [e["event"] for e in events] == [
        "preflight_launch",
        "preflight_recorded",
        "preflight_end",
    ]
    assert events[-1]["freshness"] == "fresh" and events[-1]["exit_code"] == 0


def test_scripted_session_reports_missing_questions(
    sample: Path, env: dict[str, str], tmp_path: Path
) -> None:
    expect = tmp_path / "expect.json"
    expect.write_text(json.dumps(["| 7 | A question nobody asked |"]))
    env |= {"PHX_FAKE_EXPECT": str(expect)}
    log = EventLog(tmp_path / "run.jsonl")
    prep = prepare(sample, launcher=find_launcher(env), state=tmp_path, env=env, facts=[])
    code, after = launch(
        prep, log=log, run=lambda *a, **k: subprocess.run(*a, **k, stderr=subprocess.PIPE)
    )
    assert code == 3 and after.state is Fresh.MISSING
    end = [json.loads(x) for x in (tmp_path / "run.jsonl").read_text().splitlines()][-1]
    assert end["event"] == "preflight_end" and end["rule"] == "preflight_missing"


def test_launch_cannot_start(sample: Path, env: dict[str, str], tmp_path: Path) -> None:
    prep = prepare(sample, launcher=find_launcher(env), state=tmp_path, env=env, facts=[])

    def missing(*_a: Any, **_k: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("ai-provider")

    with pytest.raises(PreflightRefused, match="could not start"):
        launch(prep, log=EventLog(tmp_path / "run.jsonl"), run=missing)


# --------------------------------------------------------------------------- record


def test_record_commits_only_its_file_and_pushes(sample: Path, tmp_path: Path) -> None:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    git(sample, "remote", "add", "origin", str(origin))
    git(sample, "push", "-q", "origin", "main")
    (sample / "scratch.txt").write_text("unrelated, uncommitted")
    done = record(sample, session_id="s-1", unresolved=["  phase 02:   colour  ", " "])
    assert done.pushed == "pushed"
    assert git(sample, "show", "--name-only", "--format=", "HEAD").split() == [PREFLIGHT_FILE]
    assert done.record["unresolved"] == ["phase 02: colour"]
    assert done.record["questions"] == ["1"] and done.record["open_questions"] == ["1"]
    assert done.record["base_commit"] and done.record["session_id"] == "s-1"
    assert git(origin, "log", "-1", "--format=%h", "main").strip() == done.commit
    assert (sample / "scratch.txt").exists()  # untouched
    assert freshness(load_plan(sample)).ok


def test_record_refusals(
    sample: Path, env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    (sample / PLAN).write_text((sample / PLAN).read_text() + "\nedited\n")
    with pytest.raises(PreflightRefused, match="uncommitted changes; commit the preflight"):
        record(sample)
    git(sample, "checkout", "--", PLAN)
    git(sample, "checkout", "-q", "-b", "side")
    with pytest.raises(PreflightRefused, match="not main"):
        record(sample)
    git(sample, "checkout", "-q", "main")
    monkeypatch.setenv("XDG_RUNTIME_DIR", env["XDG_RUNTIME_DIR"])
    with (
        RunLock(sample, started="now", unit=None, env=env),
        pytest.raises(PreflightRefused, match="supervisor is running"),
    ):
        record(sample, env=env)


# --------------------------------------------------------------------------- CLI


def test_cli_check_dry_run_record(
    sample: Path,
    env: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for key in ("PATH", "XDG_RUNTIME_DIR"):
        monkeypatch.setenv(key, env[key])
    state = ["--state-dir", str(tmp_path / "state")]
    assert main([*state, "preflight", str(sample), "--check"]) == 3
    assert "no preflight recorded" in capsys.readouterr().out
    assert main([*state, "preflight", str(sample), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert (
        "phases 01, 01a, 02" in out and "command:  " in out and "--append-system-prompt-file" in out
    )
    # no terminal under pytest: the real launch refuses
    assert main([*state, "preflight", str(sample)]) == 1
    assert "needs an interactive terminal" in capsys.readouterr().err
    assert main([*state, "preflight", str(sample), "--record", "--unresolved", "x"]) == 0
    assert "covers 01, 01a, 02; 1 unresolved" in capsys.readouterr().out
    assert main([*state, "preflight", str(sample), "--check"]) == 0
    assert "covers the plan" in capsys.readouterr().out
    assert main([*state, "status", str(sample)]) == 0
    assert "Preflight:  preflight " in capsys.readouterr().out
    # refusals are reported and logged
    assert main([*state, "preflight", str(sample), "--record"]) == 0  # re-record is fine
    edit(
        sample,
        "| 01 | Hello file | Create `hello.txt` containing `hi` | Haiku 5.5 | 00 | ⬜ Not started",
        "| 01 | Hello file | Create `hello.txt` containing `hi` | Haiku 5.5 | 00 | 🔄 In progress",
    )
    capsys.readouterr()
    assert main([*state, "preflight", str(sample), "--dry-run"]) == 1
    assert "🔄 In progress" in capsys.readouterr().err
    git(sample, "checkout", "-q", "-b", "side")
    assert main([*state, "preflight", str(sample), "--record"]) == 1
    assert "not main" in capsys.readouterr().err
    log = (tmp_path / "state" / "SMP" / "run.jsonl").read_text()
    assert '"preflight_refused"' in log and '"preflight_recorded"' in log


def test_cli_check_unreadable_plan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], make_repo: RepoFactory
) -> None:
    repo = make_repo(files={"README.md": "no plan"}, name="empty")
    assert main(["preflight", str(repo), "--check"]) == 1
    assert "phx preflight:" in capsys.readouterr().err
