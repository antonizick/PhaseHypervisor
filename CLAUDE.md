# PhaseHypervisor: Agent Instructions

These rules apply to every AI agent working in this repository. They are **mandatory**.

## What this project is
PhaseHypervisor (`phx`) is a hands-off deployer for implementation plans made by Nick's `phased-project` skill. It reads a repo's `<PREFIX>_IMPLEMENTATION_PLAN.md`, asks Nick foreseeable questions once (`phx preflight`), then runs the remaining phases one at a time. Each phase is a fresh headless Claude Code session started through `ai-provider run -p "/phase NN --auto"` on the model the plan names. PHX verifies each phase independently, waits out usage limits and resumes. Stack: Python ≥ 3.12, standard library only at runtime; `uv`, pytest, ruff and mypy for development. The supervisor itself never calls an LLM.

## Naming and timestamps (mandatory)
- **Project prefix: `PHX`.** Project documents are named `PHX_<NAME>` (`PHX_IMPLEMENTATION_PLAN.md`, `docs/PHX_DECISIONS.md`, `prompts/PHX_phase-NN-<slug>.md`…) so they can be told apart from other projects' documents without their path. Any new project-specific document gets the prefix. `CLAUDE.md`, `README.md`, `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md` and the like keep their conventional names.
- **Timestamps everywhere a date is recorded** (Phase Log, ADRs, amendments, owner questions, vault log, "Last updated"): `YYYY-MM-DD HH:MM TZ`, from `date '+%Y-%m-%d %H:%M %Z'` at the moment you write it. Never a bare date, never guessed.

## Source-of-truth documents (read before working)
| File | Purpose |
|---|---|
| `docs/PHX_SPECIFICATION.md` | Canonical spec. **The Amendments section overrides earlier sections.** |
| `PHX_IMPLEMENTATION_PLAN.md` | Phase table, status, owner questions, phase log. **Keep it accurate.** |
| `prompts/PHX_shared-instructions.md` | Conventions and close-out checklist for every phase |
| `prompts/PHX_phase-NN-*.md` | The prompt for the phase you are executing (start sessions with `/phase`) |
| `docs/PHX_DECISIONS.md` | ADR log; append, never rewrite |

## Mandatory documentation upkeep
Documentation is part of the deliverable. A phase is **not complete** until all of the following are done:
1. `PHX_IMPLEMENTATION_PLAN.md`: set the phase's status as icon plus word (`🔄 In progress` when you start; `✅ Complete` or `⛔ Blocked` at the end) and add a timestamped Phase Log entry whose **first bullet is the Timeline** (`started` = the claim commit's time, `finished` = `date` as your last step, `merged`, any `blocked` interval; format in the plan's Phase Log header), then built, deviations, follow-ups, tests. **`🔄 In progress` must be committed to `main` before any other work** (the claim protocol in `prompts/PHX_shared-instructions.md` §1a). A status that exists only on a phase branch or in a worktree does not count.
2. `CHANGELOG.md`: add entries under `[Unreleased]`.
3. Update every affected document: README, SECURITY, `docs/PHX_ARCHITECTURE.md`, guides, THIRD_PARTY_NOTICES, `.gitignore`.
4. `docs/PHX_DECISIONS.md`: add an ADR for any non-trivial choice or deviation. If the spec changes, add an amendment.
5. **Later phase prompts:** if your work changes an assumption a later prompt relies on, edit that prompt.
6. The Obsidian project note `/home/nick/Documents/02 Projects/PHX Implementation Plan.md`: update the status table (icons), the `updated:` field and add a timestamped log line.
7. Any host OS change (systemd units, files in `~/.local/bin`, keybindings) must also be documented in `/home/nick/Documents/04 Resources/OSMods/` (read its README first). Changes to the `phased-project` skill must be mirrored in `/home/nick/Documents/04 Resources/Claude Code Phased Project Method.md`, and vice versa.

## Risk rule (mandatory, ADR-0003)
Sessions may run with bypassed permissions. **If an action looks high-risk, irreversible or a bad idea, stop and ask Nick instead of doing it.** In an interactive session, ask. In a hands-off session (`/phase NN --auto` or `PHX_AUTO=1`), block the phase with the question recorded (block-with-question, `prompts/PHX_shared-instructions.md` §1b; contract `docs/PHX_AUTO_MODE_CONTRACT.md`). Examples: deleting data you did not create, touching another project's files outside the scope your prompt names, changing system-wide config not covered by the prompt, spending money beyond a stated cap, making a repo public, publishing a release, force-pushing shared history, anything that speaks aloud through Prometheus.

## Engineering rules
- Stay within the phase's scope; record out-of-scope findings as follow-ups in the Phase Log.
- Tests, lint and type checks must pass before a phase closes: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src` (available from Phase 02).
- Runtime code uses the Python standard library only (ADR-0010). Dev dependencies are pinned in `uv.lock`.
- Never commit secrets or personal data. Never read, print or copy `~/.config/ai-provider/openrouter.key`, and never use MeetingMaster3's OpenRouter key.
- Tests never launch a real Claude session or spend tokens unless the phase prompt explicitly says so (Phase 10). Use the fake `claude` / fake `ai-provider` from Phase 05.
- Follow the security and safety baseline in the spec's Amendments (§4.3).
- Git: branch `phase-NN-<slug>` in its own worktree `../PhaseHypervisor-phase-NN`; the main checkout stays on `main`. Conventional Commits, commit at checkpoints. **Git/GitHub authority (ADR-0004):** you may commit, merge, push and create **private** GitHub repos without asking. Making a repo public, publishing a GitHub release, or force-pushing shared history requires Nick's explicit confirmation (in hands-off mode: block-with-question).
- Reference machine: Omarchy (Arch, Hyprland), Linux 7.2, Python 3.14.8, uv 0.13.0, gh 2.103.2 (logged in as `antonizick`), Claude Code 2.1.310 at `~/.local/share/mise/installs/claude/latest/claude`, `ai-provider` at `~/.local/bin/ai-provider` (Super+Alt+A).
