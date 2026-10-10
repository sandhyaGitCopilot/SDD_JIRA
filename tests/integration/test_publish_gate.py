"""T043: the approval gate (FR-013, FR-015, FR-016, quickstart scenario B).

The assertion that matters is that Jira is untouched -- asserted against the
fake's recorded writes, not inferred from the exit code.
"""

import pytest

from jira_testgen.errors import DraftRefusedError
from jira_testgen.publish import publish_draft

from .draft_factory import STORY_KEY, write_approved, write_unapproved
from .fake_jira import FakeJira


def test_unapproved_draft_is_refused(make_client, drafts_dir):
    write_unapproved(drafts_dir)
    with pytest.raises(DraftRefusedError):
        publish_draft(make_client(FakeJira()), STORY_KEY, drafts_dir=drafts_dir)


def test_refusal_names_the_file_and_the_marker(make_client, drafts_dir):
    write_unapproved(drafts_dir)
    with pytest.raises(DraftRefusedError) as excinfo:
        publish_draft(make_client(FakeJira()), STORY_KEY, drafts_dir=drafts_dir)
    message = str(excinfo.value)
    assert f"{STORY_KEY}.yaml" in message
    assert "status: approved" in message


def test_nothing_is_created_and_nothing_is_linked(make_client, drafts_dir):
    write_unapproved(drafts_dir)
    fake = FakeJira()
    with pytest.raises(DraftRefusedError):
        publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert fake.created == []
    assert fake.links == []
    assert fake.writes == []


def test_an_invalid_draft_is_refused_even_when_approved(make_client, drafts_dir):
    # FR-017: validation runs before the approval check matters.
    from .draft_factory import build_draft, write_draft

    draft = build_draft(approved=True)
    draft.test_cases[0].steps = []
    write_draft(drafts_dir, draft)

    fake = FakeJira()
    with pytest.raises(DraftRefusedError) as excinfo:
        publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert "no steps" in str(excinfo.value)
    assert fake.writes == []


def test_a_missing_draft_file_says_to_prepare_first(make_client, drafts_dir):
    from jira_testgen.draft.schema import DraftSchemaError

    with pytest.raises(DraftSchemaError) as excinfo:
        publish_draft(make_client(FakeJira()), STORY_KEY, drafts_dir=drafts_dir)
    assert "prepare" in str(excinfo.value)


def test_an_approved_draft_is_not_refused(make_client, drafts_dir):
    write_approved(drafts_dir, count=4)
    report = publish_draft(make_client(FakeJira()), STORY_KEY, drafts_dir=drafts_dir)
    assert report.verdict == "success"
