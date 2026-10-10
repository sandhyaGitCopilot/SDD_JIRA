"""T089: performance targets (SC-001, SC-002).

What these can and cannot prove. SC-002 says drafting presents reviewable
drafts in under 2 minutes, and SC-001 gives the whole story-to-Jira round trip
10 minutes of engineer time. Most of both budgets is spent on things no test
here touches: Jira's own latency, and a human reading test cases.

So these assert the part that is ours -- that the tool's own work is a small
fraction of the budget, and that cost grows linearly with the number of test
cases rather than quadratically. A regression that made publishing O(n^2) in
requests would pass a wall-clock check against a fake and then fall over on a
real site, so request counts are asserted too.
"""

from __future__ import annotations

import time

from jira_testgen.prepare import prepare_draft
from jira_testgen.publish import publish_draft

from .conftest import StubJira
from .draft_factory import STORY_KEY, many_cases, write_approved
from .fake_jira import FakeJira

# Generous against a fake: the point is to catch an order-of-magnitude
# regression, not to benchmark the machine.
DRAFT_BUDGET_SECONDS = 5.0
PUBLISH_BUDGET_SECONDS = 20.0


def test_drafting_a_five_criterion_story_is_fast(make_client, drafts_dir):
    # SC-002's budget is 2 minutes, nearly all of it Jira latency and the
    # session writing test cases. The deterministic part should be trivial.
    stub = StubJira()
    started = time.perf_counter()
    result = prepare_draft(make_client(stub), STORY_KEY, drafts_dir=drafts_dir)
    elapsed = time.perf_counter() - started

    assert result.criteria_count == 5
    assert elapsed < DRAFT_BUDGET_SECONDS, f"drafting took {elapsed:.2f}s"


def test_drafting_makes_a_constant_number_of_requests(make_client, drafts_dir):
    # One story fetch. Nothing here should scale with the criteria count.
    stub = StubJira()
    prepare_draft(make_client(stub), STORY_KEY, drafts_dir=drafts_dir)
    gets = [c for c in stub.calls if c[0] == "GET"]
    assert len(gets) == 1, stub.calls


def test_publishing_twelve_test_cases_is_fast(make_client, drafts_dir):
    write_approved(drafts_dir, cases=many_cases(12))
    fake = FakeJira()
    started = time.perf_counter()
    report = publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    elapsed = time.perf_counter() - started

    assert report.verdict == "success"
    assert elapsed < PUBLISH_BUDGET_SECONDS, f"publishing took {elapsed:.2f}s"


def test_publishing_cost_is_linear_in_test_cases(make_client, drafts_dir, tmp_path):
    """Requests per test case must not grow with the size of the set.

    This is the regression that a wall-clock assertion against a fake would
    miss: against a real site, a per-test-case extra round trip is the
    difference between a minute and a quarter of an hour.
    """
    small_dir = tmp_path / "small"
    small_dir.mkdir()
    write_approved(small_dir, cases=many_cases(4))
    small = FakeJira()
    publish_draft(make_client(small), STORY_KEY, drafts_dir=small_dir)

    large_dir = tmp_path / "large"
    large_dir.mkdir()
    write_approved(large_dir, cases=many_cases(40))
    large = FakeJira()
    publish_draft(make_client(large), STORY_KEY, drafts_dir=large_dir)

    per_case_small = len(small.calls) / 4
    per_case_large = len(large.calls) / 40
    # Ten times the work must not cost more per test case than a small set did.
    assert per_case_large <= per_case_small + 0.5, (
        f"{per_case_small:.1f} requests/case at 4, "
        f"{per_case_large:.1f} at 40 -- cost is not linear"
    )


def test_a_republish_does_not_cost_more_than_the_first_publish(make_client, drafts_dir):
    # Re-running is the common case, so it must not be the expensive one.
    write_approved(drafts_dir, cases=many_cases(12))
    fake = FakeJira()
    publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    first_calls = len(fake.calls)

    publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    second_calls = len(fake.calls) - first_calls

    assert second_calls <= first_calls, (
        f"first publish made {first_calls} requests, re-publish made {second_calls}"
    )


def test_discovery_batches_the_identity_lookup(make_client, drafts_dir):
    """A first publish must not spend one search per test case (FR-053).

    The identity lookup exists to find issues created but never linked. Done
    naively that is a request per test case on every single run, including the
    first, when nothing exists yet.
    """
    write_approved(drafts_dir, cases=many_cases(40))
    fake = FakeJira()
    publish_draft(make_client(fake), STORY_KEY, drafts_dir=drafts_dir)
    searches = [c for c in fake.calls if "search/jql" in c[1]]
    # 40 test cases, batched 50 per query -> one search, not forty.
    assert len(searches) <= 2, f"{len(searches)} searches for 40 test cases"
