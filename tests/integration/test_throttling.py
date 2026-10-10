"""T077: throttling is ridden out, not surfaced (FR-051, FR-055, SC-021)."""

from jira_testgen.publish import publish_draft

from .draft_factory import STORY_KEY, many_cases, write_approved
from .fake_jira import FakeJira


def test_a_throttled_create_is_retried_and_succeeds(make_client, drafts_dir):
    write_approved(drafts_dir, cases=many_cases(4))
    # The first create attempt is throttled; the retry succeeds.
    fake = FakeJira(throttle_create_on={1})
    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert len(fake.created) == 4
    assert all(o.decision == "created" for o in report.outcomes)


def test_the_run_completes_without_engineer_intervention(make_client, drafts_dir):
    write_approved(drafts_dir, cases=many_cases(6))
    # Every other create attempt is throttled once.
    fake = FakeJira(throttle_create_on={1, 3, 5})
    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert report.verdict == "success"
    assert report.exit_code == 0


def test_retried_test_cases_are_named_in_the_report(make_client, drafts_dir):
    # FR-055: a slow run must be explainable afterwards.
    write_approved(drafts_dir, cases=many_cases(4))
    fake = FakeJira(throttle_create_on={1})
    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    retried = [o for o in report.outcomes if o.retried]
    assert retried, "the throttled test case should be recorded as retried"
    assert retried[0].retried >= 1


def test_persistent_throttling_stops_the_run_resumably(make_client, drafts_dir):
    write_approved(drafts_dir, cases=many_cases(6))
    fake = FakeJira(throttle_create_on=lambda n: True)
    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert report.exit_code == 11
    assert report.not_attempted
    assert fake.created == []


def test_the_retry_after_header_is_honoured(make_client, drafts_dir):
    # The fake returns Retry-After: 1, so the recorded waits must be exactly
    # that rather than the client's own backoff curve.
    write_approved(drafts_dir, cases=many_cases(4))
    waits: list[float] = []
    fake = FakeJira(throttle_create_on={1})

    from jira_testgen.config import Config, SecretValue
    from jira_testgen.jira.client import JiraClient

    config = Config(
        base_url="https://example.atlassian.net",
        email="qa@example.com",
        api_token=SecretValue("token-value-long-enough"),
        project_key="PROJ",
    )
    client = JiraClient(config, session=fake, sleep=waits.append)
    publish_draft(client, STORY_KEY, drafts_dir=drafts_dir)
    assert waits == [1.0]


def test_a_permanent_failure_is_still_not_retried_during_throttling(make_client, drafts_dir):
    write_approved(drafts_dir, cases=many_cases(4))
    fake = FakeJira(fail_create_on={2})
    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    failed = [o for o in report.outcomes if o.decision == "failed"]
    assert len(failed) == 1
    assert failed[0].retried == 0
