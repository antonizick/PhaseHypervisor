# PHX Phase 12b: Visual project timeline (generator, skill templates, PHX's own timeline)

**Model:** Opus 5.5 (`/model claude-opus-5-5`) · **Depends on:** 12a · **Branch:** `phase-12b-visual-timeline` · **Worktree:** `../PhaseHypervisor-phase-12b` · **Gate:** review

Since 2026-10-20 every phased project records *when* things happen: each Phase Log entry starts with a machine-readable **Timeline** bullet (claim time, finish, merge, blocked intervals), and planning entries carry start and finish times. Nobody can *see* that history, though. The only picture is the hand-drawn Mermaid gantt in PHX's own final report (`docs/PHX_FINAL-REPORT.md` §5), and on one 21-hour axis its 1–25-minute phases shrink to slivers next to the overnight gaps. This phase adds a **generator** to the `phased-project` skill: a small script that reads the plan and git and draws the timeline, so no person or agent draws it by hand. The skill templates then keep it current through the build, and PHX's own plan and final report become the first users. Phase 12c then retrofits Nick's four other projects using the recipe written here.

## Read first
`CLAUDE.md` (rule 7: the skill lives in `plugins/phased-project/`, and everything there is public), `prompts/PHX_shared-instructions.md`, **ADR-0025** (this phase's decisions), ADR-0011, ADR-0012, ADR-0013, ADR-0022, ADR-0024, `docs/PHX_AUTO_MODE_CONTRACT.md` (§2 Timeline and blocked-interval rules), `docs/PHX_FINAL-REPORT.md` §5, `docs/PHX_GETTING_STARTED.md`, the skill `plugins/phased-project/skills/phased-project/SKILL.md` and every file in its `templates/`, the Phase Log entries for 12 and 12a, and the planning entry for 12b/12c. Outside the repo: the playbook `/home/nick/Documents/04 Resources/Claude Code Phased Project Method.md`, and **read-only** the plans of MeetingMaster3, chessloopDeploy, OCC_OmarchyControlCenter and YTPL2 under `/home/nick/Work/` (test fixtures only; changing them is Phase 12c). Load the `dataviz` skill before designing the SVG.

## Nick's request (verbatim intent, 2026-10-31 10:00 CDT)
> Because our project documentation is now logging date and time stamps, moving forward I would like the implementation and final report documentation to have a timeline-visualization of when the planning and when each phase starts and stops overlaid in an easy to read, easy to understand visual timeline. The visual timeline should be updated and maintained during the /phased-project build and deployment process. And flexible on the exact technology we use to build the timeline visualization, but I want something that provides a world-class product that operates as simply and reliably as possible.

Nick then chose (2026-10-31 10:00 CDT) **both renderers**: a custom SVG as the main image, plus a Mermaid gantt in the same generated block and in the vault note. He also chose **both rollout scopes**: skill templates, PHX itself and a migration recipe (this phase), plus a retrofit of MM3, CL, OCC and YTPL2 (Phase 12c).

## Decisions already made
- **ADR-0025:** the timeline is **generated, never hand-drawn**. One stdlib-only Python script, shipped in the skill and copied into each repo. Its inputs are the plan's phase table, the Phase Log Timeline bullets and git history. Its outputs are an SVG file and a marked block (image link, Mermaid gantt, summary table) in the plan and final report, plus Mermaid and table in the vault note. The rollout is split into 12b (build) and 12c (retrofit).
- ADR-0011: manual `/phase` works without `phx`. So the generator must not need `phx` installed, and `phx` itself is unchanged by this phase.
- ADR-0012: the hands-off contract stays version 1. The Timeline bullet grammar the contract defines does not change. The generator reads it and never asks agents to write it differently.
- ADR-0004: merge and push `main` freely. **The repo is public, so every push publishes.** No tag, no GitHub Release.

## Goal
Every phased project, new or adopted, shows an accurate, good-looking picture of its planning and build history in its plan and its final report. The generator updates it at every close-out, block, resume and `/phase-add`. It needs no network, no JavaScript and no tool beyond `python3` and `git`, and it gives the same output every time it runs on the same repo state.

## What exists (verified 2026-10-31 10:00 CDT; re-check before relying on it)
- **Timeline data.** PHX's plan has 15 Timeline bullets in the exact grammar (`PHX_IMPLEMENTATION_PLAN.md`, Phase Log). Older projects are messier:
  - MM3 and CL have entries written before 2026-10-20 that say `started not recorded (written before this rule)` or `merged n/a (committed directly to main)`, and headings with bare dates;
  - OCC and YTPL2 have planning entries (`started … · finished …` only) and claim-commit hashes;
  - YTPL2 has `merged … (merge commit <hash>)`.
  The generator must accept all of these and fall back to git (`chore(plan): start phase NN`, `chore(plan): phase NN blocked`, `chore(plan): resume phase NN`, merge commits) where a bullet is missing or partial. A time it had to infer is shown as **approximate**, never presented as exact.
- **Parser constraints (`src/phx/plan.py`).** `parse_phase_table` takes the **first** table whose header has both `phase` and `status`. So the generated block must sit **after** the phase table, and its table must not have a `Status` column. `src/phx/verify.py:phase_log_entries` starts at the first `## Phase Log` heading, so the block must never use that heading. `phx plan` output must be identical before and after on every repo (task 9).
- **Hand-drawn timeline today:** `docs/PHX_FINAL-REPORT.md` §5 (Mermaid gantt plus table, with the idle gaps described in prose). `prompts/PHX_phase-12-release.md` task 3 asked for "ASCII or Mermaid gantt".
- **Skill text that already promises a timeline:** `SKILL.md` "Phase design rules" (the final report "will include a visual timeline…") and "Timeline bullet" section. There is no final-report template.
- **Rendering tools on the reference machine:** `rsvg-convert`, `chromium`, `magick` (for PNG previews and checks only; the generator itself uses none of them). `mmdc` (Mermaid CLI) is not installed.
- **Where Mermaid renders:** GitHub renders fenced `mermaid` blocks and SVG images in Markdown. Obsidian renders Mermaid natively but cannot embed a file outside the vault, which is why the vault note gets Mermaid and the table, not the SVG.

## Tasks
1. **Generator script.** Write `plugins/phased-project/skills/phased-project/scripts/phase_timeline.py`: Python ≥ 3.9, standard library only, one file, MIT header, `TIMELINE_FORMAT = 1` constant. CLI: `python3 scripts/phase_timeline.py [--repo DIR] [--write | --check | --print] [--vault-note PATH] [--gap-minutes N]`.
   - **Inputs:** the plan file (located like `src/phx/plan.py:locate_plan`: `<PREFIX>_IMPLEMENTATION_PLAN.md`, else `IMPLEMENTATION_PLAN.md`), read from the **working tree**; its phase table (ID, name, status, depends on); its Phase Log; and `git log` on `HEAD`.
   - **Events:** planning sessions (Phase 00 and every `Planning: phase <ID> inserted`, plus `phx preflight` commits if present), each phase's start, finish, merge and blocked intervals, an open bar for `🔄` and an open blocked interval for `⛔`.
   - **Source order per value:** the Timeline bullet, then git, then the heading timestamp, then "unknown" (left off the chart, listed under "not shown").
   - **Times:** parse `YYYY-MM-DD HH:MM TZ` with the zone abbreviation. Map abbreviations to offsets using the commit times git reports (`%cI`), so a CDT/CST change mid-project stays correct. Never call `datetime.now()`: open bars end at the commit time of `HEAD` (the "as of" time). This makes `--check` deterministic and CI-safe.
   - **Modes:**
     - `--write` updates the outputs in place;
     - `--check` exits 1 with a one-line reason if any output is stale, and changes nothing;
     - `--print` writes the block to stdout.
     Only text between the markers is ever rewritten, and the file is never otherwise touched. Write the temporary file and rename it over the output (atomic). Exit code 2 with a clear message when the markers or the plan are missing.
2. **SVG design (the main visual; this is where "world-class" is earned).** Output `docs/<PREFIX>_TIMELINE.svg`, a self-contained static file: no scripts, no external fonts, no `<foreignObject>`. Design defaults (change any of them only with a reason in the ADR):
   - **Layout:** a title (`<PREFIX> timeline`), a subtitle with the date span, time zone and "as of <TS>", and a legend. One row per phase in phase-ID order, with ID and short name on the left. A **Planning** lane at the top shows Phase 00 and each `/phase-add` or preflight session. Each bar is labelled with its duration.
   - **Axis:** idle gaps longer than `--gap-minutes` (default 60) are **collapsed into labelled axis breaks** ("⋯ 4 h 53 m idle ⋯"). Day changes are marked on the axis. Tick spacing adapts to the visible span.
   - **Encoding:**
     - complete phases are solid;
     - `🔄` phases are open-ended up to the "as of" line;
     - blocked intervals are **hatched**, a pattern and not only a colour;
     - approximate times have a dashed outline;
     - a merge that came later than the finish shows as a thin tail;
     - parallel phases are visible because their rows overlap in time.
   - **Colour:** palette per the `dataviz` skill, colour-blind safe, WCAG AA text contrast. An opaque card background so the image reads on both light and dark pages. A `prefers-color-scheme: dark` style block inside the SVG.
   - **Accessibility:** `<title>` and `<desc>` (with a text summary of the timeline), `role="img"`.
   - **Determinism:** fixed width (≈1200 px) and height from the row count. Stable element order, ids derived from phase IDs, numbers rounded, so regenerating an unchanged repo is byte-identical and real changes give small diffs.
3. **Markdown block.** Between `<!-- phase-timeline:start (generated by scripts/phase_timeline.py; do not edit) -->` and `<!-- phase-timeline:end -->`:
   - the SVG image link;
   - one Mermaid `gantt` per *working session*. A new gantt starts after an idle gap longer than the gap setting, since Mermaid cannot break an axis. Each gantt has a planning section and `crit` bars for blocked intervals. Task names are escaped so `:`, `#` and `;` never break the syntax;
   - a summary table with columns `Phase | Name | Started | Finished | Merged | Active | Blocked | Claim`, with no `Status` column (see "What exists");
   - totals: elapsed time, active phase time, blocked time and idle time;
   - a "not shown" line for any phase with no usable times.

   In the plan, the block goes under a new `## Timeline` heading placed **after** the phase table and before "Model rationale". In the final report it goes in the timeline section. With `--vault-note PATH`, the same block minus the image goes into the vault note under `## Timeline`.
4. **Ship it with the skill.** In the skill, add the script to the Outputs table: `scripts/phase_timeline.py` is copied into every new repo, unprefixed because it is a tool (add it to the "Never prefixed" list). Add the `## Timeline` heading and empty markers to `templates/IMPLEMENTATION_PLAN.md`. Bootstrap runs `--write` before the first commit, so Phase 00 shows from day one. Add a new section **"Visual timeline"**: what it shows, the markers, the commands, when it runs (task 5) and the conflict rule. Update "Phase design rules" so the final report embeds the generated block and does not draw one. Optionally add `templates/FINAL-REPORT.md` as a skeleton holding the markers, if it keeps the release prompts shorter.
5. **Keep it current (the maintenance rule).** Regenerate **only on `main`, never on a phase branch**. The generated block then never conflicts between parallel branches. If a conflict happens anyway, keep either side and re-run `--write`; never merge it by hand. Wire the rule into:
   - `templates/_shared-instructions.md` close-out checklist: after the merge, on `main`, `python3 scripts/phase_timeline.py --write{{#VAULT}} --vault-note "{{VAULT_NOTE_PATH}}"{{/VAULT}}`, then commit the plan, SVG and final report together with the close-out (or as `docs(plan): refresh timeline`);
   - §1b block-with-question and the resume steps: the `⛔` and resume commits regenerate too;
   - `templates/phase-add-command.md` step 5: regenerate before the planning commit;
   - `templates/phase-command.md`: `/phase status` runs `--check` and reports "timeline stale" as drift. It never writes.
   - **Leave the claim commit status-only**, since the claim protocol and `phx` rely on that. The new bar appears at the next block, resume or close-out.

   Confirm against `docs/PHX_AUTO_MODE_CONTRACT.md` that none of this changes contract-1 behaviour. If any line would, stop and ask (hands-off: block-with-question), per ADR-0012.
6. **Migration recipe.** Add a skill section **"Adding the visual timeline to an existing repo"**, written for Phase 12c and for strangers. Preconditions are the same as the other migrations: idle repo, clean `main`, never commit another agent's files. Steps: copy the script; add the `## Timeline` heading and markers to the plan (after the phase table) and to the final report if one exists; add the maintenance lines to that repo's shared instructions, `phase.md` and `phase-add.md`, copying the template wording and keeping the repo's own text; run `--write`; check `phx plan` is unchanged; commit as `chore(docs): add visual timeline` with an ADR. Mention legacy entries ("started not recorded", bare dates): the generator shows them as approximate, and nobody should rewrite history to make the chart prettier.
7. **Apply it to PhaseHypervisor itself.** Copy the script to `scripts/phase_timeline.py` in this repo. Add the block to `PHX_IMPLEMENTATION_PLAN.md` and to the PHX vault note (`--vault-note "/home/nick/Documents/02 Projects/PHX Implementation Plan.md"`). In `docs/PHX_FINAL-REPORT.md` §5, replace the hand-drawn gantt and table with the generated block and keep the narrative sentences that are still true. Add the maintenance lines to `prompts/PHX_shared-instructions.md`, `.claude/commands/phase.md` and `.claude/commands/phase-add.md`. The repo copy and the skill copy must stay byte-identical (a test checks this).
8. **Preview checkpoint for Nick (his standing preference: review visuals before they go live).** Merging this phase changes Nick's live skill, because `~/.claude/skills/phased-project` is a symlink into the main checkout. So before task 4's template changes land on `main`:
   - render the SVG for PHX and for read-only copies of MM3, CL, OCC and YTPL2, in light and dark (`rsvg-convert` or headless `chromium` → PNG, in the scratchpad);
   - look at every PNG yourself (Read the image) and fix what is ugly, clipped or misleading;
   - then show Nick the PNG paths and the PHX Mermaid block, and ask for approval or changes. In hands-off mode, use block-with-question, with the preview paths in the question.

   Iterate until he approves. Record what changed in the ADR.
9. **Regression and safety.** Run `phx plan` on this repo before and after (byte-identical output), and in read-only mode on a scratch copy of each other repo with the block added. Run the package tests from 12a (deny-list included: the script and templates are public, so no personal paths, and the vault path only appears through `{{VAULT_NOTE_PATH}}`). Re-render the templates with Nick's settings and with none: the only differences from the pre-12b render are the new timeline lines, and the contract-critical lines are unchanged.

## Out of scope
- Changing MM3, CL, OCC or YTPL2 (Phase 12c).
- Changing `phx` itself. A `phx timeline` subcommand or a verifier "timeline fresh" check are follow-ups to record, not build.
- An interactive HTML or hosted timeline, or any JavaScript or CDN dependency.
- Rewriting historical Phase Log entries to fill gaps.
- A version tag or GitHub Release (ask at close-out only if Nick raises it; ADR-0023's `v0.2.0` question is still open).

## Tests
- New `tests/test_phase_timeline.py`. The script is imported by path, and fake repos come from `tests/scenarios.py`-style git builders. Cases:
  - parsing every Timeline grammar seen in the five real plans (fixture excerpts copied into `tests/fixtures/timeline/`, personal text removed);
  - each git fallback;
  - approximate marking;
  - `🔄` open bars ending at `HEAD`'s time;
  - an open and a closed `⛔` interval;
  - two phases overlapping (parallel);
  - a CDT→CST change;
  - gap collapsing at the threshold;
  - Mermaid escaping;
  - marker handling: missing markers give exit 2, text outside the markers is byte-identical;
  - atomic write;
  - `--check` exit codes;
  - determinism: two `--write` runs give byte-identical output;
  - the block never placed before the phase table, and `parse_phase_table` and `phase_log_entries` unaffected;
  - golden-file SVG and Markdown for one fixture repo;
  - the SVG parses with `xml.etree` and has `<title>`, `<desc>` and no `<script>`.
- Repo copy ≡ skill copy of the script (byte compare).
- 12a package tests extended: the new template lines render with and without settings, and the deny-list covers `scripts/`.
- Full suite, `ruff check`, `ruff format --check`, `mypy src` (and ruff on the script), pre-commit all clean, CI green on `main`.

## Acceptance criteria
- `python3 scripts/phase_timeline.py --check` passes on `main` after the merge. The PHX plan, final report and vault note show the generated timeline, and the final report has no hand-drawn chart left.
- In the PHX SVG, phases 01–05 are readable, which they are not on the current single axis: the two long idle gaps are collapsed and labelled. Phase 00 and the 12a/12b/12c planning sessions are in the Planning lane. All durations match the summary table.
- Nick has seen and approved the PNG previews (task 8), and the approval is recorded with its timestamp in the Phase Log.
- `phx plan` output is unchanged for this repo. A new project bootstrapped from the templates in a scratch directory has the script, the markers and a Phase 00 bar after its first commit.
- The skill has the "Visual timeline" and "Adding the visual timeline to an existing repo" sections, mirrored in `docs/PHX_GETTING_STARTED.md` and Nick's playbook.

## Phase-specific docs
- **In the skill:** `SKILL.md` (Outputs, Never-prefixed, Visual timeline, migration recipe, Phase design rules).
- **Templates:** `IMPLEMENTATION_PLAN.md`, `_shared-instructions.md`, `phase-command.md`, `phase-add-command.md`, and `FINAL-REPORT.md` if you add it.
- **Repo docs:** `docs/PHX_GETTING_STARTED.md` (the timeline, with a sample image or a pointer to PHX's), README (link to the timeline), `docs/PHX_ARCHITECTURE.md` (the generator as a skill component), `docs/PHX_FINAL-REPORT.md` §5, CHANGELOG `[Unreleased]`, `CONTRIBUTING.md` (how to change the generator and refresh the golden files).
- **Decisions and spec:** an ADR for the design defaults (the gap threshold, regenerating only on `main`, the claim commit left alone, Mermaid split per session, the preview outcome), and spec amendment **R24** (projects carry a generated visual timeline).
- **Outside the repo:** the playbook note, and the vault project note (block and log line). No OS change is expected; if one happens, update OSMods.

Update `prompts/PHX_phase-12c-timeline-rollout.md` if anything it assumes changes. Then the standard close-out checklist.
