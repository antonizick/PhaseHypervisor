"""Pure parsing, ordering, model mapping and eligibility (no git)."""

from pathlib import Path

import pytest

from phx.plan import (
    ContractError,
    Gate,
    OwnerQuestion,
    Phase,
    Plan,
    PlanError,
    Status,
    UnknownModel,
    mentions_publishing,
    model_alias,
    next_eligible,
    parse_contract,
    parse_depends,
    parse_gate,
    parse_needed_by,
    parse_phase_id,
    parse_phase_table,
    parse_questions,
    parse_status,
    parse_test_commands,
    phase_sort_key,
    prompt_gate,
)

HEADER = (
    "| Phase | Phase Name | Phase Purpose | AI Model to Use | Depends on | Status "
    "| Prompt to Initiate This Phase |\n|---|---|---|---|---|---|---|\n"
)


def table(*rows: str, header: str = HEADER) -> str:
    return "# Plan\n\n## Phases\n\n" + header + "\n".join(rows) + "\n\nAfter.\n"


def row(
    pid: str, model: str = "Opus 5.5", deps: str = "none", status: str = "⬜ Not started"
) -> str:
    return (
        f"| {pid} | Name {pid} | Purpose | {model} | {deps} | {status} | [p](prompts/p-{pid}.md) |"
    )


def phase(pid: str, status: Status = Status.NOT_STARTED, deps: tuple[str, ...] = ()) -> Phase:
    return Phase(
        pid, f"Name {pid}", "Opus 5.5", "opus", deps, status, None, Gate.AUTO, "default", 1
    )


def plan_of(*phases: Phase, questions: tuple[OwnerQuestion, ...] = ()) -> Plan:
    return Plan(Path("/x"), "X_IMPLEMENTATION_PLAN.md", "X", phases, questions, (), None, 1)


# ---------------------------------------------------------------- IDs and ordering


@pytest.mark.parametrize("text", ["00", "15", "15a", " `07` ", "99z"])
def test_valid_ids(text: str) -> None:
    assert parse_phase_id(text) == text.strip().strip("`").strip()


@pytest.mark.parametrize("text", ["1", "001", "15A", "15ab", "a1", "", "Phase 01", "1a"])
def test_malformed_ids_are_rejected(text: str) -> None:
    with pytest.raises(PlanError, match="malformed phase ID"):
        parse_phase_id(text)


def test_ordering_numbers_then_letters() -> None:
    ids = ["16", "15b", "02", "15", "15a", "10", "09a"]
    assert sorted(ids, key=phase_sort_key) == ["02", "09a", "10", "15", "15a", "15b", "16"]


def test_sort_key_rejects_malformed() -> None:
    with pytest.raises(PlanError):
        phase_sort_key("5")


# ---------------------------------------------------------------- status


@pytest.mark.parametrize(
    ("cell", "status"),
    [
        ("⬜ Not started", Status.NOT_STARTED),
        ("🔄 In progress", Status.IN_PROGRESS),
        ("⛔ Blocked", Status.BLOCKED),
        ("✅ Complete    ", Status.COMPLETE),
    ],
)
def test_status_icon_and_word(cell: str, status: Status) -> None:
    assert parse_status(cell) == (status, [])


def test_status_word_only_is_flagged() -> None:
    status, problems = parse_status("Complete")
    assert status is Status.COMPLETE and "0 icons" in problems[0]


def test_status_icon_only_is_fine() -> None:
    assert parse_status("✅") == (Status.COMPLETE, [])


def test_status_two_icons_uses_word() -> None:
    status, problems = parse_status("⬜ 🔄 In progress")
    assert status is Status.IN_PROGRESS and "2 icons" in problems[0]


def test_status_two_icons_no_word_uses_first_icon() -> None:
    status, problems = parse_status("✅ ⛔")
    assert status is Status.COMPLETE and problems


def test_status_icon_and_word_disagree() -> None:
    status, problems = parse_status("✅ Not started")
    assert status is Status.COMPLETE and "disagree" in problems[0]


def test_status_unreadable() -> None:
    with pytest.raises(PlanError, match="unreadable status"):
        parse_status("done-ish")


# ---------------------------------------------------------------- models


@pytest.mark.parametrize(
    ("cell", "alias"),
    [
        ("Opus 5.5", "opus"),
        ("Sonnet 5.5", "sonnet"),
        ("Haiku 5.5", "haiku"),
        ("Fable 5.1", "fable"),
        ("Opus 5.5 (`claude-opus-5-5`)", "opus"),
        ("claude-sonnet-5-5", "sonnet"),
        ("`claude-haiku-5-5`", "haiku"),
        ("claude-fable-5-1", "fable"),
        ("Claude Opus 5.5", "opus"),
        ("  OPUS  ", "opus"),
    ],
)
def test_model_alias(cell: str, alias: str) -> None:
    assert model_alias(cell) == alias


