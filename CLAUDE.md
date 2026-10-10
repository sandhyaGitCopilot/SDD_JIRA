# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -e ".[dev]"          # editable install + pytest, responses, ruff
pytest                           # whole suite
pytest tests/unit/test_decide.py # one file
pytest -k "conflict or stale"    # by name
pytest tests/integration/test_publish.py::test_twelve_test_cases_become_twelve_issues
ruff check src tests             # must be clean before a task is marked done
jira-testgen doctor --issue PROJ-123   # or: python -m jira_testgen
```

`pytest.ini` already sets `addopts = -q`. Passing another `-q` yields `-qq`, which
suppresses the pass/fail summary line — run bare `pytest` to see counts.

`doctor`, `prepare` and `validate` never write to Jira; only `publish` does.
`validate` loads no configuration at all and works offline.

## Architecture

A four-layer package under `src/jira_testgen/`, and the layering is load-bearing:

- **`cli.py`** — argparse shell. Parses, calls a command module, maps exceptions to
  exit codes via `ExitCode`. Holds no logic worth testing on its own. There is
  deliberately **no `generate` command**: test case content is written by a Claude Code
  session into the scaffold, so no code path can produce content another way.
- **Command modules** — `prepare.py`, `publish.py`, `doctor.py`. Orchestration.
- **Pure logic** — `criteria.py`, `limits.py`, `draft/` (`schema`, `validate`,
  `fingerprint`, `identity`, `backup`). No network, no mocks needed to test it.
- **`jira/`** — the only package allowed to perform network I/O. `client.py` is the
  only module in the project that speaks HTTP.

Keeping judgement out of the shell is why most of the suite needs no mocks. Adding
network I/O outside `jira/` breaks the constitution's Principle I.

### The publish decision engine

`publish.py:decide()` is the heart of the tool. Every verdict is derived from **Jira's
state alone**, from two independent comparisons:

| issue vs. stored | draft vs. stored | outcome |
|---|---|---|
| matches | unchanged | `unchanged` |
| matches | changed | `update` |
| differs | either | `conflict` (never resolved automatically) |

The issue's `updated` timestamp is never consulted — automations, transitions and
comments all bump it and every one would produce a phantom conflict.

`publish_draft()` runs five gates before anything is written (valid draft → approval
still applies → target project/issue type/link type usable → criteria not moved on →
within the ceiling). A permanent failure on one test case is reported and the loop
continues; a Jira-wide condition stops with a resumable report.

### How duplicates are avoided: two markers, zero local state

Each created issue carries a **label** `tcgen-id-<identity>` (found via JQL) and a Jira
**issue property** `com.tcgen.testcase` (`jira/properties.py`) holding the fingerprint of
what the tool last wrote. A re-run reads both back from Jira, so nothing in `drafts/` is
needed to resume, re-run, or run from another machine. An issue linked to the story that
this tool did not create is never touched, matched, or counted.

Identity (`draft/identity.py`) is `<STORY-KEY>-TC-<NNN>`, derived from position, **never**
from wording — if identity tracked content, every edit would look like a new test case and
publish a duplicate. Allocation starts past the highest ordinal already published.

### Fingerprints

`draft/fingerprint.py` collapses all whitespace before hashing, so reformatting a draft
does not void an approval while changing any word does. Two fingerprints, one
canonicalization: the **draft** hash covers only `criteria` and `test_cases` (the
`approval` block is excluded by construction — otherwise approving would instantly void
the approval it just granted), and the **issue** hash covers rendered issue content
(summary + description text), not draft fields, to avoid reverse-parsing ADF.

### Errors, exit codes, retries

`errors.py` is the single place where "retry this" vs. "never retry this" is decided.
Three classes — `TransientError`, `PermanentError`, `UserError` — plus subclasses that
carry their own `exit_code`. Each failure class has a distinct exit code because callers
(including the skill) branch on exit codes and must never parse prose. Note `409` is
deliberately permanent, and `AmbiguousResultError` (a timed-out POST) must never be
blindly retried — the caller looks for the identity first.

Add a new failure mode by adding an error class with its `exit_code`, and update
`contracts/cli.md` and the README's exit-code table together.

### Secret redaction

Two mechanisms, both central, neither optional:

- `config.SecretValue` wraps the token with no `__repr__`, `__str__`, `__format__` or
  pickle path that yields it. `.reveal()` is called in exactly one place: the auth header.
- `logging_setup.RedactingFormatter` scrubs every record that any handler formats, and
  `scrub()` is exported so report rendering and error printing route through the same
  function.

**Redacting at a call site is forbidden.** A rule that depends on whoever writes the next
log line will be broken by the next log line — this project already had that leak once.

### Reports

`report.py` holds two invariants: every test case in the approved set appears exactly
once, and the verdict is *derived*, never set. Any conflict, failure, orphan, unlinked or
unattempted case makes the run `partial` (exit 10). There is no code path that can call a
flawed run a success.

## Testing

Three layers, and a test belongs in exactly one:

- `tests/unit/` — pure logic, **no mocks and no network**.
- `tests/contract/` — the shape of anything crossing a boundary this project does not
  control, asserted against recorded real payloads wherever obtainable.
- `tests/integration/` — whole flows, including sequences that only break on a second run.

Two harnesses: `conftest.StubJira` is read-only and records calls (which is how "nothing
was written to Jira" is asserted rather than assumed); `fake_jira.FakeJira` accepts
creates, links, updates and property writes, keeps state, and can be told to fail specific
calls — failure injection is what makes the partial-failure, unlinked and
retry-exhaustion paths testable at all.

Tests are written before the implementation and observed failing first. A requirement is
not implemented until a test would fail if it regressed.

Beware tests that assert the *absence* of a file whose existence is the documented design
(`.env` after setup, files in `drafts/` after `prepare`). Assert that such a path is
**excluded and untracked**, not missing — see `tests/unit/test_gitignore.py`.

## Constraints that are not negotiable

From `.specify/memory/constitution.md` (v1.0.0) — where it and a design document disagree,
the constitution wins and the document is corrected:

- **No paid model credential** may be required, requested, or accepted. Adding an LLM SDK
  to `pyproject.toml` is forbidden.
- **Three runtime dependencies** (`requests`, `PyYAML`, `python-dotenv`). A fourth needs
  the justification Principle VI demands.
- **Python 3.11+**, and file operations must not assume POSIX semantics — this is
  developed on Windows.
- **Nothing destructive or outward-facing happens implicitly.** An override must be a
  per-run flag or a marker a human set, must be recorded in the report, and must **not**
  be settable in `.env`.
- **No local state** when Jira can hold it.
- **Every error message names its subject** — the setting, the file, or the test case
  identity. This is enforced by `tests/unit/test_error_messages.py`, not by review.

## Spec-driven workflow

`specs/001-jira-test-case-generator/` is the source of intent: `spec.md` (FR-xxx, SC-xxx,
and a `## Clarifications` log of resolved decisions), `plan.md`, `tasks.md`,
`data-model.md`, `contracts/`, `quickstart.md`, `validation-results.md`. Code comments
cite the requirement they satisfy (`FR-043`, `SC-006`) — keep that habit; it is how a
later reader tells a load-bearing mechanism from an accident.

`tasks.md` is **append-only**. `/speckit-converge` appends a new numbered Convergence
phase; it never rewrites, renumbers or deletes an existing task, and never edits `spec.md`
or `plan.md`. Mark finished tasks `[X]` in place.

## The `jira-testgen` skill

`.claude/skills/jira-testgen/SKILL.md` governs generating test case content into a draft.
The binding rules: **never set `status: approved` on the engineer's behalf**; never edit
the `approval:` block or `criteria: source_text`; take identities from
`identity_allocation` and never renumber them; on exit 7 (draft exists) stop and ask
rather than regenerating; at least one positive case per criterion, plus at least one
negative and one edge overall, with no filler; summaries under 255 characters; and each
test case must be executable by someone who has not read the story — no "as above",
"see the ticket", or "TBD".
