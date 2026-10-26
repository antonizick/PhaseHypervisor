# Stream-json fixtures (Phase 05)

Claude Code `--output-format stream-json --verbose` streams that the runner and classifier tests replay through the fake `claude` in `tests/fakes/`. `{{session_id}}` is replaced by the fake with the `--session-id` / `--resume` value. Evidence and reasoning: ADR-0009 in `docs/PHX_DECISIONS.md`.

**Provenance key**
- **real**: captured from Claude Code 2.1.310 on this machine (2026-10-26), sanitised (bulky `init` event reduced, session ID templated, thinking signature dropped).
- **real-text**: the message text is verbatim from a real `~/.claude/projects` transcript; the event *shape* is the real stream-json shape captured from 2.1.310 for the same kind of error (synthetic assistant message with `error` + `is_api_error_message`, then a `result` with `is_error: true`, `terminal_reason: "api_error"`, `api_error_status`).
- **documented**: built from the message templates and event builders inside the Claude Code 2.1.310 binary (no live sample available); field names and formats match the code.
- **synthetic**: real event shape, invented content (normal phase outcomes).

| File | Class | Provenance | Notes |
|---|---|---|---|
| `complete.jsonl` | complete | synthetic | Valid `PHX-RESULT` line; usage and cost for accounting tests |
| `blocked.jsonl` | blocked | synthetic | `question_ids: ["6"]` |
| `refused.jsonl` | refused | synthetic | |
| `no_result.jsonl` | no_result | synthetic | Clean end, no result line |
| `bad_result_line.jsonl` | no_result | synthetic | Valid line followed by a malformed last line: last wins, so none |
| `usage_limit_session.jsonl` | usage_limit | real-text | `You've hit your session limit · resets 7:40pm (America/Chicago)` (transcript 2026-10-12), `error: rate_limit`, status 429 |
| `usage_limit_weekly_event.jsonl` | usage_limit | documented | `rate_limit_event` with `status: rejected`, `rateLimitType: seven_day`, `resetsAt` epoch seconds, plus the `weekly limit` text with a dated reset |
| `rate_limit_429_api_key.jsonl` | usage_limit (Pro) / provider_error (OpenRouter) | real | Captured against a local fake API answering 429 (API-key auth shows the generic text, not the subscriber text) |
| `auth_expired.jsonl` | auth_error | real-text | `Login expired · Please run /login`, `error: authentication_failed` (transcript 2026-10-20) |
| `openrouter_402.jsonl` | provider_error (credits) | real-text | OpenRouter 402 text (transcript 2026-10-17); key ID in the URL replaced by `<key-id>` |
| `connection_refused.jsonl` | provider_error (server) | real | Captured against a closed local port |
| `server_lost.jsonl` | provider_error (server) | real-text | `Connection lost mid-response` (transcript 2026-10-24) |
| `truncated.jsonl` | crash | synthetic | No `result` event and a half-written last line |
| `max_budget.jsonl` | provider_error (budget) | documented | `subtype: error_max_budget_usd` |
| `probe_ok.jsonl` | complete (probe) | synthetic | One-turn `ok` answer |
| `probe_real.jsonl` | complete (probe) | real | The Phase 05 live `haiku` probe on Anthropic Pro, including a real `rate_limit_event` (`status: allowed`, `unifiedWindows`) |
