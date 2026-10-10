"""Drafting: fetch a story, extract criteria, write a scaffold.

Nothing here writes to Jira (FR-013). The scaffold carries the criteria verbatim
and an identity allocation for the Claude Code session to consume; the session
fills in `test_cases`, and only then is there anything to approve.

Replacing an existing draft is refused unless explicitly requested, because that
file may hold hours of review (FR-047). On regeneration the previous version is
kept as a backup and identity allocation continues past anything already
published, so re-publishing cannot collide (FR-048, FR-050).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from jira_testgen import __version__, limits
from jira_testgen.config import validate_issue_key
from jira_testgen.criteria import extract_criteria
from jira_testgen.draft.backup import replace_with_backup
from jira_testgen.draft.identity import IdentityAllocator
from jira_testgen.draft.schema import (
    AcceptanceCriterion,
    DraftSet,
    draft_path,
    dump_draft_text,
)
from jira_testgen.errors import DraftExistsError
from jira_testgen.jira import issues
from jira_testgen.jira.client import JiraClient
from jira_testgen.logging_setup import get_logger

DEFAULT_DRAFTS_DIR = "drafts"


@dataclass
class PrepareResult:
    path: Path
    issue_key: str
    criteria_count: int
    criteria_source: str
    warnings: list[str] = field(default_factory=list)
    replaced: Path | None = None
    backup: Path | None = None
    previously_published: list[dict] = field(default_factory=list)
    next_ordinal: int = 1


def prepare_draft(
    client: JiraClient,
    issue_key: str,
    *,
    drafts_dir: str | Path = DEFAULT_DRAFTS_DIR,
    ac_field: str | None = None,
    regenerate: bool = False,
) -> PrepareResult:
    """Fetch ``issue_key`` and write its draft scaffold."""
    log = get_logger()

    # Shape first: a typo should not cost a round trip.
    key = validate_issue_key(issue_key)
    target = draft_path(drafts_dir, key)

    # Refuse early, before any request, so a refusal is instant and obviously
    # harmless.
    if target.exists() and not regenerate:
        raise DraftExistsError(
            f"A draft already exists at {target} and was left untouched.\n"
            "It may contain review and edits. To replace it, re-run with "
            "--regenerate; the previous version will be kept as "
            f"{target.name}.bak."
        )

    story = issues.get_story(client, key, ac_field=ac_field)
    log.info("retrieved %s: %s", story.key, story.summary)

    # Raises CriteriaNotFound when neither source yields anything, before any
    # file is written (FR-005).
    criteria = extract_criteria(
        description_text=story.description_text,
        ac_field_text=story.ac_field_text,
        ac_field=ac_field,
    )

    warnings: list[str] = []
    if story.description_had_non_text or story.ac_field_had_non_text:
        warnings.append(
            "The story contained non-text content (images, attachments, or macros) "
            "which was not interpreted. Check it by hand before approving."
        )

    published: list[dict] = []
    if regenerate:
        # Only needed when regenerating: a first draft has nothing to reuse.
        discovered = issues.discover_published(client, story)
        published = [
            {
                "identity": item.identity,
                "issue_key": item.issue_key,
                "content_fingerprint": item.marker.content_fingerprint,
            }
            for item in sorted(discovered.values(), key=lambda i: i.identity)
        ]
        if published:
            warnings.append(
                f"{len(published)} test case(s) are already published for {key}. "
                "Reuse an existing identity when you rewrite the equivalent test "
                "case, so publishing updates it instead of creating a second issue."
            )

    allocator = IdentityAllocator(key, [p["identity"] for p in published])

    size_hint = limits.size_warning(len(criteria.criteria))
    if size_hint:
        warnings.append(size_hint)
    if limits.exceeds_ceiling(len(criteria.criteria)):
        # Surfaced now rather than at publish, so the engineer learns before
        # reviewing rather than after (FR-065).
        warnings.append(limits.ceiling_message(len(criteria.criteria)))

    draft = DraftSet(
        source_issue=key,
        source_summary=story.summary,
        criteria_source=criteria.source,
        criteria=[
            AcceptanceCriterion(
                ordinal=c.ordinal, label=c.label, source_text=c.source_text
            )
            for c in criteria.criteria
        ],
        test_cases=[],
        warnings=warnings,
        identity_allocation={
            "prefix": allocator.prefix,
            "next_ordinal": allocator.next_ordinal,
        },
        previously_published=published,
        generated_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        tool_version=__version__,
    )

    replaced = target if target.exists() else None
    backup = replace_with_backup(target, dump_draft_text(draft))

    log.info("wrote %s with %d criteria", target, len(draft.criteria))

    return PrepareResult(
        path=target,
        issue_key=key,
        criteria_count=len(draft.criteria),
        criteria_source=criteria.source,
        warnings=warnings,
        replaced=replaced,
        backup=backup,
        previously_published=published,
        next_ordinal=allocator.next_ordinal,
    )
