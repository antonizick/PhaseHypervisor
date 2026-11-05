"""Unit tests for ``phx.progress``: the zero-token progress derivation (Phase 12d)."""

from typing import Any

from phx.progress import (
    ProgressTracker,
    activity_line,
    eta_durations,
    eta_text,
    fmt_dur,
    fmt_tokens,
    median,
    plan_durations,
    progress_fields,
    progress_reason,
)


class Clock:
    """Two clocks (monotonic and wall) that a test advances by hand."""

    def __init__(self) -> None:
        self.t = 1000.0

    def mono(self) -> float:
        return self.t

    def wall(self) -> float:
        return 1_700_000_000.0 + (self.t - 1000.0)

    def tick(self, seconds: float) -> None:
        self.t += seconds


def assistant(*blocks: dict[str, Any], msg_id: str = "m1", usage: dict | None = None) -> dict:
    return {
        "type": "assistant",
        "message": {
            "id": msg_id,
            "usage": usage or {"input_tokens": 100, "output_tokens": 10},
            "content": list(blocks),
        },
    }


def tool_use(tid: str, name: str, inp: dict[str, Any]) -> dict[str, Any]:
    return {"type": "tool_use", "id": tid, "name": name, "input": inp}


def tool_result(tid: str, content: str = "ok") -> dict[str, Any]:
    return {
        "type": "user",
        "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "content": content}]},
    }


def text(s: str) -> dict[str, Any]:
    return {"type": "text", "text": s}


def tracker(clock: Clock | None = None, **kw: Any) -> ProgressTracker:
    clock = clock or Clock()
    return ProgressTracker(
        phase="12d",
        monotonic=clock.mono,
        wall=clock.wall,
        idle_timeout_s=kw.pop("idle_timeout_s", 60.0),
        **kw,
    )


# --------------------------------------------------------------------------- stages


def test_stage_walks_the_tool_trail() -> None:
    t = tracker()
    assert t.stage == "unknown"
    t.feed({"type": "system", "subtype": "init"})
    assert t.stage == "unknown"  # no trail at all yet
    t.feed(assistant(text("thinking about it")))
    assert t.stage == "starting"
    t.feed(assistant(tool_use("u1", "Edit", {"file_path": "src/phx/a.py"}), msg_id="m2"))
    assert t.stage == "working"
    t.feed(tool_result("u1"))
    t.feed(assistant(tool_use("u2", "Bash", {"command": "uv run pytest -q"}), msg_id="m3"))
    assert t.stage == "testing"
    t.feed(tool_result("u2"))
    t.feed(assistant(tool_use("u3", "Bash", {"command": "git commit -m x"}), msg_id="m4"))
    assert t.stage == "finishing"
    t.feed(tool_result("u3"))


def test_stage_close_out_text_finishes() -> None:
    t = tracker()
    t.feed(assistant(tool_use("u1", "Read", {"file_path": "a"}), msg_id="m1"))
    t.feed(tool_result("u1"))
    assert t.stage == "working"
    t.feed(assistant(text("Close-out: merging to main"), msg_id="m2"))
    assert t.stage == "finishing"


def test_stage_text_only_starts_then_finishes() -> None:
    t = tracker()
    t.feed(assistant(text("starting the close-out checklist"), msg_id="m1"))
    assert t.stage == "finishing"
    u = tracker()
    u.feed(assistant(text("reading the plan")))
    assert u.stage == "starting"


# --------------------------------------------------------------------------- counting


def test_steps_count_completed_results_not_tool_uses() -> None:
    t = tracker()
    t.feed(assistant(tool_use("u1", "Edit", {"file_path": "a"}), msg_id="m1"))
    t.feed(assistant(tool_use("u2", "Bash", {"command": "ls"}), msg_id="m2"))
    assert t.snapshot().steps == 0  # nothing finished yet
    t.feed(tool_result("u1"))
    t.feed(tool_result("u2"))
    t.feed(tool_result("u3"))  # no matching tool_use: counts as other
    snap = t.snapshot()
    assert snap.steps == 3
    assert snap.tools["edit"] == 1 and snap.tools["bash"] == 1 and snap.tools["other"] == 1
    assert snap.in_flight is None


