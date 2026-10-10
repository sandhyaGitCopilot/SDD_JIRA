"""T050: create, update, link and property payload contracts.

These pin the request bodies this tool sends. Every silent failure mode in the
Jira layer is a payload-shape assumption, so the shapes are asserted field by
field rather than "it returned 201".
"""

from jira_testgen.config import Config, SecretValue
from jira_testgen.draft.schema import TestCase as DraftTestCase
from jira_testgen.jira import issues
from jira_testgen.jira.adf import extract_text
from jira_testgen.jira.client import JiraClient
from jira_testgen.jira.properties import PROPERTY_KEY, PublicationMarker, write_marker
from jira_testgen.jira.search import identity_to_label
from jira_testgen.publish import build_issue_description, build_issue_summary


class Recorder:
    """Captures the exact method, url and body of every request."""

    def __init__(self, responses=None):
        self.sent = []
        self.responses = responses or {}

    def request(self, method, url, params=None, json=None, timeout=None):
        self.sent.append({"method": method, "url": url, "params": params, "json": json})

        class R:
            status_code = 201

            @staticmethod
            def json():
                return {"key": "PROJ-456", "issueLinkTypes": []}

            headers: dict = {}
            text = ""

        return R()


def _client(recorder):
    config = Config(
        base_url="https://example.atlassian.net",
        email="qa@example.com",
        api_token=SecretValue("token-value-long-enough"),
    )
    return JiraClient(config, session=recorder, sleep=lambda _s: None)


def _case():
    return DraftTestCase(
        identity="PROJ-123-TC-007",
        category="boundary",
        covers=["AC-2", "AC-3"],
        summary="Reset link is still valid one minute before expiry",
        preconditions="A reset link was issued 23 hours and 59 minutes ago.",
        steps=["Open the reset link.", "Set a new password."],
        expected_results="The password is changed and sign-in succeeds.",
    )


# --- create ------------------------------------------------------------


def test_create_issue_payload_shape():
    recorder = Recorder()
    issues.create_issue(
        _client(recorder),
        project_key="PROJ",
        issue_type="Task",
        summary="A summary",
        description={"type": "doc", "version": 1, "content": []},
        labels=["tcgen-id-proj-123-tc-007"],
    )
    sent = recorder.sent[0]
    assert sent["method"] == "POST"
    assert sent["url"].endswith("/rest/api/3/issue")
    fields = sent["json"]["fields"]
    assert fields["project"] == {"key": "PROJ"}
    assert fields["issuetype"] == {"name": "Task"}
    assert fields["summary"] == "A summary"
    assert fields["description"]["type"] == "doc"
    assert fields["labels"] == ["tcgen-id-proj-123-tc-007"]


def test_create_issue_omits_labels_when_there_are_none():
    recorder = Recorder()
    issues.create_issue(
        _client(recorder),
        project_key="PROJ",
        issue_type="Task",
        summary="A summary",
        description={"type": "doc", "version": 1, "content": []},
    )
    assert "labels" not in recorder.sent[0]["json"]["fields"]


# --- update ------------------------------------------------------------


def test_update_issue_sends_only_the_given_fields():
    recorder = Recorder()
    issues.update_issue(_client(recorder), "PROJ-456", summary="New summary")
    sent = recorder.sent[0]
    assert sent["method"] == "PUT"
    assert sent["url"].endswith("/rest/api/3/issue/PROJ-456")
    assert sent["json"] == {"fields": {"summary": "New summary"}}


def test_update_issue_with_nothing_to_change_sends_no_request():
    recorder = Recorder()
    issues.update_issue(_client(recorder), "PROJ-456")
    assert recorder.sent == []


# --- link --------------------------------------------------------------


def test_link_payload_puts_the_test_case_inward_and_story_outward():
    recorder = Recorder()
    issues.link_issues(
        _client(recorder), link_type="Relates", inward_key="PROJ-456", outward_key="PROJ-123"
    )
    sent = recorder.sent[0]
    assert sent["url"].endswith("/rest/api/3/issueLink")
    assert sent["json"] == {
        "type": {"name": "Relates"},
        "inwardIssue": {"key": "PROJ-456"},
        "outwardIssue": {"key": "PROJ-123"},
    }


# --- property ----------------------------------------------------------


def test_marker_is_written_under_the_documented_key():
    recorder = Recorder()
    marker = PublicationMarker(
        identity="PROJ-123-TC-007",
        content_fingerprint="9f2b",
        source_issue="PROJ-123",
        generated_at="2026-10-09T00:00:00Z",
        tool_version="0.1.0",
    )
    write_marker(_client(recorder), "PROJ-456", marker)
    sent = recorder.sent[0]
    assert sent["method"] == "PUT"
    assert sent["url"].endswith(f"/rest/api/3/issue/PROJ-456/properties/{PROPERTY_KEY}")
    assert sent["json"]["identity"] == "PROJ-123-TC-007"
    assert sent["json"]["content_fingerprint"] == "9f2b"
    assert sent["json"]["source_issue"] == "PROJ-123"


def test_marker_payload_round_trips_through_from_payload():
    marker = PublicationMarker(
        identity="PROJ-123-TC-007", content_fingerprint="9f2b", source_issue="PROJ-123"
    )
    assert PublicationMarker.from_payload(marker.to_payload()) == marker


# --- story fetch -------------------------------------------------------


def test_story_fetch_requests_the_fields_the_tool_needs():
    recorder = Recorder()
    issues.get_story(_client(recorder), "PROJ-123", ac_field="customfield_10040")
    params = recorder.sent[0]["params"]
    requested = params["fields"].split(",")
    for field in ("summary", "description", "issuelinks", "project", "customfield_10040"):
        assert field in requested


# --- rendered issue content -------------------------------------------


def test_summary_carries_the_test_case_summary():
    assert "still valid one minute before expiry" in build_issue_summary(_case())


def test_summary_stays_within_jiras_limit():
    long_case = _case()
    long_case.summary = "x" * 400
    assert len(build_issue_summary(long_case)) <= 255


def test_description_includes_every_section_and_traceability():
    text = extract_text(build_issue_description(_case(), story_key="PROJ-123")).text
    assert "Preconditions" in text
    assert "23 hours and 59 minutes" in text
    assert "Steps" in text
    assert "- Open the reset link." in text
    assert "Expected results" in text
    assert "The password is changed" in text
    # A reader must see the traceability without running the tool.
    assert "AC-2" in text
    assert "AC-3" in text
    assert "boundary" in text.lower()
    assert "PROJ-123" in text


def test_description_is_a_valid_adf_document():
    doc = build_issue_description(_case(), story_key="PROJ-123")
    assert doc["type"] == "doc"
    assert doc["version"] == 1
    assert all("type" in node for node in doc["content"])


def test_identity_label_is_lowercased_and_prefixed():
    assert identity_to_label("PROJ-123-TC-007") == "tcgen-id-proj-123-tc-007"
