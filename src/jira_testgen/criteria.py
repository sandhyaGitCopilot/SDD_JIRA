"""Acceptance criteria: extraction, and the comparison form.

Two distinct jobs live here, and conflating them is the trap this module is
written to avoid:

- ``source_text`` is **verbatim** from Jira. It is what the engineer reads in the
  draft, and what traceability is claimed against (FR-003).
- ``normalized`` exists **only** for comparison. Jira's editor rewrites markup
  on unrelated edits, so staleness detection that compared raw text would block
  publishing constantly (FR-057).

Resolution order is the configured field first when the setting is present,
otherwise a labelled section of the description (FR-002). Finding nothing in
either place is a stop, not a degraded run (FR-005).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from jira_testgen.errors import CriteriaNotFound

SECTION_LABEL = "Acceptance Criteria"

# A heading or bolded line naming the section, however the team wrote it.
_SECTION_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?\**\s*acceptance\s+criteria\s*:?\s*\**\s*$",
    re.IGNORECASE,
)
_HEADING_RE = re.compile(r"^\s*#{1,6}\s+\S")
_BOLD_HEADING_RE = re.compile(r"^\s*\*\*[^*]+\*\*\s*:?\s*$")

# Leading list or numbering markers: "- ", "* ", "1. ", "1) ", "AC-1:", "AC1 -"
_MARKER_RE = re.compile(
    r"^\s*(?:[-*•]\s+|\d+[.)]\s+|AC[-\s]?\d+\s*[:.\-)]\s*)",
    re.IGNORECASE,
)

_WHITESPACE = re.compile(r"\s+")
_MARKUP_CHARS = re.compile(r"[*_`~]+")
_HEADING_MARKS = re.compile(r"^\s*#{1,6}\s*")


@dataclass
class Criterion:
    ordinal: int
    label: str
    source_text: str
    normalized: str


@dataclass
class CriteriaResult:
    criteria: list[Criterion]
    source: str  # "field" | "description"


def normalize_for_comparison(text: object) -> str:
    """The comparison form: markup, markers, spacing and case all removed.

    Punctuation is deliberately kept -- "it expires." and "it expires?" are
    different statements.
    """
    if text is None:
        return ""
    value = str(text)
    value = _HEADING_MARKS.sub("", value)
    value = _MARKER_RE.sub("", value)
    value = _MARKUP_CHARS.sub("", value)
    value = _WHITESPACE.sub(" ", value)
    return value.strip().casefold()


def strip_marker(line: str) -> str:
    """Remove a leading list or numbering marker, keeping the text verbatim."""
    return _MARKER_RE.sub("", line).strip()


def _is_substantive(text: str) -> bool:
    """False for a line that is only a bullet, rule, or punctuation.

    A bare "-" or "---" is layout, not a criterion, and a marker with no text
    after it does not match the marker pattern (which requires trailing
    whitespace), so it has to be rejected here instead.
    """
    return bool(re.search(r"[0-9A-Za-z]", text))


def extract_criteria(
    *,
    description_text: str | None = None,
    ac_field_text: str | None = None,
    ac_field: str | None = None,
) -> CriteriaResult:
    """Extract criteria, preferring the configured field (FR-002).

    Raises ``CriteriaNotFound`` when neither source yields anything, naming both
    places searched (FR-005).
    """
    if ac_field_text and ac_field_text.strip():
        items = _lines_to_criteria(_split_items(ac_field_text))
        if items:
            return CriteriaResult(criteria=items, source="field")

    section = _find_section(description_text or "")
    if section:
        items = _lines_to_criteria(section)
        if items:
            return CriteriaResult(criteria=items, source="description")

    field_note = (
        f"the configured field {ac_field}"
        if ac_field
        else "no acceptance criteria field is configured (JIRA_AC_FIELD is unset)"
    )
    raise CriteriaNotFound(
        "No acceptance criteria were found, so there is nothing to establish "
        "coverage against and no draft was written.\n"
        f"  - Field: {field_note}.\n"
        f"  - Description: no section labelled '{SECTION_LABEL}' was found.\n"
        "Add criteria to the story, or set JIRA_AC_FIELD to the field that holds them."
    )


def _split_items(text: str) -> list[str]:
    """Split a block of criteria text into candidate lines."""
    return [line for line in (text or "").splitlines()]


def _find_section(description_text: str) -> list[str]:
    """Return the lines under an acceptance-criteria label, if there is one."""
    lines = description_text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if _SECTION_RE.match(line):
            start = index + 1
            break
    if start is None:
        return []

    collected: list[str] = []
    for line in lines[start:]:
        # Stop at the next heading: content under a later heading is not a
        # criterion, whatever it says.
        if _HEADING_RE.match(line) or _BOLD_HEADING_RE.match(line):
            break
        collected.append(line)
    return collected


def _lines_to_criteria(lines: list[str]) -> list[Criterion]:
    criteria: list[Criterion] = []
    for raw in lines:
        text = strip_marker(raw)
        if not _is_substantive(text):
            continue
        ordinal = len(criteria) + 1
        criteria.append(
            Criterion(
                ordinal=ordinal,
                label=f"AC-{ordinal}",
                source_text=text,
                normalized=normalize_for_comparison(text),
            )
        )
    return criteria
