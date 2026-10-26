# PHX Architecture

> Skeleton from Phase 01; Phase 02 and 04 modules documented below. Each later phase fills in its components; keep this file in sync with the code.

## Components
| Component | Module (planned) | Phase | Role |
|---|---|---|---|
| CLI | `src/phx/__main__.py`, `cli.py` | 02 | argparse entry point `phx` |
| State and logging | `paths.py`, `logging.py`, `redact.py` | 02 | state dirs, JSONL log, secret redaction |
| Plan parser | `plan.py` | 04 | rows, IDs, ordering, deps, status, model alias, gates, owner questions, drift |
| Session runner | `runner.py`, `classify.py` | 05 | launch via `ai-provider run -p`, stream-json capture, exit classification |
| Verifier and recovery | `verify.py`, `recover.py`, `triage.py` | 06 | independent post-phase checks, blocked-status repair, retry/resume |
| Supervisor | `supervisor.py`, `locks.py`, `notify.py`, `vault.py` | 07 | `phx run / status / resume / stop / log / answer`, locks, state, notifications |
| Preflight | `preflight.py` | 08 | one interactive question sweep before a hands-off run |

## Phase 02 modules (built)
| Module | Role |
|---|---|
| `cli.py`, `__main__.py` | argparse entry point. Global flags `--state-dir`, `-v/--verbose`, `--version`. The `COMMANDS` table maps each subcommand to its help text and the phase that implements it; stubs print `not implemented yet (Phase NN)` and exit 2. |
| `paths.py` | `default_state_root()` (`$XDG_STATE_HOME/phx`, else `~/.local/state/phx`), `state_dir(repo)`, `sessions_dir()`, and `load_config(repo)` reading `<repo>/.phx/config.toml` into the frozen `Config` dataclass (`test_command`, `max_budget_usd`, `poll_interval_s`, `limit_poll_interval_s`, `triage`). Unknown keys or wrong types raise `ValueError`. `parse_config(text, source)` parses TOML text from anywhere (Phase 04 reads it from `main`). |
| `logging.py` | `EventLog(path)`: one redacted JSON object per line (`ts` as `YYYY-MM-DD HH:MM:SS TZ`, `epoch`, `event`, `phase`, `reason`, extra fields), a single `O_APPEND` write plus `fsync` per record (safe for concurrent appenders), optional human-readable stderr mirror. |
| `redact.py` | `redact()` / `redact_text()`: `sk-or-…`, `sk-ant-…`, `ANTHROPIC_AUTH_TOKEN=…`, `ANTHROPIC_API_KEY=…`, `Authorization: Bearer …`, `ghp_`/`gho_`/`github_pat_` tokens, in strings and nested JSON. Every `EventLog` write goes through it. |

## Phase 04: plan model (`plan.py`, built)
Pure, read-only. Every file comes from `main` through `git show main:<path>` (`show_main`), never the working tree.

```
load_plan(repo) ──► Plan
  locate_plan        <PREFIX>_IMPLEMENTATION_PLAN.md (prefix from CLAUDE.md if several) or legacy IMPLEMENTATION_PLAN.md
  parse_phase_table  columns by header name: Phase, Phase Name, AI Model to Use, Depends on, Status, Prompt…, Gate (optional)
  Gate               column → prompt header `**Gate:**` → inferred `review` (publishing mention) → `auto`
  parse_questions    "## … questions" table: #, Question, Status…/Proposed default, Needed by
  parse_contract     `^PHX-CONTRACT: (\d+)\b` in .claude/commands/phase.md
  test command       .phx/config.toml test_command → shared instructions' first clause → none
load_live(repo) ──► LiveState   phase-* branches; worktrees (porcelain) with last commit and uncommitted count
detect_drift(plan, live) ──► [Drift]   unclaimed · stale-claim · unknown-phase
next_eligible(plan) ──► Eligibility(next, resume, reasons)
```

| Type | Fields / meaning |
|---|---|
| `Plan` | `repo`, `plan_file`, `prefix` (`None` = legacy), `phases` (sorted), `questions`, `test_commands` (tuple), `test_source` (`config` / `shared-instructions` / `None`), `contract`, `problems`; `phase(id)`, `open_questions_for(id)`, `check_contract()` (raises `ContractError`: "repo not yet migrated" or unknown version) |
| `Phase` | `id`, `name`, `model` (cell text), `alias` (`opus`/`sonnet`/`haiku`/`fable` or `None`), `depends_on`, `status` (`Status`), `prompt` (path), `gate` (`Gate`), `gate_source` (`column`/`prompt`/`inferred`/`default`), `line`; `require_alias()` raises `UnknownModel` (R2) |
| `OwnerQuestion` | `id` (string, e.g. `"6"`, `"Q3"`), `question`, `status` (cell), `needed_by` (phase IDs); `open` iff the Status cell starts with `Open`, any case, ignoring leading `**` (contract §3) |
| `Eligibility` | `next` (lowest ⬜ with deps ✅ and no open question needing it), `resume` (🔄 phases), `reasons` (every other phase → why). Gate is not considered here; the supervisor applies it (ADR-0013). |
| `LiveState`, `Worktree`, `Drift` | branches → phase ID; phase worktrees (`path`, `branch`, `phase`, `last_commit` ISO, `uncommitted`); drift `kind` and `detail` |

Errors vs problems: anything that makes the plan untrustworthy (malformed or duplicate ID, short row, missing column, unreadable status, unknown Gate, invalid config) raises `PlanError` with the line number; softer inconsistencies go to `Plan.problems` (ADR-0013). Phase IDs sort by `(number, letter)`. `phx plan` (`cli.plan_report`) shows all of it, as text or `--json`.

Runtime state lives outside the repo in `~/.local/state/phx/<repo-name>/` (`run.jsonl`, `state.json`, `sessions/`). Per-repo overrides: `<repo>/.phx/config.toml`.

## Control flow of `phx run`
```
phx run <repo>
  │  lock (machine-wide + per-repo)
  ▼
parse plan on main ──► pick next eligible phase (status ⬜, deps ✅, gate)
  │
  ▼
ai-provider run -p "/phase NN --auto"   (model alias from the plan; fresh session)
  │        └─ usage limit? ─► wait, notify, resume same session
  ▼
classify exit (done / blocked / limit / failure)
  │
  ▼
verify independently (plan status on main, merge, tests, docs)
  │        └─ failed? ─► recover / retry / block with the question recorded
  ▼
gate (auto continues · review/owner pauses) ─► next phase, or stop when none remain
```

## Interface with phase sessions
PHX and a phase session talk only through the repo and one line of output, defined in [PHX_AUTO_MODE_CONTRACT.md](PHX_AUTO_MODE_CONTRACT.md) (contract version 1, Phase 03):
- **In:** `/phase NN --auto` plus `PHX_AUTO=1`. The command must carry `PHX-CONTRACT: 1`.
- **Out:** the plan on `main` (`✅`, or `⛔` with an Owner question whose Status starts with `Open`), the phase branch/worktree, and a final `PHX-RESULT: {json}` line with status `complete`, `blocked` or `refused`. The line is a hint; verification decides.
- **Locks:** `${XDG_RUNTIME_DIR}/phx/phx.lock` and `<repo-name>.lock`, held with `flock` for the supervisor's life, so a manual `/phase` can see a running supervisor and stop.

See [PHX_SPECIFICATION.md](PHX_SPECIFICATION.md) for the requirements behind each step and [PHX_DECISIONS.md](PHX_DECISIONS.md) for the decisions.
