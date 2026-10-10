"""tools/fabric/provisioning/bounded.py — a command that cannot hold the run
(agent-fabric ADR-040 Wave 5): bounded in time, and when it runs out, ended
with everything it started. Carried unchanged from tools/fabric/
new_agent_worker.py (which the decomposition retired); the worker, the
verification and the orchestrator ask these questions of an account and of
a host, and none should take long."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

# Each read-back is a question to the account; none should take long, and
# a hung one (a network, a gpg-agent) must not hold the verification.
READBACK_TIMEOUT_S = 120
# A bounded command that runs out is ended with what it started: its direct
# child is sudo, ssh or a bash wrapper, and killing that alone left the rest
# running — an account still being set up after the run said it failed.
# SIGTERM goes to the whole tree first, since sudo relays it to the command
# it runs (SIGKILL it cannot relay, and a process of another account is not
# ours to signal); SIGKILL follows for whatever is left after the grace.
STOP_GRACE_S = 5


def _stat_fields(pid: int) -> list[str] | None:
    """/proc/<pid>/stat after the command name, which may hold spaces and
    parentheses: [state, ppid, ...]; None when the process is gone."""
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii", errors="replace") as fh:
            return fh.read().rsplit(")", 1)[1].split()
    except (OSError, IndexError):
        return None


def descendants(pid: int) -> list[int]:
    kids: dict[int, list[int]] = {}
    for entry in os.listdir("/proc"):
        if entry.isdigit():
            f = _stat_fields(int(entry))
            if f and len(f) > 1 and f[1].isdigit():
                kids.setdefault(int(f[1]), []).append(int(entry))
    found, todo = [], [pid]
    while todo:
        for k in kids.get(todo.pop(), []):
            found.append(k)
            todo.append(k)
    return found


def stop_tree(proc: subprocess.Popen) -> None:
    def alive(pid: int) -> bool:
        f = _stat_fields(pid)
        return bool(f) and f[0] != "Z"

    def reach(pid: int) -> str:
        """Whether a signal reaches it: "ours"; "theirs" for a process of
        another account (root's, under sudo), which no wait makes ours; or
        "gone", exited since it was last seen — kept apart from "theirs", so
        a process that just ended is not named another account's."""
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return "gone"
        except PermissionError:
            return "theirs"
        return "ours"

    def send(pids: list[int], sig: int) -> None:
        for pid in pids:
            try:
                os.kill(pid, sig)
            except (ProcessLookupError, PermissionError):
                pass

    def running() -> list[int]:
        return [p for p in tree if alive(p) and reach(p) == "ours"]
    tree = [proc.pid, *descendants(proc.pid)]
    send(tree, signal.SIGTERM)
    deadline = time.monotonic() + STOP_GRACE_S
    while time.monotonic() < deadline:
        proc.poll()
        tree += [d for d in (descendants(proc.pid) if proc.returncode is None else []) if d not in tree]
        if not running():
            break
        time.sleep(0.05)
    send(running(), signal.SIGKILL)
    proc.wait()
    # SIGKILL is delivered, not yet acted on: a grandchild can still read
    # as running for a moment after it, and "ended" is a claim about the
    # tree, so it is waited for — bounded, and said if the bound passes.
    # Only what a signal reached is waited for; the rest is named as such.
    deadline = time.monotonic() + STOP_GRACE_S
    while running():
        if time.monotonic() >= deadline:
            left = " ".join(str(p) for p in running())
            print(f"new-agent:    {proc.args[0]}: still running after SIGKILL: pid {left}", file=sys.stderr)
            break
        time.sleep(0.02)
    unreached = " ".join(str(p) for p in tree if alive(p) and reach(p) == "theirs")
    if unreached:
        print(f"new-agent:    {proc.args[0]}: could not be signalled (another account's): pid {unreached}", file=sys.stderr)


def run_bounded(cmd: list[str], *, timeout: float, input: bytes | None = None, **popen) -> subprocess.CompletedProcess:
    """subprocess.run(cmd, input=…, timeout=…), the timeout ending the
    command's whole process tree (stop_tree) before TimeoutExpired is
    raised. The exception carries the bound the call was given: before
    3.13, the one communicate() raises holds what was left of it."""
    with subprocess.Popen(cmd, **popen) as proc:
        try:
            out, err = proc.communicate(input, timeout=timeout)
        except subprocess.TimeoutExpired:
            stop_tree(proc)
            raise subprocess.TimeoutExpired(cmd, timeout) from None
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


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
