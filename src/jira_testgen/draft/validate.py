"""Draft validation (FR-007 - FR-009, FR-011, FR-017, FR-061 - FR-063).

Every message names its subject -- the offending test case identity, or the
criterion label -- because the engineer's next action is to open the file and go
straight there.

Structural problems and coverage problems are reported together rather than one
per run: an engineer fixing three gaps should learn about three gaps.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jira_testgen import limits
from jira_testgen.draft.identity import parse_identity
from jira_testgen.draft.schema import (
    CATEGORIES,
    MAX_SUMMARY_LENGTH,
    DraftSet,
)

# FR-011: a test case must be executable by someone who has not read the story.
# Fully checking that needs human judgement, but a step list that only points at
# the story instead of saying what to do is mechanically detectable, and it is
# the failure mode worth catching.
_UNRESOLVED_REFERENCE_HINTS = (
    "as described in the story",
    "as per the story",
    "see the story",
    "see the ticket",
    "per the acceptance criteria",
    "as above",
    "same as above",
    "refer to the story",
    "tbd",
    "todo",
)


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    coverage: dict[str, list[str]] = field(default_factory=dict)
    uncovered: list[str] = field(default_factory=list)
    missing_positive: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def test_case_count(self) -> int:
        return sum(len(v) for v in self.coverage.values()) if self.coverage else 0


def validate_draft(draft: DraftSet, *, source: str = "draft") -> ValidationReport:
    """Check a draft without contacting Jira."""
    report = ValidationReport()
    known_labels = set(draft.criterion_labels())

    if not draft.criteria:
        report.errors.append(
            f"{source}: the draft has no acceptance criteria, so coverage cannot be "
            "established. Regenerate it."
        )

    if not draft.test_cases:
        # Distinct from "malformed": a fresh scaffold legitimately looks like
        # this until the Claude Code session fills it in.
        report.errors.append(
            f"{source}: no test cases yet. The Claude Code session writes these into "
            "`test_cases:`; the scaffold is not publishable until it does."
        )

    seen: dict[str, int] = {}
    for position, case in enumerate(draft.test_cases, start=1):
        label = case.identity or f"(test case {position}, no identity)"

        if not case.identity:
            report.errors.append(
                f"{source}: test case {position} has no `identity`. "
                "Use the next value from `identity_allocation`."
            )
        elif parse_identity(case.identity) is None:
            report.errors.append(
                f"{source}: {label} has a malformed identity. "
                "Expected the form PROJ-123-TC-001."
            )
        else:
            parsed = parse_identity(case.identity)
            if parsed and draft.source_issue and parsed[0] != draft.source_issue:
                report.errors.append(
                    f"{source}: {label} belongs to {parsed[0]}, not {draft.source_issue}."
                )
            seen[case.identity] = seen.get(case.identity, 0) + 1

        if not case.summary.strip():
            report.errors.append(f"{source}: {label} has an empty `summary`.")
        elif len(case.summary) > MAX_SUMMARY_LENGTH:
            # Jira rejects an over-long summary outright. Catching it here makes
            # it a fixable draft problem rather than a failure discovered
            # halfway through publishing.
            report.errors.append(
                f"{source}: {label} has a summary of {len(case.summary)} characters; "
                f"Jira accepts at most {MAX_SUMMARY_LENGTH}. Shorten it."
            )

        if not case.preconditions.strip():
            report.errors.append(
                f"{source}: {label} has empty `preconditions`. "
                "Write 'None' if there genuinely are none."
            )

        if not case.steps:
            report.errors.append(
                f"{source}: {label} has no steps (at least one is required)."
            )
        else:
            for step_index, step in enumerate(case.steps, start=1):
                if not str(step).strip():
                    report.errors.append(
                        f"{source}: {label} step {step_index} is empty."
                    )

        if not case.expected_results.strip():
            report.errors.append(f"{source}: {label} has empty `expected_results`.")

        if case.category not in CATEGORIES:
            report.errors.append(
                f"{source}: {label} has category {case.category!r}. "
                f"Use one of: {', '.join(CATEGORIES)}."
            )

        if not case.covers:
            report.errors.append(
                f"{source}: {label} does not say which criterion it covers. "
                "Add at least one label to `covers`."
            )
        for covered in case.covers:
            if covered not in known_labels:
                report.errors.append(
                    f'{source}: {label} covers "{covered}", which is not a criterion '
                    f"of {draft.source_issue}."
                )

        # FR-011: self-containment.
        for hint in _UNRESOLVED_REFERENCE_HINTS:
            haystack = " ".join(
                [case.preconditions, case.expected_results, *[str(s) for s in case.steps]]
            ).casefold()
            if hint in haystack:
                report.errors.append(
                    f"{source}: {label} defers to the story or to another test case "
                    f'(found "{hint}"). A test case must be executable by someone who '
                    "has not read the story -- write out what to do."
                )
                break

    for identity, count in seen.items():
        if count > 1:
            report.errors.append(
                f"{source}: identity {identity} is used by {count} test cases. "
                "Each must be unique."
            )

    # Coverage (FR-008, FR-007, FR-063).
    coverage: dict[str, list[str]] = {label: [] for label in draft.criterion_labels()}
    positives: dict[str, list[str]] = {label: [] for label in draft.criterion_labels()}
    for case in draft.test_cases:
        for covered in case.covers:
            if covered in coverage:
                coverage[covered].append(case.identity)
                if case.category == "positive":
                    positives[covered].append(case.identity)
    report.coverage = coverage

    for label, identities in coverage.items():
        if not identities:
            report.uncovered.append(label)
            report.errors.append(
                f"{source}: {label} is not covered by any test case."
            )
        elif not positives[label]:
            report.missing_positive.append(label)
            report.errors.append(
                f"{source}: {label} has no positive test case."
            )

    if draft.test_cases:
        categories = {case.category for case in draft.test_cases}
        if "negative" not in categories:
            report.errors.append(
                f"{source}: the set has no negative test case (at least one is required)."
            )
        if "edge" not in categories:
            report.errors.append(
                f"{source}: the set has no edge test case (at least one is required)."
            )

    warning = limits.size_warning(len(draft.test_cases))
    if warning:
        report.warnings.append(warning)
    if limits.exceeds_ceiling(len(draft.test_cases)):
        report.warnings.append(limits.ceiling_message(len(draft.test_cases)))

    return report


def approval_state_description(draft: DraftSet, current_fingerprint: str) -> str:
    """How to describe this draft's approval in human output (FR-043)."""
    if not draft.approval.is_approved:
        return "draft (not approved)"
    recorded = draft.approval.approved_fingerprint
    if recorded is None:
        return "approved (baseline not yet recorded)"
    if recorded != current_fingerprint:
        return "approval voided by edit"
    return "approved"
