import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from phx.classify import ExitClass
from phx.logging import EventLog
from phx.paths import Config, parse_config
from phx.runner import (
    Launcher,
    LauncherError,
    Timeouts,
    Usage,
    build_argv,
    build_env,
    find_launcher,
    parse_provider_env,
    probe,
    provider_snapshot,
    run_session,
    transcript_path,
)

TESTS = Path(__file__).resolve().parent
FAKES = TESTS / "fakes"
STREAMS = TESTS / "fixtures" / "streams"
FAKE_KEY = "sk-or-v1-" + "f" * 40  # fake; shaped like a key so redaction must catch it


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """A child environment whose PATH finds only the fakes (plus python)."""
    return {
        "PATH": f"{FAKES}:/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        "PHX_FAKE_ARGV_LOG": str(tmp_path / "argv.jsonl"),
        "ANTHROPIC_MODEL": "sonnet",
    }


@pytest.fixture
def state(tmp_path: Path) -> Path:
    return tmp_path / "state"


@pytest.fixture
def log(state: Path) -> EventLog:
    return EventLog(state / "run.jsonl")


def events(state: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in (state / "run.jsonl").read_text().splitlines()]


def calls(env: dict[str, str]) -> list[dict[str, Any]]:
    return [json.loads(x) for x in Path(env["PHX_FAKE_ARGV_LOG"]).read_text().splitlines()]


def go(tmp_path: Path, state: Path, log: EventLog, env: dict[str, str], **kw: Any) -> Any:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    args: dict[str, Any] = {
        "repo": repo,
        "state": state,
        "phase": "05",
        "prompt": "/phase 05 --auto",
        "alias": "opus",
        "log": log,
        "env": env,
    }
    args.update(kw)
    return run_session(**args)


# --- launcher, argv, env ----------------------------------------------------------


def test_find_launcher_prefers_ai_provider_on_path(env: dict[str, str]) -> None:
    launcher = find_launcher(env)
    assert launcher.prefix == (str(FAKES / "ai-provider"), "run")
    assert launcher.warning is None


def test_find_launcher_local_bin(tmp_path: Path) -> None:
    home = tmp_path / "home"
    local = home / ".local" / "bin" / "ai-provider"
    local.parent.mkdir(parents=True)
    local.write_text("#!/bin/sh\n")
    local.chmod(0o755)
    launcher = find_launcher({"PATH": "/nonexistent"}, home=home)
    assert launcher.ai_provider == str(local)


def test_find_launcher_falls_back_to_claude(tmp_path: Path) -> None:
    only_claude = tmp_path / "bin"
    only_claude.mkdir()
    (only_claude / "claude").symlink_to(FAKES / "claude")
    launcher = find_launcher({"PATH": str(only_claude)}, home=tmp_path)
    assert launcher.prefix == (str(only_claude / "claude"),)
    assert launcher.ai_provider is None and launcher.warning


def test_find_launcher_none(tmp_path: Path) -> None:
    with pytest.raises(LauncherError):
        find_launcher({"PATH": str(tmp_path)}, home=tmp_path)


def test_build_argv_fresh_and_resume() -> None:
    launcher = Launcher(("ai-provider", "run"), "ai-provider")
    argv = build_argv(launcher, "/phase 05 --auto", "opus", session_id="abc")
    assert argv == [
        "ai-provider", "run", "-p", "/phase 05 --auto", "--model", "opus",
        "--permission-mode", "bypassPermissions", "--output-format", "stream-json",
        "--verbose", "--session-id", "abc",
    ]  # fmt: skip
    resumed = build_argv(launcher, "continue", "opus", resume="abc", max_budget_usd=2.5)
    assert resumed[-4:] == ["--resume", "abc", "--max-budget-usd", "2.5"]
    assert "--session-id" not in resumed
    with pytest.raises(ValueError):
        build_argv(launcher, "x", "opus")
    with pytest.raises(ValueError):
        build_argv(launcher, "x", "opus", session_id="a", resume="b")


def test_build_env() -> None:
    env = build_env({"ANTHROPIC_MODEL": "sonnet", "PATH": "/bin"})
    assert env == {"PATH": "/bin", "PHX_AUTO": "1"}
    assert "PHX_AUTO" not in build_env({"PHX_AUTO": "1"}, auto=False)


