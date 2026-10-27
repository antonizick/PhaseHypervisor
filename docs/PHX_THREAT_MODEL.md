# PHX Threat Model

**Written:** 2026-10-26 23:34 CDT (Phase 11). **Scope:** PhaseHypervisor at the end of Phase 11, on Nick's single-user Omarchy machine. Read with `SECURITY.md` (the baseline S1 to S5) and the spec Amendments (§4).

## 1. System and trust boundaries

PHX is a deterministic Python program (no LLM) that runs as Nick's user. It reads a phased-project repo, starts headless Claude Code sessions through `ai-provider run` with `--permission-mode bypassPermissions`, checks each phase itself and writes logs and state. Claude also runs in two smaller sessions: a tool-less one-turn haiku **triage** session, and the interactive opus **preflight** session, which uses Nick's normal permissions.

| Asset | Where |
|---|---|
| API credentials | `~/.config/ai-provider/openrouter.key`, Claude Code's own login, `ANTHROPIC_AUTH_TOKEN` in `ai-provider`'s environment |
| Nick's repos, their `main` history and GitHub remotes | `~/Work/*` |
| Nick's home directory and vault | `~/`, `~/Documents` |
| Money | OpenRouter credit (Pro is flat-rate) |
| PHX's decision record | `~/.local/state/phx/<repo>/` (`run.jsonl`, `state.json`, `sessions/`) |