def test_bucket_mapping_covers_the_named_tools() -> None:
    t = tracker()
    for tid, name, inp in [
        ("a", "MultiEdit", {"file_path": "x"}),
        ("b", "Write", {"file_path": "y"}),
        ("c", "Read", {"file_path": "z"}),
        ("d", "Grep", {"pattern": "p"}),
        ("e", "Glob", {"pattern": "g"}),
        ("f", "WebFetch", {"url": "u"}),
    ]:
        t.feed(assistant(tool_use(tid, name, inp), msg_id=f"m-{tid}"))
        t.feed(tool_result(tid))
    snap = t.snapshot()
    assert snap.tools == {
        "edit": 1,
        "write": 1,
        "bash": 0,
        "read": 1,
        "grep": 1,
        "glob": 1,
        "other": 1,
    }
    assert snap.steps == 6


def test_tokens_dedupe_by_message_id_and_cost_from_result() -> None:
    t = tracker()
    t.feed(assistant(text("a"), msg_id="m1", usage={"input_tokens": 100, "output_tokens": 5}))
    t.feed(assistant(text("b"), msg_id="m1", usage={"input_tokens": 200, "output_tokens": 5}))
    t.feed(assistant(text("c"), msg_id="m2", usage={"input_tokens": 1, "output_tokens": 1}))
    assert t.tokens == 207  # last usage for m1 wins
    assert t.snapshot().cost_usd is None
    t.feed({"type": "result", "total_cost_usd": 1.25})
    assert t.snapshot().cost_usd == 1.25


# --------------------------------------------------------------------------- robustness


