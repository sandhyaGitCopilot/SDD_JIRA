"""T009: error classification (FR-051, FR-052).

Covers every status in the two lists the retry policy is built on, plus the
timeout shape, because a misclassification here either hangs a run or gives up
on a request that would have succeeded.
"""

import pytest

from jira_testgen.errors import (
    PERMANENT_STATUSES,
    TRANSIENT_STATUSES,
    AuthError,
    PermanentError,
    TransientError,
    body_indicates_permanent,
    classify_status,
)


@pytest.mark.parametrize("status", sorted(TRANSIENT_STATUSES))
def test_transient_statuses_are_retryable(status):
    assert isinstance(classify_status(status), TransientError)


@pytest.mark.parametrize("status", sorted(PERMANENT_STATUSES - {401, 403}))
def test_permanent_statuses_are_not_retryable(status):
    err = classify_status(status)
    assert isinstance(err, PermanentError)
    assert not isinstance(err, TransientError)


def test_401_is_an_auth_error_not_a_permanent_request_error():
    # Kept distinct so "Jira rejected these credentials" stays separable from
    # "this request is malformed" (FR-033).
    assert isinstance(classify_status(401), AuthError)


def test_403_is_permanent_but_not_an_auth_error():
    # The account is known; it simply may not do this.
    err = classify_status(403)
    assert isinstance(err, PermanentError)
    assert not isinstance(err, AuthError)


def test_retry_after_is_carried_on_transient_errors():
    err = classify_status(429, retry_after=12.5)
    assert isinstance(err, TransientError)
    assert err.retry_after == 12.5


def test_unlisted_5xx_is_treated_as_transient():
    assert isinstance(classify_status(507), TransientError)


def test_429_is_never_permanent_even_with_a_fieldish_body():
    # Throttling wins over body sniffing: a rate-limited request has not been
    # evaluated yet, so its body cannot tell us the request is wrong.
    err = classify_status(429, body={"errors": {"issuetype": "bad"}})
    assert isinstance(err, TransientError)


@pytest.mark.parametrize(
    "body",
    [
        {"errors": {"issuetype": "Specify an issue type"}},
        {"errorMessages": ["Field 'customfield_10040' cannot be set"]},
        {"errorMessages": ["You do not have permission to create issues"]},
    ],
)
def test_field_and_permission_bodies_are_permanent(body):
    assert body_indicates_permanent(body)


def test_unremarkable_body_is_not_permanent():
    assert not body_indicates_permanent({"errorMessages": []})
    assert not body_indicates_permanent(None)


def test_permanent_error_reason_summarizes_the_jira_envelope():
    err = classify_status(400, body={"errors": {"summary": "Summary must be less than 255"}})
    assert isinstance(err, PermanentError)
    assert "summary" in err.reason
