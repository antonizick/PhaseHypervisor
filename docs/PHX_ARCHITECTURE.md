# PHX Architecture

> Skeleton from Phase 01; Phase 02, 04 and 05 modules documented below. Each later phase fills in its components; keep this file in sync with the code.

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
| `paths.py` | `default_state_root()` (`$XDG_STATE_HOME/phx`, else `~/.local/state/phx`), `state_dir(repo)`, `sessions_dir()`, and `load_config(repo)` reading `<repo>/.phx/config.toml` into the frozen `Config` dataclass (`test_command`, `max_budget_usd`, `poll_interval_s`, `limit_poll_interval_s`, `triage`, and from Phase 05 `idle_timeout_s`, `wall_timeout_s`). Unknown keys or wrong types raise `ValueError`. `parse_config(text, source)` parses TOML text from anywhere (Phase 04 reads it from `main`). |
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

## Phase 05: session runner and exit classifier (`runner.py`, `classify.py`, built)
```
run_session(repo, state, phase, prompt, alias, log, config, resume?) ──► SessionOutcome
  find_launcher       ai-provider on PATH → ~/.local/bin/ai-provider ($HOME of the given env) → claude (logged warning, R7)
  provider_snapshot   `ai-provider get`; on OpenRouter `ai-provider env` parsed in memory against an allowlist → mapped model
  build_argv          <launcher> -p <prompt> --model <alias> --permission-mode bypassPermissions
                      --output-format stream-json --verbose (--session-id <uuid> | --resume <id>)
                      [--max-turns N] [--max-budget-usd X  (OpenRouter + config only, R9)]
  build_env           + PHX_AUTO=1, − ANTHROPIC_MODEL
  Popen               cwd = repo main checkout, own process group, stdin /dev/null
  stream loop         stdout lines → redacted → sessions/<phase>-<n>.jsonl; JSON events → on_event (heartbeat), last 20 kept,
                      `result` remembered; stderr → redacted 50-line tail
  timeouts            idle (no event for idle_timeout_s) / wall (wall_timeout_s) → SIGTERM group, SIGKILL after 10 s
  classify(...)       → Classification;  Usage.from_result(result) → tokens, cost, durations, per-model usage
  run.jsonl           `launch` (argv, cwd, session, transcript, provider, mapped model, budget, timeouts),
                      `launcher_fallback`, `timeout`, `session_end` (class, reason, reset_at, kind, result line, tokens, cost)
probe(state, log) ──► Classification   `-p ok --model haiku --max-turns 1`, cwd = state dir, no PHX_AUTO,
                                        clean answer = complete (R8)
```

`classify(exit_code, result, last_events, stderr_tail, *, timed_out, provider, expect_result_line, now)` is pure. Priority (ADR-0014): timeout → when the session ended in error: rejected `rate_limit_event` / `You've hit your …` → `usage_limit` (reset from `resetsAt`, else `parse_reset` of the text, local aware datetime) → `rate_limit`/429 (`usage_limit` without reset on Pro, `provider_error(rate_limited)` on OpenRouter) → `auth_error` → `provider_error` (`budget`, `credits`, `server`, `invalid_request`, `unknown`) → `crash` for other error subtypes; when it ended cleanly: the `PHX-RESULT` line (`parse_result_line`, contract §6, last line wins, malformed = none) → `complete`/`blocked`/`refused`, else `no_result`; no `result` event: `auth_error` if stderr says so, else `crash`.

| Class | Meaning | Typical next step (Phases 06/07) |
|---|---|---|
| `complete` / `blocked` / `refused` | the session's own result line | verify (R6) |
| `no_result` | ended cleanly, no valid line | verify |
| `usage_limit` | Pro window exhausted; `reset_at` if known, `kind` = limit type | wait, probe, `--resume` (ADR-0006) |
| `auth_error` | login expired / bad key | notify Nick, stop |
| `provider_error` | `credits`, `rate_limited`, `server`, `budget`, `invalid_request`, `unknown` | retry or stop by kind |
| `timeout` | `idle` or `wall` | recover/resume |
| `crash` | no result event, signal, `error_during_execution`, max turns | recover/resume |

Test doubles: `tests/fakes/claude` replays a fixture (`PHX_FAKE_STREAM`, `PHX_FAKE_EXIT`, `PHX_FAKE_DELAY`, `PHX_FAKE_HANG`, `PHX_FAKE_STDERR`, `PHX_FAKE_IGNORE_TERM`, `PHX_FAKE_ARGV_LOG`) and enforces `--verbose`; `tests/fakes/ai-provider` answers `get` (`PHX_FAKE_PROVIDER`), `env` (`PHX_FAKE_ENV`) and `run` (execs the fake claude). Put `tests/fakes` first on the child's `PATH` and set its `HOME` to a temp dir. Fixtures and their provenance: `tests/fixtures/streams/README.md`.

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
classify exit (complete / blocked / refused / no_result / usage_limit / auth / provider / timeout / crash)
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
