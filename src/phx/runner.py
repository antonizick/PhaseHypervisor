"""Launch one headless Claude Code session and capture how it went (spec R2, R7-R10).

The runner starts ``ai-provider run -p … --output-format stream-json --verbose`` in
its own process group, writes the redacted stream to ``sessions/<phase>-<n>.jsonl``,
enforces an idle timeout and a wall-clock cap, totals tokens and cost from the
``result`` event and hands everything to :func:`phx.classify.classify`. What to do
with the classification is the supervisor's job (Phases 06/07).
"""

import contextlib
import errno
import json
import os
import queue
import re
import shlex
import shutil
import signal
import subprocess
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import IO, Any

from phx.classify import Classification, classify
from phx.logging import EventLog
from phx.paths import Config, sessions_dir
from phx.redact import redact, redact_text

PERMISSION_MODE = "bypassPermissions"
PROBE_PROMPT = "ok"
PROBE_ALIAS = "haiku"
TERM_GRACE_S = 10.0
_STDERR_LINES = 50
_LAST_EVENTS = 20

# Non-secret variables of `ai-provider env` that say which model serves an alias.
# Everything else in that output (notably ANTHROPIC_AUTH_TOKEN) is dropped unread.
_ENV_ALLOWLIST = (
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "CLAUDE_CODE_SUBAGENT_MODEL",
    "CLAUDE_CODE_MAX_OUTPUT_TOKENS",
    "CLAUDE_CODE_MAX_CONTEXT_TOKENS",
)
_EXPORT = re.compile(r"^export ([A-Z_][A-Z0-9_]*)=(.*)$")


class LauncherError(RuntimeError):
    """Neither ``ai-provider`` nor ``claude`` can be found."""


@dataclass(frozen=True)
class Launcher:
    """The command prefix that starts Claude Code, e.g. ``[ai-provider, run]``."""

    prefix: tuple[str, ...]
    ai_provider: str | None  # path of ai-provider, None when falling back to claude
    warning: str | None = None


def find_launcher(env: Mapping[str, str] | None = None, home: Path | None = None) -> Launcher:
    """``ai-provider`` on PATH, else ``~/.local/bin/ai-provider``, else ``claude`` (spec R7)."""
    env = os.environ if env is None else env
    path = env.get("PATH", "")
    found = shutil.which("ai-provider", path=path)
    if found is None:
        home = home or (Path(env["HOME"]) if env.get("HOME") else Path.home())
        local = home / ".local" / "bin" / "ai-provider"
        if local.is_file() and os.access(local, os.X_OK):
            found = str(local)
    if found:
        # Omarchy's PATH has ~/.local/share/../bin; resolve the directory, keep the name
        found = str(Path(found).parent.resolve() / Path(found).name)
        return Launcher((found, "run"), found)
    claude = shutil.which("claude", path=path)
    if claude:
        return Launcher(
            (claude,),
            None,
            "ai-provider not found; launching claude directly (provider switch ignored)",
        )
    raise LauncherError("neither ai-provider nor claude found on PATH")


