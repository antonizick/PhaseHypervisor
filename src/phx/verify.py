"""Independent post-phase verification (spec R6, contract §6).

After a phase session ends, :func:`verify_phase` decides from the repo itself, read from
``main``, what actually happened. Each check reports pass, fail or skip with evidence;
the session's ``PHX-RESULT`` line is only compared against the result (disagreement is
``needs_review``). Nothing here writes to the user's checkout: the test command runs
in a throwaway clone of ``main``. The one allowed repair (a missing ``⛔`` commit) lives
in :mod:`phx.recover`.

Test commands are plan text. They run without a shell (ADR-0015): a command is split
into ``&&``-joined steps, each a word list with optional ``NAME=value`` prefixes, a
``cd DIR`` step, and quoted words or ``*``/``**`` globs expanded inside the clone.
Pipes, redirects, ``;``, ``||``, variables and command substitution are refused.
"""

import contextlib
import glob
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from phx.classify import Classification, ExitClass, PhxResult
from phx.logging import EventLog
from phx.paths import Config
from phx.plan import (
    MAIN,
    STATUS_LABELS,
    Plan,
    PlanError,
    Status,
    load_live,
    load_plan,
    show_main,
)
from phx.redact import redact_text

# --------------------------------------------------------------------------- results


class CheckStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


@dataclass(frozen=True)
class Check:
    name: str
    status: CheckStatus
    evidence: str
    required: bool = True  # a failing optional check is reported, never decisive


class RepoState(StrEnum):
    """What the row on ``main`` says, or ``missing`` when the plan cannot be read."""

    COMPLETE = "complete"
    BLOCKED = "blocked"
    IN_PROGRESS = "in_progress"
    NOT_STARTED = "not_started"
    MISSING = "missing"


class Outcome(StrEnum):
    COMPLETE = "complete"  # ✅ and every required check passed
    BLOCKED = "blocked"  # ⛔ with an open question recorded
    IN_PROGRESS = "in_progress"  # 🔄: the work stopped part-way
    NOT_STARTED = "not_started"  # ⬜: nothing was claimed
    NEEDS_REVIEW = "needs_review"  # the result line and the repo disagree
    FAILED = "failed"  # a required check failed


_STATE_OF = {
    Status.COMPLETE: RepoState.COMPLETE,
    Status.BLOCKED: RepoState.BLOCKED,
    Status.IN_PROGRESS: RepoState.IN_PROGRESS,
    Status.NOT_STARTED: RepoState.NOT_STARTED,
}
_MARK = {CheckStatus.PASS: "✓", CheckStatus.FAIL: "✗", CheckStatus.SKIP: "-"}


@dataclass(frozen=True)
class Verdict:
    phase: str
    state: RepoState
    outcome: Outcome
    checks: tuple[Check, ...]
    disagreements: tuple[str, ...] = ()
    main_head: str | None = None
    wip_blocked: bool = False  # the phase branch has a `wip(phase-NN): blocked` commit
    question_ids: tuple[str, ...] = ()  # open owner questions needed by the phase
    result: PhxResult | None = None

    @property
    def failures(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if c.required and c.status is CheckStatus.FAIL)

    @property
    def ok(self) -> bool:
        return not self.failures and not self.disagreements

    def check(self, name: str) -> Check | None:
        return next((c for c in self.checks if c.name == name), None)

    def summary(self) -> str:
        """One line for ``run.jsonl`` reasons and notifications."""
        if self.disagreements:
            return "needs review: " + "; ".join(self.disagreements)
        if self.failures:
            return "verification failed: " + "; ".join(
                f"{c.name}: {c.evidence.splitlines()[0]}" for c in self.failures
            )
        return {
            Outcome.COMPLETE: "complete and verified",
            Outcome.BLOCKED: "blocked on question " + ", ".join(f"#{q}" for q in self.question_ids),
            Outcome.IN_PROGRESS: "in progress (work stopped part-way)",
            Outcome.NOT_STARTED: "not started (nothing claimed)",
        }.get(self.outcome, str(self.outcome))

    def report(self) -> str:
        """Human-readable report: every check with its evidence, then any disagreement."""
        lines = [f"Phase {self.phase}: {self.summary()} (repo shows {self.state})"]
        for c in self.checks:
            tag = "" if c.required else " (optional)"
            first, *rest = c.evidence.splitlines() or [""]
            lines.append(f"  {_MARK[c.status]} {c.name}{tag}: {first}")
            lines += [f"      {ln}" for ln in rest]
        if self.result is not None:
            lines.append(
                f"  agent said: {self.result.status} ({self.result.reason}), "
                f"merged={self.result.merged}, pushed={self.result.pushed}"
            )
        lines += [f"  ! {d}" for d in self.disagreements]
        return "\n".join(lines)

    def as_log(self) -> dict[str, Any]:
        return {
            "state": str(self.state),
            "outcome": str(self.outcome),
            "main_head": self.main_head,
            "wip_blocked": self.wip_blocked,
            "question_ids": list(self.question_ids),
            "disagreements": list(self.disagreements),
            "checks": [
                {
                    "name": c.name,
                    "status": str(c.status),
                    "required": c.required,
                    "evidence": c.evidence,
                }
                for c in self.checks
            ],
        }


