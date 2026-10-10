"""Build approved and unapproved draft files for the publishing tests.

A fixture draft is what decouples User Story 2's tests from User Story 1: these
never call `prepare`.
"""

from __future__ import annotations

from pathlib import Path

from jira_testgen.draft.fingerprint import content_fingerprint
from jira_testgen.draft.schema import (
    AcceptanceCriterion,
    ApprovalState,
    DraftSet,
    draft_path,
    dump_draft,
)
from jira_testgen.draft.schema import TestCase as DraftTestCase

STORY_KEY = "PROJ-123"

DEFAULT_CRITERIA = [
    "User can request a reset link with a registered email address.",
    "Reset link expires after 24 hours.",
]


def make_test_case(ordinal: int, *, category="positive", covers=("AC-1",), summary=None):
    return DraftTestCase(
        identity=f"{STORY_KEY}-TC-{ordinal:03d}",
        category=category,
        covers=list(covers),
        summary=summary or f"Test case {ordinal}",
        preconditions="An account exists for qa.user@example.com.",
        steps=["Open the password reset page.", "Enter the address and submit."],
        expected_results="A confirmation is shown and the email arrives.",
    )


def build_draft(
    *,
    # Four by default: fewer cannot satisfy FR-063's set-level floor of at least
    # one negative and one edge case alongside a positive per criterion.
    count: int = 4,
    criteria: list[str] | None = None,
    approved: bool = False,
    cases: list[DraftTestCase] | None = None,
) -> DraftSet:
    """A valid draft. Categories are assigned so FR-063 is satisfied."""
    criteria_texts = criteria if criteria is not None else DEFAULT_CRITERIA
    criteria_objs = [
        AcceptanceCriterion(ordinal=i, label=f"AC-{i}", source_text=text)
        for i, text in enumerate(criteria_texts, start=1)
    ]

    if cases is None:
        cases = []
        labels = [c.label for c in criteria_objs]
        for ordinal in range(1, count + 1):
            label = labels[(ordinal - 1) % len(labels)] if labels else "AC-1"
            # Every criterion needs a positive; the set needs a negative and an
            # edge. Give the first pass positives, then alternate.
            if ordinal <= len(labels):
                category = "positive"
            elif ordinal == len(labels) + 1:
                category = "negative"
            elif ordinal == len(labels) + 2:
                category = "edge"
            else:
                category = "boundary"
            cases.append(make_test_case(ordinal, category=category, covers=(label,)))

        # Guarantee the set-level floor even for small counts.
        categories = {c.category for c in cases}
        if "negative" not in categories and len(cases) > 1:
            cases[-1].category = "negative"
        categories = {c.category for c in cases}
        if "edge" not in categories and len(cases) > 2:
            cases[-2].category = "edge"

    draft = DraftSet(
        source_issue=STORY_KEY,
        source_summary="Password reset via email link",
        criteria_source="description",
        criteria=criteria_objs,
        test_cases=cases,
        identity_allocation={"prefix": f"{STORY_KEY}-TC-", "next_ordinal": len(cases) + 1},
    )

    if approved:
        draft.approval = ApprovalState(
            status="approved", approved_fingerprint=content_fingerprint(draft)
        )
    return draft


def write_draft(drafts_dir: Path, draft: DraftSet) -> Path:
    path = draft_path(drafts_dir, draft.source_issue)
    dump_draft(draft, path)
    return path


def write_approved(drafts_dir: Path, **kwargs) -> Path:
    return write_draft(drafts_dir, build_draft(approved=True, **kwargs))


def write_unapproved(drafts_dir: Path, **kwargs) -> Path:
    return write_draft(drafts_dir, build_draft(approved=False, **kwargs))


def many_cases(n: int, criteria_count: int = 2) -> list[DraftTestCase]:
    """``n`` valid test cases spread over ``criteria_count`` criteria."""
    cases = []
    for ordinal in range(1, n + 1):
        label = f"AC-{((ordinal - 1) % criteria_count) + 1}"
        if ordinal <= criteria_count:
            category = "positive"
        elif ordinal == criteria_count + 1:
            category = "negative"
        elif ordinal == criteria_count + 2:
            category = "edge"
        else:
            category = "boundary"
        cases.append(make_test_case(ordinal, category=category, covers=(label,)))
    return cases
