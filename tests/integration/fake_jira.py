"""A fake Jira that can be written to, for the publishing tests.

Richer than ``StubJira`` in conftest: it accepts creates, links, updates and
property writes, keeps the resulting state, and can be told to fail specific
calls. Failure injection is what makes the partial-failure, unlinked and
retry-exhaustion paths testable at all.
"""

from __future__ import annotations

from jira_testgen.jira.properties import PROPERTY_KEY

STORY_KEY = "PROJ-123"


class ReadTimeout(Exception):
    """Named so the client's timeout detection recognises it."""


def _identity_from_labels(payload) -> str | None:
    for label in ((payload or {}).get("fields") or {}).get("labels") or []:
        text = str(label)
        if text.startswith("tcgen-id-"):
            return text[len("tcgen-id-") :].upper()
    return None


class Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code = status
        self._body = {} if body is None else body
        self.headers = headers or {}
        self.text = str(self._body)

    def json(self):
        return self._body


class FakeJira:
    """A tiny writable Jira.

    ``fail_create_on`` / ``fail_link_on`` / ``fail_property_on`` take a set of
    1-based call ordinals for that operation, or a callable taking the ordinal.
    """

    def __init__(
        self,
        *,
        criteria: list[str] | None = None,
        linked: list[str] | None = None,
        properties: dict | None = None,
        issue_types: list[str] | None = None,
        link_types: list[str] | None = None,
        fail_create_on=None,
        fail_link_on=None,
        fail_property_on=None,
        create_status: int = 201,
        throttle_create_on=None,
        timeout_create_on=None,
        fail_update_on=None,
    ) -> None:
        self.criteria = criteria or [
            "User can request a reset link with a registered email address.",
            "Reset link expires after 24 hours.",
        ]
        self.linked = list(linked or [])
        self.properties = dict(properties or {})
        self.issue_types = issue_types if issue_types is not None else ["Task"]
        self.link_types = link_types if link_types is not None else ["Relates", "Blocks"]
        self.fail_create_on = fail_create_on
        self.fail_link_on = fail_link_on
        self.fail_property_on = fail_property_on
        self.create_status = create_status
        self.throttle_create_on = throttle_create_on
        self.timeout_create_on = timeout_create_on
        self.fail_update_on = fail_update_on
        self.deleted: set[str] = set()
        self._update_count = 0

        self.calls: list[tuple[str, str]] = []
        self.created: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.updated: list[str] = []
        self.issues: dict[str, dict] = {}
        self._create_count = 0
        self._link_count = 0
        self._property_count = 0
        self._next_key = 400

    # ------------------------------------------------------------ helpers

    @property
    def writes(self) -> list[tuple[str, str]]:
        return [(m, u) for m, u in self.calls if m in {"POST", "PUT", "DELETE"}]

    def _should_fail(self, spec, ordinal) -> bool:
        if spec is None:
            return False
        if callable(spec):
            return bool(spec(ordinal))
        return ordinal in spec

    # --- simulating what people do in Jira ------------------------------

    def edit_in_jira(self, key: str, *, summary=None, description_text=None) -> None:
        """Simulate a person editing a published test case issue directly."""
        fields = self.issues.setdefault(key, {}).setdefault("fields", {})
        if summary is not None:
            fields["summary"] = summary
        if description_text is not None:
            fields["description"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description_text}],
                    }
                ],
            }

    def delete_issue(self, key: str) -> None:
        """Simulate a person deleting a published test case issue.

        A fully propagated delete: the issue, its property and its link all go.
        """
        self.deleted.add(key)
        self.issues.pop(key, None)
        self.properties.pop(key, None)
        if key in self.linked:
            self.linked.remove(key)

    def vanish_content(self, key: str) -> None:
        """Simulate the issue being deleted *mid-run*.

        The property and the story link are still readable -- discovery already
        saw them -- but reading the issue itself now 404s. This is the only way
        a run can hold a marker for an issue that no longer exists, since the
        marker lives on the issue, and it is what makes the `recreate` decision
        reachable at all (FR-028).
        """
        self.deleted.add(key)
        self.issues.pop(key, None)

    def unlink(self, key: str) -> None:
        """Simulate the link to the story going away while the issue remains."""
        if key in self.linked:
            self.linked.remove(key)

    def _story_description(self) -> dict:
        content = [
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
                    for text in self.criteria
                ],
            },
        ]
        return {"type": "doc", "version": 1, "content": content}

    # ---------------------------------------------------------- transport

    def request(self, method, url, params=None, json=None, timeout=None):
        self.calls.append((method, url))

        if method == "GET" and url.endswith(f"/issue/{STORY_KEY}"):
            return Resp(
                200,
                {
                    "key": STORY_KEY,
                    "fields": {
                        "summary": "Password reset via email link",
                        "project": {"key": "PROJ"},
                        "description": self._story_description(),
                        "issuelinks": [{"outwardIssue": {"key": k}} for k in self.linked],
                    },
                },
            )

        if "/issue/createmeta" in url:
            names = (params or {}).get("issuetypeNames")
            if names and names not in self.issue_types:
                return Resp(200, {"projects": [{"key": "PROJ", "issuetypes": []}]})
            return Resp(
                200,
                {"projects": [{"key": "PROJ", "issuetypes": [{"name": names or "Task"}]}]},
            )

        if url.endswith("/issueLinkType"):
            return Resp(200, {"issueLinkTypes": [{"name": n} for n in self.link_types]})

        # A created test case issue, read back. Must come after the story route.
        if method == "GET" and "/issue/" in url and "/properties/" not in url:
            key = url.split("/issue/")[1].split("?")[0]
            if key in self.deleted:
                return Resp(404, {"errorMessages": ["Issue does not exist"]})
            if key in self.issues:
                return Resp(200, {"key": key, "fields": self.issues[key].get("fields", {})})

        if "/properties/" in url:
            key = url.split("/issue/")[1].split("/properties/")[0]
            if method == "GET":
                if key in self.properties:
                    return Resp(200, {"key": PROPERTY_KEY, "value": self.properties[key]})
                return Resp(404)
            if method == "PUT":
                self._property_count += 1
                if self._should_fail(self.fail_property_on, self._property_count):
                    return Resp(400, {"errorMessages": ["property rejected"]})
                self.properties[key] = json
                return Resp(200, {})

        if method == "POST" and url.endswith("/issue"):
            self._create_count += 1
            if self._should_fail(self.timeout_create_on, self._create_count):
                # The request reaches Jira and is applied, but the client never
                # learns the outcome. This is the duplicate trap FR-053 guards.
                self._next_key += 1
                key = f"PROJ-{self._next_key}"
                self.created.append(key)
                self.issues[key] = json
                identity = _identity_from_labels(json)
                if identity:
                    self.properties[key] = {
                        "identity": identity,
                        "content_fingerprint": "written-before-the-timeout",
                        "source_issue": STORY_KEY,
                    }
                raise ReadTimeout("read timed out after the create was applied")
            if self._should_fail(self.throttle_create_on, self._create_count):
                return Resp(429, {}, {"Retry-After": "1"})
            if self._should_fail(self.fail_create_on, self._create_count):
                return Resp(
                    400,
                    {"errors": {"issuetype": "Specify a valid issue type"}},
                )
            self._next_key += 1
            key = f"PROJ-{self._next_key}"
            self.created.append(key)
            self.issues[key] = json
            return Resp(self.create_status, {"key": key})

        if method == "PUT" and "/issue/" in url and "/properties/" not in url:
            key = url.split("/issue/")[1]
            self._update_count += 1
            if self._should_fail(self.fail_update_on, self._update_count):
                return Resp(400, {"errorMessages": ["update rejected"]})
            self.updated.append(key)
            existing = self.issues.setdefault(key, {}).setdefault("fields", {})
            existing.update((json or {}).get("fields", {}))
            return Resp(204, {})

        if method == "POST" and url.endswith("/issueLink"):
            self._link_count += 1
            if self._should_fail(self.fail_link_on, self._link_count):
                return Resp(400, {"errorMessages": ["link rejected"]})
            payload = json or {}
            inward = (payload.get("inwardIssue") or {}).get("key", "")
            outward = (payload.get("outwardIssue") or {}).get("key", "")
            self.links.append((inward, outward))
            if inward not in self.linked:
                self.linked.append(inward)
            return Resp(201, {})

        if "search/jql" in url:
            # Handles both `labels = "x"` and the batched `labels in (...)`.
            jql = (params or {}).get("jql", "").lower()
            hits = []
            for key, value in self.properties.items():
                identity = (value or {}).get("identity", "")
                if not identity:
                    continue
                label = f"tcgen-id-{identity.lower()}"
                if label in jql:
                    hits.append({"key": key, "fields": {"labels": [label]}})
            return Resp(200, {"issues": hits})

        return Resp(404, {"errorMessages": [f"fake has no route for {method} {url}"]})
