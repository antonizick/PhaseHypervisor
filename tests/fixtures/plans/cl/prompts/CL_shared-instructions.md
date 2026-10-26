# Shared Instructions for Every Phase

Read this file in full before starting any phase. Each phase prompt assumes it.

**Phase IDs.** `NN` in this file is the phase ID: two digits, optionally with a lower-case letter suffix for a phase inserted after another one with `/phase-add` (`09a`, `15a`, `15b`…). An inserted phase is a normal phase with its own claim, branch and worktree; `15a` sorts after `15` and before `16`.

**Two repositories (ADR-0011).**
- **Planning repo** `/home/nick/Work/chessloopDeploy` (this one): plan, spec, ADRs, findings, lab scripts, run evidence. Local only; never pushed unless Nick asks.
- **Product repo** `antonizick/chessloop` on GitHub. Working clone `/home/nick/Work/chessloop` (created in Phase 01), per-phase worktrees `/home/nick/Work/chessloop-phase-NN`.

## 1. Orientation and claim (every phase, before writing code)
1. Read `CLAUDE.md`, `CL_IMPLEMENTATION_PLAN.md` (including the Phase Log and Owner questions), `docs/CL_FINDINGS.md`, and the spec sections named in your phase prompt. Always read the Amendments (spec §9).
2. Confirm that every phase listed under "Depends on" is `✅ Complete`. If one is not, stop and tell Nick.
3. Read the Phase Log entries of the dependency phases; they may record deviations that change what you build.
4. If an owner question this phase needs is still open, ask Nick before doing the affected work. (Hands-off mode: block-with-question, §1c.)
5. **Claim the phase on `main`** by following §1a. This is the first file change of every phase session. Do not start the Tasks until the claim is verified.
6. If the prompt is ambiguous or contradicts the spec, prefer the spec's Amendments. If it is still unclear, ask Nick before guessing on anything user-visible or hard to reverse. (Hands-off mode: block-with-question, §1c.)

## 1a. Claiming a phase (mandatory; other agents may be running in parallel)
Nick and other agents read the Status column from `main`. A status change made only on a phase branch, or left uncommitted in a worktree, is invisible to them. So every phase is claimed with a commit on `main` **before** any other work.
1. In the main checkout (`/home/nick/Work/chessloopDeploy`), check that `git branch --show-current` prints `main` and that `git status --short CL_IMPLEMENTATION_PLAN.md` prints nothing. If either check fails, stop and tell Nick. Never commit another agent's uncommitted changes.
2. Look for an existing claim: the phase's row on `main`, `git branch --list 'phase-NN-*'` and `git worktree list`. If the row is already `🔄 In progress`, or a branch or worktree exists, do not claim again; follow the resume rules in `/phase`.
3. Set the phase's Status cell to `🔄 In progress`, then commit **only that file** to `main`: `git commit -m "chore(plan): start phase NN" -- CL_IMPLEMENTATION_PLAN.md`.
4. In the Obsidian project note, set the phase's row to `🔄 In progress` and add a timestamped log line: "Phase NN started (claim commit `<hash>`, branch `phase-NN-<slug>`, worktree `../chessloopDeploy-phase-NN`)".
5. Create the worktree and branch from that commit: `git worktree add ../chessloopDeploy-phase-NN -b phase-NN-<slug> main`. Do all of the phase's planning-repo work in the worktree, using absolute paths or `cd <worktree> && …` in every command, because the shell may reset to the main checkout between commands. Never switch the main checkout off `main`: other agents commit their claims there.
6. Verify: `git show main:CL_IMPLEMENTATION_PLAN.md | grep '^| NN '` must show `🔄 In progress`.

If the phase ends `⛔ Blocked`, commit that status to `main` the same way (`chore(plan): phase NN blocked`) so that `main` doesn't show a stale `🔄`. A `✅ Complete` status reaches `main` through the merge.

