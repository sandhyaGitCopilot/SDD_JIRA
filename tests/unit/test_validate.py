"""T038: draft validation rules (FR-007 - FR-009, FR-011, FR-017, FR-061 - FR-063).

Every message must name its subject -- the test case identity or the criterion
label -- because the engineer's next action is to open the file and go there.
Several tests assert that naming explicitly.
"""

from jira_testgen.draft.schema import (
    MAX_SUMMARY_LENGTH,
    AcceptanceCriterion,
    ApprovalState,
    DraftSet,
)
from jira_testgen.draft.schema import TestCase as DraftTestCase
from jira_testgen.draft.validate import approval_state_description, validate_draft


def _case(identity="PROJ-1-TC-001", **overrides):
    defaults = dict(
        identity=identity,
        category="positive",
        covers=["AC-1"],
        summary="A summary",
        preconditions="None.",
        steps=["Open the page.", "Submit the form."],
        expected_results="It works.",
    )
    defaults.update(overrides)
    return DraftTestCase(**defaults)


def _draft(cases=None, criteria_labels=("AC-1",)):
    return DraftSet(
        source_issue="PROJ-1",
        criteria=[
            AcceptanceCriterion(ordinal=i, label=label, source_text=f"Criterion {label}.")
            for i, label in enumerate(criteria_labels, start=1)
        ],
        test_cases=list(cases if cases is not None else [_case()]),
    )


def _full_set():
    """One positive per criterion plus a negative and an edge, as FR-063 wants."""
    return _draft(
        cases=[
            _case("PROJ-1-TC-001", category="positive", covers=["AC-1"]),
            _case("PROJ-1-TC-002", category="positive", covers=["AC-2"]),
            _case("PROJ-1-TC-003", category="negative", covers=["AC-1"]),
            _case("PROJ-1-TC-004", category="edge", covers=["AC-2"]),
        ],
        criteria_labels=("AC-1", "AC-2"),
    )


def test_a_complete_set_passes():
    report = validate_draft(_full_set())
    assert report.ok, report.errors


def test_an_empty_scaffold_is_reported_as_not_yet_filled():
    # Distinct from malformed: this is the normal state right after `prepare`.
    report = validate_draft(_draft(cases=[]))
    assert not report.ok
    assert any("no test cases yet" in e for e in report.errors)


def test_missing_steps_names_the_test_case():
    report = validate_draft(_draft([_case(steps=[])]))
    assert any("PROJ-1-TC-001" in e and "no steps" in e for e in report.errors)


def test_empty_step_is_rejected():
    report = validate_draft(_draft([_case(steps=["Open the page.", "   "])]))
    assert any("step 2 is empty" in e for e in report.errors)


def test_empty_summary_is_rejected():
    report = validate_draft(_draft([_case(summary="  ")]))
    assert any("empty `summary`" in e for e in report.errors)


def test_over_long_summary_is_rejected_before_jira_sees_it():
    # Jira caps summaries at 255. Catching it here makes it a fixable draft
    # problem rather than a failure discovered halfway through publishing.
    report = validate_draft(_draft([_case(summary="x" * (MAX_SUMMARY_LENGTH + 1))]))
    assert any(str(MAX_SUMMARY_LENGTH) in e for e in report.errors)


def test_summary_at_the_limit_is_accepted():
    report = validate_draft(_draft([_case(summary="x" * MAX_SUMMARY_LENGTH)]))
    assert not any("characters" in e for e in report.errors)


def test_empty_preconditions_is_rejected_with_guidance():
    report = validate_draft(_draft([_case(preconditions="")]))
    assert any("Write 'None'" in e for e in report.errors)


def test_unknown_category_lists_the_valid_ones():
    report = validate_draft(_draft([_case(category="smoke")]))
    assert any("smoke" in e and "positive" in e for e in report.errors)


def test_covers_pointing_at_an_unknown_criterion_names_both():
    report = validate_draft(_draft([_case(covers=["AC-9"])]))
    assert any("AC-9" in e and "PROJ-1" in e for e in report.errors)


def test_empty_covers_is_rejected():
    report = validate_draft(_draft([_case(covers=[])]))
    assert any("which criterion it covers" in e for e in report.errors)


