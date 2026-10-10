---

description: "Task list for Jira Test Case Generator"
---

# Tasks: Jira Test Case Generator

**Input**: Design documents from `/specs/001-jira-test-case-generator/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Test tasks ARE included. [research.md](./research.md) §13 commits to a three-layer strategy (unit / contract / integration), and the spec's guarantees are mostly about *sequences* of runs — publish, edit, republish — which only integration tests can verify.

**Organization**: Grouped by user story so each can be implemented, tested, and delivered independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story the task belongs to (US1–US4)

## Path Conventions

Single project per [plan.md](./plan.md): `src/jira_testgen/` and `tests/` at repository root.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project skeleton and the two files that keep credentials out of version control

- [X] T001 Create directory structure `src/jira_testgen/{draft,jira}/`, `tests/{unit,contract,integration}/`, and `drafts/` with `__init__.py` in each package per plan.md
- [X] T002 Create `pyproject.toml` declaring Python >=3.11, runtime deps `requests`, `PyYAML`, `python-dotenv`, dev deps `pytest`, `responses`, and console entry point `jira-testgen = "jira_testgen.cli:main"`
- [X] T003 [P] Create `.gitignore` containing `.env` and `drafts/` so the real configuration and draft files are never committed (FR-031)
- [X] T004 [P] Create `.env.example` with placeholder values for all seven settings: `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY`, `JIRA_TEST_ISSUE_TYPE`, `JIRA_LINK_TYPE`, `JIRA_AC_FIELD`, with optional ones commented to show their defaults (FR-031)
- [X] T005 [P] Create `ruff.toml` and `pytest.ini` configuring lint rules and test discovery under `tests/`
- [X] T006 [P] Create `src/jira_testgen/__main__.py` delegating to `cli.main()` so `python -m jira_testgen` works

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The error taxonomy, redaction, config loading, and Jira access layer that every user story builds on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

**Note on the US3 split**: config *loading* is foundational and lives here. The user-facing setup guarantees — `doctor`, precise per-setting messages, exit-code separation — are User Story 3's own phase, so US1 is not blocked waiting on them.

- [X] T007 [P] Implement error taxonomy in `src/jira_testgen/errors.py`: `TransientError` (429, 502, 503, 504, connection/read timeout), `PermanentError` (400, 401, 403, 404, 405, 409, plus bodies naming a field/issue-type/permission problem), `UserError`, each carrying a reason string (FR-051, FR-052)
- [X] T008 [P] Implement redaction registry and redacting log formatter in `src/jira_testgen/logging_setup.py`: secrets registered once, scrubbed from every record's message, args, and attached exception text; stderr stream, `WARNING` default, `--verbose`/`--debug` levels, optional `--log-file` (FR-034)
- [X] T009 [P] Write unit tests for error classification in `tests/unit/test_errors.py` covering every status in T007's two lists plus timeout exceptions
- [X] T010 [P] Write unit tests for redaction in `tests/unit/test_redaction.py` asserting a registered token appears in zero bytes of formatted records, including inside exception tracebacks
- [X] T011 Implement configuration loading in `src/jira_testgen/config.py`: load `.env` via `python-dotenv`; required `base_url` (`https://` URL, trailing slash normalized), `email` (contains `@`), `api_token` (non-empty, registered as a redacted secret at load); optional `project_key` (`^[A-Z][A-Z0-9_]*$`), `test_issue_type` (default `Task`), `link_type` (default `Relates`), `ac_field` (`^customfield_\d+$` when set); record which defaults were applied (FR-030, FR-032, FR-035) — depends on T008
- [X] T012 Ensure the token value has no `__repr__`, no `__str__`, and no serialization path in `src/jira_testgen/config.py`, existing only as an argument to the auth header (FR-034) — depends on T011
- [X] T013 Implement ADF text extraction and building in `src/jira_testgen/jira/adf.py`: walk paragraphs, headings, list items, and table cells collecting text; record whether non-text nodes (image, media, macro) were present; build `heading`, `paragraph`, `orderedList`, `listItem`, `text` nodes for issue descriptions
- [X] T014 [P] Write contract tests for ADF round-tripping in `tests/contract/test_adf.py` against **recorded real** Jira payloads, not hand-written ones, per research.md §13 — depends on T013
- [X] T015 Implement HTTP client in `src/jira_testgen/jira/client.py`: Basic auth from config, v3 base path, and the retry policy — honour `Retry-After` (seconds or HTTP date) when present, else exponential backoff from 1s doubling with jitter capped at 30s per wait, 5 attempts maximum, retrying only `TransientError` (FR-051, FR-052) — depends on T007, T011
- [X] T016 [P] Write contract tests for the retry policy in `tests/contract/test_retry.py`: a 429 carrying `Retry-After` is honoured rather than guessed at, `PermanentError` is never retried, and exhaustion raises rather than hanging — depends on T015
- [X] T017 Implement issue operations in `src/jira_testgen/jira/issues.py`: `GET /rest/api/3/issue/{key}` with `fields=summary,description,issuelinks,project,{ac_field}`, `POST /rest/api/3/issue`, `PUT /rest/api/3/issue/{key}`, `POST /rest/api/3/issueLink`, and linked-issue discovery for a story — depends on T015
- [X] T018 [P] Implement issue property read/write in `src/jira_testgen/jira/properties.py` for key `com.tcgen.testcase`, treating 404 as "not this tool's issue" rather than an error (FR-026c) — depends on T015
- [X] T019 [P] Implement identity lookup in `src/jira_testgen/jira/search.py` via `GET /rest/api/3/search/jql` with `jql=labels="tcgen-id-..."`, allowing a brief settle delay before concluding no match, since JQL indexing is near-real-time but not instantaneous (FR-053) — depends on T015
- [X] T020 Implement published-work discovery in `src/jira_testgen/jira/issues.py`: for each issue linked to the story, read its `com.tcgen.testcase` property and build a map of identity → (issue key, stored fingerprint, link present), ignoring entirely any linked issue without the property (FR-026, FR-026c) — depends on T017, T018
- [X] T021 Implement CLI skeleton in `src/jira_testgen/cli.py`: `argparse` subcommands `doctor`, `prepare`, `validate`, `publish`; global `--json`, `--verbose`, `--debug`, `--log-file`; report on stdout and logs on stderr; the full exit-code table from contracts/cli.md (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11) — depends on T008, T011

