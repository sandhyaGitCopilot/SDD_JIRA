"""Issue operations and published-work discovery.

The discovery function at the bottom (``discover_published``) is the one that
carries the spec's idempotency guarantees. It reads the story's linked issues
and keeps only those carrying this tool's marker, which is what makes a re-run
correct from any machine with no local state (FR-026, FR-026b, FR-026c).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jira_testgen.errors import IssueNotFound, PermanentError
from jira_testgen.jira import adf
from jira_testgen.jira.client import JiraClient
from jira_testgen.jira.properties import PublicationMarker, read_marker
from jira_testgen.logging_setup import get_logger

STORY_FIELDS = ["summary", "description", "issuelinks", "project", "labels"]


@dataclass
class FetchedIssue:
    """A story as retrieved, flattened enough for criteria extraction."""

    key: str
    project_key: str
    summary: str
    description_text: str
    description_had_non_text: bool
    ac_field_text: str | None
    ac_field_had_non_text: bool
    linked_issue_keys: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


@dataclass
class PublishedTestCase:
    """A test case already present in Jira, as discovered from the story."""

    identity: str
    issue_key: str
    marker: PublicationMarker
    link_present: bool


def get_story(client: JiraClient, issue_key: str, *, ac_field: str | None = None) -> FetchedIssue:
    """Retrieve a story with the fields this tool needs (FR-001)."""
    fields = list(STORY_FIELDS)
    if ac_field:
        fields.append(ac_field)

    try:
        body = client.get(f"issue/{issue_key}", params={"fields": ",".join(fields)})
    except PermanentError as exc:
        # Name the key: "PROJ-124 cannot be read" is actionable in a way that
        # "HTTP 404" is not (FR-004).
        if exc.status in (401, 403, 404):
            reason = {
                404: "it does not exist",
                403: "the configured account may not view it",
                401: "Jira rejected the configured credentials",
            }[exc.status]
            raise IssueNotFound(
                f"Cannot read issue {issue_key}: {reason}."
            ) from exc
        raise
    raw_fields = (body or {}).get("fields") or {}

    description = adf.extract_text(raw_fields.get("description"))
    ac_raw = raw_fields.get(ac_field) if ac_field else None
    ac_extracted = adf.extract_text(ac_raw) if ac_raw is not None else None

    return FetchedIssue(
        key=(body or {}).get("key", issue_key),
        project_key=((raw_fields.get("project") or {}).get("key") or ""),
        summary=raw_fields.get("summary") or "",
        description_text=description.text,
        description_had_non_text=description.had_non_text,
        ac_field_text=ac_extracted.text if ac_extracted else None,
        ac_field_had_non_text=bool(ac_extracted and ac_extracted.had_non_text),
        linked_issue_keys=_linked_keys(raw_fields.get("issuelinks") or []),
        raw=body or {},
    )


def _linked_keys(issuelinks: list) -> list[str]:
    """Every issue key on the other end of a link, inward or outward."""
    keys: list[str] = []
    for link in issuelinks:
        if not isinstance(link, dict):
            continue
        for side in ("inwardIssue", "outwardIssue"):
            other = link.get(side)
            if isinstance(other, dict) and other.get("key"):
                keys.append(other["key"])
    # Preserve order, drop repeats.
    return list(dict.fromkeys(keys))


def create_issue(
    client: JiraClient,
    *,
    project_key: str,
    issue_type: str,
    summary: str,
    description: dict,
    labels: list[str] | None = None,
) -> str:
    """Create an issue and return its key."""
    payload = {
        "fields": {
            "project": {"key": project_key},
            "issuetype": {"name": issue_type},
            "summary": summary,
            "description": description,
        }
    }
    if labels:
        payload["fields"]["labels"] = labels
    body = client.post("issue", json=payload)
    return (body or {}).get("key", "")


def update_issue(
    client: JiraClient,
    issue_key: str,
    *,
    summary: str | None = None,
    description: dict | None = None,
) -> None:
    """Update an issue in place (FR-038)."""
    fields: dict = {}
    if summary is not None:
        fields["summary"] = summary
    if description is not None:
        fields["description"] = description
    if not fields:
        return
    client.put(f"issue/{issue_key}", json={"fields": fields})


def link_issues(
    client: JiraClient,
    *,
    link_type: str,
    inward_key: str,
    outward_key: str,
) -> None:
    """Link two issues. ``inward`` is the test case, ``outward`` the story."""
    client.post(
        "issueLink",
        json={
            "type": {"name": link_type},
            "inwardIssue": {"key": inward_key},
            "outwardIssue": {"key": outward_key},
        },
    )


def list_link_type_names(client: JiraClient) -> list[str]:
    """Every link type on this site, for the pre-flight check (FR-024)."""
    body = client.get("issueLinkType")
    return [t.get("name", "") for t in (body or {}).get("issueLinkTypes") or []]


@dataclass
class IssueContent:
    """A published test case issue's current content, as Jira holds it now."""

    key: str
    summary: str
    description_text: str
    exists: bool = True


