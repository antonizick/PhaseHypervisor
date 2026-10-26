"""State directories and the per-repo ``.phx/config.toml`` loader."""

import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Config:
    """Per-repo overrides with typed defaults (spec R1, R7, R10)."""

    test_command: str | None = None
    max_budget_usd: float | None = None
    poll_interval_s: int = 300
    limit_poll_interval_s: int = 900
    triage: bool = True
    idle_timeout_s: int = 1800  # no stream events for this long: kill the session
    wall_timeout_s: int = 21600  # hard cap on one session


def default_state_root() -> Path:
    """``$XDG_STATE_HOME/phx`` or ``~/.local/state/phx``."""
    base = os.environ.get("XDG_STATE_HOME")
    root = Path(base) if base else Path.home() / ".local" / "state"
    return root / "phx"


def state_dir(repo: Path, state_root: Path | None = None) -> Path:
    """State directory for one repo: ``<root>/<repo-name>/``."""
    return (state_root or default_state_root()) / repo.resolve().name


def sessions_dir(state: Path) -> Path:
    return state / "sessions"


def ensure_state_dirs(state: Path) -> None:
    sessions_dir(state).mkdir(parents=True, exist_ok=True)


def load_config(repo: Path) -> Config:
    """Read ``<repo>/.phx/config.toml``; a missing file yields the defaults.

    Unknown keys and wrongly typed values raise ``ValueError``.
    """
    path = repo / ".phx" / "config.toml"
    if not path.is_file():
        return Config()
    return parse_config(path.read_text(encoding="utf-8"), str(path))


def parse_config(text: str, source: str) -> Config:
    """Parse config TOML ``text``; ``source`` names it in error messages."""
    data: dict[str, Any] = tomllib.loads(text)
    known = {f.name: f for f in fields(Config)}
    unknown = sorted(set(data) - set(known))
    if unknown:
        raise ValueError(f"{source}: unknown config keys: {', '.join(unknown)}")
    defaults = Config()
    for key, value in data.items():
        expected = type(getattr(defaults, key))
        if expected is type(None):  # optional field: accept str or number as declared
            expected = str if key == "test_command" else float
        ok = isinstance(value, int | float) if expected is float else isinstance(value, expected)
        if isinstance(value, bool) and expected is not bool:
            ok = False
        if not ok:
            raise ValueError(f"{source}: {key} must be {expected.__name__}")
    return Config(**data)
