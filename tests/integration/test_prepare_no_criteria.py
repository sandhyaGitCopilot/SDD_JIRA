"""T029: the no-criteria stop (FR-005, quickstart scenario I).

A story with no criteria is a stop, not a degraded run: generating test cases
from the summary alone would produce a suite that claims coverage it cannot
have. The run must also leave no draft behind.
"""

import pytest

from jira_testgen.criteria import CriteriaNotFound
from jira_testgen.prepare import prepare_draft

from .conftest import NO_CRITERIA_DESCRIPTION, STORY_KEY, StubJira


def test_no_criteria_raises_rather_than_drafting(make_client, drafts_dir):
    stub = StubJira(description=NO_CRITERIA_DESCRIPTION)
    with pytest.raises(CriteriaNotFound):
        prepare_draft(make_client(stub), STORY_KEY, drafts_dir=drafts_dir)


def test_no_draft_file_is_written(make_client, drafts_dir):
    stub = StubJira(description=NO_CRITERIA_DESCRIPTION)
    with pytest.raises(CriteriaNotFound):
        prepare_draft(make_client(stub), STORY_KEY, drafts_dir=drafts_dir)
    assert list(drafts_dir.iterdir()) == []


def test_message_names_the_description_section_it_looked_for(make_client, drafts_dir):
    stub = StubJira(description=NO_CRITERIA_DESCRIPTION)
    with pytest.raises(CriteriaNotFound) as excinfo:
        prepare_draft(make_client(stub), STORY_KEY, drafts_dir=drafts_dir)
    assert "Acceptance Criteria" in str(excinfo.value)


def test_message_names_the_configured_field_when_one_is_set(make_client, drafts_dir):
    stub = StubJira(description=NO_CRITERIA_DESCRIPTION)
    with pytest.raises(CriteriaNotFound) as excinfo:
        prepare_draft(
            make_client(stub), STORY_KEY, drafts_dir=drafts_dir, ac_field="customfield_10040"
        )
    assert "customfield_10040" in str(excinfo.value)


def test_message_says_the_field_is_unset_when_it_is(make_client, drafts_dir):
    # Naming the absent setting is what tells the engineer what to do next.
    stub = StubJira(description=NO_CRITERIA_DESCRIPTION)
    with pytest.raises(CriteriaNotFound) as excinfo:
        prepare_draft(make_client(stub), STORY_KEY, drafts_dir=drafts_dir)
    assert "JIRA_AC_FIELD" in str(excinfo.value)


def test_nothing_is_written_to_jira(make_client, drafts_dir):
    stub = StubJira(description=NO_CRITERIA_DESCRIPTION)
    with pytest.raises(CriteriaNotFound):
        prepare_draft(make_client(stub), STORY_KEY, drafts_dir=drafts_dir)
    assert stub.writes == []


def test_an_existing_draft_survives_a_no_criteria_run(make_client, drafts_dir):
    # The story lost its criteria after a draft already existed: the stop must
    # not take the reviewed draft with it.
    existing = drafts_dir / f"{STORY_KEY}.yaml"
    existing.write_text("# reviewed work\n", encoding="utf-8")
    stub = StubJira(description=NO_CRITERIA_DESCRIPTION)
    with pytest.raises(CriteriaNotFound):
        prepare_draft(make_client(stub), STORY_KEY, drafts_dir=drafts_dir, regenerate=True)
    assert existing.read_text(encoding="utf-8") == "# reviewed work\n"
