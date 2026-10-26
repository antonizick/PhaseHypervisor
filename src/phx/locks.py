"""Run locks (contract §8, spec R15, S4, ADR-0007).

Two ``flock`` locks are held for the supervisor's whole life, usage-limit waits
included: ``LOCKDIR/phx.lock`` (machine-wide, one supervisor at a time) and
``LOCKDIR/<repo-name>.lock`` (per repo, the file a manual ``/phase`` checks with
``flock -n -s``). Both carry a one-line JSON body. A lock file that exists but is not
locked is stale and means "not running"; files are never deleted, only truncated.
"""

import fcntl
import json
import os
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MACHINE_LOCK = "phx.lock"
ACQUIRE_RETRY_S = 2.0  # a manual check briefly takes a shared lock (contract §8)
_RETRY_STEP_S = 0.1


class LockBusy(RuntimeError):
    """Another supervisor holds a lock; ``holder`` is its lock body, if readable."""

    def __init__(self, message: str, holder: "LockInfo | None" = None) -> None:
        super().__init__(message)
        self.holder = holder


@dataclass(frozen=True)
class LockInfo:
    """The JSON body of a held lock."""

    pid: int | None
    repo: str | None
    started: str | None
    phase: str | None
    unit: str | None

    @classmethod
    def parse(cls, text: str) -> "LockInfo":
        try:
            data = json.loads(text.strip() or "{}")
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}

        def text_or_none(key: str) -> str | None:
            value = data.get(key)
            return value if isinstance(value, str) else None

        pid = data.get("pid")
        return cls(
            pid if isinstance(pid, int) and not isinstance(pid, bool) else None,
            text_or_none("repo"),
            text_or_none("started"),
            text_or_none("phase"),
            text_or_none("unit"),
        )


def lock_dir(env: Mapping[str, str] | None = None) -> Path:
    """``${XDG_RUNTIME_DIR:-/run/user/$UID}/phx``."""
    env = os.environ if env is None else env
    base = env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return Path(base) / "phx"


def main_checkout(repo: Path) -> Path:
    """The main checkout of ``repo`` (also from a worktree): parent of the git common dir."""
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise ValueError(f"{repo} is not a git repository")
    return Path(proc.stdout.strip()).parent


def repo_name(repo: Path) -> str:
    """``basename "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"``."""
    return main_checkout(repo).name


def repo_lock_path(repo: Path, env: Mapping[str, str] | None = None) -> Path:
    return lock_dir(env) / f"{repo_name(repo)}.lock"


def _held(path: Path) -> bool:
    """True if some process holds a lock on ``path`` (a shared probe fails)."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def read_lock(path: Path) -> LockInfo | None:
    """The body of ``path`` if it is held, else ``None`` (missing or stale)."""
    if not path.exists() or not _held(path):
        return None
    try:
        return LockInfo.parse(path.read_text(encoding="utf-8"))
    except OSError:
        return LockInfo(None, None, None, None, None)


def running(repo: Path, env: Mapping[str, str] | None = None) -> LockInfo | None:
    """The live supervisor on ``repo``, or ``None``."""
    return read_lock(repo_lock_path(repo, env))


def _acquire(path: Path, retry_s: float) -> int:
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    deadline = time.monotonic() + retry_s
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except BlockingIOError:
            if time.monotonic() >= deadline:
                os.close(fd)
                raise
            time.sleep(_RETRY_STEP_S)


def _write(fd: int, body: dict[str, Any]) -> None:
    data = (json.dumps(body, ensure_ascii=False) + "\n").encode()
    os.ftruncate(fd, 0)
    os.pwrite(fd, data, 0)
    os.fsync(fd)


class RunLock:
    """Both locks for one supervisor. Use as a context manager or call ``acquire``/``release``."""

    def __init__(
        self,
        repo: Path,
        *,
        started: str,
        unit: str | None = None,
        env: Mapping[str, str] | None = None,
        retry_s: float = ACQUIRE_RETRY_S,
    ) -> None:
        self.repo = main_checkout(repo)
        self.directory = lock_dir(env)
        self.machine_path = self.directory / MACHINE_LOCK
        self.repo_path = self.directory / f"{self.repo.name}.lock"
        self.body: dict[str, Any] = {
            "pid": os.getpid(),
            "repo": str(self.repo),
            "started": started,
            "phase": None,
            "unit": unit,
        }
        self.retry_s = retry_s
        self._fds: list[int] = []

    def acquire(self) -> "RunLock":
        self.directory.mkdir(parents=True, exist_ok=True)
        os.chmod(self.directory, 0o700)
        for path, scope in ((self.machine_path, "machine-wide"), (self.repo_path, "repo")):
            try:
                fd = _acquire(path, self.retry_s)
            except BlockingIOError as exc:
                self.release()
                holder = read_lock(self.repo_path) or read_lock(path)
                who = (
                    f" (pid {holder.pid}, {holder.repo}, phase {holder.phase or '-'})"
                    if holder
                    else ""
                )
                raise LockBusy(
                    f"another phx supervisor holds the {scope} lock{who}", holder
                ) from exc
            self._fds.append(fd)
            _write(fd, self.body)
        return self

    def update(self, **fields: Any) -> None:
        """Rewrite the body (``phase=…``) while holding the locks."""
        self.body.update(fields)
        for fd in self._fds:
            _write(fd, self.body)

    def release(self) -> None:
        for fd in self._fds:
            try:
                os.ftruncate(fd, 0)
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
        self._fds = []

    def __enter__(self) -> "RunLock":
        return self.acquire()

    def __exit__(self, *exc: object) -> None:
        self.release()
