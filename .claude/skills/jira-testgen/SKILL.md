---
name: jira-testgen
description: Turn a Jira Cloud story into reviewed manual test cases. Use when the user asks to generate, draft, or write manual test cases for a Jira issue key (e.g. "test cases for PROJ-123"), or to publish approved test case drafts to Jira. Not for automated test scripts.
---

# Jira test case generator

You write the test case content. The `jira-testgen` CLI does everything else:
fetching the story, extracting acceptance criteria, allocating identities,
validating the draft, and publishing to Jira.

There is no `generate` subcommand, by design. Test case content exists only
because you wrote it — so if no session is driving, nothing can quietly produce
weaker content instead (FR-036).

**You never approve on the engineer's behalf.** Approval means a human sets
`status: approved` in the draft file. That is the gate this whole design
protects; setting it yourself defeats the feature.

## The flow

### 1. Draft the scaffold

```bash
jira-testgen prepare PROJ-123
```

Exit codes worth branching on:

| Code | Meaning | What to do |
|---|---|---|
| 0 | Scaffold written | Continue to step 2 |
| 5 | No acceptance criteria found | Stop. Report it and name both places it looked. Do not invent criteria. |
| 7 | A draft already exists | **Stop and ask the engineer.** It may hold their review. Only re-run with `--regenerate` if they say so. |
| 2 | Configuration problem | Relay the message; it names the setting. Suggest `jira-testgen doctor`. |
| 4 | Issue unreadable | Relay the message; it names the key. |

### 2. Write the test cases

Read `drafts/PROJ-123.yaml`. It contains the criteria verbatim and an
`identity_allocation` block. Fill in `test_cases:`.

**Coverage rules** (these are requirements, not preferences):

- **One positive test case per criterion, minimum.** Every criterion must appear
  in some test case's `covers`.
- Add `negative`, `boundary`, and `edge` cases **only where the criterion
  warrants one**. A criterion with no meaningful boundary gets no boundary test.
- **No filler.** Do not invent a test case to fill a category, and do not add a
  note explaining why a category is absent.
- The set as a whole must contain **at least one `negative` and at least one
  `edge`** test case.
- Typical result: 1–3 test cases per criterion. A 5-criterion story usually
  lands between 5 and 15, not a mechanical 20.

**Identity rules:**

- Take identities in order from `identity_allocation`: `prefix` +
  `next_ordinal`, zero-padded to three (`PROJ-123-TC-001`).
- **Never edit, renumber, or reorder an existing identity.** Identity links a
  draft test case to its Jira issue; changing one creates a duplicate.
- If `previously_published` is present, those test cases already exist in Jira.
  When you write the equivalent test case, **reuse that identity** so publishing
  updates the existing issue instead of creating a second one.

**Each test case must be self-contained** (FR-011). Someone who has never read
the story must be able to execute it. Write out the actual data, the actual
steps, and the actual expected result. Never write "as described in the story",
"see the ticket", "as above", or "TBD" — `validate` rejects those, and rightly.

Shape:

```yaml
test_cases:
  - identity: PROJ-123-TC-001
    category: positive          # positive | negative | boundary | edge
    covers: [AC-1]
    summary: Request reset link with a registered email address
    preconditions: |
      A user account exists with the email address qa.user@example.com.
    steps:
      - "Open the password reset page."
      - "Enter qa.user@example.com in the email field."
      - "Select Send reset link."
    expected_results: |
      A confirmation message states that a reset link has been sent.
      The email arrives at qa.user@example.com and contains a reset link.
```

Keep `summary` under 255 characters — Jira rejects anything longer.

### 3. Validate

```bash
jira-testgen validate PROJ-123
```

Exit 6 means something is wrong; the message names the offending test case or
criterion. Fix it and re-run. Do not proceed to step 4 until this exits 0.

### 4. Hand over and stop

Report to the engineer:

- the draft file path;
- the criterion-to-test-case coverage map;
- how many test cases you wrote, and anything `validate` warned about.

Then say, in plain terms: **to approve, set `status: approved` in
`drafts/PROJ-123.yaml`, then run `jira-testgen publish PROJ-123`.**

**Stop here.** Do not publish, and do not touch the `approval:` block.

### 5. Publish, only when explicitly approved

Only after the engineer says they have approved:

```bash
jira-testgen publish PROJ-123
```

Then relay the report as it stands. Codes:

| Code | Meaning | What to do |
|---|---|---|
| 0 | Everything published | Report the created issue keys |
| 6 | Not approved, or approval voided by a later edit | Relay it; the engineer must approve again |
| 8 | The story's criteria changed since drafting | Relay which criteria changed. Suggest regenerating. Use `--allow-stale-criteria` only if the engineer asks. |
| 9 | More than 100 test cases | Relay it. Use `--allow-large` only if the engineer asks. |
| 10 | Partially complete | Report what was created, what failed, and any conflicts, with reasons |
| 11 | Retries exhausted | Report what was published and what was not; a re-run resumes safely |

## Rules

- Never create or modify anything in Jira before the engineer has approved.
- Never edit the `approval:` block, in either direction.
- Never edit `source_text` under `criteria:` — it is the baseline for noticing
  that the story has moved on.
- Never invent acceptance criteria. If there are none, say so and stop.
- On exit 7, ask before regenerating. That file may be someone's afternoon.
- Re-running `publish` is safe: it recognises what already exists and never
  duplicates. If in doubt, re-run rather than hand-fixing Jira.
