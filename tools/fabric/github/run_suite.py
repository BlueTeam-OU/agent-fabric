#!/usr/bin/env python3
"""tools/fabric/github/run_suite.py <suite.sh> [args...]

Run a bash test suite so that a call to a command that does not exist
FAILS it.

Why: bash answers an undefined command with "command not found" on
stderr and status 127, and carries on. A suite whose assertion helper is
misspelt (assert_lacks where the file defines assert_not_contains) never
touches its own failure counter, and reports "all assertions passed"
with that case vacuous. It has happened in more than one project's
suites, unnoticed for weeks.

How: the suite runs as `bash <suite> <args…>` with an exported bash
function, command_not_found_handle, in its environment, so it reaches the
suite's shell and every shell the suite spawns. Bash runs that handler
in a forked child, so it cannot abort the suite, and a counter it bumps
dies with the fork: it records the name in a marker file instead, and
this decides afterwards.

Exit codes:
  the suite's own, when it called nothing undefined
  1  it called a command that does not exist (named on stderr)
  2  usage: no suite, or one that cannot be read
"""
# The docstring is --help's reason for existing; this tool has no options.
# Ported from two managed projects' tools/checks/run_suite.sh, identical
# but for the marker's variable (ADR-040; their test, run unchanged
# against the shim, the oracle).
#
# THE CONTRACT, frozen from devex-tooling's port contract 7/8:
#   argv    <suite.sh> [args...]; none: "run_suite: usage: run_suite.sh
#           <suite.sh> [args...]", exit 2; unreadable: "run_suite: cannot
#           read <suite>", exit 2.
#   env     the suite inherits ours, plus AGENT_FABRIC_UNDEF_MARKER (a
#           temporary file, removed however this ends) and the exported
#           handler, BASH_FUNC_command_not_found_handle%%.
#   stdout  the suite's, untouched.
#   stderr  the suite's; each undefined call "run_suite: undefined command:
#           <name>" as it happens; after it, if any: "run_suite: FAIL —
#           <suite> called command(s) that do not exist:", the names sorted
#           and unique, each "    <name>", then the two-line reason.
#   exit    1 on any undefined call, else the suite's; 2 usage. INT, TERM
#           or HUP: the marker removed, then this dies of the signal, as
#           the bash did after its EXIT trap; the suite is left to the
#           signal its process group got.
from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile

PROG = "run_suite"
MARKER_VAR = "AGENT_FABRIC_UNDEF_MARKER"
HANDLER_VAR = "BASH_FUNC_command_not_found_handle%%"
# Bash runs it in a fork made for the missing command, so nothing it does
# reaches the suite's shell: it records to the file, and gives the status
# bash would have, 127. (Return and exit are the same there; a mutation
# swapping them is equivalent, and no test can tell them apart.)
HANDLER = ('() { printf \'%s\\n\' "$1" >> "$' + MARKER_VAR + '";'
           ' printf \'run_suite: undefined command: %s\\n\' "$1" >&2; return 127; }')
SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


class Signalled(BaseException):
    def __init__(self, signum: int):
        super().__init__(signum)
        self.signum = signum


def run(argv: list[str]) -> int:
    if not argv:
        print(f"{PROG}: usage: run_suite.sh <suite.sh> [args...]", file=sys.stderr)
        return 2
    suite, args = argv[0], argv[1:]
    if not os.access(suite, os.R_OK):
        print(f"{PROG}: cannot read {suite}", file=sys.stderr)
        return 2

    fd, marker = tempfile.mkstemp()
    os.close(fd)
    try:
        env = {**os.environ, MARKER_VAR: marker, HANDLER_VAR: HANDLER}
        try:
            # No bound: a suite takes as long as it takes, and the caller
            # (CI, a person) owns the clock. Popen and a bare wait, not
            # subprocess.run, which kills its child on any exception: a
            # signal to this process alone must not kill the suite, as it
            # did not under the bash.
            rc = subprocess.Popen(["bash", suite, *args], env=env).wait()
        except FileNotFoundError:
            print(f"{PROG}: bash is not on PATH", file=sys.stderr)
            return 2
        with open(marker, "rb") as fh:
            names = sorted({line for line in fh.read().split(b"\n") if line})
        if names:
            err = sys.stderr.buffer
            err.write(f"{PROG}: FAIL — {suite} called command(s) that do not exist:\n".encode())
            for name in names:
                err.write(b"    " + name + b"\n")
            err.write("    bash returns 127 for these and continues, so the suite's own\n"
                      "    failures counter never saw them — it may well have reported OK.\n".encode())
            err.flush()
            return 1
        # A suite killed by a signal: bash's $? for it, 128+n.
        return rc if rc >= 0 else 128 - rc
    finally:
        try:
            os.unlink(marker)
        except FileNotFoundError:
            pass


def main() -> int:
    def signalled(signum, _frame):
        raise Signalled(signum)
    for s in SIGNALS:
        if signal.getsignal(s) is not signal.SIG_IGN:
            signal.signal(s, signalled)
    try:
        return run(sys.argv[1:])
    except Signalled as e:
        # The marker is gone (run's finally); now die of the signal, so a
        # caller reading the status sees what it would have seen.
        sys.stderr.flush()
        signal.signal(e.signum, signal.SIG_DFL)
        os.kill(os.getpid(), e.signum)
        return 128 + e.signum


if __name__ == "__main__":
    sys.exit(main())
