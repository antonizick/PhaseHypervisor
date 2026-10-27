"""Reference renderer for the phased-project skill templates (tests only).

The skill is applied by an agent, which fills the templates by hand. This module
implements the same rules (``plugins/phased-project/skills/phased-project/SKILL.md``,
"Settings and template markers") so that tests can check them:

- ``{{NAME}}`` is replaced by a value;
- ``{{#NAME}}...{{/NAME}}`` is kept when ``NAME`` is set and dropped otherwise;
- ``{{^NAME}}...{{/NAME}}`` is kept when ``NAME`` is unset and dropped otherwise;
- a dropped section that fills whole lines takes its line break with it;
- ``{{OWNER}}`` is capitalised at the start of a sentence or list item.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugins" / "phased-project"
SKILL = PLUGIN / "skills" / "phased-project"
TEMPLATES = SKILL / "templates"

DEFAULT_OWNER = "the owner"
GUIDE_URL = "https://github.com/antonizick/PhaseHypervisor/blob/main/docs/PHX_GETTING_STARTED.md"

_SECTION = re.compile(r"(^)?\{\{([#^])([A-Z0-9_]+)\}\}(.*?)\{\{/\3\}\}(\n)?", re.S | re.M)
_SENTENCE_START = re.compile(
    r"(^[ \t]*(?:(?:[-*]|\d+\.)[ \t]+)?(?:\*\*)?|[.!?:][ \t]+(?:\*\*)?)\{\{OWNER\}\}", re.M
)
PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
FREE_TEXT = re.compile(r"\{\{[^{}`#^/][^{}`]*\}\}")


def settings_values(settings: dict[str, str] | None) -> dict[str, str]:
    """Map a parsed settings section to template values (missing settings stay unset)."""
    s = settings or {}
    values: dict[str, str] = {"OWNER": s.get("Owner") or DEFAULT_OWNER}
    method = s.get("Method note")
    values["METHOD_LINK"] = (
        f"[[{Path(method).stem}]]" if method else f"[phased-project guide]({GUIDE_URL})"
    )
    if s.get("OS modifications log"):
        values["OS_LOG"] = s["OS modifications log"]
    if s.get("Vault root"):
        values["VAULT"] = "on"
    return values


def render_sections(text: str, values: dict[str, str]) -> str:
    """Resolve ``{{#X}}`` / ``{{^X}}`` sections until none are left."""

    def repl(m: re.Match[str]) -> str:
        at_line_start, kind, name, body, newline = (
            m.group(1),
            m.group(2),
            m.group(3),
            m.group(4),
            m.group(5),
        )
        keep = bool(values.get(name)) == (kind == "#")
        if keep:
            return (at_line_start or "") + body + (newline or "")
        if at_line_start is not None and newline:
            return ""
        return newline or ""

    previous = None
    while previous != text:
        previous = text
        text = _SECTION.sub(repl, text)
    return text


def render(text: str, values: dict[str, str], fill_rest: bool = False) -> str:
    """Render a template. With ``fill_rest`` every other placeholder gets a dummy value."""
    text = render_sections(text, values)
    owner = values.get("OWNER", DEFAULT_OWNER)
    text = _SENTENCE_START.sub(lambda m: m.group(1) + owner[:1].upper() + owner[1:], text)

    def fill(m: re.Match[str]) -> str:
        name = m.group(1)
        if name in values:
            return values[name]
        return f"<dummy {name.lower()}>" if fill_rest else m.group(0)

    text = PLACEHOLDER.sub(fill, text)
    if fill_rest:  # free-text markers such as {{Open|Decided|Deferred to Phase NN}}
        text = FREE_TEXT.sub("<dummy text>", text)
    return text


def parse_settings(markdown: str) -> dict[str, str]:
    """Read the ``## Phased-project settings`` section: ``- Key: value`` bullets."""
    settings: dict[str, str] = {}
    inside = False
    for line in markdown.splitlines():
        if line.startswith("## "):
            inside = line.strip() == "## Phased-project settings"
            continue
        if not inside:
            continue
        m = re.match(r"^-\s+([^:]+):\s*(.*?)\s*$", line)
        if m and m.group(2) and not m.group(2).startswith("<"):
            settings[m.group(1).strip()] = m.group(2).strip("`")
    return settings
