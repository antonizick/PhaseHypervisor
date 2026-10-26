# Shared Instructions for Every Phase

Read this file in full before starting any phase. Each phase prompt assumes it.

**Phase IDs.** `NN` in this file is the phase ID: two digits, optionally with a lower-case letter suffix for a phase inserted after another one with `/phase-add` (`09a`, `12a`, `12b`…). An inserted phase is a normal phase with its own claim, branch and worktree; `12a` sorts after `12` and before `13`.

## 1. Orientation and claim (every phase, before writing code)
1. Read `CLAUDE.md`, `YTPL2_IMPLEMENTATION_PLAN.md` (including the Phase Log and Owner questions) and the spec sections named in your phase prompt. Always read the Amendments (§13).
2. Confirm that every phase listed under "Depends on" is `✅ Complete`. If one is not, stop and tell Nick.
3. Read the Phase Log entries of the dependency phases; they may record deviations that change what you build.
4. If an owner question this phase needs is still open, ask Nick before doing the affected work. (Hands-off mode: block-with-question, §1b.)
5. **Claim the phase on `main`** by following §1a. This is the first file change of every phase session. Do not start the Tasks until the claim is verified.
6. If the prompt is ambiguous or contradicts the spec, prefer the spec's Amendments. If it is still unclear, ask Nick before guessing on anything user-visible or hard to reverse. (Hands-off mode: block-with-question, §1b.)

## 1a. Claiming a phase (mandatory; other agents may be running in parallel)
Nick and other agents read the Status column from `main`. A status change made only on a phase branch, or left uncommitted in a worktree, is invisible to them. So every phase is claimed with a commit on `main` **before** any other work.
1. In the main checkout (`/home/nick/Work/YTPL2`), check that `git branch --show-current` prints `main` and that `git status --short YTPL2_IMPLEMENTATION_PLAN.md` prints nothing. If either check fails, stop and tell Nick. Never commit another agent's uncommitted changes.
2. Look for an existing claim: the phase's row on `main`, `git branch --list 'phase-NN-*'` and `git worktree list`. If the row is already `🔄 In progress`, or a branch or worktree exists, do not claim again; follow the resume rules in `/phase`.
3. Set the phase's Status cell to `🔄 In progress`, then commit **only that file** to `main`: `git commit -m "chore(plan): start phase NN" -- YTPL2_IMPLEMENTATION_PLAN.md`.
4. In the Obsidian project note (`/home/nick/Documents/02 Projects/YTPL2 Implementation Plan.md`), set the phase's row to `🔄 In progress`, update its `updated:` field and add a timestamped log line: "Phase NN started (claim commit `<hash>`, branch `phase-NN-<slug>`, worktree `../YTPL2-phase-NN`)".
5. Create the worktree and branch from that commit: `git worktree add ../YTPL2-phase-NN -b phase-NN-<slug> main`, then install the project's dependencies inside it if it has any (`uv sync`, `npm ci --prefix frontend`). Do all of the phase's work in the worktree, using absolute paths or `cd <worktree> && …` in every command, because the shell may reset to the main checkout between commands. Never switch the main checkout off `main`: other agents commit their claims there.
6. Verify: `git show main:YTPL2_IMPLEMENTATION_PLAN.md | grep '^| NN '` must show `🔄 In progress`.

If the phase ends `⛔ Blocked`, commit that status to `main` the same way (`chore(plan): phase NN blocked`) so that `main` doesn't show a stale `🔄`. A `✅ Complete` status reaches `main` through the merge.

## 1b. Hands-off mode: block-with-question (PhaseHypervisor contract 1)
Applies only in hands-off mode (`/phase NN --auto` or `PHX_AUTO=1`, set only by PhaseHypervisor); manual sessions ignore this section. Wherever a manual session would ask Nick (an open owner question this phase needs, an ambiguity you must not guess, the risk rule in `CLAUDE.md`, or a failure you cannot fix within scope), do this instead, then end the session:
1. In the worktree, commit all work on the phase branch: `wip(phase-NN): blocked, <short reason>`. Do not merge; keep the branch and worktree.
2. In the main checkout, in `YTPL2_IMPLEMENTATION_PLAN.md`:
   - add an Owner questions row `| <next #> | <question> | Open (asked <TS>, Phase NN, auto mode). Proposed default: <default> | Phase NN |` (or, for an existing open question, name this phase in its Status cell and keep it `Open`);
   - set the phase's Status to `⛔ Blocked`;
   - add a Phase Log entry `### <TS>: Phase NN: <title> (⛔ Blocked)` with bullets: `- **Timeline:** started <claim TS> (claim commit <hash>) · blocked <TS> to (open)`, then `- **Model:** …`, then `- **Question:** #<id>: <question>`, then what is done, what remains and where to resume.
