# SMP: Sample Implementation Plan

Synthetic three-phase plan for PHX tests and pilots (not a real project).

## Phases

| Phase | Phase Name | Phase Purpose | AI Model to Use | Depends on | Status | Prompt to Initiate This Phase | Gate |
|---|---|---|---|---|---|---|---|
| 00 | Planning | Write this plan | Opus 5.5 | none | ✅ Complete | n/a (planning session) | owner |
| 01 | Hello file | Create `hello.txt` containing `hi` | Haiku 5.5 | 00 | ⬜ Not started | [SMP_phase-01-hello.md](prompts/SMP_phase-01-hello.md) | auto |
| 01a | Inserted phase | Append `there` to `hello.txt` | Haiku 5.5 (`claude-haiku-5-5`) | 01 | ⬜ Not started | [SMP_phase-01a-inserted.md](prompts/SMP_phase-01a-inserted.md) | |
| 02 | Colour file | Write Nick's favourite colour to `colour.txt` | Sonnet 5.5 | 01a | ⬜ Not started | [SMP_phase-02-colour.md](prompts/SMP_phase-02-colour.md) | review |

## Owner questions
| # | Question | Status / proposed default | Needed by |
|---|---|---|---|
| 1 | Favourite colour? | Open. Proposed default: blue | Phase 02 |

## Phase Log
Newest entries at the bottom.