def test_uncovered_criterion_is_reported_and_listed():
    draft = _draft(
        cases=[_case("PROJ-1-TC-001", covers=["AC-1"])], criteria_labels=("AC-1", "AC-2")
    )
    report = validate_draft(draft)
    assert "AC-2" in report.uncovered
    assert any("AC-2 is not covered" in e for e in report.errors)


def test_criterion_with_only_a_negative_case_is_reported():
    # FR-007: every criterion needs a positive case, whatever else it has.
    draft = _draft(cases=[_case(category="negative")], criteria_labels=("AC-1",))
    report = validate_draft(draft)
    assert "AC-1" in report.missing_positive
    assert any("no positive test case" in e for e in report.errors)


def test_set_without_a_negative_case_is_rejected():
    draft = _draft(
        cases=[
            _case("PROJ-1-TC-001", category="positive", covers=["AC-1"]),
            _case("PROJ-1-TC-002", category="edge", covers=["AC-1"]),
        ]
    )
    report = validate_draft(draft)
    assert any("no negative test case" in e for e in report.errors)


def test_set_without_an_edge_case_is_rejected():
    draft = _draft(
        cases=[
            _case("PROJ-1-TC-001", category="positive", covers=["AC-1"]),
            _case("PROJ-1-TC-002", category="negative", covers=["AC-1"]),
        ]
    )
    report = validate_draft(draft)
    assert any("no edge test case" in e for e in report.errors)


def test_duplicate_identities_are_rejected():
    draft = _draft([_case("PROJ-1-TC-001"), _case("PROJ-1-TC-001", category="negative")])
    report = validate_draft(draft)
    assert any("is used by 2 test cases" in e for e in report.errors)


def test_malformed_identity_is_rejected():
    report = validate_draft(_draft([_case("TC-1")]))
    assert any("malformed identity" in e for e in report.errors)


def test_identity_from_another_story_is_rejected():
    report = validate_draft(_draft([_case("OTHER-9-TC-001")]))
    assert any("belongs to OTHER-9" in e for e in report.errors)


# --- FR-011: self-containment -------------------------------------------


def test_steps_that_defer_to_the_story_are_rejected():
    report = validate_draft(_draft([_case(steps=["Follow the steps as described in the story."])]))
    assert any("defers to the story" in e for e in report.errors)


def test_expected_results_saying_see_the_ticket_is_rejected():
    report = validate_draft(_draft([_case(expected_results="See the ticket.")]))
    assert any("defers to the story" in e for e in report.errors)


def test_same_as_above_is_rejected():
    report = validate_draft(_draft([_case(preconditions="Same as above.")]))
    assert any("defers to the story" in e for e in report.errors)


def test_tbd_is_rejected():
    report = validate_draft(_draft([_case(expected_results="TBD")]))
    assert any("defers to the story" in e for e in report.errors)


def test_a_self_contained_case_is_not_flagged():
    report = validate_draft(_full_set())
    assert not any("defers to the story" in e for e in report.errors)


# --- size and approval --------------------------------------------------


def test_large_set_produces_a_warning_not_an_error():
    cases = [
        _case(f"PROJ-1-TC-{i:03d}", category="positive" if i % 3 else "negative", covers=["AC-1"])
        for i in range(1, 30)
    ]
    cases.append(_case("PROJ-1-TC-030", category="edge", covers=["AC-1"]))
    report = validate_draft(_draft(cases))
    assert any("review may be slow" in w for w in report.warnings)
    assert not any("review may be slow" in e for e in report.errors)


def test_approval_description_tracks_the_lifecycle():
    draft = _full_set()
    assert approval_state_description(draft, "abc") == "draft (not approved)"

    draft.approval = ApprovalState(status="approved", approved_fingerprint=None)
    assert "baseline not yet recorded" in approval_state_description(draft, "abc")

    draft.approval = ApprovalState(status="approved", approved_fingerprint="abc")
    assert approval_state_description(draft, "abc") == "approved"

    # The one that protects FR-043: content moved on after approval.
    draft.approval = ApprovalState(status="approved", approved_fingerprint="old")
    assert approval_state_description(draft, "new") == "approval voided by edit"


def test_errors_are_reported_together_not_one_per_run():
    draft = _draft([_case(summary="", steps=[], covers=[], category="bogus")])
    report = validate_draft(draft)
    assert len(report.errors) >= 4
