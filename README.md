# PhaseHypervisor (`phx`)

> **Status: pre-release, under construction.** Nothing here is usable yet.

PhaseHypervisor is a hands-off deployer for implementation plans made with the `phased-project` method. It reads a repo's `<PREFIX>_IMPLEMENTATION_PLAN.md`, asks the owner every foreseeable question once (`phx preflight`), then runs the remaining phases one at a time. Each phase is a fresh headless Claude Code session started through `ai-provider run -p "/phase NN --auto"` on the model the plan names. PHX verifies each phase independently, waits out usage limits and resumes. The supervisor itself is a plain Python program that never calls an LLM.

PHX is additive and opt-in (ADR-0011): manual `/phased-project` and `/phase` runs keep working unchanged.

## How this project is built
PHX is built with its own method. Work is split into phases in [PHX_IMPLEMENTATION_PLAN.md](PHX_IMPLEMENTATION_PLAN.md); in Claude Code, `/phase` runs the next eligible one, `/phase NN` a specific one and `/phase status` shows progress. Each phase has a self-contained prompt in [prompts/](prompts/).

| Document | Purpose |
|---|---|
| [docs/PHX_SPECIFICATION.md](docs/PHX_SPECIFICATION.md) | Canonical spec (the Amendments section overrides earlier sections) |
| [PHX_IMPLEMENTATION_PLAN.md](PHX_IMPLEMENTATION_PLAN.md) | Phase table, status, owner questions, phase log |
| [docs/PHX_DECISIONS.md](docs/PHX_DECISIONS.md) | Architecture decision records |
| [docs/PHX_ARCHITECTURE.md](docs/PHX_ARCHITECTURE.md) | Components and control flow |
| [CLAUDE.md](CLAUDE.md) | Rules for AI agents working in this repo |

## Usage
The `phx` command exists as a skeleton (Phase 02): `phx --help` lists the subcommands, and each one exits with "not implemented yet (Phase NN)" until its phase lands (`plan` in 04, `run` and friends in 07, `preflight` in 08).

## Development setup
```bash
uv sync                      # create .venv and install the dev tools
uv run phx --help
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pre-commit install    # ruff + detect-secrets on each commit
```
The runtime needs no install: `cd src && python3 -m phx --version` works on any Python 3.12+.

## Requirements (target)
Linux, Python 3.12+, [uv](https://docs.astral.sh/uv/), Claude Code and the local `ai-provider` switch script. Runtime code uses the Python standard library only.

## Security
PHX runs AI agents with bypassed permissions on your own machine. Read [SECURITY.md](SECURITY.md) before using it.

## Contributing, changes, licence
See [CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) and [CHANGELOG.md](CHANGELOG.md). Licensed under the [MIT License](LICENSE); third-party components are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
