"""`doctor`: check configuration and the live site, writing nothing.

The checks run in a fixed order, and that order is the point (FR-032, FR-033):
setting *shape* is validated before Jira is contacted, so "this setting looks
wrong" (exit 2) never gets confused with "Jira rejected these credentials"
(exit 3). Everything after that is a site-level configuration problem, reported
by naming the setting to change.

Nothing here writes. The one check that would naturally want to -- can this
account write an issue property? -- is answered by querying permissions instead,
because a diagnostic command that creates things is not a diagnostic command.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jira_testgen.config import Config
from jira_testgen.errors import AuthError, JiraTestgenError, UserError
from jira_testgen.jira import issues
from jira_testgen.jira.client import JiraClient
from jira_testgen.logging_setup import get_logger

# Permissions a full publish run needs. Writing an issue property requires edit
# permission on the issue, which is why EDIT_ISSUES appears here.
REQUIRED_PERMISSIONS = ["CREATE_ISSUES", "EDIT_ISSUES", "LINK_ISSUES"]

OK = "ok"
FAIL = "fail"
SKIP = "skip"
WARN = "warn"


@dataclass
class Check:
    name: str
    status: str
    detail: str

    @property
    def passed(self) -> bool:
        return self.status in (OK, SKIP, WARN)


@dataclass
class DoctorReport:
    checks: list[Check] = field(default_factory=list)
    defaults_used: dict = field(default_factory=dict)

    def add(self, name: str, status: str, detail: str) -> Check:
        check = Check(name=name, status=status, detail=detail)
        self.checks.append(check)
        return check

    @property
    def ok(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def credentials_rejected(self) -> bool:
        """True when Jira refused the credentials.

        Reported separately so the caller can exit 3 rather than 2: "fix your
        .env" and "Jira said no" are different answers (FR-033).
        """
        return any(
            c.name == "credentials" and c.status == FAIL and "rejected" in c.detail
            for c in self.checks
        )

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "defaults_used": self.defaults_used,
            "checks": [
                {"name": c.name, "status": c.status, "detail": c.detail} for c in self.checks
            ],
        }

    def to_text(self) -> str:
        width = max((len(c.name) for c in self.checks), default=0)
        lines = []
        for check in self.checks:
            lines.append(f"  [{check.status:<4}] {check.name.ljust(width)}  {check.detail}")
        if self.defaults_used:
            lines.append("")
            lines.append("  defaults applied:")
            for name, value in sorted(self.defaults_used.items()):
                lines.append(f"    {name} -> {value}")
        lines.append("")
        lines.append(
            "  All checks passed." if self.ok else "  Some checks failed; see above."
        )
        return "\n".join(lines)


def run_doctor(
    config: Config,
    client: JiraClient,
    *,
    issue_key: str | None = None,
) -> DoctorReport:
    """Run the checks in order. ``config`` has already passed shape validation."""
    log = get_logger()
    report = DoctorReport(defaults_used=dict(config.defaults_used))

    # 1. Shape. Reaching here means load_config accepted every setting, which
    # is the check: a malformed one would have raised before any client existed.
    report.add(
        "settings",
        OK,
        "JIRA_BASE_URL, JIRA_EMAIL and JIRA_API_TOKEN are present and well-formed",
    )

    # 2. Credentials.
    try:
        me = issues.get_myself(client)
    except AuthError as exc:
        report.add("credentials", FAIL, f"Jira rejected them: {exc.message}")
        # Nothing further can be checked, and a wall of failures would obscure
        # the one that matters.
        return report
    except JiraTestgenError as exc:
        report.add("credentials", FAIL, f"could not reach Jira: {exc.message}")
        return report
    account = me.get("emailAddress") or me.get("displayName") or "(account)"
    report.add("credentials", OK, f"accepted for {account}")

    # The project the remaining checks apply to. Without one, project-scoped
    # checks are skipped rather than guessed at.
    project_key = config.project_key
    story_project = None
    if issue_key:
        try:
            story = issues.get_story(client, issue_key, ac_field=config.ac_field)
            story_project = story.project_key
            report.add("source issue", OK, f"{issue_key} is readable")
        except JiraTestgenError as exc:
            report.add("source issue", FAIL, exc.message)
            story = None
        else:
            # 5 (early, since we have the issue in hand). Does the configured
            # acceptance-criteria field actually hold anything here?
            if config.ac_field:
                if story.ac_field_text:
                    report.add(
                        "JIRA_AC_FIELD",
                        OK,
                        f"{config.ac_field} is readable and non-empty on {issue_key}",
                    )
                else:
                    report.add(
                        "JIRA_AC_FIELD",
                        WARN,
                        f"{config.ac_field} is empty on {issue_key}; criteria would be "
                        "read from the description instead",
                    )
    if not project_key:
        project_key = story_project

    if config.ac_field and not issue_key:
        # Confirm the field at least exists on this site.
        try:
            fields = issues.get_field_ids(client)
        except JiraTestgenError as exc:
            report.add("JIRA_AC_FIELD", WARN, f"could not list fields: {exc.message}")
        else:
            if config.ac_field in fields:
                report.add(
                    "JIRA_AC_FIELD",
                    OK,
                    f"{config.ac_field} exists on this site ({fields[config.ac_field]})",
                )
            else:
                report.add(
                    "JIRA_AC_FIELD",
                    FAIL,
                    f"{config.ac_field} does not exist on this site. "
                    "Set JIRA_AC_FIELD to a real customfield id, or leave it blank "
                    "to read criteria from the description.",
                )
    elif not config.ac_field:
        report.add(
            "JIRA_AC_FIELD",
            SKIP,
            "unset; acceptance criteria will be read from the issue description",
        )

    # 3. Issue type creatable in the target project.
    if not project_key:
        report.add(
            "JIRA_TEST_ISSUE_TYPE",
            SKIP,
            "no project to check against. Set JIRA_PROJECT_KEY, or pass "
            "--issue PROJ-123 to use that story's project.",
        )
    else:
        try:
            meta = issues.get_create_meta(
                client, project_key=project_key, issue_type=config.test_issue_type
            )
        except JiraTestgenError as exc:
            report.add("JIRA_TEST_ISSUE_TYPE", FAIL, exc.message)
        else:
            if meta:
                report.add(
                    "JIRA_TEST_ISSUE_TYPE",
                    OK,
                    f"'{config.test_issue_type}' is creatable in {project_key}",
                )
            else:
                report.add(
                    "JIRA_TEST_ISSUE_TYPE",
                    FAIL,
                    f"'{config.test_issue_type}' cannot be created in {project_key}. "
                    "Set JIRA_TEST_ISSUE_TYPE to a type this project accepts.",
                )

    # 4. Link type exists on the site.
    try:
        available = issues.list_link_type_names(client)
    except JiraTestgenError as exc:
        report.add("JIRA_LINK_TYPE", FAIL, f"could not list link types: {exc.message}")
    else:
        if config.link_type in available:
            report.add("JIRA_LINK_TYPE", OK, f"'{config.link_type}' exists on this site")
        else:
            report.add(
                "JIRA_LINK_TYPE",
                FAIL,
                f"'{config.link_type}' does not exist on this site. Set JIRA_LINK_TYPE "
                f"to one of: {', '.join(sorted(available)) or '(none found)'}.",
            )

    # 6. Permissions, including the edit permission that property writes need.
    try:
        granted = issues.get_my_permissions(
            client, project_key=project_key, permissions=REQUIRED_PERMISSIONS
        )
    except JiraTestgenError as exc:
        report.add(
            "permissions",
            WARN,
            f"could not be verified ({exc.message}); publishing may still fail",
        )
    else:
        missing = [p for p in REQUIRED_PERMISSIONS if not granted.get(p, False)]
        if not granted:
            report.add(
                "permissions",
                WARN,
                "Jira returned no permission information; publishing may still fail",
            )
        elif missing:
            scope = f" in {project_key}" if project_key else ""
            report.add(
                "permissions",
                FAIL,
                f"missing{scope}: {', '.join(missing)}. "
                "Issue properties carry each test case's identity, so EDIT_ISSUES is "
                "required as well as CREATE_ISSUES.",
            )
        else:
            scope = f" in {project_key}" if project_key else ""
            report.add(
                "permissions", OK, f"{', '.join(REQUIRED_PERMISSIONS)} granted{scope}"
            )

    log.debug("doctor finished: ok=%s", report.ok)
    return report


def doctor_failure() -> UserError:
    """The error raised when checks fail, so the exit code is a config error."""
    return UserError(
        "Some checks failed. Fix the settings named above in .env and run "
        "`jira-testgen doctor` again."
    )
