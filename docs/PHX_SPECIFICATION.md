# PHX: PhaseHypervisor Specification

> **Amendments override earlier sections.** Section 4 (Amendments) is authoritative where it conflicts with sections 1–3.

**Version:** 1.0 · **Source:** planning conversation with Nick, 2026-10-26 (Claude Code session "Design Phased Project Hypervisor"). There was no separate pre-plan document; section 1 records Nick's request as he gave it, and sections 2–3 the assessment he accepted.

## 1. Owner's request (verbatim, typos kept)

> Riht now the /phased-project and /phase capabilities we have added to Claude code work perfectly. Is it possible to implement effectively a phased-project-hypervisor that I can direct to an existing Implementation_Plan designed by /phased-project And the hypervisor would launch appropriate AI model sessions that would Launch the various phases of project implementation. Ideally, it would ask me any questions in advance that it could practically anticipate, Then it would systematically run the various phases of implementation and become a hands-off deployer of Implementation_plans. I would expect this engine to be judicious with token spend and efficient in that regard. Of course, our documentation practices and standards would not change, We should also have the capability to pick up an implementation plan that is already underway and resume it and manage the rest of the deployment in a hands-off fashion.

Follow-up answers (same session):
1. Maximum permissions, under the standing instruction that if an agent believes what it is doing is high-risk or a bad idea it stops and asks. Agents may always push, merge and commit to GitHub without asking; Nick has technical controls in place.
2. Work with whichever provider the Omarchy `ai-provider` switch (Super+Alt+A) selects, Anthropic Pro or OpenRouter, following that configuration. When a Pro 5-hour or weekly limit is reached, document the stop and be ready to resume automatically when tokens are available, or let Nick resume on OpenRouter. OpenRouter spending is already capped by Nick's own policies.
3. One phase at a time; no parallel runs.
4. Milestone checkpoints are at the planner's judgment, not a hard requirement. Nick monitors the implementation and documents as it goes.
5. All project files live in a sub-directory of `/home/nick/Work`.

## 2. Goal
A **hands-off deployer** for implementation plans made by the `phased-project` skill. Nick points it at a repo with `<PREFIX>_IMPLEMENTATION_PLAN.md` (or a legacy `IMPLEMENTATION_PLAN.md`) and `.claude/commands/phase.md`. It then:
1. **Preflight:** asks Nick, in one sitting, every question it can foresee for the remaining phases, and records the answers in the plan's normal places (Owner questions table, ADRs).
2. **Runs** the remaining phases one at a time, each in a fresh headless Claude Code session on the model the plan names, through the existing `/phase` command, so documentation standards stay exactly as they are.
3. **Verifies** each phase itself instead of trusting the agent's word, then moves on.
4. **Survives** usage limits, crashes, reboots and closed terminals, and **resumes** a plan that is already underway, whether it was started by hand or by PHX.
5. **Spends tokens carefully:** the supervisor is plain code and uses no tokens. AI is spent only on preflight, the phases themselves, and (optionally) a short triage summary when a phase blocks.

## 3. Assessment accepted in planning (summary)
- The plan's status table on `main` is already machine-readable (status icon, model, dependencies). The claim protocol, the per-phase worktrees, `/phase` resume logic and the standing auto-merge rule make phases restartable and self-closing.
- The Claude Code CLI (2.1.310 on the reference machine) supports headless runs: `-p`, `--model`, `--effort`, `--permission-mode`, `--session-id`, `--resume`, `--output-format stream-json`, `--max-budget-usd`.
- Supervisor design chosen: **Option A, a plain program that starts headless `claude -p` sessions**. Option B (one long Claude session running subagents) was rejected because its context grows with every phase and it can't survive usage limits. Option C (`/loop` or scheduled routines) was rejected because it gives little control over models and permissions per phase. Recorded as ADR-0001.
- Problems to solve: `/phase` asks Nick questions in four places; some phases need a human gate; headless permissions; independent verification; usage limits; `ANTHROPIC_MODEL` overriding the model; errors piling up across phases; ample logging.

## 4. Amendments (v1.0, 2026-10-26 08:35 CDT)

