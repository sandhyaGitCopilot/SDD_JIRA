"""T027: draft file schema contract (contracts/draft-file.md).

Covers the round-trip, every field rule, and the approval lifecycle table.
"""

import pytest

from jira_testgen.draft.schema import (
    SCHEMA_VERSION,
    AcceptanceCriterion,
    ApprovalState,
    DraftSchemaError,
    DraftSet,
    dump_draft,
    load_draft,
)
from jira_testgen.draft.schema import (
    TestCase as DraftTestCase,
)


def _draft(**overrides) -> DraftSet:
    base = DraftSet(
        source_issue="PROJ-123",
        source_summary="Password reset via email link",
        criteria_source="description",
        criteria=[
            AcceptanceCriterion(ordinal=1, label="AC-1", source_text="Link expires in 24h."),
        ],
        test_cases=[
            DraftTestCase(
                identity="PROJ-123-TC-001",
                category="positive",
                covers=["AC-1"],
                summary="Reset link works before expiry",
                preconditions="A reset link was issued 1 hour ago.",
                steps=["Open the reset link.", "Set a new password."],
                expected_results="The password is changed.",
            )
        ],
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_round_trip_preserves_every_field(tmp_path):
    path = tmp_path / "PROJ-123.yaml"
    original = _draft()
    dump_draft(original, path)
    loaded = load_draft(path)

    assert loaded.source_issue == "PROJ-123"
    assert loaded.criteria_source == "description"
    assert loaded.criteria[0].label == "AC-1"
    assert loaded.criteria[0].source_text == "Link expires in 24h."
    case = loaded.test_cases[0]
    assert case.identity == "PROJ-123-TC-001"
    assert case.category == "positive"
    assert case.covers == ["AC-1"]
    assert case.steps == ["Open the reset link.", "Set a new password."]
    assert case.expected_results == "The password is changed."


def test_dumped_file_leads_with_review_instructions(tmp_path):
    # The engineer meets this file with no other guidance, so it has to explain
    # how to approve and how to reject (FR-012).
    path = tmp_path / "PROJ-123.yaml"
    dump_draft(_draft(), path)
    text = path.read_text(encoding="utf-8")
    assert text.startswith("#")
    assert "status: approved" in text
    assert "delete" in text.lower()


def test_multiline_strings_round_trip(tmp_path):
    path = tmp_path / "PROJ-123.yaml"
    draft = _draft()
    draft.test_cases[0].expected_results = "First line.\nSecond line."
    dump_draft(draft, path)
    assert load_draft(path).test_cases[0].expected_results == "First line.\nSecond line."


def test_unknown_schema_version_is_refused_not_guessed_at(tmp_path):
    path = tmp_path / "PROJ-123.yaml"
    dump_draft(_draft(), path)
    text = path.read_text(encoding="utf-8").replace(
        f"schema_version: {SCHEMA_VERSION}", "schema_version: 99"
    )
    path.write_text(text, encoding="utf-8")
    with pytest.raises(DraftSchemaError) as excinfo:
        load_draft(path)
    assert "99" in str(excinfo.value)


def test_missing_file_raises_a_clear_error(tmp_path):
    with pytest.raises(DraftSchemaError) as excinfo:
        load_draft(tmp_path / "absent.yaml")
    assert "absent.yaml" in str(excinfo.value)


def test_malformed_yaml_names_the_file(tmp_path):
    path = tmp_path / "PROJ-123.yaml"
    path.write_text("test_cases: [unclosed\n", encoding="utf-8")
    with pytest.raises(DraftSchemaError) as excinfo:
        load_draft(path)
    assert "PROJ-123.yaml" in str(excinfo.value)


def test_non_mapping_document_is_refused(tmp_path):
    path = tmp_path / "PROJ-123.yaml"
    path.write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(DraftSchemaError):
        load_draft(path)


def test_scaffold_has_no_test_cases_but_is_still_loadable(tmp_path):
    # A freshly prepared scaffold is valid YAML with an empty test_cases list;
    # "not yet filled" must stay distinguishable from "malformed".
    path = tmp_path / "PROJ-123.yaml"
    dump_draft(_draft(test_cases=[]), path)
    loaded = load_draft(path)
    assert loaded.test_cases == []
    assert loaded.approval.status == "draft"


def test_approval_defaults_to_draft_with_no_fingerprint():
    draft = _draft()
    assert draft.approval.status == "draft"
    assert draft.approval.approved_fingerprint is None


def test_approval_state_round_trips(tmp_path):
    path = tmp_path / "PROJ-123.yaml"
    draft = _draft()
    draft.approval = ApprovalState(status="approved", approved_fingerprint="a" * 64)
    dump_draft(draft, path)
    loaded = load_draft(path)
    assert loaded.approval.status == "approved"
    assert loaded.approval.approved_fingerprint == "a" * 64


def test_unknown_approval_status_is_refused(tmp_path):
    path = tmp_path / "PROJ-123.yaml"
    dump_draft(_draft(), path)
    text = path.read_text(encoding="utf-8").replace("status: draft", "status: maybe")
    path.write_text(text, encoding="utf-8")
    with pytest.raises(DraftSchemaError) as excinfo:
        load_draft(path)
    assert "maybe" in str(excinfo.value)


def test_identity_allocation_round_trips(tmp_path):
    path = tmp_path / "PROJ-123.yaml"
    draft = _draft()
    draft.identity_allocation = {"prefix": "PROJ-123-TC-", "next_ordinal": 6}
    dump_draft(draft, path)
    assert load_draft(path).identity_allocation["next_ordinal"] == 6


def test_content_region_excludes_approval_and_provenance():
    # The region the fingerprint covers is defined here, in one place.
    region = _draft().content_region()
    assert set(region) == {"criteria", "test_cases"}


def test_steps_given_as_a_bare_string_are_rejected(tmp_path):
    # Written out directly rather than by patching a dumped file: string
    # surgery on YAML is how a test ends up asserting nothing.
    path = tmp_path / "PROJ-123.yaml"
    path.write_text(
        "schema_version: 1\n"
        "source_issue: PROJ-123\n"
        "criteria:\n"
        "  - label: AC-1\n"
        "    source_text: Link expires in 24h.\n"
        "test_cases:\n"
        "  - identity: PROJ-123-TC-001\n"
        "    category: positive\n"
        "    covers: [AC-1]\n"
        "    summary: A summary\n"
        "    preconditions: None\n"
        "    steps: open the page then sign in\n"
        "    expected_results: It works.\n"
        "approval:\n"
        "  status: draft\n"
        "  approved_fingerprint: null\n",
        encoding="utf-8",
    )
    with pytest.raises(DraftSchemaError) as excinfo:
        load_draft(path)
    assert "PROJ-123-TC-001" in str(excinfo.value)


def test_covers_given_as_a_bare_string_is_rejected(tmp_path):
    path = tmp_path / "PROJ-123.yaml"
    path.write_text(
        "schema_version: 1\n"
        "source_issue: PROJ-123\n"
        "criteria:\n"
        "  - label: AC-1\n"
        "    source_text: Link expires in 24h.\n"
        "test_cases:\n"
        "  - identity: PROJ-123-TC-001\n"
        "    category: positive\n"
        "    covers: AC-1\n"
        "    summary: A summary\n"
        "    preconditions: None\n"
        "    steps:\n"
        "      - Open the page.\n"
        "    expected_results: It works.\n"
        "approval:\n"
        "  status: draft\n"
        "  approved_fingerprint: null\n",
        encoding="utf-8",
    )
    with pytest.raises(DraftSchemaError) as excinfo:
        load_draft(path)
    assert "covers" in str(excinfo.value)
