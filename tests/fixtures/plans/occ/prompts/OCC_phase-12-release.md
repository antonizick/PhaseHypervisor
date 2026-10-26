# OCC Phase 12: Release & publication

**Model:** Sonnet 5.5 (`/model claude-sonnet-5-5`) · **Depends on:** 11, 07a · **Branch:** `phase-12-release` · **Worktree:** `../OCC_OmarchyControlCenter-phase-12`

## Read first
`CLAUDE.md`, `prompts/OCC_shared-instructions.md`, spec §13.1 (A4), §13.4, §13.5. ADR-0004. The whole Phase Log (for the final report and timeline) and the Definition of done. **Owner question 9** (repository name/account, screenshots) must be answered before any publishing step.

## Goal
OCC v1.0.0 is tagged with an accurate changelog, a final report with a visual timeline of the project, every Definition-of-done item ticked with evidence, and, **only if Nick explicitly confirms in this session**, published to GitHub.

## Tasks
1. Verify the Definition of done end to end on the machine (fresh `make install` from a clean clone, `Super + Alt + T`, all five services, quit, reboot-free check that RClone units are still enabled). Tick each item with evidence.
2. `CHANGELOG.md`: move `[Unreleased]` into `## [1.0.0] - <timestamp from date>` with Added/Changed/Security sections; add compare links once a remote exists.
3. README final pass: screenshots (per Q9), install, usage, configuration, adding a service, security model, performance summary, troubleshooting links, licence. Check every link.
4. `docs/OCC_FINAL-REPORT.md`: what was built vs the spec's success criteria (each with evidence), decisions (ADR index), deviations, measured results, known limits, future ideas (spec product phase 3 leftovers: notifications/omarchy CLI integration), and a **visual timeline** of planning and build phases (starts, finishes, blocked intervals, parallel phases) drawn from every Phase Log **Timeline** bullet and `git log` (claim commits `chore(plan): start phase NN`, merges). A Mermaid `gantt` chart is fine; make sure parallel phases (05/06, 07/08) are visible.
5. Tag `v1.0.0` (annotated) on `main` after the merge; build the release binary (`make build`, record its SHA-256).
6. **Publication (requires Nick's explicit confirmation in this session; ask, show exactly what will happen, wait):** create the GitHub repo per Q9 (`gh repo create …`), set the module path if Q9 changes it (and rebuild/tests), push `main` and the tag, create a release with the binary and checksum, check that CI passes on GitHub and that no personal config or secrets are in the history (`git log -p | grep` for key patterns and `/home/nick` paths beyond the documented example). If Nick declines, stop after task 5 and record that.
7. Update the vault note to `status: complete` (or `released`) and the OSMods note with the released version.

## Out of scope
New features (use `/phase-add`).

## Tests
Full `make check`, `go test -tags integration ./...`, the Definition-of-done walkthrough, link check, CI green on GitHub if published.

## Acceptance criteria
- Every Definition-of-done box ticked with evidence.
- `v1.0.0` tag and changelog entry with a timestamp.
- Final report with timeline exists and matches the Phase Log.
- Published only with recorded confirmation (quote Nick's answer and its timestamp in the Phase Log), or explicitly not published.

## Phase-specific docs
`docs/OCC_FINAL-REPORT.md`, CHANGELOG, README, vault note, OSMods note. Then the standard close-out checklist.
