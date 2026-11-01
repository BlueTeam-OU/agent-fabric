#!/usr/bin/env python3
"""tools/fabric/control/harness_pane.py — the ExecStartPost step of
runtime/control/agent-fabric-harness.service: open the account's harness pane
in the FleetDeck server the unit just started, and run moveto's `enter --wait`
in it.

    fabric-python harness_pane.py ensure

CONTRACT
  what      The server (`agent-fabric-fleetdeck --session harness`) holds one
            workspace labelled `harness` with one pane. `ensure` makes that so
            and runs the enter command in the pane once:
              no such workspace   `workspace create --label harness --cwd
                                  ~/projects --no-focus`, then `pane run` once
                                  its shell is alone in its foreground (a pane
                                  just made runs no program of ours: whatever
                                  stays there is its profile, never "running")
              the workspace, its pane at a plain shell (a restart restores the
              layout and not the program: measured by rust-ui-dev-01, REPLY
              01a17c6b, 2026-10-27)   `pane run` again in that pane
              the workspace, its pane already running a program (enter, or the session it started)   nothing
            Either way the line is typed only once the pane's foreground has
            settled: a pane's shell is still sourcing its profile
            then (flatpak, grepconf.sh, readlink, measured 2026-10-31: 5 of 12
            restored panes read as running and were left at a bare shell),
            so a program counts as running only when one pid of it stays in
            the foreground for SETTLE_S, and a shell alone in it is ready.
            Never a second workspace or pane: two workspaces carrying the
            label, or a workspace with other than one pane, is not understood
            and is an error, not a choice.
  enter     /usr/local/share/moveto/enter <~/projects> <login> --wait, the
            line enter-ssh runs, typed into the pane with `pane run` (quoted
            for the pane's shell). The login is the process's own, from the
            passwd database, never $USER.
  read-back After the line, the pane must run a program that settles within
            READBACK_S; a pane still at its shell is an error, so the unit
            fails and Restart=on-failure starts it again, never a second line
            typed into a pane whose first one may yet arrive (it would land
            at enter's prompt as the Enter that activates the account). The
            line is typed only while the whole of `pane run`'s timeout and
            READBACK_S are left of the step; less is an error with nothing
            typed.
  wait      The unit is Type=simple: this runs once the server is forked, not
            once its socket answers. `workspace list` is asked until it
            answers, for at most WAIT_S; a server that never answers is an
            error (the unit is then failed, and Restart=on-failure tries again).
  budget    The step as a whole ends within STEP_S: every wait ends at that
            deadline too, and every call's timeout is what is left of it, so
            the step's own `harness_pane:` line, not systemd's kill, says why
            the unit failed.
  stdout    nothing but one line saying what was done.
  exit      0 the pane is open and enter was run, or was running; 1 any failure,
            one `harness_pane: …` line on stderr, no traceback.
Every call to the binary is an argument list with a timeout and a checked
status; the JSON it prints must have the shape read here or the step stops:
a missing field is never read as "no pane".
"""
from __future__ import annotations

import json
import os
import pwd
import re
import shlex
import subprocess
import sys
import time
from typing import Any, Callable

BINARY = "/usr/local/bin/agent-fabric-fleetdeck"
SESSION = "harness"
LABEL = "harness"
ENTER = "/usr/local/share/moveto/enter"
CALL_TIMEOUT_S = 15
WAIT_S = 30
POLL_S = 0.5
# systemd's default TimeoutStartSec (90 s) bounds the unit's start, the ExecStartPost included; the 10 s left over are
# the interpreter's start and the last poll's sleep. The windows below sum to less, but a slow call runs past a
# window's end, so the step's deadline, not their sum, is the bound.
STEP_S = 80
# A profile script's child lives milliseconds, enter --wait and the session for good; under a boot's load (all accounts'
# units at once) a child can last a second or two, so the settle window is several polls.
SETTLE_S = 3
STARTUP_S = 20
READBACK_S = 20

Run = Callable[[list[str], float], "tuple[int, str, str]"]


class Failed(Exception):
    """One line on stderr, exit 1."""


def real_run(argv: list[str], timeout: float) -> tuple[int, str, str]:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, errors="replace", timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise Failed(f"{os.path.basename(argv[0])} {' '.join(argv[3:5])}: no answer within {timeout:g} s") from None
    except OSError as e:
        raise Failed(f"cannot run {argv[0]}: {e.strerror or e}") from None
    return p.returncode, p.stdout, p.stderr


