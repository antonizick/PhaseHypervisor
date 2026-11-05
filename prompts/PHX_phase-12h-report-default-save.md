# PHX Phase 12h: `phx report` saves a vault note and charts by default

**Model:** Opus 5.5 (`/model claude-opus-5-5`) · **Depends on:** 12g · **Branch:** `phase-12h-report-default-save` · **Worktree:** `../PhaseHypervisor-phase-12h` · **Gate:** review

Today `phx report` only prints, so a report is kept only if Nick remembers `--vault` and `--svg DIR`. This phase makes saving the default: a plain run also writes the timestamped vault note and the charts, in a `charts<date time stamp>` folder beside the note. It ends the "read-only" default that ADR-0032 set, for the vault only (ADR-0035).

## Read first
`CLAUDE.md` (risk rule, docs upkeep), `prompts/PHX_shared-instructions.md` (§1a claim, §4a timeline refresh), **ADR-0035** (this phase's decisions), ADR-0032 and ADR-0034 (the report's rules), `src/phx/cli.py:_cmd_report`, `src/phx/report/render.py:write_vault`, `src/phx/report/svg.py:write_charts`, `src/phx/vault.py:vault_root`, `tests/conftest.py`.

## Nick's request (verbatim intent, 2026-11-05 06:26 CST)
> update the phx report function such when it runs with just a 'phx report' Command the --vault option is always invoked, also the --svc option is always invoked, have the folder of the charts have a charts<date time stamp> format

`--svc` is read as `--svg`; no such option exists.

## Decisions already made (ADR-0035)
- **When it saves:** unless an output was chosen. `phx report`, and filtered views such as `phx report --by quarter` or `phx report my-repo`, save. An explicit `--json`, `--markdown`, `--svg` or `--vault` does only what it says.
- **Where:** a `charts<stamp>` folder beside the note in `<vault>/04 Resources/PHX Reports/`, sharing the note's time stamp, with the four charts embedded in the note.
- **Opt-out:** `--no-save` prints only.

## Goal
`phx report` still prints the report, and also leaves one new note and one new charts folder in the vault, with the charts visible in the note in Obsidian.

## What exists (verified 2026-11-05 06:26 CST; re-check before relying on it)
- `cli.py:_cmd_report` gates `--svg` and `--vault` separately and prints afterwards. `args.svg` is `Path | None`, `args.vault` a bool, `args.markdown` is `None` when absent (`"-"` when bare), `args.json` a bool. Messages go to stderr.
- `render.py:write_vault` makes the note name from `now_ts(now)` (`PHX Report YYYY-MM-DD HHMM`), creates it with `O_EXCL`, adds ` (2)` on a clash, and never overwrites. A missing vault returns `(None, message)`. `VAULT_FOLDER` is `04 Resources/PHX Reports`.
- `svg.py:write_charts(report, directory)` uses `exist_ok=True` and overwrites, which is fine for `--svg DIR` but not for a stamped folder. Names: `phx-report-cost.svg`, `-cost-per-phase.svg`, `-active-hours.svg`, `-model-mix.svg`.
- **Hazard:** `tests/test_report.py` (`:774`, `:855`, `:869`) and `tests/test_report_projects.py` (`:522`) call `main(["report", ...])` with no output option. After this change they would write into the real vault unless `PHX_VAULT_ROOT` is isolated first.
- "Read-only" is claimed in `cli.py` (`COMMANDS["report"]`), `report/__init__.py`, `render.py`'s docstring, the README command row, `docs/PHX_USER_GUIDE.md` and `docs/PHX_ARCHITECTURE.md`. All become untrue for the default run.
- Nothing under `plugins/`, `examples/` or `docs/PHX_GETTING_STARTED.md` mentions `phx report`.

