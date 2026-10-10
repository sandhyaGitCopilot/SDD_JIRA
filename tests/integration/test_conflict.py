"""T074: an issue edited in Jira is a conflict, never an overwrite.

FR-039 and SC-013: zero published issues that someone edited in Jira may be
overwritten by a later run. These tests assert the content on *both* sides is
unchanged, not merely that something was reported.
"""

from jira_testgen.draft.schema import ApprovalState, load_draft
from jira_testgen.jira.adf import extract_text
from jira_testgen.publish import publish_draft

from .draft_factory import STORY_KEY, many_cases, write_approved, write_draft
from .fake_jira import FakeJira

JIRA_SIDE_EDIT = "Someone rewrote this by hand in Jira."


def _publish_then_edit_in_jira(make_client, drafts_dir, *, also_edit_draft=False):
    path = write_approved(drafts_dir, count=4)
    fake = FakeJira()
    first = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)

    target = first.outcomes[0]
    fake.edit_in_jira(target.issue_key, description_text=JIRA_SIDE_EDIT)

    if also_edit_draft:
        draft = load_draft(path)
        draft.test_cases[0].steps.append("A step added in the draft too.")
        draft.approval = ApprovalState(status="approved", approved_fingerprint=None)
        write_draft(drafts_dir, draft)

    second = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    return fake, target, second


def test_an_issue_edited_in_jira_is_reported_as_a_conflict(make_client, drafts_dir):
    _fake, target, second = _publish_then_edit_in_jira(make_client, drafts_dir)
    outcome = next(o for o in second.outcomes if o.identity == target.identity)
    assert outcome.decision == "conflict"
    assert outcome.issue_key == target.issue_key


def test_the_conflict_names_the_differing_fields(make_client, drafts_dir):
    _fake, target, second = _publish_then_edit_in_jira(make_client, drafts_dir)
    outcome = next(o for o in second.outcomes if o.identity == target.identity)
    assert "description" in outcome.fields_differing


def test_the_conflict_explains_itself(make_client, drafts_dir):
    _fake, target, second = _publish_then_edit_in_jira(make_client, drafts_dir)
    outcome = next(o for o in second.outcomes if o.identity == target.identity)
    assert "edited" in (outcome.reason or "").lower()


def test_the_jira_side_content_is_not_overwritten(make_client, drafts_dir):
    fake, target, _second = _publish_then_edit_in_jira(make_client, drafts_dir)
    fields = fake.issues[target.issue_key]["fields"]
    assert JIRA_SIDE_EDIT in extract_text(fields["description"]).text
    assert target.issue_key not in fake.updated


def test_both_sides_are_unchanged_when_both_moved(make_client, drafts_dir):
    fake, target, second = _publish_then_edit_in_jira(
        make_client, drafts_dir, also_edit_draft=True
    )
    outcome = next(o for o in second.outcomes if o.identity == target.identity)
    assert outcome.decision == "conflict"
    fields = fake.issues[target.issue_key]["fields"]
    assert JIRA_SIDE_EDIT in extract_text(fields["description"]).text
    assert fake.updated == []


def test_a_conflict_makes_the_run_partial(make_client, drafts_dir):
    _fake, _target, second = _publish_then_edit_in_jira(make_client, drafts_dir)
    assert second.verdict == "partial"
    assert second.exit_code == 10


def test_the_other_test_cases_still_publish_normally(make_client, drafts_dir):
    _fake, target, second = _publish_then_edit_in_jira(make_client, drafts_dir)
    others = [o for o in second.outcomes if o.identity != target.identity]
    assert all(o.decision == "unchanged" for o in others)


def test_resolving_in_jira_clears_the_conflict(make_client, drafts_dir):
    # FR-041: the verdict is re-derived from scratch each run, so putting the
    # issue back as the tool had it makes the conflict disappear.
    write_approved(drafts_dir, count=4)
    fake = FakeJira()
    first = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    target = first.outcomes[0]

    original = fake.issues[target.issue_key]["fields"]["description"]
    fake.edit_in_jira(target.issue_key, description_text=JIRA_SIDE_EDIT)
    second = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert any(o.decision == "conflict" for o in second.outcomes)

    # Restore it exactly.
    fake.issues[target.issue_key]["fields"]["description"] = original
    third = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert all(o.decision == "unchanged" for o in third.outcomes)
    assert third.verdict == "success"


def test_resolving_by_regenerating_the_draft_also_clears_it(make_client, drafts_dir):
    # The other way out: drop the test case, accepting whatever is in Jira.
    # Six cases so that dropping a `boundary` one leaves a still-valid draft.
    path = write_approved(drafts_dir, cases=many_cases(6))
    fake = FakeJira()
    first = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    target = next(o for o in first.outcomes if o.identity.endswith("-005"))
    fake.edit_in_jira(target.issue_key, description_text=JIRA_SIDE_EDIT)

    second = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    conflict = next(o for o in second.outcomes if o.identity == target.identity)
    assert conflict.decision == "conflict"

    # Dropping the test case from the draft leaves the issue alone, reported as
    # no longer drafted rather than silently ignored.
    draft = load_draft(path)
    draft.test_cases = [c for c in draft.test_cases if c.identity != target.identity]
    draft.approval = ApprovalState(status="approved", approved_fingerprint=None)
    write_draft(drafts_dir, draft)

    third = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert not any(o.decision == "conflict" for o in third.outcomes)
    assert any(o.decision == "orphaned_draft" for o in third.outcomes)


def test_a_summary_edited_in_jira_is_also_detected(make_client, drafts_dir):
    write_approved(drafts_dir, count=4)
    fake = FakeJira()
    first = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    target = first.outcomes[2]
    fake.edit_in_jira(target.issue_key, summary="Renamed by hand")

    second = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    outcome = next(o for o in second.outcomes if o.identity == target.identity)
    assert outcome.decision == "conflict"
    assert "summary" in outcome.fields_differing
