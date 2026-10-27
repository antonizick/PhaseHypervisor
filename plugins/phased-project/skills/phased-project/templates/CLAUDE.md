# {{PROJECT_NAME}}: Agent Instructions

These rules apply to every AI agent working in this repository. They are **mandatory**.

## What this project is
{{ONE_PARAGRAPH_SUMMARY_AND_STACK}}

## Naming and timestamps (mandatory)
- **Project prefix: `{{PREFIX}}`.** Project documents are named `{{PREFIX}}_<NAME>` (`{{PREFIX}}_IMPLEMENTATION_PLAN.md`, `docs/{{PREFIX}}_DECISIONS.md`, `prompts/{{PREFIX}}_phase-NN-<slug>.md`…) so they can be told apart from other projects' documents without their path. Any new project-specific document gets the prefix. `CLAUDE.md`, `README.md`, `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md` and the like keep their conventional names.
- **Timestamps everywhere a date is recorded** (Phase Log, ADRs, amendments, owner questions, vault log, "Last updated"): `YYYY-MM-DD HH:MM TZ`, from `date '+%Y-%m-%d %H:%M %Z'` at the moment you write it. Never a bare date, never guessed.

## Source-of-truth documents (read before working)
| File | Purpose |
|---|---|
| `docs/{{PREFIX}}_SPECIFICATION.md` | Canonical spec. **The Amendments section overrides earlier sections.** |
| `{{PREFIX}}_IMPLEMENTATION_PLAN.md` | Phase table, status, owner questions, phase log. **Keep it accurate.** |
| `prompts/{{PREFIX}}_shared-instructions.md` | Conventions and close-out checklist for every phase |
| `prompts/{{PREFIX}}_phase-NN-*.md` | The prompt for the phase you are executing (start sessions with `/phase`) |
| `docs/{{PREFIX}}_DECISIONS.md` | ADR log; append, never rewrite |

## Mandatory documentation upkeep
Documentation is part of the deliverable. A phase is **not complete** until all of the following are done:
1. `{{PREFIX}}_IMPLEMENTATION_PLAN.md`: set the phase's status as icon plus word (`🔄 In progress` when you start; `✅ Complete` or `⛔ Blocked` at the end) and add a timestamped Phase Log entry whose **first bullet is the Timeline** (`started` = the claim commit's time, `finished` = `date` as your last step, `merged`, any `blocked` interval; format in the plan's Phase Log header), then built, deviations, follow-ups, tests. **`🔄 In progress` must be committed to `main` before any other work** (the claim protocol in `prompts/{{PREFIX}}_shared-instructions.md` §1a), because parallel agents read the status from `main`. A status that exists only on a phase branch or in a worktree does not count.
2. `CHANGELOG.md`: add entries under `[Unreleased]`.
3. Update every affected document: README, SECURITY, `docs/{{PREFIX}}_ARCHITECTURE.md`, guides, THIRD_PARTY_NOTICES, `.gitignore` / `.dockerignore`.
4. `docs/{{PREFIX}}_DECISIONS.md`: add an ADR for any non-trivial choice or deviation. If the spec changes, add an amendment.
5. **Later phase prompts:** if your work changes an assumption a later prompt relies on, edit that prompt.
6. {{#VAULT}}The Obsidian project note `{{VAULT_NOTE_PATH}}`: update the status table (icons), the `updated:` field and add a timestamped log line.{{/VAULT}}{{^VAULT}}No vault note is kept for this project: skip vault steps and say so in the close-out message.{{/VAULT}}
7. {{#OS_LOG}}Any host OS change must also be documented in `{{OS_LOG}}` (read its README first).{{/OS_LOG}}{{^OS_LOG}}Any host OS change must also be documented in the project's OS-modification log, if it keeps one.{{/OS_LOG}}

## Risk rule (mandatory)
Sessions may run with bypassed permissions. **If an action looks high-risk, irreversible or a bad idea, stop and ask {{OWNER}} instead of doing it.** In an interactive session, ask. In a hands-off session (`/phase NN --auto` or `PHX_AUTO=1`, started by PhaseHypervisor), block the phase with the question recorded (block-with-question, `prompts/{{PREFIX}}_shared-instructions.md` §1b). Examples: deleting data you did not create, touching another project's files outside the scope your prompt names, changing system-wide config not covered by the prompt, spending money beyond a stated cap, making a repo public, publishing a release, force-pushing shared history.

## Engineering rules
- Stay within the phase's scope; record out-of-scope findings as follow-ups in the Phase Log.
- Tests, lint and type checks must pass before a phase closes. {{TEST_COMMANDS}}
- Never commit secrets, personal data, private recordings, model weights or `.env` files.
- Follow the security and privacy baseline in the spec's Amendments.
- Pin and lock dependencies, and check licences before adding one.
- Git: branch `phase-NN-<slug>` in its own worktree `../{{REPO_NAME}}-phase-NN`; the main checkout stays on `main`. Conventional Commits, commit at checkpoints. **Git authority (standing instruction from {{OWNER}}):** commit, merge, push and create **private** GitHub repos without asking, at checkpoints and at close-out. Only making a repo **public**, publishing a GitHub **release**, or force-pushing shared history needs {{OWNER}}'s explicit confirmation (in hands-off mode: block-with-question). If an action looks high-risk or a bad idea, stop and ask anyway.
- Reference machine: {{MACHINE_NOTES}}
