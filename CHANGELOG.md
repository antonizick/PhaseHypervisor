# Changelog

All notable changes to PhaseHypervisor are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Phase 03: hands-off `/phase` contract version 1 (`docs/PHX_AUTO_MODE_CONTRACT.md`, ADR-0012): `--auto` / `PHX_AUTO=1` trigger, block-with-question, `refused` outcome, `PHX-RESULT` line grammar, Gate column rules, lock paths for the manual-run guard, risk rule and git-authority wording, and a manual check procedure. This repo's `/phase` now carries `PHX-CONTRACT: 1`, a PHX-running check (step 0) and a hands-off section; shared instructions gain §1b. The `phased-project` skill templates, `SKILL.md` and the playbook note carry the same rules.
- Phase 02: stdlib-only `phx` package (`uv`, `src/` layout, console script `phx`, `python -m phx`), CLI skeleton with stub subcommands (`preflight`, `run`, `resume`, `status`, `stop`, `log`, `answer`, `plan`) and `--state-dir`/`--verbose`/`--version`, state-path and `.phx/config.toml` loader (`paths.py`), redacting JSONL event logger (`logging.py`, `redact.py`), 35 tests, real CI (ruff, mypy strict, pytest on Python 3.12 and 3.14) and a pre-commit config with ruff and detect-secrets. ADR-0010 accepted.
- Phase 01: repository governance files (LICENSE, NOTICE, README, SECURITY, CONTRIBUTING, CODE_OF_CONDUCT, THIRD_PARTY_NOTICES), `.gitignore`, `.editorconfig`, `.github/` templates, Dependabot config and a placeholder CI workflow, and the `docs/PHX_ARCHITECTURE.md` skeleton.
- Phase 00: specification, decision log, implementation plan and phase prompts.
