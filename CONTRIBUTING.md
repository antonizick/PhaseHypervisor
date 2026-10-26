# Contributing to PhaseHypervisor

PhaseHypervisor (`phx`) is a personal tool that is built phase by phase with the project's own method. Outside contributions are welcome once the repository is public; until then it is a private project.

## Ground rules
- Read [CLAUDE.md](CLAUDE.md), [docs/PHX_SPECIFICATION.md](docs/PHX_SPECIFICATION.md) (its Amendments override earlier sections) and [prompts/PHX_shared-instructions.md](prompts/PHX_shared-instructions.md) first.
- Work is organised in phases listed in [PHX_IMPLEMENTATION_PLAN.md](PHX_IMPLEMENTATION_PLAN.md). Run one with `/phase NN` in Claude Code; a human contributor follows the same prompt file by hand.
- Runtime code uses the Python standard library only (ADR-0010). Development dependencies are pinned in `uv.lock`.
- Never commit secrets or personal data. Never read, print or copy `~/.config/ai-provider/openrouter.key`.

## Workflow
1. Branch `phase-NN-<slug>` in its own worktree (`git worktree add ../PhaseHypervisor-phase-NN -b phase-NN-<slug> main`).
2. Use [Conventional Commits](https://www.conventionalcommits.org/) and commit at checkpoints.
3. Before a phase closes, these must pass (available from Phase 02): `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`.
4. Update the documentation the change touches: CHANGELOG `[Unreleased]`, the plan's Phase Log, ADRs for non-trivial choices.
5. Tests never launch a real Claude session or spend tokens; use the fakes.

## Reporting bugs and ideas
Use the issue templates in `.github/ISSUE_TEMPLATE/`. For security problems follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

By contributing you agree that your contribution is licensed under the [MIT License](LICENSE).
