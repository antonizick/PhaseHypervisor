# Plan fixtures

Read-only copies of real phased-project plans, taken from each repo's `main` at 2026-10-26 09:17 CDT by Phase 04 and refreshed at 2026-10-26 17:12 CDT by Phase 09 (after the hands-off migration; `Contract: 1`, explicit Gate column) and checked for secrets (none found). Only the files `phx.plan` reads are copied: the plan, `.claude/commands/phase.md`, the shared instructions and the release prompt (for Gate inference). Tests turn each folder into a throwaway git repo in `tmp_path`. Do not edit them to make a test pass; write a synthetic plan in the test instead.

| Folder | Source repo | Commit |
|---|---|---|
| `mm3/` | `MeetingMaster3` | `fd0f737` |
| `cl/` | `chessloopDeploy` | `dec549e` |
| `occ/` | `OCC_OmarchyControlCenter` | `900d543` |
| `ytpl2/` | `YTPL2` | `60132bb` |
| `sample/` | synthetic | three phases (`01`, `01a`, `02`), Gate column, contract 1; for Phase 10 pilots |
