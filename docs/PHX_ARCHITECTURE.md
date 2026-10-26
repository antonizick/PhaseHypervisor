# PHX Architecture

> Skeleton from Phase 01; Phase 02, 04, 05, 06 and 07 modules documented below. Each later phase fills in its components; keep this file in sync with the code.

## Components
| Component | Module (planned) | Phase | Role |
|---|---|---|---|
| CLI | `src/phx/__main__.py`, `cli.py` | 02 | argparse entry point `phx` |
| State and logging | `paths.py`, `logging.py`, `redact.py` | 02 | state dirs, JSONL log, secret redaction |
| Plan parser | `plan.py` | 04 | rows, IDs, ordering, deps, status, model alias, gates, owner questions, drift |
| Session runner | `runner.py`, `classify.py` | 05 | launch via `ai-provider run -p`, stream-json capture, exit classification |
| Verifier and recovery | `verify.py`, `recover.py`, `triage.py` | 06 | independent post-phase checks, blocked-status repair, retry/resume |
| Supervisor | `supervisor.py`, `locks.py`, `state.py`, `notify.py`, `vault.py`, `detach.py` | 07 | `phx run / status / resume / stop / log / answer`, locks, state, waits, notifications, detached runs, vault summary |
| Preflight | `preflight.py` | 08 | one interactive question sweep before a hands-off run |

## Phase 02 modules (built)
| Module | Role |
|---|---|
| `cli.py`, `__main__.py` | argparse entry point. Global flags `--state-dir`, `-v/--verbose`, `--version`. The `COMMANDS` table maps each subcommand to its help text and the phase that implements it; stubs print `not implemented yet (Phase NN)` and exit 2. |
| `paths.py` | `default_state_root()` (`$XDG_STATE_HOME/phx`, else `~/.local/state/phx`), `state_dir(repo)`, `sessions_dir()`, and `load_config(repo)` reading `<repo>/.phx/config.toml` into the frozen `Config` dataclass (`test_command`, `max_budget_usd`, `poll_interval_s`, `limit_poll_interval_s`, `triage`, from Phase 05 `idle_timeout_s`, `wall_timeout_s`, from Phase 06 `test_timeout_s`). Unknown keys or wrong types raise `ValueError`. `parse_config(text, source)` parses TOML text from anywhere (Phase 04 reads it from `main`). |
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
  (permission_mode, extra_args: only for the tool-less triage session, Phase 06)
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

## Phase 06: verifier and recovery (`verify.py`, `recover.py`, `triage.py`, built)
```
capture_baseline(repo) ──► Baseline(main_head, dirty)          taken by the supervisor before each launch
run_session(...) ──► SessionOutcome                              (Phase 05)
handle_outcome(repo, outcome, state, log, recoveries, baseline, config) ──► Decision
  auth_error / provider_error ─────────────────────────────────► decide (no verification)
  row 🔄 and (result line "blocked" or wip(phase-NN): blocked commit) ─► repair_blocked  (the only write)
  verify_phase(repo, NN, classification, baseline) ──► Verdict    reads main; tests in a temp clone
  live_sessions(repo, NN)      only before a retry: claude processes in the worktree or main checkout
  decide(NN, classification, verdict, session_id, recoveries, live) ──► Decision
  triage.summarize(...)        haiku, tool-less, on a pause after blocked / needs_review / failed
  run.jsonl                    verify · repair / repair_skipped · triage · decision
check_resumable(repo, NN) ──► Resumability   R14: before resuming a 🔄 phase at start-up
```

**Checks** (`Check(name, status pass|fail|skip, evidence, required)`), all read from `main` and the main checkout without writing:

| Row on `main` | Checks |
|---|---|
| `✅` | `branch_merged`, `branch_deleted`, `worktree_removed`, `phase_log` (latest `✅` entry, Timeline first), `pushed` (optional, local `origin/main` ref), `tests` (temp clone of `main`) |
| `⛔` | `question_recorded` (an open question names the phase), `phase_log` (latest `⛔` entry, Timeline with a `blocked` interval), `branch_kept` (optional) |
| `🔄` | `work_in_progress` (optional: worktree, last commit, uncommitted count) |
| any, `refused` session | `main_unchanged` (optional, against the baseline); no tests |
| always | `status`, `main_checkout` (on `main`), `main_clean` (no new uncommitted files since the baseline) |