@pytest.mark.parametrize("cell", ["GPT-5", "n/a", "", "opusx", "claude-gpt-1", "Mistral Opus"])
def test_unknown_model(cell: str) -> None:
    with pytest.raises(UnknownModel):
        model_alias(cell)


def test_require_alias() -> None:
    assert phase("01").require_alias() == "opus"
    odd = Phase("01", "n", "GPT", None, (), Status.NOT_STARTED, None, Gate.AUTO, "default", 1)
    with pytest.raises(UnknownModel, match="phase 01"):
        odd.require_alias()


# ---------------------------------------------------------------- gates


def test_parse_gate() -> None:
    assert parse_gate(" `review` ") is Gate.REVIEW
    assert parse_gate("Owner") is Gate.OWNER
    assert parse_gate("  ") is None
    with pytest.raises(PlanError, match="unknown gate"):
        parse_gate("manual")


def test_prompt_gate_header_only() -> None:
    assert prompt_gate("# T\n\n**Model:** Opus · **Gate:** owner\n") is Gate.OWNER
    assert prompt_gate("# T\n**Model:** Opus\n") is None
    late = "# T\n" + "x\n" * 20 + "**Gate:** owner\n"
    assert prompt_gate(late) is None


@pytest.mark.parametrize(
    "text",
    [
        "Then make the repo public.",
        "making a repo public requires Nick",
        "flip the GitHub repository visibility to public",
        "create a public GitHub repo",
        "MVP sign-off and GitHub publication",
        "publish a GitHub release",
        "publishing the release",
        "run gh release create v1",
        "is published to GitHub the way he chooses",
        "create a release with the binary",
    ],
)
def test_mentions_publishing(text: str) -> None:
    assert mentions_publishing(text)


@pytest.mark.parametrize(
    "text",
    [
        "Make the repository ready to publish on GitHub from day one.",
        "release notes are drafted",
        "a public API",
        "keep the repo private",
    ],
)
def test_does_not_mention_publishing(text: str) -> None:
    assert not mentions_publishing(text)


# ---------------------------------------------------------------- phase table


def test_table_by_header_names_and_extra_columns() -> None:
    header = (
        "| Status | Extra | Phase | AI Model to Use | Phase Name | Depends on | Gate |\n"
        "|---|---|---|---|---|---|---|\n"
    )
    text = table(
        "| ✅ Complete | x | 01 | Sonnet 5.5 | One | n/a | owner |",
        "| ⬜ Not started | y | 01a | Opus 5.5 | Two | 01 |  |",
        header=header,
    )
    rows, problems = parse_phase_table(text)
    assert problems == []
    (p1, g1), (p2, g2) = rows
    assert (p1.id, p1.name, p1.alias, p1.depends_on, p1.status, p1.prompt) == (
        "01",
        "One",
        "sonnet",
        (),
        Status.COMPLETE,
        None,
    )
    assert (g1, g2) == ("owner", "")
    assert p2.depends_on == ("01",)


def test_table_rows_deps_and_prompt_links() -> None:
    text = table(
        row("00", deps="none", status="✅ Complete"),
        "| 01 | One | P | Sonnet 5.5 | 00 | ⬜ Not started "
        "| [`prompts/X_phase-01.md`](prompts/X_phase-01.md)",
        "| 02 | Two | P | Sonnet 5.5 | 00, 01 | ⬜ Not started | prompts/X_phase-02.md |",
        "| 03 | Three | P | Sonnet 5.5 | — | ⬜ Not started | n/a (later) |",
    )
    rows, _ = parse_phase_table(text)
    phases = {p.id: p for p, _ in rows}
    assert phases["00"].prompt == "prompts/p-00.md"
    assert phases["01"].prompt == "prompts/X_phase-01.md"
    assert phases["02"].prompt == "prompts/X_phase-02.md"
    assert phases["02"].depends_on == ("00", "01")
    assert phases["03"].prompt is None and phases["03"].depends_on == ()


def test_depends_variants() -> None:
    assert parse_depends("none") == ()
    assert parse_depends(" N/A ") == ()
    assert parse_depends("15, 15a,15b") == ("15", "15a", "15b")
    with pytest.raises(PlanError):
        parse_depends("15, x")