**Checkpoint**: Configuration, logging, error handling, and the Jira access layer are ready — user story work can begin

---

## Phase 3: User Story 1 - Draft test cases from a Jira story and review them (Priority: P1) 🎯 MVP

**Goal**: An engineer runs one command, the Claude Code session fills in test cases, and a reviewable draft file exists. Nothing is written to Jira.

**Independent Test**: Point `prepare` at a real story with acceptance criteria, let the session fill the scaffold, and confirm a draft file appears with every criterion traceable to at least one test case — while the story and its project are unchanged in Jira.

### Tests for User Story 1

> Write these first and confirm they fail before implementing

- [X] T022 [P] [US1] Write unit tests for criteria extraction in `tests/unit/test_criteria.py`: read from `JIRA_AC_FIELD` when set, else a heading or bolded line matching `acceptance criteria` case-insensitively followed by list items or non-empty lines until the next heading; prose-style criteria; `source_text` preserved verbatim (FR-002, FR-003)
- [X] T023 [P] [US1] Write unit tests for comparison normalization in `tests/unit/test_normalize.py`: markup stripped, whitespace runs collapsed to one space, bullets and numbering prefixes dropped, casefolded — so formatting-only edits compare equal while a reworded criterion does not (FR-057)
- [X] T024 [P] [US1] Write unit tests for identity minting and parsing in `tests/unit/test_identity.py`: format `<ISSUE-KEY>-TC-<NNN>` zero-padded to 3, derived independently of wording, round-tripping to and from the lowercased label `tcgen-id-<issue-key>-tc-<nnn>` (FR-025)
- [X] T025 [P] [US1] Write unit tests for fingerprint canonicalization in `tests/unit/test_fingerprint.py`: sha256 over compact JSON of `criteria` and `test_cases` only, with keys sorted, trailing whitespace stripped, line endings normalized to `\n`; reflowing a block scalar or reordering mapping keys does **not** change the hash, changing any content word does, and the `approval` block is excluded (FR-044)
- [X] T026 [P] [US1] Write unit tests for size thresholds in `tests/unit/test_limits.py`: warning above 25 test cases, ceiling at 100, both fixed defaults with no configuration path (FR-064, FR-066)
- [X] T027 [P] [US1] Write contract tests for the draft file schema in `tests/contract/test_draft_file.py`: load/dump round-trip preserving block scalars, unknown `schema_version` refused rather than guessed at, every field rule from contracts/draft-file.md
- [X] T028 [P] [US1] Write integration test for the drafting happy path in `tests/integration/test_prepare.py` against mocked Jira: a 5-criterion story yields a scaffold with 5 criteria, 5+ identities, and empty test case slots, and **zero** Jira writes occur (quickstart scenario A)
- [X] T029 [P] [US1] Write integration test for the no-criteria stop in `tests/integration/test_prepare_no_criteria.py`: exit 5, a message naming both the configured field and the description section searched, and **no draft file written** (FR-005, quickstart scenario I)
- [X] T030 [P] [US1] Write integration test for draft-overwrite refusal in `tests/integration/test_prepare_regenerate.py`: a second `prepare` exits 7 leaving the existing file byte-for-byte unchanged; with `--regenerate` the replaced file is named, `.bak` holds the old content, the new draft is `status: draft`, and published identities are reused (FR-047–FR-050, quickstart scenario G)

