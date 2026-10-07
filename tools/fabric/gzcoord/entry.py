"""tools/fabric/gzcoord/entry.py — what bin/gzcoord-inbox, bin/gzcoord-send
and bin/gzmsg run (agent-fabric ADR-040 §7). Each is a few lines under the
system `python3`, which is only the way in: `launch` hands over to the
fleet's pinned interpreter by exec, with the entry script's own path as the
script, so the process table still reads `… gzcoord-inbox --follow` — the
session-start hook and the harness find the watch by that name. Run
there, `launch` runs tools/fabric/gzcoord/run.py's `main` in this process.

This file runs under whatever `python3` the host has before the pin is
reached, so it keeps to syntax every supported `python3` reads.

The last-resort contract holds when the pinned interpreter cannot start or
this module cannot load: one line on stderr, never a stack trace, and the
tool's own status — the inbox exits 0 (it must never block a session
start), send and gzmsg exit 1."""
from __future__ import annotations

import importlib.util
import os
import sys

PINNED = "/usr/local/bin/fabric-python"
RUNNER = os.path.join(os.path.dirname(os.path.realpath(__file__)), "run.py")
# The line each tool printed as a Node shim, kept so a caller matching on
# it keeps matching.
LAST_RESORT = {"inbox": ("gzcoord inbox", 0), "send": ("send", 1), "gzmsg": ("gzmsg", 1)}


def _same_file(a: str, b: str) -> bool:
    return os.path.realpath(a) == os.path.realpath(b)


def launch(tool: str, script: str) -> None:
    """Never returns: execs the pinned interpreter on `script` (the entry
    as it was named, link or not), or runs the tool and exits with its status."""
    label, status = LAST_RESORT[tool]
    try:
        py = os.environ.get("AGENT_FABRIC_PYTHON") or PINNED
        if not _same_file(sys.executable, py):
            if not os.access(py, os.X_OK):
                raise OSError("the fleet's pinned Python is not installed at %s" % py)
            os.execv(py, [py, "-I", script] + sys.argv[1:])
        # No Node parent to watch: a GZCOORD_SHIM_PID inherited from an
        # old-style shim up the tree names a process that is not ours, and
        # run.py would end this one at once as an orphaned start.
        os.environ.pop("GZCOORD_SHIM_PID", None)
        spec = importlib.util.spec_from_file_location("gzcoord_run", RUNNER)
        run = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(run)
        code = run.main([tool] + sys.argv[1:])
    except SystemExit:
        raise
    except BaseException as e:  # a last resort is for anything at all
        print("%s: %s" % (label, e), file=sys.stderr)
        code = status
    sys.exit(code)
