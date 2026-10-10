"""Allow `python -m jira_testgen` as an alternative to the console script."""

import sys

from jira_testgen.cli import main

if __name__ == "__main__":
    sys.exit(main())
