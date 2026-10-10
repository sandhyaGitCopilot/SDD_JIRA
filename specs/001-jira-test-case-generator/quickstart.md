# Quickstart & Validation Guide: Jira Test Case Generator

**Feature**: `001-jira-test-case-generator` | **Date**: 2026-10-09

How to set the tool up, and the scenarios that prove the feature works end to end. Each scenario maps to requirements and success criteria in [spec.md](./spec.md) — this is the checklist that says the feature is done, not a description of how to build it.

---

## Setup

```bash
pip install -e .
cp .env.example .env     # then fill in your values
jira-testgen doctor
```

`.env.example` ships with every supported setting and placeholder values:

```ini
JIRA_BASE_URL=https://your-site.atlassian.net
JIRA_EMAIL=you@example.com
JIRA_API_TOKEN=your-api-token-here

# Optional
JIRA_PROJECT_KEY=              # default: the source story's own project
JIRA_TEST_ISSUE_TYPE=          # default: Task
JIRA_LINK_TYPE=                # default: Relates
JIRA_AC_FIELD=                 # e.g. customfield_10040; unset reads criteria from the description
```

Get an API token from <https://id.atlassian.com/manage-profile/security/api-tokens>.

`.gitignore` must contain `.env` and `drafts/` before the first commit.

**Setup is validated when** `doctor` reports all checks passing, naming the defaults it applied and never printing the token (SC-008, SC-009).

---

## The normal flow

```bash
# 1. Draft (writes nothing to Jira)
jira-testgen prepare PROJ-123
#    then let the Claude Code skill fill in the test cases

# 2. Review
jira-testgen validate PROJ-123
#    open drafts/PROJ-123.yaml, read, edit, delete what you do not want

# 3. Approve — set `status: approved` in drafts/PROJ-123.yaml

# 4. Publish
jira-testgen publish PROJ-123
```

---

## Validation scenarios

Each is runnable, with a stated expected outcome. Jira-mutating scenarios should run against a scratch project.

### A. Happy path — 5 criteria to published test cases

**Setup**: a story with 5 acceptance criteria.

```bash
jira-testgen prepare PROJ-123     # scaffold with 5 criteria, identities, empty slots
# skill fills test cases
jira-testgen validate PROJ-123    # coverage map: every criterion covered, ≥1 positive each
# set status: approved
jira-testgen publish PROJ-123
```

**Expect**: one Jira issue per test case, each linked to `PROJ-123`; report lists every test case as `created` with its key; verdict `success`. End to end within 10 minutes of engineer time, drafting itself under 2 minutes.

**Covers**: FR-001 – FR-008, FR-018, FR-019, FR-021; SC-001, SC-002, SC-003, SC-004.

### B. Nothing reaches Jira before approval

```bash
jira-testgen prepare PROJ-123
jira-testgen publish PROJ-123     # expect exit 6
```

**Expect**: refusal naming `drafts/PROJ-123.yaml` and the `status: approved` marker. Zero issues and zero links created — verify in Jira.

**Covers**: FR-013, FR-015, FR-016; SC-005.

### C. Editing after approval voids it

```bash
# approve, then edit any test case's steps
jira-testgen publish PROJ-123     # expect exit 6
```

**Expect**: refusal reporting that the drafts changed after approval; `status` reset to `draft` in the file; nothing created. Re-approving and publishing then succeeds.

**Covers**: FR-043, FR-044, FR-046; SC-015.

### D. Re-publishing creates no duplicates

```bash
jira-testgen publish PROJ-123     # again, unchanged
```

**Expect**: zero new issues; every test case reported `unchanged` with its existing key; Jira issue count identical.

**Covers**: FR-026, FR-029; SC-006.

### E. Editing a published test case updates it in place

```bash
# edit one test case, re-approve
jira-testgen publish PROJ-123
```

**Expect**: that one issue `updated` and named in the report; no second issue; all others `unchanged`.

**Covers**: FR-025, FR-038, FR-040; SC-014.

### F. A Jira-side edit is a conflict, never an overwrite

**Setup**: edit a published test case issue's description directly in Jira, then change the same test case in the draft and re-approve.

