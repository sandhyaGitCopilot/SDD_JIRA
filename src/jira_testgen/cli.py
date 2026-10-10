"""Command-line interface.

There is deliberately no ``generate`` command. Test case content is written by
the engineer's Claude Code session into the scaffold ``prepare`` produces, so
there is no code path that could quietly produce content some other way
(FR-036). Every command here runs headless without a session (FR-037).

stdout carries the report only, so it stays pipeable; logs go to stderr.
Exit codes are listed in ``ExitCode`` and are part of the published contract --
the Claude Code skill branches on them rather than parsing prose.
"""

from __future__ import annotations

import argparse
import json as jsonlib
import sys
from enum import IntEnum

from jira_testgen import __version__
from jira_testgen.errors import AuthError, JiraTestgenError, UserError
from jira_testgen.logging_setup import configure_logging, get_logger, scrub


class ExitCode(IntEnum):
    """The published exit-code contract (contracts/cli.md)."""

    SUCCESS = 0
    INTERNAL_ERROR = 1
    CONFIG_ERROR = 2
    AUTH_REJECTED = 3
    ISSUE_NOT_FOUND = 4
    NO_CRITERIA = 5
    DRAFT_REFUSED = 6
    DRAFT_EXISTS = 7
    CRITERIA_CHANGED = 8
    SET_TOO_LARGE = 9
    PARTIAL = 10
    RETRIES_EXHAUSTED = 11


class NotYetImplemented(JiraTestgenError):
    """A command whose phase has not been built yet.

    Distinct from a failure: it reports which task delivers the behaviour, so a
    half-built tool says so plainly instead of appearing broken.
    """

    exit_code = ExitCode.INTERNAL_ERROR


