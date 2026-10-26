# Security Policy

## Scope
PhaseHypervisor is a **local tool** that starts AI agent sessions (Claude Code) with **bypassed permissions** on its owner's machine, inside repositories under the owner's control. It is not a service, opens no network listener and has no multi-user mode. Security reports are in scope when they show that PHX could be made to act outside that boundary: leaking secrets, running content from a repo or agent output as commands, or acting on the wrong repository.

## Reporting a vulnerability
Please do not open a public issue. Email nick@antonizick.com with a description, reproduction steps and the PHX version or commit. If the repository is hosted on GitHub, you may use its private vulnerability reporting instead. Expect an acknowledgement within a few days; this is a personal project, so there is no formal SLA.

## Security baseline (spec §4.3, S1–S5)
- **S1, bypass permissions are local-only.** PHX runs only on the owner's machine, in repos under `/home/nick/Work`, and refuses to run as root. Phase sessions are confined to their repo and worktree by the `/phase` rules, and a risk-stop rule makes an agent stop and ask (or block the phase with the question recorded) when an action looks high-risk or irreversible.
- **S2, no secret leakage.** Everything written to logs passes through a redaction step, and PHX never reads or copies `~/.config/ai-provider/openrouter.key` itself. Session transcripts (`sessions/<phase>-<n>.jsonl`) and stderr tails are redacted line by line before they are written. To log which OpenRouter model serves a phase, the runner (Phase 05) runs `ai-provider env`, whose output contains the key: PHX keeps only an allowlist of non-secret variables (base URL, model mappings, token caps), redacts those too, and drops the rest unread, so the key is never logged, stored or passed on by PHX. Phase sessions get `ai-provider`'s environment from `ai-provider` itself, not from PHX.
- **S3, untrusted content.** Repo content, plan text and agent output are treated as data. PHX parses them with strict patterns and never evaluates them or passes them unquoted to a shell. The plan parser (Phase 04) only reads `main` through `git` with argument lists, matches text with regular expressions, and never runs a command found in a plan (the test command is only extracted; Phase 06 decides how to run it).
- **S4, one writer.** A machine-wide lock plus a per-repo lock prevent two supervisors, or two phases of one repo, from running at once.
- **S5, irreversible actions stay human.** Making a repository public, publishing a release and force-pushing shared history always stop for the owner.

Secrets and personal data are never committed; `.gitignore` and (from Phase 02) a pre-commit secret scan enforce this.

## Supported versions
Pre-release. Only the latest commit on `main` is supported.
