# PhaseHypervisor (`phx`)

> **Status: pre-release.** `phx run` (Phase 07) and `phx preflight` (Phase 08) work; rollout to existing projects (09) and real-token pilots (10) are still to come.

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
| [docs/PHX_USER_GUIDE.md](docs/PHX_USER_GUIDE.md) | How to use `phx` (grows with each phase) |
| [docs/PHX_AUTO_MODE_CONTRACT.md](docs/PHX_AUTO_MODE_CONTRACT.md) | Hands-off `/phase NN --auto` contract (version 1) shared by PHX and every phase command |
| [CLAUDE.md](CLAUDE.md) | Rules for AI agents working in this repo |

## Usage
`phx plan [<repo>] [--json]` (Phase 04) parses a phased-project repo read-only, from `main`, and prints its phase table with model aliases, Gates and live branches/worktrees, the next eligible phase, resume candidates, drift, open owner questions, the `PHX-CONTRACT` version and the test command. See [docs/PHX_USER_GUIDE.md](docs/PHX_USER_GUIDE.md).

`phx run [<repo>] [--detach] [--pause-after NN] [--until NN] [--max-phases N] [--dry-run] [--require-preflight]` (Phase 07) runs the remaining phases hands-off: one `/phase NN --auto` session at a time on the plan's model, verified after each phase, waiting out usage limits (or resuming at once when you switch to OpenRouter), pausing at Gates and blocks with a desktop notification. `phx status`, `phx log [-f]`, `phx stop`, `phx answer <repo> <#> "<answer>"` and `phx resume` manage a run; `--detach` runs it as a systemd user unit. Install with `uv tool install --editable .`. See [docs/PHX_USER_GUIDE.md](docs/PHX_USER_GUIDE.md).

`phx preflight [<repo>]` (Phase 08) opens one interactive Claude Code session on `opus` that reads the remaining phase prompts, asks you everything it can foresee (in rounds of up to four questions, recommended answer first), records the answers and ADRs, sets Gates, and records `.phx/preflight.json`. `phx run` warns when that record is missing or stale (`--require-preflight` refuses). `--dry-run` shows the prompt and command; `--check` says whether the record is current. See [docs/PHX_USER_GUIDE.md](docs/PHX_USER_GUIDE.md).

## Development setup
```bash
uv sync                      # create .venv and install the dev tools
uv run phx --help
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run coverage run -m pytest && uv run coverage report   # branch coverage
uv run pre-commit install    # ruff + detect-secrets on each commit
```
The runtime needs no install: `cd src && python3 -m phx --version` works on any Python 3.12+.

## Requirements (target)
Linux, Python 3.12+, [uv](https://docs.astral.sh/uv/), Claude Code and the local `ai-provider` switch script. Runtime code uses the Python standard library only.

## Security
PHX runs AI agents with bypassed permissions on your own machine. Read [SECURITY.md](SECURITY.md) before using it.

## Contributing, changes, licence
See [CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) and [CHANGELOG.md](CHANGELOG.md). Licensed under the [MIT License](LICENSE); third-party components are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
