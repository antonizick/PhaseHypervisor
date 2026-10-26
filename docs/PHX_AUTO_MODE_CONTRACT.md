# PHX: Hands-off `/phase` Contract (version 1)

**Status:** normative · **Contract version:** `1` · **Recorded:** 2026-10-26 09:05 CDT (Phase 03) · **Decision:** [ADR-0012](PHX_DECISIONS.md#adr-0012-hands-off-phase-contract-version-1)

This document defines how a phase command (`.claude/commands/phase.md` made by the `phased-project` skill) behaves when PhaseHypervisor (`phx`) runs it without a human, and what PHX may rely on afterwards. It implements spec R3, R4, R5, R12 and R15 and the rules of ADR-0003, ADR-0004, ADR-0008 and ADR-0011. PHX Phases 04 to 07 implement against it. The skill templates carry the same rules in agent-facing form: hands-off section of `templates/phase-command.md`, §1b of `templates/_shared-instructions.md`, and the "Risk rule" section of `templates/CLAUDE.md`. If they ever disagree with this document, this document wins and the templates are fixed.

The key words **must**, **must not** and **may** are used in their usual normative sense.

## 1. Auto mode on and off
**Trigger.** Auto mode is on for a `/phase` session when either:
- the argument contains the token `--auto`, anywhere (`/phase 05 --auto`, `/phase --auto 15a`), or
- the environment variable `PHX_AUTO` is exactly `1` (checked by the agent with `printenv PHX_AUTO`).

Only PHX sets either one (spec A10). PHX launches `ai-provider run -p "/phase NN --auto"` **and** sets `PHX_AUTO=1`, so both are present; either alone is enough.

**Auto mode always names one phase.** After removing `--auto`, the remaining argument must be one phase ID (`NN` or `NNa`).
- `status` is read-only and behaves exactly as without auto mode (the PHX-running check in §8 is skipped).
- `next`, an empty argument or anything that is not a phase ID: the agent does nothing and ends with a `refused` result (§6), reason `auto mode needs a phase ID`.

**Auto mode off.** When neither trigger is present, `/phase` behaves exactly as it did before this contract (ADR-0011), with one addition: the PHX-running check (§8).

**Never interactive.** In auto mode the agent must not call AskUserQuestion, enter plan mode or wait for any input. Every place where the interactive command would ask Nick is replaced as listed in §2.

## 2. The interactive points and their auto-mode replacement
| # | Interactive `/phase` (unchanged) | Auto mode |
|---|---|---|
| 1 | Model check: if the running model differs from "AI Model to Use", give the `/model` command and ask whether to continue | Skipped: PHX chose the model. The agent writes the model it actually runs as in the Phase Log entry, as the bullet right after the Timeline: `- **Model:** ran as <model ID> (auto mode; plan lists <listed model>)`. |
| 2 | `NN` is `🔄 In progress`: ask Nick to confirm that no other session runs it | Resume without asking (PHX holds the run lock and has checked the worktree, spec R14). |
| 3 | An open owner question needed by this phase: ask Nick | Block-with-question (§4). |
| 4 | `next`: several eligible phases, ask which; an `🔄` phase exists, ask whether to resume | Cannot arise: auto mode names one phase (§1). |
| 5 | Shared instructions §1 step 6: ask Nick before guessing on anything user-visible or hard to reverse | Block-with-question (§4). |
| 6 | Risk rule (§5): stop and ask | Block-with-question (§4). |
| 7 | Close-out "Final message to Nick" | Written as usual, then the result line (§6) as the very last line. |

**Preconditions that make the command "say so and stop"** are not questions and are never recorded as blocks; they end in a `refused` result with no change to any file:
- a dependency of `NN` is not `✅ Complete`;
- the phase is already `✅ Complete`;
- the phase's Gate is `owner` (§7): PHX must not have started it;
- the claim cannot be made (the main checkout is not on `main`, or the plan file has uncommitted changes there);
- the phase ID is not in the table;
- the phase is `⛔ Blocked` and an owner question with `Needed by` naming it is still open (§4.3).

Everything else in `/phase` (reading order, claim protocol §1a, worktree, resume logic, the full close-out checklist, merge and push) is unchanged in auto mode.

## 3. Owner questions table
The plan's `## Owner questions` table keeps its existing columns: `| # | Question | Status / proposed default | Needed by |`.
- **`#`** is the question ID: an integer, the next one after the highest ID in the table. Rows may be out of order; the highest number wins.
- **Status cell.** A question is **open** if and only if its Status cell starts with `Open` (any case). Any other start (`Decided`, `Answered`, `Deferred`) is not open. Format written by an agent in auto mode:
  `Open (asked <TS>, Phase NN, auto mode). Proposed default: <default>`.
  `phx answer` (Phase 07) and Nick's hand edits replace it with `Answered <TS>: <answer>` or `Decided <TS>: <answer>`.
- **`Needed by`** lists one or more phases as `Phase NN` (comma-separated: `Phase 05, Phase 09`). Text after the phase IDs is allowed and ignored.
- `<TS>` is always `date '+%Y-%m-%d %H:%M %Z'`.

## 4. Block-with-question (spec R4)
### 4.1 When
Whenever, in auto mode and **after** the claim, the agent needs a decision from Nick: an open owner question this phase needs (point 3), an ambiguity it must not guess (point 5), a risk stop (point 6), or a failure it cannot resolve within the phase's scope (for example a check that keeps failing for a reason outside its scope). Every block records at least one question, even for a technical failure ("Tests X fail because Y; how should I proceed? Proposed default: …"). Before the claim, the agent refuses instead (§2).

### 4.2 Steps (in this order)
1. **Save the work.** In the phase worktree, commit everything on the phase branch: `wip(phase-NN): blocked, <short reason>`. Do not merge. Keep the branch and the worktree; they are how the phase resumes.
2. **Write the question.** In the main checkout (`main`), in the plan file:
   - add a row to Owner questions per §3 (or, for an existing open question this phase needs, update its Status cell to name this phase and keep it `Open`). Give a concrete proposed default;
   - set the phase's Status cell to `⛔ Blocked`;
   - add a Phase Log entry `### <TS>: Phase NN: <title> (⛔ Blocked)` whose first bullet is the Timeline with an open interval: `- **Timeline:** started <claim TS> (claim commit <hash>) · blocked <TS> to (open)`; then the Model bullet (§2 point 1); then `- **Question:** #<id>: <question>`; then what is done and what remains, and the branch/worktree to resume from.
3. **Commit to `main`, plan file only:** `git commit -m "chore(plan): phase NN blocked" -- <PREFIX>_IMPLEMENTATION_PLAN.md` (the same commit the claim protocol already requires for `⛔`). Push `main` if a remote exists (ADR-0004).
4. **Vault note:** set the phase's row to `⛔ Blocked`, update `updated:`, add a timestamped log line naming the question.
5. **End the session** with a short final message (what was done, the question, the proposed default) and the result line with `"status":"blocked"` and the question IDs (§6).

The agent does not notify Nick itself. PHX notifies, stops the run (one phase at a time, ADR-0007) and continues after `phx answer` + `phx resume`.

### 4.3 Resuming a blocked phase in auto mode
`/phase NN --auto` on a `⛔ Blocked` phase:
1. If an owner question whose `Needed by` names `NN` is still open: refuse (§6, reason `question #<id> still open`), change nothing.
2. Otherwise, in the main checkout: set the row to `🔄 In progress`, close the blocked interval in that phase's latest Timeline bullet (`blocked <TS> to <TS now>`) and commit the plan file only: `chore(plan): resume phase NN`. Update the vault note row and log.
3. In the worktree: `git merge main` (brings in the answer and the plan changes), read the answer, then continue as a normal `🔄` resume. At close-out, the final Phase Log entry's Timeline keeps every `blocked … to …` interval.

Interactive `/phase` handles a `⛔` phase as it always has; this subsection only applies in auto mode.

## 5. Risk rule (ADR-0003)
Worded once, for pasting into every `CLAUDE.md` and template:

> **Risk rule (mandatory, ADR-0003).** Sessions may run with bypassed permissions. **If an action looks high-risk, irreversible or a bad idea, stop and ask Nick instead of doing it.** In an interactive session, ask. In a hands-off session (`/phase NN --auto` or `PHX_AUTO=1`), block the phase with the question recorded (block-with-question, shared instructions §1b). Examples: deleting data you did not create, touching another project's files outside the scope your prompt names, changing system-wide config not covered by the prompt, spending money beyond a stated cap, making a repo public, publishing a release, force-pushing shared history.

## 6. Result line (spec R5)
The final assistant message of every auto-mode session ends with exactly one line:

```
PHX-RESULT: {"contract":1,"phase":"05","status":"complete","reason":"all checks passed","merged":true,"pushed":true,"question_ids":[]}
```

**Grammar.**
- The line is the last non-empty line of the final message and matches `^PHX-RESULT: (\{.*\})$`: the literal prefix `PHX-RESULT: ` (one space) followed by one JSON object on one line, no code fence around it.
- The object is compact JSON (RFC 8259), UTF-8, with these keys, all required:

| Key | Type | Meaning |
|---|---|---|
| `contract` | integer | Contract version, `1`. |
| `phase` | string or `null` | Phase ID as in the table (`"05"`, `"15a"`); `null` only for a `refused` result without a valid ID. |
| `status` | `"complete"` \| `"blocked"` \| `"refused"` | `complete`: phase finished and `✅`; `blocked`: §4 done; `refused`: a §2 precondition failed, nothing changed. |
| `reason` | string | One line, ≤ 200 characters, plain English, no secrets. |
| `merged` | boolean | The phase branch was merged into `main` in this session. Always `false` unless `complete`. |
| `pushed` | boolean | `main` was pushed after the merge (or after the `⛔` commit). `false` if there is no remote or the push failed (say why in `reason`). |
| `question_ids` | array of strings | IDs (`#` column, as strings: `["6"]`) of the questions this block depends on; `[]` unless `blocked`, and never empty when `blocked`. |

- Unknown keys may be added by later contract versions; readers ignore them.

**Reader rules (PHX).** PHX reads the `result` text of the stream-json `result` event and takes the **last** line matching the regex above. A missing line, invalid JSON, a missing key or a wrong type means "no result line": PHX logs it and relies on verification alone. The line is a hint; independent verification (spec R6) decides. Disagreement between the two is reported, never silently trusted.

## 7. Gate (spec R12, ADR-0008)
- **Column:** the phase table may have a last column headed `Gate`. Values: `auto`, `review`, `owner` (lower-case; surrounding spaces and backticks ignored). An empty cell means "not set".
- **Legacy fallback:** a phase prompt's header line may carry `· **Gate:** <value>`.
- **Precedence:** table cell, then prompt header, then the default `auto`. A value set in either place counts as "the plan says". If neither sets one and the phase's prompt mentions making a repo public or publishing a (GitHub) release, PHX treats it as `review`.
- **Meaning (enforced by PHX, not by the agent):** `auto` runs unattended; `review` runs, then PHX pauses before the next phase; `owner` is never started by PHX, which notifies Nick instead. Defence in depth: an auto-mode agent asked to run an `owner` phase refuses (§2).
- Interactive `/phase` ignores the Gate column entirely.
- Phase 00 rows carry `owner`. Release and publication phases default to `review`.

## 8. Coexistence with manual runs (ADR-0011, spec R15)
**Lock files.** PHX keeps its locks under
`LOCKDIR = ${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/phx/`:
- `LOCKDIR/phx.lock`: machine-wide, one supervisor at a time (ADR-0007);
- `LOCKDIR/<repo-name>.lock`: per repo. `<repo-name>` is the folder name of the repo's **main** checkout, found from any checkout or worktree with
  `basename "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"`.

PHX creates `LOCKDIR` with mode `0700`, holds an **exclusive `flock`** on each lock file for as long as the supervisor lives (including usage-limit waits), and writes one line of JSON into the per-repo file: `{"pid":1234,"repo":"/home/nick/Work/X","started":"<TS>","phase":"05","unit":"phx-X"}` (`phase` and `unit` may be `null`). A lock file that exists but is not locked is stale and means "not running". When acquiring, PHX retries for up to 2 seconds, because a manual check briefly takes a shared lock.

**Manual check (auto mode off, every form of `/phase`).** Before anything else the command runs:

```bash
f="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/phx/$(basename "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")").lock"; [ -e "$f" ] && ! flock -n -s "$f" true && echo "PHX-RUNNING $(cat "$f")"; printenv PHX_AUTO
```

(`flock` is util-linux, present on the reference machine; `phx` itself need not be installed.) If it prints `PHX-RUNNING`, a supervisor is live on this repo: the command tells Nick (PID, phase, start time, and `phx status` / `phx stop` if installed) and stops without claiming, resuming or changing anything. For `status` it shows the notice above the table and continues, since `status` changes nothing. The same command's last line tells the agent whether `PHX_AUTO=1` is set.

**Auto mode** skips the check: the supervisor holding the lock is the one that started the session.

**The other direction** (PHX finding a live manual Claude session in a `🔄` phase's worktree and pausing) is PHX's job (Phase 06), not the command's.

**Handover.** Manual and PHX runs may alternate at any phase boundary. A phase started by hand and left `🔄` is resumed by PHX through `/phase NN --auto` (spec R14); a phase PHX left `⛔` or `🔄` can be resumed by hand with plain `/phase NN`, after `phx stop`.

## 9. Git and GitHub authority (ADR-0004)
Worded once, for pasting into templates:

> **Git authority (standing instruction from Nick, 2026-10-26 08:44 CDT; ADR-0004):** commit, merge, push and create **private** GitHub repos without asking, at checkpoints and at close-out. Only making a repo **public**, publishing a GitHub **release**, or force-pushing shared history needs Nick's explicit confirmation (in auto mode: block-with-question). If an action looks high-risk or a bad idea, stop and ask anyway.

## 10. Versioning and detection
- A command that implements this contract contains the line `PHX-CONTRACT: 1` at the start of a line in `.claude/commands/phase.md`. PHX detects support with the multi-line regex `^PHX-CONTRACT: (\d+)\b` and refuses to run a repo whose command lacks it or carries a version it does not know (Phase 09 migrates the existing repos).
- Any change to the trigger, §2, §4, §6 or §8 that an older reader or command would misread increments the version, gets a new ADR, and updates the skill templates, the playbook and this document together. Additive result-line keys do not.

## Manual check
A procedure for Nick (or Phase 10) to confirm, with a real session, that `/phase NN --auto` blocks correctly and prints the result line. **It spends tokens; Phase 03 did not run it.**

1. Make a throwaway repo from the skill (or copy `tests/fixtures/plans/` sample plan once Phase 04 adds it) under `/home/nick/Work/phx-contract-check`, with the contract-1 `phase.md`, a remote-less `main`, and two phases: `01` (trivial: "create `hello.txt` containing `hi`") and `02`, whose prompt says "Before any task, you need Nick to choose a colour; this is owner question 1, still Open."; add Owner questions row `| 1 | Favourite colour? | Open. Proposed default: blue | Phase 02 |`.
2. Run phase 01 hands-off:
   `cd /home/nick/Work/phx-contract-check && PHX_AUTO=1 ai-provider run -p "/phase 01 --auto" --model haiku --permission-mode bypassPermissions --output-format stream-json --verbose > /tmp/claude-$(id -u)/p01.jsonl`
   Expect: row `01` is `✅ Complete` on `main`, branch and worktree gone, the Phase Log entry has the Timeline and `- **Model:** ran as …` bullets, and the last line of the `result` event's text is `PHX-RESULT: {"contract":1,"phase":"01","status":"complete",…,"merged":true,"pushed":false,"question_ids":[]}`.
   Check: `jq -r 'select(.type=="result").result' /tmp/claude-$(id -u)/p01.jsonl | tail -1`.
3. Run phase 02 the same way. Expect: no AskUserQuestion call in the stream (`grep -c AskUserQuestion` prints 0); `git log main -1 --format=%s` is `chore(plan): phase 02 blocked`; row `02` `⛔ Blocked`; question 1's Status cell names Phase 02 and is still `Open`; the Phase Log has a `blocked <TS> to (open)` Timeline; branch `phase-02-*` and worktree `../phx-contract-check-phase-02` still exist; result line `"status":"blocked"`, `"question_ids":["1"]`, `"merged":false`.
4. Run phase 02 again without answering. Expect `"status":"refused"`, reason naming question 1, and no new commit.
5. Answer: change question 1's Status cell to `Answered <TS>: green`, commit to `main`. Run phase 02 again. Expect a `chore(plan): resume phase 02` commit, the blocked interval closed, then completion as in step 2.
6. Manual-run guard: in another terminal, hold the lock `mkdir -p "$XDG_RUNTIME_DIR/phx" && flock "$XDG_RUNTIME_DIR/phx/phx-contract-check.lock" sleep 300`, then run plain `/phase status` and `/phase 01` interactively. Expect: status shows the PHX notice and the table; `/phase 01` reports the running supervisor and stops without any commit.
7. Refusals: `/phase next --auto` → `"status":"refused"`, `"phase":null`.
8. Delete `/home/nick/Work/phx-contract-check`, its worktrees and the `/tmp/claude-$(id -u)/p0*.jsonl` files.
