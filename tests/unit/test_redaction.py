"""T010: secret redaction (FR-034).

The requirement is absolute, so these tests assert zero occurrences rather than
"mostly redacted". The traceback case matters most: an exception is the path a
token is most likely to escape by, because nobody writes the formatting.
"""

import logging

import pytest

from jira_testgen.logging_setup import (
    REDACTED,
    RedactingFormatter,
    clear_secrets,
    configure_logging,
    get_logger,
    register_secret,
    scrub,
)

TOKEN = "ATATT3xFfGF0-super-secret-token-value"


@pytest.fixture(autouse=True)
def _clean_secrets():
    clear_secrets()
    yield
    clear_secrets()


def _format(record_factory):
    formatter = RedactingFormatter("%(levelname)s %(message)s")
    return formatter.format(record_factory())


def test_scrub_removes_a_registered_secret():
    register_secret(TOKEN)
    assert TOKEN not in scrub(f"auth failed for {TOKEN}")
    assert REDACTED in scrub(f"auth failed for {TOKEN}")


def test_scrub_is_a_noop_without_registered_secrets():
    assert scrub("nothing to hide") == "nothing to hide"


def test_very_short_values_are_not_registered():
    # Scrubbing a 3-character value would mangle unrelated output.
    register_secret("abc")
    assert scrub("abcdef") == "abcdef"


def test_token_is_scrubbed_from_a_log_message():
    register_secret(TOKEN)
    out = _format(
        lambda: logging.LogRecord("t", logging.ERROR, __file__, 1, f"using {TOKEN}", None, None)
    )
    assert TOKEN not in out


def test_token_is_scrubbed_from_interpolation_arguments():
    register_secret(TOKEN)
    out = _format(
        lambda: logging.LogRecord("t", logging.ERROR, __file__, 1, "using %s", (TOKEN,), None)
    )
    assert TOKEN not in out


def test_token_is_scrubbed_from_an_attached_traceback():
    register_secret(TOKEN)
    try:
        raise RuntimeError(f"request failed with token {TOKEN}")
    except RuntimeError:
        import sys

        exc_info = sys.exc_info()
    out = _format(
        lambda: logging.LogRecord("t", logging.ERROR, __file__, 1, "boom", None, exc_info)
    )
    assert TOKEN not in out
    assert REDACTED in out


def test_longest_secret_is_replaced_first():
    # A secret containing another must not be partially replaced and left
    # recoverable.
    register_secret("secret-value")
    register_secret("secret-value-extended")
    assert "secret-value" not in scrub("secret-value-extended")


def test_configured_logger_writes_redacted_output_to_a_file(tmp_path):
    register_secret(TOKEN)
    log_file = tmp_path / "run.log"
    configure_logging(debug=True, log_file=str(log_file))
    get_logger().error("failing with %s", TOKEN)
    for handler in get_logger().handlers:
        handler.flush()
    contents = log_file.read_text(encoding="utf-8")
    assert TOKEN not in contents
    assert REDACTED in contents


def test_log_file_contains_zero_bytes_of_the_token(tmp_path):
    register_secret(TOKEN)
    log_file = tmp_path / "run.log"
    configure_logging(debug=True, log_file=str(log_file))
    logger = get_logger()
    logger.debug("debug %s", TOKEN)
    logger.warning("warn %s", TOKEN)
    logger.error("error %s", TOKEN)
    for handler in logger.handlers:
        handler.flush()
    assert TOKEN.encode() not in log_file.read_bytes()
