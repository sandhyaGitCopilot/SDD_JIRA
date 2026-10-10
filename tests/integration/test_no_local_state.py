"""T078: no local state is needed to re-run safely (FR-026a, FR-026b, SC-016).

Everything the tool needs to recognise its own work lives on the Jira issues, so
deleting every local file -- or running from another machine entirely -- must
produce no duplicates.
"""

import shutil

from jira_testgen.publish import publish_draft

from .draft_factory import STORY_KEY, many_cases, write_approved
from .fake_jira import FakeJira


def test_deleting_the_drafts_directory_and_republishing_creates_no_duplicates(
    make_client, drafts_dir
):
    write_approved(drafts_dir, cases=many_cases(6))
    fake = FakeJira()
    publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    created = list(fake.created)

    # Wipe everything local, as a fresh clone or another machine would have.
    shutil.rmtree(drafts_dir)
    drafts_dir.mkdir()
    write_approved(drafts_dir, cases=many_cases(6))

    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert fake.created == created
    assert all(o.decision == "unchanged" for o in report.outcomes)


def test_publishing_from_a_second_location_is_also_a_no_op(make_client, drafts_dir, tmp_path):
    write_approved(drafts_dir, cases=many_cases(6))
    fake = FakeJira()
    publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    created = list(fake.created)

    # A second engineer, their own checkout, the same story.
    other = tmp_path / "other-machine"
    other.mkdir()
    write_approved(other, cases=many_cases(6))

    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=other)
    assert fake.created == created
    assert all(o.decision == "unchanged" for o in report.outcomes)


def test_two_engineers_publishing_in_sequence_do_not_duplicate(make_client, drafts_dir, tmp_path):
    # The spec's concurrency edge case, in its sequential form.
    first_dir = drafts_dir
    second_dir = tmp_path / "second"
    second_dir.mkdir()
    write_approved(first_dir, cases=many_cases(6))
    write_approved(second_dir, cases=many_cases(6))

    fake = FakeJira()
    publish_draft(make_client(fake), STORY_KEY, drafts_dir=first_dir)
    publish_draft(make_client(fake), STORY_KEY, drafts_dir=second_dir)
    assert len(fake.created) == 6


def test_discovery_reads_everything_it_needs_from_jira(make_client, drafts_dir):
    # If any decision depended on local state, wiping the drafts directory
    # between the two runs above would have produced duplicates. This asserts
    # the mechanism directly: markers live on the issues.
    write_approved(drafts_dir, cases=many_cases(4))
    fake = FakeJira()
    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    for outcome in report.outcomes:
        marker = fake.properties[outcome.issue_key]
        assert marker["identity"] == outcome.identity
        assert marker["source_issue"] == STORY_KEY
        assert marker["content_fingerprint"]
