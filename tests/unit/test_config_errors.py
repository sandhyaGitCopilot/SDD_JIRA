"""T062: malformed settings vs rejected credentials (FR-033).

These are different problems with different fixes, so they must not collapse
into one message or one exit code. A malformed setting is exit 2 and is caught
before Jira is contacted; credentials Jira rejects are exit 3.
"""

import pytest

from jira_testgen.cli import ExitCode
from jira_testgen.config import Config, SecretValue, load_config
from jira_testgen.errors import AuthError, UserError, classify_status
from jira_testgen.jira.client import JiraClient

TOKEN = "ATATT-token-value-long-enough"
COMPLETE = {
    "JIRA_BASE_URL": "https://example.atlassian.net",
    "JIRA_EMAIL": "qa@example.com",
    "JIRA_API_TOKEN": TOKEN,
}


@pytest.fixture(autouse=True)
def _no_jira_env(monkeypatch):
    import os

    for name in list(os.environ):
        if name.startswith("JIRA_"):
            monkeypatch.delenv(name, raising=False)


def _write_env(tmp_path, values):
    path = tmp_path / ".env"
    path.write_text("\n".join(f"{k}={v}" for k, v in values.items()) + "\n", encoding="utf-8")
    return path


# --- malformed settings: exit 2 -----------------------------------------


@pytest.mark.parametrize(
    ("setting", "value", "expected"),
    [
        ("JIRA_BASE_URL", "ftp://example.net", "https://"),
        ("JIRA_BASE_URL", "example.atlassian.net", "https://"),
        ("JIRA_EMAIL", "not-an-address", "address"),
        ("JIRA_PROJECT_KEY", "lower_case", "uppercase"),
        ("JIRA_AC_FIELD", "acceptance_criteria", "customfield_12345"),
    ],
)
def test_malformed_settings_are_named_with_guidance(tmp_path, setting, value, expected):
    with pytest.raises(UserError) as excinfo:
        load_config(_write_env(tmp_path, dict(COMPLETE, **{setting: value})))
    message = str(excinfo.value)
    assert setting in message
    assert expected in message


def test_a_malformed_setting_echoes_the_offending_value(tmp_path):
    # Showing what was found is what makes a typo obvious.
    with pytest.raises(UserError) as excinfo:
        load_config(_write_env(tmp_path, dict(COMPLETE, JIRA_EMAIL="qa.example.com")))
    assert "qa.example.com" in str(excinfo.value)


def test_a_malformed_setting_never_echoes_the_token(tmp_path):
    with pytest.raises(UserError) as excinfo:
        load_config(_write_env(tmp_path, dict(COMPLETE, JIRA_BASE_URL="ftp://x")))
    assert TOKEN not in str(excinfo.value)


def test_user_error_carries_the_configuration_exit_code():
    assert UserError("x").exit_code == int(ExitCode.CONFIG_ERROR) == 2


# --- rejected credentials: exit 3 ---------------------------------------


class _Resp:
    def __init__(self, status):
        self.status_code = status
        self.headers = {}
        self.text = ""

    def json(self):
        return {"errorMessages": ["Client must be authenticated"]}


class _Session:
    def __init__(self, status):
        self.status = status

    def request(self, *_args, **_kwargs):
        return _Resp(self.status)


def _client(status):
    config = Config(
        base_url="https://example.atlassian.net",
        email="qa@example.com",
        api_token=SecretValue(TOKEN),
    )
    return JiraClient(config, session=_Session(status), sleep=lambda _s: None)


def test_a_401_is_an_auth_error_not_a_config_error():
    with pytest.raises(AuthError):
        _client(401).get("myself")


def test_auth_error_carries_its_own_exit_code():
    assert AuthError("x").exit_code == int(ExitCode.AUTH_REJECTED) == 3


def test_auth_and_config_exit_codes_are_distinct():
    # The whole point of FR-033: "fix your .env" and "Jira said no" are
    # different answers.
    assert UserError("x").exit_code != AuthError("x").exit_code


def test_a_rejected_credential_message_does_not_contain_the_token():
    try:
        _client(401).get("myself")
    except AuthError as exc:
        assert TOKEN not in str(exc)
        assert TOKEN not in exc.message


def test_a_403_is_a_permission_problem_not_a_credential_problem():
    # The account is known; it simply may not do this. Telling the engineer to
    # check their token would send them the wrong way.
    error = classify_status(403)
    assert not isinstance(error, AuthError)
    assert "permission" in error.message.lower()
