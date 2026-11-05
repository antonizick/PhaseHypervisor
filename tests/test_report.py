"""``phx report``: loader, attribution, periods, rules and every output mode (Phase 12f)."""

import hashlib
import json
import os
import stat
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import report_events as ev
from phx.cli import COMMANDS, main
from phx.report import load as L
from phx.report import model as M
from phx.report import projects as P
from phx.report import render as R
from phx.report import rules as RU
from phx.report import svg as S
from phx.vault import vault_root
from report_events import DAY

STATE = ev.FIXTURES
NOTE = "not enough data"


@pytest.fixture(autouse=True)
def utc(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def report(*groups: list[ev.Event], **kw: Any) -> M.Report:
    return M.build([L.Source(f"p{i}", g) for i, g in enumerate(groups)], **kw)


def clean(events: list[ev.Event]) -> list[ev.Event]:
    """What the loader keeps of ``events``."""
    return L.parse_lines(ev.lines(events).splitlines(), "x")[0]


def fixture_report(**kw: Any) -> M.Report:
    return M.build([L.Source("alpha", clean(ev.alpha())), L.Source("beta", ev.beta())], **kw)


def test_fixture_files_match_the_builder() -> None:
    for name, text in ev.fixture_files().items():
        assert (STATE / name).read_text(encoding="utf-8") == text


# --- Loader --------------------------------------------------------------------------


def test_truncated_last_line_is_tolerated() -> None:
    loaded = L.load(STATE, ["alpha-project"])
    assert loaded.sources[0].events
    assert loaded.warnings == ["alpha-project: ignored a truncated last line"]


def test_bad_inner_lines_and_unknown_events_are_counted_not_fatal() -> None:
    lines = ['{"event": "x"', '"text"', '{"event": "new_thing", "epoch": 1, "extra": {}}', "{}"]
    events, warnings = L.parse_lines([*lines, ""], "p")
    assert [e["event"] for e in events] == ["new_thing"]
    assert warnings == ["p: skipped 3 unreadable line(s)"]


def test_dry_runs_never_count() -> None:
    events = clean(ev.alpha())
    assert not any(e["event"] == "dry_run" or e["phase"] == "99" for e in events)
    assert not any(e.get("options", {}).get("dry_run") for e in events)


def test_symlinks_are_skipped(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "run.jsonl").write_text(ev.lines(ev.beta()))
    root = tmp_path / "root"
    (root / "real").mkdir(parents=True)
    (root / "real" / "run.jsonl").symlink_to(outside / "run.jsonl")
    (root / "linked").symlink_to(outside)
    assert L.projects(root) == []
    loaded = L.load(root, ["real", "linked"])
    assert loaded.sources == []
    assert len(loaded.warnings) == 2


def test_missing_root_has_no_projects(tmp_path: Path) -> None:
    assert L.projects(tmp_path / "nope") == []


# --- Attribution ---------------------------------------------------------------------


def test_resumed_session_is_charged_its_increase() -> None:
    t = ev.DEC_30_2025
    first = ev.usage(cost=3.0, tokens=(10, 20, 300, 40))
    second = {
        **ev.usage(cost=3.0, tokens=(10, 20, 300, 40)),
        **ev.usage("other", cost=2.0, tokens=(1, 2, 3, 4), basis="unknown"),
    }
    r = report(
        [
            ev.launch("01", t, "s"),
            ev.end("01", t + 1, "s", cls="usage_limit", models=first),
            ev.launch("01", t + 2, "s", provider="openrouter"),
            ev.end("01", t + 3, "s", models=second, top=(9, 9, 9, 9)),
        ]
    )
    assert r.totals.cost_usd == 5.0
    assert r.totals.repeated_cost_usd == 3.0
    assert r.totals.unverified_cost_usd == 2.0
    assert r.totals.tokens.total == 370 + 10
    assert r.by_provider["openrouter"].cost_usd == 2.0
    assert r.by_model["other"].tokens.total == 10


def test_tokens_of_a_killed_run_are_not_counted_twice() -> None:
    r = fixture_report(until="2026-01")
    two = next(p for p in r.phases if p.phase == "02").totals
    assert two.tokens.input == 300 and two.tokens.cache_read == 20000  # the final totals
    assert two.cost_usd == 7.0
    assert two.sessions_without_cost == 1


def test_a_limit_placeholder_is_no_snapshot() -> None:
    t = ev.DEC_30_2025
    placeholder = ev.usage(cost=0.0, tokens=(0, 0, 0, 0))
    r = report([ev.end("01", t, "s", cls="usage_limit", models=placeholder, top=(5, 5, 5, 5))])
    assert r.totals.tokens.total == 20
    assert r.totals.cost_usd is None
    assert r.totals.sessions_without_cost == 1


def test_cost_without_a_model_breakdown_is_an_increase_too() -> None:
    t = ev.DEC_30_2025
    r = report(
        [
            ev.launch("01", t, "s"),
            ev.end("01", t, "s", cost=2.0),
            ev.end("01", t + 1, "s", cost=5.0),
        ]
    )
    assert r.totals.cost_usd == 5.0
    assert r.totals.repeated_cost_usd == 2.0
    assert "opus (alias)" in r.by_model
    assert r.totals.unverified_cost_usd == 5.0


def test_a_resume_that_adds_nothing_keeps_a_known_zero() -> None:
    t = ev.DEC_30_2025
    same = ev.usage(cost=2.0)
    r = report([ev.end("01", t, "s", models=same), ev.end("01", t + 1, "s", models=same)])
    assert r.totals.cost_usd == 2.0
    assert r.totals.sessions_without_cost == 0
    assert r.totals.repeated_cost_usd == 2.0


def test_old_records_without_cost_basis() -> None:
    t = ev.DEC_30_2025
    models = {
        "claude-opus-5-5": {"inputTokens": 1, "costUSD": 1.0},
        "vendor/x": {"inputTokens": 1, "costUSD": 1.0},
        7: "junk",
    }
    event = ev.end("01", t, "s", models=models, cost=2.0)
    assert report([event]).totals.unverified_cost_usd == 1.0


def test_a_window_does_not_break_the_chain() -> None:
    r = fixture_report(since="2026-01-01", until="2026-01-31")
    assert r.totals.cost_usd == 7.0  # all of s2, no other phase
    t = ev.DEC_30_2025
    events = [
        ev.end("01", t, "s", models=ev.usage(cost=1.0)),
        ev.end("01", ev.FEB_10_2026, "s", models=ev.usage(cost=4.0)),
    ]
    assert report(events, since="2026-02").totals.cost_usd == 3.0


# --- Aggregation ---------------------------------------------------------------------


def test_fixture_totals() -> None:
    t = fixture_report().totals
    assert t.sessions == 8
    assert t.cost_usd == 2 + 7 + 4 + 5 + 1.5
    assert t.unverified_cost_usd == 5.0
    assert t.sessions_without_cost == 2  # the killed run and the crash, never $0
    assert t.phases_completed == 5  # the resume's second verify adds none
    assert t.first_attempt == 4
    assert (t.retries, t.timeouts) == (2, 1)
    assert t.wait_s == 3600.0
    assert t.gate_pauses == 1
    assert t.noncompleting_sessions == 3
    assert t.runs == 5


@pytest.mark.parametrize("attr", ["by_project", "by_model", "by_provider"])
def test_every_grouping_adds_up(attr: str) -> None:
    r = fixture_report()
    rows = list(getattr(r, attr).values())
    assert sum(t.cost_usd or 0.0 for t in rows) == pytest.approx(r.totals.cost_usd)
    assert sum(t.tokens.total for t in rows) == r.totals.tokens.total
    assert sum(t.sessions for t in rows) == r.totals.sessions
    assert sum(t.active_s for t in rows) == r.totals.active_s
    assert sum(t.phases_completed for t in rows) == r.totals.phases_completed


@pytest.mark.parametrize("by", M.PERIODS)
def test_periods_add_up(by: str) -> None:
    r = fixture_report(by=by)
    rows = [p.totals for p in r.periods]
    assert sum(t.cost_usd or 0.0 for t in rows) == pytest.approx(r.totals.cost_usd)
    assert sum(t.sessions for t in rows) == r.totals.sessions
    assert sum(sum(p.models.values()) for p in r.periods) == pytest.approx(r.totals.cost_usd)


def test_completion_after_interrupted_verification() -> None:
    t = ev.DEC_30_2025
    events = [
        ev.end("01", t, "s", models=ev.usage()),
        ev.verify("01", t + 1, "failed"),
        ev.simple("session_dropped", t + 2, "01", reason="phase 01 is ✅ Complete"),
        ev.simple("session_dropped", t + 3, "01", reason="phase 01 is ✅ Complete"),
    ]
    assert report(events).totals.phases_completed == 1


def test_failed_verification_is_not_a_completion() -> None:
    t = ev.DEC_30_2025
    r = report([ev.end("01", t, "s", models=ev.usage()), ev.verify("01", t + 1, "failed")])
    assert r.totals.phases_completed == 0


def test_a_wait_stopped_and_never_resumed_ends_at_the_stop() -> None:
    t = ev.DEC_30_2025
    r = report([ev.simple("wait_start", t, "01"), ev.simple("wait_stopped", t + 60, "01")])
    assert r.totals.wait_s == 60.0
    assert r.open_spans == 0


def test_open_waits_and_pauses_are_not_counted() -> None:
    t = ev.DEC_30_2025
    r = report([ev.simple("wait_start", t, "01"), ev.run_end(t + 5, "paused", "blocked")])
    assert r.totals.wait_s == 0
    assert r.open_spans == 2


def test_a_wait_end_without_waited_s_uses_the_span() -> None:
    t = ev.DEC_30_2025
    r = report([ev.simple("wait_start", t, "01"), ev.simple("wait_end", t + 9, "01")])
    assert r.totals.wait_s == 9.0


def test_other_pauses_are_kept_apart_from_gates() -> None:
    t = ev.DEC_30_2025
    r = report([ev.run_end(t, "paused", "blocked"), ev.run_start(t + 100)])
    assert (r.totals.other_pause_s, r.totals.gate_pause_s) == (100.0, 0.0)


# --- Periods -------------------------------------------------------------------------


def test_month_buckets_show_empty_months_and_cross_a_year() -> None:
    r = fixture_report()
    assert [p.label for p in r.periods] == [
        "2025-12",
        "2026-01",
        "2026-02",
        "2026-03",
        "2026-04",
        "2026-05",
        "2026-06",
        "2026-07",
    ]
    empty = r.periods[3]
    assert not empty.totals.has_data
    assert all(v is None for v in empty.change.values())


def test_quarters_and_years() -> None:
    assert [p.label for p in fixture_report(by="quarter").periods] == [
        "2025-Q4",
        "2026-Q1",
        "2026-Q2",
        "2026-Q3",
    ]
    assert [p.label for p in fixture_report(by="year").periods] == ["2025", "2026"]


def test_buckets_use_the_local_zone(monkeypatch: pytest.MonkeyPatch) -> None:
    epoch = ev.JUL_01_2026 + 60  # 1 July in UTC, still 30 June in Chicago
    assert M.bucket(epoch, "month") == "2026-07"
    monkeypatch.setenv("TZ", "America/Chicago")
    time.tzset()
    assert M.bucket(epoch, "month") == "2026-06"
    assert M.bucket(epoch, "quarter") == "2026-Q2"


def test_change_is_na_without_a_real_base() -> None:
    assert M.change(5.0, None) is None
    assert M.change(5.0, 0.0) is None
    assert M.change(None, 5.0) is None
    assert M.change(15.0, 10.0) == 0.5


def test_change_after_an_empty_period_is_na() -> None:
    r = fixture_report()
    april = next(p for p in r.periods if p.label == "2026-04")
    assert april.change["cost_usd"] is None
    january = next(p for p in r.periods if p.label == "2026-01")
    assert january.change["cost_usd"] == pytest.approx(2.5)


@pytest.mark.parametrize(
    ("text", "end", "expected"),
    [
        ("2026-01-02", False, ev.JAN_02_2026),
        ("2026-01-01", True, ev.JAN_02_2026),
        ("2026-Q3", False, ev.JUL_01_2026),
        ("2026-Q2", True, ev.JUL_01_2026),
        ("2026-06", True, ev.JUL_01_2026),
        ("2026", False, 1767225600.0),
    ],
)
def test_bounds(text: str, end: bool, expected: float) -> None:
    assert M.parse_bound(text, end=end) == expected


@pytest.mark.parametrize("text", ["soon", "2026-13", "2026-Q5", "2026-02-30", "26", "1-2-3-4"])
def test_bad_bounds(text: str) -> None:
    with pytest.raises(ValueError, match="bad date"):
        M.parse_bound(text, end=False)


def test_since_after_until() -> None:
    with pytest.raises(ValueError, match="after --until"):
        fixture_report(since="2026-05", until="2026-01")


# --- Rules ---------------------------------------------------------------------------


def done(
    phase: str, day: int, cost: float, alias: str = "opus", dur: float = 600.0
) -> list[ev.Event]:
    t = ev.JAN_02_2026 + day * DAY
    sid = f"s{phase}"
    return [
        ev.launch(phase, t, sid, alias=alias),
        ev.end(phase, t + 1, sid, models=ev.usage(cost=cost), duration=dur),
        ev.verify(phase, t + 2),
    ]


def many(n: int, cost: float = 1.0, **kw: Any) -> list[ev.Event]:
    return [e for i in range(n) for e in done(f"{i:02d}", i, cost, **kw)]


def fired(result: RU.Result) -> list[RU.Recommendation]:
    return result[0]


def test_r1_fires_silent_and_short() -> None:
    fires = RU.r1_cost_concentration(report([*many(5), *done("90", 9, 30.0)]))
    (rec,) = fired(fires)
    assert rec.id == "R1"
    assert "p0 90: $30.00" in rec.evidence[0]
    assert "median $1.00" in rec.evidence[0]
    assert "3x" in rec.threshold
    assert fired(RU.r1_cost_concentration(report(many(6)))) == []
    recs, notes = RU.r1_cost_concentration(report(many(4)))
    assert recs == []
    assert notes == [f"{NOTE} for R1 on claude-opus-5-5 (4 phases, needs 5)"]


def test_r1_reads_the_table(monkeypatch: pytest.MonkeyPatch) -> None:
    events = [*many(5), *done("90", 9, 30.0)]
    monkeypatch.setitem(RU.THRESHOLDS, "r1_cost_multiple", RU.Threshold(100, "test"))
    assert fired(RU.r1_cost_concentration(report(events))) == []


def lost(phase: str, day: int, cls: str = "timeout", cost: float = 5.0) -> list[ev.Event]:
    t = ev.JAN_02_2026 + day * DAY
    return [ev.end(phase, t, f"x{phase}", cls=cls, models=ev.usage(cost=cost), duration=900)]


def test_r2_fires_silent_and_short() -> None:
    (rec,) = fired(RU.r2_noncompleting(report([*many(9), *lost("50", 1), *lost("51", 2)])))
    assert rec.id == "R2"
    assert "2 of 11 sessions did not complete: 2 timeout" in rec.evidence[0]
    assert "53%" in rec.evidence[1]
    assert rec.evidence[2].startswith("p0 50")
    assert ">= 20%" in rec.threshold
    assert fired(RU.r2_noncompleting(report(many(12)))) == []
    assert RU.r2_noncompleting(report(many(3)))[1] == [f"{NOTE} for R2 (3 sessions, needs 10)"]


def test_r3_strongest_may_step_down() -> None:
    events = [*many(5, 10.0, dur=3000.0), *done("80", 7, 1.0)]
    recs = fired(RU.r3_model_fit(report(events)))
    assert len(recs) == 1
    assert "1 phase on the strongest model quick and cheap" in recs[0].title
    assert "may suffice" in recs[0].action
    assert "plan" in recs[0].action
    assert "p0 80: $1.00" in recs[0].evidence[0]
    assert fired(RU.r3_model_fit(report(many(6, 10.0, dur=3000.0)))) == []


def test_r3_ignores_phases_with_no_known_price() -> None:
    t = ev.JAN_02_2026
    model = ev.usage("vendor/x", cost=1.0, basis="unknown")
    events = [ev.launch("80", t, "u"), ev.end("80", t, "u", models=model), ev.verify("80", t)]
    assert fired(RU.r3_model_fit(report([*many(5, 10.0, dur=3000.0), *events]))) == []


def test_r3_balanced_may_step_up() -> None:
    t = ev.JAN_02_2026
    trouble = [ev.launch("70", t, "b", alias="sonnet")]
    trouble += [ev.end("70", t + i, "b", cls="timeout", models=ev.usage()) for i in (1, 2)]
    recs = fired(RU.r3_model_fit(report([*many(5, alias="sonnet"), *trouble])))
    (rec,) = [r for r in recs if "balanced" in r.title]
    assert "2 non-completing" in rec.evidence[0]
    assert "may save money" in rec.action


def test_r3_short_of_data_says_so() -> None:
    recs, notes = RU.r3_model_fit(report(many(2)))
    assert recs == []
    assert notes == [
        f"{NOTE} for R3 (strongest model) (2 phases, needs 5)",
        f"{NOTE} for R3 (balanced model) (0 phases, needs 5)",
    ]


def cache(n: int, read: int) -> list[ev.Event]:
    t = ev.JAN_02_2026
    model = ev.usage(tokens=(100_000, 1000, read, 100_000))
    return [e for i in range(n) for e in [ev.end(f"{i}", t + i, f"c{i}", models=model)]]


def test_r4_fires_silent_and_short() -> None:
    (rec,) = fired(RU.r4_cache(report(cache(10, 10_000))))
    assert "Low cache-read share on claude-opus-5-5" in rec.title
    assert "5% of input" in rec.evidence[0]
    assert fired(RU.r4_cache(report(cache(10, 9_000_000)))) == []
    assert RU.r4_cache(report(cache(2, 10)))[1] == [
        f"{NOTE} for R4 on claude-opus-5-5 (2 sessions, needs 5)"
    ]


def test_r4_ignores_tiny_totals() -> None:
    t = ev.JAN_02_2026
    model = ev.usage(tokens=(100, 10, 10, 10))
    events = [ev.end(f"{i}", t + i, f"c{i}", models=model) for i in range(6)]
    assert fired(RU.r4_cache(report(events))) == []


def waits(n: int, seconds: float = 7200.0) -> list[ev.Event]:
    out = []
    for i in range(n):
        t = ev.JAN_02_2026 + i * 7 * DAY + 3600  # Fridays, 01:00
        out += [
            ev.simple("wait_start", t, f"{i}"),
            ev.simple("wait_end", t + seconds, f"{i}", waited_s=seconds),
        ]
    return out


def test_r5_waits_with_a_pattern() -> None:
    (rec,) = fired(RU.r5_waiting(report([*many(1), *waits(5)])))
    assert "5 waits took 10h 00m" in rec.evidence[0]
    assert "5 of 5 waits started in 00:00-06:00" in rec.evidence[1]
    assert "5 of 5 waits started in Friday" in rec.evidence[1]


def test_r5_too_few_waits_have_no_pattern_line() -> None:
    (rec,) = fired(RU.r5_waiting(report(waits(3))))
    assert len(rec.evidence) == 1


def test_r5_mixed_times_have_no_pattern() -> None:
    assert RU._wait_pattern([ev.JAN_02_2026 + i * (DAY + 6 * 3600) for i in range(8)]) is None


def test_r5_silent_and_short() -> None:
    quiet = [*many(1, dur=360000.0), *waits(3, 60.0)]
    assert fired(RU.r5_waiting(report(quiet))) == []
    assert RU.r5_waiting(report(many(1)))[1] == [
        f"{NOTE} for R5 (waits) (0 waits, needs 3)",
        f"{NOTE} for R5 (gates) (0 pauses at gates, needs 3)",
    ]


def gates(n: int, seconds: float) -> list[ev.Event]:
    out = []
    for i in range(n):
        t = ev.JAN_02_2026 + i * 10 * DAY
        out += [ev.run_end(t, "paused", "review_gate"), ev.run_start(t + seconds)]
    return out


def test_r5_gate_pauses() -> None:
    (rec,) = fired(RU.r5_waiting(report(gates(3, 86400.0))))
    assert "3 gate pauses, median 24h 00m" in rec.evidence[0]
    assert fired(RU.r5_waiting(report(gates(3, 600.0)))) == []


def killed(n: int, *, finish: bool = True, duration: float = 1900.0) -> list[ev.Event]:
    t = ev.JAN_02_2026
    out = []
    for i in range(n):
        out += [
            ev.launch(f"{i}", t + i, f"k{i}"),
            ev.simple("timeout", t + i, f"{i}", reason="idle timeout; stopping process group"),
            ev.end(f"{i}", t + i, f"k{i}", cls="timeout", duration=duration),
        ]
        if finish:
            out += [ev.end(f"{i}", t + i + 1, f"k{i}", models=ev.usage()), ev.verify(f"{i}", t + i)]
    return out


def test_r6_idle_too_tight() -> None:
    (rec,) = fired(RU.r6_timeouts(report(killed(3))))
    assert "3 sessions were killed idle (limit 30m); 3 of those 3 phases" in rec.evidence[0]
    assert "idle_timeout_s" in rec.action


def test_r6_real_hangs_stay_silent() -> None:
    assert fired(RU.r6_timeouts(report(killed(3, finish=False)))) == []
    assert fired(RU.r6_timeouts(report(killed(2)))) == []


def test_r6_wall_cap_reached() -> None:
    t = ev.JAN_02_2026
    events = [
        ev.launch("01", t, "w", wall=1000),
        ev.simple("timeout", t, "01", reason="wall timeout; stopping process group"),
        ev.end("01", t, "w", cls="timeout", duration=1000.0),
        ev.launch("02", t, "n", wall=1000),
        ev.end("02", t, "n", duration=950.0),
    ]
    (rec,) = fired(RU.r6_timeouts(report(events)))
    assert len(rec.evidence) == 2
    assert "wall_timeout_s" in rec.action
    assert report(events).sessions[0].timed_out == "wall"


def test_r6_loose_cap() -> None:
    (rec,) = fired(RU.r6_timeouts(report(many(20))))
    assert "longest of 20 sessions 10m" in rec.evidence[0]
    assert fired(RU.r6_timeouts(report(many(20, dur=10000.0)))) == []
    assert RU.r6_timeouts(report(many(4)))[1] == [
        f"{NOTE} for R6 (wall cap) (4 sessions, needs 20)"
    ]


def month(n: int, cost: float) -> list[ev.Event]:
    t = ev.JAN_02_2026 + n * 31 * DAY
    out = []
    for i in range(3):
        sid = f"m{n}{i}"
        out += [
            ev.launch(f"{n}{i}", t, sid),
            ev.end(f"{n}{i}", t + 1, sid, models=ev.usage(cost=cost)),
        ]
        out.append(ev.verify(f"{n}{i}", t + 2))
    return out


def test_r7_fires_silent_and_short() -> None:
    rising = [*month(0, 1.0), *month(1, 2.0), *month(2, 4.0)]
    (rec,) = fired(RU.r7_trend(report(rising)))
    assert rec.evidence == ("2026-01: $1.00", "2026-02: $2.00", "2026-03: $4.00")
    flat = [*month(0, 1.0), *month(1, 2.0), *month(2, 2.0)]
    assert fired(RU.r7_trend(report(flat))) == []
    assert RU.r7_trend(report(month(0, 1.0)))[1] == [f"{NOTE} for R7 (1 period usable, needs 3)"]


def provider(name: str, n: int, bad: int) -> list[ev.Event]:
    t = ev.JAN_02_2026
    out = []
    for i in range(n):
        sid = f"{name}{i}"
        cls = "timeout" if i < bad else "complete"
        out += [ev.launch("1", t, sid, provider=name), ev.end("1", t, sid, cls=cls)]
    return out


def test_r8_fires_silent_and_short() -> None:
    (rec,) = fired(RU.r8_providers(report([*provider("a", 10, 0), *provider("b", 10, 5)])))
    assert "more often on a than on b" in rec.title
    assert "may" not in rec.title
    assert "not a verdict" in rec.action
    assert fired(RU.r8_providers(report([*provider("a", 10, 0), *provider("b", 10, 1)]))) == []
    assert RU.r8_providers(report(provider("a", 10, 0)))[1] == [
        f"{NOTE} for R8 (1 provider with a fair sample, needs 2)"
    ]


def test_every_threshold_has_a_reason_and_is_used() -> None:
    source = Path(RU.__file__).read_text(encoding="utf-8")
    for name, threshold in RU.THRESHOLDS.items():
        assert threshold.reason
        assert f'"{name}"' in source.split("def limit")[1], name


def test_evaluate_collects_every_rule() -> None:
    recs, notes = RU.evaluate(fixture_report())
    assert all(any(f"for {rule} " in n for n in notes) for rule in ("R2", "R7", "R8"))
    assert all(r.evidence and r.action and r.threshold for r in recs)


# --- Rendering -----------------------------------------------------------------------


def test_text_has_caveats_trends_and_no_ansi() -> None:
    r = fixture_report()
    recs, notes = RU.evaluate(r)
    text = R.to_text(r, recs, notes)
    assert "\033" not in text
    for needle in (
        "Manual /phase sessions",
        "not an invoice",
        "$5.00 of it has no known price",
        "2 session(s) have unknown cost",
        "$3.00 that repeats earlier runs",
        "no data",
        "n/a",
        "▲",
        "Recommendations",
    ):
        assert needle in text, needle
    assert "\033[1m" in R.to_text(r, recs, notes, color=True)


def test_top_limits_rows() -> None:
    r = fixture_report()
    assert R._usage_rows(r.by_project, 1)[0][0] == "alpha"
    assert len(R._usage_rows(r.by_project, 1)) == 1


def test_nothing_fired_is_stated() -> None:
    assert "Nothing crossed a threshold." in R.to_text(report(many(1)), [], [])


def test_unknown_cost_is_never_dollars_zero() -> None:
    assert RU.money(None) == "unknown"
    t = ev.JAN_02_2026
    text = R.to_text(report([ev.end("01", t, "s", cls="crash")]), [], [])
    assert "$0.00" not in text


def test_markdown_has_tables_and_caveats() -> None:
    r = fixture_report()
    recs, notes = RU.evaluate(r)
    text = R.to_markdown(r, recs, notes, links={"alpha": "Alpha Note"})
    assert text.startswith("# PHX report")
    assert "| Period | Cost |" in text
    assert "[[Alpha Note]]" in text
    assert "not an invoice" in text
    assert "Manual /phase sessions" in text


def test_json_schema() -> None:
    r = fixture_report(by="quarter")
    recs, notes = RU.evaluate(r)
    data = json.loads(R.to_json(r, recs, notes))
    assert data["schema"] == 1
    assert set(data) == {
        "schema",
        "scope",
        "caveats",
        "totals",
        "periods",
        "models",
        "providers",
        "projects",
        "phases",
        "recommendations",
        "not_enough_data",
        "thresholds",
        "warnings",
    }
    assert data["totals"]["cost_usd"] == r.totals.cost_usd
    assert data["totals"]["tokens"]["total"] == r.totals.tokens.total
    assert data["periods"][0]["period"] == "2025-Q4"
    assert data["thresholds"]["r2_share"]["value"] == 0.2
    assert sum(p["sessions"] for p in data["periods"]) == data["totals"]["sessions"]


def test_svg_is_valid_deterministic_and_marks_empty_periods(tmp_path: Path) -> None:
    first = S.write_charts(fixture_report(), tmp_path / "a")
    second = S.write_charts(fixture_report(), tmp_path / "b")
    assert len(first) == 4
    for a, b in zip(first, second, strict=True):
        assert a.read_bytes() == b.read_bytes()
        root = ET.fromstring(a.read_text(encoding="utf-8"))
        assert root.get("width") == "830"
        text = a.read_text(encoding="utf-8")
        assert "prefers-color-scheme: dark" in text
        assert "no data" in text
        assert "data through" in text
    assert "not an invoice" in (tmp_path / "a" / "phx-report-cost.svg").read_text()
    assert "no known price" in (tmp_path / "a" / "phx-report-cost.svg").read_text()


def test_more_models_than_slots_fold_into_other() -> None:
    t = ev.JAN_02_2026
    events = [
        ev.end("1", t + i, f"s{i}", models=ev.usage(f"model-{i}", cost=i + 1.0)) for i in range(7)
    ]
    chart = S.model_mix_chart(report(events))
    assert 'class="so"' in chart
    assert "Other" in chart
    assert S.model_names(report(events))[0] == "model-6"


def test_axis_tops() -> None:
    assert S._nice_top(7.0) == 10
    assert S._nice_top(355.0) == 500
    assert S._nice_top(0.3) == pytest.approx(0.5)
    assert S._nice_top(12.0) == 20


# --- Vault ---------------------------------------------------------------------------


def test_vault_note_is_new_every_time(tmp_path: Path) -> None:
    r = fixture_report()
    env = {"PHX_VAULT_ROOT": str(tmp_path)}
    kwargs: dict[str, Any] = {"top": 5, "repos": P.Repos(), "env": env, "now": ev.JAN_02_2026}
    first, _ = R.write_vault(r, [], [], **kwargs)
    second, _ = R.write_vault(r, [], [], **kwargs)
    assert first is not None and second is not None
    assert first.name == "PHX Report 2026-01-02 0000.md"
    assert second.name == "PHX Report 2026-01-02 0000 (2).md"
    assert first.parent == tmp_path / "04 Resources" / "PHX Reports"
    assert first.read_text().startswith("---\ntags: [phx, report]\nupdated: 2026-01-02 00:00 UTC")


def test_vault_missing_is_a_message(tmp_path: Path) -> None:
    path, message = R.write_vault(
        fixture_report(),
        [],
        [],
        top=5,
        repos=P.Repos(),
        env={"PHX_VAULT_ROOT": str(tmp_path / "none")},
    )
    assert path is None
    assert "PHX_VAULT_ROOT" in message


def test_vault_links_only_notes_that_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "Alpha.md"
    note.write_text("x")
    paths = {"yes": note, "gone": vault / "Gone.md", "out": tmp_path / "Out.md"}
    monkeypatch.setattr(R, "note_path", lambda repo: paths.get(repo.name))
    repos = {name: Path("/r") / name for name in [*paths, "none"]}
    assert R.project_links(repos, vault) == {"yes": "Alpha"}


# --- CLI -----------------------------------------------------------------------------


def run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = main(["report", "--state-root", str(STATE), *argv])
    out, err = capsys.readouterr()
    return code, out, err


def test_registered() -> None:
    assert COMMANDS["report"][1] == "12f"


def test_default_leaves_the_pilot_out(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run([], capsys)
    assert code == 0
    assert "2 project(s)" in out
    assert "phx-pilot" not in out
    assert "\033" not in out
    assert "ignored a truncated last line" in out


def test_all_and_named_include_the_pilot(capsys: pytest.CaptureFixture[str]) -> None:
    assert "phx-pilot" in run(["--all"], capsys)[1]
    assert "1 project(s)" in run(["phx-pilot"], capsys)[1]


def test_exclude(capsys: pytest.CaptureFixture[str]) -> None:
    _, out, _ = run(["--exclude", "beta-project"], capsys)
    assert "1 project(s)" in out
    assert "beta-project" not in out


def test_named_by_path(capsys: pytest.CaptureFixture[str]) -> None:
    assert "1 project(s)" in run(["/some/where/beta-project"], capsys)[1]


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--since", "2026-05", "--until", "2026-01"], "after --until"),
        (["--since", "soon"], "bad date"),
        (["nope"], "no run log for: nope"),
        (["alpha-project", "--all"], "not both"),
        (["--top", "0"], "--top"),
    ],
)
def test_errors(argv: list[str], message: str, capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(argv, capsys)
    assert code != 0
    assert message in err


@pytest.mark.parametrize("by", M.PERIODS)
def test_json_mode(by: str, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(["--by", by, "--json"], capsys)
    assert code == 0
    assert json.loads(out)["scope"]["by"] == by


def test_markdown_modes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["--markdown"], capsys)[1].startswith("# PHX report")
    path = tmp_path / "r.md"
    code, out, err = run(["--markdown", str(path)], capsys)
    assert (code, out) == (0, "")
    assert "not an invoice" in path.read_text()
    assert str(path) in err


def test_svg_mode(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run(["--svg", str(tmp_path / "charts")], capsys)
    assert len(list((tmp_path / "charts").glob("*.svg"))) == 4


def test_vault_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PHX_VAULT_ROOT", str(tmp_path / "none"))
    assert "note skipped" in run(["--vault"], capsys)[2]
    monkeypatch.setenv("PHX_VAULT_ROOT", str(tmp_path))
    assert "wrote" in run(["--vault"], capsys)[2]
    assert len(list((tmp_path / "04 Resources" / "PHX Reports").glob("*.md"))) == 1


def test_empty_state_root(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["report", "--state-root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "no recorded runs" in out


def test_unreadable_file_warns_and_reports_the_rest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for name, events in (("good", ev.beta()), ("bad", ev.beta())):
        (tmp_path / name).mkdir()
        (tmp_path / name / "run.jsonl").write_text(ev.lines(events))
    (tmp_path / "bad" / "run.jsonl").chmod(0)
    try:
        code = main(["report", "--state-root", str(tmp_path)])
    finally:
        (tmp_path / "bad" / "run.jsonl").chmod(0o600)
    out = capsys.readouterr().out
    assert code == 0
    assert "bad: run.jsonl not read (PermissionError)" in out
    assert "$1.50" in out


def test_never_writes_under_the_state_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "state"
    for name, text in ev.fixture_files().items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)

    def digest() -> dict[str, str]:
        return {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*"))
            if p.is_file()
        }

    before = digest()
    for path in [root, *root.rglob("*")]:
        path.chmod(path.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    try:
        out = tmp_path / "out"
        assert main(["report", "--state-root", str(root), "--svg", str(out), "--json"]) == 0
    finally:
        for path in [root, *root.rglob("*")]:
            path.chmod(path.stat().st_mode | stat.S_IWUSR)
    capsys.readouterr()
    assert digest() == before


def test_global_state_dir_works_too(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--state-dir", str(STATE), "report"]) == 0
    assert "2 project(s)" in capsys.readouterr().out


def test_tests_cannot_reach_the_real_vault() -> None:
    """Phase 12h: a default `phx report` writes to the vault, so this must never be real."""
    root = vault_root()
    assert root != Path.home() / "Documents"
    assert not root.exists()


# --- Saving by default (Phase 12h, ADR-0035) ------------------------------------------


@pytest.fixture
def vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "vault"
    root.mkdir()
    monkeypatch.setenv("PHX_VAULT_ROOT", str(root))
    return root


def saved(root: Path) -> tuple[list[Path], list[Path]]:
    """The notes and charts folders ``root`` holds."""
    folder = root / "04 Resources" / "PHX Reports"
    if not folder.is_dir():
        return [], []
    return sorted(folder.glob("*.md")), sorted(p for p in folder.iterdir() if p.is_dir())


@pytest.mark.parametrize(
    "argv", [[], ["--by", "quarter"], ["alpha-project"], ["--no-repos"], ["--top", "3"]]
)
def test_a_view_with_no_output_option_saves(
    argv: list[str], vault: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run(argv, capsys)
    notes, folders = saved(vault)
    assert len(notes) == len(folders) == 1
    assert len(list(folders[0].glob("*.svg"))) == 4


@pytest.mark.parametrize(
    "argv", [["--json"], ["--markdown"], ["--no-save"], ["--json", "--no-save"]]
)
def test_output_options_and_no_save_write_nothing(
    argv: list[str], vault: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run(argv, capsys)
    assert saved(vault) == ([], [])


def test_explicit_vault_keeps_its_plain_note(
    vault: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run(["--vault"], capsys)
    notes, folders = saved(vault)
    assert len(notes) == 1 and folders == []
    assert "## Charts" not in notes[0].read_text(encoding="utf-8")


def test_explicit_svg_writes_only_there(
    vault: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run(["--svg", str(tmp_path / "mine")], capsys)
    assert saved(vault) == ([], [])
    assert len(list((tmp_path / "mine").glob("*.svg"))) == 4


@pytest.mark.parametrize("option", [["--vault"], ["--svg", "x"]])
def test_no_save_conflicts(
    option: list[str], vault: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["report", "--state-root", str(STATE), "--no-save", *option])
    assert code != 0
    assert "--no-save" in capsys.readouterr().err
    assert saved(vault) == ([], [])


def test_no_recorded_runs_saves_nothing(
    vault: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "state").mkdir()
    assert main(["report", "--state-root", str(tmp_path / "state")]) == 0
    capsys.readouterr()
    assert saved(vault) == ([], [])


def save(root: Path, now: float = ev.JAN_02_2026) -> list[str]:
    return R.save_report(
        fixture_report(), [], [], top=5, repos=P.Repos(), env={"PHX_VAULT_ROOT": str(root)}, now=now
    )


def test_note_and_folder_share_a_stamp(vault: Path) -> None:
    save(vault)
    (note,), (folder,) = saved(vault)
    assert note.name == "PHX Report 2026-01-02 0000.md"
    assert folder.name == "charts2026-01-02-0000"


def test_a_second_run_in_the_same_minute_overwrites_nothing(vault: Path) -> None:
    save(vault)
    (_,), (first,) = saved(vault)
    (first / "phx-report-cost.svg").write_text("mine")
    save(vault)
    notes, folders = saved(vault)
    assert [p.name for p in notes] == [
        "PHX Report 2026-01-02 0000 (2).md",
        "PHX Report 2026-01-02 0000.md",
    ]
    assert [p.name for p in folders] == ["charts2026-01-02-0000", "charts2026-01-02-0000-2"]
    assert (first / "phx-report-cost.svg").read_text() == "mine"
    assert "charts2026-01-02-0000-2/" in notes[0].read_text(encoding="utf-8")


def test_every_chart_is_embedded_once_and_exists(vault: Path) -> None:
    save(vault)
    (note,), (folder,) = saved(vault)
    text = note.read_text(encoding="utf-8")
    assert text.index("## Charts") < text.index("## Totals")
    for chart in folder.iterdir():
        assert text.count(f"![[{folder.name}/{chart.name}]]") == 1


def test_charts_follow_the_projects_section(vault: Path) -> None:
    r = fixture_report()
    r.summaries = [M.ProjectSummary("p", False, None, "repo not found", [])]
    text = R.to_markdown(r, [], [], charts=["c/a.svg"])
    assert text.index("## Projects") < text.index("## Charts") < text.index("## Totals")


def test_markdown_without_charts_is_unchanged() -> None:
    r = fixture_report()
    assert R.to_markdown(r, [], []) == R.to_markdown(r, [], [], charts=())
    assert "## Charts" not in R.to_markdown(r, [], [])


def test_no_vault_saves_nothing_and_still_prints(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = run([], capsys)
    assert code == 0
    assert "\nTotals\n" in out
    assert "report not saved" in err


def test_charts_that_fail_leave_a_note_without_embeds(
    vault: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*_args: object) -> list[Path]:
        raise OSError("disk full")

    monkeypatch.setattr(R, "write_charts", fail)
    _, out, err = run([], capsys)
    assert "\nTotals\n" in out
    assert "charts not written: OSError" in err
    (note,), _ = saved(vault)
    assert "## Charts" not in note.read_text(encoding="utf-8")


def test_a_note_that_fails_leaves_the_charts(
    vault: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    real_open = os.open

    def fail(path: Any, *args: Any, **kw: Any) -> int:
        if str(path).endswith(".md"):
            raise PermissionError("no")
        return real_open(path, *args, **kw)

    monkeypatch.setattr(R.os, "open", fail)
    _, out, err = run([], capsys)
    assert "\nTotals\n" in out
    assert "note not written: PermissionError" in err
    notes, folders = saved(vault)
    assert notes == [] and len(folders) == 1


def test_stdout_is_the_same_whether_or_not_it_saves(
    vault: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run([], capsys)[1] == run(["--no-save"], capsys)[1]


def test_a_default_run_leaves_the_state_root_unchanged(
    vault: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def digest() -> dict[str, str]:
        files = [p for p in sorted(STATE.rglob("*")) if p.is_file()]
        return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}

    before = digest()
    run([], capsys)
    assert digest() == before
