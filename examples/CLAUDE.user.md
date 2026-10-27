<!--
  Paste the parts you want into your global ~/.claude/CLAUDE.md (create the file if it does not exist).
  Everything here is optional. The phased-project skill and /phx work without any of it;
  each part says what it changes. Replace the <…> placeholders or delete the lines you don't need.
  A line whose value is still <…> is treated as unset.
-->

## Phased-project settings
<!-- Read by the phased-project skill and the /phx command. Every line is optional. -->
- Owner: <your first name; agents say "tell <name>" instead of "tell the owner">
- Work root: <absolute folder where your project repos live, e.g. ~/Work; used to check prefixes and by /phx <name>>
- Vault root: <absolute path of your notes vault (Obsidian or any Markdown folder); without it, no vault note is kept>
- Vault projects folder: <folder inside the vault for project notes, e.g. Projects>
- Method note: <absolute path of your own copy or notes on the method; the vault note links to it>
- OS modifications log: <folder where you record changes to your machine; phases that change the host write there>
- Reference implementation: <a repo you bootstrapped with this method, read by the skill when in doubt>
- Project aliases: <short names for /phx, e.g. ABC = abc-service, WEB = website>

## Standing rules for phased projects
<!-- The method's templates already write the first three into every project's CLAUDE.md.
     Putting them here as well makes them apply in planning sessions and outside phased repos. -->
- **Timestamps.** Wherever a document records when something happened (logs, decisions, "last updated"), write `YYYY-MM-DD HH:MM TZ` taken from `date '+%Y-%m-%d %H:%M %Z'` at that moment. Never a bare date, never guessed.
- **Project prefix.** Each project has a 2–4 character upper-case code. Its own documents are named `<PREFIX>_<NAME>` (`ABC_IMPLEMENTATION_PLAN.md`) so they can be told apart without their path. Conventional files (`README.md`, `CLAUDE.md`, `LICENSE`, `CHANGELOG.md`…) keep their names.
- **Git authority.** Agents may commit, merge and push, and create **private** GitHub repos, without asking. Making a repo public, publishing a release, or force-pushing shared history needs my explicit confirmation. If an action looks high-risk or a bad idea, stop and ask anyway.
  <!-- Optional but needed for hands-off runs: without it, a phase that must ask before merging cannot
       finish unattended. Delete this rule if you want to approve every push; then tell /phased-project so,
       and it writes your stricter rule into each project instead. -->
- **Model fit check (optional).** At the start of a session, after my first request, say in 2–3 sentences whether the current model suits the task and, if not, give the `/model` command for a better one. Phase sessions use `/phase`'s own model check instead.
