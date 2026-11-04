"""tools/fabric/control/units.py — `fabric-ctl <login|all> control-start | control-stop
| harness-start | harness-stop`: start or stop each account's control agent
(agent-fabric-agentd.service) or its harness unit (agent-fabric-harness.service,
the account's FleetDeck server, whose one pane runs the session), both systemd
user units, through the host executor (runtime/hostexec, ADR-010).

A stopped agent cannot answer the wire, so these are the only fabric-ctl
ops that never send a request: nothing is signed and no relay is read. The
operator's sudo is the gate, as it is for hostexec itself.

    fabric-ctl <login|all> control-start [--json] [--timeout S]
    fabric-ctl <login|all> control-stop  [--json] [--timeout S] [--include-self]
    fabric-ctl <login|all> harness-start [--json] [--timeout S]
    fabric-ctl <login|all> harness-stop  [--json] [--timeout S] [--include-self]

harness-stop is how a session is ended without hanging up its pane: the unit's
stop signals every process of the account's server (agent-fabric-harness.service,
KillMode), so the launcher takes SIGTERM and `claude` ends with its session
resumable. A hang-up of a deck's attach ends only the attach.

Per account, on the account's host: `id -u <login>`, then
`sudo -n -u <login> env XDG_RUNTIME_DIR=/run/user/<uid>
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/<uid>/bus systemctl --user
is-active|start|stop <unit>`, each one hostexec call with an argument list and
a timeout. `fabric-host run --as` is not used: its clean environment has no
user bus. The result is always read back with is-active, never taken from
`start`'s or `stop`'s exit status alone.

Rows (--json: one line each; otherwise a table):
    {"login", "state", "detail"}
    *-start  state active (it already was) | started | failed
    *-stop   state stopped (it was, or now is) | failed | skipped
`skipped` is only the account this session runs as, which a stop leaves
alone unless --include-self: stopping it ends the agent the operator is
working beside (the harness unit's: the session itself). A skipped row is not a failure.

`skipped` for a self account named explicitly (not through `all`) is a refusal
instead: exit 2, nothing run.

Exit: 0 every row is active (start) or stopped/skipped (stop); 1 any failed
row; 2 a refusal (an unknown or human login, a bad option) with nothing run.
The units stay enabled: they come back at boot, or at the next bootstrap /
moveto entry of the account, which runs `enable --now`.

--timeout is the bound of each host call, not of the run: an account takes up to
four calls, accounts one after another.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from typing import Any, Callable

UNIT = "agent-fabric-agentd.service"
HARNESS_UNIT = "agent-fabric-harness.service"
# op -> (unit, verb). A verb of "start" reads active afterwards, of "stop" inactive.
OPS = {"control-start": (UNIT, "start"), "control-stop": (UNIT, "stop"),
       "harness-start": (HARNESS_UNIT, "start"), "harness-stop": (HARNESS_UNIT, "stop")}
UNIT_OPS = tuple(OPS)
START, STOP = "control-start", "control-stop"
STEP_TIMEOUT_S = 60
LOGIN = re.compile(r"[a-z_][a-z0-9_-]*")
# is-active prints exactly one of these for a unit it knows; anything else on
# stdout (or nothing) means systemctl could not ask, which is a failure to
# read, not a state.
ACTIVE_STATES = frozenset({"active", "activating", "deactivating", "reloading", "inactive", "failed", "maintenance", "refreshing"})
# Type=simple: `start` returns once the process is forked, so a daemon that dies
# in its first moments still reads active. The unit restarts after RestartSec=5,
# and a read after this settle sees it activating (auto-restart) instead.
SETTLE_S = 2
STOPPED_STATES = frozenset({"inactive", "failed"})

Run = Callable[[str, list[str], float], "tuple[int, str, str]"]


class StepFailed(Exception):
    """One host call that did not give a usable answer; the message is the row's detail."""


def _hostexec() -> str:
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
    return os.path.join(root, "runtime", "hostexec", "hostexec")


def hostexec_run(registry: str | None = None) -> Run:
    """The real executor: one hostexec call, as the host's operator."""
    env = dict(os.environ)
    if registry is not None:
        env["AGENT_FABRIC_HOSTS_REGISTRY"] = registry

    def run(host: str, argv: list[str], timeout: float) -> tuple[int, str, str]:
        p = subprocess.run([_hostexec(), host, "--", *argv], capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL, env=env, errors="replace")
        return p.returncode, p.stdout, p.stderr
    return run


def _say(text: str) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1][:200] if lines else ""


def _call(run: Run, host: str, argv: list[str], timeout: float, what: str) -> tuple[int, str, str]:
    try:
        return run(host, argv, timeout)
    except subprocess.TimeoutExpired:
        raise StepFailed(f"{what}: no answer within {round(timeout)} s") from None
    except FileNotFoundError:
        raise StepFailed(f"{what}: hostexec not found") from None
    except OSError as e:
        raise StepFailed(f"{what}: could not run ({e.strerror or e})") from None


