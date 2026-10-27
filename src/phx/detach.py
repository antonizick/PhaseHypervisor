"""``phx run --detach``: re-run the supervisor as a transient systemd user unit (spec R11).

The unit is ``phx-<repo-name>`` (``systemd-run --user --collect``), so it survives
closing the terminal and is cleaned up when it ends. Only an allowlist of environment
variables is passed in: what ``ai-provider``/Claude Code and ``notify-send`` need, no
secrets. With ``Linger=no`` (the reference machine's setting) the user manager, and the
unit with it, stops when Nick's last login session ends; closing a terminal is fine.
"""

import os
import re
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from phx.locks import LockInfo, running

ENV_ALLOWLIST = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "LANG",
    "TZ",
    "XDG_RUNTIME_DIR",
    "XDG_STATE_HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "DBUS_SESSION_BUS_ADDRESS",
    "PHX_WORK_ROOT",
    "PHX_VAULT_ROOT",
)
STOP_TIMEOUT_S = 90  # SIGTERM grace for the unit: session term grace + logging + vault


def unit_name(repo_name: str) -> str:
    return "phx-" + re.sub(r"[^A-Za-z0-9_.-]", "_", repo_name)


def detach_argv(
    repo: Path,
    unit: str,
    phx_args: Sequence[str],
    env: Mapping[str, str],
    python: str | None = None,
) -> list[str]:
    """The ``systemd-run`` command that starts ``python -m phx <phx_args>`` in ``unit``."""
    argv = [
        "systemd-run",
        "--user",
        f"--unit={unit}",
        "--collect",
        "--quiet",
        f"--working-directory={repo}",
        f"--description=PhaseHypervisor run for {repo}",
        "--property=KillMode=mixed",  # SIGTERM to phx only; it stops its session itself
        f"--property=TimeoutStopSec={STOP_TIMEOUT_S}",
    ]
    for key in ENV_ALLOWLIST:
        if env.get(key):
            argv.append(f"--setenv={key}={env[key]}")
    argv.append(f"--setenv=PHX_UNIT={unit}")
    return [*argv, "--", python or sys.executable, "-m", "phx", *phx_args]


@dataclass(frozen=True)
class Detached:
    ok: bool
    message: str
    holder: LockInfo | None = None


def detach(
    repo: Path,
    unit: str,
    phx_args: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    wait_s: float = 10.0,
) -> Detached:
    """Start the unit and wait until its supervisor holds the repo lock."""
    env = dict(os.environ if env is None else env)
    argv = detach_argv(repo, unit, phx_args, env)
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return Detached(False, f"systemd-run failed: {exc}")
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        return Detached(False, f"systemd-run exited {proc.returncode}: {detail}")
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        holder = running(repo, env)
        if holder is not None:
            return Detached(True, f"running as unit {unit} (pid {holder.pid})", holder)
        time.sleep(0.2)
    return Detached(
        True,
        f"unit {unit} started, but its supervisor does not hold the lock yet; "
        f"check `systemctl --user status {unit}` and `phx log {repo}`",
    )
