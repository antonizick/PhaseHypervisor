# Shared Instructions for Every Phase

Read this file in full before starting any phase. Each phase prompt assumes it.

**Phase IDs.** `NN` in this file is the phase ID: two digits, optionally with a lower-case letter suffix for a phase inserted after another one with `/phase-add` (`09a`, `11a`, `11b`…). An inserted phase is a normal phase with its own claim, branch and worktree; `11a` sorts after `11` and before `12`.

## 1. Orientation and claim (every phase, before writing code)
1. Read `CLAUDE.md`, `OCC_IMPLEMENTATION_PLAN.md` (including the Phase Log and Owner questions) and the spec sections named in your phase prompt. Always read the Amendments (`docs/OCC_SPECIFICATION.md` §13) and the appendices.
2. Confirm that every phase listed under "Depends on" is `✅ Complete`. If one is not, stop and tell Nick.
3. Read the Phase Log entries of the dependency phases; they may record deviations that change what you build.
4. If an owner question this phase needs is still open, ask Nick before doing the affected work. (Hands-off mode: block-with-question, §1b.)
5. **Claim the phase on `main`** by following §1a. This is the first file change of every phase session. Do not start the Tasks until the claim is verified.
6. If the prompt is ambiguous or contradicts the spec, prefer the spec's Amendments. If it is still unclear, ask Nick before guessing on anything user-visible or hard to reverse. The vault is the source of truth for how services are launched; if a detail is missing or ambiguous there, **stop and ask** (spec §12). (Hands-off mode: block-with-question, §1b.)

## 1a. Claiming a phase (mandatory; other agents may be running in parallel)
Nick and other agents read the Status column from `main`. A status change made only on a phase branch, or left uncommitted in a worktree, is invisible to them. So every phase is claimed with a commit on `main` **before** any other work.
1. In the main checkout (`/home/nick/Work/OCC_OmarchyControlCenter`), check that `git branch --show-current` prints `main` and that `git status --short OCC_IMPLEMENTATION_PLAN.md` prints nothing. If either check fails, stop and tell Nick. Never commit another agent's uncommitted changes.
2. Look for an existing claim: the phase's row on `main`, `git branch --list 'phase-NN-*'` and `git worktree list`. If the row is already `🔄 In progress`, or a branch or worktree exists, do not claim again; follow the resume rules in `/phase`.
3. Set the phase's Status cell to `🔄 In progress`, then commit **only that file** to `main`: `git commit -m "chore(plan): start phase NN" -- OCC_IMPLEMENTATION_PLAN.md`.
4. In the Obsidian project note (`/home/nick/Documents/02 Projects/OCC Implementation Plan.md`), set the phase's row to `🔄 In progress`, update its `updated:` field and add a timestamped log line: "Phase NN started (claim commit `<hash>`, branch `phase-NN-<slug>`, worktree `../OCC_OmarchyControlCenter-phase-NN`)".
5. Create the worktree and branch from that commit: `git worktree add ../OCC_OmarchyControlCenter-phase-NN -b phase-NN-<slug> main`, then run `mise install` (once Phase 02 exists) and `go mod download` inside it. Do all of the phase's work in the worktree, using absolute paths or `cd <worktree> && …` in every command, because the shell may reset to the main checkout between commands. Never switch the main checkout off `main`: other agents commit their claims there.
6. Verify: `git show main:OCC_IMPLEMENTATION_PLAN.md | grep '^| NN '` must show `🔄 In progress`.

If the phase ends `⛔ Blocked`, commit that status to `main` the same way (`chore(plan): phase NN blocked`) so that `main` doesn't show a stale `🔄`. A `✅ Complete` status reaches `main` through the merge.

## 1b. Hands-off mode: block-with-question (PhaseHypervisor contract 1)
Applies only in hands-off mode (`/phase NN --auto` or `PHX_AUTO=1`, set only by PhaseHypervisor); manual sessions ignore this section. Wherever a manual session would ask Nick (an open owner question this phase needs, an ambiguity you must not guess, the risk rule in `CLAUDE.md`, or a failure you cannot fix within scope), do this instead, then end the session:
1. In the worktree, commit all work on the phase branch: `wip(phase-NN): blocked, <short reason>`. Do not merge; keep the branch and worktree.
2. In the main checkout, in `OCC_IMPLEMENTATION_PLAN.md`:
   - add an Owner questions row `| <next #> | <question> | Open (asked <TS>, Phase NN, auto mode). Proposed default: <default> | Phase NN |` (or, for an existing open question, name this phase in its Status cell and keep it `Open`);
   - set the phase's Status to `⛔ Blocked`;
   - add a Phase Log entry `### <TS>: Phase NN: <title> (⛔ Blocked)` with bullets: `- **Timeline:** started <claim TS> (claim commit <hash>) · blocked <TS> to (open)`, then `- **Model:** …`, then `- **Question:** #<id>: <question>`, then what is done, what remains and where to resume.