## 1b. Product (upstream) changes (phases that touch `antonizick/chessloop`)
1. `git -C /home/nick/Work/chessloop fetch origin && git -C /home/nick/Work/chessloop checkout main && git -C /home/nick/Work/chessloop pull --ff-only`. The clone's `main` must equal `origin/main` and have no local changes; if not, stop and tell Nick.
2. `git -C /home/nick/Work/chessloop worktree add /home/nick/Work/chessloop-phase-NN -b deploy/phase-NN-<slug> origin/main`. All product edits happen there.
3. Commit with Conventional Commits; reference findings in the body (`Fixes F-012, F-015`). Never commit `.env`, databases, backups, transcripts or screenshots containing secrets. Run gitleaks (`docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:<pinned> detect -s /repo`) before pushing, once Phase 02 has pinned a version.
4. **Before the PR:** the change must pass upstream CI locally (Phase 02 commands) **and** a clean-VM lab run of the affected paths with `CHESSLOOP_REPO`/`CHESSLOOP_REF` pointing at the branch (from Phase 08 on; before that, check out the branch inside the VM). Store the evidence under `runs/`.
5. **Approval (ADR-0012):** Nick pre-approved pushing, opening and merging PRs when you are confident they are low risk (required CI green, lab run passed, nothing destructive or hard to reverse). State your risk assessment in the PR body. If you have any concern, ask Nick before `git push`, `gh pr create` or merging. PR body: summary, the findings fixed, the lab evidence paths, a test plan, and "🤖 Generated with [Claude Code](https://claude.com/claude-code)". After Nick says OK: `gh pr merge <N> --squash --delete-branch`, then update the clone's `main` and remove the worktree (`git -C /home/nick/Work/chessloop worktree remove /home/nick/Work/chessloop-phase-NN`).
6. If Nick wants to review later, leave the PR open, mark the phase `⛔ Blocked` with reason "awaiting PR #N review", and say so. Later phases that depend on it must not start until it merges, because `curl | bash` users install from `main`.
7. Record the PR number and merge commit in the Phase Log and in the `Fix PR` column of `docs/CL_FINDINGS.md`.

## 1c. Hands-off mode: block-with-question (PhaseHypervisor contract 1)
Applies only in hands-off mode (`/phase NN --auto` or `PHX_AUTO=1`, set only by PhaseHypervisor); manual sessions ignore this section. Wherever a manual session would ask Nick (an open owner question this phase needs, an ambiguity you must not guess, the risk rule in `CLAUDE.md`, or a failure you cannot fix within scope), do this instead, then end the session:
1. In the worktree, commit all work on the phase branch: `wip(phase-NN): blocked, <short reason>`. Do not merge; keep the branch and worktree.
2. In the main checkout, in `CL_IMPLEMENTATION_PLAN.md`:
   - add an Owner questions row `| <next #> | <question> | Open (asked <TS>, Phase NN, auto mode). Proposed default: <default> | Phase NN |` (or, for an existing open question, name this phase in its Status cell and keep it `Open`);
   - set the phase's Status to `⛔ Blocked`;
   - add a Phase Log entry `### <TS>: Phase NN: <title> (⛔ Blocked)` with bullets: `- **Timeline:** started <claim TS> (claim commit <hash>) · blocked <TS> to (open)`, then `- **Model:** …`, then `- **Question:** #<id>: <question>`, then what is done, what remains and where to resume.
3. Commit only that file to `main`: `git commit -m "chore(plan): phase NN blocked" -- CL_IMPLEMENTATION_PLAN.md`, and push `main` if a remote exists.
4. In the Obsidian note: row `⛔ Blocked`, `updated:` field, and a timestamped log line naming the question.
5. Final message: what was done, the question and its proposed default, then the `PHX-RESULT` line with `"status":"blocked"` and the question IDs (see `/phase`).

A question is **open** while its Status cell starts with `Open`; `Answered …`, `Decided …` and `Deferred …` are not open.

