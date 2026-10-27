# PHX: Architecture Decision Log

Lightweight ADRs. Append new decisions at the bottom, and never rewrite history: to reverse a decision, add a new entry that supersedes the old one. Every phase that makes a non-trivial technical choice adds an entry here. Timestamps are `YYYY-MM-DD HH:MM TZ` from `date '+%Y-%m-%d %H:%M %Z'`; a status change (for example `Proposed` → `Accepted`, or `Superseded by ADR-00NN`) is noted in the entry with its own timestamp.

| ID | Timestamp | Decision | Status | Phase |
|---|---|---|---|---|
| ADR-0001 | 2026-10-26 08:35 CDT | Deterministic supervisor program launching headless Claude sessions | Accepted | 00 |
| ADR-0002 | 2026-10-26 08:35 CDT | Name PhaseHypervisor, prefix PHX, CLI `phx`, repo under /home/nick/Work | Accepted | 00 |
| ADR-0003 | 2026-10-26 08:35 CDT | Bypass permissions plus a mandatory stop-and-ask-on-risk rule | Accepted | 00 |
| ADR-0004 | 2026-10-26 08:35 CDT | Agents push/merge/create private repos freely, for all phased projects; public/release stays human | Accepted | 00 |
| ADR-0005 | 2026-10-26 08:35 CDT | Follow the `ai-provider` switch; launch every session through `ai-provider run` with model aliases | Accepted | 00 |
| ADR-0006 | 2026-10-26 08:35 CDT | On a Pro usage limit: wait, notify, auto-resume the same session; never auto-switch provider | Accepted | 00 |
| ADR-0007 | 2026-10-26 08:35 CDT | Strictly one phase at a time | Accepted | 00 |
| ADR-0008 | 2026-10-26 08:35 CDT | No default milestone checkpoints; per-phase Gate (auto/review/owner) and `--pause-after` | Accepted | 00 |
| ADR-0009 | 2026-10-26 08:35 CDT | Headless usage-limit stop is recognisable from stream-json/exit status | Accepted (2026-10-26 10:20 CDT, Phase 05) | 00, 05 |
| ADR-0010 | 2026-10-26 08:35 CDT | Python ≥ 3.12, standard library only at runtime | Accepted (2026-10-26 08:55 CDT, Phase 02) | 00, 02 |
| ADR-0011 | 2026-10-26 08:41 CDT | PHX is additive and opt-in; manual /phased-project and /phase stay unchanged and fully supported | Accepted | 00 |
| ADR-0012 | 2026-10-26 09:05 CDT | Hands-off `/phase` contract version 1, with a `refused` outcome and a lock checked by `flock` | Accepted | 03 |
| ADR-0013 | 2026-10-26 09:21 CDT | Plan parser heuristics: Gate outside eligibility, ⛔ exempt from drift, first-clause test command, publishing inference, config read from main | Accepted | 04 |
| ADR-0014 | 2026-10-26 10:20 CDT | Session runner and classifier: signal priority, `no_result` class, OpenRouter 429 as provider error, allowlisted provider snapshot, context-free probe | Accepted | 05 |
| ADR-0015 | 2026-10-26 15:33 CDT | Verifier and recovery: shell-free test commands, verdict outcomes, retry ladder, live sessions in the main checkout, tool-less triage | Accepted | 06 |
| ADR-0016 | 2026-10-26 16:28 CDT | Supervisor: pauses cleared only by `phx resume`, suspend-safe limit waits, graceful stop, detach env allowlist, work-root guard, `uv tool install --editable` | Accepted | 07 |
| ADR-0017 | 2026-10-26 16:59 CDT | Preflight: interactive launch with an appended system-prompt file, PHX-built context, `--record` fingerprint and staleness rules, no pre-approved publishing | Accepted | 08 |
| ADR-0018 | 2026-10-26 17:16 CDT | Rollout to the four existing projects: one adoption commit each, repo-specific stricter rules kept and flagged, `/phx` as a user-level command | Accepted | 09 |
| ADR-0019 | 2026-10-26 18:38 CDT | Pilot corrections: live-session guard counts main-checkout sessions only on later work, stopped sessions charge their turns, always detach from Claude Code | Accepted | 10 |
| ADR-0020 | 2026-10-26 23:35 CDT | Manual `/phase` PHX check is fail-closed (`PHX-CHECK-DONE` sentinel); contract stays version 1 | Accepted | 11 |
| ADR-0021 | 2026-10-26 23:35 CDT | Hardening from the threat model: confined vault and record writes, full-disk tolerance, pauses kept on refused resumes, claim commit as activity, dry-run test check | Accepted | 11 |
| ADR-0022 | 2026-10-27 05:16 CDT | Share the method: the repo is the source of the `phased-project` skill and `/phx`, shipped as a Claude Code plugin plus manual fallback, with a new public getting-started guide | Accepted | 12a (planning) |
| ADR-0023 | 2026-10-27 05:28 CDT | Phase 12a pre-decisions: symlinked live install, appended settings section, handle-only manifest metadata, sandboxed `uv tool install` check, version bump only on tag approval, `v0.2.0` tag scheme, namespaced plugin names accepted | Accepted | 12a (preflight) |

---

## ADR-0001: Deterministic supervisor program launching headless Claude sessions
**Recorded.** 2026-10-26 08:35 CDT (Phase 00)
**Context.** Nick wants a hands-off deployer of phased implementation plans that is careful with tokens and can run for days across usage limits.
**Options considered.**

| Option | Pros | Cons |
|---|---|---|
| A. Plain program supervising headless `claude -p` sessions | Supervising costs no tokens; survives crashes, reboots and limit waits; fresh small context per phase; easy to log | Real code to write and test |
| B. One long Claude session running phases as subagents | Quick to prototype | Context grows with every phase (cost and fragility); hard to resume after limits |
| C. `/loop` or scheduled routines | Built in | Little control over model and permissions per phase; poor visibility |

**Decision.** A.
**Consequences.** PHX must handle process supervision, output parsing and state itself. Claude is used only where judgment is needed.

## ADR-0002: Name, prefix and location
**Recorded.** 2026-10-26 08:35 CDT (Phase 00)
**Context.** Every phased project needs a unique prefix (existing: MM3, CL, OCC, YTPL2), and Nick asked for the project to live in a sub-directory of `/home/nick/Work`.
**Decision.** PhaseHypervisor, prefix PHX, `/home/nick/Work/PhaseHypervisor`, CLI `phx`.
**Consequences.** Documents are `PHX_*`; the vault note is `02 Projects/PHX Implementation Plan.md`.

## ADR-0003: Bypass permissions with a stop-and-ask-on-risk rule
**Recorded.** 2026-10-26 08:35 CDT (Phase 00)
**Context.** Headless sessions can't answer permission prompts. Nick accepts maximum permissions, provided agents stop and ask when something looks high-risk or a bad idea.
**Options considered.** An allowlist with `acceptEdits` (fragile; phases stall on an unlisted command); `auto` mode (may still prompt); `bypassPermissions` plus a written risk rule (chosen).
**Decision.** Phase sessions run with `--permission-mode bypassPermissions`. Every repo's `CLAUDE.md` carries the rule "if an action looks high-risk, irreversible or a bad idea, stop and ask". In auto mode, "ask" means block-with-question (spec R4).
**Consequences.** Safety relies on the agent's judgment plus Nick's own technical controls, and on S1–S5. The Phase 11 threat model reviews this.

