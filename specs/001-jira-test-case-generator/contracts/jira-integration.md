# Contract: Jira Cloud Integration

**Feature**: `001-jira-test-case-generator` | **Date**: 2026-10-09

Jira Cloud REST API v3, HTTP Basic auth (`JIRA_EMAIL` : `JIRA_API_TOKEN`). `jira/` is the only package in this project that performs network I/O.

## Endpoints used

| Purpose | Method & path | Notes |
|---|---|---|
| Read the story | `GET /rest/api/3/issue/{key}?fields=summary,description,issuelinks,project,{ac_field}` | `description` is ADF |
| Create-metadata check | `GET /rest/api/3/issue/createmeta?projectKeys={p}&issuetypeNames={t}` | Pre-flight (FR-024) |
| List link types | `GET /rest/api/3/issueLinkType` | Pre-flight (FR-024) |
| Create a test case issue | `POST /rest/api/3/issue` | Description built as ADF |
| Update a test case issue | `PUT /rest/api/3/issue/{key}` | In-place update (FR-038) |
| Link to the story | `POST /rest/api/3/issueLink` | Configured link type |
| Read the fingerprint | `GET /rest/api/3/issue/{key}/properties/com.tcgen.testcase` | 404 means not the tool's issue |
| Write the fingerprint | `PUT /rest/api/3/issue/{key}/properties/com.tcgen.testcase` | On create and on every update |
| Find by identity | `GET /rest/api/3/search/jql?jql=labels%3D"tcgen-id-..."` | Ambiguous-create check only (FR-053) |
| Verify credentials | `GET /rest/api/3/myself` | `doctor` step 2 |

## Identity and fingerprint storage

Every issue the tool creates carries both:

```text
labels:  [ "tcgen-id-proj-123-tc-001" ]        # lowercased; JQL-searchable
property com.tcgen.testcase:
  { "identity": "PROJ-123-TC-001",
    "content_fingerprint": "9f2b...",
    "source_issue": "PROJ-123",
    "generated_at": "2026-10-09T14:31:08Z",
    "tool_version": "0.1.0" }
```

Both exist because the requirements need two different things: the label is searchable, which is the only way to resolve an ambiguous create before retrying it (FR-053); the property holds a full-length hash without putting noise in front of human readers (FR-040). Neither alone suffices — see [plan.md](../plan.md) §Complexity Tracking.

**The property is authoritative.** A linked issue with no `com.tcgen.testcase` property is not this tool's, and is never matched, claimed, modified, or counted (FR-026c). Matching by summary or wording is forbidden.

**No local state.** Everything needed to resume, deduplicate, or detect a conflict is read back from Jira, which is what makes re-runs correct from another machine or after `drafts/` is deleted (FR-026b).

## Discovering what is already published

```text
GET the story with issuelinks
  └─ for each linked issue:
       GET its com.tcgen.testcase property
         ├─ 404        -> not ours; ignore entirely
         └─ present    -> map identity -> (issue key, stored fingerprint, link present)
```

Then per test case, derive a `PublishDecision` ([data-model.md](../data-model.md)) from the draft content, the issue's current content, the stored fingerprint, and whether the link exists. A recorded issue that returns 404 is `recreate` (FR-028).

## Conflict detection

Rebuild the issue's content from its current fields, normalize it the same way the draft is normalized, and hash it. Compare to the stored `content_fingerprint`:

- **equal** → nobody has touched it; safe to leave or update;
- **differs** → a person edited it in Jira; **conflict**, change nothing, report the differing fields (FR-039).

The `updated` timestamp is deliberately **not** used: automations, workflow transitions, and comments all bump it and would produce phantom conflicts.

## Error classification

The retry policy is only coherent if this mapping lives in one place (`errors.py`).

| Class | Triggers | Handling |
|---|---|---|
| `TransientError` | 429, 502, 503, 504, connection/read timeouts | Retry with backoff (below) |
| `PermanentError` | 400, 401, 403, 404, 405, 409; error bodies naming a field, issue type, or permission problem | Never retried; reported immediately with its reason (FR-052) |
| `UserError` | Bad issue key, missing setting, unreadable story | Reported before any write; no retry |

## Retry and backoff

- **Honour `Retry-After`** when present (seconds or HTTP date) — the server has stated the interval, so guessing is both wrong and likely to deepen the throttle (FR-051).
- Otherwise exponential backoff from 1s, doubling, with jitter, each wait capped at 30s.
- **5 attempts** per request. On exhaustion the run stops and reports which test cases were published and which were not, resumable (FR-054).
- Retried test cases are named in the report (FR-055).

### The ambiguous create

A create that times out may have succeeded. Before retrying:

```text
GET /rest/api/3/search/jql?jql=labels="tcgen-id-proj-123-tc-001"
  ├─ a hit  -> adopt that issue; ensure its property and link exist; do NOT create again
  └─ empty  -> safe to retry the create
```

This is the one path where a retry could otherwise breach the no-duplicates guarantee (FR-053, SC-020). Jira's create endpoint offers no idempotency key, which is precisely why the searchable label exists.

> Note: JQL indexing is near-real-time but not instantaneous. The lookup should allow a brief settle delay before concluding "empty", so a create that landed milliseconds earlier is not missed. This is a known race, bounded by the backoff wait already being observed.

## Issue content mapping

| Test case field | Jira destination |
|---|---|
| `summary` | `fields.summary`, prefixed with the identity-free story context |
| `preconditions`, `steps`, `expected_results` | `fields.description` as ADF — a heading per section, steps as an ordered list |
| `category`, `covers` | Rendered in the description so a reader sees the traceability without the tool |
| `identity` | `labels` entry **and** the property |
| issue type | `JIRA_TEST_ISSUE_TYPE`, default `Task` |
| project | `JIRA_PROJECT_KEY`, default the story's project |

## ADF handling

- **Reading**: walk the node tree collecting text from paragraphs, headings, list items, and table cells. Record whether non-text nodes (images, media, macros) were present, and surface that as a draft warning.
- **Writing**: build only the node types a test case needs — `heading`, `paragraph`, `orderedList`, `listItem`, `text`.

Contract tests assert both directions against **recorded real payloads**, not hand-written ones, because every silent failure mode in this layer is a payload-shape assumption.

## Secret handling

The token is registered as a redacted secret at config load and scrubbed centrally by the log formatter, so no call site can leak it by omission (FR-034). `--debug` logs method, path, status, attempt number, and wait duration — **never** request bodies or headers, since `Authorization` lives in the headers.