# --------------------------------------------------------------------------- git helpers


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Read-only git call (``--no-optional-locks``: ``status`` must not rewrite the index)."""
    return subprocess.run(
        ["git", "--no-optional-locks", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _out(repo: Path, *args: str) -> str | None:
    proc = _git(repo, *args)
    return proc.stdout.strip() if proc.returncode == 0 else None


def main_head(repo: Path) -> str | None:
    return _out(repo, "rev-parse", "--verify", "-q", f"refs/heads/{MAIN}")


def dirty_lines(repo: Path) -> frozenset[str]:
    """``git status --porcelain`` lines of a checkout."""
    out = _out(repo, "status", "--porcelain")
    return frozenset(ln for ln in (out or "").splitlines() if ln.strip())


@dataclass(frozen=True)
class Baseline:
    """The main checkout just before a launch, so verification can tell what the phase did."""

    main_head: str | None
    dirty: frozenset[str] = frozenset()


def capture_baseline(repo: Path) -> Baseline:
    return Baseline(main_head(repo), dirty_lines(repo))


def wip_blocked(repo: Path, phase_id: str, branches: list[str] | None = None) -> bool:
    """A ``phase-NN-*`` branch carries a ``wip(phase-NN): blocked`` commit not on ``main``."""
    if branches is None:
        branches = [b for b, pid in load_live(repo).branches.items() if pid == phase_id]
    marker = re.compile(rf"^wip\(phase-{re.escape(phase_id)}\): blocked", re.IGNORECASE)
    for branch in branches:
        log = _out(repo, "log", "--format=%s", f"{MAIN}..refs/heads/{branch}") or ""
        if any(marker.match(s) for s in log.splitlines()):
            return True
    return False


# --------------------------------------------------------------------------- Phase Log


@dataclass(frozen=True)
class LogEntry:
    line: int
    heading: str
    status: str  # text of the heading's last parenthesis, e.g. "✅ Complete"
    first_bullet: str | None

    @property
    def has_timeline(self) -> bool:
        return (self.first_bullet or "").startswith("- **Timeline:**")


_LOG_HEADING = re.compile(r"^###\s+.+?:\s+Phase\s+(?P<id>\d{2}[a-z]?)\b(?P<rest>.*)$")
_LAST_PAREN = re.compile(r"\(([^()]*)\)\s*$")


def phase_log_entries(text: str, phase_id: str) -> list[LogEntry]:
    """Phase Log entries for ``phase_id``, oldest first (``### <TS>: Phase NN: … (<status>)``)."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if re.match(r"^##\s+Phase Log", ln)), 0)
    entries: list[LogEntry] = []
    for i in range(start, len(lines)):
        m = _LOG_HEADING.match(lines[i])
        if not m or m.group("id") != phase_id:
            continue
        paren = _LAST_PAREN.search(m.group("rest"))
        bullet = next(
            (ln.strip() for ln in lines[i + 1 :] if ln.strip()),
            None,
        )
        if bullet is not None and bullet.startswith("#"):
            bullet = None
        entries.append(LogEntry(i + 1, lines[i], paren.group(1) if paren else "", bullet))
    return entries


def _is(status_text: str, icon: str, word: str) -> bool:
    return icon in status_text or word in status_text.lower()


# --------------------------------------------------------------------------- test commands


class UnsupportedCommand(ValueError):
    """The test command needs a shell feature PHX does not interpret (ADR-0015)."""


class MissingPath(Exception):
    """The command refers to a file or directory this checkout does not have."""


@dataclass(frozen=True)
class Word:
    text: str  # the literal word (quotes removed)
    pattern: str | None = None  # glob pattern if the word has unquoted * ? [


@dataclass(frozen=True)
class Step:
    argv: tuple[Word, ...] = ()
    env: tuple[tuple[str, str], ...] = ()
    cd: str | None = None  # a `cd DIR` step


_AND = object()
_FORBIDDEN = set("|;&<>()`${}\n")
_GLOB = set("*?[")
_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _tokenize(command: str) -> list[Any]:
    tokens: list[Any] = []
    text: list[str] = []
    pattern: list[str] = []
    in_word = globbed = False

    def flush() -> None:
        nonlocal in_word, globbed
        if in_word:
            literal = "".join(text)
            tokens.append(Word(literal, "".join(pattern) if globbed else None))
        text.clear()
        pattern.clear()
        in_word = globbed = False

    def quoted(s: str) -> None:
        nonlocal in_word
        text.append(s)
        pattern.append(glob.escape(s))
        in_word = True

    i, n = 0, len(command)
    while i < n:
        c = command[i]
        if c in " \t":
            flush()
            i += 1
        elif command.startswith("&&", i):
            flush()
            tokens.append(_AND)
            i += 2
        elif c in _FORBIDDEN or (c == "#" and not in_word) or (c == "~" and not in_word):
            raise UnsupportedCommand(f"shell syntax {c!r} at position {i}")
        elif c == "'":
            j = command.find("'", i + 1)
            if j < 0:
                raise UnsupportedCommand("unterminated single quote")
            quoted(command[i + 1 : j])
            i = j + 1
        elif c == '"':
            j, part = i + 1, []
            while j < n and command[j] != '"':
                if command[j] in "$`":
                    raise UnsupportedCommand(f"expansion {command[j]!r} inside double quotes")
                if command[j] == "\\" and j + 1 < n and command[j + 1] in '"\\':
                    j += 1
                part.append(command[j])
                j += 1
            if j >= n:
                raise UnsupportedCommand("unterminated double quote")
            quoted("".join(part))
            i = j + 1
        elif c == "\\":
            if i + 1 >= n:
                raise UnsupportedCommand("trailing backslash")
            quoted(command[i + 1])
            i += 2
        else:
            text.append(c)
            pattern.append(c)
            globbed = globbed or c in _GLOB
            in_word = True
            i += 1
    flush()
    return tokens


def parse_command(command: str) -> list[Step]:
    """Split a test command into steps; ``UnsupportedCommand`` if it needs a real shell."""
    tokens = _tokenize(command)
    segments: list[list[Word]] = [[]]
    for tok in tokens:
        if tok is _AND:
            segments.append([])
        else:
            segments[-1].append(tok)
    steps: list[Step] = []
    for words in segments:
        if not words:
            raise UnsupportedCommand("empty command around '&&'")
        env: list[tuple[str, str]] = []
        while words and words[0].pattern is None and _ASSIGN.match(words[0].text):
            name, _, value = words.pop(0).text.partition("=")
            env.append((name, value))
        if not words:
            raise UnsupportedCommand("assignment without a command")
        if words[0].text == "cd":
            if len(words) != 2 or env or words[1].pattern is not None:
                raise UnsupportedCommand("cd takes exactly one plain directory")
            steps.append(Step(cd=words[1].text))
        else:
            steps.append(Step(tuple(words), tuple(env)))
    return steps


# Variables never passed to the repo's own tests.
_STRIP_ENV = (
    "PHX_AUTO",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY",
    "VIRTUAL_ENV",
)
_TAIL_LINES = 20


@dataclass(frozen=True)
class CommandResult:
    command: str
    status: CheckStatus
    detail: str
    exit_code: int | None = None
    duration_s: float = 0.0
    output_tail: str = ""


def _inside(path: Path, root: Path) -> bool:
    return path == root or path.is_relative_to(root)


def _run_group(
    argv: list[str], cwd: Path, env: Mapping[str, str], timeout: float
) -> subprocess.CompletedProcess[str]:
    """Run ``argv`` in its own process group; on timeout kill the whole group.

    ``subprocess.run(timeout=…)`` kills only the direct child, so a test runner's
    workers (``make`` → ``npm`` → ``node``) would outlive the check (Phase 11).
    """
    with subprocess.Popen(
        argv,
        cwd=cwd,
        env=dict(env),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        start_new_session=True,
    ) as proc:
        try:
            out, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            raise
        return subprocess.CompletedProcess(argv, proc.returncode, out, None)


def run_command(
    command: str,
    root: Path,
    env: Mapping[str, str],
    *,
    timeout: float,
    missing_is_skip: bool,
) -> CommandResult:
    """Run one test command in ``root`` (a throwaway clone), without a shell."""
    started = time.monotonic()
    try:
        steps = parse_command(command)
    except UnsupportedCommand as exc:
        return CommandResult(
            command,
            CheckStatus.FAIL,
            f"not run: {exc}; set test_command in .phx/config.toml to a script (ADR-0015)",
        )
    root = root.resolve()
    cwd = root
    try:
        for step in steps:
            if step.cd is not None:
                target = (cwd / step.cd).resolve()
                if not _inside(target, root):
                    raise UnsupportedCommand(f"cd {step.cd} leaves the checkout")
                if not target.is_dir():
                    raise MissingPath(f"directory {step.cd} not in this checkout")
                cwd = target
                continue
            argv: list[str] = []
            for word in step.argv:
                if word.pattern is None:
                    argv.append(word.text)
                    continue
                matches = sorted(glob.glob(word.pattern, root_dir=cwd, recursive=True))
                if not matches:
                    raise MissingPath(f"{word.text} matches no files in this checkout")
                if any(not _inside((cwd / m).resolve(), root) for m in matches):
                    raise UnsupportedCommand(f"{word.text} reaches outside the checkout")
                argv += matches
            child_env = {**env, **dict(step.env)}
            exe = argv[0]
            if "/" in exe:
                if not (cwd / exe).is_file():
                    raise MissingPath(f"{exe} not in this checkout")
            elif shutil.which(exe, path=child_env.get("PATH")) is None:
                return CommandResult(command, CheckStatus.FAIL, f"{exe}: command not found on PATH")
            try:
                proc = _run_group(argv, cwd, child_env, timeout)
            except subprocess.TimeoutExpired:
                return CommandResult(
                    command,
                    CheckStatus.FAIL,
                    f"timed out after {timeout:g} s",
                    duration_s=time.monotonic() - started,
                )
            tail = redact_text("\n".join(proc.stdout.splitlines()[-_TAIL_LINES:]))
            if proc.returncode != 0:
                return CommandResult(
                    command,
                    CheckStatus.FAIL,
                    f"exit {proc.returncode} from {' '.join(argv[:3])}",
                    proc.returncode,
                    time.monotonic() - started,
                    tail,
                )
    except UnsupportedCommand as exc:
        return CommandResult(command, CheckStatus.FAIL, f"not run: {exc} (ADR-0015)")
    except MissingPath as exc:
        if missing_is_skip:
            return CommandResult(
                command,
                CheckStatus.SKIP,
                f"{exc}; this plan's checks may live in another repo (ADR-0013); "
                "set test_command in .phx/config.toml to run them here",
            )
        return CommandResult(command, CheckStatus.FAIL, str(exc))
    return CommandResult(command, CheckStatus.PASS, "exit 0", 0, time.monotonic() - started)


def test_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    for key in _STRIP_ENV:
        env.pop(key, None)
    return env


def run_tests(
    plan: Plan,
    commit: str,
    *,
    timeout: float,
    env: Mapping[str, str] | None = None,
    workdir: Path | None = None,
) -> Check:
    """The plan's test commands on a temporary clone of ``commit`` (spec R6)."""
    if not plan.test_commands:
        return Check("tests", CheckStatus.SKIP, "the plan names no test command (spec R6)")
    tmp = Path(tempfile.mkdtemp(prefix=f"phx-verify-{plan.repo.name}-", dir=workdir))
    try:
        checkout = tmp / plan.repo.name
        clone = subprocess.run(
            ["git", "clone", "-q", "--no-checkout", str(plan.repo), str(checkout)],
            capture_output=True,
            text=True,
            check=False,
        )
        if clone.returncode == 0:
            clone = subprocess.run(
                ["git", "-C", str(checkout), "checkout", "-q", "--detach", commit],
                capture_output=True,
                text=True,
                check=False,
            )
        if clone.returncode != 0:
            return Check("tests", CheckStatus.FAIL, f"could not clone main: {clone.stderr.strip()}")
        child_env = test_env(env)
        results = [
            run_command(
                cmd,
                checkout,
                child_env,
                timeout=timeout,
                missing_is_skip=plan.test_source != "config",
            )
            for cmd in plan.test_commands
        ]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    lines = []
    for r in results:
        lines.append(f"`{r.command}`: {r.status} ({r.detail}, {r.duration_s:.1f} s)")
        lines += (
            [f"  {ln}" for ln in r.output_tail.splitlines()] if r.status is CheckStatus.FAIL else []
        )
    statuses = {r.status for r in results}
    if CheckStatus.FAIL in statuses:
        status = CheckStatus.FAIL
    elif statuses == {CheckStatus.SKIP}:
        status = CheckStatus.SKIP
    else:
        status = CheckStatus.PASS
    source = f"from {plan.test_source}, clean clone of {MAIN} at {commit[:7]}"
    return Check("tests", status, "\n".join([*lines, source]))


# Lockfile -> the command that installs from it, run from the repo root (Phase 11, F9).
_INSTALLERS = (
    ("package-lock.json", "npm ci{prefix}", " --prefix {dir}"),
    ("pnpm-lock.yaml", "pnpm install --frozen-lockfile{prefix}", " --dir {dir}"),
    ("yarn.lock", "yarn install --frozen-lockfile{prefix}", " --cwd {dir}"),
    ("uv.lock", "uv sync --frozen{prefix}", " --directory {dir}"),
)


def install_steps(repo: Path, commit: str = MAIN) -> list[str]:
    """Install commands for the lockfiles tracked at ``commit`` (depth <= 2, no vendored dirs).

    A clean clone has none of what they install, so a test command that relies on them
    fails in verification after good work (Phase 10 pilot, YTPL2 Phase 03).
    """
    out = _out(repo, "ls-tree", "-r", "--name-only", commit)
    steps: list[str] = []
    for name in sorted((out or "").splitlines(), key=lambda n: (n.count("/"), n)):
        parts = name.split("/")
        if len(parts) > 3 or any(p in ("node_modules", "vendor", ".venv") for p in parts):
            continue
        for lockfile, template, prefix in _INSTALLERS:
            if parts[-1] == lockfile:
                where = "/".join(parts[:-1])
                steps.append(template.format(prefix=prefix.format(dir=where) if where else ""))
    return steps


def suggest_test_command(plan: Plan, commit: str = MAIN) -> str | None:
    """A ``test_command`` that installs dependencies first, or ``None`` if none are tracked."""
    steps = install_steps(plan.repo, commit)
    if not steps or not plan.test_commands:
        return None
    return " && ".join([*steps, *plan.test_commands])


# --------------------------------------------------------------------------- the checks


def _checkout_checks(repo: Path, baseline: Baseline | None) -> list[Check]:
    branch = _out(repo, "branch", "--show-current")
    checks = [
        Check(
            "main_checkout",
            CheckStatus.PASS if branch == MAIN else CheckStatus.FAIL,
            f"the main checkout is on {branch or 'a detached HEAD'}",
        )
    ]
    dirty = dirty_lines(repo)
    known = baseline.dirty if baseline else frozenset()
    new = sorted(dirty - known)
    if new:
        evidence = "uncommitted changes: " + ", ".join(ln[3:] for ln in new[:10])
        checks.append(Check("main_clean", CheckStatus.FAIL, evidence))
    else:
        note = f" ({len(dirty)} pre-existing change(s) ignored)" if dirty else ""
        checks.append(Check("main_clean", CheckStatus.PASS, "working tree clean" + note))
    return checks


def _pushed_check(repo: Path) -> Check:
    if _out(repo, "config", "--get", "remote.origin.url") is None:
        return Check("pushed", CheckStatus.SKIP, "no origin remote", required=False)
    ahead = _out(repo, "rev-list", "--count", f"refs/remotes/origin/{MAIN}..refs/heads/{MAIN}")
    if ahead is None:
        return Check("pushed", CheckStatus.SKIP, f"no origin/{MAIN} tracking ref", required=False)
    if ahead == "0":
        return Check("pushed", CheckStatus.PASS, f"origin/{MAIN} has {MAIN}", required=False)
    return Check(
        "pushed",
        CheckStatus.FAIL,
        f"{MAIN} is {ahead} commit(s) ahead of origin/{MAIN} (last known; not fetched)",
        required=False,
    )


def _log_check(text: str, phase_id: str, blocked: bool) -> Check:
    entries = phase_log_entries(text, phase_id)
    want = ("⛔", "blocked") if blocked else ("✅", "complete")
    entry = next((e for e in reversed(entries) if _is(e.status, *want)), None)
    if entry is None:
        return Check(
            "phase_log", CheckStatus.FAIL, f"no Phase Log entry for {phase_id} ({want[0]})"
        )
    where = f"line {entry.line}: {entry.heading.strip()}"
    if not entry.has_timeline:
        return Check("phase_log", CheckStatus.FAIL, f"{where}\nfirst bullet is not the Timeline")
    if blocked and "blocked" not in (entry.first_bullet or ""):
        return Check("phase_log", CheckStatus.FAIL, f"{where}\nTimeline has no blocked interval")
    return Check("phase_log", CheckStatus.PASS, where)


def _disagreements(
    phase_id: str,
    classification: Classification | None,
    state: RepoState,
    checks: list[Check],
    question_ids: tuple[str, ...],
    baseline: Baseline | None,
    head: str | None,
) -> list[str]:
    """Where the agent's ``PHX-RESULT`` line contradicts the repo (contract §6)."""
    result = classification.result if classification else None
    if result is None:
        return []
    by_name = {c.name: c for c in checks}
    out: list[str] = []
    if result.phase is not None and result.phase != phase_id:
        out.append(f"result line names phase {result.phase}, not {phase_id}")
    expected = {
        "complete": RepoState.COMPLETE,
        "blocked": RepoState.BLOCKED,
    }.get(result.status)
    if expected is not None and state is not expected:
        out.append(f"agent said {result.status}, repo shows {state}")
    if result.status == "refused":
        if state is RepoState.IN_PROGRESS:
            out.append("agent said refused, but the row is 🔄 In progress")
        if baseline and baseline.main_head and head != baseline.main_head:
            out.append(f"agent said refused, but {MAIN} moved since launch")
    if result.merged and (state is not RepoState.COMPLETE or _failed(by_name, "branch_merged")):
        out.append("agent said merged, but the phase branch is not merged")
    if result.pushed and _failed(by_name, "pushed"):
        out.append(f"agent said pushed, but {by_name['pushed'].evidence}")
    if result.status == "blocked":
        unknown = [q for q in result.question_ids if q not in question_ids]
        if unknown:
            out.append(
                "agent named question(s) "
                + ", ".join(f"#{q}" for q in unknown)
                + f", which are not open for phase {phase_id}"
            )
    return out


def _failed(by_name: dict[str, Check], name: str) -> bool:
    check = by_name.get(name)
    return check is not None and check.status is CheckStatus.FAIL


def verify_phase(
    repo: Path,
    phase_id: str,
    classification: Classification | None = None,
    *,
    baseline: Baseline | None = None,
    config: Config | None = None,
    env: Mapping[str, str] | None = None,
    run_test_commands: bool = True,
    log: EventLog | None = None,
) -> Verdict:
    """Check what phase ``phase_id`` left in ``repo`` (the main checkout), from ``main``.

    ``baseline`` (taken before the launch) lets pre-existing uncommitted files pass and
    a ``refused`` session be checked for "nothing changed". Tests run only when the row
    is ``✅`` (or ``run_test_commands`` is false).
    """
    repo = repo.resolve()
    config = config or Config()
    verdict = _verify(repo, phase_id, classification, baseline, config, env, run_test_commands)
    if log is not None:
        log.event(
            "verify",
            phase=phase_id,
            reason=verdict.summary(),
            session_class=str(classification.cls) if classification else None,
            **verdict.as_log(),
        )
    return verdict


def _verify(
    repo: Path,
    phase_id: str,
    classification: Classification | None,
    baseline: Baseline | None,
    config: Config,
    env: Mapping[str, str] | None,
    run_test_commands: bool,
) -> Verdict:
    result = classification.result if classification else None
    try:
        plan = load_plan(repo)
        phase = plan.phase(phase_id)
    except (PlanError, KeyError) as exc:
        detail = f"phase {phase_id} not in the table" if isinstance(exc, KeyError) else str(exc)
        return Verdict(
            phase_id,
            RepoState.MISSING,
            Outcome.FAILED,
            (Check("plan", CheckStatus.FAIL, detail),),
            result=result,
        )
    state = _STATE_OF[phase.status]
    head = main_head(repo)
    live = load_live(repo)
    branches, trees = live.for_phase(phase_id)
    wip = wip_blocked(repo, phase_id, branches)
    question_ids = tuple(q.id for q in plan.open_questions_for(phase_id))
    text = show_main(repo, plan.plan_file) or ""
    checks = [
        Check(
            "status",
            CheckStatus.PASS,
            f"row {phase_id} on {MAIN} is {STATUS_LABELS[phase.status]} "
            f"({plan.plan_file}:{phase.line})",
        )
    ]
    names = branches + [w.path for w in trees]

    if classification is not None and classification.cls is ExitClass.REFUSED:
        if baseline and baseline.main_head:
            same = head == baseline.main_head
            checks.append(
                Check(
                    "main_unchanged",
                    CheckStatus.PASS if same else CheckStatus.FAIL,
                    f"{MAIN} at {(head or '?')[:7]}, launch at {baseline.main_head[:7]}",
                    required=False,
                )
            )
    elif state is RepoState.COMPLETE:
        unmerged = [
            b
            for b in branches
            if _git(
                repo, "merge-base", "--is-ancestor", f"refs/heads/{b}", f"refs/heads/{MAIN}"
            ).returncode
            != 0
        ]
        checks.append(
            Check(
                "branch_merged",
                CheckStatus.FAIL if unmerged else CheckStatus.PASS,
                f"not merged into {MAIN}: {', '.join(unmerged)}"
                if unmerged
                else (
                    f"{', '.join(branches)} merged into {MAIN}"
                    if branches
                    else f"no phase-{phase_id}-* branch left; ✅ reached {MAIN}"
                ),
            )
        )
        checks.append(
            Check(
                "branch_deleted",
                CheckStatus.FAIL if branches else CheckStatus.PASS,
                f"still exists: {', '.join(branches)}" if branches else "no phase branch",
            )
        )
        checks.append(
            Check(
                "worktree_removed",
                CheckStatus.FAIL if trees else CheckStatus.PASS,
                "still registered: "
                + ", ".join(
                    w.path + (" (missing; git worktree prune)" if w.uncommitted is None else "")
                    for w in trees
                )
                if trees
                else "no phase worktree",
            )
        )
        checks.append(_log_check(text, phase_id, blocked=False))
        checks.append(_pushed_check(repo))
    elif state is RepoState.BLOCKED:
        checks.append(
            Check(
                "question_recorded",
                CheckStatus.PASS if question_ids else CheckStatus.FAIL,
                "open: " + ", ".join(f"#{q}" for q in question_ids)
                if question_ids
                else f"no open owner question names phase {phase_id}",
            )
        )
        checks.append(_log_check(text, phase_id, blocked=True))
        checks.append(
            Check(
                "branch_kept",
                CheckStatus.PASS if names else CheckStatus.FAIL,
                ", ".join(names) if names else "no branch or worktree to resume from",
                required=False,
            )
        )
    elif state is RepoState.IN_PROGRESS:
        evidence = [
            f"{w.path}: last commit {w.last_commit or '?'}, "
            + ("missing on disk" if w.uncommitted is None else f"{w.uncommitted} uncommitted")
            for w in trees
        ] or [f"branch {b} (no worktree)" for b in branches]
        checks.append(
            Check(
                "work_in_progress",
                CheckStatus.PASS if names else CheckStatus.FAIL,
                "\n".join(evidence)
                if names
                else "row is 🔄 but no branch or worktree (stale claim)",
                required=False,
            )
        )

    checks += _checkout_checks(repo, baseline)

    run = (
        run_test_commands
        and state is RepoState.COMPLETE
        and head is not None
        and not (classification is not None and classification.cls is ExitClass.REFUSED)
    )
    if run:
        assert head is not None
        checks.append(run_tests(plan, head, timeout=config.test_timeout_s, env=env))

    disagreements = _disagreements(
        phase_id, classification, state, checks, question_ids, baseline, head
    )
    failed = any(c.required and c.status is CheckStatus.FAIL for c in checks)
    if disagreements:
        outcome = Outcome.NEEDS_REVIEW
    elif failed:
        outcome = Outcome.FAILED
    else:
        outcome = Outcome(str(state))
    return Verdict(
        phase_id,
        state,
        outcome,
        tuple(checks),
        tuple(disagreements),
        head,
        wip,
        question_ids,
        result,
    )