### Implementation for User Story 1

- [X] T031 [P] [US1] Implement criteria extraction and dual-form storage in `src/jira_testgen/criteria.py`: `source_text` verbatim for display and traceability, `normalized` for comparison only — the two must never be substituted for each other (FR-002, FR-003, FR-057) — depends on T013
- [X] T032 [P] [US1] Implement `SourceStory` retrieval in `src/jira_testgen/criteria.py` or a sibling module: validate the issue key against `^[A-Z][A-Z0-9_]*-\d+$` before any request, then fetch and flatten the description, recording `description_had_non_text` for the draft warnings (FR-001, FR-004) — depends on T017
- [X] T033 [P] [US1] Implement identity minting in `src/jira_testgen/draft/identity.py` with the format and label mapping from T024, immutable once assigned (FR-025)
- [X] T034 [P] [US1] Implement fingerprint canonicalization in `src/jira_testgen/draft/fingerprint.py` per T025, exposing separate functions for the draft content region and for criteria comparison (FR-045, FR-057)
- [X] T035 [P] [US1] Implement size thresholds in `src/jira_testgen/limits.py`: `WARN_ABOVE = 25`, `REFUSE_ABOVE = 100` as module constants with no configuration path (FR-066)
- [X] T036 [US1] Implement draft models and YAML I/O in `src/jira_testgen/draft/schema.py`: `DraftSet`, `TestCase`, `AcceptanceCriterion`, `ApprovalState` with every field rule from contracts/draft-file.md — `category` in `positive|negative|boundary|edge`, `covers` with ≥1 existing criterion label, `steps` with ≥1 non-empty entry, `summary`/`preconditions`/`expected_results` non-empty, `schema_version` integer (FR-006, FR-061) — depends on T033, T034
- [X] T037 [US1] Implement atomic replacement with backup in `src/jira_testgen/draft/backup.py`: write to a same-directory temporary file, `fsync`, move the existing file to `<name>.yaml.bak` replacing any previous backup, then `os.replace` into place — atomic on Windows and POSIX, keeping exactly one backup generation (FR-050)
- [X] T038 [US1] Implement draft validation in `src/jira_testgen/draft/validate.py`: structural checks naming the offending test case identity; every criterion covered by ≥1 test case including ≥1 `positive`; ≥1 `negative` and ≥1 `edge` across the set; identities unique and well-formed; approval state consistency; the exact message forms from contracts/draft-file.md (FR-007, FR-008, FR-009, FR-017, FR-063) — depends on T036
- [X] T039 [US1] Implement the `prepare` command in `src/jira_testgen/cli.py`: the six-step behaviour from contracts/cli.md, including the exit-7 refusal, `--regenerate` with identity reuse read from Jira, and the `>25` warning; emit a header comment explaining review, approval, and that deleting a test case is how to reject it (FR-012, FR-047–FR-050, FR-064) — depends on T020, T031, T032, T036, T037
- [X] T040 [US1] Implement the `validate` command in `src/jira_testgen/cli.py`: run the T038 checks with no network access, printing the criterion-to-test-case coverage map, any uncovered criteria, set size against thresholds, and the approval state as `draft`, `approved`, or `approval voided by edit` (FR-009, FR-017) — depends on T038
- [X] T041 [US1] Write the Claude Code skill at `.claude/skills/jira-testgen/SKILL.md` implementing the skill contract from contracts/cli.md: run `prepare`, branch on exit 7, fill test cases with one positive per criterion plus other categories only where warranted and **no filler**, ensure ≥1 negative and ≥1 edge in the set, preserve every scaffold identity exactly, run `validate`, report coverage, then **stop** for review — and never edit the `approval` block on the engineer's behalf (FR-007, FR-015, FR-036, FR-062, FR-063)
- [X] T042 [US1] Implement generation-without-session handling in `src/jira_testgen/cli.py` and `.claude/skills/jira-testgen/SKILL.md`: `prepare`, `validate`, and `publish` all succeed headless, while writing test case content is documented as requiring a session, with no code path producing content by other means (FR-036, FR-037)

