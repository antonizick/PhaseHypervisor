# PHX User Guide

PHX runs the remaining phases of a phased-project plan for you, one at a time, each in a fresh headless Claude Code session on the model the plan names, and checks each phase itself. It is optional (ADR-0011): manual `/phase` keeps working exactly as before, and you can switch between the two at any phase boundary. `phx preflight` asks every question it can foresee up front, so the run that follows stops as rarely as possible.

**New here?** Start with [PHX_GETTING_STARTED.md](PHX_GETTING_STARTED.md): what the skill, `/phase`, `/phase-add`, `phx` and `/phx` are, how to install them, and a first project. This guide is the `phx` reference. Some examples below use the author's own repos and paths; substitute yours.

## Install
```bash
uv tool install git+https://github.com/antonizick/PhaseHypervisor   # puts `phx` in ~/.local/bin
phx --version
```
Upgrade with `uv tool upgrade phx`; undo with `uv tool uninstall phx`. Requirements: Linux, Python 3.12+, Claude Code signed in; `ai-provider`, `notify-send` and systemd are optional (see "Without `ai-provider`, notifications or systemd").

**From a clone (development, the author's setup):**
```bash
uv tool install --editable /home/nick/Work/PhaseHypervisor
```
The editable install follows the repo's main checkout, so merged phases take effect without reinstalling (ADR-0016). Undo: `uv tool uninstall phx`. Without installing: `cd /home/nick/Work/PhaseHypervisor && uv run phx …`, or `cd src && python3 -m phx …`.

## Quick start
```bash
phx plan ~/Work/YTPL2              # what PHX sees: next phase, Gates, open questions
phx preflight ~/Work/YTPL2         # one interactive session: answer what the rest will need
phx run ~/Work/YTPL2 --dry-run     # what it would run, in order; launches nothing
phx run ~/Work/YTPL2 --detach      # run hands-off in the background
phx status ~/Work/YTPL2            # where it is, what it waits for, tokens and cost so far
phx log ~/Work/YTPL2 -f            # follow every decision as it happens
```
The repo must carry the hands-off contract (`PHX-CONTRACT: 1` in `.claude/commands/phase.md`; Phase 09 migrated MeetingMaster3, chessloopDeploy, OCC and YTPL2) and live under `~/Work` (spec S1; the variable `PHX_WORK_ROOT` overrides that root).

## `phx preflight`: answer the foreseeable questions first
```bash
phx preflight [<repo>]             # interactive session on opus, in the repo's main checkout
phx preflight [<repo>] --dry-run   # build the session prompt and print the command; launch nothing
phx preflight [<repo>] --check     # is the recorded preflight still current? (exit 0 yes, 3 no)
```
A preflight is one interactive Claude Code session (through `ai-provider run` when installed, so it follows the provider switch; otherwise `claude`) that reads the plan, the spec's Amendments and the prompts of every phase not yet `✅ Complete` (not the code, to keep tokens down). It lists everything a hands-off session would otherwise stop for: open or deferred owner questions, "ask Nick" or "confirm" instructions, keys and logins, spending, manual or hardware checks, publishing, and risky steps. It checks the prerequisites it can check cheaply (tools on PATH, `gh auth status`, whether key files **exist**; it never reads them) and asks you in rounds of up to four questions, recommended answer first. Then it:
- writes each answer into the Owner questions table (`Decided <TS>: … (phx preflight)`) and, for real decisions, an ADR;
- proposes a Gate for every remaining phase (`review` for publishing, spending or manual-check phases, `owner` where you must act yourself) and writes the ones you confirm (adding the `Gate` column if the plan has none);
- commits `docs(plan): phx preflight <TS>` to `main` and pushes;
- runs `phx preflight --record`, which writes `.phx/preflight.json` (time, a fingerprint of the phase table, the phases covered, what was left unresolved), commits it and pushes.

Before the session starts, PHX does the free part itself: it refuses if a phase is `🔄 In progress` (preflight runs between phases; see `phx status`), if a supervisor is running on the repo, if the main checkout is not on `main`, or if every phase is complete. It lists the remaining phases with a suggested Gate and the questions already on file, scans the remaining prompts for leads ("ask Nick", publishing, keys, spend, manual checks), and checks `git`, `gh`, `uv`, `docker` and `gh auth status`. All of that goes into the session prompt, which is saved (mode 0600) in `~/.local/state/phx/<repo>/preflight/` and passed with `--append-system-prompt-file`. The session runs with your normal permission settings, not bypassed, because you are there.

Publishing is never pre-approved: making a repo public, publishing a release or force-pushing still needs your yes at that moment (spec S5). The preflight records the details (owner, name, visibility…) so the phase only has to ask "go?", and gives such a phase a `review` Gate.

**Mid-plan:** a preflight covers only the phases not yet complete, so you can run one at any phase boundary, for example after `/phase-add`.

**Staleness:** `phx run` checks `.phx/preflight.json` on `main` before starting. It warns (or, with `--require-preflight`, refuses) when there is none, or when it is stale: a phase row was added, removed or redefined (name, model, dependencies, prompt, Gate) since, or an owner question is open that the preflight never saw. Completing phases and answering questions do not make it stale. `phx status <repo>` shows the same line.

## `phx run`: run a plan hands-off
```bash
phx run [<repo>] [--detach] [--pause-after NN] [--until NN] [--max-phases N] [--dry-run [--skip-test-check]] [--require-preflight]
```
Each round, PHX re-reads the plan from `main` and picks, in this order:
1. a usage-limit wait left by an earlier run (it finishes the wait, then resumes that session);
2. a `🔄 In progress` phase, whoever started it: PHX first makes sure no Claude Code session is open in its worktree or in the main checkout, then resumes the session it recorded for that phase (`--resume`), or starts `/phase NN --auto`, whose own resume logic takes over;
3. a `⛔ Blocked` phase: it pauses while an owner question that phase needs is open; once answered, `/phase NN --auto` resumes it;
4. the next eligible phase (`⬜`, dependencies `✅`, no open question needing it).

Gates (spec R12): `owner` phases are never started (PHX pauses and tells you to run them yourself with `/phase NN`); `review` phases run, then PHX pauses so you can look before the next one; `auto` phases just run. After each session PHX verifies the phase on `main` (Phase 06) and decides: next phase, pause, wait for a usage limit, resume the same session, or retry fresh.

Options:
- `--detach`: **always use it when you start PHX from inside Claude Code** (a `!` command or a Bash call): a foreground run gets SIGTERM when that session is backgrounded, ends or times out, and stops mid-phase (Phase 10 pilot). Runs as the transient systemd user unit `phx-<repo>`; the command returns once the supervisor holds its lock. It survives closing the terminal; with `Linger=no` (this machine's setting) it stops when you log out completely. `systemctl --user status phx-<repo>` shows the unit.
- `--pause-after NN`: pause after phase NN completes.
- `--until NN`: run up to and including NN, start nothing later, then finish.
- `--max-phases N`: finish after N phases complete in this run.
- `--dry-run`: print the phases it would run in order (assuming each completes), with the exact launch command, and where it would stop. Launches nothing, takes no lock, writes no state. It then runs the test command once, exactly as verification will (a clean clone of `main`, no installed dependencies, no shell). If the command fails, PHX says so; when the repo tracks a lockfile (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `uv.lock`), it also prints a `test_command` for `.phx/config.toml` that installs dependencies first (Phase 11). A failure can be expected early in a plan, before the phase that adds what the tests check. `--skip-test-check` skips this step.
- `--require-preflight`: refuse to start (exit 1, rule `preflight_missing` or `preflight_stale`) unless a current preflight is recorded. Without it, PHX only warns. A `phx resume` refused this way keeps its pause (`pause_kept` in the log).

Exit status: `0` finished (nothing left, or `--until`/`--max-phases` reached), `1` error (another supervisor running, plan or contract problem, repo outside `~/Work`, internal error), `3` paused, `4` stopped.

Only one supervisor runs on the machine at a time (ADR-0007). While it runs, a manual `/phase` in that repo sees its lock and stops instead of claiming (contract §8). If the manual check cannot run (for example, a permission prompt denies it), `/phase` stops too and says so (fail-closed, ADR-0020).

## When a run pauses
A pause is remembered in `state.json` until you clear it with `phx resume`; `phx run` on a paused repo refuses and repeats the reason. `phx status` and the notification say why:

| Pause | What to do |
|---|---|
| Phase NN blocked on question #Q | `phx answer <repo> Q "<answer>"`, then `phx resume <repo>` |
| No phase can start (open question needed by the next phase) | answer it, then `phx resume` |
| Gate review after NN | review the phase's work, then `phx resume` |
| Gate owner on NN | run `/phase NN` yourself, then `phx resume` (if NN is already `🔄`, the pause says so: finish it by hand first) |
| `--pause-after NN` | `phx resume` |
| Verification failed / needs review | read `phx status` and `phx log`, fix the repo (or finish the phase by hand), then `phx resume` |
| A Claude session is open in the worktree or main checkout | it may be working on the phase: close it (or wait for it), then `phx resume`. An idle session in the main checkout, such as the one you drive `phx` from, does not cause this pause: it counts only if the phase's claim commit, branch or worktree changed after it started and after PHX's last session for that phase (ADR-0019, ADR-0021) |
| Authentication or provider error | log in again or fix the provider, then `phx resume` |
| Stopped while verifying (`stopped_during_verification`) | `phx stop` or Ctrl+C arrived while the test command ran, so the test failure proves nothing. Check the phase (or run its tests), then `phx resume` |
| Timeout or crash twice | PHX already resumed once and retried once; check the log, then `phx resume` |

## `phx resume`: clear a pause and carry on
```bash
phx resume [<repo>] [same options as run]
```
Clears the recorded pause, then runs exactly like `phx run` (including `--detach`).

## `phx answer`: answer an owner question
```bash
phx answer ~/Work/YTPL2 6 "Use the blue theme"
```
Writes `Answered <timestamp>: <answer>` into that question's Status cell in the plan on `main`, commits only the plan file (`docs(plan): answer owner question 6`) and pushes when the repo has an `origin`. It refuses while a supervisor is running on the repo, when the main checkout is not on `main` or has uncommitted plan changes, and for a question that is not open (`--force` overwrites one). A `|` in the answer is escaped. Editing the plan by hand works just as well.

## `phx status`: where is it?
```bash
phx status ~/Work/YTPL2    # one repo: supervisor PID/unit, last run, phase, wait time left, pause reason, tokens and cost per phase, plan summary, open questions
phx status                 # every repo PHX has run
phx status ~/Work/YTPL2 --json
```
"supervisor gone" means the last run was running or waiting when its process died (crash, kill, reboot); the next `phx run` carries on from `state.json`.

## `phx stop`: stop cleanly
```bash
phx stop ~/Work/YTPL2 [--timeout 120]
```
Sends SIGTERM to the supervisor (foreground or detached) and waits for it to exit. The supervisor stops the running session's process group, logs the stop and writes the run summary; the phase stays `🔄` with its session ID recorded, so the next `phx run` (or `phx resume`) continues that same session. A usage-limit wait is kept and continues on the next run. Ctrl-C on a foreground `phx run` does the same. To finish the phase by hand instead, stop PHX first, then run `/phase NN`.

## `phx log`: what happened and why
```bash
phx log ~/Work/YTPL2            # last 40 events, one line each
phx log ~/Work/YTPL2 -f         # follow
phx log ~/Work/YTPL2 -n 0 --json   # everything, raw JSON
```
`~/.local/state/phx/<repo-name>/run.jsonl` holds every decision with its reason: `run_start`, `plan` (next eligible phase and why each other phase waits), `select` (what runs and why), `session_dropped` (a recorded session forgotten because its phase was finished outside PHX), `launch` (full command line, provider), `session_end` (exit class, tokens, cost; a session stopped or cut off by a limit before its final result event counts the tokens of its turns, with cost unknown), `verify`, `decision`, `retry`, `wait_start`, `provider_check`, `provider_switch`, `wake`, `probe`, `wait_extend`, `wait_end`, `notify`, `run_end` (finished, paused, stopped or failed, with the reason and totals), `vault`. Session transcripts are in `sessions/<phase>-<n>.jsonl` beside it, and the current state in `state.json`. Everything is redacted before it is written.

## Usage limits and switching provider
When a Pro 5-hour or weekly limit stops a phase, PHX records the stop, notifies you with the resume time and waits: until the announced reset time plus 2 minutes, or 30 min, 1 h, 2 h, 4 h, then every 6 h when no reset time is given. Then one tiny `haiku` probe checks that capacity is back and the **same session** resumes (`--resume`). The wait survives suspend, `phx stop` and restarts.

To resume sooner with the optional `ai-provider` switch installed, switch it to OpenRouter (the author binds that to a key): PHX checks `ai-provider get` every 5 minutes (`poll_interval_s`) during a wait and resumes at once on OpenRouter. It never switches provider by itself (ADR-0006).

## Without `ai-provider`, notifications or systemd
- **No `ai-provider`:** `phx` launches `claude` from `PATH` and logs `ai-provider not found; launching claude directly (provider switch ignored)`. Usage-limit waits, probes and resumes work the same; the provider shows as `unknown` and there is no early resume on a provider switch.
- **No `notify-send` or no display:** notifications are skipped and logged; `phx status` and `phx log` have everything.
- **No `systemd-run --user`** (macOS, containers, non-systemd distributions): `--detach` fails. Run `phx run` in a terminal you keep open, for example in `tmux`. Never start it in the foreground from a Claude Code Bash call.
- **Repos outside `~/Work`:** set `PHX_WORK_ROOT` to your projects folder.

## Notifications
Desktop notifications (silent, never spoken) for: phase complete, blocked (with a short haiku summary of why), usage-limit wait (with the resume time), provider switch noticed, verification failure, other pauses and run finished. Without a display they are skipped and logged.

## Obsidian run summary
At the end of every run (finished, paused or stopped), PHX appends one line to the project note named in the repo's `CLAUDE.md` ("The Obsidian project note `…`"): outcome, then per phase the result, tokens, cost, sessions and waits. It changes only that note's `## Log` section and `updated:` field. The note must be a `.md` file inside your vault, `$PHX_VAULT_ROOT` (default `~/Documents`); for any other path PHX skips the summary and logs why (Phase 11).

## Troubleshooting
- **"another phx supervisor holds the … lock"**: one supervisor at a time per machine. `phx status` shows which; `phx stop <that repo>` stops it.
- **"repo not yet migrated"**: the repo's `phase.md` lacks `PHX-CONTRACT: 1`. The four existing projects were migrated in Phase 09; a newer repo gets the marker from the `phased-project` skill, an older one by the skill's "Migrating to the hands-off contract" checklist.
- **"run is paused"**: see "When a run pauses"; `phx resume` clears it.
- **"no preflight recorded" / "preflight … is stale"**: run `phx preflight <repo>`; the warning names what changed. Ignore it if you'd rather let phases block on their own questions.
- **`phx preflight` says "needs an interactive terminal"**: it opens a normal Claude Code session; run it in a terminal (`--dry-run` works anywhere).
- **"is outside …/Work"**: PHX runs only repos under `~/Work` (spec S1).
- **A warning about the test command**: verification runs it without a shell; set `test_command` in `.phx/config.toml` to a script (ADR-0015).
- **The detached unit is gone**: it is collected when it ends; `phx log` and `phx status` still have everything. `journalctl --user -u phx-<repo>` shows its stdout.
- **Lock files** in `$XDG_RUNTIME_DIR/phx/` stay after a run; an unlocked file means "not running".
- **`phx: …run.jsonl not written (No space left on device)`** on stderr (or in `journalctl --user -u phx-<repo>`): the state disk is full. The run carries on and keeps its decisions on stderr. Free space; the next write succeeds (`state_write_recovered`).
- **"note is not a .md file inside the vault"** in the `vault` event: the note named in `CLAUDE.md` is outside `$PHX_VAULT_ROOT`. Set `PHX_VAULT_ROOT` if your vault lives elsewhere.
- **`verification_failed` with "command not found" after good work**: the clean clone has no installed dependencies. Run `phx run <repo> --dry-run` for a suggested `test_command`.

## `phx plan`: see what PHX sees
```bash
phx plan /home/nick/Work/YTPL2          # human-readable
phx plan /home/nick/Work/YTPL2 --json   # everything, for scripts and debugging
phx plan                                # the repo in the current directory
```
It changes nothing. Everything comes from the repo's **`main`** branch (`git show main:…`), never from the working tree or a phase branch, the same way parallel `/phase` agents read the Status column.

The output has:
- **The phase table**: ID (sorted `15` < `15a` < `15b` < `16`), name, model alias passed to `--model` (`?` if the cell maps to no alias), dependencies, status, Gate and the phase's live branch/worktree. A Gate marked `(prompt)` came from the prompt header (`**Gate:** …`); `(inferred)` means the prompt mentions making a repo public or publishing a release and the plan sets no Gate, so PHX treats it as `review`.
- **Next**: the lowest `⬜ Not started` phase whose dependencies are all `✅ Complete` and that no open owner question needs. This is what `/phase next` would pick. The Gate is reported but does not change "next"; `phx run` applies it.
- **Resume candidates**: phases that are `🔄 In progress`.
- **Why the others wait**: a reason for each not-started or blocked phase (dependencies not complete, open owner question, or "eligible, after NN").
- **Drift** (⚠️): a `phase-NN-*` branch or worktree whose row is not `🔄` (a skipped claim; `⛔ Blocked` rows are exempt because a block keeps its branch), a `🔄` row with no branch or worktree (a stale claim), or a branch for a phase that is not in the table.
- **Open owner questions**: rows whose Status cell starts with `Open`, with the phases that need them.
- **Contract**: the `PHX-CONTRACT` version in `.claude/commands/phase.md`, or "repo not yet migrated". PHX will not run a repo without a known version (Phase 09 migrated the four existing repos).
- **Test command**: from `.phx/config.toml` (`test_command = "…"`) on `main` if set, else the backticked commands of the first clause of the shared instructions' "Tests, lint and type checks pass" line, else none.
- **Problems** (⚠️): things that look wrong but don't stop parsing, such as a status cell with no icon or two, an icon that disagrees with its word, an unknown model on a phase still to run, a dependency not in the table, or a prompt file missing on `main`.

Exit status: `0` when the plan was read, `1` with `phx plan: <reason>` when it cannot be (no plan on `main`, a malformed phase ID or row, a duplicate ID, a missing column, an unreadable status, an unknown Gate value, an invalid `.phx/config.toml`).

## `/phx`: drive PHX from inside Claude Code (Phase 09)
`/phx` ships in the `phased-project` plugin (`plugins/phased-project/commands/phx.md`, Phase 12a). Installed as a plugin it is typed `/phased-project:phx`; a manual copy in `~/.claude/commands/phx.md` (or a symlink, as on the author's machine) keeps `/phx`. It is user-level, so it works in any session and any directory. If `phx` is not installed it says how to install it and stops:

| Command | What it does |
|---|---|
| `/phx status [repo]` | runs `phx plan` and `phx status`, then summarises the next phase, the run state and anything that needs you (open question, pause, drift, `Contract:` not 1) |
| `/phx preflight [repo]` | runs `phx preflight <repo> --check` and `--dry-run`, summarises the remaining phases, leads and whether the record is current, then tells you to run `phx preflight <repo>` in a terminal (not a `!` command here). The preflight itself is an *interactive* session and refuses without a terminal, so it cannot run inside another session (ADR-0017) |
| `/phx resume [repo]` | runs `phx status`, says why the run stopped or paused, asks you to confirm, then starts `phx resume <repo> --detach` |
| `/phx run [repo] [--pause-after NN …]` | checks the contract and preflight, shows `phx run --dry-run`, asks you to confirm, then starts `phx run <repo> --detach` and tells you how to follow it (`phx status`, `phx log -f`, `phx stop`, `phx resume`) |

`repo` is a path, a name from `Project aliases` or a folder under `Work root` in your "Phased-project settings" (see [`examples/CLAUDE.user.md`](../examples/CLAUDE.user.md); the author's aliases are `MM3`, `CL`, `OCC`, `YTPL2`), or, when left out, the repo of the current directory. The command never answers owner questions, edits a repo or stops a run unless you ask. To remove it: uninstall the plugin, or delete the manual copy.

## Migrating a repo (Phase 09)
Repos made with the skill after 2026-10-14 already carry the contract. For an older repo, the `phased-project` skill has a "Migrating to the hands-off contract" checklist (also in the playbook note). MeetingMaster3, chessloopDeploy, OCC and YTPL2 were migrated on 2026-10-26 17:16 CDT with one `chore(phx): adopt hands-off phase contract` commit each; `phx plan <repo>` reports `Contract: 1` for all four. Run `phx preflight` after migrating: the explicit Gate column changes every row's fingerprint, so an earlier record is stale.

## Per-repo settings (`.phx/config.toml`)
Optional, committed on `main`, never containing secrets. Unknown keys or wrong types are an error.

| Key | Default | Meaning |
|---|---|---|
| `test_command` | from the shared instructions | Command verification runs on a clean clone of `main` (Phase 06). No shell: `&&`, `cd DIR`, `NAME=value`, quotes and globs (`**` too) work; pipes, `;`, `||`, redirects and `$VAR` do not, so point it at a script for anything more (ADR-0015). The clone has **no installed dependencies** (no `node_modules`, no build output; `uv run` syncs itself, `npm` does not), so a repo whose checks need them installs them first, e.g. YTPL2's `npm ci --prefix frontend && make check` (Phase 10 pilot). If the file sits under a broad ignore rule such as `config.toml`, add `!.phx/config.toml` to `.gitignore`: PHX reads it from `main` |
| `test_timeout_s` | `3600` | Cap on each verification test command (Phase 06) |
| `max_budget_usd` | none | Passed as `--max-budget-usd` **only when the provider is OpenRouter** (spec R9) |
| `idle_timeout_s` | `1800` | A phase session that emits no stream event for this long is stopped (SIGTERM, then SIGKILL) and classified `timeout` (Phase 05) |
| `wall_timeout_s` | `21600` | Hard cap on one phase session (Phase 05) |
| `poll_interval_s` | `300` | How often a usage-limit wait re-checks `ai-provider get` for a switch to OpenRouter (Phase 07) |
| `limit_poll_interval_s` | `900` | After a known reset time has passed and the probe still hits the limit, how often to probe again (Phase 07) |
| `triage` | `true` | When a phase blocks, needs review or fails verification, one tool-less `haiku` turn writes a ≤ 150-word summary for the notification and `run.jsonl` (Phase 06) |

Session transcripts land in `~/.local/state/phx/<repo-name>/sessions/<phase>-<n>.jsonl` (redacted), and every launch and its classified ending in `run.jsonl` beside it.

## How PHX checks a phase (Phase 06)
After every phase session PHX looks at the repo itself instead of trusting the session's last line: the row on `main`, whether the phase branch was merged and deleted and its worktree removed, the Phase Log entry and its Timeline, whether the main checkout is on `main` and has no new uncommitted files, and the test command, run in a throwaway clone of `main` (your checkout is never touched). If the session's `PHX-RESULT` line says something the repo does not show, the phase is marked **needs review** and PHX pauses with both sides in the report. The only change PHX ever makes on its own is committing `⛔ Blocked` for a phase whose agent blocked but forgot to record it. Every check and decision is in `run.jsonl` (`verify`, `repair`, `triage` and `decision` events). Before retrying or resuming a phase, PHX pauses if a Claude Code session is open in that phase's worktree or in the repo's main checkout, since it may be the one working on it.

