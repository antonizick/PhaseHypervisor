# PHX Phase 12e: README that sells PHX, with real examples

**Model:** Sonnet 5.5 (`/model claude-sonnet-5-5`) · **Depends on:** 12d · **Branch:** `phase-12e-readme-benefits` · **Worktree:** `../PhaseHypervisor-phase-12e` · **Gate:** review

The public README explains how PHX works but never says why anyone would want it. Nick has now run the method on several projects and knows what it pays back: documentation that stays accurate, quick-reference charts of every phase's stage, and above all a timeline that shows planning and implementation truthfully, idle gaps and blocked spans included. This phase rewrites the README's opening around those benefits, shows real output from a real project (P11) instead of describing it, and pushes the result to the public repo.

## Read first
`CLAUDE.md`, `prompts/PHX_shared-instructions.md`, **ADR-0031**, ADR-0011 (PHX is optional), ADR-0023 (handle only, no full name or email in public metadata), ADR-0025 and ADR-0027 (what the timeline is and how it is generated), the current `README.md`, `docs/PHX_GETTING_STARTED.md` §1 and §4, and the planning entry for 12e in the Phase Log.

## Nick's request (verbatim intent, 2026-11-05 02:24 CST)
> Can you punch up the [README] file associated with this project and update push it to GitHub. What's missing from the [README] file right now is extolling the benefits of using PHX. I've been using it for several projects now. What it provides is Immaculate Documentation, Quick reference charts, particularly stages of different phases of implementation, And probably my favorite feature, the visualization of the timeline to include planning and phase implementation steps even when there are [gaps] for idle time or block periods. The [README] file should include examples of those images. One good example is the implementation plan documentation for Project P11

## Decisions already made (ADR-0031)
- **The P11 timeline is used as is:** an unedited snapshot, as the lead example. Its phase names (including the face-swap phases) stay. Do not relabel, crop or regenerate it with changes. P11 is public, by Nick's own decision (P11 owner question 21).
- **Voice:** a neutral benefits section, plus two or three lines in the maintainer's own first-person voice, signed with the handle `antonizick` only. No full name, no email.
- **No tag and no GitHub Release** (ADR-0026 still applies). Repo visibility does not change.

## Goal
A stranger opening `github.com/antonizick/PhaseHypervisor` learns within the first screen what PHX gives them and sees the proof: a real timeline, a real status chart and links to a complete real project. The technical content stays reachable. Every claim on the page is true and checkable.

## What exists (verified 2026-11-05 02:26 CST; re-check before relying on it)
- `README.md` (66 lines): a dense status blockquote, a one-paragraph description, then `Use PHX yourself`, `How this project is built`, a long prose `Usage`, `Development setup`, `Requirements`, `Security`, and `Contributing`. It has no benefits section and no image.
- `docs/PHX_TIMELINE.svg` is linked but not embedded. PHX's own chart has one blocked span of 25 m.
- `/home/nick/Work/project1111` (`antonizick/project1111`, PUBLIC, MIT): `docs/P11_TIMELINE.svg` (1200×948, 26 KB, one `prefers-color-scheme` rule, no paths or names of people). It shows a planning lane with brainstorming, plan draft, preflight diamonds and inserted phases, two collapsed idle gaps (1 h 16 m, 2 h 56 m) and Phase 17's hatched block (58 m + 8 h 37 m blocked). Its plan's `## Timeline` block has three Mermaid gantts and a summary table. Totals: elapsed 2 d 17 h, active 1 d 20 h, blocked 8 h 37 m, idle 4 h 12 m. Also 26 phases, 48 ADRs, final report, threat model, user guide. **P11 phase 17f was `🔄 In progress` at planning time and its local `main` was ahead of `origin/main`**, so these figures will move.
- Phased plans exist for MM3, CL, OCC, YTPL2, P11 and PHX, but only `antonizick/project1111`, `antonizick/MeetingMaster3` and this repo resolved as public GitHub repos. Do not link or name the others.
- The timeline and the documentation set come from the `phased-project` skill, not from `phx`: they work with manual `/phase` too (ADR-0011). `phx` adds the hands-off run.
- `tests/test_plugin_package.py:DENY` covers `plugins/`, `examples/` and `docs/PHX_GETTING_STARTED.md`, **not** `README.md`. If you edit the guide, it must still pass. No test reads the real README.
- `docs/PHX_USER_GUIDE.md` covers every command in the README's `Usage` section, so that prose can shrink without losing content. `phx watch` is not in `docs/PHX_GETTING_STARTED.md`.
- No `docs/images/` directory exists. `docs/PHX_NextSteps_Ideas.md` is an untracked note of Nick's: leave it alone and never stage it.

