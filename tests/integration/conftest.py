"""Shared fixtures: a stub Jira and an isolated working directory.

The stub routes by URL so tests exercise the same code paths as a real site,
and it records every call -- which is how the "nothing was written to Jira"
assertions are made rather than assumed.
"""

from __future__ import annotations

import pytest

from jira_testgen.config import Config, SecretValue
from jira_testgen.jira.client import JiraClient
from jira_testgen.jira.properties import PROPERTY_KEY

STORY_KEY = "PROJ-123"

FIVE_CRITERIA_DESCRIPTION = {
    "type": "doc",
    "version": 1,
    "content": [
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": "Users need a password reset path."}],
        },
        {
            "type": "heading",
            "attrs": {"level": 3},
            "content": [{"type": "text", "text": "Acceptance Criteria"}],
        },
        {
            "type": "bulletList",
            "content": [
                {
                    "type": "listItem",
                    "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": text}]}
                    ],
                }
                for text in [
                    "User can request a reset link with a registered email address.",
                    "Reset link expires after 24 hours.",
                    "An unregistered address shows no hint that it is unregistered.",
                    "A used reset link cannot be reused.",
                    "The new password must meet the password policy.",
                ]
            ],
        },
    ],
}

NO_CRITERIA_DESCRIPTION = {
    "type": "doc",
    "version": 1,
    "content": [
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": "Nobody wrote criteria for this one."}],
        }
    ],
}


class Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code = status
        self._body = {} if body is None else body
        self.headers = headers or {}
        self.text = str(self._body)

    def json(self):
        return self._body


class StubJira:
    """A tiny Jira. Records calls; serves one story and its linked issues."""

    def __init__(self, *, description=None, linked=None, properties=None, summary=None):
        self.description = description if description is not None else FIVE_CRITERIA_DESCRIPTION
        self.linked = linked or []
        self.properties = properties or {}
        self.summary = summary or "Password reset via email link"
        self.calls: list[tuple[str, str]] = []

    # --- assertions used by the tests -----------------------------------

    @property
    def writes(self) -> list[tuple[str, str]]:
        """Every call that could change Jira."""
        return [(m, u) for m, u in self.calls if m in {"POST", "PUT", "DELETE"}]

    # --- transport ------------------------------------------------------

    def request(self, method, url, params=None, json=None, timeout=None):
        self.calls.append((method, url))

        if url.endswith(f"/issue/{STORY_KEY}"):
            return Resp(
                200,
                {
                    "key": STORY_KEY,
                    "fields": {
                        "summary": self.summary,
                        "project": {"key": "PROJ"},
                        "description": self.description,
                        "issuelinks": [{"outwardIssue": {"key": k}} for k in self.linked],
                    },
                },
            )

        if "/properties/" in url:
            for key, value in self.properties.items():
                if f"/issue/{key}/properties/{PROPERTY_KEY}" in url:
                    return Resp(200, {"key": PROPERTY_KEY, "value": value})
            return Resp(404)

        if url.endswith("/issue/MISSING-1"):
            return Resp(404, {"errorMessages": ["Issue does not exist"]})

        if "search/jql" in url:
            return Resp(200, {"issues": []})

        return Resp(404, {"errorMessages": [f"stub has no route for {url}"]})


@pytest.fixture
def config():
    return Config(
        base_url="https://example.atlassian.net",
        email="qa@example.com",
        api_token=SecretValue("token-value-long-enough"),
        project_key="PROJ",
    )


@pytest.fixture
def make_client(config):
    def _make(stub: StubJira) -> JiraClient:
        return JiraClient(config, session=stub, sleep=lambda _s: None)

    return _make


@pytest.fixture
def drafts_dir(tmp_path):
    d = tmp_path / "drafts"
    d.mkdir()
    return d
