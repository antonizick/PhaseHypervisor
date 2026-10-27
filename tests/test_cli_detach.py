"""``phx run --detach``, ``phx stop`` and signal handling through the real CLI (Phase 11).

A fake ``systemd-run`` (written per test) starts the supervisor the way systemd would:
detached, in the working directory it is given and with **only** the variables passed
as ``--setenv``. It records what it was asked to set, so the tests check the ``--detach``
environment allowlist (threat model: systemd-run environment exposure) end to end.
Test-only ``PHX_FAKE_*`` variables are passed through so the fake agent still runs.
"""

import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from conftest import RepoFactory
from phx.cli import main
from phx.detach import ENV_ALLOWLIST, Detached, detach
from phx.locks import running
from phx.supervisor import EXIT_ERROR, EXIT_STOPPED
from test_runner import FAKE_KEY
from test_supervisor import H

FAKE_SYSTEMD_RUN = """#!{python}
import json, os, subprocess, sys
args = sys.argv[1:]
record = {{"argv": args}}
env, cwd = {{}}, None
while args and args[0] != "--":
    a = args.pop(0)
    if a.startswith("--setenv="):
        k, _, v = a[len("--setenv="):].partition("=")
        env[k] = v
    elif a.startswith("--working-directory="):
        cwd = a.split("=", 1)[1]
record["env"] = env
with open(os.environ["PHX_FAKE_SYSTEMD_LOG"], "a") as fh:
    fh.write(json.dumps(record) + "\\n")
if os.environ.get("PHX_FAKE_SYSTEMD_FAIL"):
    print("Failed to start transient service unit: Unit phx-x.service already exists.",
          file=sys.stderr)
    sys.exit(1)
env.update({{k: v for k, v in os.environ.items() if k.startswith("PHX_FAKE_")}})
subprocess.Popen(args[1:], cwd=cwd, env=env, start_new_session=True,
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
"""


@pytest.fixture
def x(tmp_path: Path, make_repo: RepoFactory, monkeypatch: pytest.MonkeyPatch) -> H:
    h = H(tmp_path, make_repo, {"01": ["hang"]}).all_auto().decide_q1()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "systemd-run"
    fake.write_text(FAKE_SYSTEMD_RUN.format(python=sys.executable))
    fake.chmod(0o755)
    h.env["PATH"] = f"{bin_dir}:{h.env['PATH']}"
    h.env["PHX_FAKE_SYSTEMD_LOG"] = str(tmp_path / "systemd.jsonl")
    h.env["ANTHROPIC_AUTH_TOKEN"] = FAKE_KEY  # must not reach the unit
    h.env["SECRET_THING"] = "x"
    for key, value in h.env.items():
        monkeypatch.setenv(key, value)
    return h


def systemd_calls(x: H) -> list[dict[str, Any]]:
    path = x.tmp / "systemd.jsonl"
    return [json.loads(ln) for ln in path.read_text().splitlines()] if path.exists() else []


def test_detach_stop_and_allowlist(x: H, capsys: pytest.CaptureFixture[str]) -> None:
    state = ["--state-dir", str(x.state_root)]
    try:
        assert main([*state, "run", str(x.repo), "--detach", "--until", "01"]) == 0
        out = capsys.readouterr().out
        assert "running as unit phx-SMP (pid" in out and f"phx stop {x.repo}" in out
        (call,) = systemd_calls(x)
        assert set(call["env"]) <= {*ENV_ALLOWLIST, "PHX_UNIT"}
        assert call["env"]["PHX_UNIT"] == "phx-SMP" and call["env"]["PHX_WORK_ROOT"]
        assert FAKE_KEY not in json.dumps(call) and "SECRET_THING" not in call["env"]
        assert call["argv"][-6:] == [
            "--state-dir",
            str(x.state_root.resolve()),
            "run",
            str(x.repo),
            "--until",
            "01",
        ]
        holder = running(x.repo)
        assert holder is not None and holder.unit == "phx-SMP"
        # a second --detach refuses while the first one runs
        assert main([*state, "run", str(x.repo), "--detach"]) == EXIT_ERROR
        assert "already running" in capsys.readouterr().err
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not x.calls("01"):
            time.sleep(0.1)
        assert main([*state, "stop", str(x.repo), "--timeout", "30"]) == 0
        assert "phx: stopped: received SIGTERM" in capsys.readouterr().out
    finally:
        holder = running(x.repo)
        if holder and holder.pid:
            os.kill(holder.pid, signal.SIGKILL)
    assert running(x.repo) is None


