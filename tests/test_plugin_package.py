"""The phased-project plugin: manifests, templates, deny-list, regression vs the pre-12a skill."""

from __future__ import annotations

import difflib
import json
import re
import subprocess
from pathlib import Path

import pytest

import phx
from plugin_render import (
    PLUGIN,
    REPO,
    SKILL,
    TEMPLATES,
    parse_settings,
    render,
    settings_values,
)

PRE12A = Path(__file__).parent / "fixtures" / "skill_pre12a"
GUIDE = REPO / "docs" / "PHX_GETTING_STARTED.md"
EXAMPLE = REPO / "examples" / "CLAUDE.user.md"

FULL_SETTINGS = {
    "Owner": "Nick",
    "Work root": "/home/nick/Work",
    "Vault root": "/home/nick/Documents",
    "Vault projects folder": "02 Projects",
    "Method note": "/home/nick/Documents/04 Resources/Claude Code Phased Project Method.md",
    "OS modifications log": "/home/nick/Documents/04 Resources/OSMods/",
    "Reference implementation": "/home/nick/Work/MeetingMaster3",
}

DENY = [
    "/home/nick",
    "Nick",
    "nick@",
    "Documents/0",
    "MeetingMaster3",
    "chessloop",
    "YTPL2",
    "OCC_",
    "Omarchy",
    "OSMods",
    "Super+Alt",
]
ALLOWED_HANDLE = re.compile(
    r"antonizick/PhaseHypervisor\b|github\.com/antonizick\b|\"name\": \"antonizick\""
)

STEP0 = (
    '   `f="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/phx/$(basename "$(dirname "$(git rev-parse '
    '--path-format=absolute --git-common-dir)")").lock"; [ -e "$f" ] && ! flock -n -s "$f" true && '
    'echo "PHX-RUNNING $(cat "$f")"; printenv PHX_AUTO; echo PHX-CHECK-DONE`.'
)
RESULT_LINE = (
    '  `PHX-RESULT: {"contract":1,"phase":"NN","status":"complete",'
    '"reason":"<one line, ≤ 200 chars>","merged":true,"pushed":true,"question_ids":[]}`'
)


def templates() -> list[Path]:
    return sorted(TEMPLATES.glob("*.md"))


def public_files() -> list[Path]:
    files = [p for p in PLUGIN.rglob("*") if p.is_file()]
    files += [p for p in (REPO / "examples").rglob("*") if p.is_file()]
    return [*files, GUIDE, REPO / ".claude-plugin" / "marketplace.json"]


# --- manifests ---------------------------------------------------------------------------


def test_marketplace_manifest() -> None:
    data = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
    assert data["name"] == "phasehypervisor"
    assert data["owner"] == {"name": "antonizick", "url": "https://github.com/antonizick"}
    (entry,) = data["plugins"]
    assert entry["name"] == "phased-project"
    assert entry["source"] == "./plugins/phased-project"
    assert (REPO / entry["source"]).is_dir()


def test_plugin_manifest_and_version() -> None:
    data = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    assert data["name"] == "phased-project"
    assert data["license"] == "MIT"
    assert data["version"] == phx.__version__
    assert data["author"] == {"name": "antonizick", "url": "https://github.com/antonizick"}
    for key in ("description", "homepage", "repository"):
        assert data[key]
    assert (SKILL / "SKILL.md").is_file()
    assert (PLUGIN / "commands" / "phx.md").is_file()


def test_skill_frontmatter() -> None:
    text = (SKILL / "SKILL.md").read_text()
    assert text.startswith("---\nname: phased-project\n")
    assert "\ndescription: >\n" in text


# --- rendering ---------------------------------------------------------------------------


@pytest.mark.parametrize("settings", [FULL_SETTINGS, {}], ids=["full-settings", "no-settings"])
@pytest.mark.parametrize("template", templates(), ids=lambda p: p.name)
def test_every_template_renders(template: Path, settings: dict[str, str]) -> None:
    out = render(template.read_text(), settings_values(settings), fill_rest=True)
    out = out.replace("`{{`", "")  # the instruction "no `{{` remains" is text, not a marker
    assert "{{" not in out and "}}" not in out


def test_no_settings_render_has_no_personal_text() -> None:
    for template in templates():
        out = render(template.read_text(), settings_values({}), fill_rest=True)
        for word in DENY:
            assert word not in out, (template.name, word)


def test_no_vault_drops_vault_steps() -> None:
    shared = render((TEMPLATES / "_shared-instructions.md").read_text(), settings_values({}))
    assert "Obsidian" not in shared
    assert "4. No vault note is kept for this project; skip this step." in shared
    assert "if the project keeps an OS-modification log" in shared
    command = render((TEMPLATES / "phase-command.md").read_text(), settings_values({}))
    assert "Commit `🔄 In progress` to `main`, then create the worktree" in command
    assert "tell the owner (its PID" in command
    assert "If one is still open, ask the owner before" in command


