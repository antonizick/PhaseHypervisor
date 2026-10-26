# YTPL2: YouTube Playlist Manager Implementation Plan

**Spec:** [`docs/YTPL2_SPECIFICATION.md`](docs/YTPL2_SPECIFICATION.md). **Decisions:** [`docs/YTPL2_DECISIONS.md`](docs/YTPL2_DECISIONS.md). **Agent rules:** [`CLAUDE.md`](CLAUDE.md). **Shared phase instructions:** [`prompts/YTPL2_shared-instructions.md`](prompts/YTPL2_shared-instructions.md)
**Last updated:** 2026-10-25 23:33 CDT (Phase 02 complete)

> ⚠️ **Mandatory:** every agent that works on this project keeps this file accurate. **Before doing any other work, set your phase to `🔄 In progress` and commit that change to `main`** (claim protocol: `prompts/YTPL2_shared-instructions.md` §1a). Other agents read this table from `main`. At the end, set it to `✅ Complete` or `⛔ Blocked` and add a Phase Log entry. See `CLAUDE.md`.

## How to run a phase
Open Claude Code in `/home/nick/Work/YTPL2` and type one of:
- `/phase`: run the next eligible phase. It checks dependencies, tells you if you're on the wrong model, resumes an `In progress` phase, and asks about any open questions it needs.
- `/phase NN`: run a specific phase.
- `/phase status`: show progress and what's next, without doing any work.
- `/phase-add [after NN] <request>`: plan a new lettered phase (`09a`) later; it never builds.

Review the agent's close-out summary, then merge the phase branch when satisfied.

Each phase is claimed by a `chore(plan): start phase NN` commit on `main` and runs in its own worktree, `../YTPL2-phase-NN`, so parallel sessions never share a checkout. `/phase status` flags any branch or worktree whose row is not `🔄 In progress`.

**Parallelism:**
- After Phase 03, phases **04** and **05** can run in parallel. 04 owns `src/ytpl2/auth/`, `src/ytpl2/youtube/google_client.py`, `docs/setup/` and the live tests; 05 owns `src/ytpl2/store/` and `src/ytpl2/jobs/`.
- After Phase 07, **08** and **09** can run in parallel. 08 owns the playlist-view destructive flows and `frontend/src/features/{jobs,export}`; 09 owns `frontend/src/features/{search,player}` and the search/add API routes. Both may touch `frontend/src/App.tsx` routing and the shared toolbar, so merge one first and rebase the other.
- **11** (OCC integration, install, OSMods) can start once 08 is merged and run beside 09 or 10.
- 12 waits for 10 and 11.

**Status values:** ⬜ Not started · 🔄 In progress · ⛔ Blocked · ✅ Complete. Always write the icon **and** the word.

## Phases