class Deck:
    def __init__(self, run: Run | None = None, binary: str | None = None, session: str = SESSION):
        # Looked up now, not bound at definition, so a test names its own binary by the module's constant.
        self.run, self.prefix = run or real_run, [binary or BINARY, "--session", session]
        self.clock: Callable[[], float] = time.monotonic
        self.until = float("inf")

    def start(self, clock: Callable[[], float]) -> None:
        """From now the step has STEP_S; a call made after it is refused, one made near it times out at it."""
        self.clock, self.until = clock, clock() + STEP_S

    def left(self, within: float) -> float:
        """The deadline of a wait of `within` seconds that starts now, never past the step's."""
        return min(self.clock() + within, self.until)

    def after(self, started: float, until: float) -> str:
        """How long a wait that ended at `until` lasted, said as what bound it: its own window, or the step's
        deadline cutting it short (a window's nominal length would then name a wait that never happened)."""
        waited = f"after {self.clock() - started:.0f} s"
        return f"{waited}, when the step's {STEP_S:g} s ran out" if until >= self.until else waited

    def _run(self, args: tuple[str, ...]) -> tuple[int, str, str]:
        left = self.until - self.clock()
        if left <= 0:
            raise Failed(f"{' '.join(args[:2])}: the step's {STEP_S:g} s are spent")
        return self.run([*self.prefix, *args], min(CALL_TIMEOUT_S, left))

    def call(self, *args: str) -> dict[str, Any]:
        rc, out, err = self._run(args)
        what = " ".join(args[:2])
        if rc != 0:
            last = (err.strip().splitlines() or out.strip().splitlines() or [f"exit {rc}"])[-1][:160]
            raise Failed(f"{what}: {last}")
        try:
            doc = json.loads(out)
        except ValueError:
            raise Failed(f"{what}: the answer is not JSON") from None
        result = doc.get("result") if isinstance(doc, dict) else None
        if not isinstance(result, dict):
            raise Failed(f"{what}: the answer has no result object")
        return result

    def text(self, *args: str) -> None:
        rc, out, err = self._run(args)
        if rc != 0:
            last = (err.strip().splitlines() or out.strip().splitlines() or [f"exit {rc}"])[-1][:160]
            raise Failed(f"{' '.join(args[:2])}: {last}")


def _field(obj: Any, *path: str, what: str) -> Any:
    for key in path:
        if not isinstance(obj, dict) or key not in obj:
            raise Failed(f"{what}: the answer has no {'.'.join(path)}")
        obj = obj[key]
    return obj


# Never a leading "-": an id from the binary's JSON goes into an argv, where it would be read as an option.
ID = re.compile(r"[A-Za-z0-9_.:][A-Za-z0-9_.:-]*")


def _id(value: Any, what: str) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise Failed(f"{what}: an id that is not a plain id string")
    return value


def enter_command(login: str, home: str) -> str:
    return shlex.join([ENTER, os.path.join(home, "projects"), login, "--wait"])


def wait_for_server(deck: Deck, clock: Callable[[], float], sleep: Callable[[float], None]) -> dict[str, Any]:
    until = deck.left(WAIT_S)
    while True:
        try:
            return deck.call("workspace", "list")
        except Failed as e:
            if clock() >= until:
                raise Failed(f"the server did not answer within {WAIT_S} s ({e})") from None
            sleep(POLL_S)


def foreground_programs(info: dict[str, Any]) -> set[int]:
    """The pids in the pane's foreground besides its shell: enter in its wait, a shell it became, the session, or a
    profile script still running at the shell's start. The answer must name the shell and list the foreground
    processes: a pane at a plain shell lists its shell, so a list that is empty or has no pids is an answer not
    understood, not an idle pane."""
    shell = _field(info, "process_info", "shell_pid", what="pane process-info")
    procs = _field(info, "process_info", "foreground_processes", what="pane process-info")
    if not isinstance(shell, int) or not isinstance(procs, list) or not procs:
        raise Failed("pane process-info: no shell pid or no foreground process listed")
    pids = [p.get("pid") if isinstance(p, dict) else None for p in procs]
    if not all(isinstance(pid, int) for pid in pids):
        raise Failed("pane process-info: a foreground process without a pid")
    return {pid for pid in pids if pid != shell}


