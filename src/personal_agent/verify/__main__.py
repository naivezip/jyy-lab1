"""Run `pa-verify` with `python -m personal_agent.verify`."""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
