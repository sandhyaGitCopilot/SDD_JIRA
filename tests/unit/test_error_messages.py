"""T088: every error message names its subject.

The spec's messages are written to a standard: name the setting, name the file,
or name the test case. "Configuration is invalid" sends the engineer hunting;
"JIRA_EMAIL does not look like an address (found 'nope')" does not.

An audit is a point-in-time check that rots. These tests fix the standard in
place, so a future message that names nothing fails here instead of reaching a
user.
"""

from __future__ import annotations

import pytest

from jira_testgen.config import load_config, validate_issue_key
from jira_testgen.criteria import extract_criteria
from jira_testgen.draft.schema import DraftSchemaError, load_draft
from jira_testgen.errors import CriteriaNotFound, UserError
from jira_testgen.limits import ceiling_message, size_warning


@pytest.fixture(autouse=True)
def _no_jira_env(monkeypatch):
    import os

    for name in list(os.environ):
        if name.startswith("JIRA_"):
            monkeypatch.delenv(name, raising=False)


# --- configuration: name the setting ------------------------------------


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({}, "JIRA_BASE_URL"),
        ({"JIRA_BASE_URL": "https://x.net"}, "JIRA_EMAIL"),
        ({"JIRA_BASE_URL": "https://x.net", "JIRA_EMAIL": "a@b.c"}, "JIRA_API_TOKEN"),
        (
            {
                "JIRA_BASE_URL": "ftp://x",
                "JIRA_EMAIL": "a@b.c",
                "JIRA_API_TOKEN": "token-value",
            },
            "JIRA_BASE_URL",
        ),
        (
            {
                "JIRA_BASE_URL": "https://x.net",
                "JIRA_EMAIL": "a@b.c",
                "JIRA_API_TOKEN": "token-value",
                "JIRA_PROJECT_KEY": "lower",
            },
            "JIRA_PROJECT_KEY",
        ),
        (
            {
                "JIRA_BASE_URL": "https://x.net",
                "JIRA_EMAIL": "a@b.c",
                "JIRA_API_TOKEN": "token-value",
                "JIRA_AC_FIELD": "nope",
            },
            "JIRA_AC_FIELD",
        ),
    ],
)
def test_configuration_errors_name_the_setting(tmp_path, values, expected):
    path = tmp_path / ".env"
    path.write_text("\n".join(f"{k}={v}" for k, v in values.items()) + "\n", encoding="utf-8")
    with pytest.raises(UserError) as excinfo:
        load_config(path)
    assert expected in str(excinfo.value)


def test_configuration_errors_say_where_to_fix_them():
    # Naming the setting is only half of it; the engineer also has to know
    # which file to open.
    with pytest.raises(UserError) as excinfo:
        load_config("no-such-file.env")
    message = str(excinfo.value)
    assert ".env" in message


# --- issue keys: name the offending value -------------------------------


def test_a_bad_issue_key_shows_the_expected_shape():
    with pytest.raises(UserError) as excinfo:
        validate_issue_key("not a key")
    message = str(excinfo.value)
    assert "not a key" in message
    assert "PROJ-123" in message


# --- criteria: name both places searched --------------------------------


def test_the_no_criteria_message_names_both_sources():
    with pytest.raises(CriteriaNotFound) as excinfo:
        extract_criteria(description_text="nothing here", ac_field="customfield_10040")
    message = str(excinfo.value)
    assert "customfield_10040" in message
    assert "Acceptance Criteria" in message
    # And what to do next.
    assert "JIRA_AC_FIELD" in message


# --- drafts: name the file ----------------------------------------------


def test_a_missing_draft_names_the_path_and_the_next_step(tmp_path):
    with pytest.raises(DraftSchemaError) as excinfo:
        load_draft(tmp_path / "PROJ-123.yaml")
    message = str(excinfo.value)
    assert "PROJ-123.yaml" in message
    assert "prepare" in message


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("- not a mapping\n", "PROJ-123.yaml"),
        ("schema_version: 99\n", "99"),
        ("schema_version: 1\napproval:\n  status: maybe\n", "maybe"),
    ],
)
def test_draft_schema_errors_name_the_file_or_the_offending_value(tmp_path, body, expected):
    path = tmp_path / "PROJ-123.yaml"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(DraftSchemaError) as excinfo:
        load_draft(path)
    assert expected in str(excinfo.value)


def test_a_malformed_test_case_names_its_identity(tmp_path):
    path = tmp_path / "PROJ-123.yaml"
    path.write_text(
        "schema_version: 1\n"
        "source_issue: PROJ-123\n"
        "criteria: []\n"
        "test_cases:\n"
        "  - identity: PROJ-123-TC-007\n"
        "    steps: not-a-list\n"
        "approval:\n"
        "  status: draft\n"
        "  approved_fingerprint: null\n",
        encoding="utf-8",
    )
    with pytest.raises(DraftSchemaError) as excinfo:
        load_draft(path)
    assert "PROJ-123-TC-007" in str(excinfo.value)


# --- validation: name the test case or the criterion --------------------


def test_every_validation_error_names_a_subject():
    """No validation message may be generic.

    Each one must mention the draft file, a test case identity, or a criterion
    label -- the three things an engineer can act on.
    """
    from jira_testgen.draft.schema import AcceptanceCriterion, DraftSet
    from jira_testgen.draft.schema import TestCase as DraftTestCase
    from jira_testgen.draft.validate import validate_draft

    draft = DraftSet(
        source_issue="PROJ-1",
        criteria=[
            AcceptanceCriterion(ordinal=1, label="AC-1", source_text="One."),
            AcceptanceCriterion(ordinal=2, label="AC-2", source_text="Two."),
        ],
        test_cases=[
            DraftTestCase(
                identity="PROJ-1-TC-001",
                category="bogus",
                covers=["AC-9"],
                summary="",
                preconditions="",
                steps=[],
                expected_results="",
            ),
            DraftTestCase(
                identity="bad-identity",
                category="positive",
                covers=[],
                summary="x" * 300,
                preconditions="Same as above.",
                steps=["ok"],
                expected_results="ok",
            ),
        ],
    )
    report = validate_draft(draft, source="drafts/PROJ-1.yaml")
    assert report.errors

    subjects = ("drafts/PROJ-1.yaml", "PROJ-1-TC-001", "bad-identity", "AC-1", "AC-2", "AC-9")
    for error in report.errors:
        assert any(s in error for s in subjects), f"names no subject: {error}"


# --- limits: name the count and the threshold ---------------------------


def test_the_size_warning_names_the_count():
    assert "28" in (size_warning(28) or "")


def test_the_ceiling_message_names_count_limit_and_the_way_forward():
    message = ceiling_message(120)
    assert "120" in message
    assert "100" in message
    assert "--allow-large" in message


# --- nothing is a bare class name --------------------------------------


def test_no_error_message_is_only_a_class_name():
    # A guard against `raise UserError("invalid")`-style messages.
    import pathlib
    import re

    src = pathlib.Path(__import__("jira_testgen").__file__).parent
    offenders = []
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r'raise \w*Error\(\s*"([^"]{1,25})"\s*\)', text):
            offenders.append(f"{path.name}: {match.group(1)}")
    assert not offenders, f"messages too short to be actionable: {offenders}"
