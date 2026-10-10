"""T025: fingerprint canonicalization (FR-043, FR-044, FR-045).

Two properties carry the approval gate:

1. The `approval` block is excluded, so approving a draft cannot void its own
   approval (FR-044). This is the one that would be a silent disaster.
2. Cosmetic YAML changes do not void an approval, but any content change does.

NOTE ON SCOPE: T025 described the canonical form as "trailing whitespace
stripped, line endings normalized" while also requiring that *reflowing a block
scalar* leave the hash unchanged. Those two cannot both hold -- reflowing moves
newlines, which the described rules preserve. The stated outcome is the stronger
guarantee, so the implementation collapses all internal whitespace runs instead,
and the tests below pin that behaviour. contracts/draft-file.md should be
updated to say so.
"""

from jira_testgen.draft.fingerprint import content_fingerprint

BASE = {
    "criteria": [
        {"label": "AC-1", "source_text": "Reset link expires after 24 hours."},
    ],
    "test_cases": [
        {
            "identity": "PROJ-123-TC-001",
            "category": "positive",
            "covers": ["AC-1"],
            "summary": "Reset link works before expiry",
            "preconditions": "A reset link was issued 1 hour ago.",
            "steps": ["Open the reset link.", "Set a new password."],
            "expected_results": "The password is changed.",
        }
    ],
    "approval": {"status": "draft", "approved_fingerprint": None},
}


def _with(**overrides):
    import copy

    doc = copy.deepcopy(BASE)
    doc.update(overrides)
    return doc


def test_fingerprint_is_stable_for_identical_content():
    assert content_fingerprint(BASE) == content_fingerprint(_with())


def test_fingerprint_is_a_sha256_hex_digest():
    value = content_fingerprint(BASE)
    assert len(value) == 64
    assert all(c in "0123456789abcdef" for c in value)


def test_approval_block_is_excluded():
    # FR-044. If this fails, setting `status: approved` voids the approval it
    # just granted and the tool is unusable.
    approved = _with(approval={"status": "approved", "approved_fingerprint": "whatever"})
    assert content_fingerprint(approved) == content_fingerprint(BASE)


def test_provenance_and_warnings_are_excluded():
    noisy = _with(
        warnings=["something"],
        generated_at="2026-10-09T00:00:00Z",
        tool_version="9.9.9",
        source_summary="a different summary",
    )
    assert content_fingerprint(noisy) == content_fingerprint(BASE)


def test_mapping_key_order_does_not_matter():
    reordered = _with(
        test_cases=[
            {
                "expected_results": "The password is changed.",
                "steps": ["Open the reset link.", "Set a new password."],
                "preconditions": "A reset link was issued 1 hour ago.",
                "summary": "Reset link works before expiry",
                "covers": ["AC-1"],
                "category": "positive",
                "identity": "PROJ-123-TC-001",
            }
        ]
    )
    assert content_fingerprint(reordered) == content_fingerprint(BASE)


def test_reflowing_a_block_scalar_does_not_change_the_hash():
    reflowed = _with(
        test_cases=[
            dict(
                BASE["test_cases"][0],
                expected_results="The password\nis   changed.",
            )
        ]
    )
    assert content_fingerprint(reflowed) == content_fingerprint(BASE)


def test_trailing_whitespace_does_not_change_the_hash():
    padded = _with(
        test_cases=[dict(BASE["test_cases"][0], summary="Reset link works before expiry   ")]
    )
    assert content_fingerprint(padded) == content_fingerprint(BASE)


def test_changing_a_word_of_content_changes_the_hash():
    edited = _with(
        test_cases=[dict(BASE["test_cases"][0], expected_results="The password is NOT changed.")]
    )
    assert content_fingerprint(edited) != content_fingerprint(BASE)


def test_adding_a_step_changes_the_hash():
    edited = _with(
        test_cases=[
            dict(
                BASE["test_cases"][0],
                steps=["Open the reset link.", "Set a new password.", "Sign in."],
            )
        ]
    )
    assert content_fingerprint(edited) != content_fingerprint(BASE)


def test_reordering_steps_changes_the_hash():
    # Step order is semantic in a test case, unlike mapping key order.
    edited = _with(
        test_cases=[
            dict(BASE["test_cases"][0], steps=["Set a new password.", "Open the reset link."])
        ]
    )
    assert content_fingerprint(edited) != content_fingerprint(BASE)


def test_deleting_a_test_case_changes_the_hash():
    assert content_fingerprint(_with(test_cases=[])) != content_fingerprint(BASE)


def test_editing_a_criterion_changes_the_hash():
    edited = _with(
        criteria=[{"label": "AC-1", "source_text": "Reset link expires after 48 hours."}]
    )
    assert content_fingerprint(edited) != content_fingerprint(BASE)


def test_case_changes_in_content_are_significant():
    # Unlike criteria comparison, draft content is compared case-sensitively:
    # an engineer who fixes capitalisation has edited the test case.
    edited = _with(test_cases=[dict(BASE["test_cases"][0], summary="reset link works")])
    assert content_fingerprint(edited) != content_fingerprint(BASE)
