# Implementation Plan: Jira Test Case Generator

**Branch**: `001-jira-test-case-generator` | **Date**: 2026-10-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-jira-test-case-generator/spec.md`

## Summary

A local command-line tool, driven by a Claude Code skill, that turns one Jira Cloud story into reviewed manual test cases and publishes them back as linked issues.

The deterministic half is a Python CLI: it fetches the story, extracts acceptance criteria, assigns each prospective test case a stable identity, writes a YAML draft file, validates that draft, and publishes it to Jira with retry, conflict detection, and a per-test-case report. The judgement half — writing the actual test case wording — is done by the engineer's Claude Code session, which fills the draft scaffold the CLI produced. No paid model credential is involved anywhere.

Two design choices carry most of the spec's guarantees. First, **Jira is the only source of truth for what has been published**: each created issue carries a `tcgen-id-*` label (so it can be found by JQL) and a Jira *issue property* holding a content fingerprint (so a later run can tell an untouched issue from one a person edited). Nothing about publishing is stored locally, which is what makes re-runs safe from another machine and after any local file is deleted. Second, **every destructive or irreversible step is refused by default and requires a deliberate per-run action**: replacing a reviewed draft, publishing against changed criteria, and publishing more than 100 test cases.

## Technical Context

**Language/Version**: Python 3.11+ (matches the repository's existing `.specify/scripts/python/` tooling; `init-options.json` sets `"script": "py"`)

**Primary Dependencies**: `requests` (Jira REST), `PyYAML` (draft files), `python-dotenv` (configuration). Standard library `argparse` for the CLI, `hashlib` for fingerprints. No LLM SDK — generation runs in the Claude Code session.

**Storage**: Files only. YAML draft files under `drafts/` (gitignored), with `.bak` backups. All publishing state lives in Jira itself, never locally.

**Testing**: `pytest` with `responses` for Jira HTTP mocking; contract tests against recorded Jira payloads; one optional live smoke test gated on real credentials being present.

**Target Platform**: Local developer machines — Windows, macOS, Linux. Windows is the primary development platform here, so paths and file replacement must not assume POSIX semantics.

**Project Type**: CLI tool plus a Claude Code skill that orchestrates it. Single project.

**Performance Goals**: Drafting presents a reviewable file in under 2 minutes (SC-002). Publishing 12 test cases completes within a few minutes including retries (SC-001). Review of a 5-criterion story fits a 10-minute engineer budget.

**Constraints**: No paid language-model credential (FR-010). The API token must never reach stdout, stderr, logs, reports, or draft files (FR-034). Non-generation commands must run without a Claude Code session (FR-037). Thresholds 25 and 100 are fixed defaults, not settings (FR-066).

**Scale/Scope**: One story per run. Up to ~40 acceptance criteria; a hard ceiling of 100 test cases per story, overridable per run. Single user, local credentials.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is **an uninstantiated template** — every principle is still a `[PRINCIPLE_N_NAME]` / `[PRINCIPLE_N_DESCRIPTION]` placeholder, and the governance, version, and ratification fields are unfilled. There are therefore no ratified project principles to gate this design against.

**Gate result: PASSED VACUOUSLY** — not because the design was checked and complied, but because there is nothing to check it against. This is worth stating plainly rather than reporting a clean pass.

To keep the gate meaningful anyway, the design was held against the principles the constitution template offers as examples, which are also ordinary good practice for a tool like this:

| Example principle | How this design stands |
|---|---|
| Library-first, self-contained | Core logic sits in `src/jira_testgen/` as an importable package; the CLI and the Claude Code skill are thin shells over it. |
| CLI interface, text in / text out | Every capability is a subcommand with human-readable output and a `--json` report mode; errors go to stderr with non-zero exit codes. |
| Test-first | Phase 1 produces contracts before implementation; the fingerprint, criteria-extraction, identity, and error-classification rules are all pure functions designed to be unit-tested ahead of the Jira layer. |
| Integration testing | Contract tests cover the Jira request/response shapes and the draft file schema — the two boundaries where breakage is silent. |
| Observability | A single structured log stream with mandatory token redaction at the formatter, so redaction cannot be forgotten at a call site. |
| Simplicity / YAGNI | Three runtime dependencies, no database, no local state, no cache. |

**Recommendation**: run `/speckit-constitution` to fill the constitution before `/speckit-implement`, so later features are gated against real principles. This plan does not depend on that happening.

### Post-design re-check (after Phase 1)

Re-evaluated against the same example principles once the contracts existed. No violations introduced, and two points are worth recording:

- **Library-first held.** `jira/` is the only package doing network I/O, so criteria extraction, fingerprinting, identity, validation, and limits are all pure functions — testable with no mocks at all. That was a design goal, and the contracts confirm it survived.
- **One complexity was added deliberately** — storing identity in a label *and* the fingerprint in an issue property. It is recorded in Complexity Tracking below with the requirement that forces it. No gate demanded the justification; it is logged because a future reader will otherwise see it as redundant.

No `NEEDS CLARIFICATION` markers remain in the Technical Context: all 16 unknowns are resolved in [research.md](./research.md), and the four that depend on the engineer's own Jira site are listed there as `doctor` checks rather than left open.

## Project Structure

### Documentation (this feature)

```text
specs/001-jira-test-case-generator/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── cli.md           # Subcommands, flags, exit codes
│   ├── draft-file.md    # YAML draft schema + approval/fingerprint rules
│   └── jira-integration.md  # Endpoints, identity/fingerprint storage, error classes
├── checklists/
│   └── requirements.md  # Spec quality checklist (from /speckit-specify)
└── tasks.md             # Created by /speckit-tasks, not here
```

### Source Code (repository root)

```text
src/jira_testgen/
├── __init__.py
├── __main__.py              # python -m jira_testgen
├── cli.py                   # argparse subcommands: doctor, prepare, validate, publish
├── config.py                # .env load, required/optional validation, redaction registry
├── errors.py                # PermanentError vs TransientError vs UserError taxonomy
├── logging_setup.py         # single log stream; redacting formatter
├── criteria.py              # extract from AC field or description section; normalize
├── limits.py                # 25-test-case warning, 100-test-case ceiling
├── report.py                # Run Report assembly and rendering (text + --json)
├── publish.py               # preflight, create/update/conflict/skip, resume, linking
├── draft/
│   ├── __init__.py
│   ├── schema.py            # DraftSet / TestCase models, YAML load + dump
│   ├── identity.py          # identity minting, parsing, label mapping
│   ├── fingerprint.py       # content + criteria normalization and hashing
│   ├── backup.py            # atomic replace with .bak retention
│   └── validate.py          # structure, coverage, approval-state checks
└── jira/
    ├── __init__.py
    ├── client.py            # auth, request, Retry-After, bounded backoff
    ├── issues.py            # get, create, update, link, linked-issue discovery
    ├── properties.py        # issue property get/set (fingerprint storage)
    ├── search.py            # JQL lookup by identity label (ambiguous-create check)
    └── adf.py               # Atlassian Document Format build and text extraction

