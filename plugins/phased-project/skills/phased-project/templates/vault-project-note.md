---
tags: [project, {{TAG}}]
status: active
repo: {{REPO_DIR}}
created: {{TIMESTAMP}}
updated: {{TIMESTAMP}}
---
# {{PREFIX}}: {{PROJECT_NAME}} Implementation Plan

Tracking note for the {{PROJECT_NAME}} build. The **source of truth is in the repo**; this note is the vault-side summary and log. Agents update it at the end of every phase. Method: {{METHOD_LINK}}.

- Repo: `{{REPO_DIR}}`
- Plan and status table: `{{PREFIX}}_IMPLEMENTATION_PLAN.md`
- Canonical spec: `docs/{{PREFIX}}_SPECIFICATION.md` (from {{SOURCE_NOTE_WIKILINKS}})

## How to run the next phase
Open Claude Code in the repo directory and type `/phase` (next eligible phase), `/phase NN` (a specific phase) or `/phase status` (progress only).

## Decisions ({{TIMESTAMP}})
{{DECISION_BULLETS}}

## Phase status
| # | Phase | Model | Status |
|---|---|---|---|
{{STATUS_ROWS_WITH_ICONS}}

## Open questions for {{OWNER}}
{{QUESTIONS}}

## Log
Every line starts with a timestamp (`YYYY-MM-DD HH:MM TZ`); update `updated:` in the frontmatter whenever you edit this note.
- **{{TIMESTAMP}}:** Phase 00 complete. {{SUMMARY}}. **Undo:** delete the repo contents and this note.