| Phase | Phase Name | Phase Purpose | AI Model to Use | Depends on | Status | Prompt to Initiate This Phase |
|---|---|---|---|---|---|---|
| 00 | Planning & spec refinement | Review source docs, resolve decisions, write the spec, plan and prompts | Opus 5.5 (`claude-opus-5-5`) | none | ✅ Complete | n/a (planning session) |
| 01 | Repository foundation & governance | MIT licence, README, SECURITY, CONTRIBUTING, CoC, CHANGELOG, notices, ignore files (secrets!), .github/, gitleaks pre-commit, docs skeleton | Sonnet 5.5 (`claude-sonnet-5-5`) | 00 | ✅ Complete | [`prompts/YTPL2_phase-01-repo-foundation.md`](prompts/YTPL2_phase-01-repo-foundation.md) |
| 02 | Python + React scaffold, toolchain & CI | uv + CPython 3.13, package layout, Typer CLI skeleton, FastAPI hello + `/healthz`, Vite React-TS skeleton built into the package, Makefile, lint/type/test/audit gates, CI | Sonnet 5.5 (`claude-sonnet-5-5`) | 01 | ✅ Complete | [`prompts/YTPL2_phase-02-scaffold.md`](prompts/YTPL2_phase-02-scaffold.md) |
| 03 | Domain core, exports & FakeYouTube | Models, URL derivation, export formatters (CSV/MD/text, columns, escaping), quota maths (PT reset), job cost planner, `YouTubeClient` protocol, FakeYouTube + demo seed data, config & XDG paths | Opus 5.5 (`claude-opus-5-5`) | 02 | ⬜ Not started | [`prompts/YTPL2_phase-03-domain-core.md`](prompts/YTPL2_phase-03-domain-core.md) |
| 04 | OAuth & real YouTube client | Google Cloud setup guide, OAuth (PKCE, loopback callback, `ytpl2 auth`), 0600 token store, metered `GoogleYouTube` client, error mapping, pagination; verify ADR-0009/0010/0011 and Appendix A live | Opus 5.5 (`claude-opus-5-5`) | 03 | ⬜ Not started | [`prompts/YTPL2_phase-04-oauth-client.md`](prompts/YTPL2_phase-04-oauth-client.md) |
| 05 | Cache, quota ledger & job engine | SQLite store + migrations, playlist/item/enrichment cache with TTLs, persistent quota ledger, job engine (sequential, cancel, pause on quota/auth, resume after crash), auto-snapshots | Opus 5.5 (`claude-opus-5-5`) | 03 | ⬜ Not started | [`prompts/YTPL2_phase-05-cache-jobs.md`](prompts/YTPL2_phase-05-cache-jobs.md) |
| 06 | HTTP API, security & CLI lifecycle | FastAPI JSON API, Host/Origin/token/CSP middleware, OAuth routes, theme endpoint, `serve/start/stop/status/open/logout/doctor`, lock + state file, logging with redaction, `--demo` | Opus 5.5 (`claude-opus-5-5`) | 04, 05 | ⬜ Not started | [`prompts/YTPL2_phase-06-api-lifecycle.md`](prompts/YTPL2_phase-06-api-lifecycle.md) |
| 07 | Tron UI shell & playlist browser | Theme-driven Tron look, app shell, quota badge, auth banner, playlist list table (filter/sort/multi-select), playlist detail table (virtualized, numbered, thumbnails, streaming load), selection model, keyboard map | Opus 5.5 (`claude-opus-5-5`) | 06 | ⬜ Not started | [`prompts/YTPL2_phase-07-ui-browser.md`](prompts/YTPL2_phase-07-ui-browser.md) |
| 08 | Delete flows, jobs UI & export | Confirmation modals (cost, typed confirm, whole-playlist suggestion), job progress/cancel/resume, snapshot notices, export modal (columns, presets, formats, copy), export-then-delete workflow | Opus 5.5 (`claude-opus-5-5`) | 07 | ⬜ Not started | [`prompts/YTPL2_phase-08-delete-export.md`](prompts/YTPL2_phase-08-delete-export.md) |
| 09 | Search, add & preview player | Search view (cost shown, cached), results table + multi-select, add to existing/new playlist via jobs, IFrame preview pane for search results and playlist items; verify ADR-0012 | Opus 5.5 (`claude-opus-5-5`) | 07 | ⬜ Not started | [`prompts/YTPL2_phase-09-search-player.md`](prompts/YTPL2_phase-09-search-player.md) |
| 10 | Power features & polish | Duplicate detection (within/across cached playlists), "select unavailable", column filters, export-all summary, shortcut overlay, empty/error states, UI polish from real use | Sonnet 5.5 (`claude-sonnet-5-5`) | 08, 09 | ⬜ Not started | [`prompts/YTPL2_phase-10-power-features.md`](prompts/YTPL2_phase-10-power-features.md) |
| 11 | Install, OCC integration & OSMods | `make install` (`uv tool install` → `~/.local/bin/ytpl2`), uninstall, OCC `[[service]]` card + `occ check`, web-app window, user guide, OSMods write-up + README | Sonnet 5.5 (`claude-sonnet-5-5`) | 08 | ⬜ Not started | [`prompts/YTPL2_phase-11-install-occ.md`](prompts/YTPL2_phase-11-install-occ.md) |
| 12 | Hardening, security review & QA | Threat model, scanners, fuzz/property tests of exports and parsers, measured performance vs R20, accessibility audit, licence audit, live end-to-end on test playlists, close all follow-ups | Opus 5.5 (`claude-opus-5-5`) | 10, 11 | ⬜ Not started | [`prompts/YTPL2_phase-12-hardening.md`](prompts/YTPL2_phase-12-hardening.md) |
| 13 | Release & publication | v1.0.0 changelog and tag, final report with timeline, GitHub publication **only with Nick's in-session confirmation** | Sonnet 5.5 (`claude-sonnet-5-5`) | 12 | ⬜ Not started | [`prompts/YTPL2_phase-13-release.md`](prompts/YTPL2_phase-13-release.md) |

