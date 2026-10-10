# Contract: Draft File Format

**Feature**: `001-jira-test-case-generator` | **Date**: 2026-10-09

One YAML file per story at `drafts/<ISSUE-KEY>.yaml`. This is the artifact the QA engineer reviews, edits, and approves. `drafts/` is gitignored.

## Example

```yaml
# Review these test cases, then set `status: approved` below and run:
#   jira-testgen publish PROJ-123
# To reject a test case, delete its whole entry. To change one, edit it in place.
# Editing anything outside the `approval:` block after approving will void the
# approval and you will be asked to approve again.

schema_version: 1
source_issue: PROJ-123
source_summary: "Password reset via email link"
criteria_source: description        # or: field
generated_at: "2026-10-09T14:30:22Z"
tool_version: "0.1.0"

warnings:
  - "Description contained an image, which was not interpreted."

criteria:
  - label: AC-1
    source_text: "User can request a reset link with a registered email address."
  - label: AC-2
    source_text: "Reset link expires after 24 hours."

test_cases:
  - identity: PROJ-123-TC-001
    category: positive
    covers: [AC-1]
    summary: "Request reset link with a registered email address"
    preconditions: |
      A user account exists with the email address qa.user@example.com.
    steps:
      - "Open the password reset page."
      - "Enter qa.user@example.com in the email field."
      - "Select Send reset link."
    expected_results: |
      A confirmation message states that a reset link has been sent.
      The email arrives at qa.user@example.com and contains a reset link.

  - identity: PROJ-123-TC-002
    category: boundary
    covers: [AC-2]
    summary: "Reset link is still valid immediately before expiry"
    preconditions: |
      A reset link was issued 23 hours and 59 minutes ago.
    steps:
      - "Open the reset link."
      - "Enter a new valid password and confirm it."
    expected_results: |
      The password is changed and the user can sign in with the new password.

approval:
  status: draft                 # change to: approved
  approved_fingerprint: null    # filled in by the tool; do not edit
```

## Field rules

| Key | Required | Rules |
|---|---|---|
| `schema_version` | yes | Integer. A draft with an unknown version is refused rather than guessed at. |
| `source_issue` | yes | Must match the key given on the command line. |
| `criteria_source` | yes | `field` \| `description` (FR-002a). |
| `criteria[].label` | yes | `AC-<n>`, unique. |
| `criteria[].source_text` | yes | **Verbatim from Jira** (FR-003). Edits here break staleness comparison and are reported by `validate`. |
| `test_cases[].identity` | yes | `<ISSUE-KEY>-TC-<NNN>`. Minted by `prepare`; **never edit** (FR-025). |
| `test_cases[].category` | yes | `positive` \| `negative` \| `boundary` \| `edge` (FR-061). |
| `test_cases[].covers` | yes | ≥1 existing criterion label (FR-061). |
| `test_cases[].summary` | yes | Non-empty single line. |
| `test_cases[].preconditions` | yes | Non-empty; `None` is acceptable content. |
| `test_cases[].steps` | yes | ≥1 non-empty entry (FR-006). |
| `test_cases[].expected_results` | yes | Non-empty (FR-006). |
| `approval.status` | yes | `draft` \| `approved`. The engineer's one-word approval action (FR-015). |
| `approval.approved_fingerprint` | yes | sha256 hex or `null`. Written by the tool, never by hand. |

## Set-level rules

Enforced by `validate` (FR-007, FR-008, FR-063):

- every criterion covered by ≥1 test case, including ≥1 `positive`;
- ≥1 `negative` and ≥1 `edge` test case across the set;
- no filler: a category absent for a criterion needs no explanation (FR-062);
- identities unique;
- warning above 25 test cases, refusal above 100 at publish without `--allow-large`.

## The content fingerprint

The fingerprint is `sha256` over a canonical serialization of **only** the `criteria` and `test_cases` keys:

- keys sorted; `criteria` and `test_cases` in document order;
- each string stripped of trailing whitespace, line endings normalized to `\n`;
- serialized as compact JSON, UTF-8, then hashed.

**The `approval` block is excluded, as are `warnings`, `generated_at`, and `tool_version`.**

This exclusion is the mechanism behind FR-044: setting `status: approved` is itself a file edit, so if the hash covered it, approving would instantly void the approval it just granted. Scoping the hash to the content region makes that impossible by construction rather than by careful handling.

Canonicalization means cosmetic YAML changes — reflowing a block scalar, reordering mapping keys within a test case, changing indentation — do not void an approval. Changing any word of content does.

### Approval lifecycle

| State | `status` | `approved_fingerprint` | `publish` behaviour |
|---|---|---|---|
| Fresh scaffold | `draft` | `null` | Refuse, exit 6 (FR-016) |
| Reviewed, not approved | `draft` | `null` | Refuse, exit 6 |
| Just approved | `approved` | `null` | Record the fingerprint, proceed |
| Approved, untouched | `approved` | matches content | Proceed |
| Approved, then edited | `approved` | differs from content | Refuse, reset `status` to `draft`, exit 6 (FR-043, FR-046) |

The engineer never types a hash. They change one word; the tool records the baseline on the first approved run and enforces it thereafter.

## Backups

`prepare --regenerate` moves the existing file to `<ISSUE-KEY>.yaml.bak` (replacing any previous backup), then writes the new scaffold via a same-directory temporary file and `os.replace` — atomic on Windows and POSIX alike (FR-050).

Only one generation of backup is kept; no requirement asks for history, and accumulating timestamped files in a directory the engineer reviews would be clutter.

## Validation failure messages

Messages name the offending test case so a reviewer can go straight to it (FR-017):

```text
drafts/PROJ-123.yaml: PROJ-123-TC-004 has no steps (at least one is required).
drafts/PROJ-123.yaml: PROJ-123-TC-007 covers "AC-9", which is not a criterion of PROJ-123.
drafts/PROJ-123.yaml: AC-3 is not covered by any test case.
drafts/PROJ-123.yaml: AC-5 has no positive test case.
drafts/PROJ-123.yaml: set has no edge test case (at least one is required).
drafts/PROJ-123.yaml: approval was voided — content changed after approval. Set status: approved again.
```