**Resuming** a `⛔ Blocked` phase in hands-off mode: if a question needed by it is still open, refuse without changing anything. Otherwise set the row to `🔄 In progress`, change `blocked <TS> to (open)` to `blocked <TS> to <TS now>` in its Timeline, commit only the plan file to `main` (`chore(plan): resume phase NN`), update the Obsidian note, then run `git merge main` in the worktree, read the answer and continue as a normal resume.

**Product PRs (§1b) in hands-off mode.** Push, open and merge a product PR only when ADR-0012's low-risk test is met (required CI green, clean-VM lab run passed, nothing destructive or hard to reverse); otherwise block-with-question. Never change GitHub repo settings. The planning repo has no remote and stays local.

## 2. Target repository layout (planning repo; keep this section in sync)
```
chessloopDeploy/
├── CLAUDE.md  CL_IMPLEMENTATION_PLAN.md  README.md  .gitignore
├── .claude/commands/{phase,phase-add}.md
├── docs/
│   ├── CL_SPECIFICATION.md  CL_DECISIONS.md  CL_FINDINGS.md
│   ├── LAB.md                 ← how the lab works (Phase 03)
│   └── BASELINE-LINUX.md      ← Phase 04 audit report (matrix, pain points, doc inaccuracies)
├── prompts/                   ← shared instructions, phase prompts, change-request template
├── lab/                       ← Phase 03+
│   ├── lab.sh                 ← create | reset | destroy | shell | ip  <platform>
│   ├── platforms.conf         ← platform → Incus image alias, resources
│   ├── drive-deploy.exp       ← expect driver answering deploy.sh prompts (baseline) 
│   ├── smoke.sh               ← API smoke test: health, admin login, register, library, practice, persistence
│   ├── baseline.sh            ← Phase 04 audit steps against today's installer (one command per path)
│   ├── sabotage.sh            ← Phase 04 sabotage cases (port busy, distro docker, network drop, …)
│   ├── ui-shots.py            ← headless-browser UI screenshots (ADR-0014)
│   ├── branch-stack.sh        ← Phase 06: build an unpushed product branch in a clean VM (no installer)
│   ├── stack-check.sh         ← Phase 07: prod-stack checks (health, headers, CORS, mail, JWT) and the upgrade test
│   ├── mailpit/               ← SMTP sink config
│   ├── windows/               ← Phase 05: Win11 VM + WSL2 tooling
│   └── lib/                   ← shared bash helpers (scrub secrets, timing, evidence capture)
└── runs/<YYYY-MM-DD>-<platform>-<path>/   ← transcript.txt (scrubbed), timings.json, logs/, screenshots/, notes.md
```
Product repo layout: see its README; Phase 10 restructures `docs/`.

## 3. Conventions
- **Prefix.** Project documents carry the project prefix `CL_` (see `CLAUDE.md`). New project-specific documents follow the same rule; convention-bound files (`README.md`, `LICENSE`, `CHANGELOG.md`, `CLAUDE.md`…) keep their names.
- **Timestamps, not dates.** Every place that records when (Phase Log, ADRs, amendments, owner questions, vault log, "Last updated", changelog release headings) uses `YYYY-MM-DD HH:MM TZ` (from `date '+%Y-%m-%d %H:%M %Z'`, never a bare or guessed date). Run `date` when you write each one. Entries that predate 2026-10-20 keep their bare dates.
- **Bash:** `#!/usr/bin/env bash`, `set -euo pipefail`, shellcheck-clean, functions small, every external command's failure handled or explicitly allowed with a comment. Match the style of the existing `deploy.sh` (log helpers `info/ok/warn/err/fatal`).
- **Python (product):** match the existing FastAPI/SQLModel style; pytest tests beside the existing ones in `chessloop/backend/tests/`.
- **TypeScript (product):** match existing components and `src/api/*` wrappers; `npm run lint` (tsc) must pass.
- **Evidence:** every lab run writes `runs/<date>-<platform>-<path>/`. Scrub with `lab/lib/scrub.sh` (JWT secrets, passwords, tokens, TOTP secrets) **before** committing. Large logs (>1 MB) are gzipped.
- **Findings:** use the IDs in `docs/CL_FINDINGS.md` (`F-001`…; keep `H` rows and link them). One finding = one root cause.
- **Writing for Sam (spec §3):** short sentences, imperative steps, one action per numbered step, the exact command to copy, what you should see, and what to do if you don't. Explain any jargon at first use.
- **Versions:** never guess a version number, image tag, date or URL. Look it up (registry, release page) and record the source.
- **Host changes:** anything installed or configured on Nick's laptop is documented in `/home/nick/Documents/04 Resources/OSMods/` (README first).

