# PhaseHypervisor (`phx`)

> **Status: v0.1.0 (released 2026-10-27 04:39 CDT, public repo since 2026-10-27 04:59 CDT).** `phx preflight`, `phx run` and the rest of the CLI work end to end: piloted on real sessions (`docs/PHX_PILOT_REPORT.md`), hardened against a written threat model (`docs/PHX_THREAT_MODEL.md`), and summed up in `docs/PHX_FINAL-REPORT.md` (Definition of done, measured results, known limitations, build timeline). Publishing a GitHub Release object still needs the owner's confirmation.

PhaseHypervisor is a hands-off deployer for implementation plans made with the `phased-project` method. It reads a repo's `<PREFIX>_IMPLEMENTATION_PLAN.md`, asks the owner every foreseeable question once (`phx preflight`), then runs the remaining phases one at a time. Each phase is a fresh headless Claude Code session started through `ai-provider run -p "/phase NN --auto"` on the model the plan names. PHX verifies each phase independently, waits out usage limits and resumes. The supervisor itself is a plain Python program that never calls an LLM.

PHX is additive and opt-in (ADR-0011): manual `/phased-project` and `/phase` runs keep working unchanged.

## Use PHX yourself
This repo also ships the method itself: the `phased-project` skill (which writes each project's plan, prompts and `/phase` and `/phase-add` commands) and the `/phx` command, as a Claude Code plugin with a manual-copy fallback. **Start with [docs/PHX_GETTING_STARTED.md](docs/PHX_GETTING_STARTED.md)**: what the pieces are, how to install them, a first project, and the safety model.
```text
/plugin install phased-project --marketplace antonizick/PhaseHypervisor   # the skill and /phx
uv tool install git+https://github.com/antonizick/PhaseHypervisor          # optional: phx for hands-off runs
```

## How this project is built
PHX is built with its own method. Work is split into phases in [PHX_IMPLEMENTATION_PLAN.md](PHX_IMPLEMENTATION_PLAN.md); in Claude Code, `/phase` runs the next eligible one, `/phase NN` a specific one and `/phase status` shows progress. Each phase has a self-contained prompt in [prompts/](prompts/).

| Document | Purpose |
|---|---|
| [docs/PHX_SPECIFICATION.md](docs/PHX_SPECIFICATION.md) | Canonical spec (the Amendments section overrides earlier sections) |
| [PHX_IMPLEMENTATION_PLAN.md](PHX_IMPLEMENTATION_PLAN.md) | Phase table, status, owner questions, phase log |
| [docs/PHX_DECISIONS.md](docs/PHX_DECISIONS.md) | Architecture decision records |
| [docs/PHX_ARCHITECTURE.md](docs/PHX_ARCHITECTURE.md) | Components and control flow |
| [docs/PHX_GETTING_STARTED.md](docs/PHX_GETTING_STARTED.md) | Public guide: install the plugin and `phx`, run a first phased project (Phase 12a) |
| [docs/PHX_USER_GUIDE.md](docs/PHX_USER_GUIDE.md) | How to use `phx` (grows with each phase) |
| [docs/PHX_THREAT_MODEL.md](docs/PHX_THREAT_MODEL.md) | Threats, ratings, mitigations and their tests, accepted risks (Phase 11) |
| [docs/PHX_PILOT_REPORT.md](docs/PHX_PILOT_REPORT.md) | Measured results of the real-token pilots (Phase 10) |
| [docs/PHX_FINAL-REPORT.md](docs/PHX_FINAL-REPORT.md) | v0.1.0 final report: Definition of done evidence, results, limitations, timeline (Phase 12) |
| [docs/PHX_AUTO_MODE_CONTRACT.md](docs/PHX_AUTO_MODE_CONTRACT.md) | Hands-off `/phase NN --auto` contract (version 1) shared by PHX and every phase command |
| [CLAUDE.md](CLAUDE.md) | Rules for AI agents working in this repo |

## Usage
`phx plan [<repo>] [--json]` (Phase 04) parses a phased-project repo read-only, from `main`, and prints its phase table with model aliases, Gates and live branches/worktrees, the next eligible phase, resume candidates, drift, open owner questions, the `PHX-CONTRACT` version and the test command. See [docs/PHX_USER_GUIDE.md](docs/PHX_USER_GUIDE.md).

`phx run [<repo>] [--detach] [--pause-after NN] [--until NN] [--max-phases N] [--dry-run [--skip-test-check]] [--require-preflight]` (Phase 07) runs the remaining phases hands-off: one `/phase NN --auto` session at a time on the plan's model, verified after each phase, waiting out usage limits (or resuming at once when you switch to OpenRouter), pausing at Gates and blocks with a desktop notification. `phx status`, `phx log [-f]`, `phx stop`, `phx answer <repo> <#> "<answer>"` and `phx resume` manage a run; `--detach` runs it as a systemd user unit. Install with `uv tool install --editable .`. See [docs/PHX_USER_GUIDE.md](docs/PHX_USER_GUIDE.md).

`phx preflight [<repo>]` (Phase 08) opens one interactive Claude Code session on `opus` that reads the remaining phase prompts, asks you everything it can foresee (in rounds of up to four questions, recommended answer first), records the answers and ADRs, sets Gates, and records `.phx/preflight.json`. `phx run` warns when that record is missing or stale (`--require-preflight` refuses). `--dry-run` shows the prompt and command; `--check` says whether the record is current. See [docs/PHX_USER_GUIDE.md](docs/PHX_USER_GUIDE.md).

`/phx status|run|resume|preflight [repo]` (Phase 09; from Phase 12a shipped in the plugin, `plugins/phased-project/commands/phx.md`, typed `/phased-project:phx` when installed as a plugin) drives the CLI from inside a Claude Code session. Each phase session starts through `ai-provider run` when that script is installed, otherwise through `claude` directly.

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

## Requirements
- **Linux** (supported) with Python 3.12+, [uv](https://docs.astral.sh/uv/), git and Claude Code. macOS is untested: `phx run --detach` needs `systemd-run --user` and notifications need `notify-send`, so neither works there.
- **Optional:** an `ai-provider` script on `PATH` (the author's Claude Pro / OpenRouter switch). Without it, `phx` launches `claude` directly and logs a warning once; usage-limit waits still work, only the early resume on a provider switch does not. Optional too: `notify-send` (desktop notifications), a notes vault (run summaries, `PHX_VAULT_ROOT`).
- `phx` runs repos under `$PHX_WORK_ROOT`, default `~/Work`.

Runtime code uses the Python standard library only.

## Security
PHX runs AI agents with bypassed permissions on your own machine. Read [SECURITY.md](SECURITY.md) and the [threat model](docs/PHX_THREAT_MODEL.md) before using it.

## Contributing, changes, licence
See [CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) and [CHANGELOG.md](CHANGELOG.md). Licensed under the [MIT License](LICENSE); third-party components are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
