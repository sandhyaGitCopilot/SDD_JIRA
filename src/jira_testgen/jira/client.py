"""Jira Cloud HTTP client: auth, and the retry policy.

The policy (FR-051, FR-052, research.md §8):

- Retry only ``TransientError`` -- 429, 502, 503, 504, and connection or read
  timeouts.
- **Honour ``Retry-After`` when the server sends one.** Guessing an interval
  when Jira has stated one is both wrong and likely to deepen the throttle.
- Otherwise back off exponentially from 1s, doubling, with jitter, each wait
  capped at 30s.
- Five attempts, then give up and let the caller report a resumable stop.
- Never retry a permanent failure; report it at once with its reason.

A write whose outcome is unknown -- a timeout on a POST -- raises
``AmbiguousResultError`` rather than a plain transient error, because the
request may have landed. The caller must resolve that by looking for the
identity before trying again (FR-053); retrying blindly is how duplicates get
created.
"""

from __future__ import annotations

import email.utils
import random
import time
from typing import Any

from jira_testgen.config import Config
from jira_testgen.errors import (
    AmbiguousResultError,
    JiraTestgenError,
    TransientError,
    classify_status,
)
from jira_testgen.logging_setup import get_logger

MAX_ATTEMPTS = 5
INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 30.0
REQUEST_TIMEOUT_SECONDS = 30.0

# Methods that are safe to repeat without first checking whether they landed.
_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "PUT", "DELETE"})


class JiraClient:
    """Thin REST wrapper. The only place in this project that speaks HTTP."""

    def __init__(
        self,
        config: Config,
        *,
        session: Any | None = None,
        sleep: Any = time.sleep,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        self.config = config
        # Public, so callers that do their own waiting -- the identity lookup's
        # index settle, for instance -- wait the same way and stay injectable
        # from tests.
        self.sleep = sleep
        self._sleep = sleep
        self._max_attempts = max_attempts
        self._log = get_logger()
        # Retries since the counter was last reset. The publish loop resets it
        # per test case, so the report can say which ones were slow (FR-055).
        self.retries = 0
        self._session = session if session is not None else self._build_session()

    def reset_retry_count(self) -> None:
        self.retries = 0

    def _build_session(self):
        import requests

        session = requests.Session()
        # The token reaches exactly one place: this header. Nothing logs headers.
        session.auth = (self.config.email, self.config.api_token.reveal())
        session.headers.update(
            {"Accept": "application/json", "Content-Type": "application/json"}
        )
        return session

    # ----------------------------------------------------------------- verbs

    def get(self, path: str, *, params: dict | None = None) -> Any:
        return self.request("GET", path, params=params)

    def post(self, path: str, *, json: dict | None = None) -> Any:
        return self.request("POST", path, json=json)

    def put(self, path: str, *, json: dict | None = None) -> Any:
        return self.request("PUT", path, json=json)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)

    # --------------------------------------------------------------- engine

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
        allow_404: bool = False,
    ) -> Any:
        """Send a request, retrying transient failures.

        ``allow_404`` returns ``None`` instead of raising, for lookups where
        absence is a legitimate answer -- reading an issue property that was
        never written, for instance (FR-026c).
        """
        url = self.config.api_url(path)
        last_error: JiraTestgenError | None = None

        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._session.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
            except Exception as exc:  # noqa: BLE001 - normalised just below
                last_error = self._classify_exception(exc, method)
                if isinstance(last_error, AmbiguousResultError):
                    # Never retried here: the caller has to check whether the
                    # write landed before deciding (FR-053).
                    raise last_error from exc
                self._log.debug(
                    "%s %s attempt %d failed: %s", method, path, attempt, last_error.message
                )
                self._wait(attempt, last_error)
                continue

            status = getattr(response, "status_code", 0)
            if allow_404 and status == 404:
                self._log.debug("%s %s -> 404 (absent, allowed)", method, path)
                return None

            if 200 <= status < 300:
                self._log.debug("%s %s -> %d (attempt %d)", method, path, status, attempt)
                return _body(response)

            error = classify_status(
                status,
                body=_body(response, quiet=True),
                retry_after=_retry_after_seconds(response),
            )
            if not isinstance(error, TransientError):
                self._log.debug("%s %s -> %d (permanent)", method, path, status)
                raise error

            last_error = error
            self._log.debug(
                "%s %s -> %d (transient, attempt %d of %d)",
                method,
                path,
                status,
                attempt,
                self._max_attempts,
            )
            if attempt < self._max_attempts:
                self._wait(attempt, error)

        assert last_error is not None
        raise TransientError(
            f"Gave up on {method} {path} after {self._max_attempts} attempts: "
            f"{last_error.message}",
            status=last_error.status,
        )

    # ---------------------------------------------------------------- waits

    def _wait(self, attempt: int, error: JiraTestgenError) -> None:
        if attempt >= self._max_attempts:
            return
        delay = self._delay_for(attempt, error)
        self.retries += 1
        self._log.debug("waiting %.1fs before attempt %d", delay, attempt + 1)
        self._sleep(delay)

    def _delay_for(self, attempt: int, error: JiraTestgenError) -> float:
        stated = getattr(error, "retry_after", None)
        if stated is not None:
            # The server told us. Do not argue with it.
            return min(float(stated), MAX_BACKOFF_SECONDS)
        base = min(INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1)), MAX_BACKOFF_SECONDS)
        # Jitter keeps concurrent clients from synchronising their retries.
        return base * (0.5 + random.random() / 2)

    # ----------------------------------------------------------- exceptions

    @staticmethod
    def _classify_exception(exc: Exception, method: str) -> JiraTestgenError:
        name = type(exc).__name__
        is_timeout = "Timeout" in name or "timed out" in str(exc).lower()
        is_connection = "Connection" in name

        if is_timeout and method.upper() not in _IDEMPOTENT_METHODS:
            return AmbiguousResultError(
                f"{method} timed out; it may or may not have been applied."
            )
        if is_timeout or is_connection:
            return TransientError(f"{name}: {exc}")
        return AmbiguousResultError(f"{name}: {exc}")


def _retry_after_seconds(response: Any) -> float | None:
    """Read ``Retry-After``, which may be seconds or an HTTP date."""
    headers = getattr(response, "headers", None) or {}
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if raw is None:
        return None
    text = str(raw).strip()
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    parsed = email.utils.parsedate_to_datetime(text)
    if parsed is None:
        return None
    import datetime as _dt

    now = _dt.datetime.now(_dt.UTC)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.UTC)
    return max(0.0, (parsed - now).total_seconds())


def _body(response: Any, *, quiet: bool = False) -> Any:
    try:
        return response.json()
    except Exception:  # noqa: BLE001 - a non-JSON body is not fatal
        if quiet:
            return getattr(response, "text", None)
        return None
