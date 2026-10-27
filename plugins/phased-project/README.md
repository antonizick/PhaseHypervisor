# phased-project (Claude Code plugin)

The phased-project method for Claude Code, packaged from the [PhaseHypervisor](https://github.com/antonizick/PhaseHypervisor) repo.

- **Skill `phased-project`**: turns a plan, spec or idea document into a phased project: a spec with amendments, an ADR log, `<PREFIX>_IMPLEMENTATION_PLAN.md` with a status table, one prompt per phase, agent rules in `CLAUDE.md`, and the per-repo `/phase` and `/phase-add` commands.
- **Command `phx`**: drives PhaseHypervisor (`phx`), the optional supervisor that runs the remaining phases hands-off.

As a plugin, the names are namespaced: type `/phased-project:phased-project` and `/phased-project:phx`. The manual-copy install keeps the short names `/phased-project` and `/phx`. The commands each project gets (`/phase`, `/phase-add`) are files in that project and are never namespaced.

Start here: [Getting started](https://github.com/antonizick/PhaseHypervisor/blob/main/docs/PHX_GETTING_STARTED.md). Licence: MIT.
