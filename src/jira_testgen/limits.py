"""Set-size thresholds (FR-064, FR-065, FR-066).

Fixed constants, deliberately not settings. Making them configurable would add
two more values a first-time user has to understand, against SC-009, and an
oversized publish should be a deliberate per-run act rather than a value someone
set once and forgot (FR-067).
"""

from __future__ import annotations

# Above this many test cases, review stops fitting the 10-minute budget in
# SC-001, so the engineer is warned before starting.
WARN_ABOVE = 25

# Above this, something has almost certainly gone wrong upstream. Publishing
# requires an explicit per-run override.
REFUSE_ABOVE = 100


def size_warning(count: int) -> str | None:
    """A warning when the set is large enough to slow review, else ``None``."""
    if count > WARN_ABOVE:
        return (
            f"Set contains {count} test cases (above {WARN_ABOVE}); review may be slow."
        )
    return None


def exceeds_ceiling(count: int) -> bool:
    """True when publishing needs ``--allow-large``."""
    return count > REFUSE_ABOVE


def ceiling_message(count: int) -> str:
    """Why publishing was refused, and the way forward."""
    return (
        f"Set contains {count} test cases, above the limit of {REFUSE_ABOVE}. "
        "Review whether the story is too large to test as one unit. "
        "To publish anyway, re-run with --allow-large."
    )