# --- provider snapshot ------------------------------------------------------------

OPENROUTER_ENV = f"""export ANTHROPIC_BASE_URL=https://openrouter.ai/api
export ANTHROPIC_AUTH_TOKEN={FAKE_KEY}
export ANTHROPIC_API_KEY=''
export CLAUDE_CODE_MAX_OUTPUT_TOKENS=32000
export ANTHROPIC_DEFAULT_OPUS_MODEL=z-ai/glm-5
export ANTHROPIC_DEFAULT_HAIKU_MODEL='google/gemini-3-flash'
"""


def test_parse_provider_env_drops_secrets() -> None:
    got = parse_provider_env(OPENROUTER_ENV)
    assert got == {
        "ANTHROPIC_BASE_URL": "https://openrouter.ai/api",
        "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "32000",
        "ANTHROPIC_DEFAULT_OPUS_MODEL": "z-ai/glm-5",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "google/gemini-3-flash",
    }
    assert FAKE_KEY not in json.dumps(got)


def test_parse_provider_env_redacts_a_key_in_an_allowed_value() -> None:
    got = parse_provider_env(f"export ANTHROPIC_MODEL={FAKE_KEY}\n")
    assert got["ANTHROPIC_MODEL"] == "[REDACTED]"


def test_snapshot_openrouter(tmp_path: Path, env: dict[str, str]) -> None:
    (tmp_path / "env.sh").write_text(OPENROUTER_ENV)
    env |= {"PHX_FAKE_PROVIDER": "openrouter", "PHX_FAKE_ENV": str(tmp_path / "env.sh")}
    snap = provider_snapshot(find_launcher(env), "opus", env=env)
    assert (snap.provider, snap.mapped_model) == ("openrouter", "z-ai/glm-5")
    assert FAKE_KEY not in repr(snap)


def test_snapshot_anthropic_does_not_call_env(env: dict[str, str]) -> None:
    seen: list[list[str]] = []

    def fake_run(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 0, "anthropic\n", "")

    snap = provider_snapshot(Launcher(("ai", "run"), "ai"), "opus", run=fake_run)
    assert snap.provider == "anthropic" and snap.mapped_model is None
    assert seen == [["ai", "get"]]


