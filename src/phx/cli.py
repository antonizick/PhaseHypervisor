"""Command-line entry point: ``phx`` / ``python -m phx``."""

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from phx import __version__
from phx.plan import (
    STATUS_LABELS,
    ContractError,
    Plan,
    PlanError,
    detect_drift,
    load_live,
    load_plan,
    next_eligible,
)

# subcommand -> (help text, phase that implements it)
COMMANDS: dict[str, tuple[str, int]] = {
    "preflight": ("ask every foreseeable question before a hands-off run", 8),
    "run": ("run the remaining phases of a plan unattended", 7),
    "resume": ("resume a stopped or waiting run", 7),
    "status": ("show the state of a run", 7),
    "stop": ("stop a running supervisor", 7),
    "log": ("show or follow the run log", 7),
    "answer": ("answer a recorded owner question and unblock its phase", 7),
    "plan": ("parse a plan read-only and print it, the next phase and any drift", 4),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="phx",
        description="Hands-off deployer for phased-project implementation plans.",
    )
    parser.add_argument("--version", action="version", version=f"phx {__version__}")
    parser.add_argument("--state-dir", type=Path, help="override the state directory root")
    parser.add_argument("-v", "--verbose", action="store_true", help="mirror log events to stderr")
    sub = parser.add_subparsers(dest="command", metavar="<command>", required=True)
    for name, (help_text, _phase) in COMMANDS.items():
        cmd = sub.add_parser(name, help=help_text, description=help_text)
        if name == "plan":
            cmd.add_argument("repo", type=Path, nargs="?", default=Path("."), help="repo path")
            cmd.add_argument("--json", action="store_true", help="print JSON")
    return parser


def plan_report(plan: Plan) -> dict[str, Any]:
    """Everything ``phx plan`` shows, as JSON-ready data."""
    live = load_live(plan.repo)
    elig = next_eligible(plan)
    try:
        contract: dict[str, Any] = {"version": plan.check_contract(), "error": None}
    except ContractError as exc:
        contract = {"version": plan.contract, "error": str(exc)}
    return {
        "repo": str(plan.repo),
        "plan_file": plan.plan_file,
        "prefix": plan.prefix,
        "contract": contract,
        "test_commands": list(plan.test_commands),
        "test_source": plan.test_source,
        "phases": [asdict(p) for p in plan.phases],
        "next": elig.next.id if elig.next else None,
        "resume": [p.id for p in elig.resume],
        "reasons": elig.reasons,
        "open_questions": [asdict(q) for q in plan.questions if q.open],
        "drift": [asdict(d) for d in detect_drift(plan, live)],
        "live": asdict(live),
        "problems": list(plan.problems),
    }


def _print_plan(report: dict[str, Any]) -> None:
    print(f"{report['repo']}  ({report['plan_file']})")
    live_by_phase: dict[str, set[str]] = {}
    for branch, pid in report["live"]["branches"].items():
        live_by_phase.setdefault(pid, set()).add(branch)
    for tree in report["live"]["worktrees"]:
        live_by_phase.setdefault(tree["phase"], set()).add(Path(tree["path"]).name)
    rows = [("ID", "Phase", "Model", "Depends on", "Status", "Gate", "Live")]
    for p in report["phases"]:
        name = p["name"] if len(p["name"]) <= 40 else p["name"][:39] + "…"
        gate = (
            p["gate"]
            if p["gate_source"] in ("column", "default")
            else (f"{p['gate']} ({p['gate_source']})")
        )
        rows.append(
            (
                p["id"],
                name,
                p["alias"] or "?",
                ", ".join(p["depends_on"]) or "none",
                STATUS_LABELS[p["status"]],
                gate,
                ", ".join(sorted(live_by_phase.get(p["id"], set()))),
            )
        )
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for r in rows:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths, strict=True)).rstrip())
    print()
    print(f"Next: {report['next'] or 'none'}")
    if report["resume"]:
        print(f"Resume candidates (🔄): {', '.join(report['resume'])}")
    for pid, why in report["reasons"].items():
        if why != "complete" and not why.startswith("in progress"):
            print(f"  {pid}: {why}")
    for d in report["drift"]:
        print(f"⚠️  drift {d['phase']} ({d['kind']}): {d['detail']}")
    for q in report["open_questions"]:
        needed = ", ".join(q["needed_by"]) or "—"
        print(f"Open question #{q['id']} (needed by {needed}): {q['question']}")
    contract = report["contract"]
    print(f"Contract: {contract['error'] or contract['version']}")
    tests = report["test_commands"]
    if tests:
        print(f"Test command ({report['test_source']}): {' ; '.join(tests)}")
    else:
        print("Test command: none")
    for problem in report["problems"]:
        print(f"⚠️  {problem}")


def _cmd_plan(args: argparse.Namespace) -> int:
    try:
        report = plan_report(load_plan(args.repo))
    except PlanError as exc:
        print(f"phx plan: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_plan(report)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "plan":
        return _cmd_plan(args)
    phase = COMMANDS[args.command][1]
    print(f"phx {args.command}: not implemented yet (Phase {phase:02d})", file=sys.stderr)
    return 2
