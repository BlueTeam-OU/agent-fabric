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

import codecs
import ctypes
import os
import signal
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

PR_SET_PDEATHSIG = 1

# What the Node wrote for a code unit UTF-8 cannot hold (a lone surrogate):
# U+FFFD, one per unit. errors="replace" would write "?". Bytes, not a str:
# the UTF-8 encoder takes only ASCII back from a handler as text.
codecs.register_error("gzcoord-fffd", lambda e: ("\ufffd".encode("utf-8") * (e.end - e.start), e.end))


def tie_to_shim() -> bool:
    """False when the shim that started this is already gone. Run with no
    shim (a test, a direct call) there is nothing to tie. A shim named but
    not tied to — a pid that is no pid, no prctl — is said in one line: the
    process then outlives a shim killed outright, and nothing else says it."""
    shim = os.environ.get("GZCOORD_SHIM_PID")
    if shim is None:
        return True
    if not (shim.isascii() and shim.isdigit()):
        print(f"gzcoord: not tied to the shim (GZCOORD_SHIM_PID is no pid: {shim[:40]!r})", file=sys.stderr)
        return True
    try:
        if ctypes.CDLL(None, use_errno=True).prctl(PR_SET_PDEATHSIG, signal.SIGTERM, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "prctl failed")
    except (OSError, AttributeError) as e:
        # not Linux: the shim's own signal forwarding is what remains
        print(f"gzcoord: not tied to the shim ({e}): a shim killed outright leaves this running", file=sys.stderr)
    return os.getppid() == int(shim)


def main(argv: list[str]) -> int:
    # UTF-8 whatever the locale, and a character UTF-8 cannot hold (a lone
    # surrogate from a relay record) replaced, never raised: the Node wrote
    # UTF-8 always, and an encoding error after the ack ended --follow.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="gzcoord-fffd")
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