### Model rationale
- **Opus 5.5** (`/model claude-opus-5-5`) where a mistake is subtle, costly or irreversible:
  - the domain core, whose export escaping, quota maths across DST and the fake's fidelity everything later relies on (03);
  - OAuth and the metered API client, including the verification of Google's facts (04);
  - the job engine, whose deletes are irreversible and whose pause/resume/crash states form a state machine (05);
  - the security middleware and process lifecycle (06);
  - the complex interactive tables, with range selection, virtualization and keyboard focus (07);
  - the destructive flows, where a UI bug deletes the wrong videos (08);
  - the player integration with its CSP and embed edge cases (09);
  - the security review (12).
- **Sonnet 5.5** (`/model claude-sonnet-5-5`) for well-specified work: governance files (01), scaffolding and CI (02), polish features on an existing base (10), install scripts, OCC config and docs, which follow the existing OCC guide (11), and release packaging (13).

### Dependency graph
```
                                                   ┌─► 11 ───────┐
00 ─► 01 ─► 02 ─► 03 ─┬─► 04 ─┐                    │             ▼
                      │       ├─► 06 ─► 07 ─┬─► 08 ┴──► 10 ───► 12 ─► 13
                      └─► 05 ─┘             │          ▲
                                            └─► 09 ────┘
Parallel windows: {04, 05} after 03;  {08, 09} after 07;  11 after 08, beside 09/10.
```

### Definition of done (checked in the final phase)
- [ ] `ytpl2 start` / `stop` / `status` work; `ytpl2 serve` runs in the foreground; only one instance can run; binds 127.0.0.1:8790 only.
- [ ] First run: **Connect YouTube account** completes OAuth in the browser; the token is stored 0600; an expired or revoked token shows **Reconnect** and pauses jobs instead of failing them.
- [ ] All ~150 playlists load lazily (no items fetched), shown in a filterable, sortable table with title, privacy, item count, ID and date; system playlists are marked read-only.
- [ ] Opening a 400-item playlist shows the first page immediately and the rest streams in. A cached reopen costs 0 units and renders in < 500 ms (measured).
- [ ] Checkbox, Shift-range, Ctrl-click, select-all-in-filter and keyboard selection all work over 400 rows.
- [ ] Bulk delete of dozens of videos shows count + estimated units, requires typed confirmation above 25, writes a snapshot first, shows progress, can be cancelled, and pauses cleanly on quota exhaustion.
- [ ] Delete one or several whole playlists with typed confirmation and a snapshot; the export-then-delete workflow takes ≤ 4 clicks plus typing.
- [ ] Export to CSV, Markdown and plain text with a column picker (URL first-class), presets and copy to clipboard; output verified to open cleanly in a spreadsheet and render in Obsidian.
- [ ] Search shows its 100-unit cost, results are cached, multi-select adds to an existing or new playlist through a job; preview plays in the side pane, and embedding-disabled videos fall back to **Open on YouTube**.
- [ ] The quota badge shows estimated units used today (resets at midnight PT) with 80 %/95 % warnings; every call is in the ledger.
- [ ] Duplicate detection, "select unavailable" and the shortcut overlay work.
- [ ] Tron look follows the active Omarchy theme; contrast passes; keyboard-navigable; screen-reader labels on tables and buttons.
- [ ] `ytpl2 serve --demo` exercises every feature with zero quota and no real token.
- [ ] OCC shows a YTPL2 card (Start/Stop/Open/Logs, Busy during a job); `occ check` is clean.
- [ ] Security baseline S1-S12 verified; threat model written; scanners clean; no secrets or personal data in the repo or its history.
- [ ] OSMods README and write-up current; vault note current; repository GitHub-ready.