3. Commit only that file to `main`: `git commit -m "chore(plan): phase NN blocked" -- OCC_IMPLEMENTATION_PLAN.md`, and push `main` if a remote exists.
4. In the Obsidian note: row `⛔ Blocked`, `updated:` field, and a timestamped log line naming the question.
5. Final message: what was done, the question and its proposed default, then the `PHX-RESULT` line with `"status":"blocked"` and the question IDs (see `/phase`).

A question is **open** while its Status cell starts with `Open`; `Answered …`, `Decided …` and `Deferred …` are not open.

**Resuming** a `⛔ Blocked` phase in hands-off mode: if a question needed by it is still open, refuse without changing anything. Otherwise set the row to `🔄 In progress`, change `blocked <TS> to (open)` to `blocked <TS> to <TS now>` in its Timeline, commit only the plan file to `main` (`chore(plan): resume phase NN`), update the Obsidian note, then run `git merge main` in the worktree, read the answer and continue as a normal resume.

## 2. Target repository layout (evolves; keep `docs/OCC_ARCHITECTURE.md` in sync)
```
OCC_OmarchyControlCenter/
├── CLAUDE.md  README.md  LICENSE (MIT)  NOTICE  SECURITY.md  CONTRIBUTING.md
├── CODE_OF_CONDUCT.md  CHANGELOG.md  THIRD_PARTY_NOTICES.md
├── OCC_IMPLEMENTATION_PLAN.md            (prefixed)
├── .mise.toml  .editorconfig  .gitignore  .dockerignore  .golangci.yml
├── Makefile                               build | test | lint | check | install | uninstall
├── go.mod  go.sum
├── cmd/occ/                               main.go: launch (default) | serve | quit | status | check | render-voice
├── internal/
│   ├── config/      services.toml schema, load, validate, ~ expansion (pure)          [03]
│   ├── status/      state + badge classification, distress rules (pure)              [03]
│   ├── metrics/     CPU %-from-delta, /proc parsing, tree sums                        [03, 04]
│   ├── runner/      Command runner interface + fake for tests                         [03]
│   ├── systemd/     systemctl --user show/start/stop/restart; systemd-run transient    [04]
│   ├── procscan/    /proc scan, cmdline match, port owner, external detection          [04]
│   ├── probe/       HTTP health and JSON busy probes, TCP port checks                   [04]
│   ├── logs/        journal + file tail, error-pattern scan                              [04, 09]
│   ├── docker/      read-only container inspect + cgroup metrics (metrics_source)        [04]
│   ├── hypr/        hyprctl: list windows, close by title (Lua dispatch)                  [04]
│   ├── service/     Manager: combines adapters per service kind; demo/fake manager       [04, 05]
│   ├── server/      HTTP API, security middleware (Host, token, CSP), quit               [06]
│   ├── lifecycle/   flock single instance, state file, port pick, launcher flow          [06, 07]
│   ├── theme/       colors.toml → CSS custom properties, fallback palette                [06]
│   └── voice/       Piper render, paplay playback                                         [07]
├── web/                                   index.html, occ.css, occ.js (go:embed)       [08]
├── config/services.example.toml           the five real services, ~-relative paths     [05]
├── scripts/                               install.sh, uninstall.sh                        [07]
├── docs/
│   ├── OCC_SPECIFICATION.md               (prefixed) canonical spec; §13 Amendments win
│   ├── OCC_DECISIONS.md                   (prefixed) ADR log
│   ├── OCC_ARCHITECTURE.md                (prefixed) created in 02, kept current
│   ├── OCC_THREAT_MODEL.md                (prefixed) Phase 11
│   ├── OCC_PERFORMANCE.md                 (prefixed) Phase 11
│   ├── OCC_FINAL-REPORT.md                (prefixed) Phase 12
│   └── user-guide/                        install, using, adding-a-service, troubleshooting
├── prompts/
│   ├── OCC_shared-instructions.md         (prefixed) this file
│   ├── OCC_phase-NN-<slug>.md             (prefixed) one per phase
│   └── OCC_change-request-template.md     (prefixed) intake form for /phase-add
├── .github/                               workflows/ci.yml, ISSUE_TEMPLATE/, PULL_REQUEST_TEMPLATE.md, dependabot.yml
└── .claude/commands/                      phase.md, phase-add.md
```
Live, never in the repo: `~/.config/occ/services.toml`, `~/.local/share/occ/voice/`, `~/.local/state/occ/`, `$XDG_RUNTIME_DIR/occ/`, the installed binary `~/.local/bin/occ`.

