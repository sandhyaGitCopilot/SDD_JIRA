# Feature Specification: Jira Test Case Generator

**Feature Branch**: `001-jira-test-case-generator`

**Created**: 2026-10-09

**Status**: Draft

**Input**: User description: "Build a test case generator for QA engineers that turns a Jira issue into reviewed, ready-to-use manual test cases."

## Clarifications

### Session 2026-10-09

- Q: When the tool turns a story's acceptance criteria into test cases, should the test-case writing be done by the Claude Code session, by built-in rules, or by both with one as a fallback? → A: Claude Code session only — no rule-based generator is built or maintained.
- Q: If a test case has already been published and the engineer later edits its wording in the draft and re-runs, what should happen to the existing Jira issue? → A: Update it in place, but only while it is untouched since the tool wrote it; if someone edited it in Jira, report a conflict naming the issue and what differs, change nothing, and let the engineer resolve it by editing Jira or the draft and re-running.
- Q: Where should the tool look for a story's acceptance criteria? → A: A configured Jira field first when that optional setting is present, otherwise a labelled acceptance criteria section in the description, recording which source was used. If neither yields any criteria, stop and report that none were found, naming both places it looked, rather than generating test cases from the description alone.
- Q: How should the engineer signal that they have reviewed the drafts and approve them for publishing? → A: By setting an approval marker inside the draft file, which publish requires. If the draft content is edited after the marker is set, the approval is void and must be given again; setting the marker itself is not a content edit.
- Q: How should a re-run discover what has already been published — a record on the engineer's machine, a query to Jira, or both? → A: Query Jira only. Each created issue carries its test case identity and a fingerprint of the content the tool last wrote, stored on the issue itself, so no local file is needed for re-runs. Issues linked to the story that lack this identity are left untouched and are never matched by wording.
- Q: If the engineer re-runs drafting for a story that already has a draft file, what happens to that file? → A: Refuse by default, naming the existing file, and proceed only when the engineer explicitly asks to regenerate. A regenerated draft reuses the test case identities already published in Jira so re-publishing never duplicates, starts unapproved so it must be approved again, and the previous version is kept as a backup.
- Q: When Jira throttles the tool or a request fails transiently mid-publish, should it retry automatically or report and leave re-running to the engineer? → A: Bounded automatic retry with increasing waits for throttling and transient network or server errors, honouring any wait instruction Jira returns; permanent errors fail immediately. Before retrying a create whose outcome is unclear, such as a timeout, check Jira for an issue carrying that test case's identity so a request that actually succeeded is never created twice. If retries are exhausted the run stops, reports which test cases were published and which were not, and a re-run resumes from there.
- Q: If the story's acceptance criteria change in Jira between drafting and publishing, should the tool still publish the approved drafts? → A: No — re-read the criteria at publish time and refuse if they changed substantively, naming which criteria changed and pointing at regeneration. The comparison ignores formatting-only differences such as whitespace and markup. An explicit, deliberate override lets the engineer publish anyway, and the run report records that it was used and which criteria had changed.
- Q: How many test cases should the generator aim to produce for each acceptance criterion? → A: At least one positive per criterion, plus negative, boundary, and edge cases only where the criterion warrants them. Each test case states which criterion it covers and which category it belongs to. Nothing is generated for a category that does not apply, and the draft need not explain the omission. The set as a whole must still include at least one negative and one edge case.
- Q: At what size should a generated set trigger a warning, and should there be a hard limit on issues created per story? → A: Warn above 25 test cases and refuse above 100 unless explicitly overridden. Both thresholds are fixed defaults, not settings. The override is a per-run command flag and cannot be set permanently in the configuration file; the run report records when it was used and how many test cases were published.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Draft test cases from a Jira story and review them (Priority: P1)

A QA engineer gives the tool a Jira issue key for a story they have been asked to test. The tool reads the story's summary, description, and acceptance criteria — stopping with a clear report if it can find no criteria at all — and produces a set of structured manual test cases — each with a summary, preconditions, numbered steps, and expected results — covering positive, negative, boundary, and edge scenarios as each criterion warrants. The drafts are written to a file the engineer can open, read, and edit. The tool then stops and waits: nothing is written to Jira until the engineer marks the file approved. If a draft for that story already exists, the tool refuses to replace it unless asked to regenerate.

**Why this priority**: This is the core value and a complete, usable product on its own. A QA engineer who only ever uses this step has already replaced the slowest part of their job — turning prose requirements into a coverage-complete test suite — and can paste the results anywhere by hand. Every later story builds on the drafts this one produces.

**Independent Test**: Point the tool at a real Jira story that has acceptance criteria and confirm a draft file appears containing test cases traceable to every criterion, and that the story and its project are unchanged in Jira afterwards.

