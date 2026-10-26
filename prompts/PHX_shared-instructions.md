# Shared Instructions for Every Phase

Read this file in full before starting any phase. Each phase prompt assumes it.

**Phase IDs.** `NN` in this file is the phase ID: two digits, optionally with a lower-case letter suffix for a phase inserted after another one with `/phase-add` (`09a`, `07b`…). An inserted phase is a normal phase with its own claim, branch and worktree; `07a` sorts after `07` and before `08`.

## 1. Orientation and claim (every phase, before writing code)
1. Read `CLAUDE.md`, `PHX_IMPLEMENTATION_PLAN.md` (including the Phase Log and Owner questions) and the spec sections named in your phase prompt. Always read the Amendments (spec §4).
2. Confirm that every phase listed under "Depends on" is `✅ Complete`. If one is not, stop and tell Nick.
3. Read the Phase Log entries of the dependency phases; they may record deviations that change what you build.
4. If an owner question this phase needs is still open, ask Nick before doing the affected work.
5. **Claim the phase on `main`** by following §1a. This is the first file change of every phase session. Do not start the Tasks until the claim is verified.
6. If the prompt is ambiguous or contradicts the spec, prefer the spec's Amendments. If it is still unclear, ask Nick before guessing on anything user-visible or hard to reverse.

## 1a. Claiming a phase (mandatory)
Nick and other agents read the Status column from `main`. A status change made only on a phase branch, or left uncommitted in a worktree, is invisible to them. So every phase is claimed with a commit on `main` **before** any other work.
1. In the main checkout (`/home/nick/Work/PhaseHypervisor`), check that `git branch --show-current` prints `main` and that `git status --short PHX_IMPLEMENTATION_PLAN.md` prints nothing. If either check fails, stop and tell Nick. Never commit another agent's uncommitted changes.
2. Look for an existing claim: the phase's row on `main`, `git branch --list 'phase-NN-*'` and `git worktree list`. If the row is already `🔄 In progress`, or a branch or worktree exists, do not claim again; follow the resume rules in `/phase`.
3. Set the phase's Status cell to `🔄 In progress`, then commit **only that file** to `main`: `git commit -m "chore(plan): start phase NN" -- PHX_IMPLEMENTATION_PLAN.md`.
4. In the Obsidian project note, set the phase's row to `🔄 In progress`, update its `updated:` field and add a timestamped log line: "Phase NN started (claim commit `<hash>`, branch `phase-NN-<slug>`, worktree `../PhaseHypervisor-phase-NN`)".
5. Create the worktree and branch from that commit: `git worktree add ../PhaseHypervisor-phase-NN -b phase-NN-<slug> main`, then run `uv sync` inside it (from Phase 02 on). Do all of the phase's work in the worktree, using absolute paths or `cd <worktree> && …` in every command, because the shell may reset to the main checkout between commands. Never switch the main checkout off `main`.
6. Verify: `git show main:PHX_IMPLEMENTATION_PLAN.md | grep '^| NN '` must show `🔄 In progress`.

If the phase ends `⛔ Blocked`, commit that status to `main` the same way (`chore(plan): phase NN blocked`) so that `main` doesn't show a stale `🔄`. A `✅ Complete` status reaches `main` through the merge.

## 2. Target repository layout (evolves; keep `docs/PHX_ARCHITECTURE.md` in sync)
```
PhaseHypervisor/
├── CLAUDE.md
├── PHX_IMPLEMENTATION_PLAN.md            (prefixed)
├── README.md  LICENSE  NOTICE  SECURITY.md  CONTRIBUTING.md  CODE_OF_CONDUCT.md
├── CHANGELOG.md  THIRD_PARTY_NOTICES.md  .gitignore  .editorconfig
├── pyproject.toml  uv.lock  .pre-commit-config.yaml
├── .github/                              (CI, issue/PR templates, Dependabot)
├── .claude/commands/phase.md  phase-add.md
├── docs/
│   ├── PHX_SPECIFICATION.md              (prefixed)
│   ├── PHX_DECISIONS.md                  (prefixed)
│   ├── PHX_ARCHITECTURE.md               (prefixed, from Phase 02)
│   ├── PHX_AUTO_MODE_CONTRACT.md         (prefixed, Phase 03: the /phase --auto contract)
│   ├── PHX_USER_GUIDE.md                 (prefixed, from Phase 07)
│   └── PHX_FINAL-REPORT.md               (prefixed, Phase 12)
├── prompts/
│   ├── PHX_shared-instructions.md        (prefixed)
│   ├── PHX_change-request-template.md    (prefixed)
│   ├── PHX_preflight.md                  (prefixed, Phase 08: preflight session prompt)
│   └── PHX_phase-NN-<slug>.md            (prefixed)
├── src/phx/
│   ├── __main__.py  cli.py               (argparse entry point `phx`)
│   ├── paths.py  logging.py  redact.py   (state dirs, JSONL log, secret redaction)
│   ├── plan.py                           (Phase 04: parser, eligibility, drift)
│   ├── runner.py  classify.py            (Phase 05: launch, stream-json, exit classes)
│   ├── verify.py  recover.py  triage.py  (Phase 06)
│   ├── supervisor.py  locks.py  notify.py  vault.py  (Phase 07)
│   └── preflight.py                      (Phase 08)
└── tests/
    ├── fixtures/plans/                   (copies of MM3, CL, OCC, YTPL2 plans; sample plan)
    ├── fixtures/streams/                 (stream-json samples incl. usage-limit)
    └── fakes/                            (fake claude and ai-provider executables)
```
Runtime state lives outside the repo: `~/.local/state/phx/<repo-name>/` (`run.jsonl`, `state.json`, `sessions/`). Per-repo overrides: `<repo>/.phx/config.toml` (committed if present, never containing secrets).

