"""T075: issues this tool did not create are never touched (FR-026c, SC-017).

The rule is strict on purpose: matching by wording or summary would eventually
claim somebody else's bug report.
"""

from jira_testgen.publish import publish_draft

from .draft_factory import STORY_KEY, write_approved
from .fake_jira import FakeJira


def _with_foreign_issues(make_client, drafts_dir):
    write_approved(drafts_dir, count=4)
    fake = FakeJira(linked=["PROJ-900", "PROJ-901"])
    # Two linked issues with no marker: a bug and a hand-written test whose
    # summary deliberately resembles a generated one.
    fake.issues["PROJ-900"] = {"fields": {"summary": "Reset link bug", "description": None}}
    fake.issues["PROJ-901"] = {"fields": {"summary": "Test case 1", "description": None}}
    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    return fake, report


def test_foreign_issues_are_not_modified(make_client, drafts_dir):
    fake, _report = _with_foreign_issues(make_client, drafts_dir)
    assert "PROJ-900" not in fake.updated
    assert "PROJ-901" not in fake.updated


def test_foreign_issues_are_not_matched_to_any_test_case(make_client, drafts_dir):
    _fake, report = _with_foreign_issues(make_client, drafts_dir)
    claimed = {o.issue_key for o in report.outcomes}
    assert "PROJ-900" not in claimed
    assert "PROJ-901" not in claimed


def test_a_similar_summary_does_not_cause_a_match(make_client, drafts_dir):
    # PROJ-901's summary is "Test case 1", which is exactly what the draft
    # factory names its first test case. Matching must be by identity only.
    _fake, report = _with_foreign_issues(make_client, drafts_dir)
    assert all(o.decision == "created" for o in report.outcomes)


def test_foreign_issues_are_not_counted_as_published(make_client, drafts_dir):
    _fake, report = _with_foreign_issues(make_client, drafts_dir)
    assert len(report.outcomes) == 4


def test_four_new_issues_are_still_created_alongside_them(make_client, drafts_dir):
    fake, _report = _with_foreign_issues(make_client, drafts_dir)
    assert len(fake.created) == 4


def test_an_issue_carrying_another_storys_marker_is_left_alone(make_client, drafts_dir):
    # Same tool, different story: still not ours to touch in this run.
    write_approved(drafts_dir, count=4)
    fake = FakeJira(
        linked=["PROJ-950"],
        properties={
            "PROJ-950": {
                "identity": "OTHER-9-TC-001",
                "content_fingerprint": "aaa",
                "source_issue": "OTHER-9",
            }
        },
    )
    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert "PROJ-950" not in {o.issue_key for o in report.outcomes}
    assert "PROJ-950" not in fake.updated


def test_an_issue_with_a_malformed_marker_is_left_alone(make_client, drafts_dir):
    # Something wrote our property key with the wrong shape. Claiming the issue
    # on that basis would be worse than ignoring it.
    write_approved(drafts_dir, count=4)
    fake = FakeJira(
        linked=["PROJ-960"],
        properties={"PROJ-960": {"identity": "PROJ-123-TC-001"}},  # no fingerprint
    )
    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert "PROJ-960" not in fake.updated
    assert all(o.decision == "created" for o in report.outcomes)
