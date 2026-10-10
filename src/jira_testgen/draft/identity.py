"""Test case identity (FR-025, FR-048).

Identity is derived from the story key and a position, never from wording. That
single property is what makes editing a test case safe: if identity tracked
content, every edit would look like a new test case and publishing it would
create a duplicate.

Allocation starts past the highest ordinal already published for the story, so a
regenerated draft cannot mint an identity some existing issue already holds
(FR-048).
"""

from __future__ import annotations

import re

_IDENTITY_RE = re.compile(r"^(?P<story>[A-Z][A-Z0-9_]*-\d+)-TC-(?P<ordinal>\d{3,})$")

SUFFIX = "-TC-"


def mint_identity(story_key: str, ordinal: int) -> str:
    """``("PROJ-123", 7)`` -> ``"PROJ-123-TC-007"``."""
    if ordinal < 1:
        raise ValueError(f"ordinal must be 1 or greater, got {ordinal}")
    return f"{story_key}{SUFFIX}{ordinal:03d}"


def parse_identity(identity: str | None) -> tuple[str, int] | None:
    """``"PROJ-123-TC-007"`` -> ``("PROJ-123", 7)``, or ``None`` if malformed."""
    if not identity or not isinstance(identity, str):
        return None
    match = _IDENTITY_RE.match(identity.strip())
    if not match:
        return None
    return match.group("story"), int(match.group("ordinal"))


def ordinal_of(identity: str | None) -> int | None:
    parsed = parse_identity(identity)
    return parsed[1] if parsed else None


def identity_prefix(story_key: str) -> str:
    return f"{story_key}{SUFFIX}"


class IdentityAllocator:
    """Hands out the next free identity for a story."""

    def __init__(self, story_key: str, published_identities: list[str] | None = None) -> None:
        self.story_key = story_key
        highest = 0
        for identity in published_identities or []:
            parsed = parse_identity(identity)
            # An identity belonging to another story tells us nothing about
            # this story's numbering.
            if parsed and parsed[0] == story_key:
                highest = max(highest, parsed[1])
        self._next = highest + 1

    @property
    def next_ordinal(self) -> int:
        return self._next

    @property
    def prefix(self) -> str:
        return identity_prefix(self.story_key)

    def allocate(self) -> str:
        identity = mint_identity(self.story_key, self._next)
        self._next += 1
        return identity
