# {{PREFIX}}: {{PROJECT_NAME}} Implementation Plan

**Spec:** [`docs/{{PREFIX}}_SPECIFICATION.md`](docs/{{PREFIX}}_SPECIFICATION.md). **Decisions:** [`docs/{{PREFIX}}_DECISIONS.md`](docs/{{PREFIX}}_DECISIONS.md). **Agent rules:** [`CLAUDE.md`](CLAUDE.md). **Shared phase instructions:** [`prompts/{{PREFIX}}_shared-instructions.md`](prompts/{{PREFIX}}_shared-instructions.md)
**Last updated:** {{TIMESTAMP}} (Phase 00, planning)

> ⚠️ **Mandatory:** every agent that works on this project keeps this file accurate. **Before doing any other work, set your phase to `🔄 In progress` and commit that change to `main`** (claim protocol: `prompts/{{PREFIX}}_shared-instructions.md` §1a). Other agents read this table from `main`. At the end, set it to `✅ Complete` or `⛔ Blocked` and add a Phase Log entry. See `CLAUDE.md`.

## How to run a phase
Open Claude Code in `{{REPO_DIR}}` and type one of:
- `/phase`: run the next eligible phase. It checks dependencies, tells you if you're on the wrong model, resumes an `In progress` phase, and asks about any open questions it needs.
- `/phase NN`: run a specific phase.
- `/phase status`: show progress and what's next, without doing any work.
- `/phase-add [after NN] <request or file>`: plan a new lettered phase (`07a`) from a change request. No product work, no claim.

**Optional hands-off runs (PhaseHypervisor):** `phx preflight {{REPO_DIR}}` asks the foreseeable questions once, then `phx run {{REPO_DIR}}` runs the remaining phases unattended through `/phase NN --auto`, honouring the Gate column. Manual `/phase` stays the standard way; you can switch between the two at any phase boundary, and `/phase` stops if a `phx` supervisor is running this plan.

The agent merges a completed phase into `main` and pushes it without asking ({{OWNER}}'s standing git authority); review its close-out summary.

Each phase is claimed by a `chore(plan): start phase NN` commit on `main` and runs in its own worktree, `../{{REPO_NAME}}-phase-NN`, so parallel sessions never share a checkout. `/phase status` flags any branch or worktree whose row is not `🔄 In progress`.

{{PARALLELISM_NOTE}}

**Gate column** (read only by PhaseHypervisor; manual `/phase` ignores it): `auto` = may run unattended; `review` = pause for {{OWNER}} after it; `owner` = {{OWNER}} starts it. Empty means `auto`.

**Status values:** ⬜ Not started · 🔄 In progress · ⛔ Blocked · ✅ Complete. Always write the icon **and** the word.

## Phases

| Phase | Phase Name | Phase Purpose | AI Model to Use | Depends on | Status | Prompt to Initiate This Phase | Gate |
|---|---|---|---|---|---|---|---|
| 00 | Planning & spec refinement | Review source docs, resolve decisions, write the spec, plan and prompts | {{PLANNING_MODEL}} | none | ✅ Complete | n/a (planning session) | owner |
{{PHASE_ROWS}}

### Model rationale
{{MODEL_RATIONALE}}

### Dependency graph
```
{{DEPENDENCY_GRAPH}}
```

### Definition of done (checked in the final phase)
{{DEFINITION_OF_DONE_CHECKBOXES}}

## Owner questions
| # | Question | Status / proposed default | Needed by |
|---|---|---|---|
{{QUESTION_ROWS}}

## Phase Log
Newest entries at the bottom. Format: `### YYYY-MM-DD HH:MM TZ: Phase NN: <title> (<status>)` (timestamp from `date '+%Y-%m-%d %H:%M %Z'`, never a bare date). **The first bullet is always the Timeline:** `- **Timeline:** started <TS> (claim commit <hash>) · finished <TS> · merged <TS | not merged yet>` (add ` · blocked <TS> to <TS>` per `⛔` interval; *started* is the claim commit's time). Then bullets: built, deviations, follow-ups, tests.

### {{TIMESTAMP}}: Phase 00: Planning & spec refinement (✅ Complete)
- **Timeline:** started {{PHASE00_STARTED}} · finished {{TIMESTAMP}}
{{PHASE00_LOG_BULLETS}}
