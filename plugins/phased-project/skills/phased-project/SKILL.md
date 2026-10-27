---
name: phased-project
description: >
  Bootstrap the phased-project system for a new multi-session build: refined spec with
  amendments, ADR decision log, <PREFIX>_IMPLEMENTATION_PLAN.md status table (with icons and model per phase),
  self-contained phase prompts, agent rules in CLAUDE.md, a /phase slash command for running
  sessions, a GitHub-ready repo, and an optional vault project note. Use when the user starts a new
  project from a plan, pre-plan, spec or idea document; asks for a "phased implementation plan",
  "implementation plan", "phase prompts", or to "set this up as a phased project"; or invokes
  /phased-project. Also use it to adopt the system in an existing repo ("add phases to this project").
  To insert one new phase into a plan that already exists, use that repo's /phase-add command
  (see "Injecting phases later"); to give an older repo that command, use this skill.
argument-hint: "[path to plan/spec document] [target repo dir]"
---

# Phased Project Bootstrap

This is a standard way to plan and run any multi-session build with AI agents: one plan with a status
table, one self-contained prompt per phase, and a `/phase` command that runs one phase per session.
The public guide is
<https://github.com/antonizick/PhaseHypervisor/blob/main/docs/PHX_GETTING_STARTED.md>. The source of this
skill is the PhaseHypervisor repo (`plugins/phased-project/`); change it there, not in an installed copy.
The templates are in the `templates/` folder next to this file (the skill's base directory).

Arguments: `$ARGUMENTS`, the source document path and/or the target directory. If either is
missing, ask for it.

## Settings and template markers
**Settings.** Before writing anything, look for a `## Phased-project settings` section in the user's global
`~/.claude/CLAUDE.md` (it is loaded into your context with the user's instructions). Every setting is
optional; the section itself is optional. Each one is a bullet `- Key: value`:

| Setting | Used for | When it is missing |
|---|---|---|
| `Owner` | the name used for the person the agents report to (`{{OWNER}}`) | `the owner` |
| `Work root` | where new repos go; checking prefixes are unique; `/phx <name>` | ask for the target directory; check only the target's parent |
| `Vault root` and `Vault projects folder` | the project's vault note (`{{VAULT_NOTE_PATH}}` = `<Vault root>/<Vault projects folder>/<PREFIX> Implementation Plan.md`); the `VAULT` sections | no vault note: drop the vault note output, skip vault steps, and say so in the report |
| `Method note` | the vault note's "Method:" link (`{{METHOD_LINK}}` = `[[<note file name without .md>]]`); a private copy of the playbook you keep in step with this skill | `{{METHOD_LINK}}` is a link to the public guide |
| `OS modifications log` | where host OS changes are recorded (`{{OS_LOG}}`); the `OS_LOG` sections | the close-out item reads "if the project keeps an OS-modification log" |
| `Reference implementation` | a repo bootstrapped with this skill to read when in doubt | read the PhaseHypervisor repo's own plan, prompts and commands as the worked example |
| `Project aliases` | short names `/phx` accepts (`ABC = some-repo-folder`, comma-separated) | `/phx` takes paths or folder names under the work root |

`examples/CLAUDE.user.md` in the PhaseHypervisor repo has the section with placeholders, plus the standing
rules this method expects.

**Markers.** Templates use `{{PLACEHOLDER}}` markers (`{{REPO_DIR}}` is the absolute repo path and `{{REPO_NAME}}`
its folder name, used for phase worktrees `../{{REPO_NAME}}-phase-NN`; `{{PREFIX}}` is the project code, see
"Naming and timestamps"; `{{TIMESTAMP}}` is a timestamp, never a bare date; `{{GATE}}` is `auto`, `review` or
`owner`; `{{OWNER}}` is the `Owner` setting, capitalised at the start of a sentence). Two section markers
depend on the settings:
- `{{#NAME}}…{{/NAME}}`: keep the text inside when the setting is present (`VAULT`: a vault root is set;
  `OS_LOG`: an OS-modifications log is set), otherwise delete it, markers included;
- `{{^NAME}}…{{/NAME}}`: the reverse, kept only when the setting is missing.

A dropped section that fills whole lines takes its line breaks with it. Replace every marker, then confirm
none remain with `grep -rn '{{' <repo>`.

## Outputs (all required unless marked optional)
| Artifact | Template | Purpose |
|---|---|---|
| `docs/{{PREFIX}}_SPECIFICATION.md` | (source doc, reformatted) + `templates/spec-amendments.md` | Canonical spec. The original text is kept and an **Amendments** section at the end overrides it |
| `docs/{{PREFIX}}_DECISIONS.md` | `templates/DECISIONS.md` | ADR log; append-only |
| `CLAUDE.md` | `templates/CLAUDE.md` | Mandatory agent rules, including documentation upkeep |
| `{{PREFIX}}_IMPLEMENTATION_PLAN.md` | `templates/IMPLEMENTATION_PLAN.md` | Phase table with status icons, dependency graph, definition of done, owner questions, phase log |
| `prompts/{{PREFIX}}_shared-instructions.md` | `templates/_shared-instructions.md` | Orientation, conventions and the close-out checklist shared by every phase |
| `prompts/{{PREFIX}}_phase-NN-<slug>.md` | `templates/phase-prompt.md` | One self-contained prompt per phase |
| `.claude/commands/phase.md` | `templates/phase-command.md` | `/phase`, `/phase NN`, `/phase status`, plus the opt-in hands-off mode (`--auto`, `PHX-CONTRACT: 1`; see "Hands-off runs (PHX)") |
| `.claude/commands/phase-add.md` | `templates/phase-add-command.md` | `/phase-add [after NN] <request>`: plan and insert a new phase later (see "Injecting phases later") |
| `prompts/{{PREFIX}}_change-request-template.md` | `templates/change-request.md` | Optional intake form the owner fills in for `/phase-add` |
| Vault note `<Vault projects folder>/{{PREFIX}} Implementation Plan.md` (optional: only with a vault root) | `templates/vault-project-note.md` | Vault-side status and log |
| `git init -b main` | none | Then make the first commit `docs(plan): phase 00 planning` (see "Git authority") |

## Naming and timestamps (mandatory conventions)
**Project prefix.** Every project gets a short code (`MYAPP` → `MA`, `Order Tracker` → `OT`): 2 to 4
characters, upper-case letters and digits, unique among the owner's projects (check the work root and the
vault projects folder, where set). It is asked in the first question round (propose one derived from the
project name, "(Recommended)"), recorded in `CLAUDE.md`, and stored as `{{PREFIX}}`. The reason: people read
and search documents without their folder path, and `IMPLEMENTATION_PLAN.md` from two projects look identical.
- **Prefixed with `{{PREFIX}}_`:** the project's own documents. These are `docs/{{PREFIX}}_ARCHITECTURE.md`, `docs/{{PREFIX}}_FINDINGS.md`, `docs/{{PREFIX}}_FINAL-REPORT.md` (when a project has them), `{{PREFIX}}_IMPLEMENTATION_PLAN.md`,
  `docs/{{PREFIX}}_SPECIFICATION.md`, `docs/{{PREFIX}}_DECISIONS.md`, `prompts/{{PREFIX}}_shared-instructions.md`,
  `prompts/{{PREFIX}}_phase-NN-<slug>.md` and `prompts/{{PREFIX}}_change-request-template.md`. Any further
  project-specific document added later (an architecture or threat-model note, a guide) follows the same rule.
- **Never prefixed (a tool or convention fixes the name):** `CLAUDE.md`, `README.md`, `LICENSE`, `NOTICE`,
  `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`, `THIRD_PARTY_NOTICES.md`, `.github/`,
  `.claude/commands/phase.md` and `phase-add.md`, and git branch and worktree names (`phase-NN-<slug>`,
  `../<Repo>-phase-NN`). In the shared instructions' repo layout, mark each prefixed file as such.
- The underscore is the separator (no spaces in filenames, so paths need no quoting). In prose and in vault
  note titles the same prefix is used with a space: the vault note is `<PREFIX> Implementation Plan.md`
  so it, too, is identifiable out of context.
- Inside documents, `grep '^| NN '` patterns, claim commits (`chore(plan): start phase NN`) and branch names are
  unchanged by the prefix.

**Timestamps.** Wherever a document records *when* (Phase Log, ADRs, amendments, owner-question status,
change-request forms, "Last updated", "verified", the owner's request, the vault note's log, frontmatter, changelog
release headings) write a timestamp, never a bare date: `YYYY-MM-DD HH:MM TZ` in the machine's local time
(e.g. `2026-10-20 14:32 MDT`). Get it from `date '+%Y-%m-%d %H:%M %Z'` at the moment of writing; never
guess or reuse an earlier one. When several entries land in one session, each gets its own timestamp. Date-only
text is acceptable only for things that are inherently a calendar date: a copyright year, a version's release
date quoted from an external source, or a file name such as a dated export.

## Workflow
1. **Model check:** planning deserves the strongest available model; if you are not running on it, say so and
   give the `/model` command. Run `date '+%Y-%m-%d %H:%M %Z'` now and keep it: it is Phase 00's *started* time (`{{PHASE00_STARTED}}`).
2. **Read everything.** Read the source document(s) in full, plus related notes the source links to or that
   share the project name (in the vault, if one is set). A meeting or conversation summary is a good source:
   its decisions are the owner's, its unverified claims must be verified (never copy them as facts), and its
   open questions are owner questions. Inspect the environment where it matters: hardware (`nvidia-smi`),
   toolchain versions (python, node, docker, uv, gh) and the OS. Environment facts often invalidate plan
   assumptions (for example, a host Python too new for a project's ML stack).
3. **Review and refine.** List conflicts between the documents, gaps, risky assumptions, missing
   security and privacy controls, and open questions the source leaves unresolved. Resolve what you
   can with a justified default. Unrecoverable data loss, privacy and publishing choices always go
   to the owner.
4. **Ask** (AskUserQuestion, at most 4 per round, recommended option first, labelled "(Recommended)").
   The first round always settles the project **prefix** (see "Naming and timestamps"), unless the owner gave one.
   Ask only about decisions that change what you write. If the owner asks for trade-offs instead of
   choosing, answer with an **options table (Option | Pros | Cons), a clear recommendation and its
   reasoning**, then record the choice.
5. **Write the spec** (`docs/{{PREFIX}}_SPECIFICATION.md`). Copy the source and fix only formatting. Add the
   header note "Amendments override earlier sections". Append the Amendments section
   (`templates/spec-amendments.md`) containing: owner decisions (table), technical refinements (R1…),
   a security and privacy baseline (S1…) where relevant, the repository and publication requirement,
   and owner questions with their status. Put supporting material such as catalogues in appendices.
   **Never fabricate** external facts: emails, prices, version numbers or release dates. Leave them for the phase that can verify them. (Timestamps of *your own* actions are not fabricated: take them from `date`.)
6. **Write the ADR log.** One ADR per owner decision, plus `Proposed` ADRs for assumptions a phase
   must verify.
7. **Design the phases** (rules below), then write `{{PREFIX}}_IMPLEMENTATION_PLAN.md`, the shared instructions,
   every phase prompt, `CLAUDE.md` and the `/phase` command.
8. **Create the vault note** (only with a vault root) in `<Vault root>/<Vault projects folder>/`, linking the
   source notes with `[[wikilinks]]`. Without a vault root, skip it and say so in the report.
9. **Verify:** every link in the plan resolves (`ls` each `prompts/…` and `docs/…` path); every
   table row has exactly one status icon; no `{{` remains; each prompt's "Depends on" matches the
   table; the claim protocol (§1a of the shared instructions) and step 4 of `/phase` are present; `grep '^PHX-CONTRACT: 1' .claude/commands/phase.md` matches; every row has a Gate cell.
10. **Report to the owner:** a phases table (number, name, model), refinements made, open questions with
    the phase that needs each answer, and how to start (`/phase`). Make the first commit (`docs(plan): phase 00 planning`) and report its hash.

## Git authority (method convention)
The templates give agents this standing authority: commit, merge, push and create **private** GitHub repos without asking, at checkpoints and at close-out. Only making a repo **public**, publishing a GitHub **release**, or force-pushing shared history needs the owner's explicit confirmation. If an action looks high-risk or a bad idea, stop and ask anyway. This applies to the planning session (first commit), every phase and `/phase-add`. Hands-off runs depend on it: a phase that had to ask before merging could never finish unattended. If the owner's global rules say otherwise (for example "never push without asking"), follow them, tell the owner, and write their rule into the generated `CLAUDE.md` instead.

## Hands-off runs (PHX)
PhaseHypervisor (`phx`, <https://github.com/antonizick/PhaseHypervisor>) can run a plan's remaining phases unattended: `phx preflight <repo>` asks the foreseeable questions once, then `phx run <repo>` starts each phase as a fresh headless session running `/phase NN --auto` on the phase's model. **It is optional (PHX ADR-0011):** manual `/phase` stays the standard way, and with hands-off mode off every command behaves the same whether or not `phx` is installed. What the templates carry for it:
- `phase-command.md`: the `PHX-CONTRACT: 1` marker, step 0 (a manual `/phase` stops if a `phx` supervisor holds this repo's lock under `$XDG_RUNTIME_DIR/phx/`, and fails closed: it also stops if the check cannot run or its output lacks the closing `PHX-CHECK-DONE`), and the "Hands-off mode" section (no questions, refusals, model logged instead of checked, `PHX-RESULT:` line last).
- `_shared-instructions.md` §1b: block-with-question, which replaces every "ask the owner" in hands-off mode, and resuming a blocked phase.
- `CLAUDE.md`: the risk rule (stop and ask; in hands-off mode, block).
- `IMPLEMENTATION_PLAN.md`: the `Gate` column and a note on `phx` under "How to run a phase".
The normative definition is `docs/PHX_AUTO_MODE_CONTRACT.md` in the PhaseHypervisor repo; if the templates and it disagree, it wins and the templates are fixed. Changing any of these rules in a way an older reader would misread means a new contract version (PHX ADR-0012). Copy this text exactly as the templates have it; only `{{…}}` markers change.

## Phase design rules
- **Phase 00** is the planning session itself and is marked `✅ Complete`.
- **Phase 01** is always *repository foundation and governance*, for software projects: LICENSE,
  NOTICE, README, SECURITY, CONTRIBUTING, CODE_OF_CONDUCT, CHANGELOG (Keep a Changelog),
  THIRD_PARTY_NOTICES, .gitignore, .dockerignore, .editorconfig, .github/ (CI, issue and PR templates,
  Dependabot) and a docs skeleton. **Phase 02** is the language scaffold plus CI and quality gates.
- Build pure, testable core logic before I/O-heavy and integration work, and backend before UI.
  Fakes (fake engine, fake LLM) let the pipeline and UI be built before the heavy dependencies land.
- **The second-to-last phase** is hardening, security review and QA: threat model, scanners,
  measured performance, accessibility, licence audit, and closing every follow-up.
  **The last phase** is release and publication; agents commit, merge and push freely (git authority above),
  but making a repo public or publishing a release **requires the owner's explicit confirmation in-session**. The final report (`docs/{{PREFIX}}_FINAL-REPORT.md`) will include a visual timeline of the planning and build phases (starts, stops, blocked intervals, parallel phases), drawn from the Phase Log **Timeline** bullets and git history, so keep those accurate. Its Gate is `review`.
- **Gate per phase** (last table column, mirrored as `· **Gate:** …` in the prompt header): `auto` by default; `review` for release or publication phases and for phases whose result the owner should look at before the next one runs; `owner` for phases that need the owner's hands (hardware, accounts, payments). Phase 00 is `owner`. Only PhaseHypervisor reads it; manual `/phase` ignores it.
- **Inserted phases (letter suffix).** Work added after planning goes after the phase it builds on, as
  that number plus the next free lower-case letter (`09` → `09a`; `15a` → `15b`), never decimals (`15.10` = `15.1`)
  and never renumbering. A typical use is **interim tuning rounds** after hardening and before release
  (`15a`, `15b`…, prompt `phase-15a-pre-op-tuning-1.md`), each depending on the previous round, with the release
  phase depending on the last. Every inserted phase is a normal phase (row, prompt, claim, branch, worktree).
  Insert them with `/phase-add`. The reason for letters: renumbering would break every reference to a phase
  in commits, logs and prompts.
- Size each phase to fit one focused session: one clear goal and roughly 5–10 tasks.
- Make dependencies explicit, draw an ASCII dependency graph, and name the phases that can run in parallel.
- **Model per phase:** the strongest model (for example Opus, `/model opus`) for
  subtle correctness, state machines, parsing or round-trips, ML or perf-sensitive work, prompt
  engineering, complex interactive UI, and security review. The balanced model (for example Sonnet,
  `/model sonnet`) for scaffolding, adapters, CRUD UI, content authoring,
  packaging and docs. Use the newest model IDs available in the environment, and explain the
  choice under "Model rationale" in the plan.
- Every owner question gets a row in the plan's question table with a "Needed by: Phase NN"
  column. Phase prompts that depend on an open question must **stop and ask** if it is still open.

## Phase prompt rules (see `templates/phase-prompt.md`)
Every prompt is self-contained. It has a header line with the model and its `/model` command, "Depends on",
the branch name and the Gate; **Read first**, naming exact spec sections and prior Phase Log entries; **Goal**;
**Tasks**, numbered, concrete, naming files, interfaces and the security controls to honour; **Out of
scope**; **Tests**; **Acceptance criteria**, verifiable on the real target machine where relevant;
and **Phase-specific docs**, the docs this phase must create or update, followed by
"Then the standard close-out checklist."

## Status conventions
`⬜ Not started` · `🔄 In progress` · `⛔ Blocked` · `✅ Complete`. Always write the icon **and** the word.

**Claim protocol (parallel safety).** Agents and the owner read the Status column from `main`, so a phase is
claimed with a status-only commit on `main` (`chore(plan): start phase NN`) **before** its branch is
created or any other file changes; the vault note's row (if any) is set to `🔄` at the same moment. Each phase
then runs in its own worktree `../{{REPO_NAME}}-phase-NN`, and the main checkout always stays on
`main`. `⛔ Blocked` is committed to `main` the same way; `✅ Complete` arrives with the merge.
`/phase` refuses to start a phase's Tasks until the claim shows in `git show main:{{PREFIX}}_IMPLEMENTATION_PLAN.md`,
never silently resumes a `🔄` phase (another session may own it), and `/phase status` flags drift
between the table and live branches or worktrees. The reason: an `🔄` mark left uncommitted in a worktree,
or a phase run straight on `main`, leaves the table showing `⬜` for a phase that is underway, and a parallel
session then starts it a second time.
Phase Log entries: `### YYYY-MM-DD HH:MM TZ: Phase NN: <title> (<status>)`, then bullets covering what was built,
deviations, follow-ups, and test counts. The heading timestamp is when the entry is written (`date '+%Y-%m-%d %H:%M %Z'`).

**Timeline bullet (mandatory, first bullet of every Phase Log entry).** It makes each phase's start and stop machine-readable, for the visual project timeline in the final report:
`- **Timeline:** started <TS> (claim commit <hash>) · finished <TS> · merged <TS | not merged yet>` plus ` · blocked <TS> to <TS>` for each `⛔` interval.
- *started* is the **claim commit's** time: `git log -1 --format=%cd --date=format-local:'%Y-%m-%d %H:%M %Z' <hash>` (find the hash with `git log --format=%h --grep='^chore(plan): start phase NN' -1`). Never the time you wrote the entry.
- *finished* is `date '+%Y-%m-%d %H:%M %Z'` run as the **last step** before the final close-out commit.
- *merged* is the merge's time (agents merge completed phases without asking) (edit the bullet in the merge commit); otherwise `not merged yet`, and the timeline generator reads the merge from git.
- *blocked*: each time the phase went `⛔`, from the `⛔` commit to the unblock.
- Planning entries (Phase 00, `/phase-add`) use `started … · finished …` only; *started* is the `date` taken at the beginning of the planning session.

## Adopting the system in an existing repo
Same workflow, but inventory what exists first. Phase 01 becomes "governance gap-fill". The spec
is written from the existing README and docs plus the owner's goals. Phases cover only the remaining work.

## Migrating to the hands-off contract
Repos bootstrapped with an older version of this skill lack `PHX-CONTRACT: 1` in `.claude/commands/phase.md`.
Migrate one only when it is idle (no `🔄` row on `main`, no `phase-*` worktree, `main` clean; never commit another
agent's untracked files) and `phx plan <repo>` shows its next phase; skip any repo that is busy. As one commit
`chore(phx): adopt hands-off phase contract` (stage explicit paths), copying wording from `templates/` but keeping the repo's own text:
1. Run `phx plan <repo>` first and note the next phase and test line.
2. `.claude/commands/phase.md`: `argument-hint` gains `[--auto]`; after the "You are executing…" line insert `PHX-CONTRACT: 1`, the
   hands-off paragraph and step 0 (PHX check); append the "Hands-off mode" section.
3. `prompts/<PREFIX>_shared-instructions.md`: pointers "(Hands-off mode: block-with-question, §1b.)" on the owner-question and
   ambiguity steps; the new §1b section from `templates/_shared-instructions.md` (if §1b is taken, use the next free number and use it
   in `phase.md` and `CLAUDE.md` too); the close-out merge item per the git authority (merge without asking, push if a remote exists); the
   `PHX-RESULT` sentence on the final-message item.
4. `CLAUDE.md`: the Risk rule section; the git authority rule replaces "Never push…" and "Ask before merging". A stricter rule that is
   repo-specific by design (a local-only planning repo, a product-PR approval flow) stays, and is flagged to the owner.
5. Plan: a `Gate` column (`auto`; `review` for release or publication phases), its legend and the `phx` paragraph under "How to run a phase";
   check the column landed in the phase table and not in the Owner questions table.
6. `.claude/commands/phase-add.md`: drop "Never push" (push `main` if a remote exists).
7. An ADR in the repo's decisions log (with its index row) and, with a vault, a timestamped line in its vault note; push if the repo has a remote.
8. `phx plan <repo>` again: same next phase, no new problems, `Contract: 1`. Then run `phx preflight` (the explicit Gates change every row's
   fingerprint, so an earlier record is stale).

## Migrating an existing repo to prefixed names
Repos bootstrapped with an older version of this skill may use unprefixed names (`IMPLEMENTATION_PLAN.md`). Migrate one only
when no phase is `🔄 In progress` and `main` is clean, as its own `chore(docs): add project prefix` commit:
1. `git mv` each file in the "Prefixed" list above to its `<PREFIX>_` name (`prompts/phase-03-x.md` →
   `prompts/<PREFIX>_phase-03-x.md`); leave branches and worktrees alone.
2. Rewrite every reference to the old names: `grep -rnE 'IMPLEMENTATION_PLAN|SPECIFICATION\.md|DECISIONS\.md|_shared-instructions|prompts/phase-|_change-request-template'`
   over the repo, `.claude/commands/`, `CLAUDE.md`, the vault note (if any) and `~/.claude` memory. Links inside the plan's phase table too.
3. Add the prefix, timestamp and Timeline-bullet rules to `CLAUDE.md`, the shared instructions' checklist and the plan's Phase Log header line.
   Existing bare dates are left as they are; only new entries get timestamps.
4. Verify with the same greps (no old names left) and `/phase status`, then add an ADR and a Phase Log entry.
Do **not** rename the historical `chore(plan)` commits' referenced files in git history; they stay as they were.

## Injecting phases later (`/phase-add`)
Every bootstrapped repo gets `.claude/commands/phase-add.md` and `prompts/{{PREFIX}}_change-request-template.md`.
When the owner has new work for an existing plan, they run `/phase-add [after NN] <file or pasted text>`, in a session
on the strongest model (planning). The command:
1. grounds each item in the code;
2. asks owner decisions once, then records ADRs and owner questions;
3. picks the ID and rewires the dependents (always the release phase);
4. writes the prompt, the plan row, a `Planning: phase <ID> inserted (Planned)` Phase Log entry and the vault note (if any);
5. commits `docs(plan): add phase <ID> …` to `main`.

It never claims and never writes product code; the owner then runs `/model …` and `/phase <ID>`. **Adopting this
in a repo that has no `/phase-add`:** copy both templates in (fill `{{PROJECT_NAME}}`, `{{REPO_DIR}}`,
`{{REPO_NAME}}`, `{{PREFIX}}`, `{{OWNER}}`, `{{VAULT_NOTE_PATH}}` and the sections), and generalise the "Phase IDs" sentence in `/phase` and the shared instructions.
