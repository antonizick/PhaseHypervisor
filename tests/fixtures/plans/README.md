# Plan fixtures

Read-only copies of real phased-project plans, taken from each repo's `main` at 2026-10-26 09:17 CDT by Phase 04 and checked for secrets (none found). Only the files `phx.plan` reads are copied: the plan, `.claude/commands/phase.md`, the shared instructions and the release prompt (for Gate inference). Tests turn each folder into a throwaway git repo in `tmp_path`. Do not edit them to make a test pass; write a synthetic plan in the test instead.

| Folder | Source repo | Commit |
|---|---|---|
| `mm3/` | `MeetingMaster3` | `14cfd38` |
| `cl/` | `chessloopDeploy` | `7b55d1f` |
| `occ/` | `OCC_OmarchyControlCenter` | `cb38b94` |
| `ytpl2/` | `YTPL2` | `3516d8c` |
| `sample/` | synthetic | three phases (`01`, `01a`, `02`), Gate column, contract 1; for Phase 10 pilots |
