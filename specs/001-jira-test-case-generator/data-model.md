# Phase 1 Data Model: Jira Test Case Generator

**Feature**: `001-jira-test-case-generator` | **Date**: 2026-10-09

Entities from [spec.md](./spec.md) §Key Entities, with the fields, validation rules, and state transitions the requirements imply. Nothing here is persisted to a database — `DraftSet` lives in a YAML file, `PublicationMarker` lives on the Jira issue, and the rest exist only during a run.

---

## SourceStory

The Jira issue the engineer names. Read-only except for gaining inbound links.

| Field | Type | Notes |
|---|---|---|
| `key` | str | e.g. `PROJ-123`. Validated against `^[A-Z][A-Z0-9_]*-\d+$` before any request (fails fast on a typo). |
| `project_key` | str | From the issue; the publishing target when `JIRA_PROJECT_KEY` is unset. |
| `summary` | str | |
| `description_text` | str | ADF flattened to text. |
| `description_had_non_text` | bool | True when images, attachments, macros, or tables were present. Surfaced as a draft warning. |
| `criteria` | list[AcceptanceCriterion] | May be empty — which is a stop, not a degraded run (FR-005). |
| `criteria_source` | enum | `field` \| `description` — reported in output and draft (FR-002a). |

**Validation**: retrieval fails with a `UserError` naming the key when the issue is absent or unreadable (FR-004). An empty `criteria` list stops the run, naming both places searched (FR-005).

---

## AcceptanceCriterion

| Field | Type | Notes |
|---|---|---|
| `ordinal` | int | 1-based, position within the source. |
| `label` | str | `AC-1`, `AC-2`, … Used for traceability in drafts and issues. |
| `source_text` | str | **Verbatim** (FR-003). Never normalized in place. |
| `normalized` | str | Comparison form only: markup stripped, whitespace collapsed, bullets and numbering removed, casefolded (FR-057). |

**Relationship**: each criterion must be covered by ≥1 `TestCase` (FR-008), with at least one *positive* case (FR-007).

**Invariant**: `source_text` is what a human reads; `normalized` is what staleness detection compares. Code must never substitute one for the other.

---

## TestCase

| Field | Type | Notes |
|---|---|---|
| `identity` | str | `<ISSUE-KEY>-TC-<NNN>`, zero-padded to 3. Minted at draft time, **independent of wording** (FR-025). Immutable once assigned. |
| `summary` | str | Non-empty. |
| `preconditions` | str | Non-empty; may be a single line such as `None`. |
| `steps` | list[str] | ≥1 entry, each non-empty (FR-006). |
| `expected_results` | str | Non-empty (FR-006). |
| `category` | enum | `positive` \| `negative` \| `boundary` \| `edge` (FR-061). |
| `covers` | list[str] | ≥1 criterion label, each matching a known `AcceptanceCriterion.label` (FR-061). |

**Validation** (all enforced by `validate`, each naming the offending identity per FR-017):

- every required field present and non-empty;
- `category` within the enum;
- every `covers` entry resolves to a real criterion;
- identities unique within the draft, and well-formed;
- identity not silently changed from the scaffold.

**Deletion is rejection** (FR-014): removing a test case from the draft means it is never created. A test case already published whose draft entry is deleted leaves its Jira issue in place and is reported as no longer in the draft.

---

## DraftSet

One YAML file per story at `drafts/<ISSUE-KEY>.yaml`. Full schema in [contracts/draft-file.md](./contracts/draft-file.md).

| Field | Type | Notes |
|---|---|---|
| `schema_version` | int | Guards against a future format change breaking an old draft. |
| `source_issue` | str | The story key. |
| `source_summary` | str | For the reviewer's context. |
| `criteria_source` | enum | `field` \| `description`. |
| `criteria` | list[AcceptanceCriterion] | With `source_text` and `label`; part of the hashed content region. |
| `test_cases` | list[TestCase] | Part of the hashed content region. |
| `warnings` | list[str] | Non-text content present, set size above 25, criteria unparseable, etc. |
| `approval` | ApprovalState | **Excluded** from the hashed region (FR-044). |
| `generated_at`, `tool_version` | str | Provenance. |

### ApprovalState

| Field | Type | Notes |
|---|---|---|
| `status` | enum | `draft` \| `approved`. The engineer edits this by hand — the whole approval action (FR-015). |
| `approved_fingerprint` | str \| null | sha256 of the content region at approval. Filled by the tool on first approved run; never typed by hand. |

### State transitions

