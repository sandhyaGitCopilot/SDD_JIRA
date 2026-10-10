"""Logging, with central secret redaction.

FR-034 is absolute: the API token must appear in no output, report, draft file,
or log, including when reporting errors. Anything that relies on the author of a
future log line remembering to redact will fail the first time someone adds one,
so redaction happens here -- in the formatter every record passes through -- and
not at call sites.

Register a secret once (``register_secret``), and it is scrubbed from every
record's message, its interpolation arguments, and any attached exception text.
``scrub`` is exported so report rendering and error printing can route through
the same function.
"""

from __future__ import annotations

import logging
import sys

REDACTED = "***REDACTED***"

# Module-level, because a secret must be unforgettable once seen. Short strings
# are ignored: scrubbing a 3-character token would mangle unrelated output.
_MIN_SECRET_LENGTH = 6
_secrets: set[str] = set()

_LOGGER_NAME = "jira_testgen"


def register_secret(value: str | None) -> None:
    """Mark a value for removal from every stream this tool writes."""
    if value and len(value) >= _MIN_SECRET_LENGTH:
        _secrets.add(value)


def clear_secrets() -> None:
    """Forget all registered secrets. For tests only."""
    _secrets.clear()


def scrub(text: str) -> str:
    """Replace every registered secret in ``text``.

    Longest first, so a secret that contains another is not partially replaced
    and left recoverable.
    """
    if not _secrets:
        return text
    for secret in sorted(_secrets, key=len, reverse=True):
        if secret in text:
            text = text.replace(secret, REDACTED)
    return text


class RedactingFormatter(logging.Formatter):
    """A formatter that cannot emit a registered secret.

    Scrubbing the fully formatted record catches the message, the arguments, and
    the traceback in one pass -- which is the point: there is no path around it.
    """

    def format(self, record: logging.LogRecord) -> str:
        return scrub(super().format(record))


def get_logger() -> logging.Logger:
    """The tool's single logger."""
    return logging.getLogger(_LOGGER_NAME)


def configure_logging(
    *,
    verbose: bool = False,
    debug: bool = False,
    log_file: str | None = None,
) -> logging.Logger:
    """Install the redacting formatter on stderr, and optionally on a file.

    Logs go to stderr so that stdout carries only the report and stays pipeable
    (``--json``). Default level is WARNING; ``--verbose`` gives INFO and
    ``--debug`` gives request metadata -- method, path, status, attempt, wait --
    never bodies or headers, since ``Authorization`` lives in the headers.
    """
    level = logging.DEBUG if debug else (logging.INFO if verbose else logging.WARNING)
    logger = get_logger()
    logger.setLevel(level)
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    formatter = RedactingFormatter("%(levelname)s %(message)s")
    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(formatter)
    logger.addHandler(stream)

    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        # Same formatter class: a secret must not reach a file a user might
        # later paste into a bug report.
        file_handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(file_handler)

    return logger