**Expect**: `conflict` naming the issue and the differing fields; **both sides unchanged**; verdict `partial`. Resolving either side and re-running clears it.

**Covers**: FR-039, FR-041, FR-042; SC-013.

### G. Re-running `prepare` will not destroy a reviewed draft

```bash
jira-testgen prepare PROJ-123                  # expect exit 7
jira-testgen prepare PROJ-123 --regenerate
```

**Expect**: first call refuses, naming the existing file, leaving it byte-for-byte unchanged. With `--regenerate`: the file being replaced is named, `drafts/PROJ-123.yaml.bak` exists with the old content, the new draft is `status: draft`, and identities already published are reused — so publishing it creates **zero** duplicates.

**Covers**: FR-047 – FR-050; SC-018, SC-019.

### H. Changed criteria block publishing

**Setup**: approve a draft, then reword one acceptance criterion in Jira.

```bash
jira-testgen publish PROJ-123                            # expect exit 8
jira-testgen publish PROJ-123 --allow-stale-criteria     # proceeds
```

**Expect**: refusal naming the changed criterion and pointing at regeneration. With the override, publishing proceeds and the report records that the override was used and which criteria had changed. Separately, **reformatting** a criterion (whitespace or markup only) must *not* block.

**Covers**: FR-056 – FR-060; SC-022, SC-023.

### I. No acceptance criteria is a stop

**Setup**: a story with no criteria in `JIRA_AC_FIELD` or a labelled description section.

```bash
jira-testgen prepare PROJ-404     # expect exit 5
```

**Expect**: a stop reporting that none were found, naming both places searched, and **no draft file written**.

**Covers**: FR-005.

### J. Resume after a partial failure

**Setup**: simulate a failure partway through publishing 12 test cases (mocked Jira in the integration suite).

**Expect**: the report names which were published and which were not; re-running creates only the missing ones; final state is exactly 12 linked issues — identical to an uninterrupted run.

**Covers**: FR-027, FR-054; SC-011.

### K. Throttling is retried, not surfaced

**Setup**: mocked Jira returning 429 with `Retry-After`, then success.

**Expect**: the tool waits as instructed and completes without engineer intervention; the report names the retried test cases. A create that times out but actually succeeded is **adopted, not duplicated**.

**Covers**: FR-051 – FR-055; SC-020, SC-021.

### L. Config errors name the setting; the token never leaks

```bash
# blank each required setting in turn
jira-testgen doctor               # expect exit 2, naming that setting
```

**Expect**: each missing or malformed setting named exactly as it appears in `.env`, reported **before** any network call. Bad credentials give exit 3, distinguishable from exit 2. Across every subcommand run to failure, the token appears in zero bytes of stdout, stderr, and any log file.

**Covers**: FR-030 – FR-034; SC-008.

### M. Foreign linked issues are never touched

**Setup**: link an unrelated issue (a bug, or a manually written test) to `PROJ-123`, then publish.

**Expect**: that issue is not modified, not matched to any test case, and not counted as published. Matching never happens by wording.

**Covers**: FR-026c; SC-017.

### N. Size thresholds

**Setup**: a story generating 28 test cases, and one generating 120.

**Expect**: 28 produces a warning naming the count and publishes normally. 120 refuses with exit 9 until `--allow-large`, which publishes and records the override and the count in the report.

**Covers**: FR-064 – FR-068; SC-025.

### O. No local state is required

```bash
rm -rf drafts/
jira-testgen prepare PROJ-123 --regenerate
# approve, then publish
```

**Expect**: zero duplicates. Everything needed to recognise published work was read back from Jira.

**Covers**: FR-026a, FR-026b; SC-016.

---

## Done when

- [ ] Scenarios A – O all pass
- [ ] `doctor` passes on a clean checkout after only copying `.env.example` and filling three values
- [ ] `.env` and `drafts/` are gitignored and the real `.env` is untracked
- [ ] The API token appears in zero bytes of any output stream or log across all failing runs
- [ ] Publishing twice, from two different machines, yields one issue per test case

SC-010 — 90% of generated test cases published with no or only minor edits — is a human-judgement measure and should be sampled over real usage rather than gated here. It is flagged as the spec's weakest criterion in [checklists/requirements.md](./checklists/requirements.md).
