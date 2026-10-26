"""Append-only JSONL event log with a human-readable stderr mirror (spec R10)."""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, TextIO

from phx.redact import redact


class EventLog:
    """Writes one redacted JSON object per line to ``path`` and fsyncs it."""

    def __init__(self, path: Path, *, verbose: bool = False, mirror: TextIO | None = None) -> None:
        self.path = path
        self.verbose = verbose
        self._mirror = mirror if mirror is not None else sys.stderr
        path.parent.mkdir(parents=True, exist_ok=True)

    def event(
        self, event: str, *, phase: str | None = None, reason: str = "", **fields: Any
    ) -> None:
        now = time.time()
        record = redact(
            {
                "ts": time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(now)),
                "epoch": now,
                "event": event,
                "phase": phase,
                "reason": reason,
                **fields,
            }
        )
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        # One O_APPEND write per record keeps concurrent appenders from interleaving.
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, line.encode())
            os.fsync(fd)
        finally:
            os.close(fd)
        if self.verbose:
            tag = f" [{phase}]" if phase else ""
            print(f"{record['ts']} {event}{tag} {record['reason']}".rstrip(), file=self._mirror)
