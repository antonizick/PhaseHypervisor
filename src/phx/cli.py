"""Command-line entry point: ``phx`` / ``python -m phx``."""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from types import FrameType
from typing import Any

from phx import __version__
from phx.detach import detach, unit_name
from phx.locks import main_checkout, running
from phx.logging import EventLog
from phx.paths import default_state_root, state_dir
from phx.plan import (
    MAIN,
    STATUS_LABELS,
    ContractError,
    Plan,
    PlanError,
    detect_drift,
    load_live,
    load_plan,
    next_eligible,
    parse_phase_id,
    set_question_status,
    show_main,
)
from phx.state import RunStatus, load_state, now_ts
from phx.supervisor import EXIT_ERROR, RunOptions, Supervisor

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
        elif name in ("run", "resume"):
            cmd.add_argument("repo", type=Path, nargs="?", default=Path("."), help="repo path")
            cmd.add_argument(
                "--detach", action="store_true", help="run as a systemd user unit (phx-<repo>)"
            )
            cmd.add_argument("--pause-after", metavar="NN", help="pause after phase NN")
            cmd.add_argument("--until", metavar="NN", help="stop after phase NN; start none later")
            cmd.add_argument(
                "--max-phases", metavar="N", type=int, help="stop after N phases complete"
            )
            cmd.add_argument(
                "--dry-run", action="store_true", help="print what would run; launch nothing"
            )
        elif name == "status":
            cmd.add_argument("repo", type=Path, nargs="?", help="repo path (default: all repos)")
            cmd.add_argument("--json", action="store_true", help="print JSON")
        elif name == "stop":
            cmd.add_argument("repo", type=Path, nargs="?", default=Path("."), help="repo path")
            cmd.add_argument(
                "--timeout", type=float, default=120.0, help="seconds to wait (default 120)"
            )
        elif name == "log":
            cmd.add_argument("repo", type=Path, nargs="?", default=Path("."), help="repo path")
            cmd.add_argument("-f", "--follow", action="store_true", help="keep printing new events")
            cmd.add_argument("--json", action="store_true", help="print raw JSON lines")
            cmd.add_argument(
                "-n", "--lines", type=int, default=40, help="last N events (0 = all; default 40)"
            )
        elif name == "answer":
            cmd.add_argument("repo", type=Path, help="repo path")
            cmd.add_argument("question", help="owner question number (the # column)")
            cmd.add_argument("answer", help="the answer, one line")
            cmd.add_argument(
                "--force", action="store_true", help="also overwrite a question that is not open"
            )
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


# --------------------------------------------------------------------------- run / resume


def _repo(path: Path) -> Path:
    try:
        return main_checkout(path)
    except ValueError as exc:
        raise SystemExit(f"phx: {exc}") from None


def _phase_arg(value: str | None, flag: str) -> str | None:
    if value is None:
        return None
    try:
        return parse_phase_id(value)
    except PlanError as exc:
        raise SystemExit(f"phx: {flag}: {exc}") from None


def _forward_args(args: argparse.Namespace) -> list[str]:
    """The argv a detached supervisor gets: the same command without ``--detach``."""
    out = [] if args.state_dir is None else ["--state-dir", str(args.state_dir.resolve())]
    out += [args.command, str(_repo(args.repo))]
    if args.pause_after:
        out += ["--pause-after", args.pause_after]
    if args.until:
        out += ["--until", args.until]
    if args.max_phases is not None:
        out += ["--max-phases", str(args.max_phases)]
    return out


