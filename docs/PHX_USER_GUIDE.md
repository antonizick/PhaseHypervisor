# PHX User Guide

> Stub from Phase 04. Phase 07 adds `run`, `status`, `resume`, `stop`, `log` and `answer`; Phase 08 adds `preflight`. PHX is optional (ADR-0011): manual `/phase` keeps working exactly as before.

## `phx plan`: see what PHX sees
```bash
phx plan /home/nick/Work/YTPL2          # human-readable
phx plan /home/nick/Work/YTPL2 --json   # everything, for scripts and debugging
phx plan                                # the repo in the current directory
```
It changes nothing. Everything comes from the repo's **`main`** branch (`git show main:…`), never from the working tree or a phase branch, the same way parallel `/phase` agents read the Status column.

The output has:
- **The phase table**: ID (sorted `15` < `15a` < `15b` < `16`), name, model alias passed to `--model` (`?` if the cell maps to no alias), dependencies, status, Gate and the phase's live branch/worktree. A Gate marked `(prompt)` came from the prompt header (`**Gate:** …`); `(inferred)` means the prompt mentions making a repo public or publishing a release and the plan sets no Gate, so PHX treats it as `review`.
- **Next**: the lowest `⬜ Not started` phase whose dependencies are all `✅ Complete` and that no open owner question needs. This is what `/phase next` would pick. The Gate is reported but does not change "next"; `phx run` applies it.
- **Resume candidates**: phases that are `🔄 In progress`.
- **Why the others wait**: a reason for each not-started or blocked phase (dependencies not complete, open owner question, or "eligible, after NN").
- **Drift** (⚠️): a `phase-NN-*` branch or worktree whose row is not `🔄` (a skipped claim; `⛔ Blocked` rows are exempt because a block keeps its branch), a `🔄` row with no branch or worktree (a stale claim), or a branch for a phase that is not in the table.
- **Open owner questions**: rows whose Status cell starts with `Open`, with the phases that need them.
- **Contract**: the `PHX-CONTRACT` version in `.claude/commands/phase.md`, or "repo not yet migrated". PHX will not run a repo without a known version (Phase 09 migrates the existing repos).
- **Test command**: from `.phx/config.toml` (`test_command = "…"`) on `main` if set, else the backticked commands of the first clause of the shared instructions' "Tests, lint and type checks pass" line, else none.
- **Problems** (⚠️): things that look wrong but don't stop parsing, such as a status cell with no icon or two, an icon that disagrees with its word, an unknown model on a phase still to run, a dependency not in the table, or a prompt file missing on `main`.

Exit status: `0` when the plan was read, `1` with `phx plan: <reason>` when it cannot be (no plan on `main`, a malformed phase ID or row, a duplicate ID, a missing column, an unreadable status, an unknown Gate value, an invalid `.phx/config.toml`).

## Per-repo settings (`.phx/config.toml`)
Optional, committed on `main`, never containing secrets. Unknown keys or wrong types are an error.

| Key | Default | Meaning |
|---|---|---|
| `test_command` | from the shared instructions | Command(s) verification runs on `main` (Phase 06) |
| `max_budget_usd` | none | Passed as `--max-budget-usd` **only when the provider is OpenRouter** (spec R9) |
| `idle_timeout_s` | `1800` | A phase session that emits no stream event for this long is stopped (SIGTERM, then SIGKILL) and classified `timeout` (Phase 05) |
| `wall_timeout_s` | `21600` | Hard cap on one phase session (Phase 05) |
| `poll_interval_s`, `limit_poll_interval_s`, `triage` | `300`, `900`, `true` | Supervisor timing and haiku triage (Phases 06/07) |

Session transcripts land in `~/.local/state/phx/<repo-name>/sessions/<phase>-<n>.jsonl` (redacted), and every launch and its classified ending in `run.jsonl` beside it.
