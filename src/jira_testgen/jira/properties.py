"""Issue properties: where a published test case's fingerprint lives.

Each issue this tool creates carries a property under ``com.tcgen.testcase``
holding the test case identity and a fingerprint of the content the tool last
wrote. That fingerprint is what lets a later run tell an untouched issue from
one a person edited in Jira (FR-040), and it is the authoritative marker: an
issue without it is not this tool's and is never claimed (FR-026c).

A property is used rather than a label because it can hold a full-length hash
without putting noise in front of human readers. The searchable identity lives
in a label as well -- see ``search.py`` for why both exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jira_testgen.jira.client import JiraClient

PROPERTY_KEY = "com.tcgen.testcase"


@dataclass(frozen=True)
class PublicationMarker:
    """The tool's own record, stored on the Jira issue itself."""

    identity: str
    content_fingerprint: str
    source_issue: str
    generated_at: str | None = None
    tool_version: str | None = None

    def to_payload(self) -> dict:
        return {
            "identity": self.identity,
            "content_fingerprint": self.content_fingerprint,
            "source_issue": self.source_issue,
            "generated_at": self.generated_at,
            "tool_version": self.tool_version,
        }

    @classmethod
    def from_payload(cls, payload: Any) -> PublicationMarker | None:
        """Build a marker from a property body, or ``None`` if it is not ours.

        Defensive on purpose: a property under our key with the wrong shape
        means something else wrote it, and claiming that issue would breach
        FR-026c.
        """
        if not isinstance(payload, dict):
            return None
        identity = payload.get("identity")
        fingerprint = payload.get("content_fingerprint")
        source = payload.get("source_issue")
        if not identity or not fingerprint or not source:
            return None
        return cls(
            identity=str(identity),
            content_fingerprint=str(fingerprint),
            source_issue=str(source),
            generated_at=payload.get("generated_at"),
            tool_version=payload.get("tool_version"),
        )


def read_marker(client: JiraClient, issue_key: str) -> PublicationMarker | None:
    """Read an issue's marker. ``None`` means the issue is not this tool's."""
    body = client.request(
        "GET",
        f"issue/{issue_key}/properties/{PROPERTY_KEY}",
        allow_404=True,
    )
    if body is None:
        return None
    # Jira wraps the stored body: {"key": ..., "value": {...}}
    value = body.get("value") if isinstance(body, dict) else None
    return PublicationMarker.from_payload(value)


def write_marker(client: JiraClient, issue_key: str, marker: PublicationMarker) -> None:
    """Write or refresh an issue's marker.

    Called on create and on every update, so the stored fingerprint always
    reflects what the tool last wrote (FR-040).
    """
    client.put(
        f"issue/{issue_key}/properties/{PROPERTY_KEY}",
        json=marker.to_payload(),
    )
