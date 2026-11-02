"""Keep a project's generated timeline current from the supervisor (ADR-0030).

The generator (``scripts/phase_timeline.py``) is deterministic, but until Phase 12e only an
agent following prose refreshed it, and only at close-out, block and resume, so a running phase
never appeared. ``refresh`` runs it from ``phx`` itself, on ``main``, in its own
``docs(plan): refresh timeline`` commit. It is best effort: every refusal or failure returns a
reason and never raises, so a timeline problem cannot stop a build.
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from phx.vault import note_path

SCRIPT = Path("scripts") / "phase_timeline.py"
SUBJECT = "docs(plan): refresh timeline"
GROWTH_S = 1800.0  # an open bar is redrawn at least this often while a phase runs
TIMEOUT_S = 60


@dataclass(frozen=True)
class Refresh:
    committed: bool
    reason: str


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args), cwd=repo, capture_output=True, text=True, check=False, timeout=TIMEOUT_S
    )


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return _run(repo, "git", *args)


def refresh(repo: Path, *, grow: bool = False) -> Refresh:
    """Regenerate the timeline when stale (or, with ``grow``, to extend an open bar).

    Only on a clean ``main`` checkout with no git lock, so it never collides with an agent
    that is committing or merging there.
    """
    try:
        return _refresh(repo, grow)
    except (OSError, subprocess.SubprocessError) as exc:
        return Refresh(False, f"error: {exc}")


def _refresh(repo: Path, grow: bool) -> Refresh:
    if not (repo / SCRIPT).is_file():
        return Refresh(False, "no scripts/phase_timeline.py")
    git_dir = _git(repo, "rev-parse", "--git-dir")
    if git_dir.returncode != 0:
        return Refresh(False, "not a git repository")
    if (repo / git_dir.stdout.strip() / "index.lock").exists():
        return Refresh(False, "git index is locked")
    head = _git(repo, "symbolic-ref", "--short", "-q", "HEAD")
    if head.stdout.strip() != "main":
        return Refresh(False, "main checkout is not on main")
    if _git(repo, "status", "--porcelain").stdout.strip():
        return Refresh(False, "main checkout has uncommitted changes")
    vault = note_path(repo)
    extra = ["--vault-note", str(vault)] if vault is not None and vault.is_file() else []
    script = [sys.executable, str(SCRIPT), "--repo", "."]
    check = _run(repo, *script, "--check", *extra)
    if check.returncode == 0 and not grow:
        return Refresh(False, "up to date")
    if check.returncode not in (0, 1):
        return Refresh(False, f"generator failed: {check.stderr.strip()[:200]}")
    write = _run(repo, *script, "--write", "--as-of", time.strftime("%Y-%m-%d %H:%M %Z"), *extra)
    if write.returncode == 2 and "--as-of" in write.stderr:  # a project's older script copy
        write = _run(repo, *script, "--write", *extra)
    if write.returncode != 0:
        return Refresh(False, f"generator failed: {write.stderr.strip()[:200]}")
    changed = [
        line.split("wrote ", 1)[1].strip()
        for line in write.stdout.splitlines()
        if line.startswith("phase_timeline: wrote ")
    ]
    tracked = [p for p in changed if (repo / p).is_file() and not Path(p).is_absolute()]
    if not tracked:
        return Refresh(False, "vault note refreshed" if changed else "up to date")
    if _git(repo, "add", "--", *tracked).returncode != 0:
        return Refresh(False, "git add failed")
    commit = _git(repo, "commit", "-q", "-m", SUBJECT, "--", *tracked)
    if commit.returncode != 0:
        _git(repo, "checkout", "-q", "HEAD", "--", *tracked)  # generated: leave main clean
        return Refresh(False, f"git commit failed: {commit.stderr.strip()[:200]}")
    return Refresh(True, "refreshed " + ", ".join(tracked))
