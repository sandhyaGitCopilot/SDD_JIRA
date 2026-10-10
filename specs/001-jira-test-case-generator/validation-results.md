# Validation Results: Jira Test Case Generator

**Feature**: `001-jira-test-case-generator` | **Recorded**: 2026-10-10 | **Task**: T087

Results of running the [quickstart](./quickstart.md) scenarios A–O.

## What was and was not run

**Read this before treating the table below as a pass.** Every scenario was
executed against a **fake Jira** (an in-process stub implementing the endpoints
this tool uses), not against a real Atlassian site, because this environment has
no Jira credentials. That difference matters for a specific set of risks:

- **Payload shapes.** The fake accepts what the tool sends. A real site may
  reject a field, require a different issue-type name, or return Atlassian
  Document Format the extractor has not seen. `contracts/test_adf.py` notes the
  same gap: its fixtures follow Atlassian's documented schema rather than being
  captured from a live response.
- **Permissions and configuration.** `JIRA_AC_FIELD` ids, available issue types
  and link types, and whether the account may write issue properties are all
  site-specific. `jira-testgen doctor` exists to check exactly these, and is the
  first thing to run against a real site.
- **Timing and rate limits.** Retry and throttling behaviour is verified against
  injected responses, including `Retry-After`. Real burst limits may differ.
- **JQL index latency.** The identity lookup allows a settle delay before
  concluding an issue does not exist. The fake answers instantly, so the race
  this guards against is reasoned about rather than observed.

**Remaining work for T087**: run `jira-testgen doctor --issue <KEY>` and then
scenarios A, B, G, H and M against a scratch project on the target site, and
record real payloads into `tests/contract/`. Nothing below substitutes for that.

## Scenario results (against the fake)

| # | Scenario | Covered by | Result |
|---|---|---|---|
| A | Happy path — 5 criteria to published test cases | `test_prepare.py`, `test_publish.py`, plus a CLI walkthrough | pass |
| B | Nothing reaches Jira before approval | `test_publish_gate.py` | pass |
| C | Editing after approval voids it | `test_publish_voided.py` | pass |
| D | Re-publishing creates no duplicates | `test_republish.py` | pass |
| E | Editing a published test case updates it in place | `test_update.py` | pass |
| F | A Jira-side edit is a conflict, never an overwrite | `test_conflict.py` | pass |
| G | Re-running `prepare` will not destroy a reviewed draft | `test_prepare_regenerate.py` | pass |
| H | Changed criteria block publishing | `test_publish_stale.py` | pass |
| I | No acceptance criteria is a stop | `test_prepare_no_criteria.py` | pass |
| J | Resume after a partial failure | `test_resume.py` | pass |
| K | Throttling is retried, not surfaced | `test_throttling.py`, `test_ambiguous_create.py` | pass |
| L | Config errors name the setting; the token never leaks | `test_config.py`, `test_config_errors.py`, `test_no_token_leak.py` | pass |
| M | Foreign linked issues are never touched | `test_foreign_issues.py` | pass |
| N | Size thresholds | `test_publish_limits.py` | pass |
| O | No local state is required | `test_no_local_state.py` | pass |

Totals: **416 automated tests passing**, plus four end-to-end CLI walkthroughs
(drafting, publish exit codes, `doctor`, update/conflict).

## The "Done when" checklist from quickstart.md

- [x] Scenarios A–O all pass — **against the fake**; see the caveat above
- [ ] `doctor` passes on a clean checkout after only copying `.env.example` —
      needs a real site
- [x] `.env` and `drafts/` are gitignored and no real `.env` is present —
      enforced by `tests/unit/test_gitignore.py`
- [x] The API token appears in zero bytes of any output stream or log across all
      failing runs — `tests/integration/test_no_token_leak.py`, 49 tests
      covering every subcommand, verbosity and `--json` path
- [x] Publishing twice, from two different locations, yields one issue per test
      case — `tests/integration/test_no_local_state.py`

## Deviations found while validating

Recorded here because they are differences between the design documents and what
was built, not defects:

1. **`data-model.md` describes `recreate` as if a local ledger existed.** Once
   clarification 5 moved all state onto the Jira issues, a fully deleted issue
   carries its marker away with it, so there is nothing left to discover and the
   test case is simply created again. The `recreate` decision now fires only in
   the narrow race where an issue vanishes mid-run. FR-028's actual requirement
   — never report a missing issue as present — holds in both cases, and both are
   tested.
2. **`contracts/draft-file.md` understates the fingerprint's normalization.** It
   says trailing whitespace is stripped and line endings normalized, while also
   requiring that reflowing a block scalar leave the hash unchanged. Those cannot
   both hold, so the implementation collapses all internal whitespace, which
   satisfies the stated outcome. The contract should say so.
3. **The stored fingerprint covers *rendered* content** (issue summary plus
   description text), not the draft's fields. This avoids reverse-parsing ADF
   back into test case fields — fragile exactly where a wrong answer means either
   a phantom conflict or overwriting someone's work.
4. **Target pre-flight failures exit 2, not 1.** A `JIRA_TEST_ISSUE_TYPE` the
   project will not accept is a mis-set setting, and the message names it;
   reporting it as an internal error would read as a tool bug.
5. **`validate` loads no configuration.** It works entirely offline, so a draft
   can be checked without credentials. A malformed `.env` therefore does not
   produce exit 2 from `validate`.

## Known limitations

- **SC-010** (90% of generated test cases published with no or only minor edits)
  is a human-judgement measure and is not gated here. Sample it over real usage.
  It was flagged as the spec's weakest criterion from the start.
- **Concurrent publishing** by two engineers at the same instant is not
  prevented. Sequential re-runs are safe; a true simultaneous race is narrowed
  by the identity lookup but not eliminated, and the spec does not require it.
