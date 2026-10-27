"""The redaction audit (Phase 11, task 5), kept as a test.

Synthetic leaks must be found; a full supervisor run whose agent and provider leak
key-shaped values must leave nothing for the audit to find. ``PHX_AUDIT_DIR`` (a
``:``-separated list) also audits real PHX state, e.g. ``~/.local/state/phx``.
"""

import json
import os
from pathlib import Path

import pytest

from conftest import RepoFactory
from phx.redact import REDACTED
from redaction_audit import audit, main
from test_runner import FAKE_KEY
from test_supervisor import H


def test_finds_each_leak_shape(tmp_path: Path) -> None:
    (tmp_path / "sessions").mkdir()
    (tmp_path / "sessions" / "01-1.jsonl").write_text(
        json.dumps({"text": f"key {FAKE_KEY}"})
        + "\n"
        + json.dumps({"env": {"GH_TOKEN": "hunter2"}})
        + "\n"
        + json.dumps({"h": "Authorization: Bearer abc"})
        + "\n"
    )
    (tmp_path / "run.jsonl").write_text(
        json.dumps({"x": f"ANTHROPIC_AUTH_TOKEN={REDACTED} and OPENROUTER_API_KEY=zz"}) + "\n"
    )
    (tmp_path / "state.json").write_text('{"ok": "ANTHROPIC_MODEL=opus"}\n')
    (tmp_path / "image.png").write_bytes(b"sk-or-v1-" + b"f" * 40)  # not a text suffix
    report = audit([tmp_path])
    assert report.files == 3 and not report.clean
    found = sorted((f.path.name, f.line, f.pattern) for f in report.findings)
    assert found == [
        ("01-1.jsonl", 1, "sk-or-"),
        ("01-1.jsonl", 2, "GH_TOKEN assignment"),
        ("01-1.jsonl", 3, "bearer header"),
        ("run.jsonl", 1, "OPENROUTER_API_KEY assignment"),
    ]


def test_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    clean = tmp_path / "clean.jsonl"
    clean.write_text(json.dumps({"k": f"GH_TOKEN={REDACTED}"}) + "\n")
    assert main([str(clean)]) == 0
    assert "1 lines carry [REDACTED]; 0 unredacted" in capsys.readouterr().out
    leak = tmp_path / "leak.md"
    leak.write_text(f"oops {FAKE_KEY}\n")
    assert main([str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert f"LEAK {leak}:1: sk-or-" in out and FAKE_KEY not in out
    assert main([]) == 2


def test_supervisor_run_leaves_nothing_to_find(tmp_path: Path, make_repo: RepoFactory) -> None:
    """A run whose agent prints a key, whose stderr and provider env carry one, audits clean."""
    x = H(tmp_path, make_repo, {"01": ["complete"]}).all_auto().decide_q1()
    provider_env = tmp_path / "provider.env"
    provider_env.write_text(
        f"export ANTHROPIC_AUTH_TOKEN={FAKE_KEY}\nexport ANTHROPIC_BASE_URL=https://x\n"
    )
    x.provider_file.write_text("openrouter")
    x.env |= {
        "PHX_FAKE_ENV": str(provider_env),
        "PHX_FAKE_STDERR": f"ANTHROPIC_AUTH_TOKEN={FAKE_KEY}",
        "PHX_FAKE_LEAK": f"my key is {FAKE_KEY}; GH_TOKEN=hunter2",
        "ANTHROPIC_AUTH_TOKEN": FAKE_KEY,
    }
    x.run(until="01")
    state = x.state_root / "SMP"
    assert (state / "sessions").is_dir()
    report = audit([state])
    assert report.clean, report.findings
    assert report.redacted >= 2  # the leaks did reach PHX and were redacted
    everything = "".join(p.read_text() for p in state.rglob("*") if p.is_file())
    assert FAKE_KEY not in everything and "hunter2" not in everything


@pytest.mark.skipif(not os.environ.get("PHX_AUDIT_DIR"), reason="PHX_AUDIT_DIR not set")
def test_real_state_is_clean() -> None:
    dirs = [Path(d).expanduser() for d in os.environ["PHX_AUDIT_DIR"].split(":") if d]
    report = audit(dirs)
    assert report.files > 0
    assert report.clean, [f"{f.path}:{f.line}: {f.pattern}" for f in report.findings]
