"""Unit tests for the Phase 07 building blocks: locks, state, notify, vault, detach, CLI."""

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from conftest import RepoFactory, git
from phx import notify
from phx.cli import format_event, main, status_report
from phx.detach import ENV_ALLOWLIST, detach_argv, unit_name
from phx.locks import LockBusy, LockInfo, RunLock, lock_dir, read_lock, repo_name, running
from phx.logging import EventLog
from phx.plan import PlanError, parse_questions, set_question_status
from phx.state import Pause, PhaseTotals, RunState, Wait, load_state, save_state
from phx.vault import append_line, note_path, summary_line

# --------------------------------------------------------------------------- locks


def test_lock_acquire_body_update_release(tmp_path: Path, make_repo: RepoFactory) -> None:
    repo = make_repo(files={"a": "1"})
    env = {"XDG_RUNTIME_DIR": str(tmp_path / "run")}
    lock = RunLock(repo, started="2026-10-26 16:00 CDT", unit="phx-repo", env=env).acquire()
    try:
        assert oct(lock_dir(env).stat().st_mode & 0o777) == "0o700"
        info = running(repo, env)
        assert info == LockInfo(os.getpid(), str(repo), "2026-10-26 16:00 CDT", None, "phx-repo")
        lock.update(phase="07")
        assert running(repo, env).phase == "07"  # type: ignore[union-attr]
        body = json.loads((lock_dir(env) / "repo.lock").read_text())
        assert body["phase"] == "07" and "\n" not in json.dumps(body)
        with pytest.raises(LockBusy, match=r"repo lock|machine-wide"):
            RunLock(repo, started="x", env=env, retry_s=0.1).acquire()
    finally:
        lock.release()
    assert running(repo, env) is None  # file exists but is stale
    assert (lock_dir(env) / "repo.lock").exists()
    assert read_lock(lock_dir(env) / "missing.lock") is None


def test_repo_name_from_worktree(make_repo: RepoFactory, tmp_path: Path) -> None:
    repo = make_repo(files={"a": "1"}, name="Main")
    tree = tmp_path / "Main-phase-01"
    git(repo, "worktree", "add", "-q", str(tree), "-b", "phase-01-x")
    assert repo_name(tree) == "Main" and repo_name(repo) == "Main"


def test_lock_info_parse_garbage() -> None:
    assert LockInfo.parse("not json") == LockInfo(None, None, None, None, None)
    assert LockInfo.parse('{"pid": "x", "phase": 5}').pid is None


# --------------------------------------------------------------------------- state


def test_state_round_trip_and_atomic(tmp_path: Path) -> None:
    state = RunState(
        run_id="r1",
        repo="/x",
        status="waiting",
        phase="05",
        wait=Wait("05", "s", "p", 123.0, "limit", provider="anthropic"),
        pause=Pause("why", "blocked", "05", "ts", ["6"]),
        sessions={"05": "s"},
        phases={"05": PhaseTotals(sessions=2, tokens=10, cost_usd=0.5)},
    )
    save_state(tmp_path, state)
    loaded = load_state(tmp_path)
    assert loaded is not None
    assert loaded.wait == state.wait and loaded.pause == state.pause
    assert loaded.phases["05"].tokens == 10 and loaded.updated
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]  # no temp file left
    assert oct((tmp_path / "state.json").stat().st_mode & 0o777) == "0o600"
    (tmp_path / "state.json").write_text("{broken")
    assert load_state(tmp_path) is None
    (tmp_path / "state.json").write_text(json.dumps({"run_id": "x", "future_key": 1}))
    assert load_state(tmp_path).run_id == "x"  # type: ignore[union-attr]


# --------------------------------------------------------------------------- notify


