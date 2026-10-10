"""T061: configuration validation (FR-030, FR-032, FR-035).

Two properties matter beyond "it rejects bad input":

- every missing setting is named **exactly as it appears in .env**, so the
  engineer knows which line to edit;
- validation happens **before any network call**, which is what keeps a
  configuration error distinguishable from a credential rejection.
"""

import pytest

from jira_testgen.config import (
    DEFAULT_LINK_TYPE,
    DEFAULT_TEST_ISSUE_TYPE,
    load_config,
    validate_issue_key,
)
from jira_testgen.errors import UserError

TOKEN = "ATATT-token-value-long-enough"

COMPLETE = {
    "JIRA_BASE_URL": "https://example.atlassian.net",
    "JIRA_EMAIL": "qa@example.com",
    "JIRA_API_TOKEN": TOKEN,
}


@pytest.fixture(autouse=True)
def _no_jira_env(monkeypatch):
    # A real environment variable would otherwise mask a blanked file setting.
    for name in list(__import__("os").environ):
        if name.startswith("JIRA_"):
            monkeypatch.delenv(name, raising=False)


def _write_env(tmp_path, values):
    path = tmp_path / ".env"
    path.write_text(
        "\n".join(f"{k}={v}" for k, v in values.items() if v is not None) + "\n",
        encoding="utf-8",
    )
    return path


def test_a_complete_configuration_loads(tmp_path):
    config = load_config(_write_env(tmp_path, COMPLETE))
    assert config.base_url == "https://example.atlassian.net"
    assert config.email == "qa@example.com"
    assert config.api_token.reveal() == TOKEN


@pytest.mark.parametrize("setting", ["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"])
def test_each_required_setting_is_named_when_blank(tmp_path, setting):
    values = dict(COMPLETE)
    values[setting] = ""
    with pytest.raises(UserError) as excinfo:
        load_config(_write_env(tmp_path, values))
    assert setting in str(excinfo.value)


@pytest.mark.parametrize("setting", ["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"])
def test_each_required_setting_is_named_when_absent(tmp_path, setting):
    values = dict(COMPLETE)
    values[setting] = None
    with pytest.raises(UserError) as excinfo:
        load_config(_write_env(tmp_path, values))
    assert setting in str(excinfo.value)


def test_all_missing_settings_are_reported_together(tmp_path):
    # An engineer fixing three blanks should learn about three blanks, not
    # discover them one run at a time.
    with pytest.raises(UserError) as excinfo:
        load_config(_write_env(tmp_path, {"JIRA_PROJECT_KEY": "PROJ"}))
    message = str(excinfo.value)
    for setting in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"):
        assert setting in message


def test_the_message_points_at_env_example(tmp_path):
    with pytest.raises(UserError) as excinfo:
        load_config(_write_env(tmp_path, {}))
    assert ".env.example" in str(excinfo.value)


def test_a_missing_file_is_treated_as_an_empty_configuration(tmp_path):
    with pytest.raises(UserError) as excinfo:
        load_config(tmp_path / "absent.env")
    assert "JIRA_BASE_URL" in str(excinfo.value)


def test_validation_happens_before_any_network_call(tmp_path):
    # Nothing in load_config may touch the network; if it did, a typo would
    # cost a round trip and the exit codes would blur.
    import jira_testgen.config as config_module

    assert "requests" not in config_module.__dict__
    with pytest.raises(UserError):
        load_config(_write_env(tmp_path, {}))


# --- optional settings and their defaults (FR-035) ----------------------


def test_defaults_are_applied_and_reported(tmp_path):
    config = load_config(_write_env(tmp_path, COMPLETE))
    assert config.test_issue_type == DEFAULT_TEST_ISSUE_TYPE
    assert config.link_type == DEFAULT_LINK_TYPE
    assert config.project_key is None
    assert config.ac_field is None

    assert config.defaults_used["JIRA_TEST_ISSUE_TYPE"] == DEFAULT_TEST_ISSUE_TYPE
    assert config.defaults_used["JIRA_LINK_TYPE"] == DEFAULT_LINK_TYPE
    assert "JIRA_PROJECT_KEY" in config.defaults_used
    assert "JIRA_AC_FIELD" in config.defaults_used


def test_supplied_optional_settings_are_not_reported_as_defaults(tmp_path):
    values = dict(
        COMPLETE,
        JIRA_PROJECT_KEY="PROJ",
        JIRA_TEST_ISSUE_TYPE="Test",
        JIRA_LINK_TYPE="Blocks",
        JIRA_AC_FIELD="customfield_10040",
    )
    config = load_config(_write_env(tmp_path, values))
    assert config.project_key == "PROJ"
    assert config.test_issue_type == "Test"
    assert config.link_type == "Blocks"
    assert config.ac_field == "customfield_10040"
    assert config.defaults_used == {}


def test_trailing_slash_on_base_url_is_normalized(tmp_path):
    config = load_config(_write_env(tmp_path, dict(COMPLETE, JIRA_BASE_URL="https://x.net/")))
    assert config.base_url == "https://x.net"
    assert config.api_url("issue/PROJ-1") == "https://x.net/rest/api/3/issue/PROJ-1"


# --- issue key shape ----------------------------------------------------


@pytest.mark.parametrize("key", ["PROJ-123", "A-1", "PROJ_X-99"])
def test_valid_issue_keys_pass(key):
    assert validate_issue_key(key) == key


@pytest.mark.parametrize("key", ["", "proj-123", "PROJ", "PROJ-", "-123", "not a key", None])
def test_malformed_issue_keys_are_rejected(key):
    with pytest.raises(UserError) as excinfo:
        validate_issue_key(key)
    assert "PROJ-123" in str(excinfo.value)


def test_issue_key_whitespace_is_tolerated():
    assert validate_issue_key("  PROJ-123  ") == "PROJ-123"
