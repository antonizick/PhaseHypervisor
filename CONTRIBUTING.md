# Contributing to PhaseHypervisor

PhaseHypervisor (`phx`) is a personal tool that is built phase by phase with the project's own method. The repository is public and outside contributions are welcome.

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

## Changing the skill, templates or `/phx`
The `phased-project` skill, its templates and the `/phx` command live in `plugins/phased-project/` (ADR-0022, ADR-0024). Everything there is public on push.
1. Edit the files in `plugins/phased-project/`. Templates use `{{NAME}}` markers and the `{{#NAME}}…{{/NAME}}` / `{{^NAME}}…{{/NAME}}` sections described in the skill's "Settings and template markers"; `tests/plugin_render.py` implements the same rules.
2. Never write personal names, paths or private project names there: `tests/test_plugin_package.py` has a deny-list.
3. Hands-off contract text (`PHX-CONTRACT: 1`, step 0, the "Hands-off mode" section, §1b) must stay as it is unless the contract version changes (ADR-0012). The tests compare it with fixed text and with the pre-12a copies in `tests/fixtures/skill_pre12a/`; if you change it on purpose, update those and say why in an ADR.
4. Run `uv run pytest tests/test_plugin_package.py` and `claude plugin validate .` and `claude plugin validate plugins/phased-project`.
5. Update [docs/PHX_GETTING_STARTED.md](docs/PHX_GETTING_STARTED.md) when what a user sees or types changes. A plugin version bump goes with a repo release (`plugin.json` matches `phx --version`).

## Reporting bugs and ideas
Use the issue templates in `.github/ISSUE_TEMPLATE/`. For security problems follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

By contributing you agree that your contribution is licensed under the [MIT License](LICENSE).
