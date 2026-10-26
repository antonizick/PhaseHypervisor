# YTPL2 Phase 13: Release & publication

**Model:** Sonnet 5.5 (`/model claude-sonnet-5-5`) · **Depends on:** 12 · **Branch:** `phase-13-release` · **Worktree:** `../YTPL2-phase-13`

## Read first
`CLAUDE.md`, `prompts/YTPL2_shared-instructions.md`, spec §13.1 A4, §13.4, the plan (Definition of done, owner questions, **the whole Phase Log**), `docs/YTPL2_DECISIONS.md` (ADR-0004). **Owner question 12 (public, private or no GitHub repo) must be answered before task 6; ask Nick.**

## Goal
YTPL2 v1.0.0 is tagged and installed on the machine, with a final report that tells the story of the build, including a visual timeline of every phase. If and only if Nick confirms in this session, the repository is published on GitHub the way he chooses.

## Tasks
1. **Version and changelog:** set the version `1.0.0` in `src/ytpl2/__init__.py`, `pyproject.toml` and `frontend/package.json`. Move `[Unreleased]` to `## [1.0.0] - <timestamp from date>` in CHANGELOG (Keep a Changelog, with a timestamp per the conventions), with a fresh empty `[Unreleased]` above it.
2. **Final report** `docs/YTPL2_FINAL-REPORT.md`:
   - **Overview:** what was built against the spec, with the Definition of done table and its evidence.
   - **Decisions:** owner decisions and every ADR in one line each; deviations from the original planning document.
   - **Facts:** the verified Google facts (Appendix A final), measured performance, the security summary, and known limitations (quota, the refresh-token policy, embedding).
   - **Timeline:** a **visual timeline** of the planning and build phases, drawn from the Phase Log **Timeline** bullets and `git log`. For each phase: its start (claim commit), finish, merge, any blocked intervals, and which phases ran in parallel. Render it as a Mermaid `gantt` chart (it renders in GitHub and Obsidian), with an ASCII fallback table, and add the total elapsed time and the per-phase durations.
   - **Spend:** the quota spent in live testing per phase (from the Phase Log).
   - **Ideas for later:** soft-delete/re-add from snapshot, playlist rename and privacy edits, reordering, and anything from the post-1.0 list.
3. **README final pass:** the feature list, demo-mode screenshots and GIF (never real account data), install/quick start, the Google setup link, the quota explanation, a privacy statement, the OCC note, the licence and the "not affiliated with YouTube" notice. Check that every link resolves.
4. **Release checks:** `make check`, `make e2e`, `make build`; a fresh-clone build in a temp dir; gitleaks over the whole history; `git status` clean; no personal data in the repo (grep for Nick's channel ID or title, real playlist names seen in live runs, emails other than the contact address).
5. **Tag** `v1.0.0` (annotated, with a message summarising the release) on `main` after merge, with Nick's approval of the merge. Reinstall on the machine (`make install`) and update the OSMods `YTPL2.md` with an update entry (version, build hash, timestamp).
6. **Publication, only with Nick's explicit in-session confirmation** (owner question 12). Show him exactly what will happen: repo name, visibility, description, topics, and that the full history will be pushed. With his yes: `gh repo create` (with the chosen visibility), push `main` and the tag, enable Dependabot alerts and secret scanning, and set the description and topics; create a GitHub release from the changelog section. Without a yes, stop after task 5 and record "not published" in the plan.
7. **Close out the project:** the plan's status table is all ✅ (or explained); the vault note gets `status: done` (or `active` if publication is pending) and a final log line; post-1.0 ideas are listed for future `/phase-add` sessions.

## Out of scope
New features, or any change to the code beyond release fixes found in task 4.

## Tests
All suites green on the release commit (record the counts); the installed `ytpl2 --version` prints 1.0.0.

## Acceptance criteria
- The v1.0.0 tag exists; CHANGELOG and the final report (with its timeline) are complete and accurate against git history.
- The machine runs the release build; OSMods updated.
- Published exactly as Nick confirmed, or explicitly not published.

## Phase-specific docs
CHANGELOG, `docs/YTPL2_FINAL-REPORT.md`, README, OSMods `YTPL2.md` update, the plan and the vault note (final state). Then the standard close-out checklist.
