"""Finding an issue by test case identity.

This module exists for one reason: FR-053. A create that times out may have
succeeded, so before retrying it the tool must ask Jira whether an issue
carrying that identity already exists. Jira's create endpoint offers no
idempotency key, and issue properties are not searchable with JQL -- which is
why the identity is *also* stored as a label. The label is the only
JQL-reachable handle on a test case, and it is what keeps a retry from creating
a duplicate.

JQL indexing is near-real-time but not instantaneous, so a lookup that finds
nothing is retried briefly before being believed. Concluding "absent" too
quickly is precisely the race that produces a duplicate.
"""

from __future__ import annotations

import time

from jira_testgen.jira.client import JiraClient
from jira_testgen.logging_setup import get_logger

LABEL_PREFIX = "tcgen-id-"

# How long to let the index settle before believing an empty result. Chosen
# over a single immediate read because the cost of being wrong is a duplicate
# issue, and the cost of waiting is two seconds on an already-failed path.
SETTLE_ATTEMPTS = 3
SETTLE_DELAY_SECONDS = 1.0


def identity_to_label(identity: str) -> str:
    """``PROJ-123-TC-001`` -> ``tcgen-id-proj-123-tc-001``.

    Lowercased because Jira labels are case-sensitive in storage but awkward to
    match otherwise; the canonical, correctly-cased identity lives in the issue
    property, so nothing is lost.
    """
    return f"{LABEL_PREFIX}{identity.strip().lower()}"


def label_to_identity(label: str) -> str | None:
    """Inverse of :func:`identity_to_label`, for labels this tool wrote."""
    if not label or not label.startswith(LABEL_PREFIX):
        return None
    return label[len(LABEL_PREFIX) :].upper()


def find_issues_by_identities(
    client: JiraClient, identities: list[str]
) -> dict[str, str]:
    """Map identity -> issue key for whichever of ``identities`` exist in Jira.

    One batched query rather than one per identity, because this runs on every
    publish: a first publish would otherwise spend a request per test case
    learning that nothing exists yet.

    This is what finds an issue that was created but never linked. Discovery
    through the story's links cannot see such an issue, so without this a re-run
    would create a second one -- the duplicate FR-023 and FR-027 forbid.
    """
    if not identities:
        return {}

    log = get_logger()
    found: dict[str, str] = {}
    labels = {identity_to_label(i): i for i in identities}

    # Jira caps JQL length, so ask in batches rather than one enormous clause.
    batch_size = 50
    ordered = list(labels)
    for start in range(0, len(ordered), batch_size):
        chunk = ordered[start : start + batch_size]
        clause = ", ".join(f'"{label}"' for label in chunk)
        body = client.get(
            "search/jql",
            params={
                "jql": f"labels in ({clause})",
                "fields": "key,labels",
                "maxResults": batch_size,
            },
        )
        for issue in (body or {}).get("issues") or []:
            key = issue.get("key")
            issue_labels = ((issue.get("fields") or {}).get("labels")) or []
            for label in issue_labels:
                identity = labels.get(str(label).lower())
                if identity and key:
                    found[identity] = key

    if found:
        log.debug("found %d existing issue(s) by identity label", len(found))
    return found


def find_issue_by_identity(
    client: JiraClient,
    identity: str,
    *,
    settle: bool = True,
    sleep=time.sleep,
) -> str | None:
    """Return the issue key carrying ``identity``, or ``None``.

    With ``settle`` (the default), an empty result is retried a few times before
    being trusted, because a create that landed milliseconds ago may not be
    indexed yet.
    """
    label = identity_to_label(identity)
    jql = f'labels = "{label}"'
    log = get_logger()

    attempts = SETTLE_ATTEMPTS if settle else 1
    for attempt in range(1, attempts + 1):
        body = client.get("search/jql", params={"jql": jql, "fields": "key", "maxResults": 5})
        issues = (body or {}).get("issues") or []
        if issues:
            key = issues[0].get("key")
            log.debug("identity %s resolved to %s", identity, key)
            return key
        if attempt < attempts:
            log.debug(
                "identity %s not indexed yet; waiting %.1fs (attempt %d of %d)",
                identity,
                SETTLE_DELAY_SECONDS,
                attempt,
                attempts,
            )
            sleep(SETTLE_DELAY_SECONDS)

    log.debug("identity %s not found after %d attempt(s)", identity, attempts)
    return None
