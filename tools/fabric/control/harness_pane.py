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
                                  ~/projects --no-focus`, then `pane run`
              the workspace, its pane at a plain shell (a restart restores the
              layout and not the program: measured by rust-ui-dev-01, REPLY
              01a17c6b, 2026-10-27)   `pane run` again in that pane
              the workspace, its pane already running a program (enter, or the session it started)   nothing
            Never a second workspace or pane: two workspaces carrying the
            label, or a workspace with other than one pane, is not understood
            and is an error, not a choice.
  enter     /usr/local/share/moveto/enter <~/projects> <login> --wait, the
            line enter-ssh runs, typed into the pane with `pane run` (quoted
            for the pane's shell). The login is the process's own, from the
            passwd database, never $USER.
  wait      The unit is Type=simple: this runs once the server is forked, not
            once its socket answers. `workspace list` is asked until it
            answers, for at most WAIT_S; a server that never answers is an
            error (the unit is then failed, and Restart=on-failure tries again).
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

Run = Callable[[list[str]], "tuple[int, str, str]"]


class Failed(Exception):
    """One line on stderr, exit 1."""


def real_run(argv: list[str]) -> tuple[int, str, str]:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, errors="replace", timeout=CALL_TIMEOUT_S, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise Failed(f"{os.path.basename(argv[0])} {' '.join(argv[3:5])}: no answer within {CALL_TIMEOUT_S} s") from None
    except OSError as e:
        raise Failed(f"cannot run {argv[0]}: {e.strerror or e}") from None
    return p.returncode, p.stdout, p.stderr


class Deck:
    def __init__(self, run: Run | None = None, binary: str | None = None, session: str = SESSION):
        # Looked up now, not bound at definition, so a test names its own binary by the module's constant.
        self.run, self.prefix = run or real_run, [binary or BINARY, "--session", session]

    def call(self, *args: str) -> dict[str, Any]:
        rc, out, err = self.run([*self.prefix, *args])
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
        rc, out, err = self.run([*self.prefix, *args])
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
    until = clock() + WAIT_S
    while True:
        try:
            return deck.call("workspace", "list")
        except Failed as e:
            if clock() >= until:
                raise Failed(f"the server did not answer within {WAIT_S} s ({e})") from None
            sleep(POLL_S)


def running_program(info: dict[str, Any]) -> bool:
    """Whether the pane runs a program besides its shell: enter in its wait, a shell it became, or the session. Any
    foreground process that is not the pane's shell counts, so a session in progress is never typed over. The answer
    must name the shell and list the foreground processes: a pane at a plain shell lists its shell, so a list that is
    empty or has no pids is an answer not understood, not an idle pane."""
    shell = _field(info, "process_info", "shell_pid", what="pane process-info")
    procs = _field(info, "process_info", "foreground_processes", what="pane process-info")
    if not isinstance(shell, int) or not isinstance(procs, list) or not procs:
        raise Failed("pane process-info: no shell pid or no foreground process listed")
    pids = [p.get("pid") if isinstance(p, dict) else None for p in procs]
    if not all(isinstance(pid, int) for pid in pids):
        raise Failed("pane process-info: a foreground process without a pid")
    return any(pid != shell for pid in pids)


def ensure(deck: Deck, login: str, home: str, clock: Callable[[], float] = time.monotonic,
           sleep: Callable[[float], None] = time.sleep) -> str:
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
        deck.text("pane", "run", pane, command)
        return f"opened the {LABEL} pane {pane}"
    workspace = _id(ours[0].get("workspace_id"), "workspace list")
    panes = _field(deck.call("pane", "list", "--workspace", workspace), "panes", what="pane list")
    if not isinstance(panes, list) or len(panes) != 1:
        raise Failed(f"the {LABEL} workspace holds {len(panes) if isinstance(panes, list) else 'an unreadable list of'} panes, not one; refusing to choose")
    pane = _id(_field(panes[0], "pane_id", what="pane list") if isinstance(panes[0], dict) else None, "pane list")
    if running_program(deck.call("pane", "process-info", "--pane", pane)):
        return f"the {LABEL} pane {pane} is already running a program (enter, or the session it started)"
    deck.text("pane", "run", pane, command)
    return f"ran enter again in the restored {LABEL} pane {pane}"


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