def test_snapshot_errors() -> None:
    def boom(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        raise OSError("nope")

    assert provider_snapshot(Launcher(("ai", "run"), "ai"), "opus", run=boom).provider == "unknown"
    assert provider_snapshot(Launcher(("claude",), None), "opus").error == "ai-provider missing"


# --- sessions with the fakes ------------------------------------------------------


def test_complete_session_logs_tokens_and_cost(
    tmp_path: Path, state: Path, log: EventLog, env: dict[str, str]
) -> None:
    env["PHX_FAKE_STREAM"] = str(STREAMS / "complete.jsonl")
    seen: list[str] = []
    out = go(tmp_path, state, log, env, on_event=lambda e: seen.append(e["type"]))
    assert out.classification.cls is ExitClass.COMPLETE
    assert out.exit_code == 0 and out.events == 3 and seen == ["system", "assistant", "result"]
    assert out.usage.output_tokens == 5678 and out.usage.cost_usd == 1.2345
    assert out.usage.total_tokens == 1234 + 5678 + 20000 + 300000
    assert out.transcript == state / "sessions" / "05-1.jsonl"
    # the fake substituted our session id into the stream
    assert out.session_id in out.transcript.read_text()
    call = calls(env)[0]
    assert call["argv"][call["argv"].index("--session-id") + 1] == out.session_id
    assert call["env"] == {"PHX_AUTO": "1", "ANTHROPIC_MODEL": None, "ANTHROPIC_BASE_URL": None}
    assert call["cwd"] == str(tmp_path / "repo")
    launch, end = events(state)
    assert launch["event"] == "launch" and launch["provider"] == "anthropic"
    assert launch["argv"][2:4] == ["-p", "/phase 05 --auto"]
    assert end["event"] == "session_end" and end["class"] == "complete"
    assert end["tokens"] == out.usage.total_tokens and end["cost_usd"] == 1.2345


@pytest.mark.parametrize(
    ("fixture", "exit_code", "provider", "cls"),
    [
        ("blocked", 0, "anthropic", ExitClass.BLOCKED),
        ("refused", 0, "anthropic", ExitClass.REFUSED),
        ("no_result", 0, "anthropic", ExitClass.NO_RESULT),
        ("usage_limit_session", 1, "anthropic", ExitClass.USAGE_LIMIT),
        ("usage_limit_weekly_event", 1, "anthropic", ExitClass.USAGE_LIMIT),
        ("auth_expired", 1, "anthropic", ExitClass.AUTH_ERROR),
        ("openrouter_402", 1, "openrouter", ExitClass.PROVIDER_ERROR),
        ("rate_limit_429_api_key", 1, "openrouter", ExitClass.PROVIDER_ERROR),
        ("server_lost", 1, "anthropic", ExitClass.PROVIDER_ERROR),
        ("truncated", 0, "anthropic", ExitClass.CRASH),
    ],
)
def test_every_class_via_fakes(
    tmp_path: Path,
    state: Path,
    log: EventLog,
    env: dict[str, str],
    fixture: str,
    exit_code: int,
    provider: str,
    cls: ExitClass,
) -> None:
    env |= {
        "PHX_FAKE_STREAM": str(STREAMS / f"{fixture}.jsonl"),
        "PHX_FAKE_EXIT": str(exit_code),
        "PHX_FAKE_PROVIDER": provider,
    }
    out = go(tmp_path, state, log, env)
    assert out.classification.cls is cls
    assert out.exit_code == exit_code
    assert events(state)[-1]["class"] == str(cls)


def test_budget_only_on_openrouter(
    tmp_path: Path, state: Path, log: EventLog, env: dict[str, str]
) -> None:
    config = parse_config("max_budget_usd = 3\n", "t")
    go(tmp_path, state, log, env, config=config)
    env["PHX_FAKE_PROVIDER"] = "openrouter"
    go(tmp_path, state, log, env, config=config)
    first, second = calls(env)
    assert "--max-budget-usd" not in first["argv"]
    assert second["argv"][-2:] == ["--max-budget-usd", "3"]
    assert (state / "sessions" / "05-2.jsonl").exists()


def test_resume_argv(tmp_path: Path, state: Path, log: EventLog, env: dict[str, str]) -> None:
    out = go(
        tmp_path, state, log, env, resume="11111111-2222-4333-8444-555555555555", prompt="go on"
    )
    argv = calls(env)[0]["argv"]
    assert (
        argv[argv.index("--resume") + 1] == out.session_id == "11111111-2222-4333-8444-555555555555"
    )
    assert "--session-id" not in argv
    assert events(state)[0]["reason"] == "resume"


def test_redacts_secrets_in_stream_and_stderr(
    tmp_path: Path, state: Path, log: EventLog, env: dict[str, str]
) -> None:
    leaky = tmp_path / "leaky.jsonl"
    text = (STREAMS / "complete.jsonl").read_text()
    leaky.write_text(text.replace("Working on phase 05.", f"key {FAKE_KEY}"))
    env |= {"PHX_FAKE_STREAM": str(leaky), "PHX_FAKE_STDERR": f"ANTHROPIC_AUTH_TOKEN={FAKE_KEY}"}
    out = go(tmp_path, state, log, env)
    assert FAKE_KEY not in out.transcript.read_text()
    assert FAKE_KEY not in (state / "run.jsonl").read_text()
    assert FAKE_KEY not in out.stderr_tail


def test_stderr_tail_kept(tmp_path: Path, state: Path, log: EventLog, env: dict[str, str]) -> None:
    env |= {"PHX_FAKE_STREAM": str(STREAMS / "truncated.jsonl"), "PHX_FAKE_STDERR": "boom"}
    out = go(tmp_path, state, log, env)
    assert out.stderr_tail == "boom"
    assert "boom" in out.classification.reason
    # the half-written last line is stored but not parsed
    assert out.transcript.read_text().rstrip().endswith('"type":"te')


def test_idle_timeout_kills(
    tmp_path: Path, state: Path, log: EventLog, env: dict[str, str]
) -> None:
    env |= {"PHX_FAKE_STREAM": str(STREAMS / "truncated.jsonl"), "PHX_FAKE_HANG": "30"}
    start = time.monotonic()
    out = go(tmp_path, state, log, env, timeouts=Timeouts(idle_s=1, wall_s=60, term_grace_s=1))
    assert time.monotonic() - start < 10
    assert out.classification.cls is ExitClass.TIMEOUT and out.timed_out == "idle"
    assert out.exit_code == -15
    assert [e["event"] for e in events(state)] == ["launch", "timeout", "session_end"]


def test_wall_timeout_escalates_to_sigkill(
    tmp_path: Path, state: Path, log: EventLog, env: dict[str, str]
) -> None:
    env |= {"PHX_FAKE_DELAY": "0.2", "PHX_FAKE_HANG": "30", "PHX_FAKE_IGNORE_TERM": "1"}
    out = go(tmp_path, state, log, env, timeouts=Timeouts(idle_s=60, wall_s=1, term_grace_s=0.5))
    assert out.timed_out == "wall" and out.classification.cls is ExitClass.TIMEOUT
    assert out.exit_code == -9


def test_fake_mirrors_verbose_requirement() -> None:
    # The fake mirrors the real CLI's error, so the classifier reports it.
    out_stream = subprocess.run(
        [str(FAKES / "claude"), "-p", "x", "--output-format", "stream-json"],
        capture_output=True,
        text=True,
    )
    assert out_stream.returncode == 1 and "requires --verbose" in out_stream.stderr


def test_launcher_fallback_logged(tmp_path: Path, state: Path, log: EventLog) -> None:
    only_claude = tmp_path / "bin"
    only_claude.mkdir()
    (only_claude / "claude").symlink_to(FAKES / "claude")
    env = {"PATH": f"{only_claude}:/usr/bin:/bin", "HOME": str(tmp_path)}
    out = go(tmp_path, state, log, env)
    assert out.classification.cls is ExitClass.NO_RESULT  # minimal stream: "ok", no line
    assert out.argv[0] == str(only_claude / "claude") and out.argv[1] == "-p"
    kinds = [e["event"] for e in events(state)]
    assert kinds[0] == "launcher_fallback" and out.provider.provider == "unknown"


def test_probe(tmp_path: Path, state: Path, log: EventLog, env: dict[str, str]) -> None:
    env["PHX_FAKE_STREAM"] = str(STREAMS / "probe_ok.jsonl")
    assert probe(state=state, log=log, env=env).cls is ExitClass.COMPLETE
    call = calls(env)[0]
    argv = call["argv"]
    assert argv[argv.index("-p") + 1] == "ok"
    assert argv[argv.index("--model") + 1] == "haiku"
    assert argv[-2:] == ["--max-turns", "1"]
    assert call["env"]["PHX_AUTO"] is None
    assert call["cwd"] == str(state)
    assert (state / "sessions" / "probe-1.jsonl").exists()
    end = events(state)[-1]
    assert end["cost_usd"] == 0.0012


def test_probe_still_limited(
    tmp_path: Path, state: Path, log: EventLog, env: dict[str, str]
) -> None:
    env |= {"PHX_FAKE_STREAM": str(STREAMS / "usage_limit_session.jsonl"), "PHX_FAKE_EXIT": "1"}
    assert probe(state=state, log=log, env=env).cls is ExitClass.USAGE_LIMIT


# --- small pieces -----------------------------------------------------------------


def test_transcript_numbering(state: Path) -> None:
    first = transcript_path(state, "05")
    first.touch()
    assert transcript_path(state, "05").name == "05-2.jsonl"
    assert transcript_path(state, "05a").name == "05a-1.jsonl"


def test_usage_from_result_tolerates_junk() -> None:
    assert Usage.from_result(None) == Usage()
    u = Usage.from_result(
        {"usage": {"input_tokens": "x", "output_tokens": True}, "total_cost_usd": "1"}
    )
    assert u.total_tokens == 0 and u.cost_usd is None


def test_timeouts_from_config() -> None:
    t = Timeouts.from_config(parse_config("idle_timeout_s = 60\nwall_timeout_s = 120\n", "t"))
    assert (t.idle_s, t.wall_s) == (60.0, 120.0)
    assert Timeouts.from_config(Config()).idle_s == 1800.0


def test_fakes_are_executable() -> None:
    for name in ("claude", "ai-provider"):
        assert os.access(FAKES / name, os.X_OK)
