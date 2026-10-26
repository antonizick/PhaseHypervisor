# Phase 13: Real-PC sign-off & release

**Model:** Sonnet 5.5 (`/model claude-sonnet-5-5`) · **Depends on:** 12 · **Branch:** `phase-13-signoff-release` (planning) + `deploy/phase-13-release` (product, if release edits are needed)

## Read first
`CLAUDE.md`, `prompts/CL_shared-instructions.md`, `docs/CL_SPECIFICATION.md` §6, §9.5. `CL_IMPLEMENTATION_PLAN.md` "Definition of done". `docs/CL_FINAL-REPORT.md`. Phase 12 log. **Owner questions 6 (version/release) and 7 (real-PC run) are needed here.**

## Goal
Nick confirms on his own Windows PC that the docs work for a real Windows user, the release is cut (only with Nick's confirmation), and the project is wrapped up in the vault.

## Tasks
1. **Guided real-PC run (owner question 7):** give Nick a printable checklist `docs/WSL2-SIGNOFF.md` that follows `docs/install/windows-wsl2.md` step by step, with "what you should see" and a box to tick or note problems at each step, plus how to send back the install log (with the scrub reminder). Nick runs it; the agent fixes any doc issue (small PR, with OK) and records the result in FINDINGS and the Phase Log. If the PC already has WSL/Docker, record its state first (`wsl --version`, `wsl -l -v`, `%UserProfile%\.wslconfig`, Docker Desktop yes/no and whether its WSL integration is on). The checklist must include what the lab could not show (ADR-0017): ChessLoop still answers after closing Ubuntu, after sleep and after a real restart; and, if Nick wants it, a real phone on a Private home network reaching it with mirrored networking.
2. **Version (owner question 6):** propose a version from the CHANGELOG (SemVer; first tagged release) and a release title; Nick decides. Move `[Unreleased]` → `[x.y.z] - <date>` with the real date.
3. **Pin installs to the release:** set `deploy.sh`'s default `CHESSLOOP_REF` to the latest release tag (fetched at run time via the GitHub API, falling back to `main` with a warning) **if** Nick agrees; the docs' one-liner points at the tag's `deploy.sh` or stays on `main`, consistent with the decision (record an ADR).
4. **Release (only with Nick's explicit OK):** merge the release PR, `git tag -a vX.Y.Z` on `main` (signed if Nick's setup allows), push the tag, `gh release create` with notes from the CHANGELOG (highlights for existing users: the volume migration, the new first-login flow, the new docs). Verify that the one-line install from the release works on one clean VM.
5. **Definition of done:** tick every box in `CL_IMPLEMENTATION_PLAN.md` with evidence links; anything unmet → `⛔ Blocked` with the reason, or a `/phase-add` follow-up with Nick's agreement.
6. **Wrap-up:** vault note (status `complete`, a summary, links to the FINAL-REPORT and the release), OSMods (whether to keep the Incus lab: ask Nick; if removing it, follow the documented undo and update OSMods), and remove the remaining worktrees.

## Scope note (ADR-0025)
Release notes and the README say ChessLoop's install is for personal, private use (this computer, a home network, Windows via WSL); hosting it on the internet is not covered.

## Out of scope
New features.

## Tests
A one-line install of the released version on a clean ubuntu-24.04 VM + smoke; Nick's checklist results.

## Acceptance criteria
- Nick's real-PC WSL2 run passed (or its issues are fixed and re-checked by him).
- The release exists on GitHub with notes (only if Nick approved); the install from it works.
- Definition of done fully ticked; vault note and OSMods final.

## Phase-specific docs
Product: CHANGELOG, README (version references). Planning: `docs/WSL2-SIGNOFF.md`, FINDINGS, ADR (release pinning), Phase Log, vault note. Then the standard close-out checklist.

## Phase 12 results (read before Tasks 2-4)
- **`main` is protected (ADR-0034):** a release PR merges only when every required check is green (Backend tests, Frontend lint and build, ShellCheck, Compose files validate, Dockerfile lint (hadolint), Image build and scan ×3, Dependency audit, Install smoke, Docs links, Secret scan). Nick can bypass as admin; don't ask him to. Renaming a CI job means updating the protection rule in the same PR.
- **The image scan can turn red without a code change** when a new HIGH/CRITICAL with a fix is published for a base image or package. Rebuild first (the nginx images run `apk upgrade`); if it's a Python package, bump it after checking the release is at least two weeks old; record it as a finding.
- **New in the stack:** a one-shot `data-owner` service (exits 0 at every `up`) hands old root-owned data to the non-root backend (ADR-0033). The checklist for Nick's PC can mention that `docker ps -a` shows it as "Exited (0)" (troubleshooting guide covers it).
- **Release notes highlights to add:** non-root backend, MFA code limit, the `nick` username privilege removed (F-050), Docker key fingerprint check, PyJWT (nobody is signed out), browser-error-log limits, accessibility labels.
- **Open for Nick:** F-085 (dark-theme grey text contrast; palette change across all screens), F-070 app-side polish (seedbot author name, small text, counters), the React Router v7 upgrade (F-084). None blocks the release.
- **Evidence:** `runs/2026-10-18-regression/notes.md` (Linux and WSL matrix), `docs/CL_FINAL-REPORT.md`.
