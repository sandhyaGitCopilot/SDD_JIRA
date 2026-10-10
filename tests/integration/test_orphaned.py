"""T079: a published test case removed from the draft is reported, not deleted.

The tool never deletes a Jira issue. But silently ignoring one that is no longer
in the draft would leave it unaccounted for, which is the thing FR-023's spirit
forbids -- so it is reported as orphaned and left in place.
"""

from jira_testgen.draft.schema import ApprovalState, load_draft
from jira_testgen.publish import publish_draft

from .draft_factory import STORY_KEY, many_cases, write_approved, write_draft
from .fake_jira import FakeJira


def _publish_then_drop_one(make_client, drafts_dir):
    # Six cases, and the one dropped is a `boundary`. Dropping a positive would
    # leave its criterion uncovered, and dropping the only negative or edge case
    # would breach the set-level floor -- validation would refuse the draft
    # before publishing ever got a chance to report an orphan.
    path = write_approved(drafts_dir, cases=many_cases(6))
    fake = FakeJira()
    first = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    dropped = next(
        o for o in first.outcomes if o.identity.endswith("-005")
    )  # TC-005 is the boundary case

    draft = load_draft(path)
    draft.test_cases = [c for c in draft.test_cases if c.identity != dropped.identity]
    draft.approval = ApprovalState(status="approved", approved_fingerprint=None)
    write_draft(drafts_dir, draft)

    second = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    return fake, dropped, second


def test_the_dropped_test_case_is_reported_as_orphaned(make_client, drafts_dir):
    _fake, dropped, second = _publish_then_drop_one(make_client, drafts_dir)
    orphaned = [o for o in second.outcomes if o.decision == "orphaned_draft"]
    assert [o.identity for o in orphaned] == [dropped.identity]
    assert orphaned[0].issue_key == dropped.issue_key


def test_the_orphaned_issue_is_left_in_place(make_client, drafts_dir):
    fake, dropped, _second = _publish_then_drop_one(make_client, drafts_dir)
    assert dropped.issue_key in fake.created
    assert dropped.issue_key not in fake.deleted
    assert dropped.issue_key not in fake.updated


def test_the_reason_explains_what_to_do(make_client, drafts_dir):
    _fake, _dropped, second = _publish_then_drop_one(make_client, drafts_dir)
    orphaned = next(o for o in second.outcomes if o.decision == "orphaned_draft")
    assert orphaned.reason
    assert "draft" in orphaned.reason.lower()


def test_the_remaining_test_cases_are_unchanged(make_client, drafts_dir):
    _fake, dropped, second = _publish_then_drop_one(make_client, drafts_dir)
    others = [
        o
        for o in second.outcomes
        if o.identity != dropped.identity and o.decision != "orphaned_draft"
    ]
    assert len(others) == 5
    assert all(o.decision == "unchanged" for o in others)


def test_an_orphan_does_not_by_itself_fail_the_run(make_client, drafts_dir):
    # It is information, not a failure: the engineer deliberately deleted the
    # test case, and the issue is theirs to remove or keep.
    _fake, _dropped, second = _publish_then_drop_one(make_client, drafts_dir)
    assert second.verdict == "success"
    assert second.exit_code == 0


def test_the_report_still_accounts_for_every_identity(make_client, drafts_dir):
    _fake, _dropped, second = _publish_then_drop_one(make_client, drafts_dir)
    # Five still drafted, plus one orphan.
    assert len(second.outcomes) == 6
    identities = [o.identity for o in second.outcomes]
    assert len(set(identities)) == 6
