# PHX Phase 07: Supervisor loop, state & notifications

**Model:** Opus 5.5 (`/model claude-opus-5-5`) · **Depends on:** 06 · **Branch:** `phase-07-supervisor` · **Gate:** review

## Read first
`CLAUDE.md`, `prompts/PHX_shared-instructions.md`, spec §2, §4.1 A6–A9, §4.2 R10–R14, §4.3 S4. ADR-0006, ADR-0007, ADR-0008. `/home/nick/Documents/04 Resources/OSMods/README.md`. Phase Log entries for 04, 05 and 06.

## Goal
The usable product: `phx run <repo>` drives a plan to the end, one phase at a time, unattended, surviving limits and terminal closures, and tells Nick what is happening.

## Tasks
1. `locks.py`: machine-wide `flock` at the lock path defined in the Phase 03 contract (R15, so manual `/phase` can see a running PHX) (one supervisor at a time, ADR-0007) plus a per-repo lock; stale-lock detection by PID.
2. `state.json` (atomic write): run id, repo, current phase, attempt, session id, classification, wait-until, pause reason, provider at launch, cumulative tokens/cost.
3. `supervisor.py` loop: parse plan (04) → handle resume candidates (R14) → check gate → launch `/phase NN --auto` (05) → classify → verify/recover (06) → log → notify → next. Respect `--pause-after NN`, `--max-phases N`, `--until NN` and `--dry-run` (print what would run, spend nothing).
4. Usage-limit wait (ADR-0006): sleep until `reset_at` (+2 min) or back-off schedule; every 5 min re-read `ai-provider get`; if it changed to `openrouter`, resume immediately. Before resuming after a timed wait, run the cheap probe (05). Wake correctly after suspend (compare wall clock, don't trust a single long sleep).
5. CLI: `phx run <repo> [--detach]`, `phx resume <repo>` (clears a pause), `phx status [<repo>]` (state + plan summary + wait time left), `phx stop <repo>` (graceful: finish logging, SIGTERM the session, leave the phase resumable), `phx log <repo> [-f] [--json]`, `phx answer <repo> <question#> "<answer>"` (writes the answer into the Owner questions row on `main` with a timestamp and commits `docs(plan): answer owner question N`).
6. `notify.py`: `notify-send` for phase complete, blocked (with triage summary), usage-limit wait (with resume time), provider switch noticed, run finished, verification failure. Never audible (no Prometheus speech). Degrade silently when no display.
7. `--detach` (R11): re-exec via `systemd-run --user --unit phx-<repo> --collect --property=…` with the needed env (PATH, HOME, XDG_RUNTIME_DIR, DISPLAY/WAYLAND_DISPLAY, DBUS_SESSION_BUS_ADDRESS); `phx status/stop/log` work against it. Check whether the user's linger setting matters for surviving logout, and document it (don't change it).
8. `vault.py`: at the end of a run (or pause), append a timestamped run summary (phases run, outcomes, tokens/cost per phase, waits) to the project's Obsidian note (path from the repo's `CLAUDE.md`), touching only its Log section and `updated:` field.
9. Install for daily use: `uv tool install --editable .` (or a `~/.local/bin/phx` shim; choose and record in an ADR). This is a host modification: write `/home/nick/Documents/04 Resources/OSMods/PhaseHypervisor (phx).md` and update the OSMods README (at a glance table, section, Where things live, Last updated) per Nick's rules, including how to undo it.
10. `docs/PHX_USER_GUIDE.md`: install, `preflight` (coming in 08), `run`, `--detach`, `status`, `answer`, `resume`, `stop`, provider switching during a run, where the logs are, troubleshooting.

## Out of scope
Preflight (08), migrating other repos (09), real-token pilots (10).

## Tests
End-to-end with the fakes over a 3-phase sample plan in `tmp_path`: happy path; block → answer → resume; usage limit with reset time; limit without reset time (back-off with a fake clock); provider toggled during the wait; crash → resume; `--pause-after`; gates; lock contention; `phx stop` mid-phase; `--dry-run` spends nothing.

## Acceptance criteria
- The sample plan completes unattended with the fakes, and every scenario above passes.
- `run.jsonl` alone explains every decision in each scenario (Nick's logging rule).
- `phx run --detach` survives closing the launching terminal (manual check, recorded).
- OSMods documentation is updated.

## Phase-specific docs
User guide, architecture, OSMods write-up and README, CHANGELOG, ADRs. Then the standard close-out checklist.
