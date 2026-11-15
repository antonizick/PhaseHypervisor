### {{N}}. Amendments ({{VERSION}}, {{TIMESTAMP}})

These amendments supersede conflicting text in the earlier sections. Each amendment that records a decision has an entry in `docs/{{PREFIX}}_DECISIONS.md`.

#### {{N}}.1 Decisions confirmed by the project owner
| ID | Topic | Decision |
|---|---|---|
| A1 | {{TOPIC}} | {{DECISION_AND_WHY}} |

#### {{N}}.2 Technical refinements
- **R1 {{TITLE}}.** {{REFINEMENT; the phase that verifies it}}

#### {{N}}.3 Security and privacy baseline (applies to every phase)
- **S1 {{CONTROL}}.** {{DETAIL}}

#### {{N}}.4 Repository and publication requirement (mandatory)
The project lives in a single Git repository that is ready to publish on GitHub. It must contain and keep accurate: README, LICENSE, NOTICE, THIRD_PARTY_NOTICES, SECURITY, CONTRIBUTING, CODE_OF_CONDUCT, CHANGELOG, .gitignore, .dockerignore, .editorconfig, .github/ (CI, templates, Dependabot), and docs/. Private data never gets committed; `.gitignore` and a pre-commit secret scan enforce this.

#### {{N}}.5 Owner questions (status as of {{TIMESTAMP}})
1. **{{Open|Decided|Deferred to Phase NN}}.** {{QUESTION_AND_ANSWER_OR_PROPOSED_DEFAULT}}
{{#BRAINSTORM}}
#### {{N}}.6 Brainstorm trace
Where each idea in `{{BRAINSTORM_FILES}}` went. Disposition: **Adopted** (with the ADR, amendment or phase that carries it), **Deferred** (with its owner question) or **Dropped** (with the reason). A phase that fulfils or changes a row updates it at close-out; `/phase-add` appends rows for new brainstorm entries. Covered through: {{BRAINSTORM_COVERED_THROUGH}}.

| # | Entry (stamp: label) | Idea | Disposition | Where |
|---|---|---|---|---|
| B1 | {{ENTRY_STAMP}}: {{ENTRY_LABEL}} | {{IDEA_IN_ONE_LINE}} | {{Adopted|Deferred|Dropped}} | {{ADR_AMENDMENT_PHASE_QUESTION_OR_REASON}} |
{{/BRAINSTORM}}
