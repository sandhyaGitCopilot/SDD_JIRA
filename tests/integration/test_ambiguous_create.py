"""T076: a create that timed out but landed is adopted, not duplicated.

FR-053 and SC-020. Jira's create endpoint offers no idempotency key, so this is
the one place a retry could breach the no-duplicates guarantee: the request may
have been applied even though the client never saw the response.
"""

from jira_testgen.publish import publish_draft

from .draft_factory import STORY_KEY, many_cases, write_approved
from .fake_jira import FakeJira


def _timeout_on_second_create(make_client, drafts_dir):
    write_approved(drafts_dir, cases=many_cases(4))
    # The 2nd create is applied by Jira, then the connection times out.
    fake = FakeJira(timeout_create_on={2})
    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    return fake, report


def test_the_issue_that_landed_is_adopted_rather_than_recreated(make_client, drafts_dir):
    fake, report = _timeout_on_second_create(make_client, drafts_dir)
    adopted = [o for o in report.outcomes if o.decision == "adopted"]
    assert len(adopted) == 1
    assert adopted[0].issue_key in fake.created


def test_no_duplicate_issue_is_created_for_it(make_client, drafts_dir):
    fake, report = _timeout_on_second_create(make_client, drafts_dir)
    # One issue per test case, even though one create's outcome was unknown.
    identities = [p["identity"] for p in fake.properties.values()]
    assert len(identities) == len(set(identities))
    assert len(fake.created) == 4


def test_the_adopted_issue_gets_its_marker_and_link(make_client, drafts_dir):
    fake, report = _timeout_on_second_create(make_client, drafts_dir)
    adopted = next(o for o in report.outcomes if o.decision == "adopted")
    marker = fake.properties[adopted.issue_key]
    assert marker["identity"] == adopted.identity
    # The fingerprint written before the timeout is refreshed on adoption, so a
    # later run does not see a phantom conflict.
    assert marker["content_fingerprint"] != "written-before-the-timeout"
    assert (adopted.issue_key, STORY_KEY) in fake.links


def test_the_run_continues_past_the_ambiguous_create(make_client, drafts_dir):
    _fake, report = _timeout_on_second_create(make_client, drafts_dir)
    assert len(report.outcomes) == 4
    assert not report.not_attempted


def test_the_adoption_is_reported_rather_than_passed_off_as_a_create(make_client, drafts_dir):
    _fake, report = _timeout_on_second_create(make_client, drafts_dir)
    adopted = next(o for o in report.outcomes if o.decision == "adopted")
    assert adopted.reason
    assert "timed out" in adopted.reason.lower() or "unknown" in adopted.reason.lower()


def test_a_rerun_afterwards_sees_everything_as_unchanged(make_client, drafts_dir):
    fake, _report = _timeout_on_second_create(make_client, drafts_dir)
    fake.timeout_create_on = None
    second = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    assert all(o.decision == "unchanged" for o in second.outcomes)
    assert len(fake.created) == 4


def test_a_timeout_where_nothing_landed_is_reported_as_failed(make_client, drafts_dir):
    # The lookup finds nothing, so there is nothing to adopt. Reporting it as
    # created would be a lie; a re-run creates it properly.
    write_approved(drafts_dir, cases=many_cases(4))

    class LosesTheRequest(FakeJira):
        """Drops the 2nd create entirely: the request never reaches Jira.

        Counted separately from the base class's own counter, which super()
        also increments -- sharing it would mean the condition never fires.
        """

        attempts = 0

        def request(self, method, url, params=None, json=None, timeout=None):
            if method == "POST" and url.endswith("/issue"):
                self.attempts += 1
                if self.attempts == 2:
                    from .fake_jira import ReadTimeout

                    raise ReadTimeout("read timed out; nothing was applied")
            return super().request(method, url, params=params, json=json, timeout=timeout)

    fake = LosesTheRequest()
    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    failed = [o for o in report.outcomes if o.decision == "failed"]
    assert len(failed) == 1
    assert report.verdict == "partial"
