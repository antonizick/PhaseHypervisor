# PHX: PhaseHypervisor Implementation Plan

**Spec:** [`docs/PHX_SPECIFICATION.md`](docs/PHX_SPECIFICATION.md). **Decisions:** [`docs/PHX_DECISIONS.md`](docs/PHX_DECISIONS.md). **Agent rules:** [`CLAUDE.md`](CLAUDE.md). **Shared phase instructions:** [`prompts/PHX_shared-instructions.md`](prompts/PHX_shared-instructions.md)
**Last updated:** 2026-10-26 08:35 CDT (Phase 00, planning)

> ⚠️ **Mandatory:** every agent that works on this project keeps this file accurate. **Before doing any other work, set your phase to `🔄 In progress` and commit that change to `main`** (claim protocol: `prompts/PHX_shared-instructions.md` §1a). Other agents read this table from `main`. At the end, set it to `✅ Complete` or `⛔ Blocked` and add a Phase Log entry. See `CLAUDE.md`.

## How to run a phase
Open Claude Code in `/home/nick/Work/PhaseHypervisor` and type one of:
- `/phase`: run the next eligible phase. It checks dependencies, tells you if you're on the wrong model, resumes an `In progress` phase, and asks about any open questions it needs.
- `/phase NN`: run a specific phase.
- `/phase status`: show progress and what's next, without doing any work.
- `/phase-add [after NN] <request or file>`: plan a new lettered phase (`07a`) from a change request. No product work, no claim.

Completed phases are merged into `main` and pushed by the agent (ADR-0004). Review the agent's close-out summary.

Each phase is claimed by a `chore(plan): start phase NN` commit on `main` and runs in its own worktree, `../PhaseHypervisor-phase-NN`. `/phase status` flags any branch or worktree whose row is not `🔄 In progress`.

**PHX is optional (ADR-0011):** `/phase` keeps working by hand exactly as before; hands-off runs are opt-in, and you can switch between the two at any phase boundary.

**Serial by decision (ADR-0007):** run one phase at a time, in ID order. Phase 03 has no code dependency on 02 and could technically run alongside it, but don't. **Dogfooding:** once Phase 07 is complete, the remaining phases may be run by `phx run /home/nick/Work/PhaseHypervisor` instead of `/phase` (Phase 10 does this deliberately).

**Gate column (spec R12):** `auto` = may run unattended; `review` = pause for Nick after it; `owner` = Nick starts it.

**Status values:** ⬜ Not started · 🔄 In progress · ⛔ Blocked · ✅ Complete. Always write the icon **and** the word.

## Phases

