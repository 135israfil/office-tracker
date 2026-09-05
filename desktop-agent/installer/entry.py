"""Frozen-build entry point.

PyInstaller needs a script, not a `-m` target, and `agent/__main__.py` is not usable as
one: relative imports fail when a file is executed directly rather than as part of the
package. This is that script and nothing more — no logic lives here, so the frozen build
and `python -m agent` cannot behave differently.
"""

import multiprocessing
import sys

from agent.main import main

if __name__ == "__main__":
    # Without this a frozen Windows build re-runs the whole program in every child
    # process any dependency happens to spawn, which looks like the agent starting
    # itself in a loop.
    multiprocessing.freeze_support()
    sys.exit(main())
