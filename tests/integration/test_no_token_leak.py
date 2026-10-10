"""T063: the API token appears nowhere (FR-034, SC-008, quickstart scenario L).

FR-034 is absolute, so these assert **zero occurrences** across stdout, stderr
and any log file, for every subcommand driven to failure. Error and traceback
paths get particular attention: those are the places a secret escapes, because
nobody writes the formatting.

The sweep is re-run as T091 once every feature is in, since each new log line is
a fresh opportunity to leak.
"""

from __future__ import annotations

import pytest

from jira_testgen import cli
from jira_testgen.jira import client as client_mod

TOKEN = "ATATT3xFfGF0-very-secret-token-value-9876"

SUBCOMMANDS = [
    ["doctor"],
    ["doctor", "--issue", "PROJ-123"],
    ["prepare", "PROJ-123"],
    ["prepare", "PROJ-123", "--regenerate"],
    ["validate", "PROJ-123"],
    ["publish", "PROJ-123"],
    ["publish", "PROJ-123", "--allow-large"],
    ["publish", "PROJ-123", "--allow-stale-criteria"],
]

# `doctor` has no use for a drafts directory, so it does not accept the flag.
TAKES_DRAFTS_DIR = {"prepare", "validate", "publish"}

# `validate` works entirely offline and never loads configuration, which is
# deliberate: a draft can be checked without credentials. So a malformed .env
# does not produce a configuration error there.
LOADS_CONFIG = {"doctor", "prepare", "publish"}

VERBOSITY = [[], ["--verbose"], ["--debug"]]


class FailingResponse:
    """Everything fails, and the body echoes the token back at us.

    A hostile-but-plausible server: if the tool ever reflects a response body
    into its output unredacted, this catches it.
    """

    status_code = 401
    headers: dict = {}

    def __init__(self):
        self.text = f"auth failed for token {TOKEN}"

    def json(self):
        return {"errorMessages": [f"Client must be authenticated. token={TOKEN}"]}


class FailingSession:
    def request(self, *_args, **_kwargs):
        return FailingResponse()


class ExplodingSession:
    """Raises, so the traceback path is exercised too."""

    def request(self, *_args, **_kwargs):
        raise RuntimeError(f"connection died while sending token {TOKEN}")


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    import os

    for name in list(os.environ):
        if name.startswith("JIRA_"):
            monkeypatch.delenv(name, raising=False)
    from jira_testgen.logging_setup import clear_secrets

    clear_secrets()
    yield
    clear_secrets()


def _env_file(tmp_path, *, valid=True):
    path = tmp_path / ".env"
    body = (
        f"JIRA_BASE_URL=https://example.atlassian.net\n"
        f"JIRA_EMAIL=qa@example.com\n"
        f"JIRA_API_TOKEN={TOKEN}\n"
    )
    if not valid:
        # A malformed setting, with the token still present: this is the path
        # where load_config raises before anything else runs.
        body = body.replace("https://example.atlassian.net", "ftp://nope")
    path.write_text(body, encoding="utf-8")
    return path


def _run(monkeypatch, tmp_path, argv, *, session, env_valid=True, log=True):
    monkeypatch.setattr(
        client_mod.JiraClient, "_build_session", lambda self: session, raising=True
    )
    log_file = tmp_path / "run.log"
    full = [*argv, "--env-file", str(_env_file(tmp_path, valid=env_valid))]
    if argv[0] in TAKES_DRAFTS_DIR:
        full += ["--drafts-dir", str(tmp_path / "drafts")]
    if log:
        full += ["--log-file", str(log_file)]
    code = cli.main(full)
    return code, (log_file.read_bytes() if log_file.exists() else b"")


@pytest.mark.parametrize("argv", SUBCOMMANDS)
@pytest.mark.parametrize("verbosity", VERBOSITY)
def test_no_leak_when_every_request_fails(monkeypatch, tmp_path, capsys, argv, verbosity):
    code, log_bytes = _run(
        monkeypatch, tmp_path, [*argv, *verbosity], session=FailingSession()
    )
    captured = capsys.readouterr()
    assert code != 0
    assert TOKEN not in captured.out
    assert TOKEN not in captured.err
    assert TOKEN.encode() not in log_bytes


