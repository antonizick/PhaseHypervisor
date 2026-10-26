# PHX Phase 09: Roll out to existing projects

**Model:** Sonnet 5.5 (`/model claude-sonnet-5-5`) · **Depends on:** 03, 07 · **Branch:** `phase-09-rollout` · **Gate:** review

## Read first
`CLAUDE.md`, `prompts/PHX_shared-instructions.md` (§3 rule on files outside this repo), spec §4.1 A4, A5. `docs/PHX_AUTO_MODE_CONTRACT.md`, ADR-0004. The current skill templates (updated in Phase 03). Phase Log entries for 03 and 07.

## Goal
Every existing phased project (MeetingMaster3 `MM3`, ChessLoop `CL`, OCC `OCC`, YTPL2 `YTPL2`) supports `phx run` and follows the ADR-0004 git rules, without disturbing any work in progress.

## Tasks
1. For each repo under `/home/nick/Work` that has a `*IMPLEMENTATION_PLAN.md` and `.claude/commands/phase.md` (find them; expect the four above), check it is idle: no `🔄` row on `main`, no `phase-*` worktrees, `main` clean. **Skip any repo that isn't idle** and record it as a follow-up (it can be migrated later with `phx`'s migration notes).
2. In each idle repo, as one commit `chore(phx): adopt hands-off phase contract` on `main`:
   - `phase.md`: add step 0 (PHX check), the trigger paragraph, the "Hands-off mode" section and `PHX-CONTRACT: 1` from the skill's `templates/phase-command.md`, keeping repo-specific wording (e.g. MM3's ADR references).
   - shared instructions: §1 step 4 and step 6 pointers, the new §1b from the template, the `PHX-RESULT` note in the final-message item; close-out merge item per ADR-0004.
   - `CLAUDE.md`: ADR-0004 git rule replaces "Never push…" (keep any stricter repo-specific rule and flag it to Nick rather than loosening it silently); Risk rule section.
   - plan: add the Gate column (`auto` by default; `review` for release/publication phases such as MM3 Phase 16) and its legend.
   - an ADR in that repo's decisions log recording the adoption, linking to ADR-0004 here.
   - its Obsidian project note: a timestamped log line.
   - push if the repo has a remote (ADR-0004).
3. Run `phx plan <repo>` on each migrated repo and confirm it reports `PHX-CONTRACT: 1` and the expected next phase.
4. Add a user-level slash command `~/.claude/commands/phx.md` (`/phx status|run|preflight [repo]`) that runs the CLI and summarises its output, so Nick can drive PHX from inside Claude Code. Document it in the user guide.
5. Update the skill's "Adopting the system in an existing repo" section with a "Migrating to the hands-off contract" checklist (the steps above), and mirror it in the playbook note.
6. Update the PHX tests' fixture copies of these plans to their migrated versions.

## Out of scope
Running any phase of those projects (Phase 10 pilots one).

## Tests
`phx plan` on each migrated repo; `grep` that no "Never push" remains in any migrated repo's rules; full PHX test suite with refreshed fixtures.

## Acceptance criteria
- Every idle repo is migrated, committed and pushed (if it has a remote); every skipped repo is listed with the reason.
- Interactive `/phase` still behaves as before in those repos (read the diff to confirm).

## Phase-specific docs
Skill and playbook sections, user guide (`/phx`), each repo's ADR and vault note, CHANGELOG here. Then the standard close-out checklist.