**Checkpoint**: An engineer can draft and review test cases for a story. Nothing reaches Jira. This is a usable product on its own.

---

## Phase 4: User Story 2 - Publish approved test cases into Jira as linked issues (Priority: P2)

**Goal**: Approved drafts become Jira issues linked to the story, with a complete per-test-case report.

**Independent Test**: Mark a draft of known contents approved, run `publish`, and confirm the expected issues exist, each linked to the story, with contents matching the reviewed drafts.

### Tests for User Story 2

- [X] T043 [P] [US2] Write integration test for the approval gate in `tests/integration/test_publish_gate.py`: publishing an unapproved draft exits 6 naming the file and the `status: approved` marker, and creates **zero** issues and **zero** links (FR-016, quickstart scenario B)
- [X] T044 [P] [US2] Write integration test for voided approval in `tests/integration/test_publish_voided.py`: editing content after approval causes exit 6, resets `status` to `draft` in the file, and creates nothing; re-approving then publishes successfully (FR-043, FR-046, quickstart scenario C)
- [X] T045 [P] [US2] Write integration test for the publish happy path in `tests/integration/test_publish.py`: 12 test cases become 12 issues, each linked to the story, every one reported `created` with its key, verdict `success` (FR-018, FR-019, FR-021, quickstart scenario A)
- [X] T046 [P] [US2] Write integration test for partial failure in `tests/integration/test_publish_partial.py`: the 5th of 12 fails permanently, the other 11 are created and reported as successes, the 5th is reported failed with its reason, and the verdict is `partial` not `success` (FR-020, FR-021, FR-022)
- [X] T047 [P] [US2] Write integration test for created-but-unlinked in `tests/integration/test_publish_unlinked.py`: an issue created whose link failed is reported as created-but-unlinked, and a re-run completes the missing link without creating a second issue (FR-023, FR-027)
- [X] T048 [P] [US2] Write integration test for the stale-criteria gate in `tests/integration/test_publish_stale.py`: a reworded criterion causes exit 8 naming it and pointing at regeneration; `--allow-stale-criteria` proceeds and the report records the override and the changed criteria; a **reformatted-only** criterion does not block (FR-056–FR-060, quickstart scenario H)
- [X] T049 [P] [US2] Write integration test for the size ceiling in `tests/integration/test_publish_limits.py`: 28 test cases warn and publish, 120 exit 9 until `--allow-large`, which publishes and records the override and the count (FR-064, FR-065, FR-068, quickstart scenario N)
- [X] T050 [P] [US2] Write contract tests for create, update, link, and property payloads in `tests/contract/test_issue_payloads.py` against recorded Jira responses, including the identity label and the `com.tcgen.testcase` property body

### Implementation for User Story 2

