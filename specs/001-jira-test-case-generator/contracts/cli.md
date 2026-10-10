# Contract: Command-Line Interface

**Feature**: `001-jira-test-case-generator` | **Date**: 2026-10-09

The CLI is this project's public interface. Invoked as `jira-testgen <command>` or `python -m jira_testgen <command>`.

**There is deliberately no `generate` command.** Test case content is written by the Claude Code session into the scaffold `prepare` produces (FR-036, FR-037). Every command below runs headless without a session.

## Global conventions

| Aspect | Contract |
|---|---|
| stdout | The Run Report or command result only — safe to pipe |
| stderr | Logs, warnings, errors |
| `--json` | Emits the machine-readable report on stdout instead of text |
| `--verbose` / `--debug` | Raises log level; `--debug` logs method, path, status, attempt, wait — never bodies or headers |
| `--log-file PATH` | Also writes logs to a file; the token is scrubbed there too (FR-034) |
| Secret handling | The API token appears in zero bytes of any stream, including tracebacks |

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Unexpected internal error |
| 2 | Configuration error — missing or malformed setting, named (FR-032) |
| 3 | Authentication rejected by Jira (FR-033) |
| 4 | Source issue not found or unreadable (FR-004) |
| 5 | No acceptance criteria found in either source (FR-005) |
| 6 | Draft refused — not approved, approval voided, or structurally invalid (FR-016, FR-017, FR-043) |
| 7 | Refused to replace an existing draft without `--regenerate` (FR-047) |
| 8 | Refused — acceptance criteria changed since drafting (FR-058) |
| 9 | Refused — set exceeds 100 test cases without `--allow-large` (FR-065) |
| 10 | Partially complete — some test cases failed or are in conflict (FR-022, FR-042) |
| 11 | Stopped — retries exhausted; run is resumable (FR-054) |

Distinct codes exist because each refusal has a different remedy, and the Claude Code skill branches on them rather than parsing prose.

---

## `doctor`

```text
jira-testgen doctor [--issue PROJ-123]
```

Validates configuration and the live site without writing anything.

**Checks, in order** (shape before network, per FR-032/FR-033):

1. Every required setting present and well-formed → exit 2 naming each offender.
2. Credentials accepted → exit 3 on rejection, distinguished from (1).
3. `JIRA_TEST_ISSUE_TYPE` exists and is creatable in the target project (FR-024).
4. `JIRA_LINK_TYPE` exists on this site (FR-024).
5. `JIRA_AC_FIELD`, when set, exists and is readable — on `--issue` when given.
6. Issue properties are writable (the fingerprint mechanism is load-bearing).

**Output**: each check as pass/fail, the defaults applied and their values (FR-035), and never the token.

---

## `prepare`

```text
jira-testgen prepare PROJ-123 [--regenerate] [--json]
```

Fetches the story, extracts criteria, mints identities, writes the draft scaffold. **Touches nothing in Jira.**

**Behaviour**:

1. Validate the issue key shape, then retrieve the story → exit 4 if absent or unreadable.
2. Extract criteria from `JIRA_AC_FIELD` if set, else the labelled description section; record which (FR-002a) → exit 5 if neither yields any, naming both places searched and writing no draft.
3. If `drafts/PROJ-123.yaml` exists and `--regenerate` was not passed → exit 7, naming the file, leaving it untouched (FR-047).
4. With `--regenerate`: name the file being replaced, move it to `.bak`, and **reuse identities already published in Jira** for this story so re-publishing cannot duplicate (FR-048, FR-050). The new draft is `status: draft` (FR-049).
5. Write the scaffold: criteria with verbatim source text, identities, empty test case slots, warnings, and a header comment explaining review and approval.
6. Warn if the scaffold implies more than 25 test cases, and report when it exceeds 100 (FR-064, FR-065).

**Guarantee**: on any non-zero exit, an existing draft is byte-for-byte unchanged.

---

## `validate`

```text
jira-testgen validate PROJ-123 [--json]
```

Checks the draft without contacting Jira. Safe to run repeatedly during review.

**Checks**: schema and version; every test case's required fields, category, and `covers` resolution; identity uniqueness and well-formedness; every criterion covered by ≥1 test case with ≥1 positive (FR-007, FR-008); at least one negative and one edge case in the set (FR-063); approval state consistency.