## 4. Phase close-out checklist (all items required)
- [ ] All acceptance criteria in the phase prompt are met, with a short verification note for each.
- [ ] Tests, lint and type checks pass (from Phase 02 the product repo's `scripts/ci-local.sh` runs all the product checks below in Docker; `scripts/ci-local.sh shell` is advisory until Phase 12): planning repo `shellcheck lab/**/*.sh` (from Phase 03); product `cd chessloop/backend && pytest -q`, `cd chessloop/frontend && npm ci && npm run lint && npm run build`, `shellcheck deploy.sh manage.sh`, `docker compose -f chessloop/docker-compose.prod.yml config -q` (with a dummy `JWT_SECRET`).
- [ ] `CL_IMPLEMENTATION_PLAN.md`: Status set (`✅ Complete` or `⛔ Blocked`, icon plus word; a `⛔ Blocked` status is also committed to `main` per §1a), Phase Log entry added (timestamp, summary, deviations, follow-ups, test counts, PR number).
- [ ] **Timeline bullet written** as the first bullet of the Phase Log entry: *started* = the claim commit's time (`git log -1 --format=%cd --date=format-local:'%Y-%m-%d %H:%M %Z' <claim hash>`), *finished* = `date '+%Y-%m-%d %H:%M %Z'` taken as the last step before the final commit, *merged* = the merge time or `not merged yet`, plus `blocked <TS> to <TS>` for any `⛔` interval. Never reuse an earlier timestamp.
- [ ] `docs/CL_FINDINGS.md` updated (new findings, status changes, PR links, verified-on dates).
- [ ] Product repo: `CHANGELOG.md` `[Unreleased]` updated; README/docs/SECURITY/THIRD_PARTY_NOTICES/ignore files updated where affected (from Phase 01 on).
- [ ] ADR added for any notable choice, with its row in the index table at the top of `docs/CL_DECISIONS.md`; spec amendment added if the spec changed.
- [ ] Later phase prompts corrected if your work changed their assumptions.
- [ ] Obsidian project note updated (status icons and log line).
- [ ] OSMods documentation updated if the host system was modified.
- [ ] Planning work committed on the phase branch. Once the phase is `✅ Complete` and every check passes, merge it into `main` without asking (fast-forward where possible), from the main checkout. Conflicts in `CL_IMPLEMENTATION_PLAN.md` and `docs/CL_FINDINGS.md` and the changelog are expected when phases ran in parallel: keep every row and entry from both sides, and use the branch's final status for this phase's row. The planning repo has no remote and stays local, so there is nothing to push. Then `git worktree remove ../chessloopDeploy-phase-NN` and `git branch -d phase-NN-<slug>`. Do not merge a `⛔ Blocked` phase or one with failing checks. Making a repo public or publishing a release needs Nick's explicit confirmation (hands-off mode: block-with-question, §1c).
- [ ] Product PR handled per §1b (pushed, opened and merged only with Nick's OK; or left open and the phase marked Blocked).
- [ ] Final message to Nick: what was built, how to try it, what's next, and any open questions. In hands-off mode, its last line is the `PHX-RESULT` line (see `/phase`).
