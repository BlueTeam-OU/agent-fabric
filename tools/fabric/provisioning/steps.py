"""tools/fabric/provisioning/steps.py — each command of a new-agent run, bounded,
its failures kept out of the way in a log and shown (its last lines) only when a
step fails (carried from tools/fabric/new_agent.py)."""
from __future__ import annotations

import os
import subprocess
import sys
import threading

from provisioning import config as cfg
from provisioning.bounded import run_bounded, stop_tree
from provisioning.new_agent_args import say


class Steps:
    """Each command of the run, bounded, its failures kept out of the way
    in LOG and shown (its last lines) only when a step fails."""

    def __init__(self, log: str):
        self.log = log

    def tail(self, n: int) -> None:
        try:
            with open(self.log, encoding="utf-8", errors="surrogateescape") as fh:
                lines = fh.read().splitlines()
        except OSError:
            return
        for line in lines[-n:]:
            print(line, file=sys.stderr)
        sys.stderr.flush()

    def capture(self, cmd: list[str], *, timeout: float = cfg.STEP_TIMEOUT_S, stdin=subprocess.DEVNULL) -> tuple[int, str]:
        """stdout captured; stderr appended to LOG, as `2>>"$LOG"` did."""
        with open(self.log, "a", encoding="utf-8") as err:
            try:
                r = run_bounded(cmd, stdin=stdin, stdout=subprocess.PIPE, stderr=err, text=True,
                                errors="surrogateescape", timeout=timeout)
            except subprocess.TimeoutExpired:
                err.write(f"{cmd[0]}: no answer within {timeout} s\n")
                return 124, ""
            except OSError as exc:
                err.write(f"{cmd[0]}: {exc.strerror or exc}\n")
                return 127, ""
        return r.returncode, r.stdout.rstrip("\n")

    def through(self, cmd: list[str], *, timeout: float = cfg.WORKER_TIMEOUT_S, quiet_stdout: bool = False) -> int:
        """A command whose output is the person's to read, as it comes."""
        sys.stderr.flush()
        try:
            return run_bounded(cmd, stdin=None, stdout=subprocess.DEVNULL if quiet_stdout else None,
                               timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            say(f"{os.path.basename(cmd[0])} {' '.join(cmd[1:4])}: no answer within {timeout} s")
            return 124
        except OSError as exc:
            say(f"{cmd[0]}: {exc.strerror or exc}")
            return 127

    @staticmethod
    def indented(*cmds: list[str], timeout: float = cfg.STEP_TIMEOUT_S) -> list[int]:
        """`a | b … 2>&1 | sed 's/^/   /' >&2`: a pipeline, the LAST
        command's stderr merged into its stdout, every line indented three
        spaces on our stderr as it comes; each command's status, in order
        (bash's PIPESTATUS, without sed's)."""
        sys.stderr.flush()
        procs, prev = [], subprocess.DEVNULL
        try:
            for n, cmd in enumerate(cmds):
                last = n == len(cmds) - 1
                p = subprocess.Popen(cmd, stdin=prev, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT if last else None)
                if prev is not subprocess.DEVNULL:
                    prev.close()
                procs.append(p)
                prev = p.stdout
        except OSError as exc:
            say(f"{cmds[len(procs)][0]}: {exc.strerror or exc}")
            for p in procs:
                p.kill()
                p.wait()
            return [127] * len(cmds)
        out = procs[-1].stdout
        killed = []

        def overdue() -> None:
            for p in procs:
                if p.poll() is None:
                    killed.append(p)
                    stop_tree(p)
        timer = threading.Timer(timeout, overdue)
        timer.start()
        try:
            for raw in out:
                sys.stderr.buffer.write(b"   " + raw)
                sys.stderr.buffer.flush()
        finally:
            timer.cancel()
            out.close()
        statuses = []
        for p in procs:
            rc = p.wait()
            statuses.append(124 if p in killed else rc)
        if killed:
            say(f"{os.path.basename(cmds[0][0])}: no answer within {timeout} s")
        return statuses