| Phase | Phase Name | Phase Purpose | AI Model to Use | Depends on | Status | Prompt to Initiate This Phase | Gate |
|---|---|---|---|---|---|---|---|
| 00 | Planning & spec refinement | Capture Nick's request and answers, resolve decisions, write the spec, ADRs, this plan and the phase prompts | Opus 5.5 | none | ✅ Complete | n/a (planning session) | owner |
| 01 | Repository foundation & governance | GitHub-ready repo: LICENSE, NOTICE, README, SECURITY, CONTRIBUTING, CoC, CHANGELOG, THIRD_PARTY_NOTICES, ignore files, .editorconfig, .github/, docs skeleton, private GitHub remote | Sonnet 5.5 | 00 | ✅ Complete | [PHX_phase-01-repo-foundation.md](prompts/PHX_phase-01-repo-foundation.md) | auto |
| 02 | Python scaffold, CLI skeleton & CI | uv project, stdlib-only `phx` package and `phx` entry point with subcommand stubs, logging/redaction core, state paths, pytest/ruff/mypy, CI, pre-commit secret scan | Sonnet 5.5 | 01 | ✅ Complete | [PHX_phase-02-python-scaffold.md](prompts/PHX_phase-02-python-scaffold.md) | auto |
| 03 | Hands-off `/phase` contract & standing rules | Define `/phase NN --auto` / `PHX_AUTO=1`, block-with-question, `PHX-RESULT` line, Gate column, risk-stop rule and new git/GitHub authority; update the `phased-project` skill templates and playbook note | Opus 5.5 | 01 | ⬜ Not started | [PHX_phase-03-auto-phase-contract.md](prompts/PHX_phase-03-auto-phase-contract.md) | review |
| 04 | Plan parser & eligibility engine | Parse prefixed and legacy plans: rows, lettered IDs, ordering, deps, status, model→alias, gates, owner questions, test command; drift detection vs branches/worktrees; fixtures from MM3, CL, OCC, YTPL2 | Opus 5.5 | 02, 03 | ⬜ Not started | [PHX_phase-04-plan-parser.md](prompts/PHX_phase-04-plan-parser.md) | auto |
| 05 | Session runner & exit classifier | Launch via `ai-provider run -p` with model alias, bypass permissions, session IDs, stream-json capture; token/cost accounting; exit classification incl. usage limits (verify ADR-0009); fake `claude` for tests | Opus 5.5 | 02 | ⬜ Not started | [PHX_phase-05-session-runner.md](prompts/PHX_phase-05-session-runner.md) | auto |
| 06 | Verifier & recovery | Post-phase independent checks (spec R6), blocked-status repair, retry/resume policy, stale-claim and orphan-worktree handling, haiku triage summary | Opus 5.5 | 04, 05 | ⬜ Not started | [PHX_phase-06-verifier-recovery.md](prompts/PHX_phase-06-verifier-recovery.md) | auto |
| 07 | Supervisor loop, state & notifications | `phx run / status / resume / stop / log / answer`, locks, `state.json`, usage-limit waits with provider re-check, `--pause-after`, gates, notify-send, `--detach` via systemd-run, vault run summary, OSMods doc | Opus 5.5 | 06 | ⬜ Not started | [PHX_phase-07-supervisor.md](prompts/PHX_phase-07-supervisor.md) | review |
| 08 | Preflight question sweep | `phx preflight`: one interactive strongest-model session that reads the remaining phases, asks Nick everything foreseeable, checks prerequisites, sets gates, records answers/ADRs and commits; staleness check in `phx run` | Opus 5.5 | 07 | ⬜ Not started | [PHX_phase-08-preflight.md](prompts/PHX_phase-08-preflight.md) | auto |
| 09 | Roll out to existing projects | Apply the Phase 03 contract and ADR-0004 rules to MM3, CL, OCC and YTPL2 (only when idle), add Gate columns, `phx` user-level slash command, skill "Running hands-off" section | Sonnet 5.5 | 03, 07 | ⬜ Not started | [PHX_phase-09-rollout.md](prompts/PHX_phase-09-rollout.md) | review |
| 10 | Pilot runs & tuning | Dry run on fixtures; a real hands-off run of a throwaway 3-phase sample plan (forced block, resume, simulated limit); one real plan per owner question 2; measure tokens and time; fix what the pilots expose | Opus 5.5 | 08, 09 | ⬜ Not started | [PHX_phase-10-pilot-runs.md](prompts/PHX_phase-10-pilot-runs.md) | review |
| 11 | Hardening, security review & QA | Threat model (bypass permissions, injection via repo text, secrets in logs, lock races), scanners, coverage, failure-injection tests, docs pass, close all follow-ups | Opus 5.5 | 10 | ⬜ Not started | [PHX_phase-11-hardening-qa.md](prompts/PHX_phase-11-hardening-qa.md) | auto |
| 12 | Release v0.1.0 | Final docs, CHANGELOG, version and tag, push to the private GitHub repo, final report with timeline, MVP sign-off; making the repo public or a GitHub release stops for Nick | Sonnet 5.5 | 11 | ⬜ Not started | [PHX_phase-12-release.md](prompts/PHX_phase-12-release.md) | review |

### Model rationale
- **Opus 5.5** (`/model claude-opus-5-5`): the `/phase` contract and skill changes (every future project depends on them), plan parsing, process supervision and exit classification, verification and recovery logic, the supervisor state machine, preflight prompt design, the pilots and the security review.
- **Sonnet 5.5** (`/model claude-sonnet-5-5`): repository governance, the scaffold, mechanical rollout of an already-specified contract to four repos, and the release.