**Untrusted input.** PHX parses all of the following as data, never as code:
- plan rows and owner-question cells;
- phase prompts;
- `CLAUDE.md` and `.phx/config.toml` on `main`;
- the stream-json output of every session (the agent's text and tool output);
- git branch and worktree names;
- `/proc` entries.

Any of these can be written by an agent. An agent can be steered by prompt injection: text in a dependency, a web page, a fetched issue or a file in the repo.

**Trusted input:**
- Nick's command line and environment (`PHX_WORK_ROOT`, `PHX_VAULT_ROOT`, `PATH`);
- the `ai-provider` script;
- the Claude Code binary.

**The central fact.** A phase session already runs as Nick, with bypassed permissions, in Nick's repo. Anything an injected agent can make *PHX* do, the agent could usually do directly. PHX's job is therefore narrower:
- not to **widen** that power;
- not to **leak** what the agent cannot see (keys PHX handles);
- not to **launder** an agent's action into something that looks deliberate (a PHX commit, a deferred write);
- to keep the **human checkpoints** (S5, Gates, block-with-question) intact.

## 2. Rating

**Likelihood:** L (needs an unusual mistake or a determined injected agent), M (plausible in normal use), H (expected).

**Impact:** L (confusion, a paused run), M (lost work, one wrong commit, a few dollars), H (secret disclosure, destroyed data outside the repo, a public repo or release without Nick).

**Risk** is the higher of the two when either is H, otherwise their middle. **Residual** is the risk after the mitigation.

## 3. Threats

| # | Threat | L | I | Risk | Mitigation (where) | Test | Residual |
|---|---|---|---|---|---|---|---|
| T1 | **Bypassed permissions:** a phase agent, possibly prompt-injected, runs destructive commands, touches other projects, or publishes | M | H | H | Accepted by design (ADR-0003); bounded by S1 (repos under `$PHX_WORK_ROOT` only, never root: `Supervisor.run`, `cli._cmd_run`), the risk-stop rule in every repo's `CLAUDE.md` (block-with-question in auto mode), S5 (public, release and force-push always stop for Nick; a preflight never pre-approves them), Gates `review`/`owner`, one phase at a time, and independent verification after every phase (R6) | `test_repo_outside_work_root_refused`, `test_owner_gate_is_never_started`, `test_review_gates_pause_and_resume`, contract tests | **M, accepted.** The agent has Nick's user rights for the length of a session. Use Gate `review`/`owner` for phases that touch anything Nick cannot undo |
| T2 | **Prompt injection steering a phase agent** through repo text, plan rows, phase prompts or tool output | M | H | H | Same as T1. Plus: the result line is only a hint, and PHX believes the repo (R6, `_disagreements` → `needs_review`); a forged `PHX-RESULT` cannot complete a phase whose row, merge, Phase Log or tests disagree | `test_verify.py` (result vs repo disagreements), `test_refused_session_pauses` | **M, accepted** (inherent to agents with tools) |
| T3 | **Injection steering the triage session** | M | L | L | No tools (`--tools ""`), one turn, default permission mode, cwd in the state dir, input redacted, run text fenced as data, and the fence markers in that text defanged so it cannot close its block (Phase 11). Output is clipped to 150 words and only ever shown to Nick | `test_prompt_marks_the_run_text_as_data`, `test_run_text_cannot_close_its_data_block` | **L.** At worst a misleading summary. The verification report beside it is PHX's own |
| T4 | **Injection steering the preflight session.** Its prompt quotes clipped lead sentences and question cells from `main` (ADR-0017) | L | M | M | Interactive with Nick present, Nick's normal permissions (not bypassed); quotes are one line between « » and marked as data, with « » inside the text replaced so it cannot close the quote (Phase 11); `--record` commits only `.phx/preflight.json` and refuses a symlinked file or `.phx/` (Phase 11 security review); publishing is never pre-approved | `test_quoted_repo_text_cannot_close_its_quote`, `test_preflight_record_refuses_symlinks`, `test_mm3_acceptance_publication_caught` | **L** |
| T5 | **PHX parsing hostile plan text (S3)** | M | M | M | `plan.py` reads `main` through `git show` with argument lists and matches with anchored regexes; phase IDs are validated (`\d{2}[a-z]?`), models map to a fixed alias set, unknown models pause. Nothing from a plan reaches a shell. Git refs are built as `refs/heads/…` or `main:<path>` with `--` separators | `test_plan.py` (malformed IDs, legacy and lettered plans, 100 % coverage) | **L** |
| T6 | **Test-command interpreter (ADR-0015)** | M | M | M | No shell. `&&`, `cd`, `NAME=value`, quotes and globs only; pipes, redirects, `;`, `\|\|`, `$`, backticks, `~` and newlines are refused. `cd` targets and glob matches must resolve (symlinks followed) inside the temporary clone. The clone is of `main`, never Nick's checkout. Keys and `PHX_AUTO` are stripped from the environment. A timeout kills the command's **whole process group**, and `phx stop`/Ctrl+C reach it too (Phase 11). `--dry-run` runs the test command only for repos inside the S1 work root. The command itself still runs repo code (`make check`), which the agent wrote: same power as T1, no escalation | `test_verify.py` (quoting, globs, `cd` escapes, refusals), `test_timeout_kills_the_whole_process_group`, `test_stop_during_verification_pauses_with_a_clear_reason`, `test_dry_run_test_check_respects_the_work_root` | **L** |
| T7 | **Secrets in logs and transcripts:** a key in tool output, stderr, `ai-provider env` output or a notification | M | H | H | Every record and transcript line passes `redact.py`. It covers `sk-or-`, `sk-ant-` (including OAuth `sk-ant-oat…`), `gh[pousr]_`, `github_pat_`, bearer headers, and `NAME=value` / `NAME: value` / `"NAME": "value"` / escaped-JSON forms for any `*TOKEN`, `*API_KEY`, `*SECRET` or `*PASSWORD` name, including a name right after an escaped `\n` (Phase 11). Redaction keeps JSON valid and is idempotent. `ai-provider env` is parsed by allowlist and the key is never stored. Files are 0600, the lock dir is 0700 | `test_redact.py`, `test_redaction_audit.py` (synthetic leaks found; a full run with a leaking agent, stderr and provider audits clean), `tests/redaction_audit.py` run on all Phase 10 state: **26 files, 2,081 lines, 0 secrets** | **M.** A secret with no known shape and no telling variable name (a bare password echoed by a tool) is not recognisable. Claude Code's own transcripts under `~/.claude/projects/` are outside PHX |
| T8 | **Lock and state races:** two supervisors, a manual `/phase` racing PHX, or a crash mid-write | M | M | M | Machine-wide and per-repo `flock`, held for the supervisor's life and released by the kernel on death. Manual `/phase` step 0 checks the repo lock and is **fail-closed** (Phase 11, ADR-0020): a denied or failed check stops the command. `state.json` is written via temp file, fsync and rename; leftover temp files are never read and are removed on the next save. `phx answer` and the `⛔` repair commit only when `main` is checked out and the plan file is clean and equal to `main` | `test_lock_contention`, `test_phx_stop_command_against_a_real_process`, `test_kill_9_mid_phase_then_resume`, `test_kill_9_mid_state_write_keeps_the_last_good_state`, `test_unreadable_state_starts_fresh` | **L.** Two windows remain: `phx answer` checks the lock and then commits, and a manual `/phase` can pass step 0 just before a supervisor starts. Each needs Nick to start both within about a second; git's `index.lock` and the claim protocol's checks catch the second writer |
| T9 | **Live-session guard heuristic (ADR-0019)** misses a rival session, or blocks needlessly | M | M | M | A process in the phase worktree always counts; a headless `/phase` always counts. A main-checkout session counts when the phase shows activity after the session started and after PHX's last session ended. Activity now includes the phase's **claim or resume commit on `main`** (Phase 11), so a session that claimed by hand but has not yet branched or written is seen | `test_claim_commit_alone_counts_as_activity`, `test_idle_main_checkout_session_is_not_a_rival`, `test_pty_host_and_start_time` | **L.** Not seen: a session started *after* the last activity that then works on the phase without committing or writing. Its first write makes it visible on the next check. Also accepted: after `kill -9` of the supervisor, the orphaned session may die on its next stdout write (broken pipe) rather than finish; either way the next `phx resume` sees it or resumes the recorded session |
| T10 | **Signals and crashes mid-write** (ADR-0016) | M | M | M | SIGTERM, SIGINT and SIGHUP only set a stop flag, so a write in progress finishes. SIGKILL cannot interrupt the atomic rename halfway. A truncated `state.json` (not from PHX) starts a fresh state that resumes the phase with a fresh `/phase NN --auto` | `test_sigterm_in_the_foreground_stops_cleanly`, `test_kill_9_*`, `test_unreadable_state_starts_fresh` | **L** |
| T11 | **Full disk or vanished state dir** | L | M | M | Since Phase 11: `run.jsonl` records that cannot be written go to stderr (the journal when detached); a failed `state.json` write is logged once and the run keeps its state in memory; a failed transcript write is logged and the session continues; the vault temp file is cleaned up. A failed final save is retried and then reported loudly, because it may carry a pause. A partial log record is truncated away | `test_full_state_disk_does_not_stop_the_run`, `test_state_write_recovers_after_space_returns`, `test_event_log_short_write_goes_to_stderr`, `test_short_log_write_leaves_no_fragment`, `test_final_state_save_failure_is_shouted` | **L** |
| T12 | **`systemd-run` environment exposure** | L | H | M | `--detach` passes only `detach.ENV_ALLOWLIST`: paths, locale, display and bus addresses, `PHX_WORK_ROOT`, `PHX_VAULT_ROOT`. No `*_TOKEN` or `*_KEY` reaches the unit; `ai-provider` supplies keys to the session itself. The unit runs as Nick (`--user`) | `test_detach_stop_and_allowlist` (a fake `systemd-run` records the `--setenv`s; a planted `ANTHROPIC_AUTH_TOKEN` and `SECRET_THING` are absent), `test_detach_argv` | **L** |
| T13 | **The `phx answer` write path** (`cli.answer_question`) | L | M | L | Refuses while a supervisor holds the lock, off `main`, with a dirty or diverged plan file, or for a question that is not open (unless `--force`). It escapes `\|` and collapses newlines, edits one cell and commits only the plan file. If the commit fails (for example `index.lock` is held), it restores the file's text itself, because `git checkout` fails then too (fixed in Phase 11) | `test_answer_refusals`, `test_git_index_lock_blocks_answer_cleanly` | **L** |
| T14 | **S1 guard and its `PHX_WORK_ROOT` override** | L | M | L | The repo's main checkout (resolved) must be under the root; root UID refused. The override is an environment variable (trusted, used for tests and pilots) | `test_repo_outside_work_root_refused` | **L** |
| T15 | **Stale lock files** left in `$XDG_RUNTIME_DIR/phx/` by design | H | L | L | A lock file is "held" only while a process holds the `flock`. Contents are trusted only then. The directory is per-user, mode 0700, on tmpfs (cleared at logout/reboot) | `test_phx_stop_command_against_a_real_process` (stale after stop), `test_kill_9_mid_phase_then_resume` | **L** |
| T16 | **Git operations on the wrong repo or branch** | L | M | M | PHX itself commits only three things: the `⛔` repair, `phx answer` and `preflight.json`. All three require the main checkout on `main` and the file clean and equal to `main`, and commit only that path. A failed commit restores the file (Phase 11). Verification never touches Nick's checkout (it uses a temporary clone); the baseline of pre-existing dirty files is recorded. Repo identity comes from `git rev-parse --git-common-dir` | `test_git_index_lock_blocks_repair_cleanly`, `test_verification_never_touches_main_checkout`, `test_push_timeout_in_repair_is_logged` | **L** |
| T17 | **Vault write path from repo text.** `CLAUDE.md` on `main` names the note PHX appends to | M | M | M | Since Phase 11: the path must be absolute, end in `.md` and resolve (symlinks followed) inside `$PHX_VAULT_ROOT` (default `~/Documents`). PHX writes only `updated:` and one Log line, via temp file and rename, and leaves a note without `## Log` alone | `test_vault_path_confined_to_the_vault_root`, `test_vault_summary_appended` | **L** |
| T18 | **Runaway spend on OpenRouter** | L | M | M | One phase at a time. Wall (6 h) and idle (30 min) timeouts. The crash ladder is at most one `--resume` plus one fresh session, then a pause. Auth and provider errors pause without retry ("no retry that could spend credit"). PHX never switches provider by itself (ADR-0006). `max_budget_usd` in `.phx/config.toml` becomes `--max-budget-usd` on OpenRouter. Nick's OpenRouter key limits are the primary control | `test_crash_ladder_gives_up`, `test_classify.py` (402/429/budget), `test_runner.py` (budget flag only on OpenRouter) | **L.** Measured: an opus phase cost about $6 on Pro (Phase 10). A long plan on OpenRouter without a cap is Nick's choice |
| T19 | **A malicious or broken `ai-provider` on `PATH`** | L | H | M | Trusted by design (spec R7): `ai-provider` is optional and is whatever its user installed (for the author, a personal provider switch); placing a program by that name on one's own `PATH` is that user's trust decision, the same as for `claude`. It is found first on `PATH`, else `~/.local/bin`, else PHX falls back to `claude` (Phase 12a docs). PHX passes it argument lists only, never a shell. It parses `get` and `env` output strictly (allowlist, `shlex`), with 15 s timeouts; failures yield provider `unknown`. A broken launcher fails the session (classified `crash`), not PHX. A `PATH` writable by others would be a host problem outside PHX's scope | `test_runner.py` (snapshot errors, timeouts, launcher fallback), `test_detach_reports_systemd_run_failures` | **M, accepted** (same trust as `claude` itself) |
| T20 | **Notification injection:** triage or reason text in `notify-send` | M | L | L | Argument list, never a shell. Fixed title prefix. Text is redacted. Notifications are always silent and never spoken | `test_supervisor_units.py` (notify) | **L** |

**No unmitigated High risk remains.** T1 and T2 are High before mitigation. They are inherent to bypass-permission agents and are accepted on record (ADR-0003), with the residual held at M by S1, S5, Gates and independent verification. T7 drops to M after redaction.

## 4. Changes made by this review (Phase 11)

- **Redaction (T7):**
  - JSON-quoted and generic secret assignments are now covered;
  - so is a name right after an escaped newline;
  - quotes are kept, so redacted lines stay valid JSON, and redacting twice changes nothing;
  - the redaction audit script and test were added.
- **Full disk (T11):** a full state disk no longer ends the run or kills the session.
- **Rollback on failed commits (T13, T16):** a failed commit no longer leaves Nick's `main` checkout with an uncommitted plan edit.
- **Write confinement (T4, T17):**
  - the vault note must resolve inside `$PHX_VAULT_ROOT`;
  - `preflight --record` refuses a symlinked file or directory.
- **Triage and preflight data fencing (T3, T4):** repo text cannot close its data block or quote.
- **Test commands (T6):** a timeout kills the whole process group.
- **Live-session guard (T9):** the claim commit counts as phase activity.
- **Manual `/phase` step 0 (T8):** now fail-closed in all five repos, the skill and the playbook (ADR-0020).

## 5. Review and scanners

- **Full-codebase reviews:**
  - `/security-review`: 2 Medium findings, both fixed (T7 escaped newlines, T4 symlinked record);
  - `/code-review high`: 10 findings, all fixed (`fbce26f`). The security-relevant ones:
    - the dry-run test check ran before the S1 work-root check;
    - unquoted secret values were cut at `,`, `;` or `}`, leaving the rest in clear text;
    - a failed final save could lose a pause.
- **Pre-commit scanners on every commit:** `detect-secrets` and `detect-private-key`.
- **Redaction audit:** `uv run python tests/redaction_audit.py ~/.local/state/phx` (exit 0 clean, 1 leak). To include real state in the test suite, run `PHX_AUDIT_DIR=~/.local/state/phx uv run pytest tests/test_redaction_audit.py`.