def test_detach_reports_systemd_run_failures(x: H, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHX_FAKE_SYSTEMD_FAIL", "1")
    got = detach(x.repo, "phx-SMP", ["run", str(x.repo)])
    assert not got.ok and "systemd-run exited 1: Failed to start transient" in got.message
    monkeypatch.setenv("PATH", str(x.tmp / "nowhere"))
    got = detach(x.repo, "phx-SMP", ["run", str(x.repo)])
    assert not got.ok and got.message.startswith("systemd-run failed:")


def test_detach_unit_that_never_takes_the_lock(x: H, monkeypatch: pytest.MonkeyPatch) -> None:
    got: Detached = detach(x.repo, "phx-SMP", ["--version"], wait_s=0.5)  # exits at once
    assert got.ok and "does not hold the lock yet" in got.message
    assert "systemctl --user status phx-SMP" in got.message


def test_sigterm_in_the_foreground_stops_cleanly(x: H, capsys: pytest.CaptureFixture[str]) -> None:
    """`phx run` in the foreground: SIGTERM/SIGINT/SIGHUP stop the run, the phase stays 🔄."""

    def term_when_running() -> None:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not x.calls("01"):
            time.sleep(0.05)
        os.kill(os.getpid(), signal.SIGTERM)

    timer = threading.Thread(target=term_when_running, daemon=True)
    timer.start()
    before = signal.getsignal(signal.SIGTERM)
    code = main(["--state-dir", str(x.state_root), "run", str(x.repo), "--until", "01"])
    timer.join(5)
    assert code == EXIT_STOPPED
    assert signal.getsignal(signal.SIGTERM) is before  # handlers restored
    assert "received SIGTERM" in x.last_event("run_end")["reason"]


def test_stop_edge_cases(
    x: H, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from phx.locks import RunLock

    with RunLock(x.repo, started="now") as lock:
        lock.update(pid=2**22 + 12345)  # a PID that does not exist
        assert main(["stop", str(x.repo)]) == 0
        assert "is gone" in capsys.readouterr().out

        def denied(_pid: int, _sig: int) -> None:
            raise PermissionError

        monkeypatch.setattr(os, "kill", denied)
        assert main(["stop", str(x.repo)]) == EXIT_ERROR
        assert "not allowed to signal" in capsys.readouterr().err
        monkeypatch.setattr(os, "kill", lambda _pid, _sig: None)  # ignores SIGTERM
        assert main(["stop", str(x.repo), "--timeout", "0.3"]) == EXIT_ERROR
        assert "still running after 0 s" in capsys.readouterr().err


def test_log_follow_until_interrupted(
    x: H, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    state = ["--state-dir", str(x.state_root)]
    sleeps = {"n": 0}

    def sleep(_s: float) -> None:
        sleeps["n"] += 1
        if sleeps["n"] == 1:
            with (x.state_root / "SMP" / "run.jsonl").open("a") as fh:
                fh.write(json.dumps({"ts": "t", "event": "late", "reason": "arrived"}) + "\n")
        else:
            raise KeyboardInterrupt

    monkeypatch.setattr("phx.cli.time.sleep", sleep)
    assert main([*state, "log", str(x.repo), "-f"]) == 0  # no log yet: created, then followed
    out = capsys.readouterr()
    assert "no run log yet" in out.err and "t late arrived" in out.out
    assert main([*state, "log", str(x.repo), "--json", "-n", "0"]) == 0
    assert '"event": "late"' in capsys.readouterr().out


def test_module_entry_point() -> None:
    got = subprocess.run(
        [sys.executable, "-m", "phx", "--version"], capture_output=True, text=True, check=False
    )
    assert got.returncode == 0 and got.stdout.startswith("phx ")