**Output**: the criterion-to-test-case coverage map, any uncovered criteria (FR-009), set size against the thresholds, and the approval state — `draft`, `approved`, or `approval voided by edit`. Exit 6 on a structural failure, naming the offending test case identity (FR-017).

---

## `publish`

```text
jira-testgen publish PROJ-123 [--allow-large] [--allow-stale-criteria] [--json]
```

The only command that writes to Jira.

**Pre-flight, in order — nothing is created until all pass**:

1. `validate` must pass → exit 6.
2. `approval.status == approved` → else exit 6, naming the file and the marker expected (FR-016).
3. Recomputed content fingerprint equals `approved_fingerprint`; on mismatch, reset `status` to `draft` and exit 6 (FR-043, FR-046). When `approved_fingerprint` is null, record it from the current content and continue.
4. Target project, issue type, and link type usable (FR-024).
5. Re-read the story's criteria and compare normalized forms against the draft; on substantive change exit 8, naming the changed criteria, unless `--allow-stale-criteria` (FR-056 – FR-059). Formatting-only differences never block (FR-057).
6. Set size ≤ 100 unless `--allow-large` → else exit 9 (FR-065).

**Publishing loop**: read the story's linked issues, identify the tool's own by label and property, derive a `PublishDecision` per test case ([data-model.md](../data-model.md)), then act. Permanent per-test-case failures are reported and the loop continues (FR-020); exhausted retries against a Jira-wide condition stop the run with a resumable report (FR-054).

**Flags are per-run only.** Neither override can be set in `.env` (FR-067), and each is recorded in the report when used (FR-060, FR-068).

---

## Run Report shape (`--json`)

```json
{
  "source_issue": "PROJ-123",
  "criteria_source": "description",
  "verdict": "partial",
  "defaults_used": { "test_issue_type": "Task", "link_type": "Relates", "project_key": "PROJ" },
  "warnings": ["Set contains 28 test cases; review may be slow."],
  "overrides_used": { "stale_criteria": null, "set_size": null },
  "outcomes": [
    { "identity": "PROJ-123-TC-001", "decision": "created",   "issue_key": "PROJ-456", "retried": 0 },
    { "identity": "PROJ-123-TC-002", "decision": "unchanged", "issue_key": "PROJ-457", "retried": 0 },
    { "identity": "PROJ-123-TC-003", "decision": "updated",   "issue_key": "PROJ-458", "retried": 2 },
    { "identity": "PROJ-123-TC-004", "decision": "conflict",  "issue_key": "PROJ-459",
      "fields_differing": ["steps", "expected_results"],
      "reason": "Issue was edited in Jira after this tool last wrote it." },
    { "identity": "PROJ-123-TC-005", "decision": "failed",    "issue_key": null,
      "reason": "Issue type 'Task' rejected field 'customfield_10040'." }
  ],
  "not_attempted": [],
  "token_present_in_output": false
}
```

`token_present_in_output` is asserted false by a test that runs every subcommand to failure and scans all streams (FR-034, SC-008).

**Report completeness is a contract**: every test case in the approved set appears in `outcomes` exactly once (FR-021), and `verdict` is `partial` whenever any outcome is `conflict` or `failed` or `not_attempted` is non-empty (FR-022, FR-042).

---

## Claude Code skill contract

`.claude/skills/jira-testgen/SKILL.md` orchestrates the session-driven half:

1. Run `prepare PROJ-123`; on exit 7, report the existing draft and ask before re-running with `--regenerate`.
2. Read the scaffold; write test cases into `test_cases` — one positive per criterion, plus negative, boundary, and edge cases only where warranted, with no filler (FR-007, FR-062), ensuring at least one negative and one edge in the set (FR-063).
3. Preserve every scaffold identity exactly; never invent, renumber, or reorder them.
4. Run `validate`; fix any reported gap.
5. Report the coverage map to the engineer and **stop**, stating that approval means setting `status: approved` in the named file.
6. Only on explicit approval, run `publish` and relay the report.

The skill never edits the `approval` block on the engineer's behalf — that is the human gate the whole design protects (FR-015).
