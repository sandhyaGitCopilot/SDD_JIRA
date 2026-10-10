# Phase 0 Research: Jira Test Case Generator

**Feature**: `001-jira-test-case-generator` | **Date**: 2026-10-09

Every `NEEDS CLARIFICATION` from the Technical Context is resolved below. Decisions that depend on the engineer's own Jira site — rather than on anything this repository controls — are called out at the end as live-site checks for implementation, not as open questions.

---

## 1. Language and runtime

**Decision**: Python 3.11+, packaged as `src/jira_testgen/` with a `pyproject.toml` and a console entry point.

**Rationale**: The repository already standardises on Python for its own tooling (`.specify/scripts/python/`, `init-options.json` with `"script": "py"`), so there is no new toolchain for a contributor to install. 3.11 is the floor for `tomllib` and modern `typing` without back-compat shims. A CLI in Python also keeps the Claude Code skill trivial — it shells out to subcommands and reads their output.

**Alternatives considered**: Node/TypeScript (better JSON ergonomics, but a second toolchain in a Python repo); a shell script (cannot do the YAML parsing, hashing, and error classification this spec needs); a Jira plugin or Forge app (would require deployment and admin consent, and the spec is explicit that this runs locally with the engineer's own credentials).

---

## 2. Jira API version and rich-text handling

**Decision**: Jira Cloud REST API **v3**, with a small in-repo Atlassian Document Format (ADF) helper — a builder for issue descriptions and a text extractor for reading stories.

**Rationale**: v3 is the current Cloud API and the one Atlassian documents for new work. Its cost is that `description` is ADF (a nested JSON document) rather than a string, so the tool needs to both read it and produce it. The reading side only needs to walk the node tree collecting text from paragraphs, headings, list items, and table cells — roughly 60 lines. The writing side only needs the handful of node types a test case uses: headings, paragraphs, and ordered lists.

**Alternatives considered**: API **v2**, where `description` is a plain wiki-markup string and no ADF work is needed at all. Rejected because it is the legacy interface and building a new tool on it trades a one-off 100-line helper for a migration later. Also considered a third-party ADF library — rejected as a dependency out of proportion to the handful of node types involved.

**Consequence for tasks**: `jira/adf.py` is a prerequisite for both story retrieval and issue creation, so it should be built and unit-tested early, against recorded real ADF payloads rather than hand-written ones.

---

## 3. Authentication and configuration

**Decision**: HTTP Basic auth with `JIRA_EMAIL` as the username and `JIRA_API_TOKEN` as the password, loaded from `.env` via `python-dotenv`. Settings and their defaults:

| Setting | Required | Default when absent |
|---|---|---|
| `JIRA_BASE_URL` | yes | — (must be an `https://` URL; trailing slash tolerated) |
| `JIRA_EMAIL` | yes | — (must look like an address) |
| `JIRA_API_TOKEN` | yes | — (never echoed, never logged) |
| `JIRA_PROJECT_KEY` | no | the source story's own project (FR-035 reports this) |
| `JIRA_TEST_ISSUE_TYPE` | no | `Task` |
| `JIRA_LINK_TYPE` | no | `Relates` |
| `JIRA_AC_FIELD` | no | unset — criteria then come from the description section |

**Rationale**: Basic auth with an API token is the documented mechanism for Jira Cloud scripts and needs no OAuth dance or app registration, which keeps SC-009's "copy the example, fill in three values" promise intact. `Task` is the default issue type because a dedicated `Test` type exists only on sites with a test-management app installed; defaulting to `Test` would fail on most sites, and FR-035 requires reporting whichever default was used. `Relates` is the one link type present in a default Jira configuration.

**Alternatives considered**: OAuth 2.0 (correct for a multi-user service, disproportionate for a local single-user tool); reading credentials from the OS keychain (better secret hygiene, but the spec explicitly specifies `.env` and an example file); defaulting `JIRA_TEST_ISSUE_TYPE` to `Test` (rejected above).

---

## 4. Draft file format

**Decision**: One **YAML** file per story at `drafts/<ISSUE-KEY>.yaml`, with `drafts/` gitignored and a `.bak` sibling retained on replacement.

**Rationale**: FR-017 requires refusing a structurally invalid draft and naming the offending test case, and FR-045 requires a machine-comparable record of approved content inside the file. Both need a format with real structure. YAML keeps that while staying hand-editable: block scalars (`|`) let multi-line steps and expected results be typed naturally, and comments can carry instructions to the reviewer. One file per story matches the spec's "single current draft per story" assumption.

**Alternatives considered**: **Markdown**, which reads better and was the tempting choice for a document a QA engineer reviews — rejected because round-tripping free-form prose back into structured test cases is unreliable, and a reviewer's ordinary edit (an extra blank line, a renumbered step) can change how it parses, which would make FR-017 and FR-043 behave erratically. **JSON** — rejected as unpleasant to hand-edit, with no comments and no multi-line strings. **Markdown front matter plus prose body** — rejected as the worst of both: the structured part is validated and the part being edited is not.

**Consequence for tasks**: since the engineer reviews YAML rather than a document, `prepare` should emit a header comment explaining the file's shape, where to set the approval marker, and that deleting a test case is how to reject it.

---

## 5. How a published test case is recognised across runs

**Decision**: Two markers on every created issue:

- a **label** `tcgen-id-<ISSUE-KEY>-TC-<NNN>` (lowercased), which is the test case identity and is searchable with JQL `labels = "..."`;
- a **Jira issue property** under key `com.tcgen.testcase`, holding JSON: `{identity, content_fingerprint, source_issue, generated_at, tool_version}`.

The property is authoritative. An issue linked to the story with neither marker is never claimed, matched, or modified (FR-026c).

**Rationale**: These two requirements pull in opposite directions. FR-053 needs the identity to be *findable* before retrying an ambiguous create — which means JQL, which means a label, since issue properties are not JQL-searchable. FR-040 needs a fingerprint of arbitrary length stored without disfiguring the issue for human readers — which means a property, since labels cannot hold a hash cleanly and would be visible noise. Using both costs one extra request per created issue and satisfies each requirement with the mechanism built for it.

**Alternatives considered**: **Identity in the issue summary** as a prefix — rejected because it is human-visible clutter and a person editing the summary would destroy identity. **A local ledger file** — rejected outright by FR-026b. **A custom field** — rejected because it would require Jira admin rights to create, breaking SC-009's zero-admin setup. **Fingerprint in a label** — rejected: Jira labels disallow spaces and are length-capped, and a 64-character hash in the label list is hostile to readers.

---

## 6. Approval marker and the content hash

**Decision**: The draft carries an `approval` block:

```yaml
approval:
  status: draft        # or: approved
  approved_fingerprint: null   # sha256 over the normalized content block, set by the engineer's approval
```

`validate` and `publish` recompute a fingerprint over the **content** region only — the `criteria` and `test_cases` keys — explicitly excluding the `approval` block. Publishing proceeds only when `status: approved` **and** the recomputed fingerprint equals `approved_fingerprint`. A mismatch means the draft was edited after approval: publish refuses and rewrites `status` back to `draft` (FR-046).

**Rationale**: This is the only arrangement that satisfies FR-043 and FR-044 together. Approval must be voided by a content edit, yet setting the marker is itself a file edit — so the hash must not cover the marker. Scoping the hash to the content keys makes "approving does not void its own approval" true by construction rather than by careful handling.

**The engineer never types a hash.** They set `status: approved` and run `publish`; on first sight of an approved draft with a null fingerprint, the tool fills it in from the current content and proceeds. From then on the recorded value is the baseline, so any later edit is detected. This keeps the approval action a one-word change.

**Alternatives considered**: File modification times (unreliable across editors, syncs, and checkouts); a separate sidecar state file (defeats the point of keeping review state with the thing being reviewed, and invites the two to drift); hashing the whole file (would make approval void itself).

---

## 7. Criteria extraction and normalization

**Decision**: Resolution order per FR-002 — `JIRA_AC_FIELD` if set, otherwise a labelled section in the description. Section detection looks for a heading or bolded line matching `acceptance criteria` case-insensitively, and takes the list items or non-empty lines that follow until the next heading. Each criterion keeps its exact source text (FR-003) alongside a normalized form used only for comparison.

Normalization for comparison (FR-057): strip ADF markup to text, collapse all whitespace runs to one space, trim, drop list bullets and numbering prefixes, and casefold. Formatting-only edits therefore compare equal; a reworded criterion does not.

**Rationale**: Two distinct jobs are being done, and conflating them is the trap. Display and traceability need the criterion *verbatim*. Staleness detection needs it *insensitive to reformatting*, because Jira's editor rewrites markup on unrelated edits and would otherwise block publishing constantly. Storing both, and being explicit about which is used where, keeps FR-003 and FR-057 from fighting.

**Alternatives considered**: Fuzzy or similarity-threshold matching for staleness — rejected because a threshold is unexplainable to a user ("why did 0.91 block me?") and untestable as a guarantee. Comparing the whole description — rejected: the clarification limits comparison to the criteria, so an unrelated description edit must not block a publish.

---

## 8. Retry, backoff, and the ambiguous create

**Decision**:

- Retry only `TransientError`: HTTP 429, 502, 503, 504, and connection/read timeouts.
- **Honour `Retry-After` when present** (seconds or HTTP date); otherwise exponential backoff from 1s, doubling, with jitter, capped at 30s per wait.
- **5 attempts** per request, then the run stops (FR-054) with a resumable report.
- Never retry `PermanentError`: 400, 401, 403, 404, 405, and 409, plus any Jira error body naming a field or issue-type problem.
- Before retrying a **create** whose outcome is unknown (timeout, or a connection dropped after the request was sent), first run `JQL: labels = "tcgen-id-..."`. If an issue comes back, adopt it instead of creating a second one (FR-053).

**Rationale**: `Retry-After` exists precisely so clients do not have to guess, and Atlassian returns it on rate-limit responses; guessing an interval when the server has stated one is how a tool gets throttled harder. The attempt cap keeps a throttled run from hanging indefinitely while staying generous enough to ride out a burst limit. The ambiguous-create check is the one place where a retry could otherwise violate the no-duplicates guarantee, and it is cheap: one search, only on the uncertain path.

**Alternatives considered**: Unbounded retry (a hung run is worse than a reported stop); fixed-interval retry (ignores server guidance, and synchronises badly with other clients); an idempotency key on create — ideal in principle, but Jira's create-issue endpoint offers no such header, which is exactly why the label search exists.

---

## 9. Conflict detection on already-published issues

**Decision**: On a re-run, for each test case with a published issue: read the issue's current fields, rebuild the normalized content, and hash it. Compare against the `content_fingerprint` stored in the issue property.

| Stored fingerprint vs issue | Draft vs stored | Outcome |
|---|---|---|
| matches | unchanged | leave untouched (FR-029) |
| matches | changed | update in place, refresh fingerprint (FR-038, FR-040) |
| differs | unchanged | **conflict** — someone edited it in Jira (FR-039) |
| differs | changed | **conflict** — both sides moved (FR-039) |
| property missing | any | not the tool's issue; never claimed (FR-026c) |

Conflicts are reported with the issue key and the differing fields, change nothing, and are re-evaluated from scratch on the next run (FR-041), so resolving either side clears them.

**Rationale**: Comparing the issue against the fingerprint the tool *wrote* is what distinguishes "nobody touched it" from "a person edited it" without needing history, audit logs, or a changelog query. Deriving the verdict from two independent comparisons keeps the four outcomes mutually exclusive and directly testable.

**Alternatives considered**: Jira's `updated` timestamp — rejected because automations, workflow transitions, and comment activity all bump it, producing phantom conflicts. The issue changelog — rejected as an extra paginated request per issue to answer a question a stored hash already answers.

---

## 10. Secret redaction

**Decision**: Register the token once at config load in a redaction registry, and install a logging `Formatter` that scrubs every registered secret from the formatted message, its arguments, and any attached exception text. Report rendering and error printing route through the same scrubber. A unit test asserts the token appears in zero bytes of output across a deliberately failing run of every subcommand.

**Rationale**: FR-034 is absolute, and anything requiring the author of a future log line to remember to redact will eventually fail. Centralising at the formatter makes the safe path the default, and the "token appears nowhere" test is the only form of this requirement that is actually verifiable.

**Alternatives considered**: Redacting at each call site (fails on the first new log line); logging only pre-approved fields (safer still, but it makes diagnostic logging so awkward that people route around it); trusting that the token is never passed to a logger (not a control).

---

## 11. Replacing a draft file safely

**Decision**: Write to a temporary file in the same directory, `fsync`, move the existing file to `<name>.yaml.bak` (replacing any previous backup), then `os.replace` the temporary into place. `os.replace` is atomic on both POSIX and Windows.

**Rationale**: FR-050 requires naming the file about to be replaced and keeping the previous version recoverable. Doing this in the wrong order — or with `os.rename` onto an existing path, which fails on Windows — risks losing a reviewed draft at exactly the moment the spec promises it is safe. The primary development platform here is Windows, so this is not a theoretical concern.

**Alternatives considered**: Timestamped backups accumulating in `drafts/` (clutter, and no requirement asks for history); writing in place (a crash mid-write destroys the reviewed draft); relying on the engineer's VCS (`drafts/` is gitignored, so there is nothing to recover from).

---

## 12. Observability

**Decision**: One log stream to stderr at `WARNING` by default, `--verbose` for `INFO`, `--debug` for request/response metadata — method, path, status, attempt number, and wait duration, never bodies or headers. No file logging unless `--log-file` is passed. The Run Report is separate from logging and is the user-facing artifact, available as text or `--json`.

**Rationale**: This was the one category both clarification passes deferred, and it is a plan-level decision rather than a spec ambiguity. The risky half is already a requirement — User Story 3 scenario 4 forbids the token appearing in any log — and §10 handles it. Keeping logs off stdout leaves stdout clean for the report, so `--json` can be piped.

**Alternatives considered**: Structured JSON logs by default (useful for a service, noise for a local CLI); logging request bodies at `--debug` (would put story content and potentially an `Authorization` header into a file a user might paste into a bug report).

---

## 13. Testing strategy

**Decision**: Three layers.

- **Unit** — the pure logic: criteria extraction, normalization, fingerprinting, identity minting and parsing, error classification, limit thresholds, redaction. No network, no mocks.
- **Contract** — recorded real Jira payloads (ADF descriptions, issue-link structures, 429 responses with `Retry-After`, property reads) asserted against the parsers and builders, so an API drift fails loudly rather than silently.
- **Integration** — whole flows against a mocked Jira via `responses`: refuse-unapproved, publish-then-republish (zero duplicates), resume-after-partial-failure, conflict detection, stale-criteria refusal and override, regeneration identity reuse, ambiguous-create adoption.

One optional live smoke test runs only when real credentials are present, and is skipped otherwise.

**Rationale**: The spec's guarantees are mostly about *sequences* of runs — publish, edit, republish — so integration tests over a mocked Jira are where the real risk lives. Contract tests exist because every silent failure mode in this tool is a payload-shape assumption.

**Alternatives considered**: Testing only against a live Jira instance (slow, requires credentials in CI, and cannot simulate 429 or a timeout on demand); mocking at the `requests` level by hand (`responses` already does it).

---

## 14. Generation orchestration

**Decision**: No `generate` subcommand. The CLI exposes `doctor`, `prepare`, `validate`, and `publish`. `prepare` writes a draft scaffold containing the criteria, the assigned identities, and empty test case slots. The Claude Code skill at `.claude/skills/jira-testgen/SKILL.md` runs `prepare`, reads the scaffold, writes the test case content into the YAML, reports coverage to the engineer, and then stops for review. After approval the skill (or the engineer) runs `publish`.

**Rationale**: This is what lets FR-036 and FR-037 both hold. Generation genuinely requires a session, and there is no code path that could fake it — so running it without one cannot silently degrade. Everything else is ordinary code that runs headless, which is what makes the integration tests above possible at all.

**Alternatives considered**: A `generate` subcommand that shells out to a Claude binary (brittle, and reintroduces the "no session" failure mode inside the CLI); a rule-based generator behind a flag (explicitly ruled out by clarification 1); having the skill write the whole draft including criteria extraction (would move deterministic, testable logic into a prompt).

---

## Live-site checks for implementation

These depend on the engineer's Jira site, not on anything decided here. `doctor` exists to check them and report in the spec's naming-the-setting style, rather than failing mid-publish.

1. **Does `JIRA_TEST_ISSUE_TYPE` exist and is it creatable in the target project?** Verified via the create-metadata endpoint before any issue is created (FR-024).
2. **Does `JIRA_LINK_TYPE` exist on this site?** Verified against the issue-link-types endpoint (FR-024). `Relates` is near-universal but not guaranteed.
3. **What is the `customfield_*` id for acceptance criteria, if the team uses one?** Site-specific; the engineer sets `JIRA_AC_FIELD`, and `doctor` confirms the field exists and is readable on a sample issue. The tool never guesses at an unnamed field (clarification 3).
4. **Are issue properties writable with the engineer's permissions?** Writing a property needs edit permission on the issue the tool itself just created, so this normally follows from create permission — but `doctor` should confirm it, because the fingerprint mechanism is load-bearing for every idempotency guarantee.