def get_issue_content(client: JiraClient, issue_key: str) -> IssueContent:
    """Read back a test case issue's summary and description.

    ``exists=False`` when the issue is gone -- a person deleted it -- which the
    caller turns into a re-create rather than reporting it as present (FR-028).
    """
    body = client.request(
        "GET",
        f"issue/{issue_key}",
        params={"fields": "summary,description"},
        allow_404=True,
    )
    if body is None:
        return IssueContent(key=issue_key, summary="", description_text="", exists=False)
    fields = (body or {}).get("fields") or {}
    return IssueContent(
        key=issue_key,
        summary=fields.get("summary") or "",
        description_text=adf.extract_text(fields.get("description")).text,
    )


def get_myself(client: JiraClient) -> dict:
    """The authenticated account. Used to confirm credentials (FR-033)."""
    return client.get("myself") or {}


def get_my_permissions(
    client: JiraClient, *, project_key: str | None, permissions: list[str]
) -> dict[str, bool]:
    """Which of ``permissions`` the account holds, by name.

    Read-only, which is why `doctor` can check whether it will be able to write
    issue properties without actually writing one.
    """
    params: dict[str, str] = {"permissions": ",".join(permissions)}
    if project_key:
        params["projectKey"] = project_key
    body = client.get("mypermissions", params=params) or {}
    granted = body.get("permissions") or {}
    return {
        name: bool((granted.get(name) or {}).get("havePermission"))
        for name in permissions
        if name in granted
    }


def get_field_ids(client: JiraClient) -> dict[str, str]:
    """Map field id -> display name, for checking JIRA_AC_FIELD exists."""
    body = client.get("field") or []
    return {str(f.get("id")): str(f.get("name", "")) for f in body if isinstance(f, dict)}


def get_create_meta(client: JiraClient, *, project_key: str, issue_type: str) -> dict | None:
    """Create-metadata for a project and issue type, or ``None`` if absent."""
    body = client.get(
        "issue/createmeta",
        params={"projectKeys": project_key, "issuetypeNames": issue_type, "expand": ""},
    )
    projects = (body or {}).get("projects") or []
    if not projects:
        return None
    issue_types = projects[0].get("issuetypes") or []
    return issue_types[0] if issue_types else None


def discover_published(
    client: JiraClient, story: FetchedIssue
) -> dict[str, PublishedTestCase]:
    """Map identity -> published test case, read entirely from Jira.

    For each issue linked to the story, read its marker. An issue without one is
    not this tool's: it is ignored entirely, never matched to a draft by wording
    or summary, and never counted as a published test case (FR-026c).

    Nothing here consults local state, which is what lets a re-run behave
    identically on another machine or after ``drafts/`` is deleted (FR-026b).
    """
    log = get_logger()
    found: dict[str, PublishedTestCase] = {}

    for key in story.linked_issue_keys:
        marker = read_marker(client, key)
        if marker is None:
            log.debug("linked issue %s carries no marker; leaving it alone", key)
            continue
        if marker.source_issue != story.key:
            # Carries our marker but belongs to another story: still not ours
            # to touch in this run.
            log.debug(
                "linked issue %s belongs to %s, not %s; skipping",
                key,
                marker.source_issue,
                story.key,
            )
            continue
        found[marker.identity] = PublishedTestCase(
            identity=marker.identity,
            issue_key=key,
            marker=marker,
            link_present=True,
        )

    log.debug("discovered %d published test case(s) for %s", len(found), story.key)
    return found
