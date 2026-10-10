"""T045: the publish happy path (FR-018 - FR-021, quickstart scenario A)."""

from jira_testgen.jira.properties import PROPERTY_KEY
from jira_testgen.jira.search import identity_to_label
from jira_testgen.publish import publish_draft

from .draft_factory import STORY_KEY, many_cases, write_approved
from .fake_jira import FakeJira


def _publish_twelve(make_client, drafts_dir):
    write_approved(drafts_dir, cases=many_cases(12))
    fake = FakeJira()
    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    return fake, report


def test_twelve_test_cases_become_twelve_issues(make_client, drafts_dir):
    fake, report = _publish_twelve(make_client, drafts_dir)
    assert len(fake.created) == 12


def test_every_issue_is_linked_to_the_story(make_client, drafts_dir):
    fake, _ = _publish_twelve(make_client, drafts_dir)
    assert len(fake.links) == 12
    assert all(outward == STORY_KEY for _inward, outward in fake.links)


def test_every_test_case_is_reported_as_created_with_its_key(make_client, drafts_dir):
    fake, report = _publish_twelve(make_client, drafts_dir)
    assert len(report.outcomes) == 12
    assert all(o.decision == "created" for o in report.outcomes)
    assert all(o.issue_key for o in report.outcomes)


def test_verdict_is_success(make_client, drafts_dir):
    _, report = _publish_twelve(make_client, drafts_dir)
    assert report.verdict == "success"
    assert report.exit_code == 0


def test_each_created_issue_carries_its_identity_label(make_client, drafts_dir):
    fake, report = _publish_twelve(make_client, drafts_dir)
    for outcome in report.outcomes:
        payload = fake.issues[outcome.issue_key]
        labels = payload["fields"]["labels"]
        assert identity_to_label(outcome.identity) in labels


def test_each_created_issue_carries_a_publication_marker(make_client, drafts_dir):
    fake, report = _publish_twelve(make_client, drafts_dir)
    for outcome in report.outcomes:
        marker = fake.properties[outcome.issue_key]
        assert marker["identity"] == outcome.identity
        assert marker["source_issue"] == STORY_KEY
        assert marker["content_fingerprint"]


def test_issue_content_carries_the_test_case(make_client, drafts_dir):
    fake, report = _publish_twelve(make_client, drafts_dir)
    payload = fake.issues[report.outcomes[0].issue_key]["fields"]
    assert payload["project"] == {"key": "PROJ"}
    assert payload["issuetype"] == {"name": "Task"}
    assert payload["summary"]
    assert payload["description"]["type"] == "doc"

    from jira_testgen.jira.adf import extract_text

    text = extract_text(payload["description"]).text
    assert "Preconditions" in text
    assert "Steps" in text
    assert "Expected results" in text
    # Traceability is visible to a reader without the tool.
    assert "AC-1" in text


def test_report_names_the_criteria_source_and_defaults(make_client, drafts_dir):
    _, report = _publish_twelve(make_client, drafts_dir)
    assert report.criteria_source == "description"
    assert isinstance(report.defaults_used, dict)


def test_property_key_is_the_documented_one(make_client, drafts_dir):
    fake, _ = _publish_twelve(make_client, drafts_dir)
    assert any(f"/properties/{PROPERTY_KEY}" in url for _m, url in fake.calls)


def test_small_set_publishes_without_warnings(make_client, drafts_dir):
    write_approved(drafts_dir, count=4)
    fake = FakeJira()
    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert report.warnings == []
    assert len(fake.created) == 4