def _cmd_run(args: argparse.Namespace) -> int:
    if os.geteuid() == 0:
        print("phx: refusing to run as root (spec S1)", file=sys.stderr)
        return EXIT_ERROR
    repo = _repo(args.repo)
    if args.max_phases is not None and args.max_phases < 1:
        raise SystemExit("phx: --max-phases must be at least 1")
    options = RunOptions(
        pause_after=_phase_arg(args.pause_after, "--pause-after"),
        max_phases=args.max_phases,
        until=_phase_arg(args.until, "--until"),
        dry_run=args.dry_run,
        resume=args.command == "resume",
    )
    if args.detach and not args.dry_run:
        holder = running(repo)
        if holder is not None:
            print(f"phx: already running on {repo} (pid {holder.pid})", file=sys.stderr)
            return EXIT_ERROR
        unit = unit_name(repo.name)
        result = detach(repo, unit, _forward_args(args))
        print(f"phx: {result.message}", file=sys.stdout if result.ok else sys.stderr)
        if result.ok:
            print(
                f"     follow: phx log {repo} -f · status: phx status {repo} · "
                f"stop: phx stop {repo}"
            )
        return 0 if result.ok else EXIT_ERROR
    sup = Supervisor(
        repo,
        options=options,
        state_root=args.state_dir,
        unit=os.environ.get("PHX_UNIT"),
        verbose=args.verbose,
    )

    def on_signal(signum: int, _frame: FrameType | None) -> None:
        sup.request_stop(f"received {signal.Signals(signum).name}")

    old = {s: signal.signal(s, on_signal) for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
    try:
        return sup.run()
    finally:
        for s, handler in old.items():
            signal.signal(s, handler)


# --------------------------------------------------------------------------- status


def _left(epoch: float) -> str:
    seconds = max(0, int(epoch - time.time()))
    hours, rest = divmod(seconds, 3600)
    return f"{hours}h {rest // 60:02d}m" if hours else f"{rest // 60}m"


def status_report(repo: Path, state_root: Path | None = None) -> dict[str, Any]:
    """Everything ``phx status <repo>`` shows, as JSON-ready data."""
    sdir = state_dir(repo, state_root)
    state = load_state(sdir)
    holder = running(repo)
    report: dict[str, Any] = {
        "repo": str(repo),
        "state_dir": str(sdir),
        "running": asdict(holder) if holder else None,
        "state": state.to_json() if state else None,
        "plan": None,
    }
    if state and state.wait:
        report["wait_left"] = _left(state.wait.until)
    try:
        plan = load_plan(repo)
        elig = next_eligible(plan)
        report["plan"] = {
            "file": plan.plan_file,
            "next": elig.next.id if elig.next else None,
            "in_progress": [p.id for p in elig.resume],
            "blocked": [p.id for p in plan.phases if p.status.name == "BLOCKED"],
            "complete": sum(1 for p in plan.phases if p.status.name == "COMPLETE"),
            "total": len(plan.phases),
            "open_questions": [
                {"id": q.id, "question": q.question, "needed_by": list(q.needed_by)}
                for q in plan.questions
                if q.open
            ],
        }
    except PlanError as exc:
        report["plan_error"] = str(exc)
    return report


def _print_status(report: dict[str, Any]) -> None:
    print(report["repo"])
    holder = report["running"]
    state = report["state"]
    if holder:
        unit = f", unit {holder['unit']}" if holder.get("unit") else ""
        print(
            f"  Supervisor: running (pid {holder['pid']}{unit}, since {holder['started']}, "
            f"phase {holder['phase'] or '-'})"
        )
    else:
        print("  Supervisor: not running")
    if state:
        status = state["status"]
        if not holder and status in (RunStatus.RUNNING, RunStatus.WAITING):
            status += " (supervisor gone: crashed or killed; phx run carries on)"
        print(f"  Last run:   {state['run_id']} {status} (started {state['started']})")
        if state.get("phase"):
            print(
                f"  Phase:      {state['phase']} attempt {state['attempt']}, "
                f"last session {state.get('session_id') or '-'} "
                f"({state.get('classification') or 'running'}), provider "
                f"{state.get('provider') or '-'}"
            )
        wait = state.get("wait")
        if wait:
            print(
                f"  Waiting:    {wait['reason']}\n              wakes {now_ts(wait['until'])} "
                f"(in {report.get('wait_left')})"
            )
        pause = state.get("pause")
        if pause:
            print(f"  Paused:     {pause['reason']}")
            if pause.get("summary"):
                print(f"              {pause['summary']}")
            print(f"              then: phx resume {report['repo']}")
        elif state.get("end_reason") and status not in (RunStatus.RUNNING, RunStatus.WAITING):
            print(f"  Ended:      {state['end_reason']}")
        print(f"  Tokens:     {state['tokens']}, cost ${state['cost_usd']:.2f} (this run)")
        for pid, t in state.get("phases", {}).items():
            print(
                f"    {pid}: {t['outcome'] or '-'}, {t['sessions']} session(s), "
                f"{t['tokens']} tokens, ${t['cost_usd']:.2f}"
                + (f", waited {int(t['wait_s'] // 60)} min" if t["wait_s"] else "")
            )
    else:
        print("  No PHX run recorded yet.")
    plan = report.get("plan")
    if plan:
        extra = []
        if plan["in_progress"]:
            extra.append("🔄 " + ", ".join(plan["in_progress"]))
        if plan["blocked"]:
            extra.append("⛔ " + ", ".join(plan["blocked"]))
        print(
            f"  Plan:       {plan['complete']}/{plan['total']} ✅, next {plan['next'] or 'none'}"
            + (f" ({'; '.join(extra)})" if extra else "")
        )
        for q in plan["open_questions"]:
            print(
                f"  Open question #{q['id']} ({', '.join(q['needed_by']) or '-'}): {q['question']}"
            )
    elif report.get("plan_error"):
        print(f"  Plan:       {report['plan_error']}")


def _cmd_status(args: argparse.Namespace) -> int:
    if args.repo is not None:
        report = status_report(_repo(args.repo), args.state_dir)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            _print_status(report)
        return 0
    root = args.state_dir or default_state_root()
    rows = []
    for sdir in sorted(root.glob("*/")) if root.is_dir() else []:
        state = load_state(sdir)
        if state is None:
            continue
        holder = running(Path(state.repo)) if Path(state.repo).is_dir() else None
        rows.append((sdir.name, state, holder))
    if args.json:
        data = [
            {"repo": s.repo, "state": s.to_json(), "running": asdict(h) if h else None}
            for _n, s, h in rows
        ]
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print(f"No PHX runs recorded under {root}.")
    for name, state, holder in rows:
        live = f"running pid {holder.pid}" if holder else "not running"
        detail = state.status
        if state.wait:
            detail += f", wakes in {_left(state.wait.until)}"
        if state.pause:
            detail += f": {state.pause.reason}"
        print(f"{name}: {live}; last run {detail} (phase {state.phase or '-'})")
    return 0


# --------------------------------------------------------------------------- stop


def _cmd_stop(args: argparse.Namespace) -> int:
    repo = _repo(args.repo)
    holder = running(repo)
    if holder is None or holder.pid is None:
        print(f"phx: no supervisor is running on {repo}")
        return 0
    try:
        os.kill(holder.pid, signal.SIGTERM)
    except ProcessLookupError:
        print(f"phx: supervisor pid {holder.pid} is gone")
        return 0
    except PermissionError:
        print(f"phx: not allowed to signal pid {holder.pid}", file=sys.stderr)
        return EXIT_ERROR
    print(f"phx: asked pid {holder.pid} to stop (phase {holder.phase or '-'}); waiting…")
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        if running(repo) is None:
            state = load_state(state_dir(repo, args.state_dir))
            how = f": {state.end_reason}" if state and state.end_reason else ""
            print(f"phx: stopped{how}")
            return 0
        time.sleep(0.2)
    print(f"phx: still running after {args.timeout:.0f} s (pid {holder.pid})", file=sys.stderr)
    return EXIT_ERROR


# --------------------------------------------------------------------------- log


def format_event(line: str) -> str:
    try:
        record = json.loads(line)
    except ValueError:
        return line.rstrip("\n")
    if not isinstance(record, dict):
        return line.rstrip("\n")
    phase = f" [{record['phase']}]" if record.get("phase") else ""
    return f"{record.get('ts', '?')} {record.get('event', '?')}{phase} {record.get('reason', '')}"


def _cmd_log(args: argparse.Namespace) -> int:
    path = state_dir(_repo(args.repo), args.state_dir) / "run.jsonl"
    if not path.exists():
        print(f"phx: no run log yet ({path})", file=sys.stderr)
        if not args.follow:
            return 1
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    def emit(line: str) -> None:
        print(line.rstrip("\n") if args.json else format_event(line), flush=True)

    with path.open(encoding="utf-8") as fh:
        lines = fh.readlines()
        for line in lines[-args.lines :] if args.lines > 0 else lines:
            emit(line)
        if not args.follow:
            return 0
        try:
            while True:
                line = fh.readline()
                if line:
                    emit(line)
                else:
                    time.sleep(0.5)
        except KeyboardInterrupt:
            return 0


# --------------------------------------------------------------------------- answer


def _git(repo: Path, *argv: str, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *argv],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def answer_question(repo: Path, question_id: str, answer: str, *, force: bool = False) -> str:
    """Write ``Answered <TS>: <answer>`` into the question's Status cell and commit it to ``main``.

    Returns a one-line report; raises ``ValueError`` when it is not safe to change the plan.
    """
    answer = " ".join(answer.split())
    if not answer:
        raise ValueError("the answer is empty")
    holder = running(repo)
    if holder is not None:
        raise ValueError(
            f"a supervisor is running on {repo} (pid {holder.pid}); answer once it pauses, "
            "or phx stop it first"
        )
    branch = _git(repo, "branch", "--show-current").stdout.strip()
    if branch != MAIN:
        raise ValueError(f"the main checkout is on {branch or 'a detached HEAD'}, not {MAIN}")
    try:
        plan = load_plan(repo)
    except PlanError as exc:
        raise ValueError(str(exc)) from None
    question = next((q for q in plan.questions if q.id == question_id.lstrip("#")), None)
    if question is None:
        raise ValueError(f"owner question #{question_id} is not in the plan")
    if not question.open and not force:
        raise ValueError(
            f"owner question #{question.id} is not open ({question.status}); --force overwrites it"
        )
    if _git(repo, "status", "--porcelain", "--", plan.plan_file).stdout.strip():
        raise ValueError(f"{plan.plan_file} has uncommitted changes in the main checkout")
    text = show_main(repo, plan.plan_file)
    path = repo / plan.plan_file
    if text is None or path.read_text(encoding="utf-8") != text:
        raise ValueError(f"{plan.plan_file} in the main checkout differs from {MAIN}")
    ts = now_ts()
    path.write_text(set_question_status(text, question.id, f"Answered {ts}: {answer}"), "utf-8")
    message = f"docs(plan): answer owner question {question.id}\n\nAnswered with phx answer."
    commit = _git(repo, "commit", "-q", "-m", message, "--", plan.plan_file)
    if commit.returncode != 0:
        _git(repo, "checkout", "--", plan.plan_file)
        raise ValueError(f"git commit failed: {commit.stderr.strip()}")
    sha = _git(repo, "rev-parse", "--short", "HEAD").stdout.strip()
    pushed = "no origin remote"
    if _git(repo, "config", "--get", "remote.origin.url").returncode == 0:
        try:
            got = _git(repo, "push", "-q", "origin", MAIN, timeout=120)
            pushed = "pushed" if got.returncode == 0 else f"push failed: {got.stderr.strip()}"
        except subprocess.TimeoutExpired:
            pushed = "push timed out"
    return f"answered #{question.id} in {sha} ({pushed})"


def _cmd_answer(args: argparse.Namespace) -> int:
    repo = _repo(args.repo)
    log = EventLog(state_dir(repo, args.state_dir) / "run.jsonl")
    try:
        report = answer_question(repo, args.question, args.answer, force=args.force)
    except ValueError as exc:
        log.event("answer_refused", reason=str(exc), question=args.question)
        print(f"phx answer: {exc}", file=sys.stderr)
        return EXIT_ERROR
    log.event("answer", reason=report, question=args.question.lstrip("#"))
    print(f"phx: {report}\n     continue with: phx resume {repo}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "plan": _cmd_plan,
        "run": _cmd_run,
        "resume": _cmd_run,
        "status": _cmd_status,
        "stop": _cmd_stop,
        "log": _cmd_log,
        "answer": _cmd_answer,
    }
    handler = handlers.get(args.command)
    if handler is not None:
        return handler(args)
    phase = COMMANDS[args.command][1]
    print(f"phx {args.command}: not implemented yet (Phase {phase:02d})", file=sys.stderr)
    return 2