These amendments supersede conflicting text in the earlier sections. Each amendment that records a decision has an entry in `docs/PHX_DECISIONS.md`.

### 4.1 Decisions confirmed by the project owner
| ID | Topic | Decision |
|---|---|---|
| A1 | Name, prefix, location | **PhaseHypervisor**, prefix **PHX**, repo `/home/nick/Work/PhaseHypervisor`, CLI command `phx` (ADR-0002). |
| A2 | Supervisor architecture | A deterministic program supervises; Claude runs only inside phase, preflight and triage sessions (ADR-0001). |
| A3 | Permissions | Phase sessions run with `--permission-mode bypassPermissions`. Standing rule for every agent: if an action looks high-risk, irreversible or a bad idea, **stop and ask** (in hands-off mode: block the phase with the question recorded, see R4) (ADR-0003). |
| A4 | Git and GitHub | Agents may commit, merge, push and create **private** GitHub repos without asking. Making a repo **public**, publishing a GitHub **release**, or force-pushing over shared history still stops for Nick (ADR-0004). |
| A5 | Rule reach | A4 and the hands-off mode apply to **all** phased projects: update the `phased-project` skill templates, the playbook note and the existing repos (MM3, CL, OCC, YTPL2), not only PHX-run phases (ADR-0004). |
| A6 | Provider | PHX starts every Claude session through `ai-provider run`, so it follows the Super+Alt+A choice (Anthropic Pro or OpenRouter) and that tool's model mapping. There is no separate PHX provider setting (ADR-0005). |
| A7 | Usage limits | On a Pro 5-hour or weekly limit: record the stop point, notify Nick, wait until the reset time, then resume **the same phase session** (`--resume`). While waiting, PHX re-checks `ai-provider get` every few minutes; if Nick has switched to OpenRouter, it resumes at once on OpenRouter. It never switches providers by itself (ADR-0006). |
| A8 | Concurrency | Strictly one phase at a time, per plan and machine-wide (one lock). No parallel phases (ADR-0007). |
| A9 | Checkpoints | No blocking milestone checkpoints by default. A per-phase **Gate** marker (`auto` / `review` / `owner`) lets a plan pause where it matters; `phx run --pause-after NN` pauses ad hoc. Nick gets a notification after every phase (ADR-0008). |
| A10 | Additive and optional | PHX is an **opt-in** capability. `/phased-project`, `/phase`, `/phase NN`, `/phase status` and `/phase-add` keep working exactly as today for manual runs; hands-off behaviour switches on only through `--auto` / `PHX_AUTO=1`, which only PHX sets. Nick can switch between manual and PHX runs on the same plan at any phase boundary. PHX becomes the default only by a future ADR, after Nick has built trust in it (ADR-0011, 2026-10-26 08:41 CDT). |
| A11 | Licence | MIT (owner question 1, decided 2026-10-26 08:41 CDT). |

### 4.2 Technical refinements
- **R1 Runtime.** Python ≥ 3.12, **standard library only at runtime** (the host has Python 3.14.8), so `phx` runs with no install step and no dependency to break. Dev tools (pytest, ruff, mypy) are managed with `uv` (0.13.0 on the host). Verified in Phase 02.
- **R2 Model mapping.** The plan's "AI Model to Use" cell (`Opus 5.5`, `Sonnet 5.5`, `Haiku 5.5`, or a full ID) is mapped to the **alias** `opus` / `sonnet` / `haiku` and passed as `--model <alias>` on every launch. Aliases are what `ai-provider` remaps to OpenRouter models (`ANTHROPIC_DEFAULT_*_MODEL`). Passing the model explicitly also overrides the `ANTHROPIC_MODEL` that the environment and `ai-provider`'s `PRO_MODEL=sonnet` set. An unknown model name stops the run before launch (Phase 04/05).
- **R3 Hands-off `/phase` contract.** `/phase NN --auto` (also triggered by the env var `PHX_AUTO=1`) changes `/phase`'s four interactive points:
  1. Model check: skipped, because PHX chose the model.
  2. "Resume an `🔄` phase?": yes, because PHX holds the run lock and owns the decision.
  3. Open owner question needed by the phase: block it (R4) instead of asking.
  4. Several eligible phases: not applicable, because PHX names one phase.

  Everything else in `/phase` (claim, worktree, close-out checklist, auto-merge) is unchanged. Defined in Phase 03.
