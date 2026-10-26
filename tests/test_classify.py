import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from phx.classify import (
    ExitClass,
    classify,
    epoch_to_local,
    parse_reset,
    parse_result_line,
)

STREAMS = Path(__file__).resolve().parent / "fixtures" / "streams"
CHICAGO = ZoneInfo("America/Chicago")
# 2026-10-26 09:30 CDT
NOW = datetime(2026, 10, 26, 14, 30, tzinfo=UTC)


def load(name: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    events = []
    for line in (STREAMS / f"{name}.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue  # truncated last line
    result = next((e for e in reversed(events) if e.get("type") == "result"), None)
    return result, events


def run(name: str, exit_code: int = 0, **kw: Any) -> Any:
    result, events = load(name)
    return classify(exit_code, result, events, kw.pop("stderr", ""), now=NOW, **kw)


# --- result line ------------------------------------------------------------------


def test_result_line_valid() -> None:
    text = (
        'done\nPHX-RESULT: {"contract":1,"phase":"05","status":"complete","reason":"ok",'
        '"merged":true,"pushed":false,"question_ids":[]}\n'
    )
    line = parse_result_line(text)
    assert line is not None
    assert (line.phase, line.status, line.merged, line.pushed) == ("05", "complete", True, False)


def test_result_line_last_wins_and_malformed_last_means_none() -> None:
    result, _ = load("bad_result_line")
    assert result is not None
    assert parse_result_line(result["result"]) is None


@pytest.mark.parametrize(
    "body",
    [
        '{"contract":"1","phase":"05","status":"complete","reason":"","merged":true,"pushed":true,"question_ids":[]}',
        '{"contract":1,"phase":5,"status":"complete","reason":"","merged":true,"pushed":true,"question_ids":[]}',
        '{"contract":1,"phase":"05","status":"done","reason":"","merged":true,"pushed":true,"question_ids":[]}',
        '{"contract":1,"phase":"05","status":"blocked","reason":"","merged":1,"pushed":true,"question_ids":[]}',
        '{"contract":1,"phase":"05","status":"blocked","reason":"","merged":false,"pushed":true,"question_ids":[6]}',
        '{"contract":1,"phase":"05","status":"blocked","reason":"","merged":false,"pushed":true}',
        "[1,2]",
        "{not json}",
    ],
)
def test_result_line_rejects_bad_types(body: str) -> None:
    assert parse_result_line(f"PHX-RESULT: {body}") is None


def test_result_line_null_phase_and_unknown_keys() -> None:
    line = parse_result_line(
        'PHX-RESULT: {"contract":1,"phase":null,"status":"refused",'
        '"reason":"auto mode needs a phase ID","merged":false,"pushed":false,'
        '"question_ids":[],"extra":1}'
    )
    assert line is not None and line.phase is None and line.status == "refused"


def test_result_line_in_code_fence_text_still_needs_own_line() -> None:
    assert parse_result_line("say PHX-RESULT: {} inline") is None
    assert parse_result_line(None) is None


# --- reset times ------------------------------------------------------------------


def chicago(dt: datetime | None) -> tuple[int, int, int, int, int]:
    assert dt is not None and dt.tzinfo is not None
    d = dt.astimezone(CHICAGO)
    return (d.year, d.month, d.day, d.hour, d.minute)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("You've hit your session limit · resets 7:40pm (America/Chicago)", (2026, 10, 26, 19, 40)),
        ("You've hit your session limit · resets 10pm (America/Chicago)", (2026, 10, 26, 22, 0)),
        # earlier than now (09:30): tomorrow
        ("You've hit your session limit · resets 12:40am (America/Chicago)", (2026, 10, 27, 0, 40)),
        ("You've hit your session limit · resets 9:00am (America/Chicago)", (2026, 10, 27, 9, 0)),
        (
            "You've hit your weekly limit · resets Oct 28, 9am (America/Chicago)",
            (2026, 10, 28, 9, 0),
        ),
        (
            "You've hit your weekly limit · resets Nov 2, 9:30am (America/Chicago)",
            (2026, 11, 2, 9, 30),
        ),
        (
            "You've hit your weekly limit · resets Jan 2, 2027, 9am (America/Chicago)",
            (2027, 1, 2, 9, 0),
        ),
        # date already past and no year: next year
        ("You've hit your weekly limit · resets Jan 3, 9am (America/Chicago)", (2027, 1, 3, 9, 0)),
        (
            "You've hit your Opus limit · resets 7:40pm (America/Chicago) · progress saved",
            (2026, 10, 26, 19, 40),
        ),
        ("You've hit your fast limit · resets in 2h 15m", (2026, 10, 26, 11, 45)),
    ],
)
def test_parse_reset(text: str, expected: tuple[int, int, int, int, int]) -> None:
    assert chicago(parse_reset(text, NOW)) == expected


