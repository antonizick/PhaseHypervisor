# Third-party notices

PhaseHypervisor currently bundles **no third-party code**. The runtime uses only the Python standard library (ADR-0010 in [docs/PHX_DECISIONS.md](docs/PHX_DECISIONS.md)).

Development tools are used to build and test the project, are not redistributed with it, and are pinned in `uv.lock` (transitive dependencies are listed there). Licences are those declared by each project.

| Component | Version | Licence | Used for |
|---|---|---|---|
| uv | 0.13.0 | MIT OR Apache-2.0 | environment and lock management |
| hatchling | build backend | MIT | building the wheel |
| pytest | 9.1.1 | MIT | tests |
| ruff | 0.17.2 | MIT | lint and format |
| mypy | 2.4.0 | MIT | strict type checks |
| coverage | 7.17.0 | Apache-2.0 | branch coverage (Phase 04) |
| pre-commit | 4.7.0 | MIT | git hooks |
| detect-secrets | 1.5.0 (pre-commit hook) | Apache-2.0 | secret scan |
