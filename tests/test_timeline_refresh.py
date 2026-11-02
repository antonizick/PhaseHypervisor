"""``phx.timeline.refresh``: the supervisor keeps the generated timeline current (ADR-0030)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from phx import timeline

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "phase_timeline.py"
PLAN = Path(__file__).parent / "fixtures" / "timeline" / "modern.md"


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout


def project(root: Path) -> Path:
    git(root, "init", "-q", "-b", "main")
    for k, v in (("user.email", "t@example.invalid"), ("user.name", "T")):
        git(root, "config", k, v)
    git(root, "config", "commit.gpgsign", "false")
    shutil.copy(PLAN, root / "XYZ_IMPLEMENTATION_PLAN.md")
    (root / "scripts").mkdir()
    shutil.copy(SCRIPT, root / "scripts" / "phase_timeline.py")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "docs(plan): bootstrap")
    return root


def test_stale_timeline_is_refreshed_in_its_own_commit(tmp_path: Path) -> None:
    root = project(tmp_path)
    result = timeline.refresh(root)
    assert result.committed, result.reason
    assert git(root, "log", "-1", "--format=%s").strip() == timeline.SUBJECT
    assert git(root, "status", "--porcelain").strip() == ""
    again = timeline.refresh(root)
    assert not again.committed and again.reason == "up to date"


def test_grow_redraws_an_up_to_date_timeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project(tmp_path)
    monkeypatch.setattr(timeline.time, "strftime", lambda _fmt: "2030-01-01 10:00 CST")
    assert timeline.refresh(root).committed
    assert timeline.refresh(root, grow=True).reason == "up to date"  # same minute: no change
    monkeypatch.setattr(timeline.time, "strftime", lambda _fmt: "2030-01-01 10:40 CST")
    assert timeline.refresh(root).reason == "up to date"  # not stale: only growth redraws
    grown = timeline.refresh(root, grow=True)
    assert grown.committed, grown.reason
    assert (
        subprocess.run(
            ["python3", "scripts/phase_timeline.py", "--check"], cwd=root, check=False
        ).returncode
        == 0
    )


def test_refuses_on_dirty_or_wrong_branch_or_locked(tmp_path: Path) -> None:
    root = project(tmp_path)
    (root / "scratch.txt").write_text("x")
    assert "uncommitted" in timeline.refresh(root).reason
    (root / "scratch.txt").unlink()
    (root / ".git" / "index.lock").write_text("")
    assert "locked" in timeline.refresh(root).reason
    (root / ".git" / "index.lock").unlink()
    git(root, "checkout", "-q", "-b", "phase-05-x")
    assert "not on main" in timeline.refresh(root).reason
    assert git(root, "status", "--porcelain").strip() == ""


def test_no_script_is_a_quiet_no_op(tmp_path: Path) -> None:
    assert timeline.refresh(tmp_path).reason == "no scripts/phase_timeline.py"