def build_argv(
    launcher: Launcher,
    prompt: str,
    alias: str,
    *,
    session_id: str | None = None,
    resume: str | None = None,
    max_budget_usd: float | None = None,
    max_turns: int | None = None,
    permission_mode: str = PERMISSION_MODE,
    extra_args: Sequence[str] = (),
) -> list[str]:
    """Argument list for one headless session (never run through a shell).

    ``--verbose`` is required: Claude Code 2.1.310 exits 1 with "When using --print,
    --output-format=stream-json requires --verbose" without it.
    """
    if (session_id is None) == (resume is None):
        raise ValueError("exactly one of session_id and resume is required")
    argv = [
        *launcher.prefix,
        "-p",
        prompt,
        "--model",
        alias,
        "--permission-mode",
        permission_mode,
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    argv += ["--session-id", session_id] if session_id else ["--resume", str(resume)]
    if max_turns is not None:
        argv += ["--max-turns", str(max_turns)]
    if max_budget_usd is not None:
        argv += ["--max-budget-usd", f"{max_budget_usd:g}"]
    return argv + list(extra_args)


def build_env(base: Mapping[str, str] | None = None, *, auto: bool = True) -> dict[str, str]:
    """The child environment: ``PHX_AUTO=1``, and no inherited ``ANTHROPIC_MODEL`` (spec R2)."""
    env = dict(os.environ if base is None else base)
    env.pop("ANTHROPIC_MODEL", None)
    if auto:
        env["PHX_AUTO"] = "1"
    else:
        env.pop("PHX_AUTO", None)
    return env


# --- Provider snapshot ------------------------------------------------------------

Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class ProviderSnapshot:
    provider: str  # anthropic | openrouter | unknown
    mapped_model: str | None = None  # OpenRouter model behind the alias
    settings: dict[str, str] = field(default_factory=dict)  # allowlisted env, redacted
    error: str | None = None


def parse_provider_env(text: str) -> dict[str, str]:
    """Allowlisted, redacted ``NAME: value`` pairs from ``ai-provider env`` output."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        match = _EXPORT.match(line.strip())
        if not match or match.group(1) not in _ENV_ALLOWLIST:
            continue
        try:
            parts = shlex.split(match.group(2))
        except ValueError:
            continue
        out[match.group(1)] = redact_text(parts[0] if parts else "")
    return out


def provider_snapshot(
    launcher: Launcher,
    alias: str,
    *,
    env: Mapping[str, str] | None = None,
    run: Runner = subprocess.run,
) -> ProviderSnapshot:
    """Which provider the next launch will use and, on OpenRouter, the mapped model."""
    if launcher.ai_provider is None:
        return ProviderSnapshot("unknown", error="ai-provider missing")
    kwargs: dict[str, Any] = {"capture_output": True, "text": True, "timeout": 15, "env": env}
    try:
        got = run([launcher.ai_provider, "get"], **kwargs)
    except (OSError, subprocess.SubprocessError) as exc:
        return ProviderSnapshot("unknown", error=f"ai-provider get failed: {type(exc).__name__}")
    provider = got.stdout.strip() or "unknown"
    if got.returncode != 0 or provider not in ("anthropic", "openrouter"):
        return ProviderSnapshot("unknown", error=f"ai-provider get exited {got.returncode}")
    if provider != "openrouter":
        return ProviderSnapshot(provider)
    try:
        exported = run([launcher.ai_provider, "env"], **kwargs)
    except (OSError, subprocess.SubprocessError) as exc:
        return ProviderSnapshot(provider, error=f"ai-provider env failed: {type(exc).__name__}")
    # The raw output contains the OpenRouter key: parse the allowlist and drop the rest.
    settings = parse_provider_env(exported.stdout)
    del exported
    mapped = settings.get(f"ANTHROPIC_DEFAULT_{alias.upper()}_MODEL") or settings.get(
        "ANTHROPIC_MODEL"
    )
    return ProviderSnapshot(provider, mapped, settings)


# --- Usage accounting -------------------------------------------------------------


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    cost_usd: float | None = None
    duration_ms: int | None = None
    duration_api_ms: int | None = None
    num_turns: int | None = None
    models: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_result(cls, result: dict[str, Any] | None) -> "Usage":
        if not result:
            return cls()
        usage = result.get("usage") or {}

        def num(value: Any) -> int:
            return value if isinstance(value, int) and not isinstance(value, bool) else 0

        def opt(value: Any) -> int | None:
            return value if isinstance(value, int) and not isinstance(value, bool) else None

        cost = result.get("total_cost_usd")
        models = result.get("modelUsage")
        return cls(
            input_tokens=num(usage.get("input_tokens")),
            output_tokens=num(usage.get("output_tokens")),
            cache_creation_input_tokens=num(usage.get("cache_creation_input_tokens")),
            cache_read_input_tokens=num(usage.get("cache_read_input_tokens")),
            cost_usd=float(cost)
            if isinstance(cost, int | float) and not isinstance(cost, bool)
            else None,
            duration_ms=opt(result.get("duration_ms")),
            duration_api_ms=opt(result.get("duration_api_ms")),
            num_turns=opt(result.get("num_turns")),
            models=models if isinstance(models, dict) else {},
        )

    @classmethod
    def from_messages(
        cls, messages: Mapping[str, Mapping[str, Any]], result: dict[str, Any] | None
    ) -> "Usage":
        """``from_result``, or the sum of per-message usage when the result has no tokens.

        A stopped, killed or limit-hit session ends without a ``result`` event (or with one
        that reports zeros) although its turns spent tokens (Phase 10 pilot). ``messages``
        is the last ``usage`` seen per assistant message ID; cost stays the result's.
        """
        base = cls.from_result(result)
        if base.total_tokens or not messages:
            return base

        def total(key: str) -> int:
            return sum(v for u in messages.values() if isinstance(v := u.get(key), int) and v >= 0)

        return replace(
            base,
            input_tokens=total("input_tokens"),
            output_tokens=total("output_tokens"),
            cache_creation_input_tokens=total("cache_creation_input_tokens"),
            cache_read_input_tokens=total("cache_read_input_tokens"),
        )

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )


# --- Running a session ------------------------------------------------------------


@dataclass(frozen=True)
class Timeouts:
    idle_s: float = 1800.0
    wall_s: float = 21600.0
    term_grace_s: float = TERM_GRACE_S

    @classmethod
    def from_config(cls, config: Config) -> "Timeouts":
        return cls(float(config.idle_timeout_s), float(config.wall_timeout_s))


@dataclass
class SessionOutcome:
    phase: str
    session_id: str
    argv: list[str]
    transcript: Path
    exit_code: int | None
    classification: Classification
    usage: Usage
    provider: ProviderSnapshot
    started_at: float
    ended_at: float
    last_event_at: float | None
    events: int
    timed_out: str | None
    stderr_tail: str


def transcript_path(state: Path, phase: str) -> Path:
    """The next free ``sessions/<phase>-<n>.jsonl`` (n starts at 1)."""
    directory = sessions_dir(state)
    directory.mkdir(parents=True, exist_ok=True)
    n = 1
    while (directory / f"{phase}-{n}.jsonl").exists():
        n += 1
    return directory / f"{phase}-{n}.jsonl"


def _pump(stream: IO[str], tag: str, out: "queue.Queue[tuple[str, str | None]]") -> None:
    for line in stream:
        out.put((tag, line))
    out.put((tag, None))


def _kill_group(proc: subprocess.Popen[str], grace: float) -> None:
    """SIGTERM the session's process group, then SIGKILL after ``grace`` seconds."""
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 5.0)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=wait)
            return
        except subprocess.TimeoutExpired:
            continue


