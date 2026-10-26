# PHX Phase 06: Verifier & recovery

**Model:** Opus 5.5 (`/model claude-opus-5-5`) · **Depends on:** 04, 05 · **Branch:** `phase-06-verifier-recovery`

## Read first
`CLAUDE.md`, `prompts/PHX_shared-instructions.md`, spec §4.2 R4, R6, R9, R14, `docs/PHX_AUTO_MODE_CONTRACT.md`. Phase Log entries for 04 and 05.

## Goal
After any phase session ends, PHX decides from the **repo itself** what actually happened, repairs only what is safe, and picks the next action: continue, resume the same session, retry, wait, or pause for Nick.

## Tasks
1. `verify.py`: `verify_phase(repo, phase_id, classification) -> Verdict`, implementing every R6 check against `main` (status, merge, branch deleted, worktree removed, Phase Log entry with Timeline bullet, clean `main`, test command passes on a temporary clean checkout of `main`, never in the user's working tree). Each check reports pass/fail/skip with evidence.
2. Reconcile the agent's `PHX-RESULT` with the verdict; disagreement → `needs_review` with both shown.
3. Safe repairs only: if the agent blocked but did not commit `⛔` to `main`, commit it (`chore(plan): phase NN blocked (recorded by phx)`). Nothing else is auto-fixed.
4. `recover.py` decision table (document it in the architecture doc):

   | Situation | Action |
   |---|---|
   | complete + verified | next phase |
   | blocked + question recorded | pause, notify |
   | usage_limit | wait (07) then `--resume` same session |
   | timeout / crash, work in progress | one `--resume` of the same session with "continue the phase" prompt, then a fresh `/phase NN --auto`, then pause |
   | auth_error / provider_error | pause, notify (no retries that could burn credit) |
   | verification failed | pause with report |
5. Stale and orphan handling for R14: a `🔄` row whose worktree has no live Claude process (check `/proc` for a `claude` process with that cwd) is resumable; one with a live process means pause ("another session is running phase NN").
6. `triage.py`: on `blocked`, `needs_review` or verification failure, optionally (config, default on) run one `haiku` session that reads the phase's final messages and the verdict and writes a ≤ 150-word plain-English summary for the notification and run log. Capped by `--max-turns` and logged with its cost.

## Out of scope
The loop, waiting and notifications (07).

## Tests
Git repos in `tmp_path` simulating every row of the decision table, using the Phase 05 fakes; the `⛔` repair; live-process detection (mock `/proc` scan); triage with the fake.

## Acceptance criteria
- Every decision-table row is covered by a test that asserts both the action and the logged reason.
- Verification never modifies the user's main checkout except the documented `⛔` repair commit.

## Phase-specific docs
`docs/PHX_ARCHITECTURE.md` (verdicts and decision table), CHANGELOG. Then the standard close-out checklist.