3. Commit only that file to `main`: `git commit -m "chore(plan): phase NN blocked" -- YTPL2_IMPLEMENTATION_PLAN.md`, and push `main` if a remote exists.
4. In the Obsidian note: row `⛔ Blocked`, `updated:` field, and a timestamped log line naming the question.
5. Final message: what was done, the question and its proposed default, then the `PHX-RESULT` line with `"status":"blocked"` and the question IDs (see `/phase`).

A question is **open** while its Status cell starts with `Open`; `Answered …`, `Decided …` and `Deferred …` are not open.

**Resuming** a `⛔ Blocked` phase in hands-off mode: if a question needed by it is still open, refuse without changing anything. Otherwise set the row to `🔄 In progress`, change `blocked <TS> to (open)` to `blocked <TS> to <TS now>` in its Timeline, commit only the plan file to `main` (`chore(plan): resume phase NN`), update the Obsidian note, then run `git merge main` in the worktree, read the answer and continue as a normal resume.

## 2. Target repository layout (evolves; keep `docs/YTPL2_ARCHITECTURE.md` in sync)
```
YTPL2/
├── CLAUDE.md  README.md  LICENSE  NOTICE  SECURITY.md  CONTRIBUTING.md
├── CODE_OF_CONDUCT.md  CHANGELOG.md  THIRD_PARTY_NOTICES.md
├── YTPL2_IMPLEMENTATION_PLAN.md            (prefixed)
├── pyproject.toml  uv.lock  .python-version  Makefile  .pre-commit-config.yaml
├── .editorconfig  .gitignore  .dockerignore  .github/ (CI, templates, Dependabot)
├── src/ytpl2/
│   ├── __init__.py  __main__.py  cli.py        Typer: serve start stop status open auth logout doctor
│   ├── config.py  paths.py                     config.toml loader, XDG paths, permission checks
│   ├── domain/                                 pure logic, no I/O (Phase 03)
│   │   ├── models.py  urls.py  export.py  quota.py  planning.py  errors.py
│   ├── youtube/                                client protocol + implementations
│   │   ├── client.py (Protocol)  fake.py  demo_data.py  (Phase 03)
│   │   └── google_client.py  metering.py  (Phase 04)
│   ├── auth/  oauth.py  token_store.py         (Phase 04)
│   ├── store/  db.py  migrations/  cache.py  ledger.py  jobs_repo.py   (Phase 05)
│   ├── jobs/   engine.py  snapshot.py          (Phase 05)
│   ├── server/ app.py  security.py  theme.py  routes/  lifecycle.py   (Phase 06)
│   └── web/dist/                               built frontend (git-ignored, packaged)
├── frontend/                                   Vite React-TS (Phase 02, 07-10)
│   ├── package.json  package-lock.json  vite.config.ts  tsconfig.json
│   └── src/ api/  theme/  components/  features/{playlists,items,jobs,export,search,player}/  keyboard/  selection/
├── tests/  unit/  integration/  live/ (marker `live`)  e2e/ (Playwright, against --demo)
├── scripts/  install.sh  uninstall.sh          (Phase 11)
├── config/   config.example.toml  occ-service.example.toml
├── docs/
│   ├── YTPL2_SPECIFICATION.md  YTPL2_DECISIONS.md  YTPL2_ARCHITECTURE.md   (prefixed)
│   ├── YTPL2_THREAT-MODEL.md (Phase 12)  YTPL2_FINAL-REPORT.md (Phase 13)  (prefixed)
│   ├── setup/google-cloud.md  user-guide/  images/ (demo-mode screenshots only)
└── prompts/  YTPL2_shared-instructions.md  YTPL2_phase-NN-<slug>.md  YTPL2_change-request-template.md   (prefixed)
```

