"""Error taxonomy.

The retry policy is only coherent if "retry this" and "never retry this" are
decided in exactly one place. That place is this module (FR-051, FR-052).

Every failure the tool can hit falls into one of three classes:

- ``TransientError``  -- the request may succeed if repeated. Retried with
  backoff, honouring any wait the server asked for.
- ``PermanentError``  -- repeating it will fail identically. Reported at once
  with its reason; never retried.
- ``UserError``       -- the input or configuration is wrong. Reported before
  anything is written; never retried.
"""

from __future__ import annotations

# Statuses where repeating the request is worthwhile.
TRANSIENT_STATUSES = frozenset({429, 502, 503, 504})

# Statuses where repeating the request cannot help. 409 is here deliberately: a
# conflict means the server's state is not what we assumed, and hammering it
# will not change that.
PERMANENT_STATUSES = frozenset({400, 401, 403, 404, 405, 409})

# Substrings in a Jira error body that mean the request itself is wrong, whatever
# the status code says. Jira sometimes returns a 200-shaped envelope with errors
# inside, so status alone is not enough.
# Phrasings are matched loosely because Jira interpolates field names and ids
# into them, e.g. "Field 'customfield_10040' cannot be set". Matching the exact
# sentence would miss every real message.
_PERMANENT_BODY_MARKERS = (
    "is not on the appropriate screen",
    "cannot be set",
    "unknown field",
    "is not valid",
    "issuetype",
    "permission",
    "specify a valid project",
)


class JiraTestgenError(Exception):
    """Base class, so a caller can catch everything this tool raises."""

    exit_code = 1

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


class UserError(JiraTestgenError):
    """Bad input or configuration. Reported before any write; never retried."""

    exit_code = 2


class PermanentError(JiraTestgenError):
    """A request that cannot succeed on repetition."""

    exit_code = 1

    def __init__(
        self, message: str, *, status: int | None = None, reason: str | None = None
    ) -> None:
        super().__init__(message, status=status)
        self.reason = reason or message


class TransientError(JiraTestgenError):
    """A request worth repeating.

    ``retry_after`` carries the server's own instruction when it gave one, in
    seconds. Guessing an interval when the server has stated one is both wrong
    and likely to deepen a throttle, so the client honours this in preference to
    its own backoff (FR-051).
    """

    exit_code = 11

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, status=status)
        self.retry_after = retry_after


class AuthError(JiraTestgenError):
    """Jira rejected the credentials.

    Separate from ``UserError`` so that "this setting looks wrong" stays
    distinguishable from "Jira rejected these credentials" (FR-033).
    """

    exit_code = 3


class IssueNotFound(PermanentError):
    """The source issue does not exist or cannot be read (FR-004).

    A subclass of ``PermanentError`` because retrying cannot help, but with its
    own exit code: "that issue key is wrong" deserves a different answer from
    "that request was malformed".
    """

    exit_code = 4


class CriteriaNotFound(JiraTestgenError):
    """Neither source yielded acceptance criteria.

    A stop rather than a degraded run: generating from the summary alone would
    produce a suite that claims coverage it cannot have (FR-005).
    """

    exit_code = 5


class DraftRefusedError(JiraTestgenError):
    """A draft is unapproved, approval-voided, or structurally invalid."""

    exit_code = 6


class DraftExistsError(JiraTestgenError):
    """A draft already exists and regeneration was not requested (FR-047)."""

    exit_code = 7


class CriteriaChangedError(JiraTestgenError):
    """The story's criteria moved on after the drafts were approved (FR-058)."""

    exit_code = 8


class SetTooLargeError(JiraTestgenError):
    """The set exceeds the publishing ceiling without an override (FR-065)."""

    exit_code = 9


class AmbiguousResultError(JiraTestgenError):
    """A write whose outcome is unknown -- typically a timeout.

    The request may or may not have landed. A create that raises this must never
    be blindly retried: the caller first looks for an issue already carrying the
    test case's identity (FR-053).
    """

    exit_code = 11


def body_indicates_permanent(body: object) -> bool:
    """True when a Jira error body names a field, issue-type, or permission fault."""
    if body is None:
        return False
    text = str(body).lower()
    return any(marker in text for marker in _PERMANENT_BODY_MARKERS)


def classify_status(
    status: int,
    *,
    body: object = None,
    retry_after: float | None = None,
) -> JiraTestgenError:
    """Map an HTTP status (and optionally its body) onto the right error.

    Returns the error rather than raising it, so a caller can attach context
    before it travels.
    """
    if status in (401,):
        return AuthError("Jira rejected the configured credentials.", status=status)
    if status == 403:
        # 403 is a permission problem, not a credential problem: the account is
        # known, it simply may not do this.
        return PermanentError(
            "Jira refused the request: the account lacks permission for it.",
            status=status,
            reason="permission denied",
        )
    if status in TRANSIENT_STATUSES:
        return TransientError(
            f"Jira returned {status}; the request may succeed if repeated.",
            status=status,
            retry_after=retry_after,
        )
    if status in PERMANENT_STATUSES or body_indicates_permanent(body):
        return PermanentError(
            f"Jira returned {status} and will return it again for this request.",
            status=status,
            reason=_summarize_body(body) or f"HTTP {status}",
        )
    if 500 <= status < 600:
        # An unlisted 5xx is still a server-side fault; worth one more try.
        return TransientError(
            f"Jira returned {status}; the request may succeed if repeated.",
            status=status,
            retry_after=retry_after,
        )
    return PermanentError(f"Jira returned an unexpected status {status}.", status=status)


def _summarize_body(body: object) -> str | None:
    """Pull a short reason out of a Jira error envelope, if there is one."""
    if isinstance(body, dict):
        messages = body.get("errorMessages") or []
        errors = body.get("errors") or {}
        parts = [str(m) for m in messages]
        parts += [f"{k}: {v}" for k, v in errors.items()]
        if parts:
            return "; ".join(parts)[:400]
    return None