**Acceptance Scenarios**:

1. **Given** a valid configuration and a Jira story `PROJ-123` with a summary, a description, and 5 acceptance criteria, **When** the engineer runs the generator for `PROJ-123`, **Then** a draft file is created containing test cases in which each of the 5 criteria is referenced by at least one test case, and the run ends by reporting that the drafts await review.
2. **Given** the same story, **When** the engineer inspects the drafts, **Then** each of the 5 criteria has at least one positive test case, the set includes at least one negative and one edge test case, every test case names the criterion it covers and its category, and every test case has a non-empty summary, preconditions, at least one step, and an expected result for its steps.
3. **Given** a draft file has been produced, **When** the engineer looks in Jira, **Then** no new issues and no new links exist for `PROJ-123`.
4. **Given** an issue key that does not exist or that the configured account cannot view, **When** the engineer runs the generator, **Then** the tool stops with a message naming the issue key and the reason, and no draft file is written.
5. **Given** a story with no acceptance criteria in either the configured field or a labelled description section, **When** the engineer runs the generator, **Then** the tool stops, reports that no acceptance criteria were found and names both places it looked, and writes no draft file.
6. **Given** a story whose criteria live in a labelled description section and no criteria field setting is configured, **When** the engineer runs the generator, **Then** the criteria are read from the description and the draft file records that the description was the source.
7. **Given** a story that already has a draft file the engineer has reviewed and edited, **When** the engineer runs the generator again without asking to regenerate, **Then** the tool refuses, names the existing file, and leaves it exactly as it was.
8. **Given** the same story, **When** the engineer runs the generator again and explicitly asks to regenerate, **Then** the tool names the file it is replacing, keeps the previous version as a backup, writes a fresh unapproved draft, and reuses the identities of test cases already published in Jira for that story.
9. **Given** a regenerated draft whose test cases were already published, **When** the engineer approves and publishes it, **Then** the already-published test cases are recognised as existing rather than created a second time.

---

### User Story 2 - Publish approved test cases into Jira as linked issues (Priority: P2)

Having read and possibly edited the drafts, the QA engineer marks the draft file approved. The tool then creates one Jira issue per approved test case in the target project, links each new issue back to the original story, and reports exactly what was created and what failed.

**Why this priority**: This removes the remaining manual work — copying dozens of test cases into Jira by hand — but depends entirely on reviewed drafts existing first.

**Independent Test**: Mark a draft file of known contents approved, run the publish step, and confirm that the expected number of issues exist in Jira, each linked to the source story, with contents matching the reviewed drafts.

**Acceptance Scenarios**:

1. **Given** a reviewed draft file containing 12 test cases and an explicit approval from the engineer, **When** the publish step runs, **Then** 12 issues are created in the target project, each one linked to the source story, and the report lists each created issue with its key and summary.
2. **Given** the engineer edited a draft before approving — changing wording, adding a step, or deleting a whole test case — **When** the publish step runs, **Then** the issues created reflect the edited content exactly, and deleted test cases are not created.
3. **Given** the draft file has no approval marker set, **When** the engineer attempts to publish, **Then** the tool refuses, names the file and the marker it expects, and creates nothing.
4. **Given** an approved draft file that the engineer then edits again, **When** the engineer attempts to publish, **Then** the tool refuses, reports that the drafts changed after approval, returns the file to its unapproved state, and creates nothing.
5. **Given** 12 test cases where the 5th fails to be created in Jira (for example, the issue type is rejected by the project), **When** the publish step finishes, **Then** the other 11 are created and reported as successes, the 5th is reported as a failure with the reason, and the overall run is reported as partially complete rather than successful.
6. **Given** a test case issue was created but its link to the story could not be created, **When** the run finishes, **Then** the report names that issue as created-but-unlinked so the engineer can see it, and a re-run completes the missing link without creating a second issue.
7. **Given** an approved draft whose story has since had one acceptance criterion rewritten in Jira, **When** the engineer publishes, **Then** the tool refuses, names the changed criterion, directs the engineer to regenerate, and creates nothing.
8. **Given** an approved draft whose story has since had a criterion only reformatted — whitespace or markup changed, wording the same — **When** the engineer publishes, **Then** publishing proceeds normally and nothing is blocked.
9. **Given** a refusal because the criteria changed, **When** the engineer publishes again with an explicit override, **Then** the test cases are published and the report records that the override was used and which criteria had changed.

---

### User Story 3 - Get set up safely in minutes (Priority: P2)

A QA engineer who has just cloned the repository copies the provided example configuration file, fills in their own Jira site, email, and API token, and runs the tool successfully. If they miss or mistype a setting, the tool tells them exactly which one. Their real credentials are never committed to the repository and the API token never appears in any output.

