# PHX Phase 02: Python scaffold, CLI skeleton & CI

**Model:** Sonnet 5.5 (`/model claude-sonnet-5-5`) · **Depends on:** 01 · **Branch:** `phase-02-python-scaffold`

## Read first
`CLAUDE.md`, `prompts/PHX_shared-instructions.md` (§2 layout, §3 conventions), spec §4.2 R1, R10, §4.3 S2. ADR-0010 (Proposed). Phase Log entry for 01.

## Goal
An installable, stdlib-only `phx` package with a working CLI skeleton, the logging and redaction core every later phase builds on, and green CI.

## Tasks
1. `pyproject.toml` (uv; `requires-python = ">=3.12"`; **no runtime dependencies**; dev group: pytest, ruff, mypy, pre-commit), `uv.lock`, `src/phx/` layout, console script `phx = "phx.cli:main"` and `python -m phx`.
2. `cli.py`: argparse with subcommands `preflight`, `run`, `resume`, `status`, `stop`, `log`, `answer`, `plan` (debug: parse and print a plan). Each stub prints "not implemented yet (Phase NN)" and exits 2. Global flags: `--state-dir`, `--verbose`, `--version`.
3. `paths.py`: XDG-correct state dir `~/.local/state/phx/<repo-name>/`, sessions subdir, per-repo `.phx/config.toml` loader (`tomllib`) with typed defaults (test command override, OpenRouter `max_budget_usd`, poll intervals, triage on/off).
4. `logging.py`: append-only JSONL event logger (`ts` as `YYYY-MM-DD HH:MM:SS TZ` plus ISO epoch, `event`, `phase`, `reason`, extra fields); fsync on write; also a human-readable stderr mirror.
5. `redact.py`: redact `sk-or-…`, `sk-ant-…`, `ANTHROPIC_AUTH_TOKEN=…`, `ANTHROPIC_API_KEY=…`, `Authorization: Bearer …` and GitHub tokens (`ghp_`, `gho_`, `github_pat_`) from any string or nested JSON. Every logger write goes through it.
6. CI (`.github/workflows/ci.yml`): uv setup, `uv run ruff check .`, `ruff format --check`, `mypy src` (strict), `pytest`, on Python 3.12 and 3.14.
7. `.pre-commit-config.yaml` with ruff and a secret scan (gitleaks or detect-secrets; check the licence and pin the version).
8. Confirm ADR-0010: list the stdlib modules later phases need (subprocess, json, tomllib, fcntl, signal, argparse, shutil, datetime, zoneinfo, uuid) and mark ADR-0010 Accepted, or record why not.

## Out of scope
Plan parsing (04), launching sessions (05), the supervisor (07).

## Tests
Redaction (each secret pattern, nested JSON, no false positives on normal text and hashes); logger writes valid JSONL and survives concurrent appends; config defaults and overrides; CLI help and stubs.

## Acceptance criteria
- `uv run phx --help` lists all subcommands; `python3 -m phx --version` works **without** `uv` from `src/` on the host Python 3.14.8.
- All checks pass locally and in CI on GitHub.

## Phase-specific docs
`docs/PHX_ARCHITECTURE.md` (modules and state layout), README (dev setup), CHANGELOG, ADR-0010 status. Then the standard close-out checklist.