def test_parse_reset_other_zone_converted() -> None:
    got = parse_reset("You've hit your session limit · resets 12:50am (America/Los_Angeles)", NOW)
    # 00:50 PDT on Oct 27 is 02:50 CDT
    assert chicago(got) == (2026, 10, 27, 2, 50)


def test_parse_reset_without_zone_uses_local() -> None:
    got = parse_reset("You've hit your session limit · resets 11pm", NOW)
    assert got is not None
    assert got.astimezone().hour == 23


@pytest.mark.parametrize(
    "text", ["You've hit your limit", "resets whenever", "resets Foo 3, 9am", "resets Feb 31, 9am"]
)
def test_parse_reset_none(text: str) -> None:
    assert parse_reset(text, NOW) is None


def test_epoch_to_local() -> None:
    assert chicago(epoch_to_local(1793196000)) == (2026, 10, 28, 9, 0)
    assert chicago(epoch_to_local(1793196000000)) == (2026, 10, 28, 9, 0)
    assert epoch_to_local(None) is None
    assert epoch_to_local(True) is None
    assert epoch_to_local(-5) is None


# --- classes from fixtures --------------------------------------------------------


def test_complete() -> None:
    c = run("complete")
    assert c.cls is ExitClass.COMPLETE and c.reason == "all checks passed"
    assert c.result is not None and c.result.merged


def test_blocked() -> None:
    c = run("blocked")
    assert c.cls is ExitClass.BLOCKED and c.result.question_ids == ("6",)


def test_refused() -> None:
    assert run("refused").cls is ExitClass.REFUSED


def test_no_result_line() -> None:
    assert run("no_result").cls is ExitClass.NO_RESULT
    assert run("bad_result_line").cls is ExitClass.NO_RESULT


def test_probe_mode_accepts_clean_answer() -> None:
    assert run("probe_ok", expect_result_line=False).cls is ExitClass.COMPLETE


def test_usage_limit_session_text() -> None:
    c = run("usage_limit_session", exit_code=1, provider="anthropic")
    assert c.cls is ExitClass.USAGE_LIMIT
    assert c.kind == "session limit"
    assert chicago(c.reset_at) == (2026, 10, 26, 19, 40)
    assert "2026-10-26 19:40" in c.reason


def test_usage_limit_weekly_event_prefers_resets_at() -> None:
    c = run("usage_limit_weekly_event", exit_code=1)
    assert c.cls is ExitClass.USAGE_LIMIT
    assert c.kind == "seven_day"
    assert chicago(c.reset_at) == (2026, 10, 28, 9, 0)


def test_plain_429_on_pro_is_limit_without_reset() -> None:
    c = run("rate_limit_429_api_key", exit_code=1, provider="anthropic")
    assert c.cls is ExitClass.USAGE_LIMIT and c.reset_at is None


def test_429_on_openrouter_is_provider_error() -> None:
    c = run("rate_limit_429_api_key", exit_code=1, provider="openrouter")
    assert c.cls is ExitClass.PROVIDER_ERROR and c.kind == "rate_limited"


def test_auth_error() -> None:
    c = run("auth_expired", exit_code=1)
    assert c.cls is ExitClass.AUTH_ERROR and "/login" in c.reason


def test_openrouter_credit() -> None:
    c = run("openrouter_402", exit_code=1, provider="openrouter")
    assert c.cls is ExitClass.PROVIDER_ERROR and c.kind == "credits"


def test_server_errors() -> None:
    for name in ("connection_refused", "server_lost"):
        c = run(name, exit_code=1)
        assert c.cls is ExitClass.PROVIDER_ERROR and c.kind == "server", name


def test_budget() -> None:
    c = run("max_budget", exit_code=1, provider="openrouter")
    assert c.cls is ExitClass.PROVIDER_ERROR and c.kind == "budget"


