"""T090: the decision engine, at unit level (FR-026 - FR-029, FR-038 - FR-040).

The integration tests exercise these through whole publish runs. These pin the
truth table directly, so a wrong answer is localised to `decide` rather than
showing up three layers away -- and so the cases that are awkward to stage
through a full run (a malformed marker, a missing link combined with a Jira-side
edit) get covered at all.
"""

from __future__ import annotations

import pytest

from jira_testgen.config import Config, SecretValue
from jira_testgen.draft.fingerprint import rendered_fingerprint
from jira_testgen.draft.schema import TestCase as DraftTestCase
from jira_testgen.jira.client import JiraClient
from jira_testgen.jira.issues import PublishedTestCase
from jira_testgen.jira.properties import PublicationMarker
from jira_testgen.publish import _rendered_draft, decide

STORY = "PROJ-123"


def _case(identity=f"{STORY}-TC-001", **overrides):
    defaults = dict(
        identity=identity,
        category="positive",
        covers=["AC-1"],
        summary="Request a reset link",
        preconditions="An account exists.",
        steps=["Open the page.", "Submit."],
        expected_results="A link arrives.",
    )
    defaults.update(overrides)
    return DraftTestCase(**defaults)


class _Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body
        self.headers: dict = {}
        self.text = str(body)

    def json(self):
        return self._body


class _Session:
    """Serves one issue's content, or a 404."""

    def __init__(self, *, summary=None, body_text=None, missing=False):
        self.summary = summary
        self.body_text = body_text
        self.missing = missing

    def request(self, method, url, params=None, json=None, timeout=None):
        if self.missing:
            return _Resp(404, {"errorMessages": ["Issue does not exist"]})
        description = None
        if self.body_text is not None:
            description = {
                "type": "doc",
                "version": 1,
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": self.body_text}]}
                ],
            }
        return _Resp(200, {"key": "PROJ-401", "fields": {
            "summary": self.summary or "", "description": description}})


def _client(session):
    config = Config(
        base_url="https://example.atlassian.net",
        email="qa@example.com",
        api_token=SecretValue("token-value-long-enough"),
    )
    return JiraClient(config, session=session, sleep=lambda _s: None)


def _published(case, *, fingerprint, link_present=True, issue_key="PROJ-401"):
    return {
        case.identity: PublishedTestCase(
            identity=case.identity,
            issue_key=issue_key,
            marker=PublicationMarker(
                identity=case.identity,
                content_fingerprint=fingerprint,
                source_issue=STORY,
            ),
            link_present=link_present,
        )
    }


def _as_jira_holds_it(case):
    """The summary and body text this case would have been published as."""
    return _rendered_draft(case, STORY)


# --- create -------------------------------------------------------------


def test_nothing_published_means_create():
    decision = decide(_client(_Session()), _case(), {}, story_key=STORY)
    assert decision.action == "create"
    assert decision.issue_key is None


def test_create_makes_no_request():
    # Nothing to compare against, so asking Jira would be wasted.
    session = _Session()
    calls: list = []
    session.request = lambda *a, **k: calls.append(1) or _Resp(200, {})  # type: ignore[method-assign]
    decide(_client(session), _case(), {}, story_key=STORY)
    assert calls == []


# --- unchanged ----------------------------------------------------------


def test_matching_issue_and_matching_draft_means_unchanged():
    case = _case()
    summary, body = _as_jira_holds_it(case)
    fingerprint = rendered_fingerprint(summary, body)
    decision = decide(
        _client(_Session(summary=summary, body_text=body)),
        case,
        _published(case, fingerprint=fingerprint),
        story_key=STORY,
    )
    assert decision.action == "unchanged"
    assert decision.issue_key == "PROJ-401"


# --- update -------------------------------------------------------------


def test_untouched_issue_with_a_changed_draft_means_update():
    published_case = _case()
    summary, body = _as_jira_holds_it(published_case)
    fingerprint = rendered_fingerprint(summary, body)

    edited = _case(steps=["Open the page.", "Submit.", "Check the audit log."])
    decision = decide(
        _client(_Session(summary=summary, body_text=body)),
        edited,
        _published(edited, fingerprint=fingerprint),
        story_key=STORY,
    )
    assert decision.action == "update"
    assert decision.issue_key == "PROJ-401"


# --- conflict -----------------------------------------------------------


def test_an_issue_edited_in_jira_means_conflict():
    case = _case()
    summary, body = _as_jira_holds_it(case)
    fingerprint = rendered_fingerprint(summary, body)
    decision = decide(
        _client(_Session(summary=summary, body_text="Rewritten by a reviewer.")),
        case,
        _published(case, fingerprint=fingerprint),
        story_key=STORY,
    )
    assert decision.action == "conflict"
    assert "description" in decision.fields_differing
    assert decision.reason and "edited in Jira" in decision.reason