- [X] T051 [US2] Implement publish pre-flight in `src/jira_testgen/publish.py` in the exact order from contracts/cli.md: validation, approval marker, fingerprint comparison (recording the baseline when `approved_fingerprint` is null and resetting `status` to `draft` on mismatch), then target checks — nothing is created until all pass (FR-016, FR-017, FR-043, FR-045, FR-046) — depends on T038
- [X] T052 [US2] Implement target pre-flight in `src/jira_testgen/publish.py`: verify the target project, that `JIRA_TEST_ISSUE_TYPE` is creatable there via the create-metadata endpoint, and that `JIRA_LINK_TYPE` exists on the site — reporting each failure by naming the setting, before any issue is created (FR-024) — depends on T017
- [X] T053 [US2] Implement criteria staleness detection in `src/jira_testgen/publish.py`: re-read the story's criteria, compare normalized forms against the draft's recorded `source_text`, refuse on substantive change naming the changed criteria, and never block on formatting-only differences (FR-056, FR-057, FR-058) — depends on T031, T034
- [X] T054 [US2] Implement the `--allow-stale-criteria` and `--allow-large` overrides as **per-run flags only** in `src/jira_testgen/cli.py`, with no path to set either in `.env`, each recorded in the report when used (FR-059, FR-060, FR-065, FR-067, FR-068) — depends on T021
- [X] T055 [US2] Implement issue content mapping in `src/jira_testgen/publish.py`: summary, and description as ADF with a heading per section and steps as an ordered list, rendering `category` and `covers` so a reader sees the traceability without the tool (FR-018) — depends on T013
- [X] T056 [US2] Implement create-link-mark in `src/jira_testgen/publish.py`: create the issue, link it to the story with the configured link type, then write both the identity label and the `com.tcgen.testcase` property containing `identity`, `content_fingerprint`, `source_issue`, `generated_at`, `tool_version` (FR-018, FR-019, FR-026a) — depends on T017, T018, T033, T055
- [X] T057 [US2] Implement the publishing loop in `src/jira_testgen/publish.py`: continue past a permanent per-test-case failure, and stop the whole run only when retries are exhausted against a Jira-wide condition (FR-020, FR-054) — depends on T015, T056
- [X] T058 [US2] Implement the Run Report in `src/jira_testgen/report.py`: per-test-case `identity`, `decision`, `issue_key`, `reason`, `retried`, `fields_differing`; plus `defaults_used`, `criteria_source`, `warnings`, `overrides_used`, `not_attempted`, `verdict`; text and `--json` renderings matching the shape in contracts/cli.md (FR-021, FR-023, FR-035, FR-055) — depends on T011
- [X] T059 [US2] Enforce the report-completeness invariants in `src/jira_testgen/report.py`: every test case in the approved set appears in `outcomes` exactly once, and `verdict` is `partial` whenever any outcome is `conflict` or `failed` or `not_attempted` is non-empty (FR-021, FR-022, FR-042) — depends on T058
- [X] T060 [US2] Implement the `publish` command in `src/jira_testgen/cli.py` wiring pre-flight, the publishing loop, and the report, returning the correct exit code for each refusal (6, 8, 9), partial completion (10), and retry exhaustion (11) — depends on T051, T052, T053, T057, T059

**Checkpoint**: Approved drafts reach Jira as linked issues with a complete report. User Stories 1 and 2 both work.

---

## Phase 5: User Story 3 - Get set up safely in minutes (Priority: P2)

**Goal**: A fresh clone works after copying one file and filling in three values, every misconfiguration names the offending setting, and the API token never appears anywhere.

**Independent Test**: On a clean checkout, follow only the README; then blank each required setting in turn and confirm each produces a clear, specific message.

### Tests for User Story 3

- [X] T061 [P] [US3] Write unit tests for configuration validation in `tests/unit/test_config.py`: each required setting blanked in turn produces exit 2 naming that setting **exactly as it appears in `.env`**, reported before any network call (FR-032)
- [X] T062 [P] [US3] Write unit tests distinguishing malformed settings from rejected credentials in `tests/unit/test_config_errors.py`: a malformed `JIRA_BASE_URL` gives exit 2, valid-looking credentials that Jira rejects give exit 3, and neither prints the token (FR-033)
- [X] T063 [P] [US3] Write a security test in `tests/integration/test_no_token_leak.py` that runs **every** subcommand to failure and asserts the token appears in zero bytes of stdout, stderr, and any `--log-file` output, including tracebacks (FR-034, SC-008, quickstart scenario L)
- [X] T064 [P] [US3] Write a test in `tests/unit/test_env_example.py` asserting `.env.example` lists every setting `config.py` reads, so the two cannot drift (FR-031)
- [X] T065 [P] [US3] Write a test in `tests/unit/test_gitignore.py` asserting `.gitignore` excludes `.env` and `drafts/` (FR-031, SC-009)

### Implementation for User Story 3

- [X] T066 [US3] Implement the `doctor` command in `src/jira_testgen/cli.py` running the six checks in order from contracts/cli.md: setting shape (exit 2), credentials (exit 3), issue type creatable, link type exists, `JIRA_AC_FIELD` readable when set, and issue properties writable — reporting each as pass/fail and never printing the token (FR-024, FR-032, FR-033) — depends on T017, T018, T021
- [X] T067 [US3] Implement defaults reporting in `src/jira_testgen/config.py` and surface it in `doctor` and every Run Report, naming each optional setting that fell back and the value used (FR-035) — depends on T011, T058
- [X] T068 [US3] Add the `--issue` option to `doctor` in `src/jira_testgen/cli.py` so the acceptance-criteria field check can run against a real sample issue — depends on T066
- [X] T069 [US3] Write `README.md` with the setup sequence from quickstart.md (`pip install -e .`, copy `.env.example` to `.env`, fill three values, run `doctor`), a link to the Atlassian API token page, and the table of settings with their defaults (SC-009)

