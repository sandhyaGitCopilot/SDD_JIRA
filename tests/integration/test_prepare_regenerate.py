"""T030: draft-overwrite refusal and regeneration (FR-047 - FR-050, scenario G).

This is the path that can destroy reviewed work, so the refusal is asserted
byte-for-byte rather than by "the file still exists".
"""

import pytest

from jira_testgen.draft.schema import load_draft
from jira_testgen.errors import DraftExistsError
from jira_testgen.prepare import prepare_draft

from .conftest import STORY_KEY, StubJira

REVIEWED = """\
# a reviewed and edited draft the engineer cares about
schema_version: 1
source_issue: PROJ-123
"""


def _existing(drafts_dir):
    path = drafts_dir / f"{STORY_KEY}.yaml"
    path.write_text(REVIEWED, encoding="utf-8")
    return path


def test_second_prepare_refuses(make_client, drafts_dir):
    _existing(drafts_dir)
    with pytest.raises(DraftExistsError):
        prepare_draft(make_client(StubJira()), STORY_KEY, drafts_dir=drafts_dir)


def test_refusal_names_the_existing_file(make_client, drafts_dir):
    _existing(drafts_dir)
    with pytest.raises(DraftExistsError) as excinfo:
        prepare_draft(make_client(StubJira()), STORY_KEY, drafts_dir=drafts_dir)
    message = str(excinfo.value)
    assert f"{STORY_KEY}.yaml" in message
    assert "--regenerate" in message


def test_refusal_leaves_the_file_byte_for_byte_unchanged(make_client, drafts_dir):
    path = _existing(drafts_dir)
    before = path.read_bytes()
    with pytest.raises(DraftExistsError):
        prepare_draft(make_client(StubJira()), STORY_KEY, drafts_dir=drafts_dir)
    assert path.read_bytes() == before


def test_regenerate_keeps_the_previous_version_as_a_backup(make_client, drafts_dir):
    path = _existing(drafts_dir)
    prepare_draft(make_client(StubJira()), STORY_KEY, drafts_dir=drafts_dir, regenerate=True)
    backup = drafts_dir / f"{STORY_KEY}.yaml.bak"
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == REVIEWED
    # And the new scaffold really did replace it.
    assert path.read_text(encoding="utf-8") != REVIEWED


def test_regenerate_reports_the_file_it_replaced(make_client, drafts_dir):
    _existing(drafts_dir)
    result = prepare_draft(
        make_client(StubJira()), STORY_KEY, drafts_dir=drafts_dir, regenerate=True
    )
    assert result.replaced is not None
    assert result.replaced.name == f"{STORY_KEY}.yaml"
    assert result.backup is not None


def test_regenerated_draft_starts_unapproved(make_client, drafts_dir):
    # FR-049: regenerated content is always reviewed again.
    _existing(drafts_dir)
    result = prepare_draft(
        make_client(StubJira()), STORY_KEY, drafts_dir=drafts_dir, regenerate=True
    )
    assert load_draft(result.path).approval.status == "draft"


def test_regenerate_allocates_past_published_identities(make_client, drafts_dir):
    # FR-048: minting PROJ-123-TC-001 again would collide with the issue that
    # already holds it, so allocation continues past the highest published.
    _existing(drafts_dir)
    stub = StubJira(
        linked=["PROJ-456", "PROJ-457"],
        properties={
            "PROJ-456": {
                "identity": "PROJ-123-TC-001",
                "content_fingerprint": "aaa",
                "source_issue": STORY_KEY,
            },
            "PROJ-457": {
                "identity": "PROJ-123-TC-002",
                "content_fingerprint": "bbb",
                "source_issue": STORY_KEY,
            },
        },
    )
    result = prepare_draft(
        make_client(stub), STORY_KEY, drafts_dir=drafts_dir, regenerate=True
    )
    draft = load_draft(result.path)
    assert draft.identity_allocation["next_ordinal"] == 3


def test_regenerate_lists_published_test_cases_for_reuse(make_client, drafts_dir):
    _existing(drafts_dir)
    stub = StubJira(
        linked=["PROJ-456"],
        properties={
            "PROJ-456": {
                "identity": "PROJ-123-TC-001",
                "content_fingerprint": "aaa",
                "source_issue": STORY_KEY,
            }
        },
    )
    result = prepare_draft(
        make_client(stub), STORY_KEY, drafts_dir=drafts_dir, regenerate=True
    )
    draft = load_draft(result.path)
    published = draft.previously_published
    assert published
    assert published[0]["identity"] == "PROJ-123-TC-001"
    assert published[0]["issue_key"] == "PROJ-456"


def test_regenerate_ignores_foreign_linked_issues(make_client, drafts_dir):
    # FR-026c: an issue without this tool's marker is never claimed.
    _existing(drafts_dir)
    stub = StubJira(linked=["PROJ-999"], properties={})
    result = prepare_draft(
        make_client(stub), STORY_KEY, drafts_dir=drafts_dir, regenerate=True
    )
    draft = load_draft(result.path)
    assert draft.previously_published == []
    assert draft.identity_allocation["next_ordinal"] == 1


def test_regenerate_still_writes_nothing_to_jira(make_client, drafts_dir):
    _existing(drafts_dir)
    stub = StubJira()
    prepare_draft(make_client(stub), STORY_KEY, drafts_dir=drafts_dir, regenerate=True)
    assert stub.writes == []


def test_regenerate_replaces_an_older_backup(make_client, drafts_dir):
    # Only one generation is kept; no requirement asks for history.
    _existing(drafts_dir)
    (drafts_dir / f"{STORY_KEY}.yaml.bak").write_text("ancient", encoding="utf-8")
    prepare_draft(make_client(StubJira()), STORY_KEY, drafts_dir=drafts_dir, regenerate=True)
    assert (drafts_dir / f"{STORY_KEY}.yaml.bak").read_text(encoding="utf-8") == REVIEWED


def test_regenerate_on_a_story_with_no_existing_draft_just_drafts(make_client, drafts_dir):
    result = prepare_draft(
        make_client(StubJira()), STORY_KEY, drafts_dir=drafts_dir, regenerate=True
    )
    assert result.replaced is None
    assert result.path.exists()
    assert not (drafts_dir / f"{STORY_KEY}.yaml.bak").exists()