## Tasks
1. **Take the snapshot.** Read-only on P11: `git -C /home/nick/Work/project1111 fetch -q`, then `git -C /home/nick/Work/project1111 show origin/main:docs/P11_TIMELINE.svg > docs/images/PHX_example-P11-timeline.svg`. Use `origin/main` because that is what readers can follow the link to. Keep the bytes unchanged. Change nothing in P11. Render it to PNG in the scratchpad (`rsvg-convert`, light and dark) and look at it. If 17f is open at that moment the chart shows it as running; that is true, so keep it. If the SVG contains a path or person's name, stop and ask.
2. **Rewrite the opening of `README.md`** in this order: title, a one-line promise, a short plain status line (version, public, link to the final report), then a new `## Why use it` section, then `Use PHX yourself`. Move the long status blockquote's detail to the final report link. The rest of the file follows after them.
3. **`## Why use it`** covers the three benefits Nick named, in his order, each short and concrete:
   - **Documentation that stays accurate:** every project gets a plan, spec with amendments, ADR log, self-contained phase prompts, a timestamped Phase Log, and at the end a final report. It is a required part of closing a phase, so it can't quietly go stale. Link P11's real ones as proof.
   - **Quick-reference charts:** a native Markdown excerpt of a real P11 status table, not an image, so it stays searchable and needs no binary. Take 5-6 real rows, keep only Phase, Name, Model, Depends on, Status and Gate, and show at least `✅` and `🔄` if both exist. Add a one-line legend of the four stages (⬜ 🔄 ⛔ ✅). Say that it is an excerpt, and link the full table.
   - **The timeline (give this the most space, it is Nick's favourite):** embed `docs/images/PHX_example-P11-timeline.svg` with useful alt text, and call out what to look at: the planning lane, zigzag collapsed idle gaps, the hatched blocked span and bars per phase. Caption it with what it is, the as-of time taken from the SVG, and a link to [P11's plan](https://github.com/antonizick/project1111/blob/main/P11_IMPLEMENTATION_PLAN.md#timeline). Show 2-3 real rows of the summary table or its Totals line. Embed PHX's own `docs/PHX_TIMELINE.svg` as a smaller second example, in a `<details>` block or via a link.
   Then add the maintainer's note (two or three first-person lines signed `antonizick`) drawn from Nick's own words. Close with a line on what `phx` itself adds (hands-off runs, usage-limit waits, independent verification) and that all of this works without it.
4. **Tighten the rest without losing facts.** Replace the `Usage` prose with a compact command table (`command | what it does`) linking `docs/PHX_USER_GUIDE.md`; it must include `phx watch`. Keep `Development setup`, `Requirements`, `Security` and the document table, trimming phase-number noise that means nothing to a stranger. Keep the `Security` warning about bypassed permissions prominent: selling harder must not bury it.
5. **Check every claim.** Each number comes from the source at the time of writing, not from this prompt, and carries its as-of time or is a stable fact. Avoid absolute claims such as "never" or "immaculate" in the project's own voice, and avoid superlatives you can't back; Nick's own word may appear in his note. Check every relative link and image with `ls`, and every external link with `gh api` or `curl -I`.
6. **Render before merging.** Convert the README with `gh api markdown -f mode=gfm -f context=antonizick/PhaseHypervisor -f text="$(cat README.md)"` to HTML in the scratchpad, open it in Chromium at phone and desktop widths, and look at it, in light and dark. The image must stay readable when scaled to GitHub's column width (about 830 px).
7. **Publish.** Close out through the normal merge to `main` and push (ADR-0004, and Nick asked for this). Then open the real page on github.com and confirm that the SVG renders, not a broken image, and that the table and `<details>` block display correctly. Record that check in the Phase Log.

## Out of scope
- Any change to `project1111` or any other repo, to `phx` code, to the timeline generator or its output format.
- A version bump, tag or GitHub Release. Repo description or topics on GitHub.
- The cheat sheet and `phx -h` idea in `docs/PHX_NextSteps_Ideas.md` (use `/phase-add` for it).
- Rewriting the user guide, Getting Started guide or final report beyond correcting a fact.
- Adding screenshots of `phx status` or `phx watch` (a possible follow-up).

## Tests
- `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src` and pre-commit all stay clean. This is a docs phase; no code changes are expected.
- `python3 scripts/phase_timeline.py --check` still behaves; the snapshot must not confuse it.

## Acceptance criteria
- On github.com, the first screen of the repo page states what PHX gives you, and scrolling reaches the three benefits in Nick's order.
- The rendered page shows the P11 timeline, with the planning lane, collapsed gaps and hatched block visible, and it is byte-identical to `origin/main` of P11 at snapshot time (record the commit hash).
- The page shows a real status-table excerpt, labelled as an excerpt, with the stage legend, and a link to the full table.
- The maintainer's note is signed with the handle only; `grep -n 'Antonizick\|Antoncic\|nick@\|/home/nick' README.md` finds nothing outside the existing licence or GitHub-handle URLs.
- Every link and image resolves. The bypassed-permissions warning is still in the README. Every fact removed from `Usage` is confirmed present in `docs/PHX_USER_GUIDE.md`.
- `main` is pushed, with no tag and no release created; `gh repo view --json visibility` is unchanged.

## Phase-specific docs
`CHANGELOG.md` `[Unreleased]`; `docs/PHX_ARCHITECTURE.md` and the layout tree in `prompts/PHX_shared-instructions.md` §2 if `docs/images/` belongs there; the vault note; an ADR only if you depart from ADR-0031. Nothing under `plugins/` should change, so the playbook needs no mirror unless it does. Then the standard close-out checklist.
