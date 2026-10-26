"""Command-line entry point: ``phx`` / ``python -m phx``."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from phx import __version__

# subcommand -> (help text, phase that implements it)
COMMANDS: dict[str, tuple[str, int]] = {
    "preflight": ("ask every foreseeable question before a hands-off run", 8),
    "run": ("run the remaining phases of a plan unattended", 7),
    "resume": ("resume a stopped or waiting run", 7),
    "status": ("show the state of a run", 7),
    "stop": ("stop a running supervisor", 7),
    "log": ("show or follow the run log", 7),
    "answer": ("answer a recorded owner question and unblock its phase", 7),
    "plan": ("debug: parse a plan and print it", 4),
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
        sub.add_parser(name, help=help_text, description=help_text)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    phase = COMMANDS[args.command][1]
    print(f"phx {args.command}: not implemented yet (Phase {phase:02d})", file=sys.stderr)
    return 2
