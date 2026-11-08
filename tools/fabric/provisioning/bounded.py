"""tools/fabric/provisioning/bounded.py — a command that cannot hold the run
(agent-fabric ADR-040 Wave 5): bounded in time, and when it runs out, ended
with everything it started. The process-lifetime code moved to
tools/fabric/process.py (2026-11-08), which this module re-exports; what is
left here is what the new-agent worker, the verification and the
orchestrator ask of an account and of a host, none of which should take long."""
from __future__ import annotations

import subprocess
import sys
import types

import process
from process import descendants, run_bounded, stop_tree  # noqa: F401  (the names callers import from here)

# Each read-back is a question to the account; none should take long, and
# a hung one (a network, a gpg-agent) must not hold the verification.
READBACK_TIMEOUT_S = 120


class _Shim(types.ModuleType):
    """STOP_GRACE_S is process.py's: a suite that bounds the grace sets it
    here, where it has always been set, and process.stop_tree must read it."""

    def __getattr__(self, name: str):
        return getattr(process, name)

    def __setattr__(self, name: str, value: object) -> None:
        if name == "STOP_GRACE_S":
            process.STOP_GRACE_S = value
        else:
            super().__setattr__(name, value)


sys.modules[__name__].__class__ = _Shim


def quiet_run(cmd: list[str], *, stderr=None) -> bytes:
    sys.stderr.flush()
    try:
        return run_bounded(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=stderr,
                           timeout=READBACK_TIMEOUT_S).stdout
    except subprocess.TimeoutExpired:
        print(f"new-agent:    {cmd[0]}: no answer within {READBACK_TIMEOUT_S} s", file=sys.stderr)
        return b""
    except OSError as exc:
        # A command that cannot start is bash's own error line, written where
        # the command's stderr went: into the pipe when it was merged there
        # (the ping's `2>&1 | tail -n +2` drops it), on stderr otherwise.
        msg = f"{cmd[0]}: {exc.strerror or exc}\n"
        if stderr is subprocess.STDOUT:
            return msg.encode("utf-8", "surrogateescape")
        print(f"new-agent:    {msg}", end="", file=sys.stderr)
        return b""


def prefixed(prefix: str, out: bytes, *, skip: int = 0) -> None:
    """`… | sed 's/^/<prefix>/' >&2`: every line, the last one completed."""
    for line in out.splitlines()[skip:]:
        sys.stderr.buffer.write(prefix.encode() + line + b"\n")
    sys.stderr.buffer.flush()