def test_escaped_pipe_in_cell() -> None:
    text = table(r"| 01 | A \| B | P | Opus 5.5 | none | ⬜ Not started | x |")
    rows, _ = parse_phase_table(text)
    assert rows[0][0].name == "A | B"


def test_no_phase_table() -> None:
    with pytest.raises(PlanError, match="no phase table"):
        parse_phase_table("# Plan\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")


def test_missing_required_column() -> None:
    header = "| Phase | Phase Name | Status |\n|---|---|---|\n"
    with pytest.raises(PlanError, match="lacks columns: model, deps"):
        parse_phase_table(table("| 01 | n | ✅ Complete |", header=header))


def test_empty_phase_table() -> None:
    with pytest.raises(PlanError, match="no rows"):
        parse_phase_table(table())


def test_short_row_is_malformed() -> None:
    with pytest.raises(PlanError, match=r"line \d+: phase row has 3 cells"):
        parse_phase_table(table("| 01 | n | P |"))


def test_malformed_id_names_the_line() -> None:
    with pytest.raises(PlanError, match=r"line 7: malformed phase ID '1'"):
        parse_phase_table(table(row("1")))


def test_duplicate_id() -> None:
    with pytest.raises(PlanError, match="duplicate phase ID 01"):
        parse_phase_table(table(row("01"), row("01")))


def test_unknown_model_is_a_problem_unless_complete() -> None:
    rows, problems = parse_phase_table(
        table(row("00", model="n/a", status="✅ Complete"), row("01", model="GPT-9"))
    )
    assert [p.alias for p, _ in rows] == [None, None]
    assert problems == ["phase 01: unknown model 'GPT-9' (expected Opus, Sonnet, Haiku, Fable)"]


def test_unknown_dependency_and_status_problems() -> None:
    _, problems = parse_phase_table(table(row("01", deps="00", status="Complete")))
    assert any("0 icons" in p for p in problems)
    assert "phase 01: depends on 00, which is not in the table" in problems


# ---------------------------------------------------------------- owner questions

QUESTIONS = """
## Owner questions
| # | Question | Status / proposed default | Needed by |
|---|---|---|---|
| 1 | Licence | Decided 2026-10-26 08:41 CDT: MIT | Phase 01 |
| 5 | Optional? | **Open** | Phase 03, Phase 09 |
| 4 | Authority | open (asked 2026-10-26 09:00 CDT, Phase 05, auto mode). Proposed default: x | 05 |
| 6 | Keys | Answered 2026-10-26: yes | Phase 15a (Task 6), Phase 15b, Phase 16 |
| 7 | Short | **Open. Proposed:** y | — |
| 8 | Deferred | Deferred to Phase 16: later | Phase 16 |

## Phase Log
| # | Question | Status | Needed by |
|---|---|---|---|
| 99 | not a question | Open | 01 |
"""


def test_questions_parsed() -> None:
    qs = {q.id: q for q in parse_questions(QUESTIONS)}
    assert list(qs) == ["1", "5", "4", "6", "7", "8"]
    assert [i for i, q in qs.items() if q.open] == ["5", "4", "7"]
    assert qs["5"].needed_by == ("03", "09")
    assert qs["4"].needed_by == ("05",)
    assert qs["6"].needed_by == ("15a", "15b", "16")
    assert qs["7"].needed_by == ()


def test_legacy_open_questions_heading_without_status_column() -> None:
    text = (
        "## Open questions (owner input needed)\n"
        "| # | Question | Proposed default | Needed by |\n|---|---|---|---|\n"
        "| Q1 | Retention | **Decided 2026-10-11:** 90 days | Phase 04 |\n"
        "| Q3 | Owner | **Open** | Phase 16 |\n"
    )
    qs = parse_questions(text)
    assert [(q.id, q.open) for q in qs] == [("Q1", False), ("Q3", True)]


def test_no_questions_table() -> None:
    assert parse_questions("# Plan\n\n## Phases\n") == ()
    assert parse_questions("## Questions\n\n| a | b |\n|---|---|\n| 1 | 2 |\n") == ()


def test_question_row_too_short_is_skipped() -> None:
    text = "## Owner questions\n| # | Question |\n|---|---|\n| 1 |\n| 2 | ok |\n"
    qs = parse_questions(text)
    assert [(q.id, q.status, q.needed_by) for q in qs] == [("2", "", ())]


def test_needed_by_ignores_trailing_text_and_dates() -> None:
    assert parse_needed_by("Phase 05 (since 2026-10-26)") == ("05",)
    assert parse_needed_by("01, 13") == ("01", "13")
    assert parse_needed_by("Phase 04 and Phase 06") == ("04", "06")
    assert parse_needed_by("all phases") == ()