def test_a_renamed_issue_reports_the_summary_as_differing():
    case = _case()
    summary, body = _as_jira_holds_it(case)
    fingerprint = rendered_fingerprint(summary, body)
    decision = decide(
        _client(_Session(summary="Renamed by hand", body_text=body)),
        case,
        _published(case, fingerprint=fingerprint),
        story_key=STORY,
    )
    assert decision.action == "conflict"
    assert "summary" in decision.fields_differing


def test_conflict_wins_over_a_missing_link():
    # Both are true; refusing to touch the issue is the safer answer, and
    # relinking a conflicted issue would imply the tool had accepted it.
    case = _case()
    summary, body = _as_jira_holds_it(case)
    fingerprint = rendered_fingerprint(summary, body)
    decision = decide(
        _client(_Session(summary=summary, body_text="Edited in Jira.")),
        case,
        _published(case, fingerprint=fingerprint, link_present=False),
        story_key=STORY,
    )
    assert decision.action == "conflict"


def test_conflict_always_names_at_least_one_field():
    # The fingerprint differs but neither field does -- possible when the
    # rendering changed between tool versions. The report must still say
    # something rather than showing an empty list.
    case = _case()
    summary, body = _as_jira_holds_it(case)
    decision = decide(
        _client(_Session(summary=summary, body_text=body)),
        case,
        _published(case, fingerprint="a-stale-fingerprint-from-an-older-version"),
        story_key=STORY,
    )
    assert decision.action == "conflict"
    assert decision.fields_differing


# --- relink -------------------------------------------------------------


def test_an_untouched_issue_with_no_link_means_relink():
    case = _case()
    summary, body = _as_jira_holds_it(case)
    fingerprint = rendered_fingerprint(summary, body)
    decision = decide(
        _client(_Session(summary=summary, body_text=body)),
        case,
        _published(case, fingerprint=fingerprint, link_present=False),
        story_key=STORY,
    )
    assert decision.action == "relink"
    assert decision.issue_key == "PROJ-401"


# --- recreate -----------------------------------------------------------


def test_an_issue_that_no_longer_exists_means_recreate():
    case = _case()
    decision = decide(
        _client(_Session(missing=True)),
        case,
        _published(case, fingerprint="whatever"),
        story_key=STORY,
    )
    assert decision.action == "recreate"
    assert decision.reason and "no longer exists" in decision.reason


def test_recreate_wins_over_a_missing_link():
    # There is nothing to relink to.
    case = _case()
    decision = decide(
        _client(_Session(missing=True)),
        case,
        _published(case, fingerprint="whatever", link_present=False),
        story_key=STORY,
    )
    assert decision.action == "recreate"


# --- the timestamp that must never be consulted -------------------------


def test_the_issue_updated_timestamp_is_never_used():
    """Automations, transitions and comments all bump `updated`.

    Using it would produce a phantom conflict every time somebody commented on
    a test case, so the field is not even requested.
    """
    case = _case()
    summary, body = _as_jira_holds_it(case)
    fingerprint = rendered_fingerprint(summary, body)

    requested: list[str] = []

    class Recording(_Session):
        def request(self, method, url, params=None, json=None, timeout=None):
            requested.append((params or {}).get("fields", ""))
            return super().request(method, url, params=params, json=json, timeout=timeout)

    decide(
        _client(Recording(summary=summary, body_text=body)),
        case,
        _published(case, fingerprint=fingerprint),
        story_key=STORY,
    )
    assert requested
    assert all("updated" not in fields for fields in requested)


@pytest.mark.parametrize(
    "decision_action",
    ["create", "unchanged", "update", "conflict", "relink", "recreate"],
)
def test_every_decision_action_is_reachable(decision_action):
    # A guard against a branch quietly becoming dead, as `recreate` nearly did
    # when state moved onto the issues.
    case = _case()
    summary, body = _as_jira_holds_it(case)
    fingerprint = rendered_fingerprint(summary, body)

    scenarios = {
        "create": (_Session(), {}),
        "unchanged": (
            _Session(summary=summary, body_text=body),
            _published(case, fingerprint=fingerprint),
        ),
        "update": (
            _Session(summary=summary, body_text=body),
            _published(_case(steps=["Changed."]), fingerprint=fingerprint),
        ),
        "conflict": (
            _Session(summary=summary, body_text="Edited."),
            _published(case, fingerprint=fingerprint),
        ),
        "relink": (
            _Session(summary=summary, body_text=body),
            _published(case, fingerprint=fingerprint, link_present=False),
        ),
        "recreate": (_Session(missing=True), _published(case, fingerprint=fingerprint)),
    }
    session, published = scenarios[decision_action]
    subject = case if decision_action != "update" else _case(steps=["Changed."])
    assert decide(_client(session), subject, published, story_key=STORY).action == (
        decision_action
    )
