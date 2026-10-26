"""Plan parser and eligibility engine (spec R2, R6, R12, R14; contract §3, §7, §10).

Turns a phased-project repo into a typed model read from ``main`` (never the working
tree), answers "what runs next?" and reports drift between the plan and live
branches/worktrees. Nothing here changes a repo.
"""

import re
import subprocess
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from phx.paths import parse_config

MAIN = "main"
KNOWN_CONTRACTS = frozenset({1})


class PlanError(ValueError):
    """The plan cannot be read or is malformed."""


class UnknownModel(PlanError):
    """An "AI Model to Use" cell maps to no model alias (spec R2)."""


class ContractError(PlanError):
    """The repo's ``/phase`` command lacks a known ``PHX-CONTRACT`` marker (contract §10)."""


# --------------------------------------------------------------------------- phase IDs

_ID = re.compile(r"(\d{2})([a-z]?)")


def parse_phase_id(text: str) -> str:
    """Validate a phase ID (``NN`` or ``NNa``); surrounding spaces and backticks are ignored."""
    cleaned = text.strip().strip("`").strip()
    if not _ID.fullmatch(cleaned):
        raise PlanError(f"malformed phase ID {text.strip()!r} (expected NN or NNa, e.g. 07, 15a)")
    return cleaned


def phase_sort_key(phase_id: str) -> tuple[int, str]:
    """``15`` < ``15a`` < ``15b`` < ``16``."""
    m = _ID.fullmatch(phase_id)
    if not m:
        raise PlanError(f"malformed phase ID {phase_id!r}")
    return int(m.group(1)), m.group(2)


# --------------------------------------------------------------------------- status


