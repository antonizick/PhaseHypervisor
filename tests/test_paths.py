from pathlib import Path

import pytest

from phx.paths import (
    Config,
    ensure_state_dirs,
    load_config,
    parse_config,
    sessions_dir,
    state_dir,
)


def test_state_dir_uses_repo_name_and_xdg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
    repo = tmp_path / "MyRepo"
    repo.mkdir()
    assert state_dir(repo) == tmp_path / "xdg" / "phx" / "MyRepo"


def test_state_dir_default_and_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert state_dir(tmp_path / "R") == tmp_path / ".local/state/phx/R"
    assert state_dir(tmp_path / "R", tmp_path / "s") == tmp_path / "s" / "R"


def test_ensure_state_dirs(tmp_path: Path) -> None:
    ensure_state_dirs(tmp_path / "st")
    assert sessions_dir(tmp_path / "st").is_dir()


def test_config_defaults_when_missing(tmp_path: Path) -> None:
    assert load_config(tmp_path) == Config()
    assert Config().triage is True and Config().test_command is None


def test_config_overrides(tmp_path: Path) -> None:
    (tmp_path / ".phx").mkdir()
    (tmp_path / ".phx" / "config.toml").write_text(
        'test_command = "make test"\nmax_budget_usd = 5\npoll_interval_s = 10\ntriage = false\n'
    )
    cfg = load_config(tmp_path)
    assert cfg.test_command == "make test" and cfg.max_budget_usd == 5
    assert cfg.poll_interval_s == 10 and cfg.triage is False
    assert cfg.limit_poll_interval_s == 900


@pytest.mark.parametrize("body", ["bogus = 1", 'poll_interval_s = "soon"', "triage = 1"])
def test_config_rejects_bad_input(tmp_path: Path, body: str) -> None:
    (tmp_path / ".phx").mkdir()
    (tmp_path / ".phx" / "config.toml").write_text(body)
    with pytest.raises(ValueError):
        load_config(tmp_path)


def test_bool_is_not_a_number() -> None:
    """A TOML bool is an int in Python; numeric fields still refuse it (Phase 04 follow-up)."""
    with pytest.raises(ValueError, match="test_timeout_s must be int"):
        parse_config("test_timeout_s = true\n", "x")
    with pytest.raises(ValueError, match="max_budget_usd must be float"):
        parse_config("max_budget_usd = false\n", "x")
