# PHX Phase 12g: `phx report` project summaries for the period

**Model:** Opus 5.5 (`/model claude-opus-5-5`) · **Depends on:** 12f · **Branch:** `phase-12g-project-summaries` · **Worktree:** `../PhaseHypervisor-phase-12g` · **Gate:** review

`phx report` says how much each project used, but not what the project is or what the work was. A reader sees a repo name and a dollar figure, with no reminder of what that project does or which phases the period covered. This phase adds a project summary section: each project's description, then the phases it worked on inside the report's window. It stays deterministic and calls no model, so descriptions are extracted from the repo, not written. It reads each repo's `main`, which is a deliberate widening of ADR-0032's "run.jsonl only" (ADR-0034).

## Read first
`CLAUDE.md` (risk rule, secrets, docs upkeep), `prompts/PHX_shared-instructions.md` (§1a claim, §4a timeline refresh), **ADR-0034** (this phase's decisions), ADR-0032 and ADR-0033 (the report's rules), ADR-0023 and ADR-0031 (what may be named in public files), ADR-0001 (no LLM), `docs/PHX_THREAT_MODEL.md` (repo text is untrusted), `src/phx/report/`, `src/phx/plan.py:load_plan` and `show_main`, `src/phx/vault.py:note_path` (confining a path taken from repo text), and `parse_phase_log` in `scripts/phase_timeline.py`.

## Nick's request (verbatim intent, 2026-11-05 05:21 CST)
> Can you also update the report functionality so that it will give a summary of the projects and what the projects descriptions are for the time. the report is run over?

## Decisions already made (ADR-0034)
- **Description source:** the opening paragraph of `README.md` on `main`, extracted, not rewritten. No new config key.
- **"Worked on":** phases active in the window from **both** sources: `phx` sessions in `run.jsonl` and the plan's Phase Log Timeline bullets. Manual phases are tagged as time only.
- **Resource figures do not change.** Tokens, cost and every total stay `phx`-launched only. Manual phases appear only in the new section, never in a sum, ratio, rule or chart.
- **No LLM** (ADR-0001, ADR-0032). **Read-only:** `git show` on `main`; no checkout, fetch or write, in the repo or under the state root.

## Goal
For each project in scope, the report shows:
1. **What it is:** a one-paragraph description, or an explicit "no description found" with the reason.
2. **What was worked on in the period:** each phase active in the window with its ID, its name from the plan, its source (`phx` or `manual`) and whether it finished in the window.

## What exists (verified 2026-11-05 05:21 CST; re-check before relying on it)
- `src/phx/report/render.py:repo_paths` already recovers each project's repo from its log's latest `run_start.repo`, for the vault links. It belongs in a shared place now.
- Three of the seven state directories on the reference machine have **no `run_start`** (their logs hold only `warning` and `dry_run`), so `repo_paths` finds nothing for them. The state directory is named after the repo's basename (`paths.py:state_dir`), so `$PHX_WORK_ROOT/<project>` (default `~/Work`, `paths.py:env_root`) is a fallback. `Supervisor` resolves that root at `supervisor.py:227`; there is no shared helper yet.
- `src/phx/plan.py:load_plan(repo)` parses the plan from `main`, giving `Phase.id`, `.name` and `.status`. Legacy names (`IMPLEMENTATION_PLAN.md`) are handled. It can raise `PlanError`, which the report must turn into a warning. It holds no Phase Log and `Phase` has no purpose field; the table's purpose column is not parsed.
- `show_main(repo, path)` (`plan.py:310`) is the read primitive and returns `None` on failure.
- `parse_phase_log` (`scripts/phase_timeline.py:331`) parses Timeline bullets, but `scripts/` is not in the installed wheel (`pyproject.toml` force-includes only `PHX_preflight.md`), so `src/phx` cannot import it. Timestamps carry zone abbreviations (CDT, CST).
- README openings vary. P11-style: heading, paragraph, status blockquote, image. MM3-style: a centred HTML `<p><img></p>` first, then a heading and a bold tagline. YTPL2-style: heading, then a `> **Status:…` blockquote, then the real paragraph. The extractor must handle all three.
- `report/model.py:Report` holds `projects`, `since`, `until` and `phases` (`PhaseUse`, `phx` work only). `model.build` is pure and does no I/O; keep it that way.
- The guide and `load.py`'s docstring say the report reads only `run.jsonl`; both become untrue.
- Projects with only manual work and no state directory are invisible: nothing lists them.

