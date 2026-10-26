# PHX Phase 03: Hands-off `/phase` contract & standing rules

**Model:** Opus 5.5 (`/model claude-opus-5-5`) · **Depends on:** 01 · **Branch:** `phase-03-auto-phase-contract` · **Gate:** review

## Read first
`CLAUDE.md`, `prompts/PHX_shared-instructions.md`, spec §3 and §4.2 R3, R4, R5, R12, §4.1 A3, A4, A5. ADR-0003, ADR-0004, ADR-0008. The skill at `~/.claude/skills/phased-project/` (SKILL.md and every template) and the playbook `/home/nick/Documents/04 Resources/Claude Code Phased Project Method.md`. MeetingMaster3's `.claude/commands/phase.md` and `prompts/MM3_shared-instructions.md` as the reference implementation. Phase Log entry for 01.

> **Note (2026-10-26 08:44 CDT):** the ADR-0004 git wording was already applied to the skill (`SKILL.md` "Git authority" section, templates `CLAUDE`, `_shared-instructions`, `IMPLEMENTATION_PLAN`, `phase-add-command`), the playbook and Nick's global `~/.claude/CLAUDE.md` during planning, at Nick's request. Verify it, keep it consistent, and don't redo it. The rest of this phase is unchanged.

## Goal
Define the hands-off mode of `/phase` precisely and make it, plus the new risk and git/GitHub rules, part of Nick's standard method. After this phase, every newly bootstrapped project supports `phx`. Existing repos are migrated in Phase 09.

## Tasks
1. Write `docs/PHX_AUTO_MODE_CONTRACT.md`, the normative contract PHX and every phase command share:
   - **Trigger:** argument `--auto` (`/phase 05 --auto`) or env `PHX_AUTO=1`. Auto mode always names a phase; `next` and `status` are unchanged.
   - **The four interactive points:** model check skipped (log the model in use in the Phase Log instead); `🔄` phase resumed without asking; an open owner question needed by the phase → block-with-question (R4); "which parallel phase" never arises.
   - **Block-with-question procedure (R4):** the exact steps, including the Owner questions row format, the `⛔` commit to `main`, and keeping the worktree and branch for resumption.
   - **Risk rule** (ADR-0003) wording, and how it maps to block-with-question in auto mode.
   - **Result line (R5):** exact grammar of `PHX-RESULT: {json}` as the last line of the final message; fields `phase`, `status` (`complete`|`blocked`), `reason`, `merged` (bool), `pushed` (bool), `question_ids` (list).
   - **Gate column (R12):** optional last column `Gate` with `auto`/`review`/`owner`; legacy fallback `**Gate:**` in the prompt header line; default `auto`.
   - **Git/GitHub authority (ADR-0004)** text, worded once so it can be pasted into templates.
   - **Coexistence (ADR-0011, R15):** manual `/phase` is unchanged when auto mode is off, except that, in every form, it first checks for a live PHX supervisor on the repo and, if one is running, reports it and stops. Specify the lock-file path PHX will use so the command can check it without `phx` installed.
   - **Versioning:** `PHX-CONTRACT: 1` marker line in `phase.md` so PHX can detect support.
2. Update the skill templates in `~/.claude/skills/phased-project/templates/` (commit or back up first; record the backup path):
   - `phase-command.md`: add the auto-mode section and the `PHX-CONTRACT: 1` marker; keep interactive behaviour byte-for-byte where auto mode is off.
   - `_shared-instructions.md`: §1 step 4 and §1 step 6 point to block-with-question in auto mode; the close-out merge item adopts ADR-0004 (merge without asking, push if a remote exists, private repo creation allowed, public/release still Nick's).
   - `CLAUDE.md` template: replace "Never push…" with the ADR-0004 rule; add the Risk rule section.
   - `IMPLEMENTATION_PLAN.md` template: add the Gate column and its legend; mention `phx preflight` / `phx run` under "How to run a phase" as optional.
   - `phase-prompt.md`: optional `· **Gate:** …` in the header.
   - `phase-add-command.md`: new rows include a Gate cell.
3. Update `SKILL.md`: the phase design rule "pushing or publishing requires Nick's explicit confirmation" becomes the ADR-0004 rule; add a short "Hands-off runs (PHX)" section pointing to `docs/PHX_AUTO_MODE_CONTRACT.md` and stating that release phases default to Gate `review`.
4. Mirror every change in the playbook note (method changes must stay in sync), with a timestamped changelog line there.
5. Apply the new templates to **this** repo: regenerate `.claude/commands/phase.md`, update `prompts/PHX_shared-instructions.md` and `CLAUDE.md` only where they differ from what Phase 00 already wrote.
6. Write a manual test script `docs/PHX_AUTO_MODE_CONTRACT.md#manual-check`: steps for Nick (or Phase 10) to confirm a real `/phase NN --auto` session blocks correctly and prints the result line. Do not spend tokens running it now.

## Out of scope
Changing MM3, CL, OCC or YTPL2 (Phase 09). Any Python code.

## Tests
`grep` checks: `PHX-CONTRACT: 1` present in the template and this repo's `phase.md`; no "Never push" remains in templates or SKILL.md; `grep -rn '{{' ` in this repo is empty; the template still renders (substitute dummy values and check no placeholder is left unmatched).

## Acceptance criteria
- The contract document is complete and unambiguous enough that Phase 04/05/06 can implement against it without asking.
- Skill, templates, playbook and this repo agree; interactive `/phase` behaviour is unchanged when auto mode is off (ADR-0011): show a diff of the template with auto-mode text removed against the previous template, and it must match apart from the ADR-0004 git wording and the PHX-running check.
- The playbook note says plainly that PHX is optional and manual runs remain the standard way until Nick decides otherwise.

## Phase-specific docs
`docs/PHX_AUTO_MODE_CONTRACT.md`, skill files, playbook note, ADR for the contract version. Then the standard close-out checklist.
