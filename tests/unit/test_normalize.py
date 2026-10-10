"""T023: comparison normalization (FR-057).

This is the function that decides whether a story "changed". Too strict and
every Jira editor reflow blocks a publish; too loose and a reworded criterion
slips through. Both failure directions are tested.
"""

import pytest

from jira_testgen.criteria import normalize_for_comparison as norm


@pytest.mark.parametrize(
    ("left", "right"),
    [
        # Whitespace runs and newlines collapse.
        ("Reset link expires after 24 hours.", "Reset   link  expires\nafter 24 hours."),
        ("  leading and trailing  ", "leading and trailing"),
        # Markup is cosmetic.
        ("Reset link expires after **24 hours**.", "Reset link expires after 24 hours."),
        ("Reset link expires after _24 hours_.", "Reset link expires after 24 hours."),
        ("Reset link expires after `24 hours`.", "Reset link expires after 24 hours."),
        # List and numbering markers are cosmetic.
        ("- User can request a link.", "User can request a link."),
        ("* User can request a link.", "User can request a link."),
        ("1. User can request a link.", "User can request a link."),
        ("### Heading text", "Heading text"),
        # Case is cosmetic.
        ("Reset Link Expires", "reset link expires"),
    ],
)
def test_formatting_only_differences_compare_equal(left, right):
    assert norm(left) == norm(right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        # A reworded criterion must NOT compare equal.
        ("Reset link expires after 24 hours.", "Reset link expires after 48 hours."),
        ("User can request a reset link.", "User can request a reset code."),
        ("Link expires after 24 hours.", "Link expires."),
        ("An unregistered address shows no hint.", "An unregistered address shows a hint."),
    ],
)
def test_substantive_differences_do_not_compare_equal(left, right):
    assert norm(left) != norm(right)


def test_empty_and_none_normalize_to_empty():
    assert norm("") == ""
    assert norm(None) == ""


def test_normalization_is_idempotent():
    once = norm("###  **Reset** link   expires.")
    assert norm(once) == once


def test_punctuation_is_significant():
    # Not stripped: "expires" and "expires?" are different statements.
    assert norm("It expires.") != norm("It expires?")
