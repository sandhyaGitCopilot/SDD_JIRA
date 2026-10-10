"""The Run Report (FR-021 - FR-023, FR-035, FR-042, FR-055).

Two invariants make the report trustworthy rather than merely informative:

1. **Every test case in the approved set appears exactly once.** Enforced in
   ``finalize``, so nothing created can go unaccounted for.
2. **The verdict is derived, never set.** Any failure, conflict, unlinked or
   unmarked issue, or unattempted test case makes the run ``partial``. There is
   no code path that can call a flawed run a success.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

# Decisions that mean "this test case ended in a state that needs attention".
_PARTIAL_DECISIONS = frozenset(
    {"failed", "conflict", "created_unlinked", "created_unmarked"}
)

DECISIONS = (
    "created",
    "adopted",
    "created_unlinked",
    "created_unmarked",
    "unchanged",
    "updated",
    "relinked",
    "recreated",
    "orphaned_draft",
    "conflict",
    "failed",
    "not_attempted",
)


@dataclass
class Outcome:
    identity: str
    decision: str
    issue_key: str | None = None
    reason: str | None = None
    retried: int = 0
    fields_differing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        payload: dict = {
            "identity": self.identity,
            "decision": self.decision,
            "issue_key": self.issue_key,
            "retried": self.retried,
        }
        if self.reason:
            payload["reason"] = self.reason
        if self.fields_differing:
            payload["fields_differing"] = list(self.fields_differing)
        return payload


@dataclass
class RunReport:
    source_issue: str
    criteria_source: str = ""
    outcomes: list[Outcome] = field(default_factory=list)
    defaults_used: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    overrides_used: dict = field(default_factory=dict)
    not_attempted: list[str] = field(default_factory=list)

    # ------------------------------------------------------------ building

    def add(self, outcome: Outcome, *, retries: int = 0) -> Outcome:
        if retries and not outcome.retried:
            outcome.retried = retries
        self.outcomes.append(outcome)
        return outcome

    def finalize(self, expected_identities: list[str]) -> RunReport:
        """Fill in anything the run never reached, and check completeness.

        A run that stopped early leaves test cases unattempted; they are added
        here so the report still accounts for every one (FR-021, FR-054).
        """
        reported = {o.identity for o in self.outcomes}
        for identity in expected_identities:
            if identity not in reported:
                self.not_attempted.append(identity)
                self.outcomes.append(
                    Outcome(
                        identity=identity,
                        decision="not_attempted",
                        reason="The run stopped before reaching this test case.",
                    )
                )

        seen: dict[str, int] = {}
        for outcome in self.outcomes:
            seen[outcome.identity] = seen.get(outcome.identity, 0) + 1
        duplicated = [i for i, n in seen.items() if n > 1]
        if duplicated:
            # A programming error, not a user error: the report would be lying.
            raise AssertionError(
                f"report lists these identities more than once: {duplicated}"
            )
        return self

    # ------------------------------------------------------------- verdict

    @property
    def verdict(self) -> str:
        if self.not_attempted:
            return "partial"
        if any(o.decision in _PARTIAL_DECISIONS for o in self.outcomes):
            return "partial"
        if self.overrides_used:
            # An override means the engineer knowingly departed from the rules.
            # Reporting that as a clean success would hide it.
            return "partial"
        return "success"

    @property
    def exit_code(self) -> int:
        from jira_testgen.cli import ExitCode

        if self.not_attempted:
            return int(ExitCode.RETRIES_EXHAUSTED)
        return int(ExitCode.SUCCESS if self.verdict == "success" else ExitCode.PARTIAL)

    def count(self, decision: str) -> int:
        return sum(1 for o in self.outcomes if o.decision == decision)

    # ------------------------------------------------------------ rendering

    def to_dict(self) -> dict:
        return {
            "source_issue": self.source_issue,
            "criteria_source": self.criteria_source,
            "verdict": self.verdict,
            "defaults_used": self.defaults_used,
            "warnings": self.warnings,
            "overrides_used": self.overrides_used,
            "outcomes": [o.to_dict() for o in self.outcomes],
            "not_attempted": self.not_attempted,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_text(self) -> str:
        lines = [f"{self.source_issue}: {self.verdict}"]
        if self.criteria_source:
            lines.append(f"  criteria source: {self.criteria_source}")
        if self.defaults_used:
            lines.append("  defaults applied:")
            for name, value in sorted(self.defaults_used.items()):
                lines.append(f"    {name} -> {value}")
        for warning in self.warnings:
            lines.append(f"  ! {warning}")
        if self.overrides_used:
            lines.append("  overrides used:")
            for name, value in sorted(self.overrides_used.items()):
                lines.append(f"    {name}: {value}")

        lines.append("  test cases:")
        for outcome in self.outcomes:
            key = f" -> {outcome.issue_key}" if outcome.issue_key else ""
            retried = f" (retried {outcome.retried}x)" if outcome.retried else ""
            lines.append(f"    {outcome.identity}: {outcome.decision}{key}{retried}")
            if outcome.fields_differing:
                lines.append(f"        differs in: {', '.join(outcome.fields_differing)}")
            if outcome.reason:
                lines.append(f"        {outcome.reason}")

        summary = ", ".join(
            f"{self.count(d)} {d}" for d in DECISIONS if self.count(d)
        )
        lines.append(f"  summary: {summary or 'nothing to do'}")
        return "\n".join(lines)
