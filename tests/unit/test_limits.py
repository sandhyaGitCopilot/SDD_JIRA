"""T026: set-size thresholds (FR-064, FR-065, FR-066).

The thresholds are fixed constants on purpose: making them settings would add
two more values a first-time user has to understand, against SC-009.
"""

from jira_testgen import limits


def test_thresholds_are_the_documented_values():
    assert limits.WARN_ABOVE == 25
    assert limits.REFUSE_ABOVE == 100


def test_no_configuration_path_exists_for_the_thresholds():
    # FR-066: not settings. If someone later adds JIRA_MAX_TEST_CASES, this
    # fails and the conversation happens before the setting ships.
    from pathlib import Path

    from jira_testgen import config

    text = Path(config.__file__).read_text(encoding="utf-8")
    assert "WARN_ABOVE" not in text
    assert "REFUSE_ABOVE" not in text


def test_no_warning_at_or_below_the_threshold():
    assert limits.size_warning(25) is None
    assert limits.size_warning(1) is None
    assert limits.size_warning(0) is None


def test_warning_above_the_threshold_names_the_count():
    message = limits.size_warning(28)
    assert message is not None
    assert "28" in message


def test_exceeds_ceiling_is_exclusive():
    assert limits.exceeds_ceiling(100) is False
    assert limits.exceeds_ceiling(101) is True


def test_ceiling_message_names_both_count_and_limit():
    message = limits.ceiling_message(120)
    assert "120" in message
    assert "100" in message
    # Must point at the way forward, not just refuse.
    assert "--allow-large" in message
