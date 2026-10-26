"""Secret redaction applied to everything PHX writes to a log."""

import re
from typing import Any

REDACTED = "[REDACTED]"

# Each pattern keeps any leading label and replaces only the secret part.
_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-or-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"gh[po]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
)
_ASSIGNMENTS = re.compile(
    r"\b(ANTHROPIC_AUTH_TOKEN|ANTHROPIC_API_KEY)(\s*[=:]\s*)(?:\"[^\"]*\"|'[^']*'|\S+)"
)
_BEARER = re.compile(r"(Authorization\s*:\s*Bearer\s+)\S+", re.IGNORECASE)


def redact_text(text: str) -> str:
    """Return ``text`` with known secret shapes replaced by ``[REDACTED]``."""
    text = _ASSIGNMENTS.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
    text = _BEARER.sub(lambda m: f"{m.group(1)}{REDACTED}", text)
    for pattern in _PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def redact(value: Any) -> Any:
    """Redact every string inside nested dicts, lists and tuples (keys included)."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {redact(k): redact(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    return value