class Status(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETE = "complete"


STATUS_ICONS: dict[str, Status] = {
    "⬜": Status.NOT_STARTED,
    "🔄": Status.IN_PROGRESS,
    "⛔": Status.BLOCKED,
    "✅": Status.COMPLETE,
}
STATUS_LABELS: dict[Status, str] = {
    Status.NOT_STARTED: "⬜ Not started",
    Status.IN_PROGRESS: "🔄 In progress",
    Status.BLOCKED: "⛔ Blocked",
    Status.COMPLETE: "✅ Complete",
}
_STATUS_WORDS = re.compile(r"\b(not started|in progress|blocked|complete)\b", re.IGNORECASE)


def parse_status(cell: str) -> tuple[Status, list[str]]:
    """Status from the icon or the word, plus any inconsistencies found.

    Exactly one icon wins; otherwise the word decides. Zero or several icons, or an icon
    that disagrees with the word, are reported as problems.
    """
    icons = [STATUS_ICONS[ch] for ch in cell if ch in STATUS_ICONS]
    words = [Status(w.lower().replace(" ", "_")) for w in _STATUS_WORDS.findall(cell)]
    word = words[0] if words else None
    problems: list[str] = []
    if len(icons) != 1:
        problems.append(f"status {cell.strip()!r} has {len(icons)} icons (expected 1)")
    if len(icons) == 1:
        status = icons[0]
        if word is not None and word != status:
            problems.append(f"status {cell.strip()!r}: icon and word disagree")
        return status, problems
    if word is not None:
        return word, problems
    if icons:
        return icons[0], problems
    raise PlanError(f"unreadable status {cell.strip()!r}")


# --------------------------------------------------------------------------- models

_FAMILIES = ("opus", "sonnet", "haiku", "fable")
_MODEL_NAME = re.compile(r"(?:claude[\s-]+)?(" + "|".join(_FAMILIES) + r")\b")


def model_alias(cell: str) -> str:
    """Map an "AI Model to Use" cell to its alias (spec R2).

    ``Opus 5.5`` → ``opus``; ``claude-sonnet-5-5`` → ``sonnet``. Anything else raises
    ``UnknownModel``.
    """
    m = _MODEL_NAME.match(cell.strip().strip("`").strip().lower())
    if not m:
        raise UnknownModel(f"unknown model {cell.strip()!r} (expected Opus, Sonnet, Haiku, Fable)")
    return m.group(1)


# --------------------------------------------------------------------------- gates


class Gate(StrEnum):
    AUTO = "auto"
    REVIEW = "review"
    OWNER = "owner"


_PROMPT_GATE = re.compile(r"\*\*Gate:\*\*\s*`?\s*([A-Za-z]+)")
_PUBLISHING = re.compile(
    r"\b(?:make|makes|making|made|turn|turning|flip|flipping)\s+(?:the\s+|this\s+|a\s+|its\s+)?"
    r"(?:github\s+)?(?:repo|repository)\b[^.\n]{0,30}?\bpublic\b"
    r"|\bpublic\s+(?:github\s+)?(?:repo|repository)\b"
    r"|\bgithub\s+(?:release|publication)\b"
    r"|\bpublish(?:es|ed|ing)?\s+(?:a\s+|the\s+)?(?:github\s+)?release\b"
    r"|(?<!ready to )\bpublish(?:es|ed|ing)?\s+(?:it\s+|this\s+|the\s+repo\s+)?(?:to|on)\s+github\b"
    r"|\bcreat(?:e|es|ed|ing)\s+(?:a\s+|the\s+)?(?:github\s+)?release\b"
    r"|\bgh\s+release\s+create\b",
    re.IGNORECASE,
)


def parse_gate(cell: str) -> Gate | None:
    """A Gate value (``auto``/``review``/``owner``); empty means not set."""
    value = cell.strip().strip("`").strip().lower()
    if not value:
        return None
    try:
        return Gate(value)
    except ValueError:
        raise PlanError(f"unknown gate {cell.strip()!r} (expected auto, review, owner)") from None


def mentions_publishing(text: str) -> bool:
    """True if a prompt mentions making a repo public or publishing a release (spec R12)."""
    return _PUBLISHING.search(text) is not None


def prompt_gate(prompt: str) -> Gate | None:
    """``· **Gate:** <value>`` in the prompt header (its first 15 lines)."""
    m = _PROMPT_GATE.search("\n".join(prompt.splitlines()[:15]))
    return parse_gate(m.group(1)) if m else None


# --------------------------------------------------------------------------- tables


def _cells(line: str) -> list[str]:
    """Split a Markdown table row on unescaped pipes."""
    body = line.strip()
    body = body.removeprefix("|")
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [c.replace("\\|", "|").strip() for c in re.split(r"(?<!\\)\|", body)]


def _is_separator(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{1,}:?", c) for c in cells if c) and any(cells)


def _norm(header: str) -> str:
    return " ".join(header.lower().split())


@dataclass(frozen=True)
class _Table:
    header: list[str]
    rows: list[tuple[int, list[str]]]  # (1-based line number, cells)


def _tables(lines: list[str], start: int = 0, stop: int | None = None) -> list[_Table]:
    tables: list[_Table] = []
    i, end = start, len(lines) if stop is None else stop
    while i < end - 1:
        if lines[i].lstrip().startswith("|") and _is_separator(_cells(lines[i + 1])):
            header = [_norm(c) for c in _cells(lines[i])]
            rows: list[tuple[int, list[str]]] = []
            i += 2
            while i < end and lines[i].lstrip().startswith("|"):
                rows.append((i + 1, _cells(lines[i])))
                i += 1
            tables.append(_Table(header, rows))
        else:
            i += 1
    return tables


def _column(header: list[str], *names: str, prefix: bool = False) -> int | None:
    for idx, h in enumerate(header):
        for name in names:
            if h == name or (prefix and h.startswith(name)):
                return idx
    return None


# --------------------------------------------------------------------------- model


@dataclass(frozen=True)
class Phase:
    id: str
    name: str
    model: str
    alias: str | None
    depends_on: tuple[str, ...]
    status: Status
    prompt: str | None
    gate: Gate
    gate_source: str  # "column" | "prompt" | "inferred" | "default"
    line: int

    def require_alias(self) -> str:
        """The model alias, or ``UnknownModel`` before a launch (spec R2)."""
        if self.alias is None:
            raise UnknownModel(f"phase {self.id}: unknown model {self.model!r}")
        return self.alias


@dataclass(frozen=True)
class OwnerQuestion:
    id: str
    question: str
    status: str
    needed_by: tuple[str, ...]

    @property
    def open(self) -> bool:
        """Open iff the Status cell starts with ``Open``, any case (contract §3)."""
        return _strip_markup(self.status).lower().startswith("open")


@dataclass(frozen=True)
class Plan:
    repo: Path
    plan_file: str
    prefix: str | None
    phases: tuple[Phase, ...]
    questions: tuple[OwnerQuestion, ...]
    test_commands: tuple[str, ...]
    test_source: str | None  # "config" | "shared-instructions" | None
    contract: int | None
    problems: tuple[str, ...] = ()

    @property
    def legacy(self) -> bool:
        return self.prefix is None

    def phase(self, phase_id: str) -> Phase:
        for p in self.phases:
            if p.id == phase_id:
                return p
        raise KeyError(phase_id)

    def open_questions_for(self, phase_id: str) -> tuple[OwnerQuestion, ...]:
        return tuple(q for q in self.questions if q.open and phase_id in q.needed_by)

    def check_contract(self) -> int:
        """The contract version, or ``ContractError`` ("repo not yet migrated")."""
        if self.contract is None:
            raise ContractError(
                "repo not yet migrated: no PHX-CONTRACT marker in .claude/commands/phase.md"
            )
        if self.contract not in KNOWN_CONTRACTS:
            raise ContractError(f"unknown PHX-CONTRACT version {self.contract}")
        return self.contract


def _strip_markup(text: str) -> str:
    return text.strip().lstrip("*_` ").strip()


# --------------------------------------------------------------------------- git access


def _git(repo: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:  # pragma: no cover - git is always on the host
        raise PlanError("git not found") from exc
    if proc.returncode != 0:
        raise PlanError(f"git {' '.join(args)} failed in {repo}: {proc.stderr.strip()}")
    return proc.stdout


def show_main(repo: Path, path: str) -> str | None:
    """Contents of ``path`` on ``main``, or ``None`` if it is not there."""
    proc = subprocess.run(
        ["git", "-C", str(repo), "show", f"{MAIN}:{path}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout if proc.returncode == 0 else None


_PLAN_NAME = re.compile(r"([A-Z][A-Z0-9]*)_IMPLEMENTATION_PLAN\.md")
_CLAUDE_PREFIX = re.compile(r"Project prefix:\s*`([A-Z][A-Z0-9]*)`")


def locate_plan(repo: Path) -> tuple[str, str | None]:
    """``(<file name>, <prefix or None>)`` of the plan on ``main`` (task 1)."""
    if not (repo / ".git").exists():
        raise PlanError(f"{repo} is not a git checkout")
    _git(repo, "rev-parse", "--verify", "--quiet", f"{MAIN}^{{commit}}")
    names = _git(repo, "ls-tree", "--name-only", MAIN).splitlines()
    prefixed = sorted(n for n in names if _PLAN_NAME.fullmatch(n))
    if len(prefixed) > 1:
        claude = show_main(repo, "CLAUDE.md") or ""
        m = _CLAUDE_PREFIX.search(claude)
        chosen = [n for n in prefixed if m and n == f"{m.group(1)}_IMPLEMENTATION_PLAN.md"]
        if len(chosen) != 1:
            raise PlanError(
                f"several plans on main and no matching prefix in CLAUDE.md: {prefixed}"
            )
        prefixed = chosen
    if prefixed:
        m2 = _PLAN_NAME.fullmatch(prefixed[0])
        assert m2 is not None
        return prefixed[0], m2.group(1)
    if "IMPLEMENTATION_PLAN.md" in names:
        return "IMPLEMENTATION_PLAN.md", None
    raise PlanError(
        f"no <PREFIX>_IMPLEMENTATION_PLAN.md or IMPLEMENTATION_PLAN.md on main in {repo}"
    )


# --------------------------------------------------------------------------- parsing

_NONE_DEPS = {"", "none", "n/a", "na", "-", "\u2014", "\u2013"}
_LINK = re.compile(r"\]\(([^)\s]+)\)")
_CONTRACT = re.compile(r"^PHX-CONTRACT: (\d+)\b", re.MULTILINE)
_NEEDED_BY = re.compile(r"^\s*(?:phase\s+)?`?(\d{2}[a-z]?)`?(?![\w.])", re.IGNORECASE)


def parse_depends(cell: str) -> tuple[str, ...]:
    if cell.strip().strip("`").lower() in _NONE_DEPS:
        return ()
    return tuple(parse_phase_id(part) for part in cell.split(",") if part.strip())


def parse_needed_by(cell: str) -> tuple[str, ...]:
    """Phase IDs in a "Needed by" cell: ``Phase 05, Phase 09``, ``01, 13``, ``Phase 15a (Task 6)``.

    Text after each ID is ignored (contract §3).
    """
    ids: list[str] = []
    for part in re.split(r",|;|\band\b|&", cell):
        m = _NEEDED_BY.match(part)
        if m:
            ids.append(m.group(1))
    return tuple(ids)


def _prompt_path(cell: str) -> str | None:
    m = _LINK.search(cell)
    if m:
        return m.group(1).strip("`")
    bare = cell.strip().strip("`")
    return bare if bare.endswith(".md") and " " not in bare else None


def parse_phase_table(text: str) -> tuple[list[tuple[Phase, str]], list[str]]:
    """Phases (with their raw Gate cell resolved later) from the plan text.

    Returns ``([(phase_without_prompt_gate, raw_gate_cell)], problems)``. Columns are found by
    header name (task 2); extra columns are ignored.
    """
    lines = text.splitlines()
    for table in _tables(lines):
        h = table.header
        if "phase" in h and "status" in h:
            break
    else:
        raise PlanError("no phase table (a table with 'Phase' and 'Status' columns)")
    cols = {
        "id": _column(h, "phase"),
        "name": _column(h, "phase name"),
        "model": _column(h, "ai model to use", "model", prefix=True),
        "deps": _column(h, "depends on"),
        "status": _column(h, "status"),
    }
    missing = [k for k, v in cols.items() if v is None]
    if missing:
        raise PlanError(f"phase table lacks columns: {', '.join(missing)}")
    prompt_col = _column(h, "prompt", prefix=True)
    gate_col = _column(h, "gate")
    needed = max(v for v in cols.values() if v is not None) + 1
    out: list[tuple[Phase, str]] = []
    problems: list[str] = []
    seen: set[str] = set()
    for lineno, row in table.rows:
        if len(row) < needed:
            raise PlanError(f"line {lineno}: phase row has {len(row)} cells, expected {len(h)}")

        def cell(key: str, row: list[str] = row) -> str:
            idx = cols[key]
            assert idx is not None
            return row[idx]

        try:
            pid = parse_phase_id(cell("id"))
            deps = parse_depends(cell("deps"))
            status, status_problems = parse_status(cell("status"))
        except PlanError as exc:
            raise PlanError(f"line {lineno}: {exc}") from None
        if pid in seen:
            raise PlanError(f"line {lineno}: duplicate phase ID {pid}")
        seen.add(pid)
        problems += [f"phase {pid}: {p}" for p in status_problems]
        try:
            alias: str | None = model_alias(cell("model"))
        except UnknownModel as exc:
            alias = None
            if status is not Status.COMPLETE:
                problems.append(f"phase {pid}: {exc}")
        prompt = (
            _prompt_path(row[prompt_col])
            if prompt_col is not None and prompt_col < len(row)
            else None
        )
        gate_cell = row[gate_col] if gate_col is not None and gate_col < len(row) else ""
        out.append(
            (
                Phase(
                    id=pid,
                    name=cell("name"),
                    model=cell("model"),
                    alias=alias,
                    depends_on=deps,
                    status=status,
                    prompt=prompt,
                    gate=Gate.AUTO,
                    gate_source="default",
                    line=lineno,
                ),
                gate_cell,
            )
        )
    if not out:
        raise PlanError("phase table has no rows")
    known = {p.id for p, _ in out}
    for p, _ in out:
        problems += [
            f"phase {p.id}: depends on {d}, which is not in the table"
            for d in p.depends_on
            if d not in known
        ]
    return out, problems


def set_status_cell(text: str, phase_id: str, label: str) -> str:
    """``text`` with phase ``phase_id``'s Status cell replaced by ``label``; nothing else changes.

    Used only by the ``⛔`` repair (Phase 06). Raises ``PlanError`` if the row is missing.
    """
    lines = text.splitlines(keepends=True)
    bare = [ln.rstrip("\r\n") for ln in lines]
    for table in _tables(bare):
        if "phase" in table.header and "status" in table.header:
            id_col, st_col = _column(table.header, "phase"), _column(table.header, "status")
            assert id_col is not None and st_col is not None
            for lineno, row in table.rows:
                if len(row) > max(id_col, st_col) and row[id_col].strip("` ") == phase_id:
                    raw = bare[lineno - 1]
                    lines[lineno - 1] = (
                        _replace_cell(raw, st_col, label) + lines[lineno - 1][len(raw) :]
                    )
                    return "".join(lines)
            break
    raise PlanError(f"phase {phase_id} not in the phase table")


def _replace_cell(line: str, col: int, value: str) -> str:
    """``line`` (a table row, no newline) with cell ``col`` set to ``value``."""
    parts = re.split(r"(?<!\\)\|", line)
    offset = 1 if line.lstrip().startswith("|") else 0
    parts[col + offset] = f" {value} "
    return "|".join(parts)


def set_question_status(text: str, question_id: str, label: str) -> str:
    """``text`` with owner question ``question_id``'s Status cell set to ``label``.

    Used by ``phx answer`` (contract §3). ``|`` in ``label`` is escaped; nothing else
    changes. Raises ``PlanError`` if the table or the row is missing.
    """
    lines = text.splitlines(keepends=True)
    bare = [ln.rstrip("\r\n") for ln in lines]
    value = label.replace("|", "\\|")
    for i, line in enumerate(bare):
        if not re.match(r"^##\s+.*\bquestions\b", line, re.IGNORECASE):
            continue
        stop = next((j for j in range(i + 1, len(bare)) if bare[j].startswith("## ")), None)
        for table in _tables(bare, i + 1, stop):
            h = table.header
            id_col = _column(h, "#", "id")
            st_col = _column(h, "status", prefix=True)
            if st_col is None:
                st_col = next((k for k, c in enumerate(h) if "default" in c), None)
            if id_col is None or st_col is None or _column(h, "question") is None:
                continue
            for lineno, row in table.rows:
                if len(row) > max(id_col, st_col) and row[id_col].strip("`* ") == question_id:
                    raw = bare[lineno - 1]
                    lines[lineno - 1] = (
                        _replace_cell(raw, st_col, value) + lines[lineno - 1][len(raw) :]
                    )
                    return "".join(lines)
            raise PlanError(f"owner question {question_id} not in the questions table")
    raise PlanError("the plan has no owner questions table")


def parse_questions(text: str) -> tuple[OwnerQuestion, ...]:
    """The Owner questions table (contract §3); legacy "Open questions" headings work too."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^##\s+.*\bquestions\b", line, re.IGNORECASE):
            stop = next((j for j in range(i + 1, len(lines)) if lines[j].startswith("## ")), None)
            for table in _tables(lines, i + 1, stop):
                h = table.header
                id_col, q_col = _column(h, "#", "id"), _column(h, "question")
                if id_col is None or q_col is None:
                    continue
                st_col = _column(h, "status", prefix=True)
                if st_col is None:
                    st_col = next((k for k, c in enumerate(h) if "default" in c), None)
                nb_col = _column(h, "needed by")
                questions: list[OwnerQuestion] = []
                for _lineno, row in table.rows:
                    if len(row) <= max(id_col, q_col):
                        continue

                    def get(col: int | None, row: list[str] = row) -> str:
                        return row[col] if col is not None and col < len(row) else ""

                    questions.append(
                        OwnerQuestion(
                            id=row[id_col].strip("`* "),
                            question=row[q_col],
                            status=get(st_col),
                            needed_by=parse_needed_by(get(nb_col)),
                        )
                    )
                return tuple(questions)
    return ()


def parse_contract(phase_md: str | None) -> int | None:
    """``PHX-CONTRACT: <n>`` at the start of a line of ``.claude/commands/phase.md``."""
    if phase_md is None:
        return None
    m = _CONTRACT.search(phase_md)
    return int(m.group(1)) if m else None


_TEST_LINE = "Tests, lint and type checks pass"


def parse_test_commands(shared: str | None) -> tuple[str, ...]:
    """Backticked commands of the close-out "Tests, lint and type checks pass" line (spec R6).

    Takes the first clause after the phrase: parenthesised remarks are skipped, and the
    first ``;`` or ``.`` outside backticks and parentheses ends it.
    """
    if shared is None:
        return ()
    line = next((ln for ln in shared.splitlines() if _TEST_LINE in ln), None)
    if line is None:
        return ()
    rest = line.split(_TEST_LINE, 1)[1]
    commands: list[str] = []
    depth = 0
    for k, segment in enumerate(rest.split("`")):
        if k % 2:  # inside backticks
            if depth == 0 and segment.strip():
                commands.append(segment.strip())
            continue
        for ch in segment:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            elif ch in ";." and depth == 0:
                return tuple(commands)
    return tuple(commands)


def _shared_instructions_path(prefix: str | None) -> list[str]:
    paths = ["prompts/_shared-instructions.md"]
    if prefix:
        paths.insert(0, f"prompts/{prefix}_shared-instructions.md")
    return paths


def load_plan(repo: Path) -> Plan:
    """Parse the repo's plan, questions, gates, contract and test command from ``main``."""
    repo = repo.resolve()
    plan_file, prefix = locate_plan(repo)
    text = show_main(repo, plan_file)
    assert text is not None
    rows, problems = parse_phase_table(text)

    phases: list[Phase] = []
    for phase, gate_cell in rows:
        try:
            gate, source = parse_gate(gate_cell), "column"
            prompt_text = show_main(repo, phase.prompt) if phase.prompt else None
            if gate is None and prompt_text is not None:
                gate, source = prompt_gate(prompt_text), "prompt"
        except PlanError as exc:
            raise PlanError(f"line {phase.line}: phase {phase.id}: {exc}") from None
        if gate is None:
            if prompt_text is not None and mentions_publishing(prompt_text):
                gate, source = Gate.REVIEW, "inferred"
            else:
                gate, source = Gate.AUTO, "default"
        if phase.prompt and prompt_text is None and phase.status is not Status.COMPLETE:
            problems.append(f"phase {phase.id}: prompt {phase.prompt} not found on main")
        phases.append(Phase(**{**phase.__dict__, "gate": gate, "gate_source": source}))
    phases.sort(key=lambda p: phase_sort_key(p.id))

    config_text = show_main(repo, ".phx/config.toml")
    try:
        config = parse_config(config_text, f"{MAIN}:.phx/config.toml") if config_text else None
    except ValueError as exc:
        raise PlanError(str(exc)) from None
    if config is not None and config.test_command:
        tests: tuple[str, ...] = (config.test_command,)
        test_source: str | None = "config"
    else:
        shared = next(
            (t for p in _shared_instructions_path(prefix) if (t := show_main(repo, p)) is not None),
            None,
        )
        tests = parse_test_commands(shared)
        test_source = "shared-instructions" if tests else None

    return Plan(
        repo=repo,
        plan_file=plan_file,
        prefix=prefix,
        phases=tuple(phases),
        questions=parse_questions(text),
        test_commands=tests,
        test_source=test_source,
        contract=parse_contract(show_main(repo, ".claude/commands/phase.md")),
        problems=tuple(problems),
    )


# --------------------------------------------------------------------------- eligibility


@dataclass(frozen=True)
class Eligibility:
    """``next_eligible`` result. ``reasons`` explains every phase that is not next."""

    next: Phase | None
    resume: tuple[Phase, ...]
    reasons: dict[str, str] = field(default_factory=dict)


def next_eligible(plan: Plan) -> Eligibility:
    """Lowest ⬜ phase whose dependencies are all ✅ and that no open question blocks (task 10).

    ``🔄`` phases are reported separately as resume candidates; the Gate is left to the
    supervisor.
    """
    status = {p.id: p.status for p in plan.phases}
    reasons: dict[str, str] = {}
    chosen: Phase | None = None
    for p in plan.phases:
        if p.status is not Status.NOT_STARTED:
            reasons[p.id] = {
                Status.COMPLETE: "complete",
                Status.IN_PROGRESS: "in progress (resume candidate)",
                Status.BLOCKED: "blocked",
            }[p.status]
            continue
        unmet = [d for d in p.depends_on if status.get(d) is not Status.COMPLETE]
        if unmet:
            parts = [
                f"{d} ({'missing' if d not in status else STATUS_LABELS[status[d]]})" for d in unmet
            ]
            reasons[p.id] = "dependencies not complete: " + ", ".join(parts)
            continue
        questions = plan.open_questions_for(p.id)
        if questions:
            reasons[p.id] = "open owner question: " + ", ".join(f"#{q.id}" for q in questions)
            continue
        if chosen is None:
            chosen = p
        else:
            reasons[p.id] = f"eligible, after {chosen.id}"
    resume = tuple(p for p in plan.phases if p.status is Status.IN_PROGRESS)
    return Eligibility(chosen, resume, reasons)


# --------------------------------------------------------------------------- live state and drift

_BRANCH_ID = re.compile(r"phase-(\d{2}[a-z]?)-")
_WORKTREE_ID = re.compile(r"-phase-(\d{2}[a-z]?)$")


@dataclass(frozen=True)
class Worktree:
    path: str
    branch: str | None
    phase: str | None
    last_commit: str | None  # ISO 8601 committer date
    uncommitted: int | None  # None when the path is missing


@dataclass(frozen=True)
class LiveState:
    branches: dict[str, str | None]  # branch -> phase ID
    worktrees: tuple[Worktree, ...]  # phase worktrees only (not the main checkout)

    def for_phase(self, phase_id: str) -> tuple[list[str], list[Worktree]]:
        return (
            [b for b, pid in self.branches.items() if pid == phase_id],
            [w for w in self.worktrees if w.phase == phase_id],
        )


@dataclass(frozen=True)
class Drift:
    phase: str
    kind: str  # "unclaimed" | "stale-claim" | "unknown-phase"
    detail: str


def _branch_phase(branch: str | None) -> str | None:
    m = _BRANCH_ID.match(branch or "")
    return m.group(1) if m else None


def load_live(repo: Path) -> LiveState:
    """Branches ``phase-*`` and worktrees, with last commit time and uncommitted count (task 9)."""
    repo = repo.resolve()
    branches = {
        b.strip(): _branch_phase(b.strip())
        for b in _git(repo, "branch", "--list", "phase-*", "--format=%(refname:short)").splitlines()
        if b.strip()
    }
    trees: list[Worktree] = []
    for block in _git(repo, "worktree", "list", "--porcelain").strip().split("\n\n"):
        info: dict[str, str] = {}
        for ln in block.splitlines():
            key, _, value = ln.partition(" ")
            info[key] = value
        path = info.get("worktree")
        if not path or "bare" in info:
            continue
        branch = info.get("branch", "").removeprefix("refs/heads/") or None
        phase = _branch_phase(branch)
        if phase is None:
            m = _WORKTREE_ID.search(Path(path).name)
            phase = m.group(1) if m else None
        if phase is None:
            continue  # the main checkout or an unrelated worktree
        last: str | None = None
        dirty: int | None = None
        if Path(path).is_dir():
            last = _git(Path(path), "log", "-1", "--format=%cI").strip() or None
            dirty = len(_git(Path(path), "status", "--porcelain").splitlines())
        trees.append(Worktree(path, branch, phase, last, dirty))
    return LiveState(branches, tuple(trees))


def detect_drift(plan: Plan, live: LiveState) -> list[Drift]:
    """Drift as ``/phase status`` defines it.

    - a ``phase-NN-*`` branch or worktree exists but the row is not ``🔄`` (a skipped claim).
      ``⛔ Blocked`` rows are exempt: block-with-question keeps the branch and worktree
      on purpose (contract §4.2);
    - a ``🔄`` row with neither branch nor worktree (a stale claim);
    - a branch or worktree for a phase ID the table does not have.
    """
    drift: list[Drift] = []
    ids = {p.id for p in plan.phases}
    live_ids = {pid for pid in live.branches.values() if pid} | {
        w.phase for w in live.worktrees if w.phase
    }
    for pid in sorted(live_ids - ids, key=phase_sort_key):
        branches, trees = live.for_phase(pid)
        names = branches + [w.path for w in trees]
        drift.append(
            Drift(pid, "unknown-phase", f"{', '.join(names)} for a phase not in the table")
        )
    for p in plan.phases:
        branches, trees = live.for_phase(p.id)
        names = branches + [w.path for w in trees]
        if p.status is Status.IN_PROGRESS and not names:
            drift.append(
                Drift(
                    p.id,
                    "stale-claim",
                    "row is 🔄 In progress on main but no branch or worktree exists",
                )
            )
        elif names and p.status in (Status.NOT_STARTED, Status.COMPLETE):
            drift.append(
                Drift(
                    p.id,
                    "unclaimed",
                    f"{', '.join(names)} exists but the row on main is {STATUS_LABELS[p.status]}",
                )
            )
    return drift
