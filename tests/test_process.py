#!/usr/bin/env python3
"""tools/fabric/process.py: the one owner of process lifetime (the owner's 2026-11-08 ask, j125). The code was carried from
tools/fabric/provisioning/bounded.py, whose own suite (tests/test_new_agent.py) runs unchanged against the shim as the oracle;
this file holds what the module added.

Stdlib only; runnable as `python3 tests/test_process.py`. **Each case names the mutation it kills**:

  run_timeout_ends_tree      <- run_bounded's stop_tree on TimeoutExpired dropped, or the partial output not carried
  run_interrupt_ends_tree    <- the `except BaseException` stop_tree in run_bounded dropped
  group_error_ends_tree      <- group's `except BaseException: end_group` dropped
  group_ends_setsid_helper   <- end_group's descendants walk dropped (the group KILL alone misses a helper in a session of its own)
  group_interrupt_to_handler <- raise_signal replaced by a bare KeyboardInterrupt in group
  group_interrupt_held       <- _sigint_held not entered before the spawn, or the held interrupt not raised in the body's try
  group_interrupt_no_child   <- the held interrupt not raised when the spawn itself failed
  group_spawn_error          <- OSError from the spawn swallowed
  group_sweep                <- the `sweep` branch of group's normal exit dropped, or made unconditional
  group_leaves_waited_alone  <- end_group called on a normal exit with nothing left
  signal_group_is_bool       <- ProcessLookupError not turned into False
  popen_group_shapes         <- start_new_session / process_group swapped
  shim_forwards_grace        <- bounded's STOP_GRACE_S or stop_tree write not forwarded to process
"""
from __future__ import annotations

import atexit
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import process  # noqa: E402
from provisioning import bounded  # noqa: E402

TMP = tempfile.mkdtemp(prefix="process-")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)
process.STOP_GRACE_S = 2   # a TERM-deaf child costs the grace, not the default five seconds
WAIT_S = 20


def alive(pid: int) -> bool:
    f = process._stat_fields(pid)
    return bool(f) and f[0] != "Z"


def until(what: str, check) -> None:
    deadline = time.monotonic() + WAIT_S
    while not check():
        assert time.monotonic() < deadline, f"never: {what}"
        time.sleep(0.02)


def gone(pid: int) -> bool:
    """Not alive, waited for: SIGKILL is delivered, and a member's exit is the kernel's moment, not the caller's."""
    until(f"pid {pid} gone", lambda: not alive(pid))
    return True


def pid_from(path: str) -> int:
    until(f"{path} written", lambda: os.path.isfile(path) and open(path).read().strip().isdigit())
    return int(open(path).read())


def reap(*pids: int) -> None:
    """A case that failed must not leave its sleepers behind."""
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def sleeper(name: str, extra: str = "") -> list[str]:
    """sh that records a child's pid, then waits: the child is the grandchild a bare kill of the leader would strand."""
    pidfile = os.path.join(TMP, name)
    return ["sh", "-c", f"{extra}sleep 300 & echo $! > {pidfile}.tmp; mv {pidfile}.tmp {pidfile}; wait"]


