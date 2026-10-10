"""T046: partial failure (FR-020, FR-021, FR-022).

A permanent failure on one test case must not take the run with it, and the
verdict must say "partial" rather than claiming success.
"""

from jira_testgen.publish import publish_draft

from .draft_factory import STORY_KEY, many_cases, write_approved
from .fake_jira import FakeJira


def _publish_with_fifth_failing(make_client, drafts_dir):
    write_approved(drafts_dir, cases=many_cases(12))
    fake = FakeJira(fail_create_on={5})
    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    return fake, report


def test_the_other_eleven_are_created(make_client, drafts_dir):
    fake, _ = _publish_with_fifth_failing(make_client, drafts_dir)
    assert len(fake.created) == 11


def test_the_run_does_not_abort_at_the_failure(make_client, drafts_dir):
    # FR-020: the loop continues past a permanent per-test-case failure.
    _, report = _publish_with_fifth_failing(make_client, drafts_dir)
    assert len(report.outcomes) == 12
    assert sum(1 for o in report.outcomes if o.decision == "created") == 11


def test_the_failure_is_reported_with_a_reason(make_client, drafts_dir):
    _, report = _publish_with_fifth_failing(make_client, drafts_dir)
    failed = [o for o in report.outcomes if o.decision == "failed"]
    assert len(failed) == 1
    assert failed[0].reason
    assert failed[0].issue_key is None


def test_verdict_is_partial_not_success(make_client, drafts_dir):
    # FR-022: a partially complete run must not look like a successful one.
    _, report = _publish_with_fifth_failing(make_client, drafts_dir)
    assert report.verdict == "partial"
    assert report.exit_code == 10


def test_a_permanent_failure_is_not_retried(make_client, drafts_dir):
    # Retrying a rejected issue type only wastes time.
    fake, _ = _publish_with_fifth_failing(make_client, drafts_dir)
    creates = [1 for m, u in fake.calls if m == "POST" and u.endswith("/issue")]
    assert len(creates) == 12  # 11 successes + 1 single failed attempt


def test_every_test_case_appears_exactly_once(make_client, drafts_dir):
    # FR-021: the report is complete by construction.
    _, report = _publish_with_fifth_failing(make_client, drafts_dir)
    identities = [o.identity for o in report.outcomes]
    assert len(identities) == len(set(identities)) == 12


def test_an_unusable_issue_type_fails_before_anything_is_created(make_client, drafts_dir):
    # FR-024: target pre-flight runs before the loop.
    import pytest

    from jira_testgen.errors import UserError

    write_approved(drafts_dir, count=4)
    fake = FakeJira(issue_types=["Bug"])  # the configured "Task" is absent
    with pytest.raises(UserError) as excinfo:
        publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert "JIRA_TEST_ISSUE_TYPE" in str(excinfo.value)
    assert fake.created == []


def test_a_missing_link_type_fails_before_anything_is_created(make_client, drafts_dir):
    import pytest

    from jira_testgen.errors import UserError

    write_approved(drafts_dir, count=4)
    fake = FakeJira(link_types=["Blocks"])  # the configured "Relates" is absent
    with pytest.raises(UserError) as excinfo:
        publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert "JIRA_LINK_TYPE" in str(excinfo.value)
    assert fake.created == []
