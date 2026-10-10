"""T070: idempotent republish (FR-026, FR-029, quickstart scenario D)."""

from jira_testgen.publish import publish_draft

from .draft_factory import STORY_KEY, many_cases, write_approved
from .fake_jira import FakeJira


def _publish_twice(make_client, drafts_dir, count=12):
    write_approved(drafts_dir, cases=many_cases(count))
    fake = FakeJira()
    first = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    second = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    return fake, first, second


def test_the_second_run_creates_nothing(make_client, drafts_dir):
    fake, first, _second = _publish_twice(make_client, drafts_dir)
    assert len(fake.created) == 12
    assert all(o.decision == "created" for o in first.outcomes)


def test_every_test_case_is_reported_as_already_existing(make_client, drafts_dir):
    _fake, _first, second = _publish_twice(make_client, drafts_dir)
    assert len(second.outcomes) == 12
    assert all(o.decision == "unchanged" for o in second.outcomes)


def test_the_existing_keys_are_reported(make_client, drafts_dir):
    _fake, first, second = _publish_twice(make_client, drafts_dir)
    before = {o.identity: o.issue_key for o in first.outcomes}
    after = {o.identity: o.issue_key for o in second.outcomes}
    assert before == after


def test_no_issue_is_modified_on_the_second_run(make_client, drafts_dir):
    fake, _first, _second = _publish_twice(make_client, drafts_dir)
    assert fake.updated == []


def test_a_third_run_is_also_a_no_op(make_client, drafts_dir):
    fake, _first, _second = _publish_twice(make_client, drafts_dir)
    created = list(fake.created)
    third = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert fake.created == created
    assert all(o.decision == "unchanged" for o in third.outcomes)
    assert third.verdict == "success"


def test_republish_verdict_is_success(make_client, drafts_dir):
    _fake, _first, second = _publish_twice(make_client, drafts_dir)
    assert second.verdict == "success"
    assert second.exit_code == 0
