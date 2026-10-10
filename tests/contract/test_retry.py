"""T016: retry policy contract (FR-051, FR-052, FR-053).

Uses an injected stub session rather than `responses`, because the behaviour
under test is *timing and classification*, not wire format: these tests need to
assert which waits were chosen and that a timed-out POST is never silently
repeated. A stub makes both observable and keeps the suite instant.
"""

import pytest

from jira_testgen.config import Config, SecretValue
from jira_testgen.errors import AmbiguousResultError, AuthError, PermanentError, TransientError
from jira_testgen.jira.client import MAX_BACKOFF_SECONDS, JiraClient


class FakeResponse:
    def __init__(self, status, body=None, headers=None):
        self.status_code = status
        self._body = body if body is not None else {}
        self.headers = headers or {}
        self.text = str(self._body)

    def json(self):
        return self._body


class FakeSession:
    """Replays a scripted sequence of responses or exceptions."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def request(self, method, url, params=None, json=None, timeout=None):
        self.calls.append((method, url))
        if not self.script:
            raise AssertionError("FakeSession ran out of scripted responses")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class ReadTimeout(Exception):
    pass


class ConnectionError_(Exception):
    pass


def _config():
    return Config(
        base_url="https://example.atlassian.net",
        email="qa@example.com",
        api_token=SecretValue("token-value-long-enough"),
    )


def _client(script, **kwargs):
    waits = []
    session = FakeSession(script)
    client = JiraClient(
        _config(),
        session=session,
        sleep=waits.append,
        **kwargs,
    )
    return client, session, waits


def test_successful_request_returns_the_body():
    client, session, waits = _client([FakeResponse(200, {"key": "PROJ-1"})])
    assert client.get("issue/PROJ-1") == {"key": "PROJ-1"}
    assert waits == []


def test_429_is_retried_then_succeeds():
    client, session, waits = _client(
        [FakeResponse(429, {}, {"Retry-After": "2"}), FakeResponse(200, {"ok": True})]
    )
    assert client.get("issue/PROJ-1") == {"ok": True}
    assert len(session.calls) == 2


def test_retry_after_is_honoured_rather_than_guessed():
    # The server stated 7 seconds; the client must not substitute its own
    # backoff curve (FR-051).
    client, _, waits = _client(
        [FakeResponse(429, {}, {"Retry-After": "7"}), FakeResponse(200, {})]
    )
    client.get("issue/PROJ-1")
    assert waits == [7.0]


def test_retry_after_as_http_date_is_understood():
    client, _, waits = _client(
        [
            FakeResponse(503, {}, {"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"}),
            FakeResponse(200, {}),
        ]
    )
    client.get("issue/PROJ-1")
    assert waits and waits[0] > 0


def test_retry_after_is_capped():
    client, _, waits = _client(
        [FakeResponse(429, {}, {"Retry-After": "9999"}), FakeResponse(200, {})]
    )
    client.get("issue/PROJ-1")
    assert waits == [MAX_BACKOFF_SECONDS]


def test_backoff_grows_when_no_retry_after_is_given():
    client, _, waits = _client(
        [FakeResponse(503), FakeResponse(503), FakeResponse(200, {})]
    )
    client.get("issue/PROJ-1")
    assert len(waits) == 2
    # Jittered, so assert the trend and the bound rather than exact values.
    assert waits[1] > waits[0]
    assert all(w <= MAX_BACKOFF_SECONDS for w in waits)


@pytest.mark.parametrize("status", [400, 404, 405, 409])
def test_permanent_statuses_are_not_retried(status):
    client, session, waits = _client([FakeResponse(status, {"errorMessages": ["nope"]})])
    with pytest.raises(PermanentError):
        client.get("issue/PROJ-1")
    assert len(session.calls) == 1
    assert waits == []


def test_401_raises_auth_error_without_retrying():
    client, session, _ = _client([FakeResponse(401)])
    with pytest.raises(AuthError):
        client.get("myself")
    assert len(session.calls) == 1


def test_exhausted_retries_raise_rather_than_hanging():
    client, session, _ = _client([FakeResponse(503)] * 5, max_attempts=5)
    with pytest.raises(TransientError) as excinfo:
        client.get("issue/PROJ-1")
    assert len(session.calls) == 5
    assert "after 5 attempts" in str(excinfo.value)


def test_allow_404_returns_none_for_an_absent_property():
    # Reading a property that was never written is a legitimate answer, not an
    # error (FR-026c).
    client, _, _ = _client([FakeResponse(404)])
    assert client.request("GET", "issue/PROJ-1/properties/x", allow_404=True) is None


def test_timed_out_post_is_ambiguous_and_never_silently_retried():
    # The create may have landed. Retrying blind is how duplicates appear, so
    # the caller must resolve it by identity first (FR-053).
    client, session, waits = _client([ReadTimeout("read timed out")])
    with pytest.raises(AmbiguousResultError):
        client.post("issue", json={})
    assert len(session.calls) == 1
    assert waits == []


def test_timed_out_get_is_merely_transient_and_is_retried():
    client, session, _ = _client([ReadTimeout("read timed out"), FakeResponse(200, {"ok": 1})])
    assert client.get("issue/PROJ-1") == {"ok": 1}
    assert len(session.calls) == 2


def test_connection_error_is_retried():
    client, session, _ = _client(
        [ConnectionError_("connection refused"), FakeResponse(200, {"ok": 1})]
    )
    assert client.get("issue/PROJ-1") == {"ok": 1}
    assert len(session.calls) == 2


def test_non_json_error_body_does_not_mask_the_status():
    class Unparseable(FakeResponse):
        def json(self):
            raise ValueError("not json")

    client, _, _ = _client([Unparseable(400)])
    with pytest.raises(PermanentError):
        client.get("issue/PROJ-1")
