"""Append-only JSONL event log with a human-readable stderr mirror (spec R10)."""

import errno
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
        self.write_errors = 0  # records that could not be written to ``path``
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
        try:
            # One O_APPEND write per record keeps concurrent appenders from interleaving.
            fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                if os.write(fd, line.encode()) != len(line.encode()):
                    raise OSError(errno.ENOSPC, "short write")
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError as exc:
            # Full disk or a vanished state dir must not stop the run (Phase 11): the
            # record goes to stderr, which a detached run keeps in the journal.
            self.write_errors += 1
            print(
                f"phx: {self.path} not written ({exc.strerror or exc}): {line.rstrip()}",
                file=self._mirror,
            )
            return
        if self.verbose:
            tag = f" [{phase}]" if phase else ""
            print(f"{record['ts']} {event}{tag} {record['reason']}".rstrip(), file=self._mirror)
