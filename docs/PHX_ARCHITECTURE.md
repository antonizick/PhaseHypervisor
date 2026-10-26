# PHX Architecture

> Skeleton from Phase 01, Phase 02 modules documented below. Each later phase fills in its components; keep this file in sync with the code.

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
| `paths.py` | `default_state_root()` (`$XDG_STATE_HOME/phx`, else `~/.local/state/phx`), `state_dir(repo)`, `sessions_dir()`, and `load_config(repo)` reading `<repo>/.phx/config.toml` into the frozen `Config` dataclass (`test_command`, `max_budget_usd`, `poll_interval_s`, `limit_poll_interval_s`, `triage`). Unknown keys or wrong types raise `ValueError`. |
| `logging.py` | `EventLog(path)`: one redacted JSON object per line (`ts` as `YYYY-MM-DD HH:MM:SS TZ`, `epoch`, `event`, `phase`, `reason`, extra fields), a single `O_APPEND` write plus `fsync` per record (safe for concurrent appenders), optional human-readable stderr mirror. |
| `redact.py` | `redact()` / `redact_text()`: `sk-or-…`, `sk-ant-…`, `ANTHROPIC_AUTH_TOKEN=…`, `ANTHROPIC_API_KEY=…`, `Authorization: Bearer …`, `ghp_`/`gho_`/`github_pat_` tokens, in strings and nested JSON. Every `EventLog` write goes through it. |

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

See [PHX_SPECIFICATION.md](PHX_SPECIFICATION.md) for the requirements behind each step and [PHX_DECISIONS.md](PHX_DECISIONS.md) for the decisions.