@pytest.mark.parametrize("argv", SUBCOMMANDS)
def test_no_leak_when_the_transport_raises(monkeypatch, tmp_path, capsys, argv):
    code, log_bytes = _run(
        monkeypatch, tmp_path, [*argv, "--debug"], session=ExplodingSession()
    )
    captured = capsys.readouterr()
    assert code != 0
    assert TOKEN not in captured.out
    assert TOKEN not in captured.err
    assert TOKEN.encode() not in log_bytes


@pytest.mark.parametrize("argv", SUBCOMMANDS)
def test_no_leak_when_configuration_is_malformed(monkeypatch, tmp_path, capsys, argv):
    # The token is present but never registered as a secret on this path,
    # because load_config raises first. Nothing may print it anyway.
    code, log_bytes = _run(
        monkeypatch,
        tmp_path,
        [*argv, "--debug"],
        session=FailingSession(),
        env_valid=False,
    )
    captured = capsys.readouterr()
    if argv[0] in LOADS_CONFIG:
        assert code == 2, f"{argv} should report a configuration error"
    else:
        assert code != 0
    assert TOKEN not in captured.out
    assert TOKEN not in captured.err
    assert TOKEN.encode() not in log_bytes


def test_no_leak_in_the_json_report_path(monkeypatch, tmp_path, capsys):
    code, log_bytes = _run(
        monkeypatch,
        tmp_path,
        ["doctor", "--json", "--debug"],
        session=FailingSession(),
    )
    captured = capsys.readouterr()
    assert code != 0
    assert TOKEN not in captured.out + captured.err
    assert TOKEN.encode() not in log_bytes


# ---------------------------------------------------------------------------
# T091: the sweep re-run once every feature is in.
#
# T063 covered failing runs. Everything below covers the paths added since:
# successful report rendering, the update / conflict / orphan decisions, and
# every --json output. Each new report field and log line is a fresh chance to
# leak, which is why this is re-run rather than trusted.
# ---------------------------------------------------------------------------


def _working_env(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "JIRA_BASE_URL=https://example.atlassian.net\n"
        "JIRA_EMAIL=qa@example.com\n"
        f"JIRA_API_TOKEN={TOKEN}\n"
        "JIRA_PROJECT_KEY=PROJ\n",
        encoding="utf-8",
    )
    return path


def _run_against(monkeypatch, tmp_path, fake, argv):
    monkeypatch.setattr(
        client_mod.JiraClient, "_build_session", lambda self: fake, raising=True
    )
    log_file = tmp_path / "success.log"
    full = [
        *argv,
        "--debug",
        "--env-file",
        str(_working_env(tmp_path)),
        "--log-file",
        str(log_file),
    ]
    if argv[0] in TAKES_DRAFTS_DIR:
        full += ["--drafts-dir", str(tmp_path / "drafts")]
    code = cli.main(full)
    return code, (log_file.read_bytes() if log_file.exists() else b"")


def _assert_clean(capsys, log_bytes):
    captured = capsys.readouterr()
    assert TOKEN not in captured.out
    assert TOKEN not in captured.err
    assert TOKEN.encode() not in log_bytes


@pytest.mark.parametrize("json_flag", [[], ["--json"]])
def test_no_leak_in_a_successful_publish_report(monkeypatch, tmp_path, capsys, json_flag):
    from .draft_factory import many_cases, write_approved
    from .fake_jira import FakeJira

    drafts = tmp_path / "drafts"
    drafts.mkdir()
    write_approved(drafts, cases=many_cases(6))
    code, log_bytes = _run_against(
        monkeypatch, tmp_path, FakeJira(), ["publish", "PROJ-123", *json_flag]
    )
    assert code == 0
    _assert_clean(capsys, log_bytes)


