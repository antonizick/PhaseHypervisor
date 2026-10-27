import pytest

from phx.redact import REDACTED, redact, redact_text


@pytest.mark.parametrize(
    "secret",
    [
        "sk-or-v1-abcdef0123456789abcdef",
        "sk-ant-api03-AbCdEf0123456789_-xyz",
        "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2",
        "gho_" + "a1B2c3D4e5F6g7H8i9J0k1L2",
        "ghs_" + "a1B2c3D4e5F6g7H8i9J0k1L2",
        "sk-ant-oat01-AbCdEf0123456789_-xyz",
        "github_pat_11ABCDEFG0123456789_abcdefghijklmnop",
    ],
)
def test_token_shapes_are_redacted(secret: str) -> None:
    out = redact_text(f"key is {secret} ok")
    assert secret not in out
    assert REDACTED in out


@pytest.mark.parametrize(
    "name",
    [
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "DB_PASSWORD",
        "CLIENT_SECRET",
    ],
)
def test_env_assignments(name: str) -> None:
    assert redact_text(f"{name}=hunter2 next") == f"{name}={REDACTED} next"
    assert redact_text(f'{name}="two words"') == f'{name}="{REDACTED}"'
    assert redact_text(f"export {name}='x y'") == f"export {name}='{REDACTED}'"
    assert redact_text(f"{name}: hunter2") == f"{name}: {REDACTED}"


def test_json_forms_stay_valid_json() -> None:
    import json

    raw = json.dumps({"env": {"ANTHROPIC_AUTH_TOKEN": "hunter2", "ANTHROPIC_MODEL": "opus"}})
    out = redact_text(raw)
    assert "hunter2" not in out
    assert json.loads(out) == {"env": {"ANTHROPIC_AUTH_TOKEN": REDACTED, "ANTHROPIC_MODEL": "opus"}}
    # a JSON document quoted inside a stream-json string (tool output)
    inner = json.dumps({"GH_TOKEN": "abc def", "x": 1})
    line = json.dumps({"type": "user", "content": inner + " and OPENROUTER_API_KEY=zz9"})
    out = redact_text(line)
    assert "abc def" not in out and "zz9" not in out
    assert json.loads(json.loads(out)["content"].rsplit(" and ", 1)[0]) == {
        "GH_TOKEN": REDACTED,
        "x": 1,
    }
    header = json.dumps({"h": "Authorization: Bearer abc.def"})
    assert json.loads(redact_text(header)) == {"h": f"Authorization: Bearer {REDACTED}"}


def test_bearer_header() -> None:
    assert redact_text("Authorization: Bearer abc.def") == f"Authorization: Bearer {REDACTED}"


def test_nested_json() -> None:
    value = {"a": ["x sk-ant-api03-AbCdEf0123456789", {"b": 1}], "c": ("ghp_" + "z" * 24,)}
    out = redact(value)
    assert out == {"a": [f"x {REDACTED}", {"b": 1}], "c": [REDACTED]}


@pytest.mark.parametrize(
    "text",
    [
        "Phase 02 complete at 462d097",
        "sha256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "the sk- prefix and a ghp_ mention",
        "ANTHROPIC_MODEL=claude-sonnet-5-5",
        "CLAUDE_CODE_MAX_OUTPUT_TOKENS=32000",
        '{"input_tokens": 12, "cache_read_input_tokens": 3}',
        "max_tokens: 400",
    ],
)
def test_no_false_positives(text: str) -> None:
    assert redact_text(text) == text


@pytest.mark.parametrize(
    ("text", "kept"),
    [
        ("DB_PASSWORD=abc,def;ghi done", " done"),
        ("GITHUB_TOKEN: abc}def]x", ""),
        (r"GH_TOKEN=abc\\def", ""),
    ],
)
def test_unquoted_values_are_redacted_whole(text: str, kept: str) -> None:
    """Code review (Phase 11): punctuation inside an unquoted secret is part of it."""
    name = text.split("=")[0].split(":")[0]
    assert redact_text(text).endswith(f"{REDACTED}{kept}") and redact_text(text).startswith(name)


def test_idempotent() -> None:
    once = redact_text(f'GH_TOKEN=abc "OPENROUTER_API_KEY": "x" {"sk-or-v1-" + "f" * 20}')
    assert redact_text(once) == once and once.count(REDACTED) == 3


def test_names_after_escaped_newlines() -> None:
    """Multi-line `env` output inside a JSON string (Phase 11 security review)."""
    import json

    line = json.dumps({"content": "PATH=/usr/bin\nANTHROPIC_AUTH_TOKEN=abc123\tGH_TOKEN=xyz"})
    out = redact_text(line)
    assert "abc123" not in out and "xyz" not in out
    assert json.loads(out)["content"].splitlines()[0] == "PATH=/usr/bin"