## 3. Conventions
- **Prefix.** Project documents carry the project prefix `PHX_` (see `CLAUDE.md`). Convention-bound files keep their names.
- **Timestamps, not dates.** Every place that records when uses `YYYY-MM-DD HH:MM TZ`. Run `date '+%Y-%m-%d %H:%M %Z'` when you write each one; do not guess or copy an earlier timestamp.
- **Python:** 3.12+ syntax, full type hints, `mypy --strict` on `src/`, ruff (lint + format), standard library only at runtime. `subprocess` calls always use argument lists, never `shell=True`.
- **Logging:** every outcome and its reason goes to `run.jsonl` as one JSON object per line with `ts`, `event`, `phase`, `reason` and relevant fields. Pass everything through `redact.py` before writing.
- **Tests:** no network, no real Claude, no real `notify-send` in unit tests. Use the fakes and `tmp_path` git repos.
- **Files outside this repo** (the skill under `~/.claude/skills/phased-project/`, the playbook note, other projects' repos, OSMods): only the phases whose prompts name them may change them, and each change gets a backup or a git commit in that location.

## 4. Phase close-out checklist (all items required)
- [ ] All acceptance criteria in the phase prompt are met, with a short verification note for each.
- [ ] Tests, lint and type checks pass: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src` (from Phase 02 on).
- [ ] `PHX_IMPLEMENTATION_PLAN.md`: Status set (`✅ Complete` or `⛔ Blocked`, icon plus word; a `⛔ Blocked` status is also committed to `main` per §1a), Phase Log entry added (timestamp, summary, deviations, follow-ups, test counts).
- [ ] **Timeline bullet written** as the first bullet of the Phase Log entry: *started* = the claim commit's time (`git log -1 --format=%cd --date=format-local:'%Y-%m-%d %H:%M %Z' <claim hash>`), *finished* = `date '+%Y-%m-%d %H:%M %Z'` taken as the last step before the final commit, *merged* = the merge time, plus `blocked <TS> to <TS>` for any `⛔` interval. Never reuse an earlier timestamp.
- [ ] `CHANGELOG.md` `[Unreleased]` updated (from Phase 01 on).
- [ ] README, SECURITY, `PHX_ARCHITECTURE`, user guide, THIRD_PARTY_NOTICES, ignore files updated where affected.
- [ ] ADR added for any notable choice (timestamped in both the entry and its row in the index table); spec amendment added if the spec changed.
- [ ] Later phase prompts corrected if your work changed their assumptions.
- [ ] Obsidian project note updated (status icons, `updated:` field and a timestamped log line).
- [ ] OSMods documentation updated if the host system was modified; playbook note updated if the skill was changed.
- [ ] Work committed on the phase branch. Once the phase is `✅ Complete` and every check passes, merge it into `main` from the main checkout without asking (fast-forward where possible), push `main` if a remote exists (ADR-0004), then `git worktree remove ../PhaseHypervisor-phase-NN`, `git branch -d phase-NN-<slug>`, and remove any temporary files or processes you created. Do not merge a `⛔ Blocked` phase or one with failing checks. Making the repo public or publishing a GitHub release requires Nick's explicit confirmation.
- [ ] Final message to Nick: what was built, how to try it, what's next, and any open questions.
