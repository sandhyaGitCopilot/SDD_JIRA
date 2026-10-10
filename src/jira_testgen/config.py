"""Configuration loading and validation (FR-030 - FR-035).

Two rules shape this module.

**Shape before network.** Every setting is checked for presence and form before
any request is made, so a missing or malformed setting is reported by name
without contacting Jira. Only then are credentials exercised. That ordering is
what keeps "this setting looks wrong" (exit 2) distinguishable from "Jira
rejected these credentials" (exit 3) -- FR-032, FR-033.

**The token is not a string.** It is wrapped in ``SecretValue``, which has no
``__repr__``, no ``__str__``, and no serialization path that yields its value
(FR-034, T012). Reaching the real token requires calling ``.reveal()``, which
happens in exactly one place: building the auth header.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from jira_testgen.errors import UserError
from jira_testgen.logging_setup import register_secret

DEFAULT_TEST_ISSUE_TYPE = "Task"
DEFAULT_LINK_TYPE = "Relates"

_PROJECT_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_AC_FIELD_RE = re.compile(r"^customfield_\d+$")
_ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*-\d+$")


class SecretValue:
    """A string that will not reveal itself by accident.

    Printing it, formatting it, logging it, or putting it in a traceback yields
    a placeholder. Only ``reveal()`` returns the real value.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __bool__(self) -> bool:
        return bool(self._value)

    def __len__(self) -> int:
        # Length is safe to expose and useful for "is it plausibly a token?".
        return len(self._value)

    def __repr__(self) -> str:
        return "SecretValue(***REDACTED***)"

    __str__ = __repr__

    def __format__(self, _spec: str) -> str:
        return "***REDACTED***"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, SecretValue):
            return self._value == other._value
        return NotImplemented

    def __hash__(self) -> int:
        return hash(("SecretValue", self._value))

    def __reduce__(self):
        # Refuse to pickle: serialization is a leak path.
        raise TypeError("SecretValue must not be serialized.")


@dataclass(frozen=True)
class Config:
    base_url: str
    email: str
    api_token: SecretValue
    project_key: str | None = None
    test_issue_type: str = DEFAULT_TEST_ISSUE_TYPE
    link_type: str = DEFAULT_LINK_TYPE
    ac_field: str | None = None
    defaults_used: dict[str, str] = field(default_factory=dict)

    def api_url(self, path: str) -> str:
        """Absolute URL for a v3 REST path."""
        return f"{self.base_url}/rest/api/3/{path.lstrip('/')}"


def validate_issue_key(key: str) -> str:
    """Reject a malformed issue key before any request is made (FR-001)."""
    candidate = (key or "").strip()
    if not _ISSUE_KEY_RE.match(candidate):
        raise UserError(
            f"'{key}' is not a Jira issue key. Expected a form like PROJ-123."
        )
    return candidate


def load_config(env_file: str | os.PathLike[str] | None = ".env") -> Config:
    """Read and validate configuration.

    Raises ``UserError`` naming every missing or malformed required setting --
    all of them at once, so an engineer fixing three blanks learns about three
    blanks rather than discovering them one run at a time (FR-032).
    """
    values = _read_env(env_file)

    problems: list[str] = []

    base_url = (values.get("JIRA_BASE_URL") or "").strip().rstrip("/")
    if not base_url:
        problems.append("JIRA_BASE_URL is missing.")
    elif not base_url.startswith(("https://", "http://")):
        problems.append(
            "JIRA_BASE_URL must start with https:// "
            f"(found '{base_url}')."
        )

    email = (values.get("JIRA_EMAIL") or "").strip()
    if not email:
        problems.append("JIRA_EMAIL is missing.")
    elif "@" not in email:
        problems.append(f"JIRA_EMAIL does not look like an address (found '{email}').")

    raw_token = (values.get("JIRA_API_TOKEN") or "").strip()
    if not raw_token:
        problems.append("JIRA_API_TOKEN is missing.")
    else:
        # Registered the moment it is read, before anything else can run.
        # Defence in depth for FR-034: even the paths that fail during
        # validation -- and any message added here in future -- are scrubbed.
        register_secret(raw_token)

    defaults_used: dict[str, str] = {}

    project_key = (values.get("JIRA_PROJECT_KEY") or "").strip() or None
    if project_key and not _PROJECT_KEY_RE.match(project_key):
        problems.append(
            "JIRA_PROJECT_KEY must be uppercase letters, digits, and underscores "
            f"(found '{project_key}')."
        )
    if not project_key:
        defaults_used["JIRA_PROJECT_KEY"] = "the source story's own project"

    test_issue_type = (values.get("JIRA_TEST_ISSUE_TYPE") or "").strip()
    if not test_issue_type:
        test_issue_type = DEFAULT_TEST_ISSUE_TYPE
        defaults_used["JIRA_TEST_ISSUE_TYPE"] = DEFAULT_TEST_ISSUE_TYPE

    link_type = (values.get("JIRA_LINK_TYPE") or "").strip()
    if not link_type:
        link_type = DEFAULT_LINK_TYPE
        defaults_used["JIRA_LINK_TYPE"] = DEFAULT_LINK_TYPE

    ac_field = (values.get("JIRA_AC_FIELD") or "").strip() or None
    if ac_field and not _AC_FIELD_RE.match(ac_field):
        problems.append(
            "JIRA_AC_FIELD must look like customfield_12345 "
            f"(found '{ac_field}')."
        )
    if not ac_field:
        defaults_used["JIRA_AC_FIELD"] = "unset; criteria read from the description"

    if problems:
        raise UserError(
            "Configuration is incomplete. Fix these settings in .env "
            "(copy .env.example if you have not yet):\n  - "
            + "\n  - ".join(problems)
        )

    return Config(
        base_url=base_url,
        email=email,
        api_token=SecretValue(raw_token),
        project_key=project_key,
        test_issue_type=test_issue_type,
        link_type=link_type,
        ac_field=ac_field,
        defaults_used=defaults_used,
    )


def _read_env(env_file: str | os.PathLike[str] | None) -> dict[str, str]:
    """Merge a .env file over the process environment.

    python-dotenv is used when installed; a tiny parser stands in otherwise, so
    that configuration never fails for want of an optional import.
    """
    merged: dict[str, str] = {
        k: v
        for k, v in os.environ.items()
        if k.startswith("JIRA_")
    }
    if env_file is None:
        return merged

    path = Path(env_file)
    if not path.is_file():
        return merged

    try:
        from dotenv import dotenv_values

        parsed = {k: v for k, v in dotenv_values(path).items() if v is not None}
    except ImportError:  # pragma: no cover - exercised only without python-dotenv
        parsed = _parse_env_file(path)

    # A real environment variable wins over the file, which is what lets a test
    # or a one-off run override a setting without editing .env.
    for key, value in parsed.items():
        merged.setdefault(key, value)
    return merged


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out