## ADR-0004: Git and GitHub authority for agents, in all phased projects
**Recorded.** 2026-10-26 08:35 CDT (Phase 00)
**Context.** Nick's standing instruction: agents may always push, merge and commit to GitHub without asking; he has technical controls in place. He chose to apply this to all phased projects, not only PHX runs.
**Decision.** Agents commit, merge, push and create **private** GitHub repos without asking. Making a repo public, publishing a GitHub release and force-pushing shared history still stop for Nick. The `phased-project` skill templates, the playbook note and the MM3, CL, OCC and YTPL2 repos are updated to match (Phases 03 and 09).
**Update 2026-10-26 08:44 CDT.** Nick made this a global standing instruction ("never ask for authorization to merge, push or commit, ever"). It was applied straight away to `~/.claude/CLAUDE.md`, the skill and the playbook, ahead of Phase 03.
**Consequences.** This supersedes the template rule "Never push … without Nick's explicit confirmation". Each existing repo is changed only when none of its phases is `🔄 In progress`.

## ADR-0005: Follow the ai-provider switch
**Recorded.** 2026-10-26 08:35 CDT (Phase 00)
**Context.** Nick switches Claude Code between Anthropic Pro and OpenRouter with Super+Alt+A (`~/.local/bin/ai-provider`). That tool exports the provider's environment at session start and maps the `opus`/`sonnet`/`haiku` aliases to OpenRouter models. Nick prefers PHX to follow it rather than have its own setting.
**Decision.** Every PHX-launched session runs as `ai-provider run -p … --model <alias>`. The provider is read at each launch, so a toggle takes effect from the next phase or resume.
**Consequences.** On OpenRouter, phases run on whatever models `~/.config/ai-provider/config` maps (currently non-Claude models). PHX logs the provider and the mapped model for every launch.

## ADR-0006: Usage-limit behaviour
**Recorded.** 2026-10-26 08:35 CDT (Phase 00)
**Context.** A plan can be bigger than one Pro 5-hour window or the weekly allowance.
**Options considered.** Wait and auto-resume (chosen); auto-fail over to OpenRouter (spends shared credit and changes models without Nick choosing); stop until Nick resumes.
**Decision.** Record the stop point, notify, sleep until the reset time (or back off if none is given), then `--resume` the same session. Re-check `ai-provider get` every 5 minutes while waiting; if Nick switched to OpenRouter, resume at once on it.
**Consequences.** Needs reliable limit detection (ADR-0009) and a supervisor that survives the terminal closing (spec R11).

## ADR-0007: One phase at a time
**Recorded.** 2026-10-26 08:35 CDT (Phase 00)
**Decision.** Strictly serial, enforced by a machine-wide lock. Parallel-eligible phases run in ID order.
**Consequences.** Simpler failure handling and steadier token use; slower wall-clock time. The parallel-safety claim protocol stays, for manual sessions.

