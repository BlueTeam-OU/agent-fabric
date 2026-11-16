"""The path bin/fabric-ctl runs: a few lines that import control.ctl, so Python caches its bytecode.
A script run as __main__ is compiled on every start (ctl.py is ~3,000 lines); ctl.py itself still
runs as a script for the tests that name its path."""
import os
import sys

# Run as a script, sys.path[0] is control/, whose secrets.py and tools.py would shadow the standard
# library's and the fabric's own (ctl.py says the same).
sys.path[0] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

from control import ctl  # noqa: E402

sys.exit(ctl.cli())
