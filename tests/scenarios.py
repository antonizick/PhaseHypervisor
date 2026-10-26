"""Throwaway phased-project repos in the states a phase session can leave behind (Phase 06).

``Scenario`` builds a contract-1 repo with phases 00 and 05 (05 matches the phase named
in the Phase 05 stream fixtures) and then acts like an agent would: claim, work in the
worktree, complete and merge, or block with a question.
"""

import subprocess
from pathlib import Path

PLAN = "TST_IMPLEMENTATION_PLAN.md"
BRANCH = "phase-05-thing"

_HEADER = (
    "| Phase | Phase Name | Phase Purpose | AI Model to Use | Depends on | Status "
    "| Prompt to Initiate This Phase | Gate |"
)
_ROW_05 = (
    "| 05 | Thing | Make `hello.txt` | Haiku 5.5 | 00 | {status} "
    "| [TST_phase-05-thing.md](prompts/TST_phase-05-thing.md) | auto |"
)
_PLAN = f"""# TST: Test Implementation Plan

## Phases

{_HEADER}
|---|---|---|---|---|---|---|---|
| 00 | Planning | Write the plan | Opus 5.5 | none | ✅ Complete | n/a | owner |
{_ROW_05}

## Owner questions
| # | Question | Status / proposed default | Needed by |
|---|---|---|---|
| 6 | Favourite colour? | {{question}} | Phase 05 |

## Phase Log
Newest entries at the bottom.
{{log}}"""

DECIDED = "Decided 2026-10-26 08:00 CDT: blue"
OPEN = "Open (asked 2026-10-26 11:00 CDT, Phase 05, auto mode). Proposed default: blue"
COMPLETE_LOG = """
### 2026-10-26 11:30 CDT: Phase 05: Thing (✅ Complete)
- **Timeline:** started 2026-10-26 11:00 CDT (claim commit abc1234) · finished {ts} · merged {ts}
- Built: hello.txt.
""".format(ts="2026-10-26 11:30 CDT")
BLOCKED_LOG = """
### 2026-10-26 11:20 CDT: Phase 05: Thing (⛔ Blocked)
- **Timeline:** started {ts} (claim commit abc1234) · blocked 2026-10-26 11:20 CDT to (open)
- **Model:** ran as claude-haiku-5-5 (auto mode; plan lists Haiku 5.5)
- **Question:** #6: Favourite colour?
""".replace("{ts}", "2026-10-26 11:00 CDT")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def render(status: str, question: str = DECIDED, log: str = "") -> str:
    return _PLAN.format(status=status, question=question, log=log)


class Scenario:
    def __init__(self, root: Path, test_command: str = "test -f hello.txt") -> None:
        self.repo = root / "repo"
        self.worktree = root / "repo-phase-05"
        files = {
            PLAN: render("⬜ Not started"),
            "prompts/TST_shared-instructions.md": (
                f"- [ ] Tests, lint and type checks pass: `{test_command}`.\n"
            ),
            "prompts/TST_phase-05-thing.md": "# Phase 05\n\nMake hello.txt.\n",
            ".claude/commands/phase.md": "PHX-CONTRACT: 1\n",
        }
        for rel, text in files.items():
            path = self.repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "planning")

    # --- agent actions -----------------------------------------------------------

    def write_plan(self, where: Path, text: str, message: str) -> None:
        (where / PLAN).write_text(text, encoding="utf-8")
        git(where, "commit", "-q", "-m", message, "--", PLAN)

    def claim(self) -> "Scenario":
        self.write_plan(self.repo, render("🔄 In progress"), "chore(plan): start phase 05")
        git(self.repo, "worktree", "add", "-q", str(self.worktree), "-b", BRANCH, "main")
        return self

    def work(self, name: str = "hello.txt", text: str = "hi\n", commit: bool = True) -> "Scenario":
        (self.worktree / name).write_text(text, encoding="utf-8")
        if commit:
            git(self.worktree, "add", name)
            git(self.worktree, "commit", "-q", "-m", f"feat: {name}")
        return self

    def complete(
        self,
        *,
        log: str = COMPLETE_LOG,
        merge: bool = True,
        remove_worktree: bool = True,
        delete_branch: bool = True,
    ) -> "Scenario":
        self.write_plan(
            self.worktree, render("✅ Complete", log=log), "docs(plan): phase 05 complete"
        )
        if merge:
            git(self.repo, "merge", "-q", "--ff-only", BRANCH)
        if remove_worktree:
            git(self.repo, "worktree", "remove", str(self.worktree))
        if delete_branch:
            git(self.repo, "branch", "-q", "-D" if not merge else "-d", BRANCH)
        return self

    def wip_blocked(self) -> "Scenario":
        (self.worktree / "partial.txt").write_text("half\n", encoding="utf-8")
        git(self.worktree, "add", "partial.txt")
        git(self.worktree, "commit", "-q", "-m", "wip(phase-05): blocked, needs a colour")
        return self

    def block(self, *, question: bool = True, log: str = BLOCKED_LOG) -> "Scenario":
        """Full block-with-question (contract §4.2): wip commit, then ⛔ + question on main."""
        self.wip_blocked()
        text = render("⛔ Blocked", question=OPEN if question else DECIDED, log=log)
        self.write_plan(self.repo, text, "chore(plan): phase 05 blocked")
        return self

    def head(self) -> str:
        return git(self.repo, "rev-parse", "main")
