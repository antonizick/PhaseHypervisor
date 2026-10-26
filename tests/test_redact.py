import pytest

from phx.redact import REDACTED, redact, redact_text


@pytest.mark.parametrize(
    "secret",
    [
        "sk-or-v1-abcdef0123456789abcdef",
        "sk-ant-api03-AbCdEf0123456789_-xyz",
        "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2",
        "gho_" + "a1B2c3D4e5F6g7H8i9J0k1L2",
        "github_pat_11ABCDEFG0123456789_abcdefghijklmnop",
    ],
)
def test_token_shapes_are_redacted(secret: str) -> None:
    out = redact_text(f"key is {secret} ok")
    assert secret not in out
    assert REDACTED in out


@pytest.mark.parametrize("name", ["ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"])
def test_env_assignments(name: str) -> None:
    assert redact_text(f"{name}=hunter2 next") == f"{name}={REDACTED} next"
    assert redact_text(f'{name}="two words"') == f"{name}={REDACTED}"


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
    ],
)
def test_no_false_positives(text: str) -> None:
    assert redact_text(text) == text
