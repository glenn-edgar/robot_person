"""`python -m ct_runner` shim. Delegates to ct_runner.runner.main and
exits with its return code.
"""

from __future__ import annotations

import sys

from .runner import main


if __name__ == "__main__":
    sys.exit(main())