def case_run_timeout_ends_tree() -> None:
    argv = sleeper("rt", "echo partial; ")
    try:
        process.run_bounded(argv, timeout=1, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        raise AssertionError("no timeout")
    except subprocess.TimeoutExpired as exc:
        pid = pid_from(os.path.join(TMP, "rt"))
        assert not alive(pid), "the grandchild outlived the bound"
        assert exc.output == b"partial\n", exc.output
    finally:
        reap(pid_from(os.path.join(TMP, "rt")))


def case_run_interrupt_ends_tree() -> None:
    real = subprocess.Popen.communicate

    def interrupted(self, *a, **kw):
        pid_from(os.path.join(TMP, "ri"))
        raise KeyboardInterrupt

    subprocess.Popen.communicate = interrupted
    try:
        process.run_bounded(sleeper("ri"), timeout=30)
        raise AssertionError("no interrupt")
    except KeyboardInterrupt:
        pass
    finally:
        subprocess.Popen.communicate = real
    pid = pid_from(os.path.join(TMP, "ri"))
    try:
        assert not alive(pid), "an interrupt left the grandchild running"
    finally:
        reap(pid)


def case_group_error_ends_tree() -> None:
    try:
        with process.group(sleeper("ge"), stdin=subprocess.DEVNULL) as p:
            pid = pid_from(os.path.join(TMP, "ge"))
            raise RuntimeError("body failed")
    except RuntimeError:
        pass
    try:
        assert not alive(pid) and p.returncode is not None
    finally:
        reap(pid)


def case_group_ends_setsid_helper() -> None:
    # `setsid sleep` from a non-leader execs in place, so $! is the sleeper, in a session the group KILL cannot reach.
    argv = ["sh", "-c", f"setsid sleep 300 & echo $! > {TMP}/sh.tmp; mv {TMP}/sh.tmp {TMP}/sh; wait"]
    try:
        with process.group(argv) as p:
            pid = pid_from(os.path.join(TMP, "sh"))
            assert os.getsid(pid) != os.getsid(p.pid), "the helper is not in a session of its own"
            raise TimeoutError
    except TimeoutError:
        pass
    try:
        assert gone(pid), "a helper in a session of its own outlived the group's end"
    finally:
        reap(pid)


def case_group_interrupt_held() -> None:
    """An interrupt landing right after the child exists, before the body: the child is ended, the interrupt delivered."""
    real = process.popen_group
    started: list[subprocess.Popen] = []

    def spawn_then_interrupt(*a, **kw):
        p = real(*a, **kw)
        started.append(p)
        os.kill(os.getpid(), signal.SIGINT)   # the handler of ours is in, so this only notes it
        return p

    process.popen_group = spawn_then_interrupt
    entered = False
    try:
        with process.group(["sleep", "300"]):
            entered = True
        raise AssertionError("the held interrupt was lost")
    except KeyboardInterrupt:
        pass
    finally:
        process.popen_group = real
    try:
        assert not entered, "the body ran after an interrupt"
        assert started[0].returncode is not None and not alive(started[0].pid), "the child was left running"
        assert signal.getsignal(signal.SIGINT) is signal.default_int_handler, "SIGINT's handler not put back"
    finally:
        reap(started[0].pid)


def case_group_interrupt_goes_to_the_callers_handler() -> None:
    """review_codex turns SIGINT into its own exception (a cancelled ledger row); a held one must reach that handler."""
    class Cancelled(Exception):
        pass

    def handler(signum, frame):
        raise Cancelled

    real = process.popen_group
    started: list[subprocess.Popen] = []

    def spawn_then_interrupt(*a, **kw):
        p = real(*a, **kw)
        started.append(p)
        os.kill(os.getpid(), signal.SIGINT)
        return p

    process.popen_group = spawn_then_interrupt
    previous = signal.signal(signal.SIGINT, handler)
    try:
        with process.group(["sleep", "300"]):
            raise AssertionError("body entered")
    except Cancelled:
        pass
    finally:
        signal.signal(signal.SIGINT, previous)
        process.popen_group = real
    try:
        assert started[0].returncode is not None and not alive(started[0].pid), "the child was left running"
    finally:
        reap(started[0].pid)


def case_group_interrupt_no_child() -> None:
    real = process.popen_group

    def fail(*a, **kw):
        os.kill(os.getpid(), signal.SIGINT)
        raise FileNotFoundError("no such command")

    process.popen_group = fail
    try:
        with process.group(["nope"]):
            raise AssertionError("body entered")
    except KeyboardInterrupt:
        pass
    finally:
        process.popen_group = real
    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler


def case_group_spawn_error() -> None:
    try:
        with process.group([os.path.join(TMP, "no-such-command")]):
            raise AssertionError("body entered")
    except FileNotFoundError:
        pass
    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler


def case_group_sweep() -> None:
    """The leader exits at once and leaves a member in its group (a server, a build daemon)."""
    argv = ["sh", "-c", f"sleep 300 & echo $! > {TMP}/sw.tmp; mv {TMP}/sw.tmp {TMP}/sw"]
    with process.group(argv, sweep=True, stdin=subprocess.DEVNULL) as p:
        p.wait()
        pid = pid_from(os.path.join(TMP, "sw"))
    try:
        assert gone(pid), "a member left in the group outlived it"
    finally:
        reap(pid)
    os.unlink(os.path.join(TMP, "sw"))
    with process.group(argv, sweep=False) as p:
        p.wait()
        pid = pid_from(os.path.join(TMP, "sw"))
    try:
        assert alive(pid), "sweep=False ended a member of a command that was waited for"
    finally:
        reap(pid)


def case_group_leaves_waited_alone() -> None:
    called: list[int] = []
    real = process.end_group
    process.end_group = lambda proc, label="": called.append(proc.pid)
    try:
        with process.group(["true"]) as p:
            p.wait()
    finally:
        process.end_group = real
    assert not called, "a command that exited and left nothing was ended again"


def case_signal_group_is_bool() -> None:
    p = process.popen_group(["sleep", "300"])
    try:
        assert process.group_alive(p.pid)
        assert process.signal_group(p.pid, signal.SIGKILL) is True
        p.wait()
        assert process.signal_group(p.pid) is False and not process.group_alive(p.pid)
    finally:
        reap(p.pid)


def case_popen_group_shapes() -> None:
    a = process.popen_group(["sleep", "300"])
    b = process.popen_group(["sleep", "300"], session=False)
    c = process.spawn_service(["sleep", "300"])
    try:
        assert os.getsid(a.pid) == a.pid, "not a session of its own"
        assert os.getpgid(b.pid) == b.pid and os.getsid(b.pid) == os.getsid(0), "a group of the caller's session expected"
        assert os.getsid(c.pid) == c.pid
    finally:
        for p in (a, b, c):
            p.kill()
            p.wait()


def case_shim_forwards_grace() -> None:
    saved = process.STOP_GRACE_S
    try:
        bounded.STOP_GRACE_S = 0.25
        assert process.STOP_GRACE_S == 0.25 and bounded.STOP_GRACE_S == 0.25
    finally:
        bounded.STOP_GRACE_S = saved
    assert bounded.stop_tree is process.stop_tree and bounded.run_bounded is process.run_bounded
    spy_calls: list[str] = []
    real_stop = bounded.stop_tree
    bounded.stop_tree = lambda proc, label="": (spy_calls.append(label), real_stop(proc, label))
    try:
        try:
            bounded.run_bounded(["sleep", "300"], timeout=0.3, label="spy")
        except subprocess.TimeoutExpired:
            pass
    finally:
        bounded.stop_tree = real_stop
    assert spy_calls == ["spy"] and process.stop_tree is real_stop, (spy_calls, process.stop_tree)


def main() -> int:
    cases = [(n, f) for n, f in sorted(globals().items()) if n.startswith("case_") and callable(f)]
    for name, fn in cases:
        fn()
        print(f"  ok   {name[5:].replace('_', ' ')}")
    print("test_process.py: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
