"""T049: set-size warning and ceiling (FR-064, FR-065, FR-068, scenario N)."""

import pytest

from jira_testgen.errors import SetTooLargeError
from jira_testgen.publish import publish_draft

from .draft_factory import STORY_KEY, many_cases, write_approved
from .fake_jira import FakeJira


def test_twenty_eight_warns_and_still_publishes(make_client, drafts_dir):
    write_approved(drafts_dir, cases=many_cases(28))
    fake = FakeJira()
    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert len(fake.created) == 28
    assert any("28" in w for w in report.warnings)


def test_a_set_at_the_warning_threshold_does_not_warn(make_client, drafts_dir):
    write_approved(drafts_dir, cases=many_cases(25))
    report = publish_draft(make_client(FakeJira()), STORY_KEY, drafts_dir=drafts_dir)
    assert not any("review may be slow" in w for w in report.warnings)


def test_a_hundred_is_allowed(make_client, drafts_dir):
    # The ceiling is exclusive: 100 publishes, 101 does not.
    write_approved(drafts_dir, cases=many_cases(100))
    fake = FakeJira()
    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert len(fake.created) == 100
    assert report.verdict == "success"


def test_over_a_hundred_is_refused(make_client, drafts_dir):
    write_approved(drafts_dir, cases=many_cases(120))
    fake = FakeJira()
    with pytest.raises(SetTooLargeError) as excinfo:
        publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    message = str(excinfo.value)
    assert "120" in message
    assert "100" in message
    assert "--allow-large" in message
    assert fake.created == []


def test_the_override_publishes_the_large_set(make_client, drafts_dir):
    write_approved(drafts_dir, cases=many_cases(120))
    fake = FakeJira()
    report = publish_draft(
        make_client(fake), STORY_KEY, drafts_dir=drafts_dir, allow_large=True
    )
    assert len(fake.created) == 120
    assert report.overrides_used.get("set_size") == 120


def test_the_size_override_makes_the_run_partial(make_client, drafts_dir):
    # FR-068: an oversized publish is recorded, not quietly normal.
    write_approved(drafts_dir, cases=many_cases(120))
    report = publish_draft(
        make_client(FakeJira()), STORY_KEY, drafts_dir=drafts_dir, allow_large=True
    )
    assert report.verdict == "partial"


def test_the_ceiling_is_checked_before_any_issue_is_created(make_client, drafts_dir):
    write_approved(drafts_dir, cases=many_cases(120))
    fake = FakeJira()
    with pytest.raises(SetTooLargeError):
        publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert fake.writes == []