**Verdict outcome:** `needs_review` if the `PHX-RESULT` line disagrees with the repo (status, phase ID, `merged`, `pushed`, question IDs; `refused` with the row `🔄` or `main` moved); else `failed` if a required check failed; else the row's state: `complete`, `blocked`, `in_progress`, `not_started`. `missing` state (plan unreadable, phase not in the table) is always `failed`.

**Test commands** (ADR-0015): `parse_command` splits on `&&` into `cd DIR` and word steps with `NAME=value` prefixes, quotes and globs (`**` recursive); anything else is `UnsupportedCommand`. `run_command` runs each step with an argument list in the clone; a missing path is `skip` for a shared-instructions command (ADR-0013), `fail` for a `.phx/config.toml` one.

**Decision table** (`recover.decide`, first matching row wins; `rule` is logged):

| # | Session class | Verdict | Action | Rule |
|---|---|---|---|---|
| 1 | `auth_error` | not verified | pause, notify | `auth_error` |
| 2 | `provider_error` (any kind) | not verified | pause, notify; no retry that could burn credit | `provider_error` |
| 3 | any other | `needs_review` | pause, notify, report with both sides | `needs_review` |
| 4 | `refused` | any | pause with the agent's reason; no repair | `refused` |
| 5 | any other | `failed` | pause with the report | `verification_failed` |
| 6 | `complete`, `no_result`, `timeout`, `crash`, `usage_limit` | `complete` | next phase | `complete` |
| 7 | `blocked`, `no_result`, `crash`, … | `blocked` (after the `⛔` repair if needed) | pause, notify, question IDs | `blocked` |
| 8 | `usage_limit` | `in_progress` / `not_started` | wait (Phase 07), then `--resume` the same session with the continue prompt | `usage_limit` |
| 9 | `no_result` | `not_started` | pause | `no_result_unclaimed` |
| 10 | `timeout` / `crash` / `no_result` | `in_progress` / `not_started`, live Claude process | pause ("another session is running phase NN" / "open in the main checkout") | `live_session` |
| 11 | same | same, `recoveries == 0` | `--resume <session>` with the continue prompt | `retry_resume` |
| 12 | same | same, `recoveries == 1` (or no session ID) | fresh `/phase NN --auto` | `retry_fresh` |
| 13 | same | same, `recoveries >= 2` | pause | `retries_exhausted` |
| 14 | no verdict / anything else | | pause | `unverified` / `unexpected` |

`Decision`: `action` (`next_phase`, `pause`, `wait`, `resume_session`, `fresh_session`), `phase`, `reason`, `rule`, `notify`, `session_id` and `prompt` for the next launch, `reset_at`, `question_ids`, `verdict`, `repair` (commit hash), `summary` (triage), `live`.

**`⛔` repair** (`repair_blocked`): main checkout on `main`, plan file clean and equal to `main`, row `🔄`; rewrites only the Status cell (`plan.set_status_cell`), commits only the plan file (`chore(plan): phase NN blocked (recorded by phx)`), pushes if `origin` exists. Otherwise `repair_skipped` with the reason.

**Triage** (`triage.summarize`): `haiku`, `--tools ""`, `--permission-mode default`, `--max-turns 1`, cwd = state dir, no `PHX_AUTO`; prompt = verdict report + the phase's last messages from its redacted transcript, marked as data; answer redacted and clipped to 150 words; transcript `sessions/<phase>-triage-<n>.jsonl`; cost and tokens in the `triage` event. Best effort: never raises.

## Phase 07: supervisor (`supervisor.py`, `locks.py`, `state.py`, `notify.py`, `vault.py`, `detach.py`, built)
```
phx run <repo>                       (cli._cmd_run: S1 checks, signal handlers → request_stop)
  │  --detach ─► detach.detach: systemd-run --user --unit phx-<repo> --collect … -- python -m phx run …
  ▼
Supervisor.run
  RunLock: $XDG_RUNTIME_DIR/phx/phx.lock + <repo-name>.lock (flock, JSON body, contract §8)
  state.json: refuse if paused (unless phx resume); carry sessions, wait, recoveries from the last run
  loop ─────────────────────────────────────────────────────────────────────────────┐
    load_plan + check_contract (first round: config from main, test-command warnings) │
    _select: pending wait → 🔄 (check_resumable; --resume recorded session | fresh) │
             → ⛔ (pause if a question is open | fresh) → next_eligible → finished/pause
    Gate owner → pause · require_alias → pause on unknown model                      │
    _run_phase:                                                                       │
      capture_baseline → run_session(cancel=stop_event, on_start=record session ID)   │
      stopped? → end (phase stays 🔄)                                                 │
      handle_outcome → Decision                                                       │
        next_phase ─► notify, Gate review / --pause-after / --until / --max-phases ───┘
        pause      ─► end (notify: blocked + triage summary | failed | paused)
        wait       ─► _wait (wall-clock, 60 s steps; provider check every poll_interval_s;
                      probe at wake) ─► run_session(resume=session, continue prompt)
        resume_session / fresh_session ─► recoveries += 1, launch again
  _finish: state.json, run_end, notification, vault.append_summary, exit 0/1/3/4
```