def user_uid(run: Run, host: str, login: str, timeout: float) -> int:
    rc, out, err = _call(run, host, ["id", "-u", login], timeout, "id -u")
    word = out.strip()
    if rc != 0 or not word.isdigit():
        raise StepFailed(f"no uid for {login} on {host}: {_say(err) or _say(out) or f'exit {rc}'}")
    return int(word)


def is_start(op: str) -> bool:
    return OPS[op][1] == "start"


def systemctl(run: Run, host: str, login: str, uid: int, verb: str, timeout: float, unit: str = UNIT) -> tuple[int, str, str]:
    # The user bus is addressed by hand: `sudo -u` keeps neither variable, and
    # hostexec's `--as` clears the environment, which has no bus to give back.
    run_dir = f"/run/user/{uid}"
    argv = ["sudo", "-n", "-u", login, "env", f"XDG_RUNTIME_DIR={run_dir}", f"DBUS_SESSION_BUS_ADDRESS=unix:path={run_dir}/bus",
            "systemctl", "--user", verb, unit]
    return _call(run, host, argv, timeout, f"systemctl --user {verb}")


def is_active(run: Run, host: str, login: str, uid: int, timeout: float, unit: str = UNIT) -> str:
    """The unit's state word. `is-active` exits non-zero for every state but
    active, so the word is read, not the status; an unreadable answer raises."""
    rc, out, err = systemctl(run, host, login, uid, "is-active", timeout, unit)
    word = out.strip()
    if word not in ACTIVE_STATES:
        raise StepFailed(f"is-active gave no state: {_say(err) or _say(out) or f'exit {rc}'}")
    return word


def _act(run: Run, host: str, login: str, uid: int, verb: str, timeout: float, unit: str = UNIT) -> None:
    rc, out, err = systemctl(run, host, login, uid, verb, timeout, unit)
    if rc != 0:
        raise StepFailed(f"systemctl --user {verb} exit {rc}: {_say(err) or _say(out) or 'no output'}")


def one(op: str, placed: dict, run: Run, timeout: float, sleep: Callable[[float], None] = time.sleep) -> dict:
    login, host = placed["login"], placed["host"]
    unit = OPS[op][0]
    row = lambda state, detail="": {"login": login, "state": state, "detail": detail}  # noqa: E731
    try:
        if not LOGIN.fullmatch(login):
            raise StepFailed(f"{login!r} is not a login name")
        uid = user_uid(run, host, login, timeout)
        before = is_active(run, host, login, uid, timeout, unit)
        if is_start(op):
            if before == "active":
                return row("active", "already active")
            _act(run, host, login, uid, "start", timeout, unit)
            sleep(SETTLE_S)
            after = is_active(run, host, login, uid, timeout, unit)
            if after == "active":
                return row("started", f"was {before}")
            # A unit whose ConditionPathExists fails starts "successfully" and stays inactive: said, not guessed at.
            hint = " (the unit is skipped on an account without /usr/local/bin/agent-fabric-fleetdeck)" if unit == HARNESS_UNIT and after == "inactive" else ""
            return row("failed", f"is-active reads {after} after start{hint}")
        if before in STOPPED_STATES:
            return row("stopped", f"already {before}")
        _act(run, host, login, uid, "stop", timeout, unit)
        after = is_active(run, host, login, uid, timeout, unit)
        return row("stopped", f"was {before}") if after in STOPPED_STATES else row("failed", f"is-active reads {after} after stop")
    except StepFailed as e:
        return row("failed", str(e))


def run_units(op: str, expected: list[dict], *, run: Run, me: str | None, include_self: bool = False,
              timeout: float = STEP_TIMEOUT_S, sleep: Callable[[float], None] = time.sleep) -> list[dict]:
    rows = []
    for placed in expected:
        if not is_start(op) and placed["login"] == me and not include_self:
            rows.append({"login": placed["login"], "state": "skipped", "detail": "this session's own account (--include-self stops it)"})
        else:
            rows.append(one(op, placed, run, timeout, sleep))
    return rows


def ok(op: str, rows: list[dict]) -> bool:
    good = ("active", "started") if is_start(op) else ("stopped", "skipped")
    return all(r["state"] in good for r in rows)


def table(rows: list[dict]) -> str:
    width = max((len(r["login"]) for r in rows), default=0)
    return "\n".join(f"{r['login'].ljust(width)}  {r['state'].ljust(7)}  {r['detail']}".rstrip() for r in rows)


def check_args(args: dict[str, Any]) -> str:
    """The refusal for options that do not go with this op, or ""."""
    if args.get("include_self") and (args["op"] not in OPS or is_start(args["op"])):
        return "--include-self goes with control-stop and harness-stop only"
    return ""