def test_no_leak_when_the_report_carries_updates_and_conflicts(monkeypatch, tmp_path, capsys):
    # The decision types added in the last phase, all in one report.
    from jira_testgen.draft.schema import ApprovalState, load_draft

    from .draft_factory import many_cases, write_approved, write_draft
    from .fake_jira import FakeJira

    drafts = tmp_path / "drafts"
    drafts.mkdir()
    write_approved(drafts, cases=many_cases(6))
    fake = FakeJira()
    _run_against(monkeypatch, tmp_path, fake, ["publish", "PROJ-123"])
    capsys.readouterr()

    # One edited in Jira (conflict), one edited in the draft (update), one
    # dropped from the draft (orphan).
    fake.edit_in_jira(fake.created[0], description_text="Hand-edited in Jira.")
    draft = load_draft(drafts / "PROJ-123.yaml")
    draft.test_cases[1].steps.append("A step added in the draft.")
    draft.test_cases = [c for c in draft.test_cases if not c.identity.endswith("-005")]
    draft.approval = ApprovalState(status="approved", approved_fingerprint=None)
    write_draft(drafts, draft)

    code, log_bytes = _run_against(
        monkeypatch, tmp_path, fake, ["publish", "PROJ-123", "--json"]
    )
    captured = capsys.readouterr()
    assert code == 10
    # The report really does contain the new decisions, so this is a live test
    # of those code paths rather than a vacuous pass.
    assert "conflict" in captured.out
    assert "orphaned_draft" in captured.out
    assert TOKEN not in captured.out
    assert TOKEN not in captured.err
    assert TOKEN.encode() not in log_bytes


def test_no_leak_in_a_successful_doctor_report(monkeypatch, tmp_path, capsys):
    from .fake_jira import FakeJira, Resp

    class Healthy(FakeJira):
        def request(self, method, url, params=None, json=None, timeout=None):
            if url.endswith("/myself"):
                return Resp(200, {"emailAddress": "qa@example.com"})
            if "/mypermissions" in url:
                return Resp(
                    200,
                    {
                        "permissions": {
                            p: {"havePermission": True}
                            for p in ("CREATE_ISSUES", "EDIT_ISSUES", "LINK_ISSUES")
                        }
                    },
                )
            return super().request(method, url, params=params, json=json, timeout=timeout)

    code, log_bytes = _run_against(monkeypatch, tmp_path, Healthy(), ["doctor", "--json"])
    assert code == 0
    _assert_clean(capsys, log_bytes)


def test_no_leak_in_prepare_and_validate_json_output(monkeypatch, tmp_path, capsys):
    from .conftest import StubJira

    code, log_bytes = _run_against(
        monkeypatch, tmp_path, StubJira(), ["prepare", "PROJ-123", "--json"]
    )
    assert code == 0
    _assert_clean(capsys, log_bytes)

    code, log_bytes = _run_against(
        monkeypatch, tmp_path, StubJira(), ["validate", "PROJ-123", "--json"]
    )
    _assert_clean(capsys, log_bytes)


def test_no_leak_when_a_draft_is_written_to_disk(monkeypatch, tmp_path, capsys):
    # FR-034 covers draft files too, not just streams.
    from .conftest import StubJira

    _run_against(monkeypatch, tmp_path, StubJira(), ["prepare", "PROJ-123"])
    capsys.readouterr()
    for path in (tmp_path / "drafts").rglob("*"):
        if path.is_file():
            assert TOKEN not in path.read_text(encoding="utf-8")


def test_the_token_is_registered_as_a_secret_once_config_loads(tmp_path):
    from jira_testgen.config import load_config
    from jira_testgen.logging_setup import scrub

    load_config(_env_file(tmp_path))
    assert TOKEN not in scrub(f"leaking {TOKEN} here")


def test_a_malformed_config_still_registers_the_token_before_validating(tmp_path):
    # Defence in depth: the token is registered as soon as it is read, so that
    # any later message -- including ones added in future -- is scrubbed even on
    # the paths that fail before Jira is contacted.
    from jira_testgen.config import load_config
    from jira_testgen.errors import UserError
    from jira_testgen.logging_setup import scrub

    with pytest.raises(UserError):
        load_config(_env_file(tmp_path, valid=False))
    assert TOKEN not in scrub(f"leaking {TOKEN} here")
