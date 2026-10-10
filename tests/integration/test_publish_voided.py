"""T044: approval voided by a later edit (FR-043, FR-044, FR-046, scenario C).

Two behaviours together: publishing is refused, and the file is reset to
unapproved so the stale marker cannot sit there looking approved.
"""

import pytest

from jira_testgen.draft.schema import load_draft
from jira_testgen.errors import DraftRefusedError
from jira_testgen.publish import publish_draft

from .draft_factory import STORY_KEY, build_draft, write_approved, write_draft
from .fake_jira import FakeJira


def _edit_after_approval(drafts_dir):
    path = write_approved(drafts_dir, count=4)
    draft = load_draft(path)
    draft.test_cases[0].steps.append("An extra step added after approving.")
    # Keep the now-stale fingerprint: that is the situation being tested.
    write_draft(drafts_dir, draft)
    return path


def test_editing_after_approval_refuses_the_publish(make_client, drafts_dir):
    _edit_after_approval(drafts_dir)
    with pytest.raises(DraftRefusedError):
        publish_draft(make_client(FakeJira()), STORY_KEY, drafts_dir=drafts_dir)


def test_refusal_says_the_draft_changed_after_approval(make_client, drafts_dir):
    _edit_after_approval(drafts_dir)
    with pytest.raises(DraftRefusedError) as excinfo:
        publish_draft(make_client(FakeJira()), STORY_KEY, drafts_dir=drafts_dir)
    assert "changed" in str(excinfo.value).lower()


def test_nothing_is_written_to_jira(make_client, drafts_dir):
    _edit_after_approval(drafts_dir)
    fake = FakeJira()
    with pytest.raises(DraftRefusedError):
        publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert fake.writes == []


def test_the_file_is_reset_to_unapproved(make_client, drafts_dir):
    # FR-046: re-approving must be a deliberate act, not a stale marker left in
    # place.
    path = _edit_after_approval(drafts_dir)
    with pytest.raises(DraftRefusedError):
        publish_draft(make_client(FakeJira()), STORY_KEY, drafts_dir=drafts_dir)
    assert load_draft(path).approval.status == "draft"


def test_reapproving_then_publishing_succeeds(make_client, drafts_dir):
    from jira_testgen.draft.schema import ApprovalState

    path = _edit_after_approval(drafts_dir)
    with pytest.raises(DraftRefusedError):
        publish_draft(make_client(FakeJira()), STORY_KEY, drafts_dir=drafts_dir)

    draft = load_draft(path)
    draft.approval = ApprovalState(status="approved", approved_fingerprint=None)
    write_draft(drafts_dir, draft)

    report = publish_draft(make_client(FakeJira()), STORY_KEY, drafts_dir=drafts_dir)
    assert report.verdict == "success"


def test_approving_with_no_recorded_baseline_records_it_and_proceeds(make_client, drafts_dir):
    # The engineer only ever types one word; the tool fills in the baseline on
    # the first approved run.
    from jira_testgen.draft.schema import ApprovalState

    draft = build_draft(count=4)
    draft.approval = ApprovalState(status="approved", approved_fingerprint=None)
    path = write_draft(drafts_dir, draft)

    report = publish_draft(make_client(FakeJira()), STORY_KEY, drafts_dir=drafts_dir)
    assert report.verdict == "success"

    saved = load_draft(path)
    assert saved.approval.status == "approved"
    assert saved.approval.approved_fingerprint is not None


def test_cosmetic_reformatting_does_not_void_approval(make_client, drafts_dir):
    # Whitespace is not content: an engineer who re-indents has not changed the
    # test cases.
    path = write_approved(drafts_dir, count=4)
    draft = load_draft(path)
    draft.test_cases[0].expected_results = (
        draft.test_cases[0].expected_results.replace(" ", "  ") + "\n"
    )
    write_draft(drafts_dir, draft)

    report = publish_draft(make_client(FakeJira()), STORY_KEY, drafts_dir=drafts_dir)
    assert report.verdict == "success"
