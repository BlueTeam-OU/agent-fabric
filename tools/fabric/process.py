"""tools/fabric/process.py — the one owner of process lifetime: starting a
command in a group of its own, and ending it with everything it started
(the owner's 2026-11-08 ask for one owner per cross-cutting mechanism).

A module that spawns a command into a session or group of its own, or
signals a group, calls this module; tools/fabric/process_spawns.py finds the
one that does it itself. What a caller may rely on:

- run_bounded: subprocess.run(cmd, input=…, timeout=…) whose timeout, and
  whose interrupt (any BaseException), ends the command's whole process tree
  (stop_tree) before the exception goes on; TimeoutExpired carries what the
  command had written.
- group: a context manager for a command that leads a session of its own.
  SIGINT is held from before the spawn until the body is entered and then
  delivered through the cleanup, so an interrupt cannot unwind past the only
  handle of a child that nothing else signals; on any exit the child's tree
  is ended (end_group).
- end_group: the descendants by parentage first (stop_tree: TERM, then KILL
  for the TERM-deaf), then the group KILL.
- popen_group / spawn_service: the bare spawns, for a caller that keeps its
  own handle or lets the command outlive it.
- signal_group, group_alive: the signal to a group, and whether one is left.

Carried from tools/fabric/provisioning/bounded.py (which re-exports it) and
from the sites the 2026-11-08 sweep moved here; each lesson below records
the incident that made the code the way it is."""
from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time
from collections.abc import Iterator

# A command that runs out is ended with what it started: its direct child is
# sudo, ssh or a bash wrapper, and killing that alone left the rest running —
# an account still being set up after the run said it failed. SIGTERM goes to
# the whole tree first, since sudo relays it to the command it runs (SIGKILL it
# cannot relay, and a process of another account is not ours to signal);
# SIGKILL follows for whatever is left after the grace.
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


def stop_tree(proc: subprocess.Popen, label: str = "new-agent") -> None:
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
            print(f"{label}:    {proc.args[0]}: still running after SIGKILL: pid {left}", file=sys.stderr)
            break
        time.sleep(0.02)
    unreached = " ".join(str(p) for p in tree if alive(p) and reach(p) == "theirs")
    if unreached:
        print(f"{label}:    {proc.args[0]}: could not be signalled (another account's): pid {unreached}", file=sys.stderr)


def run_bounded(cmd: list[str], *, timeout: float, input: bytes | None = None, label: str = "new-agent",
                **popen) -> subprocess.CompletedProcess:
    """subprocess.run(cmd, input=…, timeout=…), the timeout ending the
    command's whole process tree (stop_tree) before TimeoutExpired is
    raised. The exception carries the bound the call was given: before
    3.13, the one communicate() raises holds what was left of it. It also
    carries what the command had written, as subprocess.run's does: a caller
    builds its one-line reason from it. `label` is what stop_tree's own
    stderr lines are prefixed with."""
    with subprocess.Popen(cmd, **popen) as proc:
        try:
            out, err = proc.communicate(input, timeout=timeout)
        except subprocess.TimeoutExpired:
            stop_tree(proc, label)
            # The tree is gone, so the pipes reach EOF; the bound is for a process stop_tree could not signal.
            try:
                out, err = proc.communicate(timeout=STOP_GRACE_S)
            except subprocess.TimeoutExpired:
                out = err = None
            raise subprocess.TimeoutExpired(cmd, timeout, output=out, stderr=err) from None
        except BaseException:
            # An interrupt ends the tree too: Popen's __exit__ only waits for the direct child.
            stop_tree(proc, label)
            raise
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


# ── groups ────────────────────────────────────────────────────────────

def signal_group(pgid: int, sig: int = signal.SIGKILL) -> bool:
    """sig to the group; False when none is left to signal (gone, or another
    account's), which is what every caller wanted to know. A group id names
    a group only while its leader's pid is held (unreaped) or a member is
    left: once both are gone the number can be a stranger's, so a caller
    signals before it reaps the leader."""
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def group_alive(pgid: int) -> bool:
    return signal_group(pgid, 0)


def popen_group(argv: list[str], *, session: bool = True, **popen) -> subprocess.Popen:
    """Popen with the command leading a group of its own: a session (the
    default: no controlling terminal, so a terminal's Ctrl-C does not reach
    it, and a caller that must end it on an interrupt says so with `group`),
    or with session=False only a process group of the caller's session, which
    keeps the terminal and is what a wrapper that forwards signals wants."""
    return subprocess.Popen(argv, **popen, **({"start_new_session": True} if session else {"process_group": 0}))


def spawn_service(argv: list[str], **popen) -> subprocess.Popen:
    """A command that outlives the caller: a session of its own, so the
    caller's group signals and its terminal's hangup do not reach it. Not
    ended by this module; whoever starts one owns its stop."""
    return popen_group(argv, **popen)


def end_group(proc: subprocess.Popen, label: str = "new-agent") -> None:
    """The command's descendants by parentage (stop_tree: TERM, then KILL for
    the TERM-deaf), then its group: a helper that made a session of its own
    is in no group of ours, and only the parentage finds it, so the walk comes
    before any signal (a group TERM first would kill the parent and orphan the
    helper out of the walk). The group KILL takes a member orphaned to init,
    which the walk cannot see."""
    helpers = descendants(proc.pid)   # noted first: a signal inside stop_tree's grace skips its own KILL
    try:
        stop_tree(proc, label)
    finally:
        for pid in helpers:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.kill(pid, signal.SIGKILL)
        signal_group(proc.pid)
        proc.wait()


@contextlib.contextmanager
def _sigint_held() -> Iterator[list[bool]]:
    """SIGINT noted, not acted on, for the body; [True] afterwards when one
    came. Off the main thread, or with SIGINT ignored (a background job),
    there is no handler of ours to swap in and nothing is held."""
    interrupted = [False]

    def note(signum: int, frame: object) -> None:
        interrupted[0] = True

    previous: object = None
    if signal.getsignal(signal.SIGINT) is not signal.SIG_IGN:
        with contextlib.suppress(ValueError):
            previous = signal.signal(signal.SIGINT, note)
    try:
        yield interrupted
    finally:
        if previous is not None:
            signal.signal(signal.SIGINT, previous)


@contextlib.contextmanager
def group(argv: list[str], *, label: str = "new-agent", sweep: bool = True, **popen) -> Iterator[subprocess.Popen]:
    """The command in a session of its own, ended with its tree on any way
    out of the body (a timeout, an interrupt, an error). An interrupt that
    lands inside Popen, or between it and the body, would unwind past the
    only handle of a child that leads a session of its own and that nothing
    else signals; so SIGINT is held from before the spawn and delivered, as a
    KeyboardInterrupt, once the body is entered. OSError from the spawn goes
    to the caller (with a held interrupt raised instead: no child exists).
    `sweep` also ends what a command that exited left in its group (a server,
    a build daemon); off, a command that was waited for is left as it ended."""
    with _sigint_held() as interrupted:
        try:
            proc = popen_group(argv, **popen)
        except OSError:
            if interrupted[0]:
                raise KeyboardInterrupt from None
            raise
    # The handler is back: a second SIGINT is the default's, delivered below by the body's own try.
    try:
        if interrupted[0]:
            raise KeyboardInterrupt
        yield proc
    except BaseException:
        end_group(proc, label)
        raise
    else:
        if proc.poll() is None or (sweep and group_alive(proc.pid)):
            end_group(proc, label)