**Checkpoint**: A first-time user can get running from a clean checkout, and credential failures are legible.

---

## Phase 6: User Story 4 - Re-run a story without creating duplicates (Priority: P3)

**Goal**: Re-running is always safe — no duplicates, resumption after failure, in-place updates where the draft changed, and a refusal to overwrite anything a person edited in Jira.

**Independent Test**: Publish a set, publish it again unchanged, and confirm the Jira issue count is identical with every test case reported as already present; then edit one and confirm its issue is updated rather than duplicated.

### Tests for User Story 4

- [X] T070 [P] [US4] Write integration test for idempotent republish in `tests/integration/test_republish.py`: publishing the identical set again creates zero issues and reports all as `unchanged` with their existing keys (FR-026, FR-029, quickstart scenario D)
- [X] T071 [P] [US4] Write integration test for resumption in `tests/integration/test_resume.py`: a run that created 7 of 12 before failing, re-run, creates the remaining 5, reports the 7 as existing, and ends at exactly 12 linked issues — the same final state as an uninterrupted run (FR-027, FR-054, quickstart scenario J)
- [X] T072 [P] [US4] Write integration test for a deleted issue in `tests/integration/test_recreate.py`: a published test case whose issue was deleted in Jira is re-created rather than reported as present (FR-028)
- [X] T073 [P] [US4] Write integration test for in-place update in `tests/integration/test_update.py`: editing a published test case and re-approving updates that one issue, reports it as `updated`, creates no second issue, and leaves the others `unchanged` (FR-038, quickstart scenario E)
- [X] T074 [P] [US4] Write integration test for conflict detection in `tests/integration/test_conflict.py`: an issue edited in Jira is reported as `conflict` with the differing fields, **both sides unchanged**, verdict `partial`; resolving either side and re-running clears it (FR-039, FR-041, FR-042, quickstart scenario F)
- [X] T075 [P] [US4] Write integration test for foreign linked issues in `tests/integration/test_foreign_issues.py`: an unrelated issue linked to the story is not modified, not matched to any test case, and not counted as published — and matching never happens by wording (FR-026c, quickstart scenario M)
- [X] T076 [P] [US4] Write integration test for the ambiguous create in `tests/integration/test_ambiguous_create.py`: a create that times out but actually succeeded is **adopted via the identity label, not duplicated** (FR-053, SC-020, quickstart scenario K)
- [X] T077 [P] [US4] Write integration test for throttling in `tests/integration/test_throttling.py`: a 429 carrying `Retry-After` is waited out and the run completes without engineer intervention, with retried test cases named in the report (FR-051, FR-055, SC-021)
- [X] T078 [P] [US4] Write integration test for statelessness in `tests/integration/test_no_local_state.py`: deleting `drafts/` entirely, regenerating, and publishing produces zero duplicates (FR-026b, SC-016, quickstart scenario O)
- [X] T079 [P] [US4] Write integration test for an orphaned draft entry in `tests/integration/test_orphaned.py`: a published test case deleted from the draft leaves its Jira issue in place and is reported as no longer present in the draft

### Implementation for User Story 4

- [X] T080 [US4] Implement the publish decision engine in `src/jira_testgen/publish.py` producing the seven mutually exclusive decisions from data-model.md — `create`, `unchanged`, `update`, `conflict`, `relink`, `recreate`, `orphaned_draft` — derived purely from draft content, issue content, stored fingerprint, and link presence, with no run history, no local state, and no timestamps (FR-026–FR-029, FR-038, FR-039) — depends on T020, T034
- [X] T081 [US4] Implement conflict detection in `src/jira_testgen/publish.py`: rebuild the issue's content from its current fields, normalize and hash it, and compare against the stored `content_fingerprint` — deliberately **not** using the issue's `updated` timestamp, since automations, workflow transitions, and comments all bump it and would produce phantom conflicts (FR-039, FR-040) — depends on T018, T080
- [X] T082 [US4] Implement in-place update in `src/jira_testgen/publish.py`: update the issue's fields to match the approved draft and refresh the stored fingerprint so it always reflects what the tool last wrote (FR-038, FR-040) — depends on T081
- [X] T083 [US4] Implement `relink`, `recreate`, and `orphaned_draft` handling in `src/jira_testgen/publish.py`: create a missing link without creating a second issue, re-create a test case whose recorded issue returns 404, and leave an orphaned published issue in place while reporting it (FR-023, FR-027, FR-028) — depends on T080
- [X] T084 [US4] Implement ambiguous-create resolution in `src/jira_testgen/publish.py`: before retrying any create whose outcome is unclear, search by identity label and adopt an existing issue — ensuring its property and link exist — rather than creating a second one (FR-053) — depends on T019, T056
- [X] T085 [US4] Implement resumable stop on retry exhaustion in `src/jira_testgen/publish.py`: report which test cases were published and which were not, populate `not_attempted`, and exit 11 leaving the run resumable (FR-054) — depends on T057, T058
- [X] T086 [US4] Extend the Run Report in `src/jira_testgen/report.py` to carry `conflict` with `fields_differing`, `updated`, `retried` counts, and `not_attempted`, with `verdict: partial` whenever any conflict exists (FR-042, FR-055) — depends on T058, T080

