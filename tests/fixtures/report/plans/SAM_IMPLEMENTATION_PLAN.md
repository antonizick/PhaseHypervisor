# SAM Implementation Plan

## Phases

| Phase | Phase name | Purpose | AI Model to Use | Depends on | Status | Prompt | Gate |
|---|---|---|---|---|---|---|---|
| 00 | Planning | Plan | Opus 5.5 | none | ✅ Complete | n/a | owner |
| 01 | `First` phase | Do it | Sonnet 5.5 | 00 | ✅ Complete | n/a | auto |
| 02 | Across the change | Do it | Sonnet 5.5 | 01 | ✅ Complete | n/a | auto |
| 03 | Blocked one <b>x</b> [[y]] | Do it | Sonnet 5.5 | 02 | ⛔ Blocked | n/a | auto |
| 04 | Still running | Do it | Sonnet 5.5 | 03 | 🔄 In progress | n/a | auto |
| 05 | Old format | Do it | Sonnet 5.5 | 04 | ✅ Complete | n/a | auto |
| 06 | Start not kept | Do it | Sonnet 5.5 | 05 | ✅ Complete | n/a | auto |
| 07 | Never started | Do it | Sonnet 5.5 | 06 | ⬜ Not started | n/a | auto |

## Phase Log

Newest entries at the bottom. Format: `### YYYY-MM-DD HH:MM TZ: Phase NN: <title> (<status>)`.

### 2026-10-01 09:00 CDT: Phase 00: Planning (✅ Complete)
- **Timeline:** started 2026-10-01 08:00 CDT · finished 2026-10-01 09:00 CDT

### 2026-10-01 09:30 CDT: Planning: phase 06 inserted (Planned)
- **Timeline:** started 2026-10-01 09:10 CDT · finished 2026-10-01 09:30 CDT

### 2026-10-05 12:00 CDT: Phase 01: First phase (✅ Complete)
- **Timeline:** started 2026-10-05 10:00 CDT (claim commit `abc1234`) · finished 2026-10-05 12:00 CDT · merged 2026-10-05 12:05 CDT

### 2026-11-02 09:00 CST: Phase 02: Across the change (✅ Complete)
- **Timeline:** started 2026-10-31 22:00 CDT (claim commit `abc1235`) · finished 2026-11-02 09:00 CST · merged 2026-11-02 09:01 CST

### 2026-11-03 10:00 CST: Phase 03: Blocked one (⛔ Blocked)
- **Timeline:** started 2026-11-03 09:00 CST (claim commit `abc1236`) · blocked 2026-11-03 10:00 CST to (open)
- **Question:** #1: Which one?

### 2026-11-04 10:00 CST: Phase 04: Still running (Interim)
- **Timeline:** started 2026-11-04 09:00 CST (claim commit `abc1237`)

### 2026-11-04: Phase 05: Old format (Complete)
- Built on a branch before Timeline bullets existed.

### 2026-11-05 11:00 CST: Phase 06: Start not kept (✅ Complete)
- **Timeline:** started not recorded (written before this rule) · finished 2026-11-05 11:00 CST (commit `abc1238`) · merged n/a (committed to main)

## Later notes

### 2026-12-01 09:00 CST: Phase 07: Not in the log section (✅ Complete)
- **Timeline:** started 2026-12-01 08:00 CST
