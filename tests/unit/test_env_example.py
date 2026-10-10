"""T064: .env.example lists every setting the tool reads (FR-031, SC-009).

A first-time user's only setup step is copying this file, so a setting the code
reads but the example omits is invisible until something fails.
"""

import re
from pathlib import Path

import jira_testgen.config as config_module

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / ".env.example"

# Settings read from the environment, as they appear in config.py.
_SETTING_RE = re.compile(r'values\.get\("(JIRA_[A-Z_]+)"\)')
_EXAMPLE_RE = re.compile(r"^\s*(JIRA_[A-Z_]+)\s*=", re.MULTILINE)


def _settings_read_by_config() -> set[str]:
    source = Path(config_module.__file__).read_text(encoding="utf-8")
    return set(_SETTING_RE.findall(source))


def _settings_in_example() -> set[str]:
    return set(_EXAMPLE_RE.findall(EXAMPLE.read_text(encoding="utf-8")))


def test_the_example_file_exists():
    assert EXAMPLE.is_file()


def test_every_setting_the_code_reads_is_in_the_example():
    missing = _settings_read_by_config() - _settings_in_example()
    assert not missing, f".env.example is missing: {sorted(missing)}"


def test_the_example_lists_no_setting_the_code_ignores():
    # The other direction matters too: a stale example sends people hunting for
    # a setting that does nothing.
    extra = _settings_in_example() - _settings_read_by_config()
    assert not extra, f".env.example lists unused settings: {sorted(extra)}"


def test_the_three_required_settings_have_placeholder_values():
    text = EXAMPLE.read_text(encoding="utf-8")
    for setting in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"):
        match = re.search(rf"^{setting}=(.*)$", text, re.MULTILINE)
        assert match, f"{setting} is absent"
        assert match.group(1).strip(), f"{setting} has no placeholder value"


def test_the_optional_settings_are_left_blank():
    # Blank means "apply the documented default". A placeholder value here
    # would be silently adopted as a real setting.
    text = EXAMPLE.read_text(encoding="utf-8")
    for setting in (
        "JIRA_PROJECT_KEY",
        "JIRA_TEST_ISSUE_TYPE",
        "JIRA_LINK_TYPE",
        "JIRA_AC_FIELD",
    ):
        match = re.search(rf"^{setting}=(.*)$", text, re.MULTILINE)
        assert match, f"{setting} is absent"
        assert match.group(1).strip() == "", f"{setting} should be blank in the example"


def test_the_example_contains_no_real_looking_token():
    text = EXAMPLE.read_text(encoding="utf-8")
    assert "ATATT" not in text, "the example appears to contain a real API token"


def test_the_example_documents_each_default():
    text = EXAMPLE.read_text(encoding="utf-8")
    assert config_module.DEFAULT_TEST_ISSUE_TYPE in text
    assert config_module.DEFAULT_LINK_TYPE in text


def test_the_example_points_at_the_token_page():
    assert "id.atlassian.com" in EXAMPLE.read_text(encoding="utf-8")
