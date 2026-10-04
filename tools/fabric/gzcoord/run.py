"""tools/fabric/gzcoord/run.py <gzmsg|send|inbox> [argv…] — the entry the
shims at communication/gzcoord/scripts/*.mjs run under the pinned Python
(`fabric-python -I`, which puts no script directory on sys.path: this file
puts tools/fabric there itself). Each tool's own contract is its module's
header; this file only routes, and ties the child's life to its shim.

The shim stays alive for as long as the tool runs — the harness and the
session-start hook find the watch by `inbox.mjs --follow` in the process
table — so the tool must not outlive it: a shim killed outright (SIGKILL,
which it cannot forward) would leave a watch running that nothing sees and
a second one started beside it. On Linux the kernel ends this process when
the shim's ends (PR_SET_PDEATHSIG); a shim that is already gone when this
starts is an orphaned start, and nothing runs."""
from __future__ import annotations

import ctypes
import os
import signal
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

PR_SET_PDEATHSIG = 1


def tie_to_shim() -> bool:
    """False when the shim that started this is already gone."""
    shim = os.environ.get("GZCOORD_SHIM_PID")
    if not shim or not shim.isdigit():
        return True
    try:
        ctypes.CDLL(None, use_errno=True).prctl(PR_SET_PDEATHSIG, signal.SIGTERM, 0, 0, 0)
    except (OSError, AttributeError):
        pass   # not Linux: the shim's own signal forwarding is what remains
    return os.getppid() == int(shim)


def main(argv: list[str]) -> int:
    tool, rest = (argv[0] if argv else ""), argv[1:]
    if tool not in ("gzmsg", "send", "inbox"):
        print("usage: run.py gzmsg|send|inbox [argv…]", file=sys.stderr)
        return 2
    if not tie_to_shim():
        return 0 if tool == "inbox" else 1
    if tool == "gzmsg":
        from gzcoord import gzmsg
        return gzmsg.run(rest)
    if tool == "send":
        from gzcoord import send
        return send.run(rest)
    from gzcoord import inbox
    return inbox.run(rest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
