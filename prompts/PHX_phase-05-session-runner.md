# PHX Phase 05: Session runner & exit classifier

**Model:** Opus 5.5 (`/model claude-opus-5-5`) · **Depends on:** 02 · **Branch:** `phase-05-session-runner`

## Read first
`CLAUDE.md`, `prompts/PHX_shared-instructions.md`, spec §4.2 R2, R5, R7, R8, R9, R10, §4.3. ADR-0005, ADR-0006, ADR-0009 (Proposed). `~/.local/bin/ai-provider` (read it; do **not** read the key file). `claude --help`. Phase Log entry for 02.

## Goal
`phx.runner` launches one Claude Code session the right way for the selected provider, streams and stores its output, accounts for tokens and cost, and classifies how it ended, including usage limits, with fixtures proving each class.

## Tasks
1. Launcher: argv `["ai-provider", "run", "-p", prompt, "--model", alias, "--permission-mode", "bypassPermissions", "--output-format", "stream-json", "--verbose", "--session-id", uuid]` (or `--resume <id>` to continue), cwd = repo main checkout, env adds `PHX_AUTO=1` and removes any inherited `ANTHROPIC_MODEL`. Find `ai-provider` on PATH, else `~/.local/bin/ai-provider`, else fall back to `claude` with a logged warning (R7). Check `claude --help` for whether `--verbose` is required with stream-json, and record the answer.
2. Provider snapshot per launch: `ai-provider get`, and for OpenRouter the mapped model from `ai-provider env` **with secrets redacted before logging** (never log the env output raw).
3. Optional `--max-budget-usd` only on OpenRouter when `.phx/config.toml` sets it (R9).
4. Stream handling: write raw events to `sessions/<phase>-<n>.jsonl` (redacted), track last-event time for a heartbeat, extract the final `result` event (usage, cost, duration, `is_error`, subtype) and the `PHX-RESULT` line.
5. Timeouts: an idle timeout (no events for N minutes, default 30) and a wall-clock cap (default 6 h), both configurable; on timeout, SIGTERM then SIGKILL the process group.
6. **Verify ADR-0009:** find the real shape of a headless usage-limit stop. Look in the official Claude Code docs and changelog (WebFetch/WebSearch), in `~/.claude/projects/*/*.jsonl` transcripts on this machine for past limit messages, and in `stream-json` error/result subtypes. Write fixtures from what you find (real samples redacted, or documented formats marked as such). Update ADR-0009 to Accepted (with the evidence) or record the fallback-only decision.
7. Classifier (`classify.py`), pure function over (exit code, result event, last events, stderr tail) → `complete | blocked | usage_limit(reset_at?) | auth_error | provider_error(kind) | timeout | crash`, each with a human reason. Parse reset times in the formats found in task 6, converting to local time.
8. Limit probe: `probe()` runs a minimal 1-turn `haiku` call through the same launcher (`-p "ok" --max-turns 1`) to test whether capacity is back; returns a classification.
9. Fakes: `tests/fakes/claude` and `tests/fakes/ai-provider` executables that replay a fixture stream, exit code and delay chosen by env vars, so every later phase can test without tokens.

## Out of scope
Deciding what to do with a classification (06/07).

## Tests
Argv/env construction per provider; redaction of the env snapshot; stream parsing incl. truncated output; each classifier class from fixtures; timeouts with the fake; resume argv; probe.

## Acceptance criteria
- With the fakes, every exit class is produced and logged with tokens/cost where present.
- ADR-0009 is resolved with evidence; the fixtures say whether each sample is real or documented.
- No test spends tokens. (Optional, ≤ 1 cheap real call: one `haiku` probe on the current provider to confirm the argv works; log its cost.)

## Phase-specific docs
`docs/PHX_ARCHITECTURE.md` (runner, classifier), ADR-0009, CHANGELOG. Then the standard close-out checklist.
