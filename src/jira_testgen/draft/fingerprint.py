"""Content fingerprints (FR-040, FR-043, FR-044, FR-045).

Two fingerprints are computed from the same canonicalization:

- the **draft** fingerprint, over a draft's content region, which decides
  whether an approval still applies;
- the **issue** fingerprint, over a published issue's content, which decides
  whether a person has edited it in Jira.

The region hashed covers ``criteria`` and ``test_cases`` and nothing else. The
``approval`` block is excluded by construction, because setting the approval
marker is itself a file edit -- if the hash covered it, approving a draft would
instantly void the approval it just granted (FR-044).

Whitespace is collapsed before hashing, so cosmetic YAML changes -- reflowing a
block scalar, re-indenting, trailing spaces -- do not void an approval, while
any change to the words does.
"""

from __future__ import annotations

import hashlib
import json
import re

CONTENT_KEYS = ("criteria", "test_cases")

_WHITESPACE = re.compile(r"\s+")

# Fields that make up a test case's comparable content. `identity` is included:
# moving content to a different identity is a different test case.
TEST_CASE_CONTENT_FIELDS = (
    "identity",
    "category",
    "covers",
    "summary",
    "preconditions",
    "steps",
    "expected_results",
)


def collapse(text: object) -> str:
    """Collapse whitespace runs to single spaces and strip the ends."""
    if text is None:
        return ""
    return _WHITESPACE.sub(" ", str(text)).strip()


def canonicalize(value: object) -> object:
    """Recursively normalize strings; leave structure (and list order) intact.

    List order is preserved deliberately: step order is semantic in a test case,
    even though mapping key order is not.
    """
    if isinstance(value, dict):
        return {str(k): canonicalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonicalize(v) for v in value]
    if isinstance(value, str):
        return collapse(value)
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return collapse(value)


def _content_region(document: object) -> dict:
    """Pull just the hashed region out of whatever we were handed."""
    if hasattr(document, "content_region"):
        source = document.content_region()
    elif isinstance(document, dict):
        source = document
    else:  # pragma: no cover - defensive
        raise TypeError(f"cannot fingerprint {type(document)!r}")
    return {key: source.get(key) for key in CONTENT_KEYS}


def _digest(payload: object) -> str:
    blob = json.dumps(
        canonicalize(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def content_fingerprint(document: object) -> str:
    """Fingerprint a draft's content region (FR-045)."""
    return _digest(_content_region(document))


def rendered_fingerprint(summary: str, description_text: str) -> str:
    """Fingerprint an issue's *rendered* content: its summary and body text.

    This is what gets stored on the Jira issue, and it is deliberately over the
    rendered form rather than the draft fields. Comparing an issue against this
    needs only the issue's current summary and description -- no reverse-parsing
    of Atlassian Document Format back into test case fields, which would be
    fragile in exactly the place where a wrong answer means either a phantom
    conflict or an overwrite of someone's work (FR-040).
    """
    return _digest({"summary": collapse(summary), "body": collapse(description_text)})


def test_case_fingerprint(test_case: object) -> str:
    """Fingerprint one test case's content, for comparison against an issue.

    This is what gets stored on the Jira issue and compared on a later run to
    tell an untouched issue from one a person edited (FR-040).
    """
    if hasattr(test_case, "to_content_dict"):
        payload = test_case.to_content_dict()
    elif isinstance(test_case, dict):
        payload = {k: test_case.get(k) for k in TEST_CASE_CONTENT_FIELDS}
    else:  # pragma: no cover - defensive
        raise TypeError(f"cannot fingerprint {type(test_case)!r}")
    return _digest(payload)
