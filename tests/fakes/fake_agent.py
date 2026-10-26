"""A scripted phase agent for the fake ``claude`` (Phase 07 end-to-end tests).

Enabled by ``PHX_FAKE_AGENT=<scenario.json>``. The scenario maps a key to a list of
actions, used one per call (the last one repeats):

    {"01": ["crash", "complete"], "02": ["block:3"], "probe": ["limit", "ok"]}

Keys: a phase ID (from ``/phase NN --auto`` or ``Continue phase NN``), ``probe`` (the
limit probe, prompt ``ok``) and ``triage`` (a ``--tools`` session). Every call is
appended to ``<scenario>.calls.jsonl``. Phase actions change the repo like a real agent
would (claim, worktree, merge, ``⛔`` with a question) and print a stream-json run with
a ``PHX-RESULT`` line. Actions: ``complete``, ``block:<question id>``, ``limit``,
``limit:<seconds to reset>``, ``crash``, ``hang``, ``refuse``, ``noop``; probe: ``ok``,
``limit``, ``limit:<seconds>``, ``auth``.
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PHASE_RE = re.compile(r"(?:/phase|[Cc]ontinue phase) (\d{2}[a-z]?)\b")


def ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M %Z")


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


# --------------------------------------------------------------------------- stream output


def emit(event: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


def init(session: str) -> None:
    emit({"type": "system", "subtype": "init", "session_id": session, "model": "fake"})


def result(session: str, text: str, *, error: bool = False, cost: float = 0.01) -> None:
    emit(
        {
            "type": "result",
            "subtype": "success",
            "is_error": error,
            "result": text,
            "session_id": session,
            "total_cost_usd": cost,
            "num_turns": 3,
            "usage": {"input_tokens": 1000, "output_tokens": 200},
        }
    )


def phx_result(session: str, phase: str, status: str, reason: str, **kw: Any) -> None:
    line = {
        "contract": 1,
        "phase": phase,
        "status": status,
        "reason": reason,
        "merged": kw.get("merged", False),
        "pushed": False,
        "question_ids": kw.get("question_ids", []),
    }
    result(session, f"Done.\n\nPHX-RESULT: {json.dumps(line, separators=(',', ':'))}")


def limit(session: str, reset_in: int | None) -> None:
    init(session)
    text = "You've hit your session limit"
    if reset_in is not None:
        emit(
            {
                "type": "rate_limit_event",
                "rate_limit_info": {
                    "status": "rejected",
                    "resetsAt": int(time.time()) + reset_in,
                    "rateLimitType": "five_hour",
                },
                "session_id": session,
            }
        )
        text += " · resets soon"
    result(session, text, error=True, cost=0)


# --------------------------------------------------------------------------- plan edits


def plan_file(repo: Path) -> Path:
    return next(repo.glob("*_IMPLEMENTATION_PLAN.md"))


def _set_cell(text: str, header_word: str, row_id: str, column: str, value: str) -> str:
    lines = text.split("\n")
    col = None
    for i, line in enumerate(lines):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and header_word in cells and column in cells:
            col = cells.index(column)
            continue
        if col is not None and line.startswith("|") and cells and cells[0] == row_id:
            parts = line.split("|")
            parts[col + 1] = f" {value} "
            lines[i] = "|".join(parts)
            return "\n".join(lines)
    raise SystemExit(f"fake agent: row {row_id} not found")


def set_status(text: str, phase: str, label: str) -> str:
    return _set_cell(text, "Phase", phase, "Status", label)


def status_of(text: str, phase: str) -> str:
    for line in text.split("\n"):
        if line.startswith(f"| {phase} |"):
            for label in ("⬜", "🔄", "⛔", "✅"):
                if label in line:
                    return label
    raise SystemExit(f"fake agent: phase {phase} not found")


def set_question(text: str, qid: str, status: str, phase: str) -> str:
    try:
        return _set_cell(text, "#", qid, "Status / proposed default", status)
    except SystemExit:
        lines = text.split("\n")
        start = next(i for i, ln in enumerate(lines) if ln.startswith("| # |"))
        end = start + 1
        while end < len(lines) and lines[end].startswith("|"):
            end += 1
        lines.insert(end, f"| {qid} | Which colour? | {status} | Phase {phase} |")
        return "\n".join(lines)


def commit_plan(repo: Path, text: str, message: str) -> None:
    path = plan_file(repo)
    path.write_text(text, encoding="utf-8")
    git(repo, "commit", "-q", "-m", message, "--", path.name)


# --------------------------------------------------------------------------- agent actions


class Agent:
    def __init__(self, repo: Path, phase: str) -> None:
        self.repo = repo
        self.phase = phase
        self.worktree = repo.parent / f"{repo.name}-phase-{phase}"
        self.branch = f"phase-{phase}-work"

    def plan(self, where: Path | None = None) -> str:
        return plan_file(where or self.repo).read_text(encoding="utf-8")

    def claim(self) -> None:
        status = status_of(self.plan(), self.phase)
        if status == "⬜":
            commit_plan(
                self.repo,
                set_status(self.plan(), self.phase, "🔄 In progress"),
                f"chore(plan): start phase {self.phase}",
            )
            git(self.repo, "worktree", "add", "-q", str(self.worktree), "-b", self.branch, "main")
        elif status == "⛔":
            commit_plan(
                self.repo,
                set_status(self.plan(), self.phase, "🔄 In progress"),
                f"chore(plan): resume phase {self.phase}",
            )
            git(self.worktree, "merge", "-q", "--no-edit", "main")
        elif not self.worktree.exists():
            git(self.repo, "worktree", "add", "-q", str(self.worktree), "-b", self.branch, "main")

    def complete(self, session: str) -> None:
        self.claim()
        hello = self.worktree / "hello.txt"
        with hello.open("a", encoding="utf-8") as fh:
            fh.write(f"phase {self.phase}\n")
        git(self.worktree, "add", "hello.txt")
        git(self.worktree, "commit", "-q", "-m", f"feat: phase {self.phase}")
        git(self.worktree, "merge", "-q", "--no-edit", "main")
        text = set_status(self.plan(self.worktree), self.phase, "✅ Complete")
        text += (
            f"\n### {ts()}: Phase {self.phase}: Fake work (✅ Complete)\n"
            f"- **Timeline:** started {ts()} (claim commit abc1234) · finished {ts()} "
            f"· merged {ts()}\n- **Model:** ran as fake (auto mode; plan lists fake)\n"
        )
        commit_plan(self.worktree, text, f"docs(plan): phase {self.phase} complete")
        git(self.repo, "merge", "-q", "--ff-only", self.branch)
        git(self.repo, "worktree", "remove", str(self.worktree))
        git(self.repo, "branch", "-q", "-d", self.branch)
        init(session)
        phx_result(session, self.phase, "complete", "all checks passed", merged=True)

    def block(self, session: str, qid: str) -> None:
        self.claim()
        (self.worktree / "partial.txt").write_text("half\n", encoding="utf-8")
        git(self.worktree, "add", "partial.txt")
        git(self.worktree, "commit", "-q", "-m", f"wip(phase-{self.phase}): blocked, needs answer")
        text = set_question(
            self.plan(),
            qid,
            f"Open (asked {ts()}, Phase {self.phase}, auto mode). Proposed default: blue",
            self.phase,
        )
        text = set_status(text, self.phase, "⛔ Blocked")
        text += (
            f"\n### {ts()}: Phase {self.phase}: Fake work (⛔ Blocked)\n"
            f"- **Timeline:** started {ts()} (claim commit abc1234) · blocked {ts()} to (open)\n"
            f"- **Model:** ran as fake (auto mode; plan lists fake)\n"
            f"- **Question:** #{qid}: Which colour?\n"
        )
        commit_plan(self.repo, text, f"chore(plan): phase {self.phase} blocked")
        init(session)
        phx_result(session, self.phase, "blocked", f"needs question {qid}", question_ids=[qid])


def record(scenario: Path, entry: dict[str, Any]) -> None:
    with open(f"{scenario}.calls.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def main(args: list[str]) -> int:
    scenario = Path(os.environ["PHX_FAKE_AGENT"])
    plan = json.loads(scenario.read_text(encoding="utf-8"))
    prompt = args[args.index("-p") + 1] if "-p" in args else ""
    session = "00000000-0000-4000-8000-00000000fake"
    for flag in ("--session-id", "--resume"):
        if flag in args:
            session = args[args.index(flag) + 1]
    if "--tools" in args:
        key, default = "triage", "summary"
    elif prompt == "ok":
        key, default = "probe", "ok"
    else:
        match = PHASE_RE.search(prompt)
        key, default = (match.group(1), "complete") if match else ("unknown", "noop")
    calls_path = Path(f"{scenario}.calls.jsonl")
    n = 0
    if calls_path.exists():
        n = sum(1 for ln in calls_path.read_text().splitlines() if json.loads(ln)["key"] == key)
    actions = plan.get(key) or [default]
    action = actions[min(n, len(actions) - 1)]
    record(
        scenario,
        {
            "key": key,
            "action": action,
            "prompt": prompt,
            "resume": "--resume" in args,
            "session": session,
            "model": args[args.index("--model") + 1] if "--model" in args else None,
            "auto": os.environ.get("PHX_AUTO"),
        },
    )
    name, _, arg = action.partition(":")
    repo = Path.cwd()

    if key == "triage":
        init(session)
        result(session, "Summary: the phase needs Nick's favourite colour.", cost=0.001)
        return 0
    if key == "probe":
        if name == "ok":
            init(session)
            result(session, "ok", cost=0.0001)
        elif name == "auth":
            init(session)
            result(session, "Invalid API key · Please run /login", error=True, cost=0)
            return 1
        else:
            limit(session, int(arg) if arg else None)
        return 0

    agent = Agent(repo, key)
    if name == "complete":
        agent.complete(session)
    elif name == "block":
        agent.block(session, arg or "9")
    elif name == "limit":
        agent.claim()
        limit(session, int(arg) if arg else None)
    elif name == "crash":
        agent.claim()
        init(session)
        return 1
    elif name == "hang":
        agent.claim()
        init(session)
        for _ in range(600):
            time.sleep(0.1)
        return 0
    elif name == "refuse":
        init(session)
        phx_result(session, key, "refused", "dependency not complete")
    else:  # noop
        init(session)
        result(session, "I did nothing.")
    return 0
