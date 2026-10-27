# PHX Pilot Report (Phase 10)

Pilots ran 2026-10-26 17:46 CDT to 2026-10-26 22:21 CDT. Every number below was measured: phase sessions from PHX's own `session_end` events in `~/.local/state/phx/<repo>/run.jsonl` (the stream-json `result` event, or the per-message fallback for cut-off sessions), interactive sessions from Claude Code's transcript `~/.claude/projects/<dir>/<session>.jsonl` (assistant messages deduplicated by message ID). "Cache read" and "cache write" are `cache_read_input_tokens` and `cache_creation_input_tokens`; "tokens" is their sum with input and output. Costs are the `total_cost_usd` Claude Code reports (list prices on a Pro/Max login; nothing was billed per token). The "Pilot" repos are a throwaway plan, `~/Work/tries/phx-pilot` (prefix `PXP`), and YTPL2.

## 1. What was exercised

| Path | Where | Result |
|---|---|---|
| Dry runs on the migrated repos | MM3, CL, OCC, YTPL2 | Planned actions correct (MM3 → 16 then review pause; CL finished; OCC → 11 then pause on Q9; YTPL2 → 03, 05 then pause on Q5/6/14). No repo had a preflight record. Fixed: an over-long pause reason (now summarised) and the launcher path |
| Real preflight → `--check` → two commits | PXP, YTPL2 | Both recorded and `--check` exit 0. `--require-preflight` refused after phases 07–09 were added to PXP ("phase(s) added: 07, 08, 09") |
| Hands-off phases on the plan's models | PXP 01, 02, 05 (haiku), 03 (sonnet), 07–09 (haiku); YTPL2 03 (opus) | All verified independently (status, merge, worktree, Phase Log, tests in a clean clone) |
| Open owner question before launch | PXP 01 → 02 | PHX paused instead of launching 02 with Q1 open; `phx resume` after Nick answered |
| Agent-raised block → `phx answer` → `phx resume` | PXP 07 | Agent added Q2 and committed `⛔`; PHX verified it and wrote a haiku triage summary; resumed from `⛔` and completed |
| Usage limit mid-session | PXP 08 (shim) | Classified `usage_limit`, waited 308.6 s (reset + 2 min) with 2 provider checks, 1 probe, then `--resume` of the **same** session, which completed |
| `phx stop` mid-phase → `phx resume` | PXP 05 (Nick), PXP 09 | Clean stop (exit 4, `🔄` kept, session recorded); 09 resumed the **same** session and completed, with 7 idle Claude processes in the main checkout ignored |
| Handover manual → PHX → manual (ADR-0011) | PXP 03 (PHX) → 04 (manual) → 05 (PHX, then manual) → 06 (manual) | Status, Phase Log and vault note consistent throughout; `owner` Gates set in the preflight kept PHX off 04 and 06 |
| Manual `/phase` while PHX runs | PXP 08, 09 (headless haiku tests) | Step 0 prints `PHX-RUNNING …` when it can run; see finding F5 |
| Contract manual check (`PHX_AUTO_MODE_CONTRACT.md#manual-check`) | PXP (in place of a separate `phx-contract-check` repo) | Step 2 (complete + `PHX-RESULT`) on every PXP phase; step 3 (block, no AskUserQuestion, `⛔` commit, `blocked` result) and step 5 (answer, `chore(plan): resume phase 07`, completion) on PXP 07. Step 4 (agent refuses while the question is open) was not reached, because PHX itself never launches a phase with an open question. Step 6 only partly: two headless manual `/phase` runs during a PHX run refused without changes, but on dependency grounds, and one of them carried on after its lock check was denied (F5). Step 7 (`PHX_AUTO=1 ai-provider run -p "/phase next --auto" --permission-mode bypassPermissions`) was **not run**: Claude Code's auto-mode classifier refused to let this phase session launch a bypass-permissions session. Nick can run 4, 6 and 7 by hand |
| Real plan, one phase, hands-off | YTPL2 Phase 03 (opus) | §4 |

## 2. Per-session measurements

### PXP sample plan (haiku/sonnet)