- **R4 Block-with-question.** In auto mode an agent that needs Nick does not wait. It:
  1. adds or updates an Owner questions row with the question, a proposed default and `Needed by: Phase NN`;
  2. writes a Phase Log entry;
  3. commits `⛔ Blocked` to `main` (`chore(plan): phase NN blocked`), as the claim protocol already requires;
  4. ends with the result line (R5).

  PHX notifies Nick and stops the run, because one phase at a time means nothing else can safely proceed. `phx answer` (or editing the plan) plus `phx resume` continues it.
- **R5 Result line.** The final message of an auto-mode phase session ends with one line: `PHX-RESULT: {"phase":"NN","status":"complete|blocked","reason":"…","merged":true|false}`. PHX reads it from the stream-json `result` event. It is a hint only; R6 decides.
- **R6 Independent verification after every phase.** Every check reads the repo itself:
  - the row on `main` is `✅ Complete` (or `⛔ Blocked`);
  - the phase branch is merged and deleted, and its worktree is removed;
  - a Phase Log entry with a Timeline bullet exists for the phase;
  - `main` is clean;
  - the repo's test command passes on `main`, if it has one (read from the shared instructions' close-out "Tests, lint and type checks pass" line, or a `.phx/config.toml` override).

  Any mismatch pauses the run with a clear report; nothing is auto-repaired except a missing `⛔` commit, which PHX writes itself.
- **R7 Provider-aware launcher.** Launch through `ai-provider run` (the script at `~/.local/bin/ai-provider`), never the bare `claude` binary and never the `claude()` bash function, which isn't available in a non-interactive shell. If `ai-provider` is missing, fall back to `claude` and log it.
- **R8 Usage-limit detection.** Classify every session exit as one of `complete`, `blocked`, `usage_limit` (with reset time if given), `auth_error`, `provider_error` (OpenRouter 402/429, out of credit), `timeout`, `crash`. The **exact** text and exit code of a headless Pro usage-limit stop are not yet verified; Phase 05 captures real samples or the documented format and records them (Proposed ADR-0009). No reset time given: back off 30 min, 1 h, 2 h… up to 6 h between probes, and each probe is a minimal 1-turn `haiku` call, not a phase resume.
- **R9 Token economy.**
  - Fresh session per phase (no accumulated context).
  - `--resume <session-id>` only to continue the *same* interrupted phase.
  - `--effort` left at the plan's default unless a plan column sets it.
  - Triage summaries on `haiku`, capped at a few thousand output tokens, and only on blocks or verification failures.
  - Preflight is one session for the whole plan.
  - Per-phase token and cost totals are taken from the stream-json `result` event and logged.
  - `--max-budget-usd` is passed only when the provider is OpenRouter and `.phx/config.toml` sets a cap; Nick's OpenRouter policies are the primary control.