**Checkpoint**: All four user stories are independently functional. Re-running is safe under every failure mode in the spec.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T087 [P] Run every quickstart scenario A–O from quickstart.md against a scratch Jira project and record the results
- [X] T088 [P] Audit every error message against the spec's "name the setting / name the file / name the test case" standard, in `src/jira_testgen/` — a message that does not name its subject is a defect
- [X] T089 [P] Verify performance targets in `tests/integration/test_performance.py`: drafting a 5-criterion story presents reviewable drafts in under 2 minutes (SC-002), and publishing 12 test cases completes within a few minutes including retries (SC-001)
- [X] T090 [P] Add unit tests for any branch left uncovered by the story phases in `tests/unit/`, prioritising the fingerprint, normalization, and decision-engine paths where a silent error is costly
- [X] T091 Re-run the full token-leak sweep in `tests/integration/test_no_token_leak.py` after all features are complete, extending it to cover every subcommand and flag combination added since T063, since each new log line and error path is a fresh opportunity to leak (FR-034)
- [X] T092 [P] Document the `drafts/` lifecycle and the `.bak` convention in `README.md`, including that approval is a one-word edit and deleting a test case is how to reject it
- [X] T093 Run `/speckit-constitution` to fill `.specify/memory/constitution.md`, which is still an uninstantiated template — so this feature's Constitution Check passed vacuously rather than cleanly (see plan.md)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Setup — **blocks all user stories**
- **User Story 1 (Phase 3)**: Depends on Foundational. No dependencies on other stories
- **User Story 2 (Phase 4)**: Depends on Foundational. Needs a draft file to publish, which US1 produces — a hand-written fixture draft makes it independently testable
- **User Story 3 (Phase 5)**: Depends on Foundational only. Fully independent of US1, US2, US4
- **User Story 4 (Phase 6)**: Depends on Foundational and on US2's publishing path, since it governs *re*-publishing
- **Polish (Phase 7)**: Depends on all desired stories

### Story dependency notes

US1 and US3 are genuinely independent and can proceed in parallel. US2 depends on US1 only for *input* — a fixture draft file decouples them for testing. US4 is the one real dependency: it extends US2's publishing path rather than standing beside it, so US2 should be complete before US4 starts.

### Within each story

Tests before implementation. Pure logic (criteria, identity, fingerprint, limits) before the models that use it; models before services; services before CLI commands.

### Parallel opportunities

- Setup: T003, T004, T005, T006 together
- Foundational: T007, T008 together, then T009, T010 together; T014, T016, T018, T019 together once their dependencies land
- US1: all of T022–T030 together; then T031–T035 together
- US2: all of T043–T050 together
- US3: all of T061–T065 together; the whole phase can run alongside US1
- US4: all of T070–T079 together
- Polish: T087, T088, T089, T090, T092 together

---

## Parallel Example: User Story 1