def run_session(
    *,
    repo: Path,
    state: Path,
    phase: str,
    prompt: str,
    alias: str,
    log: EventLog,
    config: Config | None = None,
    resume: str | None = None,
    launcher: Launcher | None = None,
    env: Mapping[str, str] | None = None,
    timeouts: Timeouts | None = None,
    max_turns: int | None = None,
    auto: bool = True,
    expect_result_line: bool = True,
    on_event: Callable[[dict[str, Any]], None] | None = None,
    permission_mode: str = PERMISSION_MODE,
    extra_args: Sequence[str] = (),
    cancel: threading.Event | None = None,
    on_start: Callable[[str], None] | None = None,
) -> SessionOutcome:
    """Run one session to its end and classify it.

    ``resume`` continues an earlier session ID; otherwise a fresh UUID is used.
    ``on_event`` is called for every parsed stream event (heartbeat for Phase 07).
    ``permission_mode`` and ``extra_args`` exist for the tool-less triage session (Phase 06).
    ``cancel`` (Phase 07, ``phx stop``): once set, the session's process group is stopped
    like a timeout and the session classifies as ``timeout`` with kind ``stopped``.
    ``on_start`` receives the session ID once the process has started.
    """
    config = config or Config()
    timeouts = timeouts or Timeouts.from_config(config)
    base_env = dict(os.environ if env is None else env)
    launcher = launcher or find_launcher(base_env)
    if launcher.warning:
        log.event("launcher_fallback", phase=phase, reason=launcher.warning)
    snapshot = provider_snapshot(launcher, alias, env=base_env)
    budget = config.max_budget_usd if snapshot.provider == "openrouter" else None
    session_id = resume or str(uuid.uuid4())
    argv = build_argv(
        launcher,
        prompt,
        alias,
        session_id=None if resume else session_id,
        resume=resume,
        max_budget_usd=budget,
        max_turns=max_turns,
        permission_mode=permission_mode,
        extra_args=extra_args,
    )
    transcript = transcript_path(state, phase)
    log.event(
        "launch",
        phase=phase,
        reason="resume" if resume else "fresh session",
        argv=argv,
        cwd=str(repo),
        session_id=session_id,
        transcript=str(transcript),
        provider=snapshot.provider,
        mapped_model=snapshot.mapped_model,
        provider_settings=snapshot.settings,
        provider_error=snapshot.error,
        max_budget_usd=budget,
        idle_timeout_s=timeouts.idle_s,
        wall_timeout_s=timeouts.wall_s,
    )

    started = time.monotonic()
    started_wall = time.time()
    proc = subprocess.Popen(
        argv,
        cwd=repo,
        env=build_env(base_env, auto=auto),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=True,  # own process group, so a timeout kills every child
    )
    lines: queue.Queue[tuple[str, str | None]] = queue.Queue()
    assert proc.stdout is not None and proc.stderr is not None
    pumps = [
        threading.Thread(target=_pump, args=(proc.stdout, "out", lines), daemon=True),
        threading.Thread(target=_pump, args=(proc.stderr, "err", lines), daemon=True),
    ]
    for pump in pumps:
        pump.start()
    if on_start is not None:
        on_start(session_id)

    stderr: deque[str] = deque(maxlen=_STDERR_LINES)
    recent: deque[dict[str, Any]] = deque(maxlen=_LAST_EVENTS)
    result: dict[str, Any] | None = None
    per_message: dict[str, Mapping[str, Any]] = {}
    last_event = started
    last_event_wall: float | None = None
    events = 0
    open_streams = 2
    timed_out: str | None = None
    fd: int | None = os.open(transcript, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        while open_streams:
            now = time.monotonic()
            if cancel is not None and cancel.is_set():
                timed_out = "stopped"
            elif now - started >= timeouts.wall_s:
                timed_out = "wall"
            elif now - last_event >= timeouts.idle_s:
                timed_out = "idle"
            if timed_out:
                log.event(
                    "stop" if timed_out == "stopped" else "timeout",
                    phase=phase,
                    reason=(
                        "stop requested; stopping process group"
                        if timed_out == "stopped"
                        else f"{timed_out} timeout; stopping process group"
                    ),
                )
                _kill_group(proc, timeouts.term_grace_s)
                break
            try:
                tag, line = lines.get(timeout=min(1.0, timeouts.idle_s, timeouts.wall_s) / 4)
            except queue.Empty:
                continue
            if line is None:
                open_streams -= 1
                continue
            if tag == "err":
                stderr.append(redact_text(line.rstrip("\n")))
                continue
            if fd is not None:
                data = (redact_text(line.rstrip("\n")) + "\n").encode()
                try:
                    if os.write(fd, data) != len(data):
                        raise OSError(errno.ENOSPC, "short write")
                except OSError as exc:  # full disk: keep the session, lose the copy
                    os.close(fd)
                    fd = None
                    log.event(
                        "transcript_write_failed",
                        phase=phase,
                        reason=f"{transcript} not written further ({exc.strerror or exc}); "
                        "the session continues",
                    )
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            last_event = time.monotonic()
            last_event_wall = time.time()
            events += 1
            recent.append(event)
            if event.get("type") == "result":
                result = event
            elif event.get("type") == "assistant":
                message = event.get("message")
                if isinstance(message, dict) and isinstance(message.get("usage"), dict):
                    per_message[str(message.get("id"))] = message["usage"]
            if on_event is not None:
                on_event(event)
    finally:
        if fd is not None:
            os.close(fd)
        # the transcript's mtime is "when PHX's session ended" (recover.last_session_end),
        # also when a full disk stopped the transcript early
        with contextlib.suppress(OSError):
            os.utime(transcript)
        try:
            exit_code: int | None = proc.wait(timeout=timeouts.term_grace_s + 5)
        except subprocess.TimeoutExpired:
            _kill_group(proc, timeouts.term_grace_s)
            exit_code = proc.returncode

    usage = Usage.from_messages(per_message, result)
    stderr_tail = "\n".join(stderr)
    classification = classify(
        exit_code,
        result,
        list(recent),
        stderr_tail,
        timed_out=timed_out,
        provider=snapshot.provider,
        expect_result_line=expect_result_line,
    )
    outcome = SessionOutcome(
        phase=phase,
        session_id=str(result.get("session_id") or session_id) if result else session_id,
        argv=argv,
        transcript=transcript,
        exit_code=exit_code,
        classification=classification,
        usage=usage,
        provider=snapshot,
        started_at=started_wall,
        ended_at=time.time(),
        last_event_at=last_event_wall,
        events=events,
        timed_out=timed_out,
        stderr_tail=stderr_tail,
    )
    log.event(
        "session_end",
        phase=phase,
        reason=classification.reason,
        session_id=outcome.session_id,
        exit_code=exit_code,
        events=events,
        duration_s=round(outcome.ended_at - started_wall, 1),
        tokens=usage.total_tokens,
        usage=redact(usage.__dict__),
        cost_usd=usage.cost_usd,
        stderr_tail=stderr_tail[-2000:] or None,
        **classification.as_log(),
    )
    return outcome


def probe(
    *,
    state: Path,
    log: EventLog,
    launcher: Launcher | None = None,
    env: Mapping[str, str] | None = None,
    timeouts: Timeouts | None = None,
) -> Classification:
    """Is capacity back? A minimal 1-turn ``haiku`` call through the same launcher (spec R8).

    Runs in the state directory (no repo context) and without ``PHX_AUTO``. A clean
    answer classifies as ``complete``; a limit as ``usage_limit``.
    """
    state.mkdir(parents=True, exist_ok=True)
    outcome = run_session(
        repo=state,
        state=state,
        phase="probe",
        prompt=PROBE_PROMPT,
        alias=PROBE_ALIAS,
        log=log,
        launcher=launcher,
        env=env,
        timeouts=timeouts or Timeouts(idle_s=300, wall_s=600),
        max_turns=1,
        auto=False,
        expect_result_line=False,
    )
    return outcome.classification
