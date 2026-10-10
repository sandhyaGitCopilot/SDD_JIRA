"""T071: resuming after a partial run (FR-027, FR-054, quickstart scenario J).

The promise is that an interrupted run, resumed, reaches the same final state as
an uninterrupted one (SC-011). That is asserted directly here by comparing
against a clean run.
"""

from jira_testgen.publish import publish_draft

from .draft_factory import STORY_KEY, many_cases, write_approved
from .fake_jira import FakeJira


def test_a_run_stopped_by_throttling_reports_what_was_published(make_client, drafts_dir):
    write_approved(drafts_dir, cases=many_cases(12))
    # Throttle the 8th create past the retry bound, so the run stops there.
    fake = FakeJira(throttle_create_on=lambda n: n >= 8)
    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)

    created = [o for o in report.outcomes if o.decision == "created"]
    assert len(created) == 7
    assert report.not_attempted, "the rest must be reported as unattempted"
    assert report.verdict == "partial"
    assert report.exit_code == 11


def test_every_test_case_still_appears_in_the_report(make_client, drafts_dir):
    # FR-021: nothing may go unaccounted for, even when the run stopped early.
    write_approved(drafts_dir, cases=many_cases(12))
    fake = FakeJira(throttle_create_on=lambda n: n >= 8)
    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert len(report.outcomes) == 12
    identities = [o.identity for o in report.outcomes]
    assert len(set(identities)) == 12


def test_resuming_creates_only_the_missing_ones(make_client, drafts_dir):
    write_approved(drafts_dir, cases=many_cases(12))
    fake = FakeJira(throttle_create_on=lambda n: n >= 8)
    first = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    created_first = len([o for o in first.outcomes if o.decision == "created"])

    fake.throttle_create_on = None
    second = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)

    created_second = len([o for o in second.outcomes if o.decision == "created"])
    unchanged = len([o for o in second.outcomes if o.decision == "unchanged"])
    assert created_first + created_second == 12
    assert unchanged == created_first


def test_the_story_ends_with_exactly_twelve_linked_issues(make_client, drafts_dir):
    write_approved(drafts_dir, cases=many_cases(12))
    fake = FakeJira(throttle_create_on=lambda n: n >= 8)
    publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    fake.throttle_create_on = None
    publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)

    assert len(fake.created) == 12
    assert len(fake.links) == 12


def test_resumed_state_matches_an_uninterrupted_run(make_client, drafts_dir, tmp_path):
    # SC-011 stated as an equality rather than a vibe.
    write_approved(drafts_dir, cases=many_cases(12))
    interrupted = FakeJira(throttle_create_on=lambda n: n >= 8)
    publish_draft(make_client(interrupted), STORY_KEY, drafts_dir=drafts_dir)
    interrupted.throttle_create_on = None
    publish_draft(make_client(interrupted), STORY_KEY, drafts_dir=drafts_dir)

    clean_dir = tmp_path / "clean"
    clean_dir.mkdir()
    write_approved(clean_dir, cases=many_cases(12))
    clean = FakeJira()
    publish_draft(make_client(clean), STORY_KEY, drafts_dir=clean_dir)

    assert len(interrupted.created) == len(clean.created)
    assert len(interrupted.links) == len(clean.links)
    assert sorted(
        p["identity"] for p in interrupted.properties.values()
    ) == sorted(p["identity"] for p in clean.properties.values())
