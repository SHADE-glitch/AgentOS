"""Allow ``python -m aos.cli`` to run the CLI."""

import sys

from aos.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