def test_malformed_events_never_raise() -> None:
    t = tracker()
    for junk in (
        None,
        [],
        {"type": "assistant"},
        {"type": "assistant", "message": "not a dict"},
        {"type": "assistant", "message": {"content": "not a list", "usage": "nope"}},
        {"type": "assistant", "message": {"content": [None, 3, {"type": "tool_use"}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result"}]}},
        {"type": "user"},
        {"type": "result", "total_cost_usd": "lots"},
        {"type": "result", "total_cost_usd": True},
    ):
        t.feed(junk)  # type: ignore[arg-type]
    snap = t.snapshot()
    assert snap.stage == "working"  # the bare tool_use is the only trail
    assert snap.steps >= 1  # the id-less tool_result still counts as `other`


def test_tool_description_is_redacted_and_truncated() -> None:
    t = tracker()
    secret = "sk-or-v1-" + "f" * 40  # pragma: allowlist secret
    t.feed(assistant(tool_use("u1", "Bash", {"command": f"curl -H 'X: {secret}' {'q' * 200}"})))
    snap = t.snapshot()
    assert snap.tool_desc is not None
    assert secret not in snap.tool_desc
    assert "[REDACTED]" in snap.tool_desc
    assert len(snap.tool_desc) <= 80


def test_last_text_is_redacted_and_truncated() -> None:
    t = tracker()
    t.feed(assistant(text("ghp_" + "a" * 30 + " " + "x" * 300)))
    snap = t.snapshot()
    assert snap.last_text is not None
    assert len(snap.last_text) <= 120
    assert "ghp_" not in snap.last_text


# --------------------------------------------------------------------------- ETA


def test_median_zero_one_odd_even() -> None:
    assert median([]) is None
    assert median([5.0]) == 5.0
    assert median([3.0, 1.0, 2.0]) == 2.0
    assert median([4.0, 1.0, 2.0, 3.0]) == 2.5


def test_eta_zero_sample_is_honest() -> None:
    assert eta_text([], 60.0) == "no estimate yet (first phase in this plan)"
    assert eta_text([], 60.0, "testing") == "no estimate yet (first phase in this plan)"


def test_eta_single_and_tight_samples() -> None:
    one = eta_text([4800.0], 600.0)
    assert one == "~70m of ~80m typical left (median of 1 phase)"
    tight = eta_text([4800.0, 5000.0, 4600.0], 600.0)
    assert tight == "~70m of ~80m typical left (median of 3 phases)"
    even = eta_text([4800.0, 5400.0], 0.0)
    assert even == "~85m of ~85m typical left (median of 2 phases)"


def test_eta_wide_sample_spans_a_range() -> None:
    wide = eta_text([600.0, 600.0, 4800.0, 4800.0], 0.0)
    assert wide == "~10m to ~80m of ~45m typical left (median of 4 phases)"


def test_eta_stage_hints_do_not_shrink_the_number() -> None:
    base = eta_text([4800.0], 4500.0)
    testing = eta_text([4800.0], 4500.0, "testing")
    assert testing.startswith(base)
    assert "testing now" in testing
    assert "finishing" in eta_text([4800.0], 4500.0, "finishing")


def test_plan_durations_from_timeline_bullets() -> None:
    text_body = (
        "# X: Plan\n"
        "## Phase Log\n"
        "### 2026-10-26 08:35 CDT: Phase 00: Planning & spec refinement (✅ Complete)\n"
        "- **Timeline:** started 2026-10-26 08:27 CDT · finished 2026-10-26 08:35 CDT\n"
        "\n"
        "### 2026-10-27 05:16 CDT: Planning: phase 12a inserted (Planned)\n"
        "- **Timeline:** started 2026-10-27 05:11 CDT · finished 2026-10-27 05:16 CDT\n"
        "\n"
        "### 2026-10-31 10:53 CDT: Phase 12b: Visual project timeline (⛔ Blocked)\n"
        "- **Timeline:** started 2026-10-31 10:27 CDT (claim commit 747de43)"
        " · blocked 2026-10-31 10:53 CDT to (open)\n"
        "\n"
        "### 2026-10-31 11:20 CDT: Phase 12b: Visual project timeline (✅ Complete)\n"
        "- **Timeline:** started 2026-10-31 10:27 CDT (claim commit 747de43)"
        " · finished 2026-10-31 11:20 CDT · merged 2026-10-31 11:20 CDT"
        " · blocked 2026-10-31 10:53 CDT to 2026-10-31 11:18 CDT\n"
        "\n"
        "### 2026-10-31 12:00 CDT: Phase 13: Later (✅ Complete)\n"
        "- **Timeline:** started not recorded · finished 2026-10-31 12:30 CDT\n"
    )
    got = plan_durations(text_body)
    # 00: 8 min; 12b: 53 min minus 25 min blocked = 28 min. Planning and the ⛔ entry
    # and the "started not recorded" bullet give nothing.
    assert got == [8 * 60.0, 28 * 60.0]
    assert eta_durations(text_body, [99.0]) == got  # log beats the fallback
    assert eta_durations("", [60.0, 120.0]) == [60.0, 120.0]
    assert eta_durations(None, []) == []


# --------------------------------------------------------------------------- output lines


def test_activity_and_reason_read_alone() -> None:
    clock = Clock()
    t = tracker(clock, durations=[4800.0], attempt=1)
    t.feed(assistant(tool_use("u1", "Edit", {"file_path": "src/phx/supervisor.py"}), msg_id="m1"))
    t.feed(tool_result("u1"))
    t.feed(assistant(tool_use("u2", "Bash", {"command": "uv run pytest"}), msg_id="m2"))
    t.feed(tool_result("u2"))
    clock.tick(2820.0)  # 47 minutes in
    snap = t.snapshot()
    assert activity_line(snap) == "running uv run pytest"
    reason = progress_reason(snap)
    assert reason.startswith("phase 12d attempt 1, 47m elapsed · running uv run pytest · 2 steps")
    assert "(1 edit, 1 bash)" in reason
    assert "220 tokens" in reason
    assert "~33m of ~80m typical left" in reason
    fields = progress_fields(snap)
    assert fields["stage"] == "testing"
    assert fields["steps"] == 2 and fields["attempt"] == 1
    assert fields["last_tool"] == "Bash uv run pytest"


def test_progress_reason_without_a_tool() -> None:
    t = tracker(attempt=2)
    t.feed(assistant(text("hello"), msg_id="m1"))
    reason = progress_reason(t.snapshot())
    assert "phase 12d attempt 2" in reason
    assert "writing: hello" in reason
    assert "0 steps" in reason
    assert "no estimate yet" in reason


# --------------------------------------------------------------------------- stall


def test_stall_warning_once_per_quiet_spell_and_names_the_tool() -> None:
    clock = Clock()
    t = tracker(clock, idle_timeout_s=120.0)  # warns at 60 s
    t.feed(assistant(tool_use("u1", "Bash", {"command": "uv run pytest"}), msg_id="m1"))
    clock.tick(30.0)
    assert t.stall_warning() is None  # quiet, but under the threshold
    clock.tick(40.0)
    first = t.stall_warning()
    assert first is not None
    assert "running uv run pytest" in first["reason"]
    assert "no event for 70s" in first["reason"]
    assert first["stalled_for_s"] == 70.0
    assert first["idle_timeout_s"] == 120.0
    clock.tick(10.0)
    assert t.stall_warning() is None  # once per quiet spell
    t.feed(tool_result("u1"))  # an event clears the spell
    clock.tick(70.0)
    second = t.stall_warning()
    assert second is not None and second["tool"] is None
    assert "idle timeout at 2m" in second["reason"]
    snap = t.snapshot()
    assert snap.stalled_for_s == 70.0
    assert snap.in_flight is None


def test_snapshot_stall_field_and_in_flight_age() -> None:
    clock = Clock()
    t = tracker(clock, idle_timeout_s=120.0)
    t.feed(assistant(tool_use("u1", "Bash", {"command": "make check"}), msg_id="m1"))
    clock.tick(65.0)
    snap = t.snapshot()
    assert snap.stalled_for_s == 65.0
    assert snap.in_flight == "running make check (65s)"
    assert snap.eta  # always populated


def test_stall_warning_from_a_silent_start() -> None:
    clock = Clock()
    t = tracker(clock, idle_timeout_s=120.0)
    clock.tick(61.0)
    warn = t.stall_warning()
    assert warn is not None and "no event" in warn["reason"]


# --------------------------------------------------------------------------- edge cases


def test_formatters() -> None:
    assert fmt_dur(0) == "0s" and fmt_dur(45.4) == "45s"
    assert fmt_dur(6000) == "1h 40m"
    assert fmt_tokens(0) == "0" and fmt_tokens(999) == "999"
    assert fmt_tokens(1_500) == "1.5k"
    assert fmt_tokens(12_345) == "12k"
    assert fmt_tokens(1_234_567) == "1.23M"


def test_plan_durations_ignores_unparseable_times() -> None:
    body = (
        "### 2026-10-26 08:35 CDT: Phase 01: X (✅ Complete)\n"
        "- **Timeline:** started 2026-13-01 08:27 CDT · finished 2026-10-26 08:35 CDT\n"
        "\n### 2026-10-26 08:35 CDT: Phase 02: Y (✅ Complete)\n"
        "- **Timeline:** started 2026-10-26 08:27 CDT · finished 2026-10-26 08:35 CDT"
        " · blocked 2026-13-45 08:30 CDT to 2026-10-26 08:31 CDT\n"
    )
    # month 13 cannot be parsed: the first bullet is skipped and the blocked pair
    # (whose first stamp is unparseable) is ignored, so 02 keeps its full 8 minutes
    assert plan_durations(body) == [8 * 60.0]


def test_feed_swallows_a_raising_event() -> None:
    class Boom(dict):
        def get(self, *args: Any, **kw: Any) -> Any:
            raise RuntimeError("malformed beyond repair")

    t = tracker()
    t.feed(Boom())  # type: ignore[arg-type]
    assert t.snapshot().steps == 0


def test_generic_tool_uses_its_description() -> None:
    t = tracker()
    t.feed(assistant(tool_use("u1", "Task", {"description": "find the drift"}), msg_id="m1"))
    snap = t.snapshot()
    assert snap.tool_desc == "find the drift"
    assert activity_line(snap) == "using find the drift"


def test_reason_includes_cost_and_fields_age_when_present() -> None:
    t = tracker()
    t.feed(assistant(text("hi"), msg_id="m1"))
    t.feed({"type": "result", "total_cost_usd": 1.25})
    reason = progress_reason(t.snapshot())
    assert "$1.25" in reason
    fields = progress_fields(t.snapshot())
    assert fields["last_event_age_s"] is not None and fields["cost_usd"] == 1.25
    empty = progress_fields(tracker().snapshot())
    assert empty["last_event_age_s"] is None


def test_eta_refuses_samples_of_seconds() -> None:
    assert (
        eta_text([1.5, 2.0], 0.2)
        == "no useful estimate yet (completed phases are too short to compare)"
    )