## 3. Conventions
- **Prefix.** Project documents carry the project prefix `OCC_` (see `CLAUDE.md`). New project-specific documents follow the same rule; convention-bound files (`README.md`, `LICENSE`, `CHANGELOG.md`, `CLAUDE.md`…) keep their names.
- **Timestamps, not dates.** Every place that records when (Phase Log, ADRs, amendments, owner questions, vault log, "Last updated", changelog release headings) uses `YYYY-MM-DD HH:MM TZ`. Run `date '+%Y-%m-%d %H:%M %Z'` when you write each one; do not guess or copy an earlier timestamp.
- **Go style.** `gofmt`/`goimports`, `go vet`, `golangci-lint` clean. Standard library first; any new module needs a licence check (MIT/BSD/Apache-2.0 only) and a THIRD_PARTY_NOTICES entry. Errors wrapped with `%w`, no panics outside `main`. `context.Context` with timeouts on every external command and HTTP probe (default 2 s; never let one slow service stall the dashboard).
- **Pure core, thin I/O.** Logic that decides (config validation, status classification, CPU maths, port choice, parsing `systemctl show`, `/proc` and log lines) is pure and table-tested. I/O goes through small interfaces (`runner.Runner`, filesystem roots, HTTP clients) with fakes, so most tests never touch the real machine.
- **Real-machine tests** are opt-in with the build tag `integration` (`go test -tags integration ./...`) and must never stop or start a service Nick is using without saying so first. They use throwaway transient units named `occ-test-*` and clean them up.
- **Commands.** Always argv arrays via `exec.CommandContext`, never `sh -c` with interpolated data. Only `systemctl --user` / `systemd-run --user`. Never `enable`, `disable`, `mask`, `daemon-reload`, `sudo`.
- **Audible actions.** Anything that plays sound (voice cues, the launcher) is audible: warn Nick before running it, and keep automated tests silent (inject a fake player).
- **Hyprland.** `hyprctl dispatch` uses the Lua form (`hl.dsp.focus(…)`, `hl.dsp.window.close(…)`); the classic syntax fails on Hyprland 0.56.
- **Host changes** (binary in `~/.local/bin`, Hyprland bind, mise Go, voice files) are documented in `/home/nick/Documents/04 Resources/OSMods/` (read `OSMODs README.md` first; update its at-a-glance table, section, "Where things live" and "Last updated"). Never edit `/usr/share/omarchy/`.
- **Commits.** Conventional Commits (`feat(server): …`, `test(status): …`, `docs: …`), committed at checkpoints on the phase branch.

## 4. Phase close-out checklist (all items required)
- [ ] All acceptance criteria in the phase prompt are met, with a short verification note for each.
- [ ] Tests, lint and type checks pass: `make check` (= `gofmt -l` empty, `go vet ./...`, `golangci-lint run`, `go test -race ./...`, `govulncheck ./...`); plus `go test -tags integration ./...` where the phase touches the real machine. Before Phase 02 exists: the docs-only checks in the phase prompt.
- [ ] `OCC_IMPLEMENTATION_PLAN.md`: Status set (`✅ Complete` or `⛔ Blocked`, icon plus word; a `⛔ Blocked` status is also committed to `main` per §1a), Phase Log entry added (timestamp, summary, deviations, follow-ups, test counts).
- [ ] **Timeline bullet written** as the first bullet of the Phase Log entry: *started* = the claim commit's time (`git log -1 --format=%cd --date=format-local:'%Y-%m-%d %H:%M %Z' <claim hash>`), *finished* = `date '+%Y-%m-%d %H:%M %Z'` taken as the last step before the final commit, *merged* = the merge time or `not merged yet`, plus `blocked <TS> to <TS>` for any `⛔` interval. Never reuse an earlier timestamp.
- [ ] `CHANGELOG.md` `[Unreleased]` updated (a release heading carries a timestamp, not just a date).
- [ ] README, SECURITY, `docs/OCC_ARCHITECTURE.md`, user guides, THIRD_PARTY_NOTICES, ignore files updated where affected.
- [ ] ADR added for any notable choice (timestamped in both the entry and its row in the index table at the top of `docs/OCC_DECISIONS.md`); `Proposed` ADRs this phase verified are flipped to `Accepted` (or superseded) with a timestamped note; spec amendment added if the spec changed.
- [ ] Later phase prompts corrected if your work changed their assumptions.
- [ ] Obsidian project note updated (status icons, `updated:` field and a timestamped log line).
- [ ] OSMods documentation updated if the host system was modified.
- [ ] Work committed on the phase branch. Once the phase is `✅ Complete` and every check passes, merge it into `main` without asking (fast-forward where possible), from the main checkout. Conflicts in `OCC_IMPLEMENTATION_PLAN.md` and the changelog are expected when phases ran in parallel: keep every row and entry from both sides, and use the branch's final status for this phase's row. Then push `main` if a remote exists (create a **private** GitHub repo if the plan calls for one; ADR-0004), `git worktree remove ../OCC_OmarchyControlCenter-phase-NN` and `git branch -d phase-NN-<slug>`. Do not merge a `⛔ Blocked` phase or one with failing checks. Making a repo public or publishing a release needs Nick's explicit confirmation (hands-off mode: block-with-question, §1b).
- [ ] Final message to Nick: what was built, how to try it, what's next, and any open questions. In hands-off mode, its last line is the `PHX-RESULT` line (see `/phase`).
