import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "plans"

RepoFactory = Callable[..., Path]


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture(autouse=True)
def _isolated_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the user's git config (hooks, signing) out of throwaway test repos."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for key, value in {
        "GIT_AUTHOR_NAME": "PHX Test",
        "GIT_AUTHOR_EMAIL": "phx-test@example.invalid",
        "GIT_COMMITTER_NAME": "PHX Test",
        "GIT_COMMITTER_EMAIL": "phx-test@example.invalid",
    }.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def make_repo(tmp_path: Path) -> RepoFactory:
    """Build a git repo on ``main`` from a fixture folder and/or ``{path: text}``."""

    def factory(
        fixture: str | None = None, files: dict[str, str] | None = None, name: str = "repo"
    ) -> Path:
        repo = tmp_path / name
        if fixture:
            shutil.copytree(FIXTURES / fixture, repo)
        repo.mkdir(exist_ok=True)
        for rel, text in (files or {}).items():
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        git(repo, "init", "-q", "-b", "main")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "fixture")
        return repo

    return factory
