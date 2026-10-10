"""T024: identity minting and parsing (FR-025).

The one property that matters: identity is derived from position, never from
wording. If editing a test case changed its identity, every edit would publish a
duplicate.
"""

import pytest

from jira_testgen.draft.identity import (
    IdentityAllocator,
    mint_identity,
    ordinal_of,
    parse_identity,
)
from jira_testgen.jira.search import identity_to_label, label_to_identity


def test_identity_format_is_zero_padded_to_three():
    assert mint_identity("PROJ-123", 1) == "PROJ-123-TC-001"
    assert mint_identity("PROJ-123", 42) == "PROJ-123-TC-042"
    assert mint_identity("PROJ-123", 100) == "PROJ-123-TC-100"


def test_identity_does_not_depend_on_wording():
    # Same story, same position -> same identity, whatever the test case says.
    assert mint_identity("PROJ-123", 7) == mint_identity("PROJ-123", 7)


def test_parse_identity_round_trips():
    story, ordinal = parse_identity("PROJ-123-TC-007")
    assert story == "PROJ-123"
    assert ordinal == 7


def test_parse_identity_rejects_nonsense():
    for bad in ["", "PROJ-123", "PROJ-123-TC-", "TC-001", "PROJ-123-TC-abc", None]:
        assert parse_identity(bad) is None


def test_ordinal_of_reads_the_number():
    assert ordinal_of("PROJ-123-TC-013") == 13
    assert ordinal_of("not-an-identity") is None


def test_label_round_trip_is_lossless_for_the_key():
    identity = "PROJ-123-TC-001"
    label = identity_to_label(identity)
    assert label == "tcgen-id-proj-123-tc-001"
    assert label_to_identity(label) == identity


def test_allocator_starts_at_one_when_nothing_is_published():
    allocator = IdentityAllocator("PROJ-123", published_identities=[])
    assert allocator.next_ordinal == 1
    assert allocator.allocate() == "PROJ-123-TC-001"
    assert allocator.allocate() == "PROJ-123-TC-002"


def test_allocator_starts_past_the_highest_published_ordinal():
    # FR-048: a regenerated draft must not mint an identity that a published
    # issue already holds, or publishing it would collide.
    allocator = IdentityAllocator(
        "PROJ-123",
        published_identities=["PROJ-123-TC-001", "PROJ-123-TC-005"],
    )
    assert allocator.next_ordinal == 6
    assert allocator.allocate() == "PROJ-123-TC-006"


def test_allocator_ignores_identities_from_another_story():
    allocator = IdentityAllocator(
        "PROJ-123", published_identities=["OTHER-9-TC-050", "PROJ-123-TC-002"]
    )
    assert allocator.next_ordinal == 3


def test_allocator_tolerates_unparseable_published_identities():
    allocator = IdentityAllocator("PROJ-123", published_identities=["garbage", ""])
    assert allocator.next_ordinal == 1


def test_mint_rejects_a_non_positive_ordinal():
    with pytest.raises(ValueError):
        mint_identity("PROJ-123", 0)
