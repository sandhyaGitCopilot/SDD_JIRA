# Specification Quality Checklist: Jira Test Case Generator

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-10-09
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`

### Validation record (iteration 1 — all items pass)

- **Implementation detail check**: Functional requirements deliberately describe a "local configuration file" and "site address / account email / API token" rather than naming `.env` keys, file formats, or HTTP endpoints. Those concrete names belong in `/speckit-plan`. Two domain terms are retained intentionally: **Jira Cloud** (the integration target, named by the user, not a technology choice this spec makes) and **Claude Code session** (appears only in Assumptions, where it records the user's stated no-paid-credential constraint).
- **Traceability check**: FR-008 and SC-003 together make the brief's "each acceptance criterion traceable to at least one test case" requirement verifiable, with FR-009 covering the honest-failure path when a criterion cannot be covered.
- **Approval gate check**: FR-013, FR-015, FR-016 and SC-005 make the "nothing in Jira before approval" constraint testable from three angles — behaviour, what counts as approval, and the refusal path.
- **Idempotency check**: FR-025 through FR-029 cover the four distinct re-run situations (clean re-run, resumed partial run, externally deleted issue, newly added test cases), each with a matching acceptance scenario in User Story 4.
- **Secret-handling check**: FR-034 and SC-008 state the token-never-emitted requirement as a zero-occurrence, directly observable outcome rather than an intention.
- **Unverifiable-criteria check**: SC-010 ("90% published with no or minor edits") is a human-judgement measure and is the weakest criterion in the set. It is retained because draft usability is the feature's central quality claim and no purely mechanical substitute exists; it should be sampled over real usage rather than gated in a single test.

### Post-clarification re-validation (2026-10-09)

`/speckit-clarify` asked 5 questions and all 16 checklist items still pass. No item changed state. The three assumptions flagged above as needing confirmation are now settled decisions in the spec, along with two further ambiguities the session surfaced:

1. **Generation engine** — resolved: Claude Code session only, no rule-based generator (FR-010, FR-036, FR-037).
2. **Acceptance criteria source** — resolved: configured field first, labelled description section otherwise, source always reported; **no criteria in either place is now a stop, not a degraded run** (FR-002, FR-002a, FR-005).
3. **Re-run semantics for changed test cases** — resolved: update in place while untouched, report a conflict when the issue was edited in Jira (FR-029, FR-038 through FR-042).
4. **Approval mechanism** — resolved: an approval marker set inside the draft file, voided by any later content edit (FR-015, FR-016, FR-043 through FR-046).
5. **Prior-publish discovery** — resolved: Jira is the only source of truth, via an identity and content fingerprint stored on each created issue; no local state (FR-026 through FR-026c, FR-040). The former "Publication Record" entity is now **Publication Marker**.

Contradictions removed rather than layered over, as the clarifications inverted earlier behaviour:

- The original FR-005 and User Story 1 scenario 5 said a story with no acceptance criteria still produced drafts. Both were rewritten to the stop behaviour; the matching edge case was replaced too.
- The original "Publication Record" described durable local state. It was replaced outright, since FR-026b now forbids requiring any local record.
- FR-021 and the Run Report entity were widened to carry the new `updated` and `conflict` outcomes, so the reporting requirements match FR-042.

Note on the implementation-detail check: **Claude Code session** now appears in functional requirements, not only in Assumptions. It is retained because it is the user's stated execution constraint and the thing FR-036 and FR-037 must be testable against — not a technology choice this spec is making.

Still worth noting for `/speckit-plan`: SC-010 remains a human-judgement measure (see above), and the draft file's concrete format is deliberately unspecified — the spec constrains only that it be human-readable and editable (FR-012), with the approval marker and approved-content record living inside it (FR-015, FR-045).

### Second clarification pass (2026-10-09)

A second `/speckit-clarify` run asked 5 more questions, all in areas the first pass had left Deferred or had not reached. All 16 checklist items still pass and no item changed state. The spec now holds 72 functional requirements, 25 success criteria, 32 edge cases and 19 assumptions.

6. **Re-running drafting over an existing draft** — resolved: refuse by default naming the file, regenerate only on explicit request, reuse already-published identities, start unapproved, keep the previous version as a backup (FR-047 through FR-050). This closed a genuine hazard: identity is assigned at draft time, so a silent regenerate would have minted fresh identities and duplicated every published issue.
7. **Throttling and transient failures** — resolved: bounded retry with increasing waits honouring Jira's own wait instruction, no retry on permanent errors, an identity check before retrying any create whose outcome was unclear, and a resumable stop when retries are exhausted (FR-051 through FR-055).
8. **Criteria changing between drafting and publishing** — resolved: re-read and compare at publish time ignoring formatting-only differences, refuse on substantive change, explicit override recorded in the report (FR-056 through FR-060).
9. **Generation depth** — resolved: one positive per criterion plus other categories only where warranted, no filler, with a set-level floor of at least one negative and one edge case (FR-007, FR-061 through FR-063).
10. **Set size** — resolved: warn above 25 test cases, refuse above 100 without an explicit per-run override; both are fixed defaults, not settings (FR-064 through FR-068).

Contradictions removed in this pass, again rather than layered over:

- **FR-007 and SC-004** required all four scenario categories across every set. Answer 9 made boundary coverage conditional, so both were rewritten, along with User Story 1 scenario 2, which asserted the old rule.
- **FR-020** said the run continues past any individual failure. Answer 7 introduced a whole-run stop on exhausted retries, so FR-020 now distinguishes a permanent per-test-case failure (continue) from a Jira-wide condition (stop, resumable).
- The **"review will be slow" edge case** was an unquantified adjective. It now names the 25 and 100 thresholds, so it is testable.
- **FR-021 and the Run Report entity** were widened again to carry `retried`, `not yet attempted`, and both override records.

Deferred after this pass: **observability** — what the tool logs and where. User Story 3 scenario 4 already requires that no log contain the token, which is the part that carries risk; the rest is a planning decision. Nothing else high-impact remains unresolved.