def _notifier(tmp_path: Path, env: dict[str, str], calls: list[Any]) -> notify.Notifier:
    def run(argv: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    return notify.Notifier(EventLog(tmp_path / "run.jsonl"), env=env, repo_label="R", run=run)


def test_notify_sends_silently(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "notify-send").write_text("#!/bin/sh\n")
    (bin_dir / "notify-send").chmod(0o755)
    calls: list[Any] = []
    env = {"PATH": str(bin_dir), "WAYLAND_DISPLAY": "wayland-1", "XDG_RUNTIME_DIR": "/run/user/1"}
    n = _notifier(tmp_path, env, calls)
    assert n.send(notify.blocked("/w/R", "05", ("6",), "blocked", "needs a colour"), phase="05")
    argv = calls[0]
    assert "--hint=boolean:suppress-sound:true" in argv and "--urgency=critical" in argv
    assert argv[-2] == "PHX R: phase 05 blocked on question #6"
    assert 'phx answer /w/R 6 "<answer>"' in argv[-1] and "needs a colour" in argv[-1]
    record = json.loads((tmp_path / "run.jsonl").read_text())
    assert record["event"] == "notify" and record["sent"] is True and record["kind"] == "blocked"


@pytest.mark.parametrize(
    ("env", "why"),
    [
        ({"PATH": "/nonexistent"}, "no display"),
        ({"PATH": "/nonexistent", "DISPLAY": ":0"}, "no session bus"),
        ({"PATH": "/nonexistent", "DISPLAY": ":0", "XDG_RUNTIME_DIR": "/r"}, "not found"),
    ],
)
def test_notify_degrades_silently(tmp_path: Path, env: dict[str, str], why: str) -> None:
    calls: list[Any] = []
    n = _notifier(tmp_path, env, calls)
    assert n.send(notify.finished("done")) is False
    assert calls == []
    assert why in json.loads((tmp_path / "run.jsonl").read_text())["skipped"]


def test_notify_builders() -> None:
    assert "Super+Alt+A" in notify.waiting("05", "limit", "19:42").body
    assert notify.provider_switch("05", "openrouter").title == "provider switched to openrouter"
    assert notify.paused("/w/R", None, "x").title == "run paused"
    assert "phx resume /w/R" in notify.paused("/w/R", "05", "x").body


# --------------------------------------------------------------------------- vault


def test_vault_append_line_touches_only_log_and_updated() -> None:
    text = (
        "---\nupdated: old\ntags: [a]\n---\n# N\n\nbody updated: keep\n\n"
        "## Log\n- a\n\n## Next\nz\n"
    )
    out = append_line(text, "- new", "2026-10-26 16:00 CDT")
    assert out == (
        "---\nupdated: 2026-10-26 16:00 CDT\ntags: [a]\n---\n# N\n\nbody updated: keep\n\n"
        "## Log\n- a\n- new\n\n## Next\nz\n"
    )
    assert append_line("# no log\n", "- x", "t") is None
    assert append_line("## Log\n", "- x", "t") == "## Log\n- x\n"


def test_vault_note_path_and_summary(make_repo: RepoFactory) -> None:
    repo = make_repo(files={"CLAUDE.md": "6. The Obsidian project note `/v/X Plan.md`: do it.\n"})
    assert note_path(repo) == Path("/v/X Plan.md")
    state = RunState(run_id="r", status="paused", end_reason="review gate")
    state.phases["05"] = PhaseTotals(2, 1_500_000, 3.456, 3900.0, "complete")
    line = summary_line(state, "TS")
    assert line == (
        "- **TS:** PHX run `r` ended paused: review gate. Phases: 05 ✅ complete "
        "(1.5M tokens, $3.46, 2 session(s), waited 1h 05m). Total 0 tokens, $0.00."
    )


# --------------------------------------------------------------------------- plan helper


def test_set_question_status() -> None:
    text = (
        "## Owner questions\n| # | Question | Status / proposed default | Needed by |\n"
        "|---|---|---|---|\n| 1 | A? | Open. Proposed default: x | Phase 02 |\n"
        "| 2 | B? | Open | Phase 03 |\n\n## Phase Log\n"
    )
    out = set_question_status(text, "2", "Answered TS: y|z")
    assert "| 2 | B? | Answered TS: y\\|z | Phase 03 |" in out
    assert out.replace("Answered TS: y\\|z", "Open") == text
    (q1, q2) = parse_questions(out)
    assert q1.open and not q2.open and q2.status == "Answered TS: y|z"
    with pytest.raises(PlanError, match="not in the questions table"):
        set_question_status(text, "9", "x")
    with pytest.raises(PlanError, match="no owner questions table"):
        set_question_status("# nothing\n", "1", "x")


# --------------------------------------------------------------------------- detach


def test_detach_argv() -> None:
    env = {k: f"v-{k}" for k in ENV_ALLOWLIST} | {"ANTHROPIC_AUTH_TOKEN": "secret", "FOO": "x"}
    argv = detach_argv(Path("/w/My Repo"), unit_name("My Repo"), ["run", "/w/My Repo"], env, "py")
    assert argv[:5] == ["systemd-run", "--user", "--unit=phx-My_Repo", "--collect", "--quiet"]
    assert "--working-directory=/w/My Repo" in argv
    assert "--property=KillMode=mixed" in argv
    assert "--setenv=PHX_UNIT=phx-My_Repo" in argv
    assert "--setenv=WAYLAND_DISPLAY=v-WAYLAND_DISPLAY" in argv
    assert not any("secret" in a or "FOO" in a for a in argv)
    assert argv[-5:] == ["py", "-m", "phx", "run", "/w/My Repo"]


# --------------------------------------------------------------------------- CLI


def test_log_formatting(tmp_path: Path, make_repo: RepoFactory, capsys: Any) -> None:
    repo = make_repo(files={"a": "1"}, name="R")
    log = EventLog(tmp_path / "state" / "R" / "run.jsonl")
    for i in range(3):
        log.event("decision", phase="05", reason=f"step {i}")
    assert main(["--state-dir", str(tmp_path / "state"), "log", str(repo), "-n", "2"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 2 and out[-1].endswith("decision [05] step 2")
    assert main(["--state-dir", str(tmp_path / "state"), "log", str(repo), "--json"]) == 0
    assert json.loads(capsys.readouterr().out.splitlines()[0])["reason"] == "step 0"
    assert format_event("garbage\n") == "garbage"


def test_status_report_and_listing(
    tmp_path: Path, make_repo: RepoFactory, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    repo = make_repo("sample", name="SMP")
    sdir = tmp_path / "state" / "SMP"
    state = RunState(run_id="r", repo=str(repo), status="waiting", phase="01")
    state.wait = Wait("01", "s", None, 9_999_999_999.0, "usage limit (five_hour)")
    save_state(sdir, state)
    report = status_report(repo, tmp_path / "state")
    assert report["running"] is None and report["plan"]["next"] == "01"
    assert report["plan"]["open_questions"][0]["id"] == "1"
    assert main(["--state-dir", str(tmp_path / "state"), "status", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "Supervisor: not running" in out and "supervisor gone" in out
    assert "Waiting:    usage limit (five_hour)" in out and "Plan:       1/4 ✅, next 01" in out
    assert main(["--state-dir", str(tmp_path / "state"), "status"]) == 0
    assert "SMP: not running; last run waiting, wakes in" in capsys.readouterr().out


def test_stop_without_supervisor(
    tmp_path: Path, make_repo: RepoFactory, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    repo = make_repo(files={"a": "1"})
    assert main(["stop", str(repo)]) == 0
    assert "no supervisor is running" in capsys.readouterr().out


def test_run_rejects_bad_options(make_repo: RepoFactory) -> None:
    repo = make_repo(files={"a": "1"})
    with pytest.raises(SystemExit, match="--until"):
        main(["run", str(repo), "--until", "7"])
    with pytest.raises(SystemExit, match="at least 1"):
        main(["run", str(repo), "--max-phases", "0"])


def test_vault_path_confined_to_the_vault_root(make_repo: RepoFactory, tmp_path: Path) -> None:
    """CLAUDE.md is repo text: PHX writes only a .md note inside PHX_VAULT_ROOT (Phase 11)."""
    from phx.logging import EventLog
    from phx.state import RunState
    from phx.vault import append_summary, vault_root

    vault = tmp_path / "vault"
    vault.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("## Log\n")
    (vault / "link.md").symlink_to(outside)
    env = {"PHX_VAULT_ROOT": str(vault), "HOME": str(tmp_path)}
    assert vault_root({"HOME": "/h"}) == Path("/h/Documents")
    assert vault_root(env) == vault
    log = EventLog(tmp_path / "run.jsonl")
    for target in (outside, vault / "link.md", Path("rel/x.md")):
        repo = make_repo("sample", name=f"work/R{abs(hash(target)) % 10**6}")
        (repo / "CLAUDE.md").write_text(f"The Obsidian project note `{target}`\n")
        git(repo, "add", "CLAUDE.md")
        git(repo, "commit", "-q", "-m", "note")
        got = append_summary(repo, RunState(), log, env)
        assert not got.written and "inside the vault" in got.reason, target
    assert outside.read_text() == "## Log\n"