## Owner questions
| # | Question | Status / proposed default | Needed by |
|---|---|---|---|
| 1 | Project prefix | **Decided** 2026-10-25 22:26 CDT: `YTPL2` (ADR-0001) | 00 |
| 2 | Frontend stack | **Decided** 2026-10-25 22:26 CDT: React + TS + Vite + TanStack (ADR-0002) | 02 |
| 3 | Snapshot before deletes | **Decided** 2026-10-25 22:26 CDT: always, cannot be skipped (ADR-0003) | 05 |
| 4 | Licence and publication | **Decided** 2026-10-25 22:26 CDT: MIT; publish only in Phase 13 with confirmation (ADR-0004) | 01, 13 |
| 5 | Google Cloud project + Desktop OAuth client; `client_secret.json` placed at `~/.config/ytpl2/` | **Open (Nick's action).** Phase 04 writes `docs/setup/google-cloud.md`, then waits for the file | 04 |
| 6 | Consent-screen publishing status: Testing (weekly reconnect?) vs In production unverified | **Open.** Phase 04 verifies R7 and recommends; default Testing until then | 04 |
| 7 | Daily quota limit | **Proposed default:** 10 000 units unless the Cloud project shows otherwise | 04 |
| 8 | Port | **Proposed default:** 127.0.0.1:8790, no fallback (ADR-0013) | 06 |
| 9 | Typed-confirmation threshold | **Proposed default:** any playlist delete, and > 25 videos | 08 |
| 10 | Default export columns | **Proposed default:** position, title, URL (`watch?v=`), channel, duration | 08 |
| 11 | Cache TTLs | **Proposed default:** playlists 1 h, items 24 h, enrichment 7 d, search 1 h | 05 |
| 12 | Public or private GitHub repo (or not at all) | **Open** | 13 |
| 13 | OCC card + Omarchy web-app window | **Proposed default:** yes, both (R25) | 11 |
| 14 | Live-test quota budget on throwaway `YTPL2-TEST-` playlists | **Open. Proposed:** yes, ≤ 1 000 units per run (R22) | 04 |

## Phase Log
Newest entries at the bottom. Format: `### YYYY-MM-DD HH:MM TZ: Phase NN: <title> (<status>)` (timestamp from `date '+%Y-%m-%d %H:%M %Z'`, never a bare date). **The first bullet is always the Timeline:** `- **Timeline:** started <TS> (claim commit <hash>) · finished <TS> · merged <TS | not merged yet>` (add ` · blocked <TS> to <TS>` per `⛔` interval; *started* is the claim commit's time). Then bullets: built, deviations, follow-ups, tests.

### 2026-10-25 22:38 CDT: Phase 00: Planning & spec refinement (✅ Complete)
- **Timeline:** started 2026-10-25 22:22 CDT · finished 2026-10-25 22:38 CDT
- **Sources:** the pasted YTPL2 planning document (Grok conversation) and its vault note `04 Resources/YT Playlist Manager Brainstorming.md` (which also holds the original feature list and Nick's answers); the OCC repo and its adding-a-service guide; OSMods `OCC Omarchy Control Center.md`; the machine (toolchain, ports, theme).
- **Owner decisions** (one question round): prefix `YTPL2` (owner override of the 2-4 character rule), React+TS+Vite+TanStack, always auto-snapshot before deletes, MIT with publication later (ADR-0001…0004).
- **Refinements** (spec §13.2 R1-R26):
  - reconciled "no systemd" with OCC (`serve` vs `start`, ADR-0006);
  - fixed port 8790 (ADR-0013);
  - uv CPython 3.13, because host Python is 3.14 (ADR-0005);
  - SQLite store and server-side job engine (ADR-0007/0008);
  - quota ledger with PT reset; lazy and streamed loading;
  - `videos.list` enrichment for duration;
  - typed confirmations and the whole-playlist suggestion;
  - unavailable-video handling; export escaping and CSV-injection guard;
  - FakeYouTube + `--demo` (ADR-0014);
  - live-test safety on `YTPL2-TEST-` playlists only;
  - OCC card design.
- **Unverified facts left for phases:** OAuth scope and Testing-mode refresh-token expiry (ADR-0009), quota costs (Appendix A, ADR-0010), special-playlist access (ADR-0011), embed referrer/nocookie behaviour (ADR-0012). The planning conversation's claim that "search and uploads have separate buckets" was not carried into the spec.
- **Security baseline:** S1-S12 added.
- **Files:**
  - `docs/YTPL2_SPECIFICATION.md`, `docs/YTPL2_DECISIONS.md` (14 ADRs);
  - `CLAUDE.md`, this plan, `prompts/YTPL2_shared-instructions.md`, 13 phase prompts, `prompts/YTPL2_change-request-template.md`;
  - `.claude/commands/phase.md` and `phase-add.md`;
  - vault note `02 Projects/YTPL2 Implementation Plan.md`.
- **Repo:** `git init -b main`; no commit (awaiting Nick).

### 2026-10-25 23:15 CDT: Phase 01: Repository foundation & governance (✅ Complete)
- **Timeline:** started 2026-10-25 23:13 CDT (claim commit 08f97c5) · finished 2026-10-25 23:15 CDT · merged 2026-10-25 23:28 CDT (merge commit 2e93dc8)
- **Preliminary:** `main` had no commits, so the claim protocol could not run. With Nick's OK, baseline commit `a7f2fee` ("phase 00 planning baseline") was made first, then the claim commit.
- **Built:**
  - `LICENSE` (MIT), `NOTICE`, `README`, `SECURITY`, `CONTRIBUTING`, `CODE_OF_CONDUCT` (Contributor Covenant 2.1), `CHANGELOG`, `THIRD_PARTY_NOTICES`;
  - `.gitignore`, `.dockerignore`, `.editorconfig`;
  - `.pre-commit-config.yaml` (gitleaks v8.30.1, pre-commit-hooks v6.0.0, revs read from the GitHub releases) and `.gitleaks.toml` (GOCSPX secrets, `1//` refresh tokens, `client_secret`/`refresh_token` JSON fields);
  - `.github/` (CI with placeholder jobs `python`, `frontend` and a working `gitleaks` job; bug/feature templates; PR template; Dependabot for uv, npm in `/frontend`, github-actions);
  - docs skeleton (`YTPL2_ARCHITECTURE.md`, `user-guide/`, `setup/`, `images/.gitkeep`);
  - ADR-0015.
- **Deviations:** the prompt says copyright "Nick Antoncic"; OCC's LICENSE says **Nick Antonizick**, which is used. The CI `gitleaks` job runs `uvx pre-commit run --all-files` rather than gitleaks-action, so local and CI use one config.
- **Follow-ups:**
  - Phase 02 fills the `python` and `frontend` CI jobs and adds `make check`; it should also pin the CI action tags (`checkout@v7`, `setup-uv@v10` are major tags).
  - `pre-commit install` wrote the hook into the shared `.git/hooks`, so it also guards the main checkout.
  - Dependabot's `uv` ecosystem needs `pyproject.toml`/`uv.lock` (Phase 02).
  - `CODE_OF_CONDUCT.md` is copied from OCC; the contact is Nick's email.
- **Tests:**
  - `uvx pre-commit run --all-files`: all three hooks pass.
  - A force-added fake `client_secret.json` and a fake refresh token in a tracked-path file were both blocked by gitleaks (rules `google-oauth-client-secret`, `-refresh-token`, `-client-secret-file`); test files removed, nothing committed.
  - `git check-ignore -v` confirmed `client_secret.json`, `token.json`, `ytpl2.db`, `ytpl2.db-wal`, `backups/x.csv`, `exports/a.md`, `x.csv`, `config.toml` and `.env` are ignored, and `tests/fixtures/*.csv` and `config/config.example.toml` are not.
  - The `.github` YAML and `.pre-commit-config.yaml` parse with PyYAML (no actionlint installed).
- **Live quota spent:** 0 units. No OSMods change (no host system files modified beyond the repo's git hook).

### 2026-10-25 23:33 CDT: Phase 02: Python + React scaffold, toolchain & CI (✅ Complete)
- **Timeline:** started 2026-10-25 23:29 CDT (claim commit a37572b) · finished 2026-10-25 23:33 CDT · merged 2026-10-26 04:22 CDT
- **Built:**
  - `pyproject.toml` (hatchling, `requires-python >=3.13,<3.14`, `.python-version` 3.13), `uv.lock`; package `src/ytpl2/` with Typer CLI (`serve` and `version` work; `start stop status open auth logout doctor` print "not implemented yet (Phase NN)" and exit 2), `config.py`, `paths.py`, empty `domain/ youtube/ auth/ store/ jobs/ server/` with import rules in their docstrings.
  - `server/app.py` `create_app(settings)`: `/healthz`, `/` and `/assets/` from `web/dist`, 503 plain-text notice if not built. Bound to 127.0.0.1:8790 only (`ss -ltn` confirmed).
  - `frontend/`: Vite 8.3.5, React 19.3.1, TypeScript 6.0.3 (strict), TanStack Table 9.3.1 and Virtual 3.14.22, ESLint 10.13.0 flat config, Prettier 3.9.10, Vitest 5.0.5 + Testing Library + jsdom; builds into `src/ytpl2/web/dist`; dev proxy for `/api` and `/healthz`; `.node-version` 26.8.1.
  - `Makefile` (`sync build dev check check-py check-fe e2e clean`); CI with python, frontend and gitleaks jobs, actions pinned to exact tags (`checkout v7.0.1`, `setup-uv v10.3.2`, `setup-node v7.1.0`).
  - Python deps: fastapi 0.162.0, uvicorn 0.54.0, typer 0.27.3, google-api-python-client 2.201.0, google-auth 2.62.0, google-auth-oauthlib 1.5.0; dev: pytest 9.1.1, pytest-cov, mypy 2.4.0, ruff 0.17.2, pip-audit 2.10.1, httpx 0.28.1. All licences MIT/BSD/Apache-2.0 (listed in THIRD_PARTY_NOTICES). Everything works on CPython 3.13.16, so ADR-0005 stands.
- **Deviations:** Vite's template ships oxlint; replaced by ESLint flat config as the prompt asks. Added `format:check` (Prettier) to the frontend gate. `.mise.toml` not needed (`frontend/.node-version` used by CI). No ADR needed (no Python-version or backend change).
- **Follow-ups:**
  - Starlette's `TestClient` warns that `httpx` is deprecated in favour of `httpx2`; check the replacement (and its licence) when Phase 03 touches tests.
  - `pip-audit` skips the local `ytpl2` package ("not on PyPI"); harmless.
  - `make e2e` is a placeholder until Phase 07; `make dev` is untested with a browser.
  - The CI workflow has not run on GitHub (no remote); YAML parses with PyYAML.
- **Tests:** `make check` green: 13 pytest tests (unit healthz/CLI, integration `serve` smoke) and 2 Vitest tests; ruff, mypy `--strict`, pip-audit, eslint, tsc, prettier, npm audit clean. `make build` produced `ytpl2-0.0.0-py3-none-any.whl` containing `ytpl2/web/dist/index.html`; installed into a fresh venv, `ytpl2 serve` returned `{"status":"ok","version":"0.0.0","auth":"required","demo":false}` on `/healthz` and the built page on `/`.
- **Live quota spent:** 0 units. No OSMods change (no host files modified).