## ADR-0008: Checkpoints and gates
**Recorded.** 2026-10-26 08:35 CDT (Phase 00)
**Context.** Nick left checkpoints to the planner's judgment; he monitors the documents as work proceeds.
**Decision.** No blocking milestone checkpoints by default. An optional per-phase Gate (`auto` default, `review` pauses after the phase, `owner` won't start the phase) and `phx run --pause-after NN`. A desktop notification after every phase, and a summary in the vault note after every run.
**Consequences.** Errors could pile up between Nick's reviews; independent verification (spec R6) and the stop-on-risk rule limit this.

## ADR-0009: Headless usage-limit stops are recognisable (Accepted)
**Recorded.** 2026-10-26 08:35 CDT (Phase 00)
**Context.** The exact message, exit code and reset-time format of a headless Pro usage-limit stop have not been verified.
**Decision (proposed).** Phase 05 collects real or documented samples, writes the classifier against them with fixtures, and falls back to timed back-off probes when no reset time can be parsed.
**Consequences.** Until verified, the back-off path is the safety net.

**Accepted 2026-10-26 10:20 CDT (Phase 05), with evidence.** Verified against Claude Code 2.1.310 on this machine:
1. **Stream shape (real, captured).** A failed API call in `-p --output-format stream-json --verbose` mode ends with a synthetic `assistant` event (`message.model: "<synthetic>"`, top-level `error` kind and `is_api_error_message: true`) followed by a `result` event with `subtype: "success"`, `is_error: true`, `terminal_reason: "api_error"`, `api_error_status` (HTTP status or `null`) and the message in `result`. Exit code 1. Captured against a closed port and against a local fake API answering 429 (`error: "rate_limit"`, `api_error_status: 429`); no tokens spent.
2. **Pro limit text (real).** `~/.claude/projects` transcripts contain the subscriber stops verbatim, stored with `error: "rate_limit"` and `apiErrorStatus: 429`: `You've hit your session limit · resets 7:40pm (America/Chicago)` (2026-10-12, 2026-10-21). Also real: `Login expired · Please run /login` (`authentication_failed`), OpenRouter `API Error: 402 … requires more credits`, `Connection lost mid-response` (`server_error`).
3. **Templates (documented, from the binary).** The message is `You've hit your <limit>[ · resets <when>][ · progress saved]`. `<limit>` is `session limit` (five_hour), `weekly limit` (seven_day), `Opus limit`, `Sonnet limit`, `Fable limit`, `usage credit limit`, `usage limit` and others. `<when>` is `7:40pm`/`10pm` within 24 h, else `Oct 28, 9am` (with `, 2027` when the year differs), followed by ` (IANA zone)`. Fast mode says `resets in 3h 20m`.
4. **Machine-readable signal (real).** The stream also carries `{"type":"rate_limit_event","rate_limit_info":{"status":"allowed|allowed_warning|rejected","resetsAt":<epoch seconds>,"rateLimitType":"five_hour|seven_day|…",…}}`. Seen live (`status: "allowed"`, with `unifiedWindows`) in the Phase 05 probe on Pro (one `haiku` call, 24,371 tokens, $0.0032 notional).
5. **Docs/web.** No official page documents the headless limit output; issue reports quote the same `You've hit your session limit · resets …` text.

**So:** the classifier uses a `rejected` `rate_limit_event`'s `resetsAt` first, then the `You've hit your …` text (reset parsed in its own zone, returned in local time), then `error: rate_limit` / 429 without a reset time, which triggers the back-off probes. Fixtures in `tests/fixtures/streams/` are labelled real, real-text, documented or synthetic (see its README). Residual risk: Anthropic can change the wording; the event and 429 paths still catch it, without a reset time.

## ADR-0010: Standard-library-only runtime (Accepted)
**Recorded.** 2026-10-26 08:35 CDT (Phase 00)
**Context.** PHX must keep running unattended for days; dependencies are a failure surface. The host Python is 3.14.8; `tomllib`, `json`, `subprocess`, `argparse` and `fcntl` cover the needs.
**Decision.** Runtime uses only the standard library, Python ≥ 3.12. Dev tools via `uv`.
**Confirmed.** 2026-10-26 08:55 CDT (Phase 02). `pyproject.toml` has `dependencies = []`; `python3 -m phx --version` runs from `src/` on the host Python 3.14.8 with no install. Stdlib modules later phases rely on, all present in 3.12 and 3.14: `argparse`, `json`, `tomllib`, `subprocess`, `signal`, `fcntl`, `shutil`, `datetime`, `zoneinfo`, `uuid`, `pathlib`, `dataclasses`, `re`, `os`, `time`. Phase 02 already uses `argparse`, `tomllib`, `json`, `os`, `re`, `dataclasses`, `pathlib`, `time`. No gap found; nothing needs a third-party package.

## ADR-0011: PHX is additive and opt-in
**Recorded.** 2026-10-26 08:41 CDT (Phase 00)
**Context.** Nick wants hands-off runs as a new, optional capability. He will keep running `/phased-project` and `/phase` by hand while he tests PHX and builds trust in it; PHX may become the default later.
**Decision.**
- Manual behaviour of `/phased-project`, `/phase` (all forms) and `/phase-add` stays exactly as it is today. The only differences when auto mode is off are the ADR-0004 git rules (Nick's separate decision) and an optional Gate column that manual runs ignore.
- Hands-off behaviour is reachable only through `--auto` / `PHX_AUTO=1`.
- Manual and PHX runs can alternate on one plan at any phase boundary, and never run at once (spec R15).
- Making PHX the default needs a future ADR.
**Consequences.** Phase 03 must prove interactive `/phase` is unchanged with auto mode off. Phase 09 must not alter manual flows in migrated repos. Phase 10 includes a manual-to-PHX-to-manual handover test. The user guide documents both ways of working side by side.

## ADR-0012: Hands-off phase contract, version 1
**Recorded.** 2026-10-26 09:05 CDT (Phase 03)
**Context.** PHX runs `/phase NN --auto` in headless sessions and must know, without asking anyone, how the command behaves and how it reports. Spec R3, R4, R5, R12 and R15 set the outline; Phase 03 had to make it exact enough for Phases 04–07 to implement against, and portable to every phased project through the skill templates.
**Decision.** [`docs/PHX_AUTO_MODE_CONTRACT.md`](PHX_AUTO_MODE_CONTRACT.md) is the normative contract, version `1`, marked in each command by a `PHX-CONTRACT: 1` line. Choices beyond the spec text:
- **A third result status, `refused`** (spec R5 lists `complete` and `blocked`). Preconditions the interactive command answers with "say so and stop" (unmet dependency, phase already complete, Gate `owner`, claim impossible, no phase ID) change nothing, so they must not look like a block; otherwise PHX's R6 repair would commit a `⛔` for a phase nobody claimed. Two more required keys, `pushed` and `question_ids` (from the phase prompt), plus `contract`.
- **Every block records a question**, including technical failures, so `phx answer` always has something to answer and `question_ids` is never empty for `blocked`.
- **Open questions** are those whose Status cell starts with `Open`; question IDs are carried as strings.
- **Lock check by `flock`**, not by PID: PHX holds an exclusive `flock` on `${XDG_RUNTIME_DIR:-/run/user/$UID}/phx/<repo-name>.lock` for its whole life, and the command tests it with `flock -n -s`. A crashed supervisor leaves no live lock, so stale files are harmless. `flock` is util-linux, present on the reference machine, so `phx` need not be installed.
- **`/phase status` with a supervisor running** shows the notice and still prints the table (the phase prompt said every form stops; status changes nothing, and is most useful exactly then).
- **Resuming a blocked phase** in auto mode is a separate `chore(plan): resume phase NN` commit that closes the Timeline's blocked interval, followed by `git merge main` in the worktree.

| Option | Pros | Cons |
|---|---|---|
| A. Contract with `refused`, `flock` lock check (chosen) | Unambiguous for the verifier; stale locks harmless; no `phx` install needed | One more status for 05/06 to handle |
| B. Two statuses only, preconditions reported as `blocked` | Matches spec R5 text | `blocked` would sometimes mean "nothing claimed", forcing the verifier to guess |
| C. PID file checked with `kill -0` | No `flock` needed | PID reuse gives false positives; a crashed supervisor's file looks live |

**Consequences.** Phase 04 parses `Open` and the marker; Phase 05 parses the result line including `refused`; Phase 06 pauses on `refused` without repair; Phase 07 implements the locks exactly as §8. Phase 09 copies the template sections into MM3, CL, OCC and YTPL2. Interactive `/phase` is unchanged apart from step 0 (verified by diff in Phase 03). A change an older reader would misread needs contract version 2 and a new ADR.

## ADR-0013: Plan parser heuristics
**Recorded.** 2026-10-26 09:21 CDT (Phase 04)
**Context.** `phx.plan` must read four real plans written over several months (MM3, CL, OCC, YTPL2) and every future one, without ever changing them. The phase prompt, spec R6/R12 and contract §3/§7 leave a few rules open.
**Decision.**
- **Gate is not part of eligibility.** `next_eligible` returns the lowest ⬜ phase with deps ✅ and no open question needed by it, and carries its Gate; the supervisor (Phase 07) decides what `review`/`owner` mean. Keeps "what is next" identical to `/phase next`.
- **`⛔ Blocked` rows are exempt from "branch or worktree without a claim" drift.** `/phase status` flags any `phase-NN-*` branch whose row is not `🔄`, but block-with-question (contract §4.2) keeps the branch and worktree on purpose. Flagging them would make every block look like drift.
- **Test command = the first clause** of the shared instructions' "Tests, lint and type checks pass" line: backticked spans, skipping anything in parentheses, up to the first `;` or `.` outside backticks. On the real plans this yields PHX's four `uv run` commands, OCC/YTPL2 `make check`, CL `shellcheck lab/**/*.sh` (its product checks live in another repo; CL needs a `.phx/config.toml` `test_command` if it is ever run hands-off), MM3 none. A `.phx/config.toml` `test_command` on `main` wins.
- **Publishing inference (R12)** is a conservative regex: "make/turn the repo public", "public GitHub repo", "GitHub release/publication", "publish(ed) a release", "publish(ed) to/on GitHub" (not "ready to publish on GitHub"), "create a release", `gh release create`. It matches every release prompt of the four repos and PHX 12; the only extra hit is PHX 04's own prompt, which has an explicit Gate. A false positive costs one pause; an explicit Gate always wins.
- **Everything is read from `main`** with `git show main:<path>`: the plan, prompts (for Gate), shared instructions, `.claude/commands/phase.md` and `.phx/config.toml` (new `paths.parse_config`). A phase branch or a dirty working tree never changes what PHX sees.
- **Problems vs errors.** Malformed IDs, duplicate IDs, short rows, missing required columns, unreadable status and bad Gate cells raise `PlanError` (the plan cannot be trusted). Zero/two status icons, icon/word disagreement, an unknown model on a phase that is not complete, a dependency not in the table and a missing prompt are listed in `Plan.problems` and shown by `phx plan`; `Phase.require_alias()` raises `UnknownModel` before a launch (R2).

| Option | Pros | Cons |
|---|---|---|
| A. Heuristics above (chosen) | Correct on all five real plans; no plan needs editing; explicit settings always win | Heuristics can misread an unusual plan (shown in `phx plan` output) |
| B. Require explicit Gate and test-command settings in every plan | Exact | Every existing plan needs edits before `phx plan` works; contradicts ADR-0011's "unchanged" spirit |

**Consequences.** Phase 06 runs `Plan.test_commands` (a tuple) and reports CL-style plans whose real checks are elsewhere; Phase 07 applies Gates after `next_eligible`; Phase 09 may add Gate columns and a CL `.phx/config.toml` when migrating.

## ADR-0014: Session runner and exit classifier design
**Recorded.** 2026-10-26 10:20 CDT (Phase 05)
**Context.** Phase 05 builds `phx.runner` and `phx.classify` (spec R7–R10). The prompt lists eight exit classes and leaves the precedence between signals, the OpenRouter case and the probe's footprint open.
**Decision.**
- **Signal priority:** timeout → (session ended in error) rejected `rate_limit_event` or `You've hit your …` text → `rate_limit`/429 → auth (`authentication_failed`, 401/403, `/login` text) → `--max-budget-usd` stop → credit (`billing_error`, 402) → server (`server_error`, 5xx) → rejected request (`invalid_request`, 400) → other API error → otherwise the `PHX-RESULT` line → no `result` event = `crash`. An API error that the session recovered from (a normal assistant message came after it, clean `result`) is ignored.
- **A ninth class, `no_result`:** the session ended cleanly but without a valid result line. Calling that `complete` or `crash` would mislead; contract §6 says verification decides, so Phase 06 treats it as "verify".
- **A 429 on OpenRouter is `provider_error(rate_limited)`**, not `usage_limit`: Pro limits are waited out (ADR-0006); OpenRouter throttling is not a Pro window.
- **Provider snapshot:** `ai-provider get` each launch; on OpenRouter `ai-provider env` is parsed in memory against an allowlist of non-secret variables (base URL, model mappings, token caps). The rest of that output, including the key, is dropped unread and never logged.
- **Probe:** `-p ok --model haiku --max-turns 1` through the same launcher, in the state directory and without `PHX_AUTO`, classified with `expect_result_line=False` (a clean answer = `complete`).
- **Timeouts:** `idle_timeout_s` (default 1800) and `wall_timeout_s` (21600) in `.phx/config.toml`; the session runs in its own process group (`start_new_session`), SIGTERM then SIGKILL after 10 s.
- **`--verbose` is mandatory** with `-p --output-format stream-json` (2.1.310 exits 1 without it).

| Option | Pros | Cons |
|---|---|---|
| A. Nine classes with `no_result` (chosen) | Honest; Phase 06 can tell "agent forgot the line" from a crash | One class more than the prompt listed |
| B. Map a missing line to `crash` | Matches the prompt's list | A finished, merged phase would look like a crash and trigger needless recovery |

**Consequences.** Phases 06/07 handle `no_result` by verifying. The probe still loads the user's global `CLAUDE.md` and system prompt (~24k mostly cached tokens per probe); Phase 10 may measure whether `--safe-mode` makes it cheaper without changing auth.

## ADR-0015: Verifier and recovery design
**Recorded.** 2026-10-26 15:33 CDT (Phase 06)
**Context.** Phase 06 builds `phx.verify`, `phx.recover` and `phx.triage` (spec R6, R9, R14). The prompt asks for an ADR on running plan test commands that need a shell without `shell=True` on untrusted text, and leaves open how the decision table treats combinations it does not list, where to look for a live manual session, and how to keep the triage session safe.
**Decision.**
- **Test commands run without a shell, through a small interpreter.** A command is split on top-level `&&` into steps; a step is `cd DIR`, or words with optional leading `NAME=value` assignments. Single and double quotes and backslash escapes are honoured; unquoted `*`, `?`, `[` are globs expanded with Python's `glob` (`**` recursive, like bash `globstar`) relative to the step's directory. Pipes, redirects, `;`, `||`, `&`, subshells, `$` and backtick expansions, `~`, braces and comments are refused: the `tests` check fails with "not run: … set test_command in .phx/config.toml to a script". `cd` and glob results must stay inside the checkout. Each command runs with an argument list, stdin `/dev/null`, a `test_timeout_s` cap (new config key, default 3600) and an environment without `PHX_AUTO`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY` and `VIRTUAL_ENV`.
- **Where tests run:** a `git clone --no-checkout` of the repo into a fresh temp directory, then a detached checkout of `main`'s commit; removed afterwards. Ignored and untracked files of the user's checkout never reach it, and the user's checkout, index and worktree list are never written.
- **Plans whose checks live elsewhere (ADR-0013):** when the command comes from the shared instructions and refers to a path the checkout lacks (a `cd` target, a script, a glob with no match), the command is `skip` with a note pointing to `.phx/config.toml`. When it comes from `.phx/config.toml`, the same thing is a failure: an explicit setting must be right. CL's `shellcheck lab/**/*.sh` is skipped this way.
- **Verdicts.** Checks are pass/fail/skip with evidence; some are optional (reported, never decisive): `pushed` (from the local `origin/main` ref, never fetched), `branch_kept`, `work_in_progress`, `main_unchanged`. The outcome is `complete`, `blocked`, `in_progress`, `not_started` (what the row says, all required checks passing), `failed` (a required check failed) or `needs_review` (the `PHX-RESULT` line disagrees with the repo on status, phase ID, `merged`, `pushed` or question IDs; a `refused` session whose row is `🔄` or whose `main` moved since launch). A **baseline** taken before the launch makes pre-existing uncommitted files in the main checkout pass (MM3 has some) and lets "refused, nothing changed" be checked. Tests run only for a `✅` row and never for a `refused` session.
- **Decision rules beyond the table.** Auth and provider errors pause without verifying. Otherwise the repo decides: a phase that is `✅` and verified goes on to the next phase even if the session ended as `timeout`, `crash`, `no_result` or `usage_limit`. A `⛔` row with a recorded question pauses whatever the class. `no_result` on an unclaimed phase pauses (it neither worked nor refused). The timeout/crash ladder (also `no_result` with the row `🔄`) is: `--resume` of the same session with a "continue the phase" prompt, then a fresh `/phase NN --auto`, then pause; the supervisor counts the recoveries (`MAX_RECOVERIES = 2`).
- **The `⛔` repair** has the claim protocol's preconditions (main checkout on `main`, plan file unchanged there and equal to `main`, row `🔄`), rewrites only that row's Status cell, commits only the plan file as `chore(plan): phase NN blocked (recorded by phx)` and pushes `main` when an `origin` remote exists (ADR-0004; a failed push is logged, not fatal). Anything unsafe is logged as `repair_skipped` and left for Nick.
- **Live sessions (R14, R15) are looked for in the phase worktree and the main checkout.** Claude Code's process keeps the directory it started in, and `/phase` sessions start in the main checkout (the claim protocol); only their tools run in the worktree. Observed in this phase: this very session's `claude` process (pid 9892) has the main checkout as its cwd. A Claude process is matched by `comm`, by `argv[0]`/`argv[1]` basename `claude`, or a `node`/`bun` running `claude-code`. The current process and its ancestors are excluded, so a `phx` started from inside Claude Code is not its own rival.
- **Triage is tool-less.** One `haiku` session with `--tools ""`, `--permission-mode default`, `--max-turns 1`, in the state directory and without `PHX_AUTO`; the prompt marks the verdict and the phase's final messages (redacted, last 6000 characters) as data. The answer is redacted and clipped to 150 words. It runs only when a pause follows a `blocked`, `needs_review` or `failed` verdict and `triage` is on; a failure is logged and the decision stands.

| Option for test commands | Pros | Cons |
|---|---|---|
| A. Shell-free interpreter for `&&`, `cd`, assignments, quotes, globs (chosen) | No shell ever parses plan text; covers every real plan (PHX `uv run …`, OCC/YTPL2 `make check`, CL's `**` glob, `cd x && …`); refusals say exactly what to change | A subset: pipes or `||` need a script |
| B. `bash -c "<command>"` in the clone | Full compatibility, little code | A shell on plan text (S3); variable and command expansion from repo content |
| C. `shlex.split` and run as one argument list | Smallest | No `&&`, `cd` or globs: CL and product-style commands cannot run |

| Option for live-session scope | Pros | Cons |
|---|---|---|
| A. Worktree and main checkout (chosen) | Finds real `/phase` sessions, whose cwd is the main checkout | A Claude session open in the main checkout for something else also pauses a resume (safe direction; reason says "may be running") |
| B. Worktree only (spec R15 text) | No false positives | Misses every real session |

**Consequences.** Phase 07 calls `capture_baseline` before each launch, `handle_outcome` after it, keeps the recovery count and session ID in `state.json`, calls `check_resumable` before resuming a `🔄` phase (R14) and puts `Decision.summary` in the notification. Phase 11 threat-models the interpreter and the triage prompt. Spec amendment R18.

## ADR-0016: Supervisor loop, state and installation
**Recorded.** 2026-10-26 16:28 CDT (Phase 07)
**Context.** Phase 07 builds the supervisor (`phx run / resume / status / stop / log / answer`) on top of Phases 04 to 06. The prompt leaves open what `phx run` does with an earlier pause, how a wait survives suspend and restarts, what `phx stop` leaves behind, which environment a detached unit gets, how `limit_poll_interval_s` is used, how S1's "repos under /home/nick/Work" is enforced, and asks for an ADR on installing `phx` for daily use.
**Decision.**
- **A pause is sticky.** Any pause (block, review Gate, `--pause-after`, owner Gate, verification failure, live session, nothing eligible) is stored in `state.json`. `phx run` refuses while it is set (exit 3) and says why; only `phx resume` clears it, then runs exactly like `phx run`. `--until NN` and `--max-phases N` end the run as `finished`, not paused. A phase reported `✅` by a resumed run is gated like any other.
- **What runs next**, in order: a pending usage-limit wait from an earlier supervisor (its phase still `⬜`/`🔄`); a `🔄` phase (after `check_resumable`; `--resume` of the session PHX recorded for it, else a fresh `/phase NN --auto`; more than one `🔄` pauses); a `⛔` phase (pause while an owner question needs it, else a fresh `/phase NN --auto`, contract §4.3); the next eligible phase. Gate `owner` pauses before launch, `review` pauses after. Nothing eligible but phases remain: pause with every phase's reason. The session ID is written to `state.json` as soon as the process starts (`run_session(on_start=…)`), so a supervisor killed mid-phase can be resumed with `--resume`.
- **Usage-limit waits (ADR-0006).** Wake at `reset_at` + 2 min, or after the back-off 30 min, 1 h, 2 h, 4 h, 6 h, 6 h… when no reset time is given. The wake time is a wall-clock epoch stored in `state.json`; the supervisor sleeps at most 60 s at a time and re-reads the wall clock, so a suspend or a restart only shortens or resumes the wait. `ai-provider get` is checked at once and then every `poll_interval_s` (300 s); a change to `openrouter` resumes at once without a probe. After a timed wait one `haiku` probe decides: clean → resume; limit with a new reset time → wait for it; limit after a known reset time passed → re-probe every `limit_poll_interval_s` (900 s); limit without one → next back-off step; auth error → pause. A usage-limit resume does not count as a recovery.
- **Stop is graceful.** `phx stop` sends SIGTERM to the PID in the repo lock and waits for the lock to be released (`--timeout`, default 120 s). SIGTERM, SIGINT and SIGHUP set a stop event; a running session's process group is stopped like a timeout (`run_session(cancel=…)`, class `timeout`, kind `stopped`), nothing is verified or retried, `run_end` and the vault summary are written, and the phase stays `🔄` with its session recorded. A wait is kept and continues on the next run. Exit codes: 0 finished, 1 error (lock busy, plan/contract error, supervisor error), 3 paused, 4 stopped.
- **Detached runs** use `systemd-run --user --unit phx-<repo> --collect` with `KillMode=mixed` (SIGTERM to `phx` only; it stops its own session) and `TimeoutStopSec=90`, and pass only an allowlist of variables: `PATH`, `HOME`, `USER`, `LOGNAME`, `LANG`, `TZ`, `XDG_*` dirs, `DISPLAY`, `WAYLAND_DISPLAY`, `DBUS_SESSION_BUS_ADDRESS`, `PHX_WORK_ROOT`, plus `PHX_UNIT`. Secrets in the launching shell never reach the unit. The reference machine has `Linger=no`: the unit survives closing a terminal (checked) but not the end of Nick's last login session; PHX does not change linger.
- **Work-root guard (S1).** `phx run`/`resume` refuse a repo outside `$PHX_WORK_ROOT`, default `~/Work`, and refuse to run as root. The variable exists for tests and pilots; Phase 11 reviews it.
- **Answers** (`phx answer`) follow the repair's preconditions (main checkout on `main`, plan file clean and equal to `main`, no supervisor running), escape `|`, refuse a question that is not open unless `--force`, commit only the plan file (`docs(plan): answer owner question N`) and push when `origin` exists.
- **Notifications** go through `notify-send` with `--hint=boolean:suppress-sound:true` and never speak; without a display, a bus or `notify-send` they are skipped and logged.
- **Install: `uv tool install --editable /home/nick/Work/PhaseHypervisor`.**

| Option | Pros | Cons |
|---|---|---|
| A. `uv tool install --editable` from the main checkout (chosen) | Standard; `phx` lands in `~/.local/bin` (already on PATH); an isolated venv; follows `main` as phases merge, with no reinstall; `uv tool uninstall phx` undoes it | The installed `phx` changes when `main` changes (only by verified merges); the venv's Python comes from uv |
| B. A shell shim `~/.local/bin/phx` running `python3 -m phx` with `PYTHONPATH` | No uv involvement, one small file | Hand-written file to maintain; uses whatever `python3` is first on PATH |
| C. `uv tool install` (non-editable) | Pinned code, unaffected by later merges | Needs a reinstall after every phase; easy to run stale code |

**Consequences.** Phase 08 adds the preflight staleness warning where the test-command warnings are emitted (first loop iteration). Phase 10's simulated limit must run in the foreground or through shims, because a detached unit does not receive `PHX_FAKE_*` variables. Phase 11 threat-models the work-root override, the detach allowlist and the `phx answer` write path. Spec amendment R19.

## ADR-0017: Preflight session, record and staleness
**Recorded.** 2026-10-26 16:59 CDT (Phase 08)
**Context.** Spec R13 asks for one interactive session on the strongest model that asks Nick everything foreseeable for the rest of a plan, records the answers and Gates, and commits; `phx run` warns when no preflight has run since the plan last changed. The prompt leaves open how the session is started interactively, how much PHX does itself, what "the plan last changed" means when every phase changes the status column, and what a preflight may decide about publishing.
**Decision.**
- **Launch:** `ai-provider run --model opus --session-id <uuid> --name "phx preflight <repo>" --append-system-prompt-file <prompt> "<kickoff>"`, interactive (no `-p`), in the main checkout. Verified on Claude Code 2.1.310 without tokens: the flag is parsed on an interactive start (a missing file fails with "Append system prompt file not found" before any UI or API call; an unknown flag fails with "unknown option"), and the binary's help text for it carries no "only works with --print" note, unlike the subagent variant. The kickoff is a short first message so the session starts at once. No `PHX_AUTO` (the session must ask), no `ANTHROPIC_MODEL`, and no `--permission-mode`: Nick is present, so his own permission settings apply.
- **PHX does the free part:** it refuses when a supervisor holds the repo lock, the checkout is off `main`, a phase is `🔄` (offering `phx status`) or every phase is `✅`; it lists the remaining phases with a suggested Gate, the open questions and the **deferred** ones a remaining phase needs (MM3's Q3/Q5 style), heuristic leads from the remaining prompts (regex, ranked, clipped, quoted as data), and `git`/`gh`/`uv`/`docker`/`gh auth status` checks. The session reads only the plan, `CLAUDE.md`, the spec's Amendments, the ADR index and the remaining prompts.
- **Record by command, not by the agent:** the session runs `phx preflight --record` (exact command in its prompt, `sys.executable -m phx`), which computes the fingerprint from `main` and commits only `.phx/preflight.json`. An agent-written hash would not match PHX's.
- **Staleness = the plan's definition changed, not its progress.** A fingerprint per phase row covers ID, name, model, dependencies, prompt path and an explicitly set Gate; status and inferred/default Gates (which follow prompt edits that phases make routinely) are left out. The record also lists the question IDs it saw. Stale when a row was added, removed or changed, the plan file was renamed, or an owner question is open that the record never saw.

| Option for "the plan changed" | Pros | Cons |
|---|---|---|
| A. Row-definition fingerprint + unseen open questions (chosen) | Completing phases and answering questions keep it fresh; `/phase-add`, re-planned rows and new hand-written questions make it stale; reasons name the phases | A question raised and answered by a block is not flagged (by design: it was handled) |
| B. Hash of the whole phase table and questions | Simple | Stale after every phase (the Status column) and every answer: the warning would always fire |
| C. Git history since the record (commits touching the table) | Exact "since" | Needs history walks and diff parsing of Markdown tables; same Status-column problem |

- **Publishing is never pre-approved (S5, ADR-0004).** A preflight records the details (owner, name, visibility, topics) and proposes a `review` Gate for publishing, spending and manual-check phases (`owner` where Nick must act himself); the phase still asks for the yes at that moment and blocks with the question in hands-off mode.
- **Gate column:** a preflight may add the `Gate` column (last column, a value in every row) to a plan that has none, per contract §7.
- **`--require-preflight`** ends the run as `failed` (exit 1) before anything is launched, with rule `preflight_missing`, `preflight_stale` or `preflight_invalid`; without it PHX logs a `warning` with the same rule and carries on. It is not a sticky pause: nothing about the run needs resuming.
- **Packaging:** the prompt lives in `prompts/PHX_preflight.md` (a project document) and is force-included into the wheel as `phx/PHX_preflight.md`; an editable install reads the repo copy.
- `phx preflight` does not apply the S1 work-root check: it bypasses no permissions and Nick is at the keyboard. It refuses to run as root.

**Consequences.** Phase 09's `/phx` slash command cannot host an interactive preflight inside a running Claude Code session; it should print `phx preflight <repo>` for Nick to run in a terminal (or run `--dry-run`/`--check`). Phase 10 runs the first real preflight and measures its tokens (the interactive session writes no PHX transcript; its session ID is in `run.jsonl`). Phase 11's threat model covers the preflight prompt's quoted repo text and the `--record` write path.

## ADR-0018: Rollout to existing projects
**Recorded.** 2026-10-26 17:16 CDT (Phase 09)

**Context.** MeetingMaster3 (`MM3`), chessloopDeploy (`CL`), OCC and YTPL2 were bootstrapped before the hands-off contract. All four were idle (no `🔄` row on `main`, no `phase-*` worktree, nothing running) when Phase 09 started; MM3's main checkout had three unrelated untracked scripts (`runServer.sh`, `serverCheck.sh`, `serverTest.sh`), which were left alone and not committed.

**Options considered.**
| Option | Pros | Cons |
|---|---|---|
| One `chore(phx): adopt hands-off phase contract` commit per repo, only the files the migration touches (chosen) | Easy to review and to revert; never sweeps in other work | Four commits to look at |
| Copy the skill templates over each repo's files | Uniform text | Loses repo-specific wording (ADR references, CL's product section, OCC's vault rule) |
| Migrate only the repo about to be piloted | Smaller change now | Phase 10 and later pilots would each need a rollout first |

**Decision.**
- Each repo got the contract by inserting the template blocks into its own files (`phase.md`: marker, step 0, hands-off section; shared instructions: pointers, block-with-question section, ADR-0004 merge/push wording, `PHX-RESULT` note; `CLAUDE.md`: Risk rule and the ADR-0004 git rule; plan: Gate column, legend and a `phx` paragraph; an ADR and a vault log line). Gates: `auto` for every phase, `review` for the release or publication phase (MM3 16, CL 13, OCC 12, YTPL2 13).
- **Stricter repo-specific rules were kept and flagged to Nick:** CL's planning repo stays local-only (no remote) and its product PRs stay under ADR-0012 (low-risk test, never changing GitHub repo settings); because CL's shared instructions already use §1b for product changes, its block-with-question section is **§1c** and its `phase.md` says so. The older rules "Never push…" (MM3, OCC, YTPL2 `CLAUDE.md` and close-out) and "Ask Nick whether to merge" (YTPL2, CL) were *not* stricter-by-design, they predate Nick's standing authority of 2026-10-26 08:44 CDT, so they were replaced by the ADR-0004 text. `/phase-add` in MM3, OCC and YTPL2 no longer says "Never push" (CL's stays: no remote).
- CL's test line yields only its planning-repo check (`shellcheck lab/**/*.sh`, ADR-0013). Whether CL needs a `.phx/config.toml` `test_command` is left to Nick (CL is complete, so no run is planned).
- No repo has a git remote, so nothing was pushed.
- `~/.claude/commands/phx.md` is a user-level command (works in any repo; not a project file) and, per ADR-0017, never hosts the interactive preflight.
- The test fixtures under `tests/fixtures/plans/` are refreshed copies of the migrated files, so tests now see `Contract: 1` and column-sourced Gates; the unmigrated path is tested with a fixture whose marker is removed.

**Consequences.** `phx plan` reports `Contract: 1` and the same next phase as before for all four (MM3 16, CL none, OCC 11, YTPL2 03). Interactive `/phase` behaves as before: the differences are step 0 (stops only when a `phx` supervisor is running), the hands-off section (inert without `--auto`/`PHX_AUTO=1`) and the ADR-0004 git rules. A preflight recorded before the migration is stale. Undo per repo: `git revert` its adoption commit (MM3 `ba51654`, CL `dec549e`, OCC `2e0a7d4`, YTPL2 `2935948`).

## ADR-0019: Pilot corrections to the live-session guard, accounting and detaching
**Recorded.** 2026-10-26 18:38 CDT (Phase 10)

**Context.** In the Phase 10 pilot Nick drove PHX from Claude Code sessions opened in the pilot repo. A foreground `phx resume` started with `!` got SIGTERM when that session was backgrounded, and stopped phase 05 cleanly. Every `phx resume` afterwards paused with "a Claude session is open in the main checkout": first Nick's idle interactive `claude`, then a `claude bg-pty-host` wrapper hosting an idle background agent. Neither was working on 05, so the phase had to be finished by hand. The stopped session was logged with 0 tokens although it had spent 4.5 k output and 386 k cache-read tokens, because PHX read totals only from the final `result` event.

**Options considered.**
| Option | Pros | Cons |
|---|---|---|
| Keep counting every Claude process in the main checkout | Never resumes over a manual session | Driving PHX from Claude Code in the repo (what `/phx` invites) blocks every resume |
| Count a main-checkout process only on evidence of later work: headless `/phase`, or the phase's branch tip or a changed worktree file newer than the process start and PHX's last session end (chosen) | Idle shells and the driver session stop blocking; a manual `/phase NN` that is editing still blocks | Heuristic: a manual session that has done nothing for the phase since it started is not seen; its first commit or edit makes it count |
| An override flag (`--ignore-sessions`) | Simple | Puts the judgement on Nick every time; easy to misuse |

**Decision.** The second option (spec R21). Processes in the worktree always count. `claude bg-pty-host` wrappers are skipped. PHX's last session end is the mtime of its newest `sessions/<phase>-<n>.jsonl`. A resumable check names the ignored processes in `resume_check`. Usage: when the result event is missing or reports zero tokens, PHX sums the last `usage` per assistant message ID; cost stays unknown. A recorded session whose phase is `✅` on `main` is dropped (`session_dropped`). `/phx` gains `resume` and always detaches; the user guide says to always `--detach` from inside Claude Code.

**Consequences.** Resume works while Nick keeps Claude Code open in the repo. Token totals now include interrupted sessions (cost still only from result events). The guard remains conservative for sessions in the worktree.

## ADR-0020: The manual `/phase` PHX check fails closed
**Recorded.** 2026-10-26 23:35 CDT (Phase 11)

**Context.** Contract §8 step 0 makes a manual `/phase` check for a live supervisor before it claims anything. In the Phase 10 pilot (finding F5), a headless manual `/phase` had that check denied by permissions four times. It carried on to the next steps and stopped only because a dependency was missing. A check that is skipped when it cannot run protects nothing.

**Options considered.**
| Option | Pros | Cons |
|---|---|---|
| Keep the wording ("if it prints `PHX-RUNNING` … stop") | No change to five repos | Silence is ambiguous: the check prints nothing both when no supervisor runs and when it never ran |
| Add a closing sentinel `echo PHX-CHECK-DONE`, and stop unless the output ends with it (chosen) | Unambiguous; works for denied, failed and timed-out calls; one line per repo | A manual `/phase` in a sandbox that forbids shell commands now refuses (by design; Nick runs it interactively instead) |
| Bump the contract to version 2 | Signals the change | PHX reads nothing new (hands-off mode skips step 0), so a bump would only force needless re-migrations |

**Decision.** The second option, in the skill template, `SKILL.md`, the playbook, contract §8 and the `phase.md` of PHX, MM3 (`81ee0a6`), CL (`9555f22`), OCC (`a1d5cdd`) and YTPL2 (`582b460`), one commit per repo. `status` reports the failed check above the table and continues. The contract stays at **version 1**.

**Consequences.** A manual `/phase` that cannot verify PHX is absent no longer claims. Test fixtures were refreshed from the four repos. The contract test asserts the sentinel.

## ADR-0021: Hardening decisions from the Phase 11 threat model
**Recorded.** 2026-10-26 23:35 CDT (Phase 11)

**Context.** `docs/PHX_THREAT_MODEL.md` rated 20 threats. These decisions are the ones that change behaviour.

**Decisions.**
1. **Vault note confinement (T17).** The note path read from `CLAUDE.md` on `main` must be an absolute `.md` path. It must resolve, symlinks followed, inside `$PHX_VAULT_ROOT`, default `~/Documents`. Otherwise the summary is skipped and logged. Alternatives: trust the path (repo text could point PHX at any Markdown file), or an allowlist file (more setup for no gain). `PHX_VAULT_ROOT` joins the `--detach` allowlist.
2. **`preflight --record` refuses symlinks (T4).** A committed symlink at `.phx/` or `.phx/preflight.json` would redirect the write outside the repo.
3. **Full disk is not fatal (T11).**
   - Event-log records that cannot be written go to stderr (the journal when detached).
   - A failed `state.json` write is logged once and the run continues with its state in memory.
   - A failed transcript write stops only the transcript.
   - Rejected alternative: stop the run on the first failed write. That would kill a phase session that is doing good work because PHX's own bookkeeping disk is full.
4. **Failed commits restore the file's text (T13, T16).** They no longer run `git checkout --`, which fails while `index.lock` is held and would leave Nick's `main` checkout dirty.
5. **`phx resume` keeps the pause when the run is refused at startup (F6).** The pause is cleared only after the plan, contract, config, preflight and launcher checks pass. A refusal logs `pause_kept`.
6. **The claim commit counts as phase activity (T9, F8).** The live-session guard treats the latest `chore(plan): start|resume phase NN` commit on `main` as activity, so a session that claimed by hand and has not yet branched is not resumed over.
7. **Dry-run test check (F9).**
   - What runs: `phx run --dry-run` runs the plan's test command once, exactly as verification will (a clean clone of `main`, no shell). If it fails, PHX says so, and when lockfiles are tracked (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `uv.lock`, depth ≤ 2) it suggests a `test_command` that installs them first.
   - Opting out: `--skip-test-check` skips the check.
   - Triage: the triage prompt now says the clone has no installed dependencies.
   - Why not the preflight: in `phx preflight` the check would delay the interactive session by the test time, and its context step must stay instant.
8. **Redaction scope (T7).** Assignments are redacted for any upper-case name ending in `TOKEN`, `API_KEY`, `SECRET` or `PASSWORD`, in shell, YAML, JSON and escaped-JSON forms. Quotes are kept, so lines stay valid JSON. Redaction is idempotent.
9. **Test-command timeouts kill the process group (T6).** Because the command then runs in its own session, the terminal's Ctrl+C no longer reaches it. `phx stop` and Ctrl+C now kill running test commands themselves (`verify.stop_running_tests`). A stop that interrupted the tests pauses as `stopped_during_verification`, because that test failure proves nothing.
10. **Code-review fixes.**
    - The dry-run test check obeys the S1 work root.
    - A failed final `state.json` save is retried once, then reported loudly.
    - A partial event-log write is truncated away.
    - The transcript's mtime stays current after a write failure, since it is PHX's 'last session end'.
    - The `test_command` suggestion is made only for a single shared-instructions command.

**Consequences.** No High risk is left unmitigated. A real run whose vault note lives outside `~/Documents` (the Phase 10 pilot's throwaway vault) needs `PHX_VAULT_ROOT`.

## ADR-0022: Share the method from this repo as a plugin, with a public guide
**Recorded.** 2026-10-27 05:16 CDT (planning of Phase 12a, `/phase-add`)

**Context.** PHX v0.1.0 is public, but only Nick can use it as intended. The `phased-project` skill, its templates (which generate every repo's `/phase` and `/phase-add`) and the `/phx` command exist only in Nick's `~/.claude`, with about 95 references to his name, paths, vault and private repos. They also rely on standing rules that live only in his global `CLAUDE.md`. Nick asked whether the whole system could be packaged so that other users can deploy it, with instructions on how the pieces work together. Planning concluded that it can: the `phx` runtime already falls back to `claude` without `ai-provider`, and its vault root is configurable. Nick chose among these options on 2026-10-27 05:14 CDT.

**Options considered.**

| Question | Option | Pros | Cons |
|---|---|---|---|
| Source of the skill | **A. Repo is the source; Nick switches to it** | One copy, no drift; Nick uses what others get | Edits the live skill every project depends on; needs a regression check and backups |
| | B. Separate public copy | No risk to Nick's setup | Two copies drift; every improvement made twice |
| | C. Export script that sanitises Nick's copy | Nick keeps one hand-edited copy | Fragile substitution; could leak personal text into a public repo |
| Install path | **A. Plugin (marketplace in this repo) plus manual-copy fallback** | Native install and update; works without plugins too | Two install paths to document and test |
| | B. Plugin only | Simplest | Leaves non-plugin users to work it out |
| | C. `install.sh` only | One command, could also install `phx` | Script writing into `~/.claude` is less trusted; no auto-update |
| Explanatory guide | **A. New public guide in the repo; playbook stays Nick's** | Written for strangers; nothing private published | One more document to keep in step |
| | B. Publish a scrubbed playbook | One document | Written for Nick; changes his vault habit |

**Decision.** A, A, A. Personal values move into an optional "Phased-project settings" section of the user's global `CLAUDE.md`, and `examples/CLAUDE.user.md` gives new users that section plus the standing rules. Phase 12a decides, and records in its own ADR, how plugin namespacing works, whether Nick's install uses symlinks or the plugin, and the exact settings format.

**Consequences.** From Phase 12a on, skill and template changes are made in `plugins/phased-project/` in this repo. They are mirrored in `docs/PHX_GETTING_STARTED.md` and in Nick's playbook note (`CLAUDE.md` rule 7 changes). Everything committed to the plugin is public on push, so a deny-list test guards against personal text. The hands-off contract stays version 1 (ADR-0012), and manual use without `phx` stays fully supported (ADR-0011). Tagging a plugin or app version, or creating a GitHub Release, still needs Nick's confirmation (ADR-0004).

## ADR-0023: Phase 12a pre-decisions from the preflight
**Recorded.** 2026-10-27 05:28 CDT (phx preflight)

**Context.** Phase 12a (ADR-0022) left several choices to the phase, and some of its tasks touch Nick's live setup or a public repo. Without these answers, a hands-off run would block or guess. Nick answered them in the preflight. Owner questions 6 to 12 record each answer.

**Options considered.**

| Question | Option | Pros | Cons |
|---|---|---|---|
| Nick's live install | **A. Symlinks into the main checkout** | Short names kept; edits land in the repo; easy undo from backups | Not the exact plugin path strangers use; breaks if the checkout moves |
| | B. Plugin install from the local marketplace | Exactly what others get | Possibly namespaced names; plugin cache between edits and the live copy |
| | C. Leave it to Nick | No risk to the live setup | Acceptance criterion unmet; follow-up |
| Global `CLAUDE.md` | **A. Append the settings section after a backup** | Existing rules untouched | Some duplication with the phased-project pointer |
| | B. Append and tidy duplicates | Shorter file | Rewrites Nick's rules hands-off |
| | C. Print the block for Nick to paste | Zero risk | Manual step |
| Manifest author/owner | **A. `antonizick` handle only** | Fits the deny-list; no personal data published | Less personal attribution |
| | B. Full name / C. full name and email | Fuller attribution | Deny-list exceptions; email published |
| `uv tool install git+…` check | **A. Scratch `HOME`/`UV_TOOL_DIR`/`UV_TOOL_BIN_DIR` only** | Tests the stranger path; Nick's editable install safe | Needs network |
| | B. Don't try / C. anywhere, then restore | No network / simplest | Untested path / risks Nick's install |
| Versioning | **A. Bump to 0.2.0 only when Nick approves the tag** | No version claimed without a release | Bump commit at close-out |
| | B. Bump now / C. no bump, no tag | Simpler / no release | Version without tag / plugin users track `main` |
| Tag scheme | **A. `v0.2.0` repo tag only** | Matches `v0.1.0`; one version | No `claude plugin tag` form |
| | B. Both / C. plugin tag only / D. decide later | Plugin-native tags | Two schemes to keep in step |
| Namespaced plugin names | **A. Accept and document both forms** | No blocking; honest docs | Longer names for plugin users |
| | B. Lead with manual install / C. block | Short names / Nick decides | Plugin demoted / stops the run |

**Decision.** A in every row. In task 6 of Phase 12a: back up `~/.claude/skills/phased-project`, `~/.claude/commands/phx.md` and `~/.claude/CLAUDE.md` with timestamps, append the "Phased-project settings" section, then replace the skill and command with symlinks into `/home/nick/Work/PhaseHypervisor/plugins/phased-project/`. Do this only if the task 8 regression diff shows nothing but explained wording changes; otherwise block-with-question. The manifests name `antonizick` (with its GitHub URL) and give no email. The stranger `uv tool install` path is tried only in a scratch environment. The phase ships at 0.1.0. Its close-out asks one question: may it tag `v0.2.0` and create a GitHub Release? On a yes, it bumps `pyproject.toml`, `plugin.json` and CHANGELOG to 0.2.0 in one commit before tagging.

**Consequences.** Phase 12a can run hands-off up to its close-out question. The tag and Release still need Nick's explicit yes at that moment (ADR-0004, ADR-0017: nothing is pre-approved for publishing). The test that the plugin version matches `phx --version` holds at both 0.1.0 and 0.2.0.
