# PHX Phase 12i: `phx run --only NN` (one named phase)

**Model:** Opus 5.5 (`/model claude-opus-5-5`) · **Depends on:** 12h · **Branch:** `phase-12i-run-only` · **Worktree:** `../PhaseHypervisor-phase-12i` · **Gate:** auto

Lucent2 Phase 20k lets Lucent plan a tuning change request as a new phase with `/phase-add` and, after Nick's one yes, have PHX build **only that phase** unattended. Today `phx run` always takes the lowest eligible phase and ends the run at the first owner-gated phase or the first other `🔄`. In the Lucent2 plan 20l, 20m and 20n are eligible and owner-gated, so a newly planned 20o is never reached, and `--until` and `--max-phases` cannot pin one phase. This phase adds `--only NN`: the supervisor picks exactly that phase, runs it with everything PHX already does, and ends (ADR-0036).

## Read first
`CLAUDE.md` (risk rule), `prompts/PHX_shared-instructions.md`, **ADR-0036** (this phase's decisions), ADR-0007 (one at a time), ADR-0008 (gates), ADR-0011 (coexistence), `docs/PHX_AUTO_MODE_CONTRACT.md` §2, §4.3, §7 and §8, `src/phx/cli.py` (`run`/`resume` arguments, `_forward_args`, `_cmd_run`), `src/phx/supervisor.py` (`RunOptions`, `_select`, `_choose`, `_gate_before`, `_gate_after`, `_limits_reached`, the dry-run path near `:1188`), `src/phx/plan.py:next_eligible`, `tests/` for the supervisor and CLI.

## Nick's request (verbatim intent, 2026-11-09 17:39 CST)
Chosen by Nick in the Lucent2 Phase 20k session, from: "Add phx --only (Recommended): Plan a small PHX phase adding `phx run --only NN`, which runs that one phase with PHX's locks, waits, verification and notices. 20k builds and tests against that interface with a fake phx. The live end-to-end run waits until PHX ships it." The change request Lucent2 20k wrote is restated under Tasks.

## Decisions already made (ADR-0036)
- `--only NN` changes **which phase** the supervisor picks, nothing else. Contract version stays 1.
- Other phases' states never stop or redirect an `--only` run: other eligible phases, other owner gates, other `🔄` phases (one being run by hand), other `⛔` phases.
- Gates still apply to `NN` itself: `owner` refuses (R12), `review` runs and then ends the run.
- Lucent2 detects support by finding `--only` in `phx run --help`, and reads `state.phases[NN].cost_usd` from `phx status --json` for its daily cost cap.

## Goal
`phx run --only 20o ~/Work/Lucent2` builds 20o, and only 20o, while 20l, 20m and 20n are eligible and owner-gated, then exits 0 if 20o ended `✅ Complete`.

## What exists (verified 2026-11-09 17:39 CST; re-check before relying on it)
- `cli.py` adds `--detach`, `--pause-after`, `--until`, `--max-phases`, `--dry-run` to both `run` and `resume`; `_forward_args` passes them to a detached unit (not `--dry-run`); `_cmd_run` builds `RunOptions` and validates with `_phase_arg`.
- `supervisor.py:RunOptions` has `pause_after`, `max_phases`, `until`, `dry_run`, `resume`, `require_preflight`, `test_check`. `_select` calls `plan.next_eligible` and `_choose`, then applies `--until`. `_choose` ends the run when several phases are `🔄` (`several_in_progress`), when a `🔄` phase is owner-gated (`owner_gate`), on a `⛔` phase with open questions (`blocked`), and returns the next eligible otherwise. The live-session check (`check_resumable`) runs only for a `🔄` resume candidate. `_gate_before` refuses `owner`; `_gate_after` pauses after `review`.
- `plan.py:next_eligible` returns the lowest `⬜` phase with dependencies `✅` and no open question, plus the `🔄` list.
- The dry-run loop near `supervisor.py:1188` prints each phase it would run, with its gate.
- `phx status --json` reports `state.phases[<id>].cost_usd` (`state.py:PhaseTotals`).

## Tasks
1. **CLI.** Add `--only NN` to `run` and `resume` (help text: `run only phase NN, then stop`). Validate with `_phase_arg`. `--only` with `--until`, `--max-phases` or `--pause-after` is an argument error (`EXIT_ERROR`, one stderr line). Pass it through `_forward_args` for `--detach`. Add `only: str | None` to `RunOptions`.
2. **Selection.** With `only` set, `_select` skips `next_eligible` and `_choose`'s cross-phase rules, and picks `NN` itself:
   - not in the table → end `FAILED` before any launch, rule `only_unknown`;
   - `✅ Complete` → end `FINISHED`, rule `only_done` (nothing to do; exit 0 only if the run completed it, so a second call reports it as already complete without launching);
   - a dependency not `✅` → end `PAUSED`, rule `only_deps`, naming them;
   - open owner questions needed by `NN` → end `PAUSED`, rule `blocked`, with the question IDs (as today);
   - `⬜` → `phase_prompt`; `🔄` → the same resume logic as today for that phase, including `check_resumable` and a recorded session; `⛔` with no open question → resume per contract §4.3.
   Every other phase's status is ignored.
3. **Gates and the end.** `_gate_before` still refuses `owner` for `NN`. After `NN` completes, the run ends `FINISHED` with reason `--only NN done`, whatever its gate (a `review` gate has no next phase to pause before). A blocked or failed `NN` ends as today.
4. **Exit codes.** `0` when `NN` ended `✅ Complete` in this run or was already complete; non-zero (as today's mapping) for blocked, paused, failed and refused. Document the mapping in the user guide.
5. **Dry run.** `phx run --only NN --dry-run` prints only `NN` with its gate and why, launches nothing, and still runs the test-command check unless `--skip-test-check`.
6. **Locks and coexistence.** Unchanged: `phx.lock`, the per-repo lock, and the manual `/phase` check (contract §8). Nothing in the contract changes.
7. **Docs.** README command row, `docs/PHX_USER_GUIDE.md` (what `--only` does, what it ignores, the refusals, exit codes), `docs/PHX_ARCHITECTURE.md` (selection), CHANGELOG, a spec amendment for the new option.

## Out of scope
Several named phases in one run; changes to the hands-off contract or the phased-project skill; anything in Lucent2.

## Tests
- `--only` picks `NN` while a lower `⬜` phase is eligible, while a lower phase is owner-gated, and while another phase is `🔄` (being run by hand).
- Each refusal: unknown ID, complete, dependency not complete, open question, owner gate.
- `🔄 NN` resumes with the live-session check; `⛔ NN` with answered questions resumes.
- The run ends after `NN` with reason `--only NN done`, also for a `review` gate.
- Argument errors with `--until`, `--max-phases`, `--pause-after`; `--detach` forwards `--only`.
- Dry run prints only `NN`.
- `phx run --help` contains `--only`.
- `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src` and pre-commit stay clean.

## Acceptance criteria
- `phx run --only 20o --dry-run ~/Work/Lucent2` (or any repo with a lower owner-gated eligible phase) lists only the named phase. Without a 20o in that plan, check the same with a fixture plan and say so.
- `phx run --help` shows `--only NN`, so Lucent2's Settings check `phx_only` passes once this is installed (`uv tool install --reinstall` or the repo's install path).
- Without `--only`, every existing test still passes unchanged: today's behaviour is untouched.

## Phase-specific docs
README, `docs/PHX_USER_GUIDE.md`, `docs/PHX_ARCHITECTURE.md`, CHANGELOG, spec amendment. Then the standard close-out checklist.