### Dependency graph
```
00 ─► 01 ─┬─► 02 ─┬─► 04 ─┐
          │       └─► 05 ─┴─► 06 ─► 07 ─┬─► 08 ─┐
          └─► 03 ──► 04                 └─► 09 ─┴─► 10 ─► 11 ─► 12
                └──────────────────────────► 09
```
Run serially in ID order (ADR-0007).

### Definition of done (checked in the final phase)
- [ ] `phx preflight <repo>` asks foreseeable questions once and records them in the plan and ADRs.
- [ ] `phx run <repo>` runs every remaining `auto` phase of a plan serially, each on its listed model via `ai-provider`, with no human input, and verifies each one independently.
- [ ] `phx run` resumes a plan already underway (manual or PHX-started), including a `🔄` phase.
- [ ] A blocked phase records its question, notifies Nick, and continues after `phx answer` + `phx resume`.
- [ ] A Pro usage limit is detected, logged, waited out and resumed in the same session; toggling to OpenRouter during the wait resumes at once.
- [ ] Supervisor costs zero tokens; per-phase token/cost totals are logged; triage uses haiku only on failures.
- [ ] `run.jsonl` explains every decision; secrets are redacted (tested).
- [ ] `--detach` survives closing the terminal; `phx stop` stops cleanly.
- [ ] Skill templates, playbook note and MM3/CL/OCC/YTPL2 carry the auto-mode contract and ADR-0004 rules.
- [ ] With auto mode off, `/phased-project`, `/phase` and `/phase-add` behave exactly as before (ADR-0011); a plan can be handed manual → PHX → manual without problems.
- [ ] Tests, lint, type checks pass in CI; repo pushed to a private GitHub repo.

## Owner questions
| # | Question | Status / proposed default | Needed by |
|---|---|---|---|
| 1 | Licence for PHX | Decided 2026-10-26 08:41 CDT: MIT | Phase 01 |
| 2 | Which real plan to pilot hands-off after the sample plan | Open, proposed default the next eligible phase of YTPL2 or OCC (whichever has one), else sample plan only | Phase 10 |
| 3 | Provider and usage-limit behaviour | Decided 2026-10-26 08:35 CDT: follow `ai-provider`; wait, notify, auto-resume (ADR-0005, ADR-0006) | Phase 05 |
| 5 | Is PHX optional or a replacement? | Decided 2026-10-26 08:41 CDT: additive and opt-in; manual `/phased-project` and `/phase` stay fully supported (ADR-0011) | Phase 03 |
| 4 | Git/GitHub authority and reach | Decided 2026-10-26 08:35 CDT: push/merge/private repos freely, all phased projects (ADR-0004) | Phase 03 |

