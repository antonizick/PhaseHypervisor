"""Synthetic ``run.jsonl`` events for the report tests (Phase 12f).

``python tests/report_events.py`` rewrites ``tests/fixtures/report/``; a test checks the
files still match. Nothing here comes from a real project.
"""

import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures" / "report" / "state"
DAY = 86400.0
# Epochs in UTC, which the tests set as the local zone.
DEC_30_2025 = 1767052800.0
JAN_02_2026 = 1767312000.0
FEB_10_2026 = 1770681600.0
APR_02_2026 = 1775088000.0
JUN_30_2026 = 1782777600.0
JUL_01_2026 = 1782864000.0

Event = dict[str, Any]


def usage(
    model: str = "claude-opus-5-5",
    cost: float | None = 1.0,
    tokens: tuple[int, int, int, int] = (100, 200, 9000, 700),
    basis: str = "list",
) -> dict[str, Any]:
    entry = {
        "inputTokens": tokens[0],
        "outputTokens": tokens[1],
        "cacheReadInputTokens": tokens[2],
        "cacheCreationInputTokens": tokens[3],
        "costUSD": cost,
        "costBasis": basis,
    }
    return {model: entry}


def launch(
    phase: str,
    epoch: float,
    sid: str,
    *,
    alias: str = "opus",
    provider: str = "anthropic",
    idle: int = 1800,
    wall: int = 21600,
) -> Event:
    return {
        "epoch": epoch,
        "event": "launch",
        "phase": phase,
        "reason": "fresh session",
        "session_id": sid,
        "argv": ["ai-provider", "run", "--model", alias],
        "provider": provider,
        "idle_timeout_s": idle,
        "wall_timeout_s": wall,
    }


def end(
    phase: str,
    epoch: float,
    sid: str,
    *,
    cls: str = "complete",
    duration: float = 600.0,
    models: dict[str, Any] | None = None,
    cost: float | None = None,
    top: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> Event:
    if cost is None and models:
        known = [m["costUSD"] for m in models.values() if m["costUSD"] is not None]
        cost = sum(known) if known else None
    return {
        "epoch": epoch,
        "event": "session_end",
        "phase": phase,
        "reason": "",
        "session_id": sid,
        "duration_s": duration,
        "class": cls,
        "cost_usd": cost,
        "usage": {
            "input_tokens": top[0],
            "output_tokens": top[1],
            "cache_read_input_tokens": top[2],
            "cache_creation_input_tokens": top[3],
            "cost_usd": cost,
            "models": models or {},
        },
    }


def verify(phase: str, epoch: float, outcome: str = "complete") -> Event:
    return {"epoch": epoch, "event": "verify", "phase": phase, "reason": "", "outcome": outcome}


def simple(name: str, epoch: float, phase: str | None = None, **fields: Any) -> Event:
    return {"epoch": epoch, "event": name, "phase": phase, "reason": "", **fields}


def run_start(epoch: float, *, dry_run: bool = False, repo: str = "/repos/sample") -> Event:
    options = {"dry_run": dry_run}
    return simple("run_start", epoch, run_id=f"r{epoch:.0f}", repo=repo, options=options)


def run_end(epoch: float, status: str = "finished", rule: str = "all_complete") -> Event:
    return simple("run_end", epoch, status=status, rule=rule)


def phase_done(
    phase: str, epoch: float, sid: str, *, cost: float = 1.0, alias: str = "opus"
) -> list[Event]:
    """One clean first-attempt phase."""
    return [
        launch(phase, epoch, sid, alias=alias),
        end(phase, epoch + 600, sid, models=usage(cost=cost)),
        verify(phase, epoch + 610),
    ]


def alpha() -> list[Event]:
    """Two runs across a year and a quarter boundary, an empty month, and every oddity."""
    t = DEC_30_2025
    events = [run_start(t), *phase_done("01", t + 100, "s1", cost=2.0), run_end(t + 900)]
    t = JAN_02_2026
    events += [
        simple("dry_run", t, steps=[]),
        run_start(t - 500, dry_run=True),
        launch("99", t - 400, "ghost"),
        end("99", t - 300, "ghost", models=usage(cost=500.0)),
        run_end(t - 200),
        run_start(t),
        # A retry-heavy phase: a limit stop, a kill that reports nothing, a completion.
        launch("02", t + 100, "s2"),
        end("02", t + 700, "s2", cls="usage_limit", models=usage(cost=3.0)),
        simple("wait_start", t + 701, "02"),
        simple("wait_end", t + 4301, "02", waited_s=3600.0),
        simple("retry", t + 4302, "02"),
        launch("02", t + 4303, "s2"),
        simple("timeout", t + 5000, "02", reason="idle timeout; stopping process group"),
        end("02", t + 5001, "s2", cls="timeout", top=(10, 20, 3000, 40)),
        simple("retry", t + 5002, "02"),
        launch("02", t + 5003, "s2"),
        end(
            "02",
            t + 6000,
            "s2",
            models=usage(cost=7.0, tokens=(300, 500, 20000, 900)),
            top=(5, 6, 7, 8),
        ),
        verify("02", t + 6010),
        run_end(t + 6020, "paused", "review_gate"),
    ]
    t = APR_02_2026  # nothing at all in March
    events += [
        run_start(t),
        simple("resume", t, "02"),
        verify("02", t + 1),  # the resume reports it again
        *phase_done("03", t + 100, "s3", cost=4.0),
        run_end(t + 900),
    ]
    t = JUN_30_2026
    events += [
        run_start(t),
        launch("04", t + 100, "s4", alias="sonnet", provider="openrouter"),
        end(
            "04",
            t + 900,
            "s4",
            models=usage("vendor/other-model", cost=5.0, basis="unknown"),
        ),
        verify("04", t + 910),
        launch("05", t + 1000, "s5"),
        end("05", JUL_01_2026 + 60, "s5", cls="crash"),  # no cost known
        run_end(JUL_01_2026 + 120),
    ]
    return events


def beta() -> list[Event]:
    t = FEB_10_2026
    return [run_start(t), *phase_done("01", t + 100, "b1", cost=1.5), run_end(t + 900)]


def lines(events: list[Event]) -> str:
    return "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events)


def fixture_files() -> dict[str, str]:
    return {
        "alpha-project/run.jsonl": lines(alpha()) + '{"epoch": 17, "event": "trunca',
        "beta-project/run.jsonl": lines(beta()),
        "phx-pilot/run.jsonl": lines(phase_done("01", FEB_10_2026, "p1", cost=100.0)),
    }


if __name__ == "__main__":
    for name, text in fixture_files().items():
        path = FIXTURES / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
