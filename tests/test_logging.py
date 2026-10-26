import io
import json
import multiprocessing
from pathlib import Path

from phx.logging import EventLog


def test_writes_valid_redacted_jsonl(tmp_path: Path) -> None:
    mirror = io.StringIO()
    log = EventLog(tmp_path / "sub" / "run.jsonl", verbose=True, mirror=mirror)
    log.event("launch", phase="02", reason="eligible", argv=["x", "ANTHROPIC_API_KEY=abc"])
    (rec,) = [json.loads(line) for line in log.path.read_text().splitlines()]
    assert rec["event"] == "launch" and rec["phase"] == "02" and rec["reason"] == "eligible"
    assert rec["argv"] == ["x", "ANTHROPIC_API_KEY=[REDACTED]"]
    assert isinstance(rec["epoch"], float) and rec["ts"].count(":") == 2
    assert "launch [02] eligible" in mirror.getvalue()
    assert "abc" not in mirror.getvalue()


def test_silent_when_not_verbose(tmp_path: Path) -> None:
    mirror = io.StringIO()
    EventLog(tmp_path / "r.jsonl", mirror=mirror).event("x")
    assert mirror.getvalue() == ""


def _worker(path: str, n: int) -> None:
    log = EventLog(Path(path))
    for i in range(50):
        log.event("tick", worker=n, i=i, pad="x" * 2000)


def test_concurrent_appends_stay_valid(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    procs = [multiprocessing.Process(target=_worker, args=(str(path), n)) for n in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
    lines = path.read_text().splitlines()
    assert len(lines) == 200
    assert all(json.loads(line)["event"] == "tick" for line in lines)