| Phase | Session | Model | Wall (s) | Turns | Input | Output | Cache read | Cache write | Cost (USD) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| 01 | `72efd5d5` | haiku | 68.2 | 22 | 26 | 12,536 | 513,384 | 54,982 | 0.0224 |
| 02 | `c419521f` | haiku | 64.7 | 23 | 32 | 11,888 | 682,005 | 42,308 | 0.0212 |
| 03 | `f4286c79` | sonnet | 35.3 | 8 | 16 | 4,308 | 267,359 | 43,548 | 0.2440 |
| 05 (stopped) | `185999bf` | haiku | 26.5 | – | 0 recorded (transcript: 4,553 out, 385,709 read, 36,057 write) | | | | – |
| 07 (blocks) | `a94ca44d` | haiku | 35.7 | 9 | 16 | 6,232 | 310,740 | 39,823 | 0.0142 |
| 07 triage | `12afd2ea` | haiku | 6.3 | 1 | 2 | 712 | 3,262 | 7,661 | 0.0019 |
| 07 (resumed) | `b974d280` | haiku | 56.9 | 18 | 28 | 10,075 | 654,569 | 51,374 | 0.0219 |
| 08 (limit hit) | `ae2a8461` | haiku | 35.3 | 1 | 12 | 39 | 223,518 | 38,509 | 0.0000 ¹ |
| wait | | | 308.6 | | | | | | |
| probe | `caf918df` | haiku | 4.6 | 1 | 2 | 175 | 9,210 | 14,936 | 0.0032 |
| 08 (resumed, same session) | `ae2a8461` | haiku | 62.3 | 10 | 20 | 11,343 | 584,366 | 15,070 | 0.0258 |
| 09 (stopped) | `b4d2c9e8` | haiku | 23.6 | – | 12 | 51 | 216,856 | 38,180 | – ¹ |
| 09 (resumed, same session) | `b4d2c9e8` | haiku | 49.0 | 9 | 18 | 8,475 | 518,500 | 10,509 | 0.0227 |

¹ Cut-off sessions have no `result` event (or one with zero usage), so their tokens come from the per-message fallback added in this phase; the output figure counts only completed messages and Claude Code reports no cost for them. Phase 05's stop happened before the fix, so PHX recorded 0; its transcript numbers are shown instead.

Run 07–09 with the limit (one `phx run` plus one `phx resume`): **1,588,923 tokens, $0.0476** of reported cost for three phases, a block, a wait and a stop. A typical tiny haiku phase costs 0.5–0.7 M tokens (almost all cache reads) and about $0.02; the same-sized sonnet phase cost 11× more.

### Preflights (interactive opus)

