# PHX Phase 08: Preflight question sweep

**Model:** Opus 5.5 (`/model claude-opus-5-5`) · **Depends on:** 07 · **Branch:** `phase-08-preflight`

## Read first
`CLAUDE.md`, `prompts/PHX_shared-instructions.md`, spec §1 ("ask me any questions in advance that it could practically anticipate"), §4.2 R12, R13, R9. `docs/PHX_AUTO_MODE_CONTRACT.md`. Nick's preference for Option | Pros | Cons tables when he asks for trade-offs (global CLAUDE.md). Phase Log entry for 07.

## Goal
`phx preflight <repo>` front-loads Nick's involvement: one interactive session asks everything foreseeable for the rest of the plan, so `phx run` can go hands-off with as few blocks as possible.

## Tasks
1. `prompts/PHX_preflight.md`: the session prompt. It tells the agent to:
   - read the plan, the Owner questions, the spec Amendments and every not-started phase prompt (prompts only, not the codebase, to keep tokens down);
   - list each decision a phase would otherwise stop for: open owner questions, "ask Nick" or "confirm" instructions, credentials or keys, paid services and caps, hardware or manual checks, publishing steps, anything that looks risky under the risk rule;
   - check prerequisites it can check cheaply: tools on PATH, `gh auth status`, key files **exist** (never read their contents), Docker or GPU if a prompt needs them;
   - ask Nick in AskUserQuestion rounds (≤ 4 per round, recommended option first, labelled "(Recommended)"), grouping by phase;
   - record each answer in the Owner questions table (Decided + timestamp) and as an ADR where it is a decision;
   - propose Gates (`review` for publishing, manual-check or spend phases; `owner` where Nick must act physically), and confirm them with Nick;
   - commit `docs(plan): phx preflight <TS>` to `main` (claim protocol rules: main checkout, plan file only plus the decisions file);
   - write `.phx/preflight.json` (timestamp, plan hash, phases covered, unresolved items) and commit it.
2. `preflight.py`: launch the session **interactively** (not `-p`) through `ai-provider run` with `--model opus` and the prompt via `--append-system-prompt-file` or an initial message (check which works for an interactive start), in the repo's main checkout; refuse if a phase is `🔄` (offer `phx status`).
3. Staleness: `phx run` warns (and with `--require-preflight` refuses) if `.phx/preflight.json` is missing or its plan hash is older than the plan's last change to the phase table or Owner questions.
4. A preflight also works mid-plan: it covers only phases not yet complete.

## Out of scope
Answering questions on Nick's behalf; reading the codebase in depth.

## Tests
Prompt-assembly and staleness logic unit tests; launch argv with the fake; a fixture plan with known open questions where a scripted fake asserts the expected question list (no tokens).

## Acceptance criteria
- On the MM3 fixture, a dry review of the generated question list (by reading the prompt's instructions against MM3's remaining phase 16) shows it would catch the GitHub-publication confirmation and set Gate `review`.
- A real preflight is **not** run here; Phase 10 does that.

## Phase-specific docs
User guide (preflight section), architecture, CHANGELOG. Then the standard close-out checklist.
