# PHX Phase 04: Plan parser & eligibility engine

**Model:** Opus 5.5 (`/model claude-opus-5-5`) · **Depends on:** 02, 03 · **Branch:** `phase-04-plan-parser`

## Read first
`CLAUDE.md`, `prompts/PHX_shared-instructions.md`, spec §4.2 R2, R6, R12, R14, `docs/PHX_AUTO_MODE_CONTRACT.md`. Phase Log entries for 02 and 03.

## Goal
A pure, well-tested `phx.plan` module that turns any phased-project repo into a typed model: phases, their status **as on `main`**, models, dependencies, gates, owner questions, the test command and live branches/worktrees. It answers "what runs next, and is anything inconsistent?"

## Tasks
1. Locate the plan: `<PREFIX>_IMPLEMENTATION_PLAN.md` (prefix from `CLAUDE.md` or the filename) or legacy `IMPLEMENTATION_PLAN.md`; always read it via `git show main:<file>`, never the working tree.
2. Parse the phase table by **header names**, not column positions (`Phase`, `Phase Name`, `AI Model to Use`, `Depends on`, `Status`, `Prompt…`, optional `Gate`). Tolerate extra columns, `none`, comma lists, `n/a`.
3. Phase ID ordering: `NN` then letters (`15` < `15a` < `15b` < `16`); reject malformed IDs with a clear error.
4. Status from icon **or** word; flag rows with zero or two icons.
5. Model → alias (R2): `Opus*`→`opus`, `Sonnet*`→`sonnet`, `Haiku*`→`haiku`, `Fable*`→`fable`, full IDs `claude-<family>-…` by family; anything else → `UnknownModel` error.
6. Gate: column, else `**Gate:**` in the prompt header, else `auto`; any prompt that mentions making a repo public or a GitHub release is at least `review` (R12).
7. Owner questions table: id (string), text, status, needed-by phase IDs, per contract §3 (a question is open if and only if its Status cell starts with `Open`, any case). Also read the `PHX-CONTRACT: <n>` marker from `.claude/commands/phase.md` (contract §10) into the model; a missing marker or unknown version is an error PHX reports before launching.
8. Test command: `.phx/config.toml` override, else the backticked commands on the shared instructions' "Tests, lint and type checks pass" line, else none.
9. Live state: `git branch --list 'phase-*'`, `git worktree list --porcelain`, last commit time per worktree, uncommitted-change count; detect drift exactly as `/phase status` defines it.
10. `next_eligible(plan)`: the lowest ⬜ phase with all deps ✅ and no open owner question needed by it; return a reason object for every non-eligible phase (for logging). `🔄` phases are reported separately as resume candidates.
11. `phx plan <repo>` prints the parsed table, next phase, drift and open questions (human and `--json`).
12. Contract support: detect `PHX-CONTRACT: 1` in `.claude/commands/phase.md`; report "repo not yet migrated" otherwise.

## Out of scope
Launching anything (05); changing any repo.

## Tests
Fixtures: copy the current plans and `phase.md` of MM3, CL, OCC and YTPL2 into `tests/fixtures/plans/` (read-only copies; strip nothing sensitive is expected, but check). Synthetic plans for: lettered IDs, missing Gate column, malformed rows, unknown model, open question blocking, drift cases, legacy unprefixed name. Git-backed tests build throwaway repos in `tmp_path`.

## Acceptance criteria
- `phx plan` on each of the four real repos prints a correct table and next phase (check by hand against `/phase status` logic) without touching them.
- 100 % branch coverage of `plan.py` ordering, eligibility and model mapping.

## Phase-specific docs
`docs/PHX_ARCHITECTURE.md` (plan model), user guide stub for `phx plan`, CHANGELOG. Then the standard close-out checklist.