.claude/skills/jira-testgen/
└── SKILL.md                 # session-driven generation: prepare -> fill -> review -> publish

tests/
├── contract/                # Jira payload shapes; draft file schema round-trips
├── integration/             # end-to-end flows against a mocked Jira
└── unit/                    # criteria, fingerprint, identity, limits, redaction

drafts/                      # gitignored; PROJ-123.yaml and PROJ-123.yaml.bak
.env.example                 # every supported setting, placeholder values
.gitignore                   # .env, drafts/
pyproject.toml
README.md
```

**Structure Decision**: Single project. The deliverable is one installable Python package (`src/jira_testgen/`) exposing a CLI, plus one Claude Code skill that drives it. There is no server, no frontend, and no second deployable, so the web and mobile layouts do not apply.

The internal split follows the spec's own seams rather than generic layers: `criteria/`, `draft/`, and `jira/` correspond to the three places the spec places hard guarantees (criterion traceability, review and approval, publishing idempotency). `jira/` is the only package that performs network I/O, which keeps everything else unit-testable without mocks.

## Key design decisions

These are settled in [research.md](./research.md); summarised here because they shape every task that follows.

1. **Identity as a Jira label, fingerprint as a Jira issue property.** The label (`tcgen-id-PROJ-123-TC-001`) is JQL-searchable, which is what makes FR-053's ambiguous-create check possible; the property holds the fingerprint and tool metadata without cluttering the issue for human readers. An issue with neither is not the tool's and is never claimed (FR-026c).

2. **YAML draft files, one per story.** Strictly parseable for FR-017's structural validation while remaining editable by hand. Block scalars keep multi-line steps readable. Markdown was rejected because free-form prose cannot be validated or round-tripped reliably.

3. **Approval is a marker plus a content hash, both inside the draft file.** The hash covers only the test cases and criteria blocks, never the approval block itself — which is precisely what FR-044 requires, since setting the marker must not void the approval it grants.

4. **Error classification is a first-class module.** FR-051 and FR-052 only work if "retry this" and "never retry this" are decided in one place. `errors.py` maps HTTP status and Jira error bodies onto `TransientError` (retry with backoff, honouring `Retry-After`) or `PermanentError` (report immediately).

5. **Token redaction lives in the log formatter, not at call sites.** FR-034 is an absolute, and a per-call-site approach fails the first time someone adds a log line. The token is registered once at config load and scrubbed centrally from every record, including exception text.

6. **Generation is a skill, not a code path.** The CLI has no "generate" subcommand. `prepare` writes a scaffold with criteria and identities but empty test cases; the Claude Code session fills it; `validate` and `publish` are indifferent to who wrote the content. This is what satisfies FR-036 and FR-037 simultaneously.

## Complexity Tracking

No constitution violations to justify — see the Constitution Check above for why the gate is vacuous rather than passed.

One deliberate complexity is worth recording even though no gate forces it:

| Choice | Why needed | Simpler alternative rejected because |
|---|---|---|
| Identity in a label *and* fingerprint in an issue property | FR-053 needs JQL-searchable identity; FR-040 needs an arbitrary-length fingerprint that does not disfigure the issue | Label-only cannot hold a hash within Jira's label constraints; property-only is not searchable by JQL, so an ambiguous create could not be resolved before retrying |
