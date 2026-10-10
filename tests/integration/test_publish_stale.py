"""T048: the stale-criteria gate (FR-056 - FR-060, quickstart scenario H).

The traceability claim is the feature's central promise, so a story whose
criteria moved on must not be published against silently. A criterion that was
merely reformatted must not block anyone.
"""

import pytest

from jira_testgen.errors import CriteriaChangedError
from jira_testgen.publish import publish_draft

from .draft_factory import DEFAULT_CRITERIA, STORY_KEY, write_approved
from .fake_jira import FakeJira


def test_a_reworded_criterion_refuses_the_publish(make_client, drafts_dir):
    write_approved(drafts_dir, count=4)
    fake = FakeJira(
        criteria=[DEFAULT_CRITERIA[0], "Reset link expires after 48 hours."]
    )
    with pytest.raises(CriteriaChangedError):
        publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)


def test_the_refusal_names_the_changed_criterion(make_client, drafts_dir):
    write_approved(drafts_dir, count=4)
    fake = FakeJira(criteria=[DEFAULT_CRITERIA[0], "Reset link expires after 48 hours."])
    with pytest.raises(CriteriaChangedError) as excinfo:
        publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    message = str(excinfo.value)
    assert "AC-2" in message
    assert "48 hours" in message
    assert "regenerate" in message.lower()


def test_nothing_is_created_when_criteria_changed(make_client, drafts_dir):
    write_approved(drafts_dir, count=4)
    fake = FakeJira(criteria=[DEFAULT_CRITERIA[0], "Reset link expires after 48 hours."])
    with pytest.raises(CriteriaChangedError):
        publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert fake.created == []
    assert fake.writes == []


def test_an_added_criterion_also_blocks(make_client, drafts_dir):
    write_approved(drafts_dir, count=4)
    fake = FakeJira(criteria=[*DEFAULT_CRITERIA, "A brand new criterion."])
    with pytest.raises(CriteriaChangedError):
        publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)


def test_a_removed_criterion_also_blocks(make_client, drafts_dir):
    write_approved(drafts_dir, count=4)
    fake = FakeJira(criteria=[DEFAULT_CRITERIA[0]])
    with pytest.raises(CriteriaChangedError):
        publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)


def test_reformatting_only_does_not_block(make_client, drafts_dir):
    # FR-057. Jira's editor rewrites markup on unrelated edits; if this blocked
    # a publish, the gate would be unusable.
    write_approved(drafts_dir, count=4)
    fake = FakeJira(
        criteria=[
            "**User can request a reset link with a registered email address.**",
            "Reset   link  expires after 24 hours.",
        ]
    )
    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert report.verdict == "success"


def test_the_override_lets_it_through(make_client, drafts_dir):
    write_approved(drafts_dir, count=4)
    fake = FakeJira(criteria=[DEFAULT_CRITERIA[0], "Reset link expires after 48 hours."])
    report = publish_draft(
        make_client(fake), STORY_KEY, drafts_dir=drafts_dir, allow_stale_criteria=True
    )
    assert len(fake.created) == 4
    assert all(o.decision == "created" for o in report.outcomes)


def test_the_override_is_recorded_with_the_changed_criteria(make_client, drafts_dir):
    # FR-060: a knowingly stale suite is never published silently.
    write_approved(drafts_dir, count=4)
    fake = FakeJira(criteria=[DEFAULT_CRITERIA[0], "Reset link expires after 48 hours."])
    report = publish_draft(
        make_client(fake), STORY_KEY, drafts_dir=drafts_dir, allow_stale_criteria=True
    )
    recorded = report.overrides_used.get("stale_criteria")
    assert recorded
    assert any("AC-2" in entry for entry in recorded)


def test_the_override_makes_the_run_partial_not_a_clean_success(make_client, drafts_dir):
    write_approved(drafts_dir, count=4)
    fake = FakeJira(criteria=[DEFAULT_CRITERIA[0], "Reset link expires after 48 hours."])
    report = publish_draft(
        make_client(fake), STORY_KEY, drafts_dir=drafts_dir, allow_stale_criteria=True
    )
    assert report.verdict == "partial"