def _emit(text: str = "", *, stream=None) -> None:
    """Print, scrubbed.

    Every byte this tool writes to stdout or stderr goes through here. The log
    formatter already scrubs logs, but reports and error messages reach the
    terminal by a different route -- and FR-034 covers "any output, report,
    draft file, or log". Centralising it means a future print cannot leak by
    omission, which is exactly how the first version of this did leak: a
    transport exception carrying the token landed in a `doctor` check detail
    and went straight to stdout.
    """
    print(scrub(str(text)), file=stream or sys.stdout)  # noqa: T201 - the one real print


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jira-testgen",
        description=(
            "Turn a Jira Cloud story into reviewed, ready-to-use manual test cases."
        ),
    )
    parser.add_argument("--version", action="version", version=f"jira-testgen {__version__}")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--json", action="store_true", help="emit the machine-readable report on stdout"
    )
    common.add_argument("--verbose", action="store_true", help="log at INFO level")
    common.add_argument(
        "--debug",
        action="store_true",
        help="log request metadata (method, path, status, attempt, wait) -- never bodies",
    )
    common.add_argument("--log-file", metavar="PATH", help="also write logs to PATH")
    common.add_argument(
        "--env-file", metavar="PATH", default=".env", help="configuration file (default: .env)"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser(
        "doctor",
        parents=[common],
        help="validate configuration and the live site without writing anything",
    )
    doctor.add_argument(
        "--issue",
        metavar="KEY",
        help="check the acceptance-criteria field against this issue",
    )

    prepare = sub.add_parser(
        "prepare", parents=[common], help="fetch a story and write a draft scaffold"
    )
    prepare.add_argument("issue_key", metavar="ISSUE-KEY")
    prepare.add_argument(
        "--regenerate",
        action="store_true",
        help="replace an existing draft, keeping the previous version as a backup",
    )
    prepare.add_argument(
        "--drafts-dir", metavar="PATH", default="drafts", help="where drafts live"
    )

    validate = sub.add_parser(
        "validate", parents=[common], help="check a draft file without contacting Jira"
    )
    validate.add_argument("issue_key", metavar="ISSUE-KEY")
    validate.add_argument(
        "--drafts-dir", metavar="PATH", default="drafts", help="where drafts live"
    )

    publish = sub.add_parser(
        "publish", parents=[common], help="create or update test case issues in Jira"
    )
    publish.add_argument("issue_key", metavar="ISSUE-KEY")
    # Per-run only: neither override may be set in .env (FR-067).
    publish.add_argument(
        "--allow-large",
        action="store_true",
        help="publish a set of more than 100 test cases (per-run only)",
    )
    publish.add_argument(
        "--allow-stale-criteria",
        action="store_true",
        help="publish although the story's criteria changed since drafting (per-run only)",
    )
    publish.add_argument(
        "--drafts-dir", metavar="PATH", default="drafts", help="where drafts live"
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    configure_logging(
        verbose=getattr(args, "verbose", False),
        debug=getattr(args, "debug", False),
        log_file=getattr(args, "log_file", None),
    )
    log = get_logger()

    try:
        handler = {
            "doctor": _cmd_doctor,
            "prepare": _cmd_prepare,
            "validate": _cmd_validate,
            "publish": _cmd_publish,
        }[args.command]
        return int(handler(args))
    except UserError as exc:
        # Scrubbed on the way out: an error message is the likeliest place for a
        # secret to escape, and nobody writes the formatting (FR-034).
        _emit(exc.message, stream=sys.stderr)
        return int(ExitCode.CONFIG_ERROR)
    except AuthError as exc:
        _emit(exc.message, stream=sys.stderr)
        return int(ExitCode.AUTH_REJECTED)
    except JiraTestgenError as exc:
        _emit(exc.message, stream=sys.stderr)
        return int(getattr(exc, "exit_code", ExitCode.INTERNAL_ERROR))
    except KeyboardInterrupt:  # pragma: no cover
        _emit("Interrupted.", stream=sys.stderr)
        return int(ExitCode.INTERNAL_ERROR)
    except Exception as exc:  # noqa: BLE001 - last resort, still redacted
        log.debug("unhandled error", exc_info=True)
        _emit(f"Unexpected error: {exc}", stream=sys.stderr)
        return int(ExitCode.INTERNAL_ERROR)


# ---------------------------------------------------------------------------
# Command handlers.
# ---------------------------------------------------------------------------


def _build_client(args):
    """Load config and open a client. Shape is validated before any request."""
    from jira_testgen.config import load_config
    from jira_testgen.jira.client import JiraClient

    config = load_config(getattr(args, "env_file", ".env"))
    return config, JiraClient(config)


def _cmd_doctor(args) -> int:
    """Validate configuration and the live site. Writes nothing."""
    from jira_testgen.doctor import doctor_failure, run_doctor

    # load_config raises UserError (exit 2) for a malformed setting, before any
    # client exists -- which is what keeps exit 2 and exit 3 apart (FR-033).
    config, client = _build_client(args)
    report = run_doctor(config, client, issue_key=args.issue)

    if args.json:
        _emit(jsonlib.dumps(report.to_dict(), indent=2))
    else:
        _emit(f"jira-testgen doctor ({config.base_url})")
        _emit(report.to_text())

    if report.credentials_rejected:
        # Exit 3, not 2: the settings are fine, Jira refused them (FR-033).
        raise AuthError(
            "Jira rejected the configured credentials. Check JIRA_EMAIL and "
            "JIRA_API_TOKEN, and that the token has not been revoked."
        )
    if not report.ok:
        # Raised rather than returned so the message and exit code come from the
        # same place as every other configuration failure.
        raise doctor_failure()
    return int(ExitCode.SUCCESS)


def _cmd_prepare(args) -> int:
    """Fetch a story and write its draft scaffold. Writes nothing to Jira."""
    from jira_testgen.prepare import prepare_draft

    config, client = _build_client(args)
    result = prepare_draft(
        client,
        args.issue_key,
        drafts_dir=args.drafts_dir,
        ac_field=config.ac_field,
        regenerate=args.regenerate,
    )

    if args.json:
        _emit(
            jsonlib.dumps(
                {
                    "issue": result.issue_key,
                    "draft_file": str(result.path),
                    "criteria_count": result.criteria_count,
                    "criteria_source": result.criteria_source,
                    "warnings": result.warnings,
                    "replaced": str(result.replaced) if result.replaced else None,
                    "backup": str(result.backup) if result.backup else None,
                    "previously_published": result.previously_published,
                    "next_ordinal": result.next_ordinal,
                    "defaults_used": config.defaults_used,
                },
                indent=2,
            )
        )
        return int(ExitCode.SUCCESS)

    if result.replaced:
        _emit(f"Replaced {result.replaced}")
        if result.backup:
            _emit(f"Previous version kept at {result.backup}")
    _emit(
        f"Wrote {result.path} with {result.criteria_count} acceptance criteria "
        f"(read from the {result.criteria_source})."
    )
    for warning in result.warnings:
        _emit(f"  ! {warning}")
    # FR-035: say which optional settings fell back, and to what.
    if config.defaults_used:
        _emit("  defaults applied:")
        for name, value in sorted(config.defaults_used.items()):
            _emit(f"    {name} -> {value}")
    if result.previously_published:
        _emit(f"  Already published for {result.issue_key}:")
        for item in result.previously_published:
            _emit(f"    {item['identity']} -> {item['issue_key']}")
    _emit()
    # T042: generation needs a session, and the tool says so rather than
    # quietly producing content some other way (FR-036).
    _emit(
        "Next: the Claude Code session writes the test cases into `test_cases:`.\n"
        f"Then run `jira-testgen validate {result.issue_key}`, review the file, and "
        "set `status: approved` in it to approve."
    )
    return int(ExitCode.SUCCESS)


def _cmd_validate(args) -> int:
    """Check a draft without contacting Jira."""
    from jira_testgen.draft.fingerprint import content_fingerprint
    from jira_testgen.draft.schema import draft_path, load_draft
    from jira_testgen.draft.validate import approval_state_description, validate_draft

    path = draft_path(args.drafts_dir, args.issue_key)
    draft = load_draft(path)
    report = validate_draft(draft, source=str(path))
    approval = approval_state_description(draft, content_fingerprint(draft))

    if args.json:
        _emit(
            jsonlib.dumps(
                {
                    "issue": draft.source_issue,
                    "draft_file": str(path),
                    "criteria_source": draft.criteria_source,
                    "test_case_count": len(draft.test_cases),
                    "coverage": report.coverage,
                    "uncovered": report.uncovered,
                    "missing_positive": report.missing_positive,
                    "errors": report.errors,
                    "warnings": report.warnings,
                    "approval": approval,
                    "ok": report.ok,
                },
                indent=2,
            )
        )
        return int(ExitCode.SUCCESS if report.ok else ExitCode.DRAFT_REFUSED)

    _emit(f"{path}")
    _emit(f"  criteria source : {draft.criteria_source}")
    _emit(f"  test cases      : {len(draft.test_cases)}")
    _emit(f"  approval        : {approval}")
    _emit("  coverage:")
    for label, identities in report.coverage.items():
        covered = ", ".join(identities) if identities else "(none)"
        _emit(f"    {label}: {covered}")
    for warning in report.warnings:
        _emit(f"  ! {warning}")
    if report.errors:
        _emit()
        _emit("Problems to fix before publishing:")
        for error in report.errors:
            _emit(f"  - {error}")
        return int(ExitCode.DRAFT_REFUSED)
    _emit()
    _emit(
        "Draft is structurally valid and fully covered. "
        f"To approve, set `status: approved` in {path}."
    )
    return int(ExitCode.SUCCESS)


def _cmd_publish(args) -> int:
    """Create or update test case issues in Jira. The only command that writes."""
    from jira_testgen.publish import publish_draft

    config, client = _build_client(args)
    report = publish_draft(
        client,
        args.issue_key,
        drafts_dir=args.drafts_dir,
        config=config,
        # Per-run only: there is deliberately no path to set either of these in
        # .env (FR-067).
        allow_large=args.allow_large,
        allow_stale_criteria=args.allow_stale_criteria,
    )

    _emit(report.to_json() if args.json else report.to_text())
    return report.exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