**Why this priority**: Nothing else in the feature can be used until this works, and a leaked API token is the most expensive failure this feature could cause. It is listed below drafting only because drafting defines what the tool is for.

**Independent Test**: On a clean checkout, follow only the repository's setup instructions, and confirm a successful run against a real Jira story; then deliberately blank each required setting in turn and confirm each produces a clear, specific message.

**Acceptance Scenarios**:

1. **Given** a clean checkout, **When** the engineer copies the example configuration to the real configuration file and fills in site URL, email, and API token, **Then** the tool runs successfully with no other setup steps.
2. **Given** a configuration missing the API token, **When** the engineer runs any command, **Then** the tool stops before contacting Jira and reports that the API token setting is missing, naming it exactly as it appears in the configuration file.
3. **Given** a site URL that is malformed or a credential pair that Jira rejects, **When** the engineer runs any command, **Then** the tool stops and distinguishes "this setting looks wrong" from "Jira rejected these credentials", and in neither case prints the token.
4. **Given** a run that fails for any reason, **When** the engineer reads all output and any log file produced, **Then** the API token value does not appear anywhere in it, in whole or in part.
5. **Given** the real configuration file exists with live credentials, **When** the engineer inspects what the repository would commit, **Then** the real configuration file is excluded and only the placeholder example file is tracked.

---

### User Story 4 - Re-run a story without creating duplicates (Priority: P3)

A QA engineer runs the tool again for a story they have already processed — because the story changed, because a previous run failed halfway, or because they simply forgot. The tool recognises what already exists in Jira and never creates a second copy. Where a test case's reviewed wording has changed, it brings the Jira issue up to date; where someone has edited that issue in Jira, it refuses to overwrite and says so.

**Why this priority**: Re-runs are common in practice and duplicate test case issues are tedious to clean up, but a careful engineer can avoid the situation manually, so this is a safety net rather than the main path.

**Independent Test**: Publish a draft set, then publish the identical set again and confirm the issue count in Jira is unchanged and every test case is reported as already present; then edit one test case and re-publish, and confirm its issue is updated rather than duplicated.

**Acceptance Scenarios**:

1. **Given** all 12 test cases for a story were published successfully, **When** the engineer publishes the same draft file again, **Then** no new issues are created and the report lists all 12 as already existing, with their existing issue keys.
2. **Given** a previous publish run created 7 of 12 issues before failing, **When** the engineer publishes again, **Then** the remaining 5 are created, the 7 are reported as already existing, and the story ends with exactly 12 linked test case issues.
3. **Given** a published test case whose issue was later deleted in Jira by a person, **When** the engineer publishes again, **Then** the tool detects the issue is gone and re-creates it rather than silently reporting it as present.
4. **Given** the engineer adds two new test cases to an already-published draft file and re-approves, **When** the publish step runs, **Then** only the two new test cases are created and the previously published ones are left untouched.
5. **Given** the engineer edits the steps of an already-published test case whose Jira issue nobody has touched since the tool created it, **When** the engineer re-approves and publishes, **Then** that existing issue is updated in place to match the edited draft, no new issue is created, and the report names it as updated.
6. **Given** an already-published test case whose Jira issue someone has since edited directly in Jira, **When** the engineer re-publishes with a changed draft for it, **Then** the tool leaves both the issue and the draft unchanged and reports a conflict naming the issue and what differs.
7. **Given** a conflict was reported in the previous run, **When** the engineer resolves it by editing either the Jira issue or the draft and re-runs, **Then** the conflict is re-evaluated and no longer reported, and the test case ends in the state the engineer chose.
8. **Given** a run in which one test case is created, one updated, one unchanged, and one in conflict, **When** the run finishes, **Then** the report distinguishes all four outcomes and reports the run as partially complete because of the conflict.

---

### Edge Cases

