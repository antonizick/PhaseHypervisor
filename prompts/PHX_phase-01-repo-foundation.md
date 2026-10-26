# PHX Phase 01: Repository foundation & governance

**Model:** Sonnet 5.5 (`/model claude-sonnet-5-5`) · **Depends on:** 00 · **Branch:** `phase-01-repo-foundation`

## Read first
`CLAUDE.md`, `prompts/PHX_shared-instructions.md`, spec §2, §4.1 (A1, A4) and §4.4. Phase Log entry for 00. Owner question 1 (licence): if still open, use the proposed default MIT, and say so in the Phase Log.

## Goal
A GitHub-ready repository with complete governance files, a docs skeleton, and a private GitHub remote, so every later phase has a home for its docs and CI.

## Tasks
1. `LICENSE` (owner question 1; default MIT, copyright "Nick Antoncic"), `NOTICE`, `THIRD_PARTY_NOTICES.md` (none yet; say so).
2. `README.md`: what PHX is, status "pre-release, under construction", how the project is built (`/phase`), links to the spec, plan and decisions. No usage instructions yet beyond "see Phase 07".
3. `SECURITY.md`: scope (local tool that runs AI agents with bypassed permissions on the owner's machine), how to report, the S1–S5 baseline in plain words.
4. `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1, referenced by URL rather than pasted if you can't verify the text), `CHANGELOG.md` (Keep a Changelog, `[Unreleased]`).
5. `.gitignore` (Python, uv, `.venv`, `.phx/state*`, `*.jsonl` session logs if any land in-repo), `.editorconfig`.
6. `.github/`: issue templates (bug, feature), PR template, `dependabot.yml` (github-actions + pip/uv weekly), a placeholder CI workflow that Phase 02 fills in.
7. `docs/PHX_ARCHITECTURE.md` skeleton: the component list from shared instructions §2 and a sequence sketch of `phx run` → `ai-provider run -p "/phase NN --auto"` → verify → next.
8. Create the **private** GitHub repo `antonizick/PhaseHypervisor` with `gh repo create --private --source . --remote origin` and push `main` (ADR-0004). If the name is taken, stop and ask.

## Out of scope
Python code and CI contents (Phase 02); the auto-mode contract (Phase 03).

## Tests
None beyond: `gh repo view antonizick/PhaseHypervisor --json visibility` shows `PRIVATE`; every Markdown link in the new files resolves.

## Acceptance criteria
- All governance files exist and are accurate for a local AI-orchestration tool.
- Remote `origin` exists, is private, and `main` is pushed.

## Phase-specific docs
The files above. Then the standard close-out checklist.
