"""Draft file models and YAML I/O (contracts/draft-file.md).

YAML was chosen over Markdown because FR-017 requires refusing a structurally
invalid draft and naming the offending test case, which needs a format with real
structure. Block scalars keep multi-line steps readable by hand.

Loading is strict on purpose: an unknown ``schema_version`` or an unknown
approval status is refused rather than guessed at, because guessing at a draft's
meaning is how reviewed work gets published wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from jira_testgen.errors import JiraTestgenError

SCHEMA_VERSION = 1
CATEGORIES = ("positive", "negative", "boundary", "edge")
APPROVAL_STATUSES = ("draft", "approved")

# Jira caps issue summaries at 255 characters. Enforced here so an over-long
# summary is a draft-validation failure the engineer can fix, rather than a
# per-test-case permanent failure discovered halfway through publishing.
MAX_SUMMARY_LENGTH = 255

HEADER = """\
# Review these test cases, then set `status: approved` at the bottom and run:
#     jira-testgen publish {issue}
#
# To reject a test case, delete its whole entry. To change one, edit it in place.
# Editing anything outside the `approval:` block after approving will void the
# approval, and you will be asked to approve again.
#
# Do not edit `identity` values or `source_text` under `criteria`: identities
# link a draft test case to its Jira issue, and the criterion text is the
# baseline used to notice that the story has moved on.
"""


class DraftSchemaError(JiraTestgenError):
    """The draft file is missing, unparseable, or not the shape we expect."""

    exit_code = 6


@dataclass
class AcceptanceCriterion:
    ordinal: int
    label: str
    source_text: str


@dataclass
class TestCase:
    identity: str
    category: str
    covers: list[str]
    summary: str
    preconditions: str
    steps: list[str]
    expected_results: str

    def to_content_dict(self) -> dict:
        """The fields that make up this test case's comparable content."""
        return {
            "identity": self.identity,
            "category": self.category,
            "covers": list(self.covers),
            "summary": self.summary,
            "preconditions": self.preconditions,
            "steps": list(self.steps),
            "expected_results": self.expected_results,
        }


@dataclass
class ApprovalState:
    status: str = "draft"
    approved_fingerprint: str | None = None

    @property
    def is_approved(self) -> bool:
        return self.status == "approved"


@dataclass
class DraftSet:
    source_issue: str
    source_summary: str = ""
    criteria_source: str = "description"
    criteria: list[AcceptanceCriterion] = field(default_factory=list)
    test_cases: list[TestCase] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    approval: ApprovalState = field(default_factory=ApprovalState)
    identity_allocation: dict = field(default_factory=dict)
    previously_published: list[dict] = field(default_factory=list)
    generated_at: str | None = None
    tool_version: str | None = None
    schema_version: int = SCHEMA_VERSION

    def content_region(self) -> dict:
        """Exactly the region the fingerprint covers (FR-044, FR-045)."""
        return {
            "criteria": [
                {"label": c.label, "source_text": c.source_text} for c in self.criteria
            ],
            "test_cases": [tc.to_content_dict() for tc in self.test_cases],
        }

    def criterion_labels(self) -> list[str]:
        return [c.label for c in self.criteria]


# ---------------------------------------------------------------------------
# YAML representation
# ---------------------------------------------------------------------------


class _DraftDumper(yaml.SafeDumper):
    """Dumper that writes multi-line strings as readable block scalars."""


def _represent_str(dumper: yaml.Dumper, data: str):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_DraftDumper.add_representer(str, _represent_str)


def to_mapping(draft: DraftSet) -> dict:
    """The on-disk shape. Key order here is the order the engineer reads."""
    mapping: dict[str, Any] = {
        "schema_version": draft.schema_version,
        "source_issue": draft.source_issue,
        "source_summary": draft.source_summary,
        "criteria_source": draft.criteria_source,
        "generated_at": draft.generated_at,
        "tool_version": draft.tool_version,
    }
    if draft.warnings:
        mapping["warnings"] = list(draft.warnings)
    mapping["criteria"] = [
        {"label": c.label, "source_text": c.source_text} for c in draft.criteria
    ]
    if draft.identity_allocation:
        mapping["identity_allocation"] = dict(draft.identity_allocation)
    if draft.previously_published:
        mapping["previously_published"] = [dict(p) for p in draft.previously_published]
    mapping["test_cases"] = [
        {
            "identity": tc.identity,
            "category": tc.category,
            "covers": list(tc.covers),
            "summary": tc.summary,
            "preconditions": tc.preconditions,
            "steps": list(tc.steps),
            "expected_results": tc.expected_results,
        }
        for tc in draft.test_cases
    ]
    mapping["approval"] = {
        "status": draft.approval.status,
        "approved_fingerprint": draft.approval.approved_fingerprint,
    }
    return mapping