| Module | Role |
|---|---|
| `locks.py` | `RunLock` (machine-wide `phx.lock` then `<repo-name>.lock`, exclusive `flock`, 2 s retry, one-line JSON body `pid`/`repo`/`started`/`phase`/`unit`, `update(phase=…)`, release truncates); `running(repo)` reads a held lock (shared probe, like the contract's shell check); `main_checkout`, `repo_name` (`git rev-parse --git-common-dir`). Files are never deleted. |
| `state.py` | `RunState` (run ID, status `running`/`waiting`/`paused`/`stopped`/`finished`/`failed`, PID, unit, phase, attempt, recoveries, session ID, last class, provider, heartbeat, `Wait`, `Pause`, `sessions` phase → last PHX session, per-phase `PhaseTotals` sessions/tokens/cost/wait/outcome, totals, completed phases, end reason); `save_state` writes temp + fsync + rename, mode 0600. |
| `supervisor.py` | `Supervisor(repo, options=RunOptions(pause_after, max_phases, until, dry_run, resume), state_root, env, clock, notifier, unit, proc_root, exclude, triage, vault)`. `run()` → exit code. `request_stop()` from signal handlers. `Clock` protocol (`now`, `sleep(seconds, stop)`) so tests run waits on a fake clock. Dry run simulates completions without lock, state or launches. |
| `notify.py` | `Notifier.send(Note)`: `notify-send --app-name=phx --urgency=… --hint=boolean:suppress-sound:true`; skipped (logged) without display, bus or binary. Builders: `phase_complete`, `blocked`, `waiting`, `provider_switch`, `verification_failed`, `paused`, `finished`. |
| `vault.py` | `note_path` (CLAUDE.md on `main`: "Obsidian project note \`…\`"), `summary_line`, `append_line` (end of `## Log`, `updated:`), `append_summary` (atomic write; skipped and logged when no note or no Log section). |
| `detach.py` | `unit_name`, `detach_argv` (env allowlist, `KillMode=mixed`, `TimeoutStopSec=90`, `PHX_UNIT`), `detach` (waits up to 10 s for the lock). |
| `cli.py` | `run`/`resume`, `status` (`status_report`, all repos without an argument), `stop` (SIGTERM + wait for the lock), `log` (`-f`, `--json`, `-n`), `answer` (`answer_question`, `plan.set_question_status`). |

Phase 05/06 additions used here: `run_session(cancel=…, on_start=…)`; `classify(timed_out="stopped")` → `timeout` kind `stopped`; `plan.set_question_status`.

Test doubles: `tests/fakes/fake_agent.py` makes the fake `claude` a scripted phase agent (`PHX_FAKE_AGENT=<scenario.json>`: per phase a list of actions `complete`, `block:Q`, `limit[:s]`, `crash`, `hang`, `refuse`, `noop`; `probe` and `triage` keys) that claims, works in a worktree, merges or blocks for real; `tests/fakes/notify-send` records calls; `PHX_FAKE_PROVIDER_FILE` lets a test flip `ai-provider get` mid-wait.

## Interface with phase sessions
PHX and a phase session talk only through the repo and one line of output, defined in [PHX_AUTO_MODE_CONTRACT.md](PHX_AUTO_MODE_CONTRACT.md) (contract version 1, Phase 03):
- **In:** `/phase NN --auto` plus `PHX_AUTO=1`. The command must carry `PHX-CONTRACT: 1`.
- **Out:** the plan on `main` (`✅`, or `⛔` with an Owner question whose Status starts with `Open`), the phase branch/worktree, and a final `PHX-RESULT: {json}` line with status `complete`, `blocked` or `refused`. The line is a hint; verification decides.
- **Locks:** `${XDG_RUNTIME_DIR}/phx/phx.lock` and `<repo-name>.lock`, held with `flock` for the supervisor's life, so a manual `/phase` can see a running supervisor and stop.

See [PHX_SPECIFICATION.md](PHX_SPECIFICATION.md) for the requirements behind each step and [PHX_DECISIONS.md](PHX_DECISIONS.md) for the decisions.