```bash
# All US1 tests together (they fail until implementation lands):
Task: "Unit tests for criteria extraction in tests/unit/test_criteria.py"
Task: "Unit tests for comparison normalization in tests/unit/test_normalize.py"
Task: "Unit tests for identity minting in tests/unit/test_identity.py"
Task: "Unit tests for fingerprint canonicalization in tests/unit/test_fingerprint.py"
Task: "Unit tests for size thresholds in tests/unit/test_limits.py"
Task: "Contract tests for the draft file schema in tests/contract/test_draft_file.py"
Task: "Integration test for the drafting happy path in tests/integration/test_prepare.py"

# Then all US1 pure-logic modules together:
Task: "Criteria extraction in src/jira_testgen/criteria.py"
Task: "Identity minting in src/jira_testgen/draft/identity.py"
Task: "Fingerprint canonicalization in src/jira_testgen/draft/fingerprint.py"
Task: "Size thresholds in src/jira_testgen/limits.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1: Setup (T001–T006)
2. Phase 2: Foundational (T007–T021) — blocks everything
3. Phase 3: User Story 1 (T022–T042)
4. **STOP and VALIDATE**: run quickstart scenarios A, G, and I
5. Demo: an engineer can draft and review test cases for a real story, with nothing written to Jira

This is a genuine MVP. A QA engineer who only ever uses `prepare` and `validate` has already replaced the slowest part of their job and can paste the results into Jira by hand.

### Incremental delivery

1. Setup + Foundational → access layer ready
2. US1 → draft and review (**MVP**, scenarios A, G, I)
3. US3 → safe, legible setup (scenario L) — can run in parallel with US1
4. US2 → publishing (scenarios B, C, H, N)
5. US4 → safe re-runs (scenarios D, E, F, J, K, M, O)
6. Polish → full quickstart sweep

### Parallel team strategy

After Foundational completes: one developer on US1, another on US3 immediately, since they share nothing. US2 starts when US1's draft schema is stable — or earlier against a fixture draft. US4 waits for US2.

---

## Notes

- `[P]` means a different file and no dependency on incomplete work
- Verify each test fails before implementing against it
- Commit after each task or logical group
- Every checkpoint is a valid place to stop and demo
- Two reversible-now, awkward-later choices from plan.md are worth revisiting before T036 and T013 respectively: **YAML** for the draft file, and **API v3 with a hand-rolled ADF helper**

---

## Phase 8: Convergence

Appended by `/speckit-converge` on 2026-10-10. Assessment of the present state of
the code against spec.md, plan.md, tasks.md and the constitution — not a diff.

- [X] T094 CRITICAL: rewrite `test_no_real_env_file_is_present_in_the_repository` in tests/unit/test_gitignore.py to assert that `.env` is ignored/untracked rather than absent, so following the documented setup (`cp .env.example .env`) leaves the suite green per Constitution "Development Workflow" and SC-009 (contradicts)
- [X] T095 CRITICAL: rewrite `test_no_draft_file_is_currently_tracked_outside_the_placeholder` in tests/unit/test_gitignore.py to assert drafts are ignored rather than that none exist, so running `prepare` as designed leaves the suite green per Constitution "Development Workflow" and FR-012 (contradicts)
- [ ] T096 Record real Jira payloads as contract fixtures in tests/contract/ (issue GET with ADF description, create, link, property write) now that live credentials work, replacing hand-written schema approximations, per Constitution III (partial)
- [ ] T097 Fix the prepare-time size threshold in src/jira_testgen/prepare.py, which feeds the acceptance-criteria count into `size_warning`/`ceiling_message` and so reports it as a test-case count, per FR-064 and FR-065 (contradicts)
- [ ] T098 [P] Add a test driving `prepare` with more than 25 and more than 100 acceptance criteria, asserting the draft warning names the quantity it actually counted, per FR-064, FR-065 and SC-025 (missing)
- [ ] T099 Extract the URL from `inlineCard`/`blockCard` nodes in src/jira_testgen/jira/adf.py as readable text and exclude them from the non-text warning, so a story whose description holds a bare URL is not reported as containing images, attachments or macros, per spec.md edge case "Non-text content in the story" and FR-001 (partial)
- [ ] T100 Run quickstart.md scenarios A, B, G, H and M against a real Jira scratch project and record the outcomes in specs/001-jira-test-case-generator/validation-results.md, per quickstart.md "Done when" (partial)
- [ ] T101 [P] Correct the fingerprint normalization rules in specs/001-jira-test-case-generator/contracts/draft-file.md, which state trailing-whitespace stripping and line-ending normalization while also requiring reflow-invariance, to describe the implemented whole-whitespace collapse (contradicts)
- [ ] T102 [P] Align the publish-decision vocabulary in specs/001-jira-test-case-generator/data-model.md with contracts/cli.md and the implementation (`created`/`updated` not `create`/`update`), and restate `recreate` without assuming a local ledger, per analysis findings I1/I2 (contradicts)