## Phase Log
Newest entries at the bottom. Format: `### YYYY-MM-DD HH:MM TZ: Phase NN: <title> (<status>)` (timestamp from `date '+%Y-%m-%d %H:%M %Z'`, never a bare date). **The first bullet is always the Timeline:** `- **Timeline:** started <TS> (claim commit <hash>) · finished <TS> · merged <TS | not merged yet>` (add ` · blocked <TS> to <TS>` per `⛔` interval; *started* is the claim commit's time). Then bullets: built, deviations, follow-ups, tests.

### 2026-10-26 08:35 CDT: Phase 00: Planning & spec refinement (✅ Complete)
- **Timeline:** started 2026-10-26 08:27 CDT · finished 2026-10-26 08:35 CDT
- Source: Nick's request and four follow-up answers in the Claude Code session "Design Phased Project Hypervisor" (recorded verbatim in spec §1).
- Environment checked: Claude Code 2.1.310 (headless flags present: `-p`, `--model`, `--effort`, `--permission-mode` incl. `bypassPermissions`, `--session-id`, `--resume`, `--output-format stream-json`, `--max-budget-usd`), Python 3.14.8, uv 0.13.0, gh 2.103.2 logged in as `antonizick`; `ai-provider` script, its config (PRO_MODEL=sonnet, OpenRouter alias mapping) and the `claude()` bash wrapper.
- Findings that shaped the plan: `ANTHROPIC_MODEL`/`PRO_MODEL` would silently override phase models (R2); the `claude()` wrapper is a bash function unavailable to non-interactive launchers (R7); `/phase` has four interactive points (R3).
- Decisions: ADR-0001 to ADR-0008 accepted; ADR-0009 (limit detection) and ADR-0010 (stdlib runtime) proposed.
- Open: owner question 2.
- 2026-10-26 08:44 CDT: first commit made without asking; the standing git authority was applied to the global CLAUDE.md, the skill templates and the playbook now (ahead of Phase 03, per Nick).
- 2026-10-26 08:41 CDT: Nick answered owner question 1 (MIT) and set PHX as additive and opt-in (ADR-0011, spec A10, R15).

### 2026-10-26 08:51 CDT: Phase 01: Repository foundation & governance (✅ Complete)
- **Timeline:** started 2026-10-26 08:50 CDT (claim commit 792294d) · finished 2026-10-26 08:51 CDT · merged 2026-10-26 08:51 CDT
- Built: LICENSE (MIT), NOTICE, THIRD_PARTY_NOTICES, README, SECURITY (S1–S5), CONTRIBUTING, CODE_OF_CONDUCT (Contributor Covenant 2.1 by reference), CHANGELOG, .gitignore, .editorconfig, `.github/` (bug and feature issue templates, PR template, Dependabot for github-actions and uv, placeholder CI), `docs/PHX_ARCHITECTURE.md` skeleton. Private repo `antonizick/PhaseHypervisor` created (visibility checked) and `main` pushed.
- Deviations: the prompt's copyright holder "Nick Antoncic" is a misspelling; the licence and notices use "Nick Antonizick" (the owner's name per git config and email). Owner question 1 was already decided (MIT), so no default was needed. No ADR needed.
- Follow-ups: Phase 02 replaces the placeholder CI and fills THIRD_PARTY_NOTICES with dev tools; prompt 01 should have its copyright spelling fixed (left as is, historical).
- Tests: none in scope. Every Markdown link in the new files resolves (scripted check); `gh repo view antonizick/PhaseHypervisor --json visibility` is checked at close-out.

### 2026-10-26 08:57 CDT: Phase 02: Python scaffold, CLI skeleton & CI (✅ Complete)
- **Timeline:** started 2026-10-26 08:53 CDT (claim commit 462d097) · finished 2026-10-26 08:57 CDT · merged 2026-10-26 08:57 CDT
- Built: `pyproject.toml` (uv, hatchling, no runtime deps, dev group pytest/ruff/mypy/pre-commit), `uv.lock`, `src/phx/` (`cli.py`, `__main__.py`, `paths.py`, `logging.py`, `redact.py`), `phx` console script and `python -m phx`; argparse subcommands `preflight run resume status stop log answer plan` as stubs (exit 2); `.phx/config.toml` loader with typed defaults; redacting fsync'd JSONL logger with stderr mirror; real CI (ruff, ruff format, mypy strict, pytest on 3.12 and 3.14); `.pre-commit-config.yaml` (ruff, detect-secrets 1.5.0 with `.secrets.baseline`); ADR-0010 Accepted; README dev setup, ARCHITECTURE, THIRD_PARTY_NOTICES, CHANGELOG.
- Deviations: secret scan is detect-secrets (Apache-2.0, pure Python) rather than gitleaks, which needs a Go toolchain on the host. Its baseline records three fake token fixtures in `tests/test_redact.py`. CI is triggered by `pull_request` and pushes to `main`, so the branch was verified through PR #2 before merging.
- Follow-ups: none out of scope. Later phases add modules to `docs/PHX_ARCHITECTURE.md` as built.
- Tests: 35 passed; ruff check, ruff format --check, mypy --strict src and pre-commit clean; CI green on 3.12 and 3.14 (PR #2); `python3 -m phx --version` verified from `src/` with the host Python 3.14.8 and no uv.
