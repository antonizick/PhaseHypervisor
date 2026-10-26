# PHX Phase 10: Pilot runs & tuning

**Model:** Opus 5.5 (`/model claude-opus-5-5`) · **Depends on:** 08, 09 · **Branch:** `phase-10-pilot-runs` · **Gate:** review

## Read first
`CLAUDE.md`, `prompts/PHX_shared-instructions.md`, spec §2, §4.2 R8, R9. User guide. Owner question 2 (pilot plan; if still open, ask Nick, or in auto mode use the proposed default). Phase Log entries for 07, 08 and 09.

## Goal
Prove PHX on real sessions and real tokens, measure what it costs, and fix what the pilots expose. **This phase spends tokens on purpose.**

## Tasks
1. **Dry run:** `phx run --dry-run` against each migrated repo; confirm the planned actions are right.
2. **Sample plan:** bootstrap a throwaway plan `/home/nick/Work/tries/phx-pilot/` (prefix `PXP`, 3 tiny phases on `haiku`/`sonnet`, e.g. write a function, its tests, its docs; no remote). Run `phx preflight` (real, interactive, short) then `phx run --detach`. Include:
   - one phase whose prompt deliberately requires an owner answer (→ block, `phx answer`, `phx resume`);
   - a forced interruption (`phx stop` mid-phase, then `phx resume`, which must continue the same session);
   - a simulated usage limit: point PHX at the Phase 05 fake for one launch via config, or, if a real limit occurs naturally, record it.
3. **Handover test (ADR-0011):** in the sample plan, run one phase by hand with `/phase`, the next with `phx run --max-phases 1`, then the next by hand again; confirm the docs and status stay consistent. Also confirm manual `/phase` refuses to start while `phx run` is active.
4. Run the contract's manual check (Phase 03 `#manual-check`) inside the pilot.
5. **Real plan** per owner question 2: run one eligible phase of the chosen project hands-off with `--max-phases 1`. Watch and log.
6. Measure per phase: tokens in/out, cache reads, cost, wall time, waits; compare against a manual `/phase` run of similar size if Phase Log data allows. Write `docs/PHX_PILOT_REPORT.md`.
7. Fix defects found (small fixes here; anything bigger → `/phase-add` a lettered phase and stop).
8. If a Pro limit or a provider toggle happened during the pilots, verify the wait/resume path against reality and update ADR-0009 if needed.

## Out of scope
Security review (11).

## Tests
Regression tests for every defect fixed; full suite green.

## Acceptance criteria
- The sample plan completes hands-off, with the block, the interruption and the limit path each exercised and logged.
- One real phase of a real project completes hands-off, documented to that project's normal standard.
- The pilot report gives measured numbers, not estimates.

## Phase-specific docs
`docs/PHX_PILOT_REPORT.md`, user guide fixes, CHANGELOG. Then the standard close-out checklist.