def dump_draft(draft: DraftSet, path: str | Path) -> Path:
    """Write a draft, leading with the review instructions."""
    target = Path(path)
    body = yaml.dump(
        to_mapping(draft),
        Dumper=_DraftDumper,
        sort_keys=False,
        allow_unicode=True,
        width=100,
        default_flow_style=False,
    )
    target.write_text(
        HEADER.format(issue=draft.source_issue) + "\n" + body, encoding="utf-8"
    )
    return target


def dump_draft_text(draft: DraftSet) -> str:
    """The same content as a string, for atomic writes."""
    body = yaml.dump(
        to_mapping(draft),
        Dumper=_DraftDumper,
        sort_keys=False,
        allow_unicode=True,
        width=100,
        default_flow_style=False,
    )
    return HEADER.format(issue=draft.source_issue) + "\n" + body


def load_draft(path: str | Path) -> DraftSet:
    """Read and structurally validate a draft file.

    Every failure names the file, because the engineer's next action is to open
    it (FR-017).
    """
    source = Path(path)
    if not source.is_file():
        raise DraftSchemaError(
            f"No draft file at {source}. Run `jira-testgen prepare` first."
        )

    try:
        raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise DraftSchemaError(f"{source}: could not be parsed as YAML -- {exc}") from exc

    if not isinstance(raw, dict):
        raise DraftSchemaError(f"{source}: expected a mapping at the top level.")

    version = raw.get("schema_version")
    if version != SCHEMA_VERSION:
        raise DraftSchemaError(
            f"{source}: schema_version {version!r} is not supported "
            f"(this tool writes version {SCHEMA_VERSION}). "
            "Regenerate the draft rather than editing the version."
        )

    approval_raw = raw.get("approval") or {}
    if not isinstance(approval_raw, dict):
        raise DraftSchemaError(f"{source}: `approval` must be a mapping.")
    status = approval_raw.get("status", "draft")
    if status not in APPROVAL_STATUSES:
        raise DraftSchemaError(
            f"{source}: approval status {status!r} is not understood. "
            f"Use one of: {', '.join(APPROVAL_STATUSES)}."
        )

    criteria = []
    for index, item in enumerate(raw.get("criteria") or [], start=1):
        if not isinstance(item, dict):
            raise DraftSchemaError(f"{source}: criterion {index} must be a mapping.")
        criteria.append(
            AcceptanceCriterion(
                ordinal=index,
                label=str(item.get("label") or f"AC-{index}"),
                source_text=str(item.get("source_text") or ""),
            )
        )

    test_cases = []
    for index, item in enumerate(raw.get("test_cases") or [], start=1):
        if not isinstance(item, dict):
            raise DraftSchemaError(f"{source}: test case {index} must be a mapping.")
        identity = str(item.get("identity") or f"(test case {index}, no identity)")
        steps = item.get("steps")
        if steps is not None and not isinstance(steps, list):
            raise DraftSchemaError(
                f"{source}: {identity} has `steps` that is not a list. "
                "Write each step as its own `- ` entry."
            )
        covers = item.get("covers")
        if covers is not None and not isinstance(covers, list):
            raise DraftSchemaError(
                f"{source}: {identity} has `covers` that is not a list. "
                "Write it as a list of criterion labels, e.g. [AC-1]."
            )
        test_cases.append(
            TestCase(
                identity=str(item.get("identity") or ""),
                category=str(item.get("category") or ""),
                covers=[str(c) for c in (covers or [])],
                summary=str(item.get("summary") or ""),
                preconditions=str(item.get("preconditions") or ""),
                steps=[str(s) for s in (steps or [])],
                expected_results=str(item.get("expected_results") or ""),
            )
        )

    allocation = raw.get("identity_allocation") or {}
    if not isinstance(allocation, dict):
        raise DraftSchemaError(f"{source}: `identity_allocation` must be a mapping.")

    published = raw.get("previously_published") or []
    if not isinstance(published, list):
        raise DraftSchemaError(f"{source}: `previously_published` must be a list.")

    return DraftSet(
        source_issue=str(raw.get("source_issue") or ""),
        source_summary=str(raw.get("source_summary") or ""),
        criteria_source=str(raw.get("criteria_source") or "description"),
        criteria=criteria,
        test_cases=test_cases,
        warnings=[str(w) for w in (raw.get("warnings") or [])],
        approval=ApprovalState(
            status=status,
            approved_fingerprint=approval_raw.get("approved_fingerprint"),
        ),
        identity_allocation=allocation,
        previously_published=[p for p in published if isinstance(p, dict)],
        generated_at=raw.get("generated_at"),
        tool_version=raw.get("tool_version"),
        schema_version=version,
    )


def draft_path(drafts_dir: str | Path, issue_key: str) -> Path:
    return Path(drafts_dir) / f"{issue_key}.yaml"
