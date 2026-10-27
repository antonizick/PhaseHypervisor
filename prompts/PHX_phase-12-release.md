# PHX Phase 12: Release v0.1.0

**Model:** Sonnet 5.5 (`/model claude-sonnet-5-5`) · **Depends on:** 11 · **Branch:** `phase-12-release` · **Gate:** review

## Read first
`CLAUDE.md`, `prompts/PHX_shared-instructions.md`, the plan's Definition of done, ADR-0004, `docs/PHX_THREAT_MODEL.md`. All Phase Log entries. Phase Log entry for 11.

## Goal
Ship PHX v0.1.0 to Nick's private GitHub repo with a final report, and leave it installed and documented for daily use.

## Tasks
1. Check every Definition of done box with evidence (a test, a log excerpt or a pilot result).
2. Version `0.1.0` in `pyproject.toml` and `phx --version`; CHANGELOG release heading with a timestamp.
3. `docs/PHX_FINAL-REPORT.md`: what was built, measured results from the pilots, known limitations (start from the accepted residual risks in `docs/PHX_THREAT_MODEL.md` §3 and the follow-ups Phase 11 deferred), and the **visual timeline** of planning and build phases (starts, stops, blocked intervals) drawn from the Phase Log Timeline bullets and git history (ASCII or Mermaid gantt).
4. Tag `v0.1.0` and push `main` and the tag to the private `origin` (ADR-0004). **Do not** make the repo public or create a GitHub Release object: ask Nick in the final message whether he wants either.
5. Confirm the installed `phx` is the released version; update the OSMods write-up and the vault project note (status `complete` in frontmatter when done).
6. Update the playbook note's "Hands-off runs" section with the released command set.

## Out of scope
New features; public publication without Nick's confirmation.

## Tests
Full suite, lint, types, CI green on the tag.

## Acceptance criteria
- Tag `v0.1.0` on the private remote; CI green; Definition of done fully checked.
- Final report includes the timeline.

## Phase-specific docs
Final report, CHANGELOG, README, OSMods, vault note, playbook. Then the standard close-out checklist.