| Plan | Session | Messages | Input | Output | Cache read | Cache write | Wall | Result |
|---|---|---:|---:|---:|---:|---:|---|---|
| PXP | `8a072c59` (preflight part) | 9 | 18 | 4,346 | 481,774 | 34,899 | 18:00:17 → 18:01:28 CDT, incl. Nick's answer | `acd695a` + record `8d848cb`; Gates `owner` on 04 and 06 |
| YTPL2 (phases 03–13) | `51989027` | 21 | 42 | 17,878 | 1,781,031 | 106,860 | 21:49:00 → 21:57:08 CDT (8 min, incl. Nick's answers) | `72fb84f` (plan + 53 lines of ADRs) + record `6337d68`; nothing unresolved |

Claude Code writes no cost into an interactive transcript. The PXP session's total, $0.81, includes Nick driving `phx` from that same session after the preflight. Both preflights read only the plan, the remaining prompts, the decisions log and the assembled context, as `prompts/PHX_preflight.md` allows.

### Hands-off vs. manual

Nick ran PXP 04 by hand (`7c15819e`, haiku, interactive `/phase 04`): 22 messages, 12,754 output, 1,474,565 cache read, 82,448 cache write, 92 s. The hands-off phases of the same size (01, 02) took 65–68 s, about the same output, and **½ to ⅓ of the cache reads** (513–682 K): a headless session does not carry the interactive session's conversation and tool chatter. Supervisor overhead is small: verification uses no tokens, a triage summary 11.6 K tokens ($0.002), a capacity probe 24.3 K ($0.003). No earlier phase-log data in this repo records per-phase tokens, so there is no larger manual baseline.

## 3. Findings and fixes

| # | Finding | Fix |
|---|---|---|
| F1 | Resume falsely blocked twice by the R14 live-session guard: Nick's idle interactive Claude in the main checkout (pid 181859) and a `claude bg-pty-host` wrapper (pid 185546) looked like rivals | Fixed (ADR-0019, R21): pty hosts are skipped (real cmdline `argv[0] == "claude bg-pty-host"`); a main-checkout process counts only if it is a headless `/phase` session or there is work on the phase newer than both its start and PHX's last session end; the reason names ignored PIDs. Verified on PXP 09 with 7 idle processes |
| F2 | A session cut off by `phx stop` recorded 0 tokens | Fixed: per-message usage summed by message ID when `result` is missing or empty (verified: 09 stop recorded 255,099) |
| F3 | Nick, finishing an owner-gated `🔄` phase by hand, got "Gate owner" with no hint | Fixed: "finish it with /phase NN, then phx resume" |
| F4 | Pause reasons listed every waiting phase; launcher path printed as `…/share/../bin/ai-provider`; a recorded session of a phase Nick finished by hand stayed in `state.json` | Fixed (summary, normalised path, `session_dropped`) |
| F5 | Manual `/phase` step 0 **fails open**: in a headless test, permissions denied the lock check four times and the agent carried on (stopping only on dependencies) | Phase 11 task 8: make step 0 fail-closed across the skill, playbook, contract §8 and the five repos' `phase.md` |
| F6 | `phx resume --require-preflight` clears the pause before it refuses | Phase 11 task 8 |
| F7 | A foreground `phx run` started with `!` inside Claude Code dies when the session is backgrounded (SIGTERM at 18:16:13); the stop was clean | `/phx` and the user guide now always use `--detach` from inside Claude Code |
| F8 | The ADR-0019 heuristic could be gamed by a rival that does nothing visible | Phase 11 task 8: threat-model it |
| F9 | Verification's clean clone has no installed dependencies, so checks that need `node_modules` fail after good work (YTPL2 03) | YTPL2 `.phx/config.toml` (`546f4b3`); user guide documents it; Phase 11 task 8: check the test command in a clean clone at preflight / dry-run time and tell triage |

Regression tests: `tests/test_recover.py` (pty host and start time, idle main-checkout session, last session end), `tests/test_runner.py` (usage fallback, limit session counts its turns, launcher path), `tests/test_supervisor.py` (owner-gate message, waiting summary, dropped session). Suite: 428 passed; ruff, format and mypy clean.

## 4. Real plan: YTPL2 Phase 03

`phx run /home/nick/Work/YTPL2 --max-phases 1 --require-preflight --detach` at 21:59 CDT (unit `phx-YTPL2`, worktree code of this phase). Phase 03, "Domain core, exports & FakeYouTube", Gate `auto`, plan model Opus 5.5.

| Item | Measured |
|---|---|
| Session | `2617a398`, `claude-opus-5-5`, 76 turns, 554 stream events, exit 0, `PHX-RESULT` complete |
| Wall time | 1,141.0 s (19 min; API time 1,007 s), claim `71ca3fe` 21:59 → merge `a3f9bfe` 22:16 CDT |
| Tokens | input 142 · output 115,040 · cache read 10,436,766 · cache write 216,416 · total 10,768,364 |
| Cost | $6.12 (phase) + triage 14,195 tokens, $0.0027; verification itself 0 tokens |
| Waits | none (no usage limit) |
| Delivered | models, errors, URLs, CSV/Markdown/text exports, quota maths, planner, `YouTubeClient`, FakeYouTube, config loader; 199 tests, 99.5 % domain coverage; ADR-0021..0023; Phase Log with Timeline and `Model` bullet; vault note row and two log lines; worktree and branch removed. Documented to YTPL2's normal standard |

**Outcome: paused `verification_failed`, then verified.** The agent ran `make check` green in its worktree, but PHX's independent check (the plan's `make check` in a clean clone of `main`) failed in `check-fe`: `prettier` not found (exit 127), because a clean clone has no `frontend/node_modules`. The work was sound: `npm ci --prefix frontend && make check` in a fresh clone passed. Fix in YTPL2 (`546f4b3`): a tracked `.phx/config.toml` with `test_command = "npm ci --prefix frontend && make check"` and `!.phx/config.toml` in its `.gitignore` (a broad `config.toml` rule hid it). `verify_phase` then reported *complete and verified* (tests 26.9 s). The pause is left in place on purpose: `phx resume /home/nick/Work/YTPL2` would go on to Phase 05 (04 has Gate `owner`), which is Nick's call. The pause shows the guard working (PHX did not trust the agent's own green run) and a gap (finding F9). The haiku triage advised `npm install` in the main checkout, which would not have fixed a clean clone.

Cost shape: an opus phase of real size is ~10.8 M tokens, 97 % of them cache reads; output is 1 %. At that rate the eleven remaining YTPL2 phases would cost about 11 × $6.12 ≈ $67 if they were similar in size (an extrapolation, not a measurement).

## 5. ADR-0009 (usage-limit handling)

No real Pro limit and no provider toggle happened during the pilots, so ADR-0009 is unchanged. The limit path was exercised on a real session through a shim that ends the real `ai-provider run` and prints the Phase 05 fixture's limit lines: classification, the reset + 2 min wait, provider checks, the probe and `--resume` of the same session all behaved as ADR-0009 describes.
