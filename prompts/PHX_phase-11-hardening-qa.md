# PHX Phase 11: Hardening, security review & QA

**Model:** Opus 5.5 (`/model claude-opus-5-5`) · **Depends on:** 10 · **Branch:** `phase-11-hardening-qa`

## Read first
`CLAUDE.md`, `prompts/PHX_shared-instructions.md`, spec §4.3, ADR-0003, ADR-0004. `docs/PHX_PILOT_REPORT.md`. All Phase Log follow-ups. Phase Log entry for 10.

## Goal
PHX is safe to leave running: the threat model is written down, risks are mitigated or accepted on record, failure modes are tested, and every follow-up is closed.

## Tasks
1. `docs/PHX_THREAT_MODEL.md`, covering:
   - bypassed permissions;
   - prompt injection through repo text, plan rows, phase prompts or tool output steering a phase agent or the triage/preflight sessions;
   - PHX itself parsing hostile plan text (S3), including the shell-free test-command interpreter in `phx.verify` (ADR-0015: quoting, globs, `cd` confinement) and the tool-less triage prompt in `phx.triage`;
   - secrets in logs and session transcripts;
   - lock and state races;
   - systemd-run environment exposure;
   - the `phx answer` write path (Phase 07: `cli.answer_question`, refuses while the lock is held);
   - the S1 guard and its `PHX_WORK_ROOT` override, the `--detach` environment allowlist (`detach.ENV_ALLOWLIST`), stale lock files left in `$XDG_RUNTIME_DIR/phx/` by design, and signal handling during `state.json` writes (ADR-0016);
   - git operations on the wrong repo or branch;
   - runaway spend on OpenRouter;
   - a malicious or broken `ai-provider` on PATH.

   Rate each threat, name the mitigation and its test, or record the accepted risk.
2. Fix what the review finds; run `/security-review` and `/code-review high` on the full codebase and address findings.
3. Failure injection: kill -9 the supervisor mid-phase and mid-state-write; full disk on the state dir; git lock contention; clock jumps across suspend; a plan edited by Nick during a run (PHX must re-read and respect it).
4. Coverage ≥ 90 % overall, 100 % on `plan.py`, `classify.py`, `recover.py` (`recover.py` was 95 % at the end of Phase 06: the git-commit-failure and push-timeout paths of `repair_blocked` and some `/proc` read errors are untested).
5. Secret-redaction audit: grep every state and session file produced in Phase 10 for key patterns.
6. Docs pass: README, user guide, architecture, SECURITY all accurate; THIRD_PARTY_NOTICES for dev tools if required.
7. Close or explicitly defer every Phase Log follow-up.

## Out of scope
New features.

## Tests
The failure-injection suite above; redaction audit script kept as a test.

## Acceptance criteria
- Threat model complete; no unmitigated High risk.
- All checks and the new tests pass; no secrets in any PHX output from the pilots.

## Phase-specific docs
Threat model, SECURITY, all affected docs, CHANGELOG. Then the standard close-out checklist.