def test_truncated_stream_is_crash() -> None:
    c = run("truncated", exit_code=0)
    assert c.cls is ExitClass.CRASH and "without a result event" in c.reason


def test_signal_crash() -> None:
    c = run("truncated", exit_code=-9)
    assert c.cls is ExitClass.CRASH and "signal 9" in c.reason


def test_auth_from_stderr_without_stream() -> None:
    c = classify(1, None, [], "Invalid API key · Please run /login")
    assert c.cls is ExitClass.AUTH_ERROR


def test_timeout_wins() -> None:
    c = run("complete", timed_out="idle")
    assert c.cls is ExitClass.TIMEOUT and c.kind == "idle"


def test_error_during_execution_is_crash() -> None:
    result = {"type": "result", "subtype": "error_during_execution", "is_error": True, "result": ""}
    c = classify(1, result, [result])
    assert c.cls is ExitClass.CRASH and c.kind == "error_during_execution"


def test_recovered_api_error_is_ignored() -> None:
    # An API error followed by a normal assistant message and a clean result.
    result, events = load("complete")
    err = {
        "type": "assistant",
        "error": "server_error",
        "is_api_error_message": True,
        "message": {"content": [{"type": "text", "text": "API Error: overloaded"}]},
    }
    events = [events[0], err, *events[1:]]
    assert classify(0, result, events).cls is ExitClass.COMPLETE


def test_as_log_is_json() -> None:
    c = run("usage_limit_session", exit_code=1)
    data = json.loads(json.dumps(c.as_log()))
    assert data["class"] == "usage_limit" and data["reset_at"].startswith("2026-10-26T19:40")


# --- the real probe stream (Claude Code 2.1.310, Anthropic Pro) ---------------------


def test_real_probe_stream() -> None:
    result, events = load("probe_real")
    assert classify(0, result, events, expect_result_line=False).cls is ExitClass.COMPLETE
    assert classify(0, result, events).cls is ExitClass.NO_RESULT
    # an "allowed" rate_limit_event is informational
    assert any(e["type"] == "rate_limit_event" for e in events)


def test_real_rate_limit_event_shape_when_rejected() -> None:
    """The real event with status flipped to "rejected" and an error ending."""
    result, events = load("probe_real")
    event = next(e for e in events if e["type"] == "rate_limit_event")
    event["rate_limit_info"]["status"] = "rejected"
    assert result is not None
    result = {**result, "is_error": True, "api_error_status": 429, "result": "API Error"}
    c = classify(1, result, [*events[:-1], result], now=NOW)
    assert c.cls is ExitClass.USAGE_LIMIT and c.kind == "five_hour"
    assert c.reset_at == epoch_to_local(event["rate_limit_info"]["resetsAt"])


def test_validate_rejects_non_object() -> None:
    from phx.classify import _validate_result

    assert _validate_result([1, 2]) is None


def test_parse_reset_unknown_zone_falls_back_to_local() -> None:
    got = parse_reset("You've hit your session limit · resets 11pm (Mars/Olympus_Mons)", NOW)
    assert got is not None and got.astimezone().hour == 23


def api_end(text: str, error: str | None, status: int | None) -> Any:
    err = {"type": "assistant", "error": error, "is_api_error_message": True,
           "message": {"content": [{"type": "text", "text": text}]}}  # fmt: skip
    result = {"type": "result", "subtype": "success", "is_error": True,
              "api_error_status": status, "result": text}  # fmt: skip
    return classify(1, result, [err, result])


def test_invalid_request_and_unknown_api_errors() -> None:
    c = api_end("API Error: Opus 5.5's safeguards flagged this message", "invalid_request", None)
    assert c.cls is ExitClass.PROVIDER_ERROR and c.kind == "invalid_request"
    c = api_end("API Error: 400 status code (no body)", "unknown", 400)
    assert c.cls is ExitClass.PROVIDER_ERROR and c.kind == "unknown"
    c = api_end("API Error: 418 teapot", None, 418)
    assert c.cls is ExitClass.PROVIDER_ERROR and c.kind == "unknown"
    c = api_end("API Error: 503 overloaded", None, 503)
    assert c.kind == "server"


def test_error_result_without_text() -> None:
    result = {"type": "result", "subtype": "error_max_turns", "is_error": True}
    c = classify(1, result, [result])
    assert c.cls is ExitClass.CRASH and c.reason == "session ended with error_max_turns"
