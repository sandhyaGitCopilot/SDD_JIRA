"""T028: the drafting happy path (quickstart scenario A).

The load-bearing assertion is the last one: a drafting run must make zero writes
to Jira (FR-013, SC-005). Everything else is about the scaffold being usable.
"""

from jira_testgen.draft.schema import load_draft
from jira_testgen.prepare import prepare_draft

from .conftest import STORY_KEY, StubJira


def test_five_criteria_yield_a_scaffold_with_five_criteria(make_client, drafts_dir):
    stub = StubJira()
    result = prepare_draft(make_client(stub), STORY_KEY, drafts_dir=drafts_dir)

    draft = load_draft(result.path)
    assert len(draft.criteria) == 5
    assert [c.label for c in draft.criteria] == ["AC-1", "AC-2", "AC-3", "AC-4", "AC-5"]


def test_scaffold_records_the_criteria_source(make_client, drafts_dir):
    # FR-002a: the engineer can always see where the criteria came from.
    stub = StubJira()
    result = prepare_draft(make_client(stub), STORY_KEY, drafts_dir=drafts_dir)
    assert load_draft(result.path).criteria_source == "description"
    assert result.criteria_source == "description"


def test_scaffold_keeps_criterion_text_verbatim(make_client, drafts_dir):
    stub = StubJira()
    result = prepare_draft(make_client(stub), STORY_KEY, drafts_dir=drafts_dir)
    draft = load_draft(result.path)
    assert draft.criteria[1].source_text == "Reset link expires after 24 hours."


def test_scaffold_has_empty_test_cases_awaiting_the_session(make_client, drafts_dir):
    stub = StubJira()
    result = prepare_draft(make_client(stub), STORY_KEY, drafts_dir=drafts_dir)
    draft = load_draft(result.path)
    assert draft.test_cases == []
    # Identities are allocated for the session to consume, so it never has to
    # invent one (FR-025).
    assert draft.identity_allocation["next_ordinal"] == 1
    assert draft.identity_allocation["prefix"] == f"{STORY_KEY}-TC-"


def test_scaffold_starts_unapproved(make_client, drafts_dir):
    stub = StubJira()
    result = prepare_draft(make_client(stub), STORY_KEY, drafts_dir=drafts_dir)
    draft = load_draft(result.path)
    assert draft.approval.status == "draft"
    assert draft.approval.approved_fingerprint is None


def test_file_is_named_after_the_story(make_client, drafts_dir):
    stub = StubJira()
    result = prepare_draft(make_client(stub), STORY_KEY, drafts_dir=drafts_dir)
    assert result.path.name == f"{STORY_KEY}.yaml"
    assert result.path.exists()


def test_non_text_content_is_reported_as_a_warning(make_client, drafts_dir):
    description = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 3},
                "content": [{"type": "text", "text": "Acceptance Criteria"}],
            },
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Only criterion."}],
                            }
                        ],
                    }
                ],
            },
            {
                "type": "mediaSingle",
                "content": [{"type": "media", "attrs": {"id": "x", "type": "file"}}],
            },
        ],
    }
    stub = StubJira(description=description)
    result = prepare_draft(make_client(stub), STORY_KEY, drafts_dir=drafts_dir)
    assert any("not interpreted" in w for w in result.warnings)


def test_drafting_writes_nothing_to_jira(make_client, drafts_dir):
    # FR-013, SC-005. Asserted against recorded calls, not assumed.
    stub = StubJira()
    prepare_draft(make_client(stub), STORY_KEY, drafts_dir=drafts_dir)
    assert stub.writes == []


def test_a_missing_issue_stops_without_writing_a_draft(make_client, drafts_dir):
    import pytest

    from jira_testgen.errors import PermanentError

    stub = StubJira()
    with pytest.raises(PermanentError):
        prepare_draft(make_client(stub), "MISSING-1", drafts_dir=drafts_dir)
    assert list(drafts_dir.iterdir()) == []


def test_a_malformed_issue_key_is_rejected_before_any_request(make_client, drafts_dir):
    import pytest

    from jira_testgen.errors import UserError

    stub = StubJira()
    with pytest.raises(UserError):
        prepare_draft(make_client(stub), "not a key", drafts_dir=drafts_dir)
    assert stub.calls == []