- **Story with no acceptance criteria at all**: the run stops and reports that none were found, naming both the configured field and the description section it searched. No drafts are produced, because there is nothing to establish coverage against.
- **Configured criteria field exists but is empty on this story**: treated as no criteria from that source, so the description section is tried next; if that is also empty, the run stops as above.
- **Configured criteria field does not exist on the Jira site**: reported as a configuration problem naming the setting, distinct from the field merely being empty.
- **Criterion with no meaningful boundary or negative case** (for example, a purely declarative statement): only the positive test case is generated for it, with no filler and no explanation required in the draft.
- **Story whose criteria individually warrant no negative or edge case at all**: the set-level floor still applies, so at least one negative and one edge test case are produced for the story.
- **Story with a very large number of acceptance criteria** (for example, 40): the tool still produces traceable test cases for each, warns once the set exceeds 25 test cases, and refuses to publish beyond 100 without an explicit per-run override.
- **Acceptance criteria written as free prose rather than a list**: the tool extracts what it can and records in the draft file exactly which text it treated as each criterion, so the engineer can correct a bad split during review.
- **Non-text content in the story** (images, attachments, embedded tables, macros): the tool uses the text it can read and notes in the draft file that non-text content was present and not interpreted.
- **An issue key that is an epic, bug, or sub-task rather than a story**: the tool proceeds on the same basis — summary, description, criteria — and does not require the issue to be of any particular type.
- **Target project rejects the configured test issue type**: the tool reports the rejection naming the issue type setting, and does not fall back to a different type silently.
- **Configured link type does not exist on the Jira site**: the tool reports it naming the link type setting, before creating any issues.
- **Draft file edited after the approval marker was set**: publish refuses, reports that the drafts changed after approval, and returns the file to unapproved.
- **Approval marker set on a draft file that was never changed**: approval stands; a run that makes no edits is still a valid approval.
- **Draft file edited into an invalid state** (a test case left with no steps, or the file's structure broken): the publish step refuses with a message pointing at the offending test case, and creates nothing.
- **Generation requested with no Claude Code session driving the run**: the tool stops and explains that writing test cases requires a session, while still permitting retrieval, draft validation, and publishing of an already-approved draft file.
- **Acceptance criterion rewritten in Jira after the drafts were approved**: publishing refuses, names the changed criterion, and points at regeneration, so a suite is never published under a traceability claim that no longer holds.
- **Acceptance criterion added or removed in Jira after approval**: treated the same as a rewritten one, since coverage of the story as it now stands can no longer be claimed.
- **Acceptance criterion only reformatted in Jira**: publishing is not blocked, because the comparison ignores whitespace and markup differences.
- **Draft file already exists for the story**: the drafting run refuses and names the file, so a reviewed and edited draft is never silently replaced.
- **Regeneration requested after some test cases were already published**: the fresh draft reuses the published identities, so publishing it updates or leaves those issues rather than duplicating them.
- **Regeneration requested for a story whose criteria have changed in Jira**: the fresh draft reflects the new criteria, starts unapproved, and the previous draft is retained as a backup.
- **Draft file missing or deleted when publish is attempted**: the tool reports that there is nothing to publish and suggests re-running the draft step.
- **Published test case issue edited in Jira and in the draft, differently**: reported as a conflict with both sides named; neither is overwritten.
- **Published test case deleted from the draft file after its issue was created**: the Jira issue is left in place and reported as no longer present in the draft, rather than being deleted or silently ignored.
- **Two engineers process the same story concurrently**: because prior work is discovered from Jira rather than local state, the second to publish finds the first's test cases already present and does not duplicate them.
- **Story already has linked issues that this tool did not create** (a manually written test, a bug, a sub-task): they are left untouched, not matched to any draft, and not counted as published test cases.
- **Published test case issue stripped of its identity marker in Jira**: it is no longer recognisable as published, so its draft test case is treated as unpublished and created afresh; the stripped issue is left alone.
- **Jira throttles the tool mid-publish**: the tool waits as Jira instructs and retries; if throttling persists past the retry bound, the run stops and reports exactly which test cases were published and which were not.
- **A create times out with an unclear outcome**: before retrying, the tool looks for an issue already carrying that test case's identity, so a create that actually succeeded is never repeated.
- **Jira unreachable mid-publish**: already-created issues are reported, the failure is reported with its reason, and a re-run resumes without duplicating.
- **A permanent failure on one test case among many**: that test case is reported as failed with its reason and the rest of the set is still attempted.
- **Jira permissions allow reading the story but not creating issues in the target project**: the failure is reported as a permission problem naming the project, and the drafts remain intact for a later retry.

## Requirements *(mandatory)*

### Functional Requirements

**Retrieving the source story**

- **FR-001**: The tool MUST accept a Jira issue key as input and retrieve that issue's summary, description, and acceptance criteria.
- **FR-002**: The tool MUST locate acceptance criteria from a configured Jira field when that optional setting is present, and otherwise from a clearly-labelled acceptance criteria section within the issue description.
- **FR-002a**: The tool MUST report which of the two sources the criteria were read from, in its output and in the draft file.
- **FR-003**: The tool MUST record, in the draft output, the exact source text it treated as each individual acceptance criterion.
- **FR-004**: The tool MUST stop with a clear message naming the issue key when the issue does not exist, cannot be read with the configured credentials, or returns no usable text.
- **FR-005**: The tool MUST stop when neither source yields any acceptance criteria, and MUST report that none were found, naming both the configured field (or its absence) and the description section it looked for. It MUST NOT generate test cases from the summary and description alone, and MUST NOT write a draft file.

**Generating test cases**

- **FR-006**: The tool MUST produce manual test cases that each contain a summary, preconditions, an ordered list of steps, and the expected result of those steps.
- **FR-007**: The tool MUST generate at least one positive test case for every acceptance criterion, and MUST add negative, boundary, and edge test cases for a criterion only where that criterion warrants them.
- **FR-061**: Every test case MUST state which acceptance criterion it covers and which scenario category it belongs to — positive, negative, boundary, or edge.
- **FR-062**: The tool MUST NOT generate a placeholder or filler test case for a category that does not apply to a criterion, and MUST NOT be required to explain the omission in the draft file.
- **FR-063**: The generated set as a whole MUST include at least one negative test case and at least one edge test case for the story.
- **FR-064**: The tool MUST warn the engineer when a generated set exceeds 25 test cases, naming the count, so that an unusually long review is flagged before it starts.
- **FR-065**: The tool MUST refuse to publish a set of more than 100 test cases unless the engineer explicitly overrides the limit, and MUST report the count and the limit when it refuses. It MUST also surface that the set exceeds the limit when the draft is written, so the engineer learns of it before reviewing.
- **FR-066**: The 25-test-case warning threshold and the 100-test-case limit MUST be fixed defaults, and MUST NOT be configuration settings a first-time user has to understand.
- **FR-067**: The override for the 100-test-case limit MUST be a per-run action, and MUST NOT be settable as a persistent value in the configuration file.
- **FR-068**: When the limit is overridden, the run report MUST record that it was used and how many test cases were published.
- **FR-008**: The tool MUST make every retrieved acceptance criterion traceable to at least one generated test case, and MUST make that mapping visible in the draft file.
- **FR-009**: The tool MUST report, before review, any acceptance criterion it could not cover, rather than presenting the set as complete.
- **FR-010**: Test case content MUST be written by the engineer's Claude Code session. The tool MUST NOT require any paid language-model credential, and MUST NOT provide a second rule-based generator as an alternative source of test case content.
- **FR-036**: The tool MUST stop with a clear explanatory message when generation is requested without a Claude Code session driving the run, rather than producing test cases by other means.
- **FR-037**: The non-generation parts of the workflow — retrieval, criteria extraction, draft validation, publishing, reporting, and repeat-run detection — MUST be runnable without a Claude Code session.
- **FR-011**: The tool MUST produce test cases that are self-contained — readable and executable by a QA engineer who has not read the source story.

**Review and approval**

- **FR-012**: The tool MUST write the generated drafts to a file in a format the engineer can read and edit directly, and MUST report where that file is.
- **FR-047**: The tool MUST refuse to replace an existing draft file for a story, naming that file, unless the engineer explicitly asks for the drafts to be regenerated.
- **FR-048**: When regenerating, the tool MUST reuse the test case identities already published in Jira for that story, so that publishing a regenerated draft never creates a second issue for an already published test case.
- **FR-049**: Regenerating MUST leave the new draft unapproved, voiding any approval the replaced draft carried, so that regenerated content is always reviewed before it can be published.
- **FR-050**: Before replacing a draft file, the tool MUST name the file it is about to replace and MUST keep the previous version as a recoverable backup.
- **FR-013**: The tool MUST stop after writing the drafts and MUST NOT create, modify, or link anything in Jira until the engineer has explicitly approved.
- **FR-014**: The tool MUST allow the engineer to edit draft wording, add steps, add whole test cases, and delete whole test cases before approving, and MUST publish the approved edited content rather than the originally generated content.
- **FR-015**: The tool MUST require the engineer to set an explicit approval marker inside the draft file. The absence of an objection, the file merely having been saved, and the engineer invoking the publish step MUST NOT be treated as approval.
- **FR-016**: The tool MUST refuse to publish, with an explanatory message naming the draft file and the marker it expects, when the approval marker is not set.
- **FR-043**: The tool MUST treat any change to draft content made after the approval marker was set as voiding that approval, and MUST refuse to publish, reporting that the drafts changed since they were approved and must be approved again.
- **FR-044**: Setting, clearing, or re-setting the approval marker itself MUST NOT count as a change to draft content, so approving a draft never voids its own approval.
- **FR-045**: The tool MUST record, within the draft file itself, enough about the approved content that a later run can determine whether the drafts have changed since approval. This is draft review state, not a record of what has been published.
- **FR-046**: On detecting a voided approval, the tool MUST return the draft file to its unapproved state, so that re-approving is a deliberate act rather than a stale marker left in place.
- **FR-017**: The tool MUST validate the draft file before publishing and MUST refuse with a message identifying the offending test case when a draft is structurally invalid or missing required parts.

**Publishing to Jira**

- **FR-018**: After approval, the tool MUST create one Jira issue per approved test case in the target project, carrying that test case's summary, preconditions, steps, and expected results.
- **FR-019**: The tool MUST link each created issue to the original story using the configured link relationship.
- **FR-020**: The tool MUST continue attempting the remaining test cases after an individual test case fails permanently, rather than aborting the whole run. It MUST stop the run only when retries are exhausted against a condition affecting Jira as a whole, such as sustained throttling or Jira being unreachable.
- **FR-051**: The tool MUST retry a request that fails from throttling or a transient network or server error, with increasing waits and a bounded number of attempts, and MUST honour any wait instruction Jira returns instead of choosing its own interval.
- **FR-052**: The tool MUST NOT retry a permanent failure — such as a rejected issue type, a missing permission, or an invalid field — and MUST report it immediately with its reason.
- **FR-053**: Before retrying a create whose outcome is unclear, such as one that timed out, the tool MUST check Jira for an issue already carrying that test case's identity, and MUST NOT create a second issue when one is found.
- **FR-054**: When retries are exhausted, the tool MUST stop and report which test cases were published and which were not, leaving the run resumable so that a later re-run continues from that point without duplicating.
- **FR-055**: The tool MUST name in the run report every test case whose publishing was retried, so that a slow run is explainable after the fact.
- **FR-021**: The tool MUST report, for every test case in the approved set, whether it was created, already existed unchanged, was updated, is in conflict, or failed — and for failures and conflicts, the reason.
- **FR-022**: The tool MUST distinguish a fully successful run from a partially complete one in its final report and its exit signal.
- **FR-023**: The tool MUST report any issue that was created but could not be linked, so that no created issue is left unaccounted for.
- **FR-024**: The tool MUST verify the configured target project, test issue type, and link relationship are usable before it begins creating issues.
- **FR-056**: Before publishing, the tool MUST re-read the source story's acceptance criteria and compare them against the criterion source text recorded in the draft.
- **FR-057**: That comparison MUST ignore formatting-only differences, such as whitespace and markup, so that a reformatted but substantively unchanged criterion does not block publishing.
- **FR-058**: The tool MUST refuse to publish when the criteria have substantively changed since drafting, naming which criteria changed and directing the engineer to regenerate the drafts.
- **FR-059**: The tool MUST allow the engineer to override that refusal only by an explicit, deliberate action, and MUST NOT treat an ordinary publish invocation as an override.
- **FR-060**: When an override is used, the run report MUST record that it was used and which criteria had changed, so that a knowingly stale suite is never published silently.

**Repeat runs**

- **FR-025**: The tool MUST give each test case a stable identity, assigned when the draft is first written and independent of the test case's wording, so that editing a test case does not make it look like a new one.
- **FR-026**: The tool MUST detect test cases already published for a story by reading the issues linked to that story in Jira, and MUST NOT create a second issue for them.
- **FR-026a**: The tool MUST store each test case's identity, and a fingerprint of the content it last wrote, on the created Jira issue itself, so that a re-run needs no state held outside Jira.
- **FR-026b**: The tool MUST NOT require any locally stored record of past publishing, and MUST behave identically on a different machine, a fresh clone, or after any local files have been deleted.
- **FR-026c**: The tool MUST leave untouched any issue linked to the story that does not carry a test case identity written by this tool, and MUST NOT match such an issue to a draft by its wording or summary.
- **FR-027**: The tool MUST complete the work left unfinished by a previous failed run — including creating missing issues and missing links — without duplicating what succeeded.
- **FR-028**: The tool MUST re-create a test case whose previously created Jira issue no longer exists, rather than reporting it as present.
- **FR-029**: The tool MUST leave a previously published test case's Jira issue untouched when its approved draft content is unchanged, including when other, newly added test cases are being published in the same run.
- **FR-038**: The tool MUST update a previously published test case's Jira issue in place to match the approved draft when the draft content has changed and the issue has not been modified in Jira since the tool last wrote it, and MUST name every issue it updated in the run report.
- **FR-039**: The tool MUST NOT overwrite a published test case's Jira issue that has been modified outside the tool. It MUST instead report a conflict naming the issue and stating what differs between the draft and the issue, and leave both unchanged.
- **FR-040**: The tool MUST use the fingerprint stored on each published issue to distinguish an issue unchanged since the tool wrote it from one modified in Jira, without the engineer having to tell it which, and MUST refresh that fingerprint whenever it updates the issue.
- **FR-041**: The tool MUST re-evaluate a reported conflict from scratch on the next run, so that an engineer who resolves it by editing either the Jira issue or the draft sees the conflict clear itself.
- **FR-042**: The tool MUST report conflicts as an outcome distinct from created, already existing, updated, and failed, and MUST report a run containing unresolved conflicts as partially complete.

**Configuration and credentials**

- **FR-030**: The tool MUST read Jira connection settings — site address, account email, API token — and the optional target project, test issue type, link relationship, and acceptance criteria field from a local configuration file that is not part of the repository's tracked contents.
- **FR-031**: The repository MUST include a placeholder example configuration file listing every supported setting, and MUST exclude the real configuration file from version control.
- **FR-032**: The tool MUST validate configuration before contacting Jira and MUST stop with a message naming each missing or malformed required setting, exactly as that setting is named in the configuration file.
- **FR-033**: The tool MUST distinguish a malformed setting from credentials that Jira rejected, in its error messages.
- **FR-034**: The tool MUST NOT print, log, or write the API token — in whole or in part — in any output, report, draft file, or log, including when reporting errors.
- **FR-035**: The tool MUST apply a documented default for each optional setting when it is absent, and MUST report which defaults it used.

### Key Entities

- **Source Story**: The Jira issue the engineer names. Carries a key, a summary, a description, and zero or more acceptance criteria. Read-only to this feature apart from gaining links to test case issues.
- **Acceptance Criterion**: One testable requirement extracted from the source story. Carries its own position or label and the exact source text it came from. Must be traceable to at least one test case.
- **Test Case**: One manual test. Carries a summary, preconditions, ordered steps, expected results, a scenario category (positive, negative, boundary, edge), the criteria it covers, and a stable identity assigned at draft time and independent of its wording, used to recognise it across runs even after it has been edited.
- **Draft Set**: The reviewable collection of test cases for one source story, together with the criterion-to-test-case mapping, the recorded criterion source text, which source the criteria came from, any warnings raised during generation, and its approval state. The approval state covers both whether the marker is set and the content it was set against, so a later edit can be recognised as voiding it. Regenerating a Draft Set produces an unapproved replacement and retains the previous version as a backup.
- **Publication Marker**: The identity and content fingerprint the tool stores on each test case issue it creates, in Jira itself rather than in any local file. The identity makes the issue recognisable as the published form of a specific draft test case; the fingerprint lets a later run tell an untouched issue apart from one someone has edited in Jira. An issue linked to the story without a Publication Marker is not this tool's and is never claimed by it.
- **Configuration**: The set of connection and behaviour settings, each either required or optional-with-default. Its token value is sensitive and must never be emitted.
- **Run Report**: The per-run account of outcomes — created, already existing unchanged, updated, in conflict, failed with reason, created-but-unlinked, retried, and not yet attempted when a run stopped early — the overall verdict of fully successful or partially complete, and which overrides were used: a stale-criteria override with the criteria that had changed, and a set-size override with the number of test cases published.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A story with 5 acceptance criteria goes from issue key to reviewed test cases present in Jira in under 10 minutes of engineer time, including review.
- **SC-002**: Drafting a story with 5 acceptance criteria finishes and presents reviewable drafts in under 2 minutes without engineer intervention.
- **SC-003**: 100% of retrieved acceptance criteria are traceable to at least one generated test case, or are explicitly reported as uncovered.
- **SC-004**: Every generated set contains a positive test case for each acceptance criterion, plus at least one negative and at least one edge test case for the story.
- **SC-024**: 100% of generated test cases state the criterion they cover and the category they belong to.
- **SC-025**: Every generated set above 25 test cases produces a warning naming the count; zero sets above 100 test cases are published without an explicit per-run override, and 100% of such overrides are recorded with the number published.
- **SC-005**: Zero issues are created or modified in Jira before the approval marker is set, across all runs.
- **SC-015**: Zero publishes succeed from a draft file edited after its approval marker was set; 100% of such attempts are refused and reported as needing re-approval.
- **SC-022**: Zero suites are published against substantively changed criteria without an explicit override; 100% of overrides are recorded in the report with the criteria that had changed.
- **SC-023**: Zero publishes are blocked by formatting-only changes to criteria.
- **SC-018**: Zero reviewed draft files are replaced without the engineer explicitly asking; where a replacement does occur, the previous version is recoverable in 100% of cases.
- **SC-019**: Publishing a regenerated draft for an already-published story creates zero duplicate issues.
- **SC-006**: Publishing the same approved set any number of times results in exactly one Jira issue per test case — no duplicates.
- **SC-007**: After any run, successful or failed, zero created test case issues are left unlinked to their story and unreported.
- **SC-008**: Every required setting that is missing or malformed produces a message naming that specific setting; the API token value appears in zero lines of output or logs.
- **SC-009**: A first-time user completes setup by copying the example configuration, filling in their values, and running the tool — with no additional steps and no edits to repository files.
- **SC-010**: 90% of generated test cases are published by the engineer with no edits or only minor wording edits, indicating the drafts are usable as produced.
- **SC-011**: An interrupted publish run, resumed, reaches the same final state as an uninterrupted one in 100% of cases.
- **SC-020**: Zero duplicate issues result from retries, including creates whose outcome was never confirmed.
- **SC-021**: A publish run that meets transient throttling completes without engineer intervention, and when it cannot, it reports every test case's published state so the engineer knows exactly where it stopped.
- **SC-013**: Zero published test case issues that were edited in Jira are overwritten by a later run; 100% of such cases are reported as conflicts naming the issue and the difference.
- **SC-014**: Editing a published test case and re-publishing results in exactly one Jira issue for that test case, updated to match the draft — never a second issue.
- **SC-016**: Re-running a published story from a different machine, or after deleting every local file the tool produced, creates zero duplicate issues.
- **SC-017**: Zero issues not created by this tool are modified, claimed, or reported as published test cases, across all runs.
- **SC-012**: No run requires the engineer to supply a paid language-model credential.

## Assumptions

- **Generation engine**: Test case content is written by the engineer's existing Claude Code session (clarified 2026-10-09). This satisfies the "no paid credential" constraint without a second generator to maintain. Everything around generation is deterministic code, so only the generation step depends on a session.
- **Acceptance criteria location**: Criteria are read from a configured Jira field when that optional setting is present, otherwise from a labelled acceptance criteria section in the description, and the source used is always reported (clarified 2026-10-09). The tool does not guess at unnamed fields, and a story with no criteria in either place is a stop, not a degraded run.
- **Approval mechanism**: Approval is an explicit marker the engineer sets inside the draft file, checked by the publish step, and voided by any later edit to the draft content (clarified 2026-10-09). It is never a timeout, never inferred from the file being saved, and never implied by invoking publish.
- **One issue per test case**: Each test case becomes its own Jira issue, as stated in the brief, rather than one issue holding all test cases.
- **Target project**: Test case issues are created in the configured project when one is set, and otherwise in the same project as the source story.
- **Default test issue type and link relationship**: Documented defaults are applied when these settings are absent, and the tool reports which defaults it used rather than guessing silently.
- **Retry policy**: Throttling and transient errors are retried automatically with increasing waits, honouring Jira's own wait instruction; permanent errors are not retried (clarified 2026-10-09). Retry bounds are a deliberate internal default rather than a user setting, to keep first-time setup to the connection values alone.
- **Duplicate detection and updates**: Identity is a stable label assigned when a test case is first drafted, deliberately not derived from its wording, so edits never read as new test cases (clarified 2026-10-09). Identity and a content fingerprint are stored on the Jira issue itself, so a re-run discovers prior work by reading the story's linked issues and needs no local state. Each matched issue is then left alone, updated, or reported as a conflict.
- **Scope — manual test cases only**: Automated test scripts, test execution, test results, and test cycle or test plan management are out of scope.
- **Scope — one story per run**: Each run processes a single issue key. Bulk processing of many stories is out of scope.
- **Fixed thresholds**: The 25-test-case warning and the 100-test-case publishing limit are built-in defaults rather than settings, and the limit's override is a per-run flag that cannot be made permanent in the configuration file (clarified 2026-10-09). This keeps first-time setup to the connection values alone and keeps an oversized publish a deliberate act every time.
- **Generation depth**: Coverage depth is judged per criterion rather than fixed per category, so a 5-criterion story typically yields roughly 5 to 15 test cases rather than a mechanical 20 (clarified 2026-10-09). This keeps review inside the 10-minute target and avoids filler the engineer would delete.
- **Criteria staleness**: The draft's recorded criterion source text is the baseline for detecting that a story moved on, compared ignoring formatting so that reformatting never blocks a publish (clarified 2026-10-09). Only the acceptance criteria are compared, not the summary or the rest of the description.
- **One draft file per story**: A story has a single current draft file, replaced only on explicit regeneration and backed up when it is (clarified 2026-10-09). Keeping several competing drafts for one story side by side is out of scope.
- **Scope — no write-back to the story**: Beyond the links from created test case issues, the source story is not edited.
- **Single user, local use**: The tool runs locally on one engineer's machine with their own Jira credentials. Shared or server deployment, and multi-user credential management, are out of scope.
- **Jira Cloud only**: The target is Jira Cloud with API token authentication, as stated. Jira Server and Data Center are out of scope.
- **Engineer permissions**: The configured account can read the source story and create and link issues in the target project. The tool reports permission failures clearly but cannot resolve them.
- **Review happens outside the tool**: The engineer reads and edits the draft file in their own editor; the tool does not provide a review interface of its own.
