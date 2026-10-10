"""T072: a published issue that no longer exists is re-created (FR-028).

A note on how this is reachable at all. Because no state is kept locally, the
only record that a test case was published is the marker **on the issue**. So a
fully propagated delete -- issue, property and link all gone -- leaves nothing
to discover, and the test case is simply created again. That satisfies FR-028's
real requirement (never report a missing issue as present), but it is
indistinguishable from a first publish.

The distinct `recreate` path exists for the narrow race where the issue vanishes
*mid-run*: discovery read its marker, and the content read then 404s. Both are
tested below.
"""

from jira_testgen.publish import publish_draft

from .draft_factory import STORY_KEY, write_approved
from .fake_jira import FakeJira


def _published(make_client, drafts_dir):
    write_approved(drafts_dir, count=4)
    fake = FakeJira()
    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    return fake, report


# --- deleted mid-run: the `recreate` decision ---------------------------


def test_an_issue_that_vanishes_mid_run_is_recreated(make_client, drafts_dir):
    fake, first = _published(make_client, drafts_dir)
    victim = first.outcomes[1]
    fake.vanish_content(victim.issue_key)

    second = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    outcome = next(o for o in second.outcomes if o.identity == victim.identity)
    assert outcome.decision == "recreated"
    assert outcome.issue_key != victim.issue_key


def test_the_recreated_issue_carries_its_identity_again(make_client, drafts_dir):
    fake, first = _published(make_client, drafts_dir)
    victim = first.outcomes[1]
    fake.vanish_content(victim.issue_key)

    second = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    outcome = next(o for o in second.outcomes if o.identity == victim.identity)
    marker = fake.properties[outcome.issue_key]
    assert marker["identity"] == victim.identity
    assert marker["source_issue"] == STORY_KEY


def test_the_recreated_issue_is_linked_to_the_story(make_client, drafts_dir):
    fake, first = _published(make_client, drafts_dir)
    victim = first.outcomes[1]
    fake.vanish_content(victim.issue_key)

    second = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    outcome = next(o for o in second.outcomes if o.identity == victim.identity)
    assert (outcome.issue_key, STORY_KEY) in fake.links


def test_the_survivors_are_left_alone(make_client, drafts_dir):
    fake, first = _published(make_client, drafts_dir)
    victim = first.outcomes[1]
    fake.vanish_content(victim.issue_key)

    second = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    others = [o for o in second.outcomes if o.identity != victim.identity]
    assert all(o.decision == "unchanged" for o in others)
    assert fake.updated == []


# --- fully deleted: never reported as present --------------------------


def test_a_fully_deleted_issue_is_not_reported_as_present(make_client, drafts_dir):
    # The requirement that actually matters: a missing issue must never be
    # passed off as already published.
    fake, first = _published(make_client, drafts_dir)
    victim = first.outcomes[1]
    fake.delete_issue(victim.issue_key)

    second = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    outcome = next(o for o in second.outcomes if o.identity == victim.identity)
    assert outcome.decision != "unchanged"
    assert outcome.issue_key not in (None, victim.issue_key)


def test_a_fully_deleted_issue_is_published_again(make_client, drafts_dir):
    fake, first = _published(make_client, drafts_dir)
    fake.delete_issue(first.outcomes[1].issue_key)

    publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    live = [k for k in fake.created if k not in fake.deleted]
    assert len(live) == 4


def test_recreation_leaves_exactly_one_issue_per_test_case(make_client, drafts_dir):
    fake, first = _published(make_client, drafts_dir)
    fake.delete_issue(first.outcomes[1].issue_key)
    publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)

    identities = [p["identity"] for p in fake.properties.values()]
    assert len(identities) == len(set(identities)) == 4


# --- unlinked but alive ------------------------------------------------


def test_an_unlinked_but_surviving_issue_is_relinked_not_recreated(make_client, drafts_dir):
    fake, first = _published(make_client, drafts_dir)
    victim = first.outcomes[2]
    fake.unlink(victim.issue_key)
    created_before = list(fake.created)

    second = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    outcome = next(o for o in second.outcomes if o.identity == victim.identity)
    assert outcome.decision == "relinked"
    assert outcome.issue_key == victim.issue_key
    assert fake.created == created_before