## Tasks
1. **Repo lookup.** One function, in `report/`, returning each project's repo: latest `run_start.repo`, else `$PHX_WORK_ROOT/<project>` if it is a git repo. Run-log paths are local data but still get checked: the path must exist, and a repo outside the work root gets a warning and is skipped. Replace `repo_paths`. Add `--no-repos` for logs-only output, so the old behaviour stays available.
2. **Description extractor.** A pure `describe(readme: str) -> str | None` in a new `report/projects.py`. Skip headings, HTML blocks, images, badges, blockquotes, code fences, tables and lists; take the first prose paragraph. Reduce Markdown to text (links to their label, emphasis removed, inline HTML dropped), fold whitespace, and cap at 300 characters on a word boundary with an ellipsis. Fall back to a bold tagline line if no paragraph qualifies, then to `None`.
3. **Untrusted text.** README and plan text are repo text (`docs/PHX_THREAT_MODEL.md`). Before any output, strip control characters and ANSI escapes, and in Markdown and the vault note neutralise `[[`, table pipes, leading `#`, and HTML. A hostile README must not move the terminal cursor, forge a report section or plant a vault link. Run it through `redact.py` as well. Nothing from a repo reaches a shell, and no rule or threshold depends on it.
4. **Manual phases.** A small stdlib Phase Log parser in `report/projects.py` over the plan text from `show_main`: per entry the phase ID, status and Timeline `started`/`finished`. Convert zone abbreviations through the local zone's names; if one is unknown, fall back to the date and say so. Skip planning entries. A phase overlaps the window if its span intersects it; a block interval does not split it. Do not reimplement the timeline generator, and add a test that the two agree on a shared fixture's phase IDs.
5. **Merge.** Phases from `phx` come from `Report.phases`; a Phase Log phase with no `phx` session in the window is `manual`. Names come from the plan, else the ID alone with no error. Mark `finished in period`. Deterministic order: by start time, then phase ID. A phase worked on by both is `phx` and not repeated.
6. **Model.** Keep `model.build` pure: gathering is a separate step in `cli.py` that takes the repos and window and returns `ProjectSummary(project, repo_found, description, description_note, phases)`, attached to the `Report`. Assert by test that the resource totals are unchanged with and without it. Filter the phase list with the same window as `build`, from `parse_bound`. A project with nothing in the window stays listed with "no recorded work in this period", so a window never hides that a project exists.
7. **Output.** A "Projects" section right after the header caveats, in terminal and Markdown via `sections()`; `--top` limits phases per project, with "and N more". JSON stays `schema: 1` and gains an additive `project_summaries` key; document it. Add a caveat line that manual phases come from the plan and carry time only. Charts do not change. The vault note links each project as it does now. Scan time stays low: one `git show` per file per project.
8. **Docs.** User guide: the new section, where each piece comes from, how to fix a poor description (edit the README's opening paragraph), `--no-repos`, a synthetic example, and the corrected "reads" sentence. Also the README command row and benefits sentence, `docs/PHX_ARCHITECTURE.md`, `CHANGELOG.md`, the threat model entry for the new read, and the `load.py` docstring. Add a spec amendment (R26) since the reporter's inputs change.
9. **Real-data check (read-only).** Run it on the reference machine for two windows, one wide and one holding manual phases only. Read every description as Nick would, tune the extractor against all real READMEs, and hand-check one project's phase list against its plan. Record only aggregate results in the Phase Log. Show Nick the output paths (scratchpad) in the final message, since this is a `review` phase.

## Out of scope
- Any LLM summary, or rewriting text. A description is what the README says.
- Estimating tokens or cost for manual phases, or adding them to any total, rule or chart. Mining Phase Log prose for accomplishments.
- A `description` config key (declined, ADR-0034). Discovering repos with no state directory; scanning the work root.
- Fixing the `phx status` and `run_end` overstatement (ADR-0033 follow-up); it needs its own phase.
- Changing how `phx run` works, or a version bump, tag or GitHub Release.

## Tests
- Fixtures: synthetic READMEs and plans under `tests/fixtures/report/` (covered by the deny-list), in all three opening shapes, plus a README with no prose and a hostile one (ANSI, `[[link]]`, `# forged`, pipes, HTML, a fake secret).
- `describe`: each shape, cap on a word boundary, tagline fallback, `None`. Sanitising: the hostile text is inert in all three outputs.
- Phase Log parser: CDT and CST across the change, an unknown zone, an open blocked phase, a phase with no `finished`, planning entries skipped, a legacy plan.
- Window: a phase straddling each edge, one wholly outside, the same quarter and year boundaries as 12f.
- Merge: `phx` only, manual only, both, a name missing from the plan.
- Lookup: a `run_start` path, the work-root fallback, a missing repo, a repo outside the root, no plan, no README, a broken plan (each a warning or note, and others still report). `tmp_path` git repos, no network.
- Guards: totals, rules and charts are byte-identical with and without `--no-repos`; repos and the state root are unchanged afterwards; `--json` still validates, with the new key documented.
- `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src` and pre-commit stay clean.

## Acceptance criteria
- `phx report` on the reference machine shows a sensible description for every project with a README, and a clear note for any without one.
- A window with hand-run phases only lists them, tagged as time only, with their names, while the resource tables stay empty of them.
- Narrowing `--since`/`--until` changes the phase lists correctly; a project with no work in the window says so.
- A hostile README fixture changes nothing but its own sanitised description.
- All resource figures match 12f's on the same logs, and `--no-repos` reproduces the 12f behaviour.
- No LLM or network call; nothing written to a repo or the state root. Real descriptions and private repo names appear nowhere in the repository.

## Phase-specific docs
`CHANGELOG.md` `[Unreleased]`; `docs/PHX_USER_GUIDE.md`; `README.md`; `docs/PHX_ARCHITECTURE.md`; `docs/PHX_THREAT_MODEL.md`; spec amendment R26; the layout tree in `prompts/PHX_shared-instructions.md` §2 if a module or fixture directory is added. Nothing under `plugins/` should change. Add an ADR only if you depart from ADR-0034.

Then the standard close-out checklist.