```text
  (no file)
      │  prepare
      ▼
  scaffold ── session fills test cases ──▶ draft (status: draft)
      │                                       │
      │                                       │ engineer sets status: approved
      │                                       ▼
      │                                  approved (fingerprint null)
      │                                       │
      │                                       │ publish: fingerprint recorded, publishing proceeds
      │                                       ▼
      │                                  approved (fingerprint set)
      │                                    │        │
      │             content edited ────────┘        └──── unchanged ──▶ publish allowed
      │                     │
      │                     ▼
      │              status reset to draft, publish refused (FR-043, FR-046)
      │
      └── prepare again ──▶ refused unless --regenerate (FR-047);
                            on --regenerate: .bak written, fresh scaffold,
                            status: draft, published identities reused (FR-048, FR-049, FR-050)
```

**Invariant**: `publish` writes nothing to Jira unless `status == approved` **and** the recomputed content fingerprint equals `approved_fingerprint`.

---

## PublicationMarker

Stored **on the Jira issue**, never locally (FR-026b). Two parts:

| Part | Where | Content |
|---|---|---|
| Identity label | issue `labels` | `tcgen-id-<issue-key>-tc-<nnn>` (lowercased). JQL-searchable — this is what makes the ambiguous-create check possible (FR-053). |
| Property | issue property `com.tcgen.testcase` | `{identity, content_fingerprint, source_issue, generated_at, tool_version}` |

**Authority**: the property is authoritative. An issue linked to the story carrying neither is **not the tool's**, and is never matched, claimed, modified, or counted as a published test case (FR-026c).

**Fingerprint lifecycle**: written on create, refreshed on every update (FR-040). It always reflects *what the tool last wrote*, which is the entire basis of conflict detection.

---

## PublishDecision

Derived per test case at publish time; not persisted. The four-way comparison from [research.md](./research.md) §9:

| `decision` | Meaning | Action |
|---|---|---|
| `create` | No published issue for this identity | Create, link, write marker |
| `unchanged` | Published, issue matches its fingerprint, draft matches too | Nothing (FR-029) |
| `update` | Published, issue matches its fingerprint, draft changed | Update fields, refresh fingerprint (FR-038) |
| `conflict` | Published, issue no longer matches its fingerprint | Nothing; report the differing fields (FR-039) |
| `relink` | Issue exists and matches, but the link to the story is missing | Create the link only (FR-023, FR-027) |
| `recreate` | Recorded issue no longer exists in Jira | Create afresh (FR-028) |
| `orphaned_draft` | Published issue whose draft entry was deleted | Leave the issue; report it |

**Invariant**: decisions are mutually exclusive and derived purely from (draft content, issue content, stored fingerprint, link presence) — no run history, no local state, no timestamps.

---

## Configuration

| Field | Required | Default | Validation |
|---|---|---|---|
| `base_url` | yes | — | `https://` URL; trailing slash normalized |
| `email` | yes | — | contains `@` |
| `api_token` | yes | — | non-empty; **registered as a redacted secret at load** (FR-034) |
| `project_key` | no | source story's project | `^[A-Z][A-Z0-9_]*$` |
| `test_issue_type` | no | `Task` | exists and is creatable in the target project (`doctor`, FR-024) |
| `link_type` | no | `Relates` | exists on the site (`doctor`, FR-024) |
| `ac_field` | no | unset | `^customfield_\d+$` when set |

**Validation ordering matters** (FR-032, FR-033): shape is checked *before* any network call, so a missing or malformed setting is reported by name without contacting Jira. Only then are credentials exercised, so "this setting looks wrong" stays distinguishable from "Jira rejected these credentials".

**Invariant**: `api_token` has no `__repr__`, no `__str__`, and no serialization path that yields its value. It exists only as an argument to the auth header.

---

## RunReport

Assembled per run; rendered as text or `--json`. Full shape in [contracts/cli.md](./contracts/cli.md).

| Field | Type | Notes |
|---|---|---|
| `source_issue` | str | |
| `outcomes` | list[Outcome] | One per test case: `identity`, `decision`, `issue_key`, `reason`, `retried` (count), `fields_differing` |
| `defaults_used` | dict | Which optional settings fell back, and to what (FR-035) |
| `criteria_source` | enum | `field` \| `description` (FR-002a) |
| `warnings` | list[str] | Including the >25 size warning (FR-064) |
| `overrides_used` | dict | `stale_criteria` with the changed criteria (FR-060); `set_size` with the count published (FR-068) |
| `not_attempted` | list[str] | Identities left when a run stopped on exhausted retries (FR-054) |
| `verdict` | enum | `success` \| `partial` |

**Invariant**: `verdict` is `partial` whenever any outcome is `conflict` or `failed`, or `not_attempted` is non-empty (FR-022, FR-042). Every test case in the approved set appears in `outcomes` exactly once (FR-021) — the report is complete by construction, so nothing created can go unaccounted for.
