<!--
SYNC IMPACT REPORT (scratch material for review of this amendment; remove before commit)

Version change: (none — unfilled scaffold) → 1.0.0
Bump rationale: initial ratification. The file previously contained only
  unfilled all-caps placeholder tokens, so there was no prior governance to
  supersede. First concrete adoption is 1.0.0, not a MINOR bump on 0.x.

Modified principles: none (no prior named principles existed)

Added sections:
  - I. Library-First
  - II. CLI Interface
  - III. Test-First (NON-NEGOTIABLE)
  - IV. Refuse By Default
  - V. Secrets Are Redacted Centrally
  - VI. Simplicity
  - Additional Constraints
  - Development Workflow
  - Governance

Removed sections: none

Note on principle count: the resolved scaffold offers five principle slots; six
  were specified and are recorded, following the same structure.

Follow-up TODOs: none. RATIFICATION_DATE is set to the date of this adoption
  (2026-10-10) because no earlier adoption exists — the scaffold was never
  filled in.

Retrospective note: feature 001-jira-test-case-generator was planned and built
  before these principles were ratified. Its Constitution Check therefore
  recorded a vacuous pass and held the design against this scaffold's *example*
  principles instead. Those examples are the basis of what is written below, so
  the feature is believed compliant, but it was never gated. Future features
  will be.
-->

# Jira Test Case Generator Constitution

## Core Principles

### I. Library-First

Core logic MUST live in an importable package (`src/jira_testgen/`). The CLI and
the Claude Code skill are thin shells over it: argument parsing, output
formatting, and exit codes only. Any module that performs network I/O MUST be
confined to a dedicated package, and no other module may perform it.

Rationale: keeping judgement and computation out of the shell is what makes the
majority of the code testable with no mocks at all. It also means a second
front end — a different CLI, a library consumer, another skill — costs nothing.

### II. CLI Interface

Every capability MUST be reachable as a subcommand. Reports go to stdout and
logs to stderr, so stdout stays pipeable. Every command MUST offer `--json`.
Each distinct failure class MUST have its own exit code, documented in a
contract; callers branch on exit codes and MUST NOT be expected to parse prose.

Rationale: an automated caller — a skill, a script, CI — needs to know *which*
kind of failure occurred without reading English. Collapsing failures into exit
1 pushes that cost onto every caller forever.

### III. Test-First (NON-NEGOTIABLE)

Tests MUST be written before the implementation they cover, and MUST be observed
failing first. Three layers are required:

- **unit** — pure logic, no mocks and no network;
- **contract** — the shape of anything crossing a boundary this project does not
  control, asserted against recorded real payloads wherever obtainable;
- **integration** — whole flows, including the sequences that only break on the
  second run.

A requirement is not implemented until a test would fail if it regressed.

Rationale: every silent failure mode in a tool like this is either a payload
assumption or a multi-run sequence. Neither is caught by reading the code.

### IV. Refuse By Default

No destructive or outward-facing action may happen implicitly. Anything that
writes to an external system, replaces reviewed work, or departs from a stated
rule MUST be refused by default and MUST require a deliberate per-run act — a
flag, or a marker a human set. Such an act MUST be recorded in the run's report,
and MUST NOT be settable as a persistent configuration value. A run that used an
override, or that left anything in a partial state, MUST NOT report success.

Rationale: a default that destroys reviewed work will eventually destroy it. A
persistent override is set once and forgotten, which makes the deliberate act
decorative; keeping it per-run keeps the decision where the consequence is.

### V. Secrets Are Redacted Centrally

Secrets MUST be registered once, as soon as they are read, and scrubbed at a
single chokepoint that every output stream passes through — logs, reports,
errors, and tracebacks alike. Redaction at call sites is FORBIDDEN. Compliance
MUST be proved by a test asserting **zero occurrences** across every subcommand,
verbosity level, and output format, driven to failure.

Rationale: a rule that depends on the author of a future log line remembering it
will be broken by the next log line. This project has already had exactly that
leak: output was protected at error sites while report rendering went straight
to stdout unscrubbed.

### VI. Simplicity

Runtime dependencies MUST be few and MUST be justified. State MUST NOT be stored
locally when the remote system can hold it. Added complexity MUST be recorded
with the requirement that forces it, so a later reader can tell a necessary
mechanism from an accident.

Rationale: local state is the usual cause of a tool behaving differently on a
colleague's machine. Recording justified complexity is what stops someone
"simplifying" away a mechanism that is load-bearing.

## Additional Constraints

- **Runtime**: Python 3.11 or later.
- **Dependencies**: three runtime dependencies. Adding a fourth requires the
  justification that Principle VI demands.
- **No paid model credential**: no paid language-model credential may ever be
  required, requested, or accepted. Work needing a model runs through the user's
  existing Claude Code session. Adding such an SDK to the dependency manifest is
  FORBIDDEN, and a test MUST enforce its absence.
- **Platform**: local developer machines across Windows, macOS and Linux. File
  operations MUST NOT assume POSIX semantics.

## Development Workflow

- **Quality gate**: `ruff check src tests` MUST pass and the full test suite MUST
  be green before any task is marked complete. A task is not done because the
  code was written.
- **Error messages name their subject**: every message MUST name the setting, the
  file, or the test case it concerns. A message that names nothing is a defect,
  and this is enforced by test, not by review.
- **Report outcomes faithfully**: a partially complete run MUST be reported as
  partial. Progress notes MUST state what was verified and what was not.
- **Design artifacts stay true**: when implementation diverges from a design
  document, the divergence MUST be recorded rather than left to be discovered.

## Governance

This constitution supersedes other practices in this repository. Where it and a
design document disagree, this document wins, and the design document is
corrected.

**Amendments** MUST be made through `/speckit-constitution`, MUST state the
version bump and its rationale, and MUST NOT be made by editing principles
silently. A principle may be weakened or removed only by explicit amendment —
never by reinterpretation in the course of delivering a feature.

**Versioning** follows semantic versioning:

- **MAJOR** — a principle is removed or redefined incompatibly;
- **MINOR** — a principle or section is added, or guidance materially expanded;
- **PATCH** — clarification and wording, with no change in meaning.

**Compliance** MUST be verified at planning time. `/speckit-plan` records a
Constitution Check; if a principle cannot be honoured, the violation MUST be
justified in Complexity Tracking with the requirement that forces it, or the
design MUST change. A Constitution Check that passes because nothing was checked
MUST say so plainly rather than reporting a clean pass.

Use `README.md` for runtime development guidance, and
`specs/<feature>/plan.md` for per-feature design decisions.

**Version**: 1.0.0 | **Ratified**: 2026-10-10 | **Last Amended**: 2026-10-10
