"""One child, bounded in bytes and in time, and gone when the call is (agent-fabric ADR-065 §2 A).

The arguments of a review tool and the code of the pull request it reads are hostile, so a child never outlives its call:
it runs in a session of its own, its stdout is read to a byte cap and no further, and when the cap or the wall budget is
reached the whole process group is killed, not the leader alone (a check that forks is the common case, not the corner).
"""
from __future__ import annotations

import os
import select
import signal
import subprocess
import time
from dataclasses import dataclass

READ_CHUNK = 65536
STDERR_CAP = 8192        # a child's complaint is for one line of ours; never a way to flood the result
POLL_S = 0.05


@dataclass
class Ran:
    returncode: int | None       # None: the child was ended (cut or timed_out) and its status says nothing about the work
    out: bytes
    err: bytes
    cut: bool = False             # stdout reached the cap and the group was ended
    timed_out: bool = False


def _kill_group(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run_bounded(argv: list[str], env: dict[str, str], cwd: str, budget_s: float, cap_bytes: int, pass_fds: tuple[int, ...] = ()) -> Ran:
    """argv run without a shell, stdin closed, in a session of its own. The group is killed before the leader is reaped: while the leader
    is a zombie its pid, which is the group's id, cannot be handed to a stranger, so the final kill never reaches one."""
    deadline = time.monotonic() + budget_s
    p = subprocess.Popen(argv, env=env, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         start_new_session=True, pass_fds=pass_fds)
    out, err = bytearray(), bytearray()
    cut = timed_out = False
    open_fds = {p.stdout.fileno(): out, p.stderr.fileno(): err}
    try:
        # Read until both pipes are closed and the leader has exited, or the cap or the budget ends it. The moment the leader has exited
        # (seen without reaping it) the group is ended: a straggler holding the pipes open is not worth the budget, and the leader's own
        # output is already in them.
        exited = False
        while (open_fds or not exited) and not cut and not timed_out:
            left = deadline - time.monotonic()
            if left <= 0:
                timed_out = True
                break
            if open_fds:
                for fd in select.select(list(open_fds), [], [], min(left, POLL_S))[0]:
                    chunk = os.read(fd, READ_CHUNK)
                    if not chunk:
                        del open_fds[fd]
                        continue
                    sink = open_fds[fd]
                    sink += chunk
                    if sink is out and len(out) > cap_bytes:
                        del out[cap_bytes:]
                        cut = True
                    elif sink is err and len(err) > STDERR_CAP:
                        del err[STDERR_CAP:]
            else:
                time.sleep(POLL_S / 5)
            if not exited and os.waitid(os.P_PID, p.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None:
                exited = True
                _kill_group(p.pid)
    finally:
        _kill_group(p.pid)
        p.wait()
        p.stdout.close()
        p.stderr.close()
    return Ran(None if (cut or timed_out) else p.returncode, bytes(out), bytes(err), cut, timed_out)


def text_of(data: bytes, cap_bytes: int, cut: bool) -> str:
    """Bytes as text for a model, with the cut said in the text: a result that stops without saying so reads as the whole answer."""
    text = data.decode("utf-8", "replace")
    if cut:
        text += f"\n[output cut at {cap_bytes} bytes; more exists, narrow the request]"
    return text