def test_owner_capitalised_at_sentence_start() -> None:
    shared = render((TEMPLATES / "_shared-instructions.md").read_text(), settings_values({}))
    assert "\nThe owner and other agents read the Status column" in shared
    add = render((TEMPLATES / "phase-add-command.md").read_text(), settings_values({}))
    assert "   - **The owner's request (verbatim intent, TIMESTAMP)**;" in add


def test_settings_parse() -> None:
    block = (
        "# x\n## Phased-project settings\n- Owner: Ada\n- Vault root: `/v`\n"
        "- Work root: <folder>\n## Other\n- Owner: no\n"
    )
    assert parse_settings(block) == {"Owner": "Ada", "Vault root": "/v"}
    assert parse_settings(EXAMPLE.read_text()) == {}


# --- contract-critical text (ADR-0011, ADR-0012) -----------------------------------------


@pytest.mark.parametrize("settings", [FULL_SETTINGS, {}], ids=["full-settings", "no-settings"])
def test_contract_lines_fixed(settings: dict[str, str]) -> None:
    out = render((TEMPLATES / "phase-command.md").read_text(), settings_values(settings))
    lines = out.splitlines()
    assert lines.count("PHX-CONTRACT: 1") == 1
    assert STEP0 in lines
    assert out.count("PHX-CHECK-DONE") == 2
    assert RESULT_LINE in lines
    assert lines[-1].startswith("  `status` is `complete`, `blocked`")
    owner = settings.get("Owner", "the owner")
    expected = (
        (PRE12A / "phase-command.md")
        .read_text()
        .split("## Hands-off mode")[1]
        .replace("Nick", owner)
    )
    assert out.split("## Hands-off mode")[1] == expected


def _changed(old: str, new: str) -> list[str]:
    diff = difflib.unified_diff(old.splitlines(), new.splitlines(), n=0, lineterm="")
    return [line for line in diff if line[:1] in "+-" and line[:3] not in ("+++", "---")]


def test_full_settings_render_matches_pre12a_skill() -> None:
    """With the author's settings, only explained wording changes from the pre-12a live copies."""
    values = settings_values(FULL_SETTINGS)
    for name in ("phase-command.md", "phase-add-command.md"):
        assert render((TEMPLATES / name).read_text(), values) == (PRE12A / name).read_text(), name
    shared = render((TEMPLATES / "_shared-instructions.md").read_text(), values)
    assert _changed((PRE12A / "_shared-instructions.md").read_text(), shared) == [
        "-- [ ] OSMods documentation updated if the host system was modified.",
        "+- [ ] OS-modification log (`/home/nick/Documents/04 Resources/OSMods/`)"
        " updated if the host system was modified.",
    ]


# --- deny-list ---------------------------------------------------------------------------


def test_deny_list() -> None:
    hits = []
    for path in public_files():
        for n, line in enumerate(path.read_text().splitlines(), 1):
            for word in DENY:
                if word in line:
                    hits.append(f"{path.relative_to(REPO)}:{n}: {word}")
            if "antonizick" in ALLOWED_HANDLE.sub("", line):
                hits.append(f"{path.relative_to(REPO)}:{n}: antonizick outside the repo URL/owner")
    assert hits == []


# --- fresh user, manual install, by the guide ---------------------------------------------


def _guide_manual_install() -> list[str]:
    section = GUIDE.read_text().split("### 3b.")[1].split("```bash\n")[1].split("```")[0]
    return [line for line in section.splitlines() if line and not line.startswith("git clone")]


def test_fresh_user_manual_install(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    (work / "PhaseHypervisor").symlink_to(REPO)  # stands in for the `git clone` line
    commands = _guide_manual_install()
    assert commands[0].startswith("mkdir -p ~/.claude/skills")
    for command in commands:
        subprocess.run(
            ["bash", "-c", command],
            cwd=work,
            env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
            check=True,
        )
    skill = home / ".claude" / "skills" / "phased-project"
    assert (skill / "SKILL.md").is_file()
    assert (home / ".claude" / "commands" / "phx.md").is_file()
    assert sorted(p.name for p in (skill / "templates").iterdir()) == [p.name for p in templates()]
    phase_md = render(
        (skill / "templates" / "phase-command.md").read_text(), settings_values({}), fill_rest=True
    )
    assert "\nPHX-CONTRACT: 1\n" in phase_md
    for word in DENY:
        assert word not in phase_md
