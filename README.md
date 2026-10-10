# jira-testgen

Turn a Jira Cloud story into reviewed, ready-to-use manual test cases.

You give it an issue key. It reads the story's acceptance criteria, your Claude
Code session writes the test cases, you review and approve them in a file, and
then it creates them in Jira as issues linked back to the story.

Nothing is created in Jira until you explicitly approve. Re-running is safe: it
recognises what already exists and never creates a duplicate.

No paid language-model credential is needed or accepted. Test case content is
written by your existing Claude Code session; everything else is ordinary code.

## Setup

```bash
pip install -e .
cp .env.example .env     # then fill in three values
jira-testgen doctor
```

That is the whole setup. `doctor` checks your settings and your Jira site and
writes nothing.

### Settings

`.env` is gitignored and must never be committed. Your API token is never
printed, logged, or written to any file.

| Setting | Required | Default when blank |
|---|---|---|
| `JIRA_BASE_URL` | yes | — (e.g. `https://your-site.atlassian.net`) |
| `JIRA_EMAIL` | yes | — the account the tool acts as |
| `JIRA_API_TOKEN` | yes | — [create one here](https://id.atlassian.com/manage-profile/security/api-tokens) |
| `JIRA_PROJECT_KEY` | no | the source story's own project |
| `JIRA_TEST_ISSUE_TYPE` | no | `Task` |
| `JIRA_LINK_TYPE` | no | `Relates` |
| `JIRA_AC_FIELD` | no | unset — criteria are read from the description |

Every run reports which defaults it applied, so you are never guessing.

**`JIRA_TEST_ISSUE_TYPE` defaults to `Task`,** not `Test`, because a dedicated
`Test` issue type only exists on sites with a test-management app installed. If
your project has one, set it.

**`JIRA_AC_FIELD`** is for teams who keep acceptance criteria in a dedicated
custom field. Find its id with `jira-testgen doctor --issue PROJ-123`. Leave it
blank and criteria are read from a section of the description headed
"Acceptance Criteria". The tool never guesses at an unnamed field.

## Usage

```bash
# 1. Draft. Reads the story, writes drafts/PROJ-123.yaml. Writes nothing to Jira.
jira-testgen prepare PROJ-123

# 2. Your Claude Code session fills in the test cases, then:
jira-testgen validate PROJ-123

# 3. Review drafts/PROJ-123.yaml. Edit freely. Delete any test case you
#    do not want. Then set `status: approved` in that file.

# 4. Publish.
jira-testgen publish PROJ-123
```

Ask your Claude Code session for "test cases for PROJ-123" and it will drive
steps 1–2 for you, then stop and wait for your review.

### Approving

Approval is one word. Open the draft file and change:

```yaml
approval:
  status: draft        # -> approved
```

**Editing the draft after approving voids the approval.** The tool notices,
refuses to publish, and resets the file to `draft` so you approve the content
you actually meant. Reformatting — whitespace, indentation — does not count as
an edit.

### Drafts

One draft file per story, at `drafts/PROJ-123.yaml`. The directory is
gitignored; nothing in it is needed to resume or re-run, because everything the
tool needs to recognise its own work is stored in Jira.

The lifecycle:

```text
(nothing)
   │ prepare PROJ-123
   ▼
scaffold ── session writes test_cases ──▶ draft
                                            │ you set status: approved
                                            ▼
                                         approved ── publish ──▶ issues in Jira
                                            │
                        you edit it again ──┴──▶ approval void, reset to draft
```

Three things to know about editing a draft:

- **Approving is a one-word edit.** Change `status: draft` to `status: approved`.
  You never type a fingerprint; the tool records the baseline itself on the
  first approved run.
- **Deleting a test case is how you reject it.** Remove its whole entry. It is
  never created. If it was already published, the issue is left in Jira and
  reported as an orphan so you can decide whether to delete it there.
- **Reformatting is not editing.** Whitespace and indentation changes do not
  void an approval. Changing any word does.

Re-running `prepare` on a story that already has a draft is **refused**, because
that file may hold your review. To replace it deliberately:

```bash
jira-testgen prepare PROJ-123 --regenerate
```

The previous version is kept as `drafts/PROJ-123.yaml.bak` — **one generation,
not a history** — the new draft starts unapproved, and identity numbering
continues past anything already published so re-publishing cannot collide.

### What happens when you publish again

Re-running `publish` is always safe. Each test case gets one of these outcomes,
decided entirely from what is in Jira:

| Outcome | When | What the tool does |
|---|---|---|
| `created` | No issue carries this identity | Creates and links it |
| `unchanged` | Draft and issue both match what was last written | Nothing |
| `updated` | You edited the draft; nobody touched the issue | Updates the issue in place |
| `conflict` | Somebody edited the issue in Jira | **Nothing.** Reports which fields differ |
| `relinked` | The issue exists but its link to the story is missing | Adds the link |
| `recreated` | The issue was deleted | Creates it again |
| `adopted` | A create timed out but had actually landed | Adopts the existing issue |
| `orphaned_draft` | Published, but no longer in your draft | Leaves it; reports it |
| `failed` | This one test case cannot be published | Reports the reason, continues with the rest |

A `conflict` is never resolved for you. Either restore the issue in Jira, or
change the draft to match it, then re-run — the verdict is recomputed from
scratch every time, so resolving either side clears it.

Any `conflict`, `failed`, orphaned or unlinked issue makes the run **partially
complete** (exit 10) rather than a success, so a flawed run never reports a
clean bill of health.

## Commands

| Command | What it does | Writes to Jira |
|---|---|---|
| `doctor` | Checks settings, credentials, issue type, link type, field, permissions | no |
| `prepare KEY` | Fetches the story and writes the draft scaffold | no |
| `validate KEY` | Checks a draft's structure and coverage, offline | no |
| `publish KEY` | Creates or updates the test case issues | **yes** |

Useful flags: `--json` for machine-readable output, `--verbose` / `--debug` for
more logging, `--log-file PATH` to keep a log. Logs go to stderr so stdout stays
pipeable.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 2 | Configuration problem — the message names the setting |
| 3 | Jira rejected the credentials |
| 4 | The issue does not exist or cannot be read |
| 5 | No acceptance criteria found |
| 6 | Draft not approved, approval voided, or invalid |
| 7 | A draft already exists (use `--regenerate`) |
| 8 | The story's criteria changed since drafting |
| 9 | More than 100 test cases (use `--allow-large`) |
| 10 | Partially complete — see the report |
| 11 | Retries exhausted; re-run to resume |

Codes 2 and 3 are deliberately different: "fix your `.env`" and "Jira said no"
need different responses.

## How it avoids duplicates

Each created issue carries two markers: a label holding the test case's
identity, and a Jira issue property holding a fingerprint of what the tool last
wrote. A re-run reads those back from Jira, so it knows exactly what exists.

Nothing is stored locally. Re-running from a different machine, or after
deleting `drafts/`, produces no duplicates. An issue linked to your story that
this tool did not create is never touched, matched, or counted.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check src tests
```

Tests are unit (pure logic, no mocks), contract (recorded Jira payload shapes),
and integration (whole flows against a fake Jira). The design documents live in
`specs/001-jira-test-case-generator/`.
