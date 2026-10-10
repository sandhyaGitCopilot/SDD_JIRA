"""T047: created-but-unlinked, and relinking on a re-run (FR-023, FR-027).

An issue created whose link failed is the one way this tool can leave something
in Jira that nobody asked for. It must be named in the report, and a re-run must
finish the job without creating a second issue.
"""

from jira_testgen.publish import publish_draft

from .draft_factory import STORY_KEY, write_approved
from .fake_jira import FakeJira


def test_a_failed_link_is_reported_as_created_but_unlinked(make_client, drafts_dir):
    write_approved(drafts_dir, count=4)
    fake = FakeJira(fail_link_on={2})
    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)

    unlinked = [o for o in report.outcomes if o.decision == "created_unlinked"]
    assert len(unlinked) == 1
    assert unlinked[0].issue_key is not None
    assert unlinked[0].reason


def test_an_unlinked_issue_makes_the_run_partial(make_client, drafts_dir):
    # Nothing created may go unaccounted for, so this cannot be a clean success.
    write_approved(drafts_dir, count=4)
    fake = FakeJira(fail_link_on={2})
    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert report.verdict == "partial"


def test_the_issue_still_exists_and_keeps_its_marker(make_client, drafts_dir):
    # It must stay discoverable, or the re-run could not find it.
    write_approved(drafts_dir, count=4)
    fake = FakeJira(fail_link_on={2})
    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    unlinked = next(o for o in report.outcomes if o.decision == "created_unlinked")
    assert unlinked.issue_key in fake.properties


def test_a_rerun_completes_the_missing_link(make_client, drafts_dir):
    write_approved(drafts_dir, count=4)
    fake = FakeJira(fail_link_on={2})
    first = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    unlinked = next(o for o in first.outcomes if o.decision == "created_unlinked")

    created_before = list(fake.created)
    fake.fail_link_on = None
    second = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)

    relinked = [o for o in second.outcomes if o.decision == "relinked"]
    assert [o.issue_key for o in relinked] == [unlinked.issue_key]
    # And no second issue was created for it.
    assert fake.created == created_before


def test_a_rerun_after_full_success_creates_nothing(make_client, drafts_dir):
    write_approved(drafts_dir, count=4)
    fake = FakeJira()
    publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    created_before = list(fake.created)

    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert fake.created == created_before
    assert all(o.decision == "unchanged" for o in report.outcomes)
    assert report.verdict == "success"


def test_a_failed_marker_write_is_reported_rather_than_silently_dropped(make_client, drafts_dir):
    # Without its marker an issue is invisible to later runs, which would mean a
    # duplicate next time. It must be surfaced.
    write_approved(drafts_dir, count=4)
    fake = FakeJira(fail_property_on={1})
    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    flagged = [o for o in report.outcomes if o.decision == "created_unmarked"]
    assert len(flagged) == 1
    assert report.verdict == "partial"
