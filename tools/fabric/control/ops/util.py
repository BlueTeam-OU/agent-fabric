"""control.ops.util is control/opsutil.py, the same module object: it moved out of the package so that importing it does not run
control/ops/__init__ (every op's code). Code and tests that name control.ops.util, or patch it, reach the one module."""
import sys

from control import opsutil

sys.modules[__name__] = opsutil