# ---------------------------------------------------------------- contract and tests


def test_contract_marker() -> None:
    assert parse_contract("x\nPHX-CONTRACT: 1\n") == 1
    assert parse_contract("x PHX-CONTRACT: 1\n") is None
    assert parse_contract(None) is None


def test_check_contract() -> None:
    assert plan_of(phase("01")).check_contract() == 1
    legacy = Plan(Path("/x"), "IMPLEMENTATION_PLAN.md", None, (), (), (), None, None)
    assert legacy.legacy
    with pytest.raises(ContractError, match="not yet migrated"):
        legacy.check_contract()
    future = Plan(Path("/x"), "f", "X", (), (), (), None, 2)
    with pytest.raises(ContractError, match="unknown PHX-CONTRACT version 2"):
        future.check_contract()


@pytest.mark.parametrize(
    ("line", "commands"),
    [
        (
            "- [ ] Tests, lint and type checks pass: `uv run pytest`, `uv run ruff check .`, "
            "`uv run mypy src` (from Phase 02 on).",
            ("uv run pytest", "uv run ruff check .", "uv run mypy src"),
        ),
        (
            "- [ ] Tests, lint and type checks pass: `make check` (= `gofmt -l` empty, "
            "`go vet ./...`); plus `go test -tags integration ./...` where it applies.",
            ("make check",),
        ),
        (
            "- [ ] Tests, lint and type checks pass: `make check` (and `make e2e` from Phase 07).",
            ("make check",),
        ),
        (
            "- [ ] Tests, lint and type checks pass (product repo `scripts/ci-local.sh`): planning "
            "`shellcheck lab/**/*.sh` (from Phase 03); product `pytest -q`.",
            ("shellcheck lab/**/*.sh",),
        ),
        ("- [ ] Tests, lint and type checks pass.", ()),
        ("Tests, lint and type checks pass: `a` and `b`", ("a", "b")),
    ],
)
def test_test_commands(line: str, commands: tuple[str, ...]) -> None:
    assert parse_test_commands(f"# S\n{line}\n") == commands


def test_test_commands_absent() -> None:
    assert parse_test_commands(None) == ()
    assert parse_test_commands("# nothing here\n") == ()


# ---------------------------------------------------------------- eligibility


def q(qid: str, status: str, *needed: str) -> OwnerQuestion:
    return OwnerQuestion(qid, "?", status, needed)


def test_next_is_lowest_eligible_with_reasons() -> None:
    plan = plan_of(
        phase("00", Status.COMPLETE),
        phase("01", Status.COMPLETE, ("00",)),
        phase("02", Status.NOT_STARTED, ("01",)),
        phase("02a", Status.NOT_STARTED, ("01",)),
        phase("03", Status.NOT_STARTED, ("02",)),
    )
    e = next_eligible(plan)
    assert e.next is not None and e.next.id == "02"
    assert e.resume == ()
    assert e.reasons == {
        "00": "complete",
        "01": "complete",
        "02a": "eligible, after 02",
        "03": "dependencies not complete: 02 (⬜ Not started)",
    }


def test_resume_candidates_and_blocked() -> None:
    plan = plan_of(
        phase("01", Status.IN_PROGRESS),
        phase("02", Status.BLOCKED),
        phase("03", Status.NOT_STARTED, ("01", "02", "99")),
    )
    e = next_eligible(plan)
    assert e.next is None
    assert [p.id for p in e.resume] == ["01"]
    assert e.reasons["01"] == "in progress (resume candidate)"
    assert e.reasons["02"] == "blocked"
    assert e.reasons["03"] == (
        "dependencies not complete: 01 (🔄 In progress), 02 (⛔ Blocked), 99 (missing)"
    )


def test_open_question_blocks_only_its_phase() -> None:
    plan = plan_of(
        phase("01", Status.NOT_STARTED),
        phase("02", Status.NOT_STARTED),
        questions=(q("3", "Open", "01"), q("4", "Decided: x", "02"), q("5", "**Open**", "01")),
    )
    e = next_eligible(plan)
    assert e.next is not None and e.next.id == "02"
    assert e.reasons["01"] == "open owner question: #3, #5"
    assert plan.open_questions_for("02") == ()


def test_nothing_left() -> None:
    e = next_eligible(plan_of(phase("01", Status.COMPLETE)))
    assert e.next is None and e.resume == () and e.reasons == {"01": "complete"}


def test_plan_phase_lookup() -> None:
    plan = plan_of(phase("01"))
    assert plan.phase("01").id == "01"
    with pytest.raises(KeyError):
        plan.phase("02")
