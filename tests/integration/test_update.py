"""T073: editing a published test case updates it in place (FR-038, scenario E).

This is the behaviour the previous phase deliberately refused to perform until
conflict detection existed, so these tests are also the proof that it now does.
"""

from jira_testgen.draft.schema import ApprovalState, load_draft
from jira_testgen.publish import publish_draft

from .draft_factory import STORY_KEY, write_approved, write_draft
from .fake_jira import FakeJira


def _publish_then_edit(make_client, drafts_dir, *, index=0, new_step="A newly added step."):
    path = write_approved(drafts_dir, count=4)
    fake = FakeJira()
    first = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)

    draft = load_draft(path)
    draft.test_cases[index].steps.append(new_step)
    # Re-approve, as an engineer would after editing.
    draft.approval = ApprovalState(status="approved", approved_fingerprint=None)
    write_draft(drafts_dir, draft)

    second = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    return fake, first, second


def test_the_edited_test_case_is_updated(make_client, drafts_dir):
    fake, first, second = _publish_then_edit(make_client, drafts_dir)
    edited = first.outcomes[0]
    outcome = next(o for o in second.outcomes if o.identity == edited.identity)
    assert outcome.decision == "updated"
    assert outcome.issue_key == edited.issue_key


def test_no_second_issue_is_created(make_client, drafts_dir):
    fake, first, _second = _publish_then_edit(make_client, drafts_dir)
    assert len(fake.created) == 4


def test_the_report_names_the_updated_issue(make_client, drafts_dir):
    _fake, first, second = _publish_then_edit(make_client, drafts_dir)
    updated = [o for o in second.outcomes if o.decision == "updated"]
    assert [o.issue_key for o in updated] == [first.outcomes[0].issue_key]


def test_the_others_are_left_untouched(make_client, drafts_dir):
    fake, first, second = _publish_then_edit(make_client, drafts_dir)
    edited = first.outcomes[0].identity
    others = [o for o in second.outcomes if o.identity != edited]
    assert all(o.decision == "unchanged" for o in others)
    assert fake.updated == [first.outcomes[0].issue_key]


def test_the_new_content_reaches_jira(make_client, drafts_dir):
    from jira_testgen.jira.adf import extract_text

    fake, first, _second = _publish_then_edit(
        make_client, drafts_dir, new_step="Verify the audit log entry."
    )
    fields = fake.issues[first.outcomes[0].issue_key]["fields"]
    assert "Verify the audit log entry." in extract_text(fields["description"]).text


def test_the_fingerprint_is_refreshed_after_an_update(make_client, drafts_dir):
    # FR-040: the stored fingerprint must always reflect what the tool last
    # wrote, or the next run would see a phantom conflict.
    fake, first, _second = _publish_then_edit(make_client, drafts_dir)
    key = first.outcomes[0].issue_key
    before = _fingerprint_at_create(first, key)
    assert fake.properties[key]["content_fingerprint"] != before

    third = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert all(o.decision == "unchanged" for o in third.outcomes)


def _fingerprint_at_create(report, key):
    # The first run's fingerprint, recovered from the outcome ordering.
    return getattr(next(o for o in report.outcomes if o.issue_key == key), "_fp", None)


def test_updating_a_summary_also_works(make_client, drafts_dir):
    path = write_approved(drafts_dir, count=4)
    fake = FakeJira()
    first = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)

    draft = load_draft(path)
    draft.test_cases[1].summary = "A thoroughly rewritten summary"
    draft.approval = ApprovalState(status="approved", approved_fingerprint=None)
    write_draft(drafts_dir, draft)

    second = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    outcome = next(o for o in second.outcomes if o.identity == first.outcomes[1].identity)
    assert outcome.decision == "updated"
    fields = fake.issues[outcome.issue_key]["fields"]
    assert fields["summary"] == "A thoroughly rewritten summary"


def test_an_update_run_is_a_clean_success(make_client, drafts_dir):
    _fake, _first, second = _publish_then_edit(make_client, drafts_dir)
    assert second.verdict == "success"
    assert second.exit_code == 0


def test_cosmetic_draft_changes_do_not_trigger_an_update(make_client, drafts_dir):
    # Whitespace is not content; re-indenting a draft must not rewrite Jira.
    path = write_approved(drafts_dir, count=4)
    fake = FakeJira()
    publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)

    draft = load_draft(path)
    draft.test_cases[0].expected_results = (
        "  " + draft.test_cases[0].expected_results.replace(" ", "  ") + "\n"
    )
    write_draft(drafts_dir, draft)

    second = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert all(o.decision == "unchanged" for o in second.outcomes)
    assert fake.updated == []