def settled(deck: Deck, pane: str, clock: Callable[[], float], sleep: Callable[[float], None], within: float,
            shell_waits: bool) -> bool:
    """True once one non-shell pid has stayed in the foreground for SETTLE_S: a program runs. With the shell alone in
    the foreground, False at once, or, with shell_waits, asked again until a program settles. Never settled within
    `within` is an error naming what was seen."""
    started, until = clock(), deck.left(within)
    kept: set[int] | None = None    # the pids seen in every read since `since`
    since = started
    while True:
        pids = foreground_programs(deck.call("pane", "process-info", "--pane", pane))
        if not pids:
            if not shell_waits:
                return False
            kept = None
        elif kept is None or not kept & pids:
            kept, since = pids, clock()
        else:
            kept &= pids
            if clock() - since >= SETTLE_S:
                return True
        if clock() >= until:
            what = "is still at its shell" if not pids else "has no program that stays in its foreground"
            raise Failed(f"the {LABEL} pane {pane} {what} {deck.after(started, until)}")
        sleep(POLL_S)


def shell_alone(deck: Deck, pane: str, clock: Callable[[], float], sleep: Callable[[float], None], within: float) -> None:
    """Returns at the first read with the shell alone in the pane's foreground. For a pane this step just made, where
    whatever else is there is its profile however long it stays: never read as a program already running."""
    started, until = clock(), deck.left(within)
    while foreground_programs(deck.call("pane", "process-info", "--pane", pane)):
        if clock() >= until:
            raise Failed(f"the {LABEL} pane {pane} has not come to its shell {deck.after(started, until)}")
        sleep(POLL_S)


def ensure(deck: Deck, login: str, home: str, clock: Callable[[], float] = time.monotonic,
           sleep: Callable[[float], None] = time.sleep) -> str:
    deck.start(clock)
    listing = wait_for_server(deck, clock, sleep)
    workspaces = _field(listing, "workspaces", what="workspace list")
    if not isinstance(workspaces, list):
        raise Failed("workspace list: workspaces is not a list")
    # An entry without a `label` is a shape not understood, not an unlabelled workspace: reading it as "none of ours"
    # would create a second harness workspace on every start. A present null is an unlabelled one.
    if not all(isinstance(w, dict) and "label" in w for w in workspaces):
        raise Failed("workspace list: an entry is not an object with a label")
    ours = [w for w in workspaces if w["label"] == LABEL]
    if len(ours) > 1:
        raise Failed(f"{len(ours)} workspaces are labelled {LABEL}; refusing to choose one")
    command = enter_command(login, home)
    if not ours:
        made = deck.call("workspace", "create", "--label", LABEL, "--cwd", os.path.join(home, "projects"), "--no-focus")
        pane = _id(_field(made, "root_pane", "pane_id", what="workspace create"), "workspace create")
        said = f"opened the {LABEL} pane {pane}"
        shell_alone(deck, pane, clock, sleep, STARTUP_S)
    else:
        workspace = _id(ours[0].get("workspace_id"), "workspace list")
        panes = _field(deck.call("pane", "list", "--workspace", workspace), "panes", what="pane list")
        if not isinstance(panes, list) or len(panes) != 1:
            raise Failed(f"the {LABEL} workspace holds {len(panes) if isinstance(panes, list) else 'an unreadable list of'} panes, not one; refusing to choose")
        pane = _id(_field(panes[0], "pane_id", what="pane list") if isinstance(panes[0], dict) else None, "pane list")
        said = f"ran enter again in the restored {LABEL} pane {pane}"
        if settled(deck, pane, clock, sleep, STARTUP_S, shell_waits=False):
            return f"the {LABEL} pane {pane} is already running a program (enter, or the session it started)"
    # The line is typed only with room for all of `pane run` (CALL_TIMEOUT_S) and then all of the read-back
    # (READBACK_S). A call cut short times out with the line's arrival unknown, and a read-back cut short fails a pane
    # whose enter did start; either fails the unit, and the restart kills that enter. Not typing is the safe side:
    # the restart types it.
    if deck.until - clock() < CALL_TIMEOUT_S + READBACK_S:
        raise Failed(f"the {LABEL} pane {pane} was not typed into: less than the {CALL_TIMEOUT_S + READBACK_S:g} s "
                     f"`pane run` and its read-back need is left of the step's {STEP_S:g} s")
    deck.text("pane", "run", pane, command)
    settled(deck, pane, clock, sleep, READBACK_S, shell_waits=True)
    return said


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args != ["ensure"]:
        print("usage: harness_pane.py ensure", file=sys.stderr)
        return 2
    try:
        entry = pwd.getpwuid(os.getuid())
        print(ensure(Deck(), entry.pw_name, entry.pw_dir))
    except Failed as e:
        print(f"harness_pane: {e}", file=sys.stderr)
        return 1
    except (KeyError, OSError) as e:
        print(f"harness_pane: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