## 3. Conventions
- **Prefix.** Project documents carry the project prefix `YTPL2_` (see `CLAUDE.md`). New project-specific documents follow the same rule; convention-bound files (`README.md`, `LICENSE`, `CHANGELOG.md`, `CLAUDE.md`…) keep their names.
- **Timestamps, not dates.** Every place that records when (Phase Log, ADRs, amendments, owner questions, vault log, "Last updated", changelog release headings) uses `YYYY-MM-DD HH:MM TZ`. Run `date '+%Y-%m-%d %H:%M %Z'` when you write each one; do not guess or copy an earlier timestamp.
- **Python.** `src/` layout; type hints everywhere, `mypy --strict` clean; ruff format and lint; no global mutable state outside the app factory; `domain/` imports nothing from `server/`, `store/` or `youtube/google_client.py`. Time comes from an injectable clock (needed for quota resets and TTL tests); `zoneinfo("America/Los_Angeles")` for the quota day.
- **API client.** All YouTube access goes through the `YouTubeClient` protocol. The real client wraps every call in the metering layer, which records it in the ledger before returning. Nothing outside `youtube/` imports `googleapiclient`.
- **HTTP API.** JSON under `/api/…`; errors are `{"error": "<code>", "message": "<plain English>", "hint": "<next step>"}` with a fitting status code; state-changing routes require the `X-YTPL2-Token` header (S3); mutations of YouTube data only via `POST /api/jobs` (S9). Keep a route table in `docs/YTPL2_ARCHITECTURE.md`.
- **Frontend.** TypeScript strict; function components and hooks; one API module (`frontend/src/api/`) that adds the token header; colours only from CSS variables set by the theme endpoint; no inline styles that break the CSP (use CSS modules or classes; inline `style` attributes are blocked by `style-src 'self'`; React's `style` prop sets CSSOM properties and is allowed, but prefer classes); `textContent`-safe rendering only (S7); accessible names on every control; `prefers-reduced-motion` respected.
- **Tests.** pytest with markers `unit`, `integration`, `live`; Vitest + Testing Library for components; Playwright e2e against `ytpl2 serve --demo` on a random free port with its own temp data dir. Never call the real API outside `-m live` (R22).
- **Live API runs.** Only on `YTPL2-TEST-` private playlists created by the test; clean up in `finally`; print "quota spent: N units"; note it in the Phase Log.
- **Commits.** Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`), small and at checkpoints.

## 4. Phase close-out checklist (all items required)
- [ ] All acceptance criteria in the phase prompt are met, with a short verification note for each.
- [ ] Tests, lint and type checks pass: `make check` (and `make e2e` from Phase 07 on; `YTPL2_LIVE=1 uv run pytest -m live` where the phase touches the real API).
- [ ] `YTPL2_IMPLEMENTATION_PLAN.md`: Status set (`✅ Complete` or `⛔ Blocked`, icon plus word; a `⛔ Blocked` status is also committed to `main` per §1a), Phase Log entry added (timestamp, summary, deviations, follow-ups, test counts, live quota spent).
- [ ] **Timeline bullet written** as the first bullet of the Phase Log entry: *started* = the claim commit's time (`git log -1 --format=%cd --date=format-local:'%Y-%m-%d %H:%M %Z' <claim hash>`), *finished* = `date '+%Y-%m-%d %H:%M %Z'` taken as the last step before the final commit, *merged* = the merge time or `not merged yet`, plus `blocked <TS> to <TS>` for any `⛔` interval. Never reuse an earlier timestamp.
- [ ] `CHANGELOG.md` `[Unreleased]` updated (a release heading carries a timestamp, not just a date).
- [ ] README, SECURITY, `YTPL2_ARCHITECTURE`, user guide, setup guide, THIRD_PARTY_NOTICES, ignore files updated where affected.
- [ ] ADR added for any notable choice (timestamped in both the entry and its row in the index table at the top of `docs/YTPL2_DECISIONS.md`); spec amendment added if the spec changed; any `Proposed` ADR this phase verifies is moved to Accepted or Superseded.
- [ ] Later phase prompts corrected if your work changed their assumptions.
- [ ] Obsidian project note updated (status icons, `updated:` field and a timestamped log line).
- [ ] OSMods documentation updated if the host system was modified.
- [ ] No secrets or personal data staged: `git diff --cached` reviewed, gitleaks clean.
- [ ] Work committed on the phase branch. Once the phase is `✅ Complete` and every check passes, merge it into `main` without asking (fast-forward where possible), from the main checkout. Conflicts in `YTPL2_IMPLEMENTATION_PLAN.md` and the changelog are expected when phases ran in parallel: keep every row and entry from both sides, and use the branch's final status for this phase's row. Then push `main` if a remote exists (create a **private** GitHub repo if the plan calls for one; ADR-0004), `git worktree remove ../YTPL2-phase-NN` and `git branch -d phase-NN-<slug>`. Do not merge a `⛔ Blocked` phase or one with failing checks. Making a repo public or publishing a release needs Nick's explicit confirmation (hands-off mode: block-with-question, §1b).
- [ ] Final message to Nick: what was built, how to try it, what's next, and any open questions. In hands-off mode, its last line is the `PHX-RESULT` line (see `/phase`).