## Tasks
1. **Isolate tests first, in its own commit.** An autouse fixture in `tests/conftest.py` sets `PHX_VAULT_ROOT` to a per-test temporary path that does not exist, so no test can reach the real vault. Add a guard test that a default run with that isolation writes nothing outside `tmp_path`. Confirm the suite passes before changing behaviour.
2. **Default rule.** In `_cmd_report`, save when not `--no-save` and none of `--json`, `--markdown`, `--svg` or `--vault` was given. Filters and `--no-repos`, `--top`, `--state-root` do not count as outputs. Add `--no-save`. `--no-save` with `--vault` or `--svg` is an error (`EXIT_ERROR`, message on stderr); with `--json` or `--markdown` it is harmless. The "no recorded runs" exit saves nothing.
3. **Charts folder.** Name: `charts<YYYY-MM-DD-HHMM>`, for example `charts2026-11-05-0624`, taken from the same `now` as the note. Create it with `mkdir(exist_ok=False)`, adding `-2`, `-3` on a clash, so it never reuses a folder. Keep `write_charts` as it is for `--svg DIR`; add a small function that reserves the stamped folder and calls it.
4. **Embeds.** Write charts first, then the note, with `![[<folder>/<file>.svg]]` for each chart in a `## Charts` section, placed after the Projects section or first if there is none. Only the default run embeds: an explicit `--vault` keeps today's note, and `to_markdown` without charts is byte-identical to today.
5. **Failures.** One `now` per run. No vault: one stderr message, nothing written anywhere else, exit 0. Charts cannot be written: say so and still write the note, without embeds. A note that cannot be written leaves the charts and says so. The terminal report prints in every case.
6. **Output.** The report text still goes to stdout unchanged, so `phx report > file` still works; `wrote …` lines stay on stderr.
7. **Docs.** Correct every "read-only" claim listed above: reading stays read-only over logs and repos, and the only default writes are the two vault items. Update the guide (the default, `--no-save`, the folder name, embeds, that `--state-root` still saves, that notes accumulate), the README row and sentence, and `docs/PHX_ARCHITECTURE.md`. Add spec amendment R27 and a threat-model line for the new default write.
8. **Real check.** Run `phx report` once for real: open the note, confirm the four charts embed in Obsidian's format, and leave that note and folder as the first real output. Confirm `--no-save`, `--json` and `phx report --by quarter` behave as decided, removing only the extra notes and folders this phase created for checking. Give Nick the two paths in the final message, since this is a `review` phase.

## Out of scope
- Pruning or rotating old notes and folders. An option for a charts location. A setting that turns the default off permanently.
- Changing `--svg DIR` or `--vault` when given explicitly, the report's figures, or the charts themselves.
- Any version bump, tag or GitHub Release.

## Tests
- Default rule, one test each: bare; `--by quarter`; a named repo; `--no-repos`; each explicit output writes only what it says; `--no-save`; the `--no-save` conflicts; "no recorded runs" writes nothing.
- Folder: the name, shared stamp with the note, a same-minute second run gets its own note and folder and overwrites neither.
- Embeds: each chart once, every target exists; absent on explicit `--vault`; `to_markdown` unchanged without charts.
- Failures: no vault, unwritable charts, unwritable note, each with stdout still complete.
- State root and repos unchanged after a default run; a manual-only window saves with empty charts.
- `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src` and pre-commit stay clean.

## Acceptance criteria
- `phx report` prints as before, and leaves one new note and one `charts<stamp>` folder in `04 Resources/PHX Reports/`, with four charts showing in the note.
- `phx report --by quarter` does the same; `--json`, `--markdown`, `--svg DIR` and `--vault` do only what they say; `--no-save` writes nothing.
- A test run leaves the real vault untouched.
- Nothing is written under the state root or in any repo, and no "read-only" claim in the docs is left untrue.

## Phase-specific docs
`CHANGELOG.md` `[Unreleased]`; `docs/PHX_USER_GUIDE.md`; `README.md`; `docs/PHX_ARCHITECTURE.md`; `docs/PHX_THREAT_MODEL.md`; spec amendment R27. Nothing under `plugins/` should change. Add an ADR only if you depart from ADR-0035.

Then the standard close-out checklist.
