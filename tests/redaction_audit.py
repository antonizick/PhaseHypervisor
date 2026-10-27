#!/usr/bin/env python3
"""Secret-redaction audit of PHX output (Phase 11, task 5).

Scans files for anything :func:`phx.redact.redact_text` would still change, i.e. a
token shape (``sk-or-…``, ``sk-ant-…``, ``ghp_…``), a secret assignment
(``ANTHROPIC_AUTH_TOKEN=…``, ``"GH_TOKEN": "…"``) or a bearer header that reached
disk unredacted. It never prints a secret: a finding names the file, the line and
which pattern matched.

    uv run python tests/redaction_audit.py ~/.local/state/phx [more dirs or files]

Exit 0 when clean, 1 when something leaked. ``tests/test_redaction_audit.py`` keeps
it as a test; set ``PHX_AUDIT_DIR`` to audit real state as part of the suite.
"""

import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from phx.redact import _ASSIGNMENTS, _BEARER, _PATTERNS, REDACTED

_SUFFIXES = {".jsonl", ".json", ".log", ".md", ".txt", ".toml", ""}


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    pattern: str


@dataclass
class Report:
    files: int = 0
    lines: int = 0
    redacted: int = 0  # lines that carry [REDACTED]: redaction did its job there
    findings: tuple[Finding, ...] = ()

    @property
    def clean(self) -> bool:
        return not self.findings


def _files(paths: Iterable[Path]) -> Iterator[Path]:
    for path in paths:
        if path.is_file():
            yield path
        elif path.is_dir():
            for sub in sorted(path.rglob("*")):
                if sub.is_file() and not sub.is_symlink() and sub.suffix in _SUFFIXES:
                    yield sub


def _which(line: str) -> str | None:
    for pattern in _PATTERNS:
        if pattern.search(line):
            return pattern.pattern.split("[", 1)[0] or pattern.pattern[:12]
    for m in _ASSIGNMENTS.finditer(line):
        if REDACTED not in m.group(3):
            return f"{m.group(1)} assignment"
    if any(REDACTED not in m.group(0) for m in _BEARER.finditer(line)):
        return "bearer header"
    return None


def audit(paths: Iterable[Path]) -> Report:
    report = Report()
    findings: list[Finding] = []
    for path in _files(paths):
        report.files += 1
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            report.lines += 1
            report.redacted += REDACTED in line
            hit = _which(line)
            if hit:
                findings.append(Finding(path, n, hit))
    report.findings = tuple(findings)
    return report


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: redaction_audit.py PATH [PATH …]", file=sys.stderr)
        return 2
    report = audit(Path(a).expanduser() for a in argv)
    for f in report.findings:
        print(f"LEAK {f.path}:{f.line}: {f.pattern}")
    print(
        f"audited {report.files} files, {report.lines} lines; "
        f"{report.redacted} lines carry {REDACTED}; {len(report.findings)} unredacted secrets"
    )
    return 0 if report.clean else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