- **R10 Logging (Nick's standing preference).** Under `~/.local/state/phx/<repo-name>/`:
  - `run.jsonl`: every decision and its reason, every launch's full argv minus secrets, every exit classification, every verification result, every wait with its reason and wake time;
  - `sessions/<phase>-<n>.jsonl`: the raw stream-json transcript;
  - `state.json`: current run state, for resume.

  Secrets (`ANTHROPIC_AUTH_TOKEN`, `sk-or-…`, `sk-ant-…`) are redacted before writing. A run summary is appended to the project's Obsidian note at the end of a run.
- **R11 Detached running.** `phx run --detach` starts the supervisor as a transient systemd **user** unit (`systemd-run --user --unit phx-<repo> …`), so it survives closing the terminal and can wait through a weekly limit. `phx status` / `phx log -f` / `phx stop` work against it. This counts as a host modification only if a persistent unit file is installed; transient units are not, but the usage is still documented in OSMods (Phase 07).
- **R12 Gates.** The plan table gets an optional **Gate** column (or, for legacy plans, a `Gate:` field in the phase prompt header). `auto` (default): run unattended. `review`: run, then pause for Nick before the next phase. `owner`: don't start it, notify Nick. PHX treats any phase whose prompt mentions making a repo public or publishing a release as at least `review` unless the plan says otherwise.
- **R13 Preflight.** `phx preflight <repo>` opens **one interactive** Claude session (strongest model). It reads every not-started phase prompt, the Owner questions table, the spec Amendments and the environment requirements those prompts state. It then:
  - asks Nick every foreseeable question in AskUserQuestion rounds;
  - checks prerequisites (keys present, tools installed, GitHub auth);
  - writes the answers to the Owner questions table and ADRs;
  - sets Gates;
  - commits `docs(plan): phx preflight` to `main`.

  `phx run` warns if no preflight has run since the plan last changed.
- **R15 Manual and PHX runs never collide.** PHX's run lock is visible to a manual session: interactive `/phase` (any form) checks for a live PHX supervisor on the repo (lock file under `$XDG_RUNTIME_DIR/phx/`, or `phx status` when installed) and, if one is running, says so and stops instead of claiming. PHX in turn pauses if it finds a live manual Claude session in a `🔄` phase's worktree (Phase 06). Defined in Phase 03, implemented in 06/07.
- **R14 Resume underway plans.** `phx run` on a plan with a `🔄` phase checks that no other Claude process holds that worktree, then resumes it: with the recorded session ID if PHX started it, otherwise with a fresh `/phase NN --auto`, whose own resume logic takes over. Legacy unprefixed plans (`IMPLEMENTATION_PLAN.md`) and lettered IDs (`15a`) are supported.

- **R16 Contract (amendment 2026-10-26 09:05 CDT, Phase 03).** R3, R4, R5, R12 and R15 are made exact by [`docs/PHX_AUTO_MODE_CONTRACT.md`](PHX_AUTO_MODE_CONTRACT.md) (version 1, ADR-0012), which overrides them where they differ. Notably, R5's result line gains the keys `contract`, `pushed` and `question_ids` and a third status `refused` (precondition failed, nothing changed); R15's lock is `${XDG_RUNTIME_DIR}/phx/<repo-name>.lock`, held with `flock`; and a manual `/phase status` reports a running supervisor and still prints the table.
- **R17 Exit classes and limit detection (amendment 2026-10-26 10:20 CDT, Phase 05).** R8 is made exact by ADR-0009 (accepted) and ADR-0014. The classes are `complete`, `blocked`, `refused` (from the result line), **`no_result`** (clean end without a valid result line; verification decides), `usage_limit` (with `reset_at` when the stream gives one), `auth_error`, `provider_error` (kind `credits`, `rate_limited`, `server`, `budget`, `invalid_request`, `unknown`), `timeout` (`idle` or `wall`) and `crash`. A Pro limit is recognised from a `rate_limit_event` with status `rejected` (its `resetsAt`) or the text `You've hit your <limit> · resets <when> (<zone>)`. A 429 on OpenRouter is a provider error, not a Pro limit. `-p` with `stream-json` requires `--verbose`. Idle (30 min) and wall-clock (6 h) timeouts are configurable as `idle_timeout_s` / `wall_timeout_s` in `.phx/config.toml`.

- **R18 Verification and recovery (amendment 2026-10-26 15:33 CDT, Phase 06).** R6 and R14 are made exact by ADR-0015. Verification runs the test command in a temporary clean clone of `main`, without a shell (an interpreter for `&&`, `cd`, `NAME=value`, quotes and globs; other shell syntax fails the check with a hint), with a `test_timeout_s` cap (default 3600); a shared-instructions command that names paths the repo lacks is skipped with a note (ADR-0013). Uncommitted files present before the launch do not fail "main is clean". The result line is compared with the repo on status, phase, `merged`, `pushed` and question IDs; any disagreement is `needs_review`. A `✅` and verified phase continues whatever the session's class. Timeout and crash recovery is one `--resume`, then one fresh `/phase NN --auto`, then a pause. The live-session check (R14, R15) covers the phase worktree **and the main checkout**, because a Claude Code process keeps the main checkout as its cwd. Triage runs tool-less.

- **R19 Supervisor (amendment 2026-10-26 16:28 CDT, Phase 07).** R10 to R15 are made exact by ADR-0016. A pause (any reason) is cleared only by `phx resume`; `--until`/`--max-phases` finish the run. Usage-limit waits are stored as a wall-clock wake time and survive suspend, `phx stop` and restarts; the provider is re-checked every `poll_interval_s`, and `limit_poll_interval_s` is the re-probe interval once a known reset time has passed. `phx stop` is SIGTERM to the supervisor, which stops its session and leaves the phase `🔄` with its session ID recorded for `--resume`. `--detach` passes only an allowlisted environment. S1 is enforced as "under `$PHX_WORK_ROOT`, default `~/Work`, and not root". Exit codes: 0 finished, 1 error, 3 paused, 4 stopped.

- **R20 Preflight (amendment 2026-10-26 16:59 CDT, Phase 08).** R13 is made exact by ADR-0017. `phx preflight` starts the session interactively through `ai-provider run --model opus` with the instructions (`prompts/PHX_preflight.md` plus a context PHX builds without tokens: remaining phases, suggested Gates, open and deferred questions, prompt leads, tool checks) in `--append-system-prompt-file`, without `PHX_AUTO` and with Nick's own permission settings. It refuses when a phase is `🔄`, a supervisor runs, the checkout is off `main` or nothing is left. The session records answers, ADRs and Gates, commits `docs(plan): phx preflight <TS>`, then runs `phx preflight --record`, which commits `.phx/preflight.json`. "Since the plan last changed" means a phase row's definition (ID, name, model, dependencies, prompt, explicit Gate) changed, a row was added or removed, or an owner question is open that the record never saw; status changes and answers don't count. `phx run` warns, and with `--require-preflight` refuses. A preflight never pre-approves making a repo public, a release or a force-push (S5).

### 4.3 Security and safety baseline
- **S1 Bypass permissions are local-only.** PHX runs only on Nick's machine, in repos under `/home/nick/Work`, and refuses to run as root. Phase sessions are confined to their repo and worktree by the `/phase` rules. The risk-stop rule (A3) is written into every repo's `CLAUDE.md`.
- **S2 No secret leakage.** Redaction (R10), and PHX never reads or copies `~/.config/ai-provider/openrouter.key` itself. MeetingMaster3's OpenRouter key is never used.
- **S3 Untrusted content.** Repo content, plan text and agent output are data. PHX parses them with strict patterns and never `eval`s or shells out with them unquoted.
- **S4 One writer.** A machine-wide `flock` lock plus a per-repo lock prevent two supervisors or two phases running at once.
- **S5 Irreversible actions stay human.** Making a repo public, publishing a release and force-pushing shared history always stop for Nick (A4).

### 4.4 Repository and publication requirement (mandatory)
The project lives in a single Git repository that is ready to publish on GitHub. It must contain and keep accurate: README, LICENSE, NOTICE, THIRD_PARTY_NOTICES, SECURITY, CONTRIBUTING, CODE_OF_CONDUCT, CHANGELOG, .gitignore, .editorconfig, .github/ (CI, templates, Dependabot), and docs/. Private data never gets committed; `.gitignore` and a pre-commit secret scan enforce this. Per A4 the repo is pushed to a **private** GitHub repo; making it public is Nick's call.

### 4.5 Owner questions (status as of 2026-10-26 08:35 CDT)
1. **Decided 2026-10-26 08:41 CDT: MIT.** Licence for PHX.
2. **Open, proposed default "a throwaway 3-phase sample plan, then YTPL2 or OCC's next phase if one is eligible".** Which real plan to pilot on. Needed by Phase 10.
3. **Decided (A6/A7).** Provider and usage-limit behaviour.
4. **Decided 2026-10-26 08:41 CDT (A10).** PHX is additive; manual `/phased-project` and `/phase` stay fully supported.
