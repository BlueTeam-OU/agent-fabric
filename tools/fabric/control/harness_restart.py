"""tools/fabric/control/harness_restart.py — `fabric-ctl <login|all> harness-restart`:
restart an idle account's harness unit (agent-fabric-harness.service, its FleetDeck
server and the session pane in it) so that the pane resumes the session by itself.

    fabric-ctl <login|all> harness-restart [--json] [--timeout S] [--include-self]

CONTRACT
  why     A restart ends the server's pane, and the unit's ExecStartPost
          (harness_pane.py ensure) types `enter … --wait`, which waits for a
          person's Enter. This verb makes the one ensure that follows its start
          type `--resume` instead (the ADR-048 exception, harness_pane.py's
          header), and reads back that the session runs again.
  per account, in order, on the account's host through hostexec (units.py's
  calls; no request is sent and no relay is written)
    1  the unit is active (a stopped one is `harness-start`'s: said, nothing run)
    2  every session in the account's state record is idle, as `fabric-ctl
       states` reads it: working, blocked, unknown (no record, an old one, one
       the account cannot read) and none (no session: a dormant account is not
       one to wake) all refuse, and nothing has been stopped
    3  the server's MainPID is read, to tell the new server from the old
    4  the marker is written BY THE ACCOUNT (`sudo -u <login> fabric-python
       <its checkout>/harness_pane.py mark-resume`): nothing of this verb ever
       writes into another login's home. It is written before the stop so that
       a marker that cannot be written leaves the unit running
    5  stop, read back by is-active; start, read back by is-active and a new,
       non-zero MainPID
    6  presence (`fabric-ctl <login> presence`, the account's own agent): a
       session whose claude started after step 3, within RESUME_WAIT_S. A
       presence that does not answer, or answers a session that began before
       the restart, is a failed row, never a pass
  rows    {"login", "state", "detail"}, one line each (--json) or a table
            restarted  all of the above held
            refused    step 1 or 2: nothing was stopped
            failed     any later step, or a call that gave no usable answer; the
                       detail names the step and what was already done
            skipped    this session's own account, unless --include-self
            not-run    after a failed row: `all` stops at the first failure
  exit    0 every row restarted or skipped; 1 any other row; 2 a refusal of the
          command line (an unknown or human login, this session's own account
          named without --include-self) with nothing run. A refused row does not
          stop `all`: it left its account as it was, and the next one may be idle.
  --timeout bounds each host call and each probe, not the run.
"""
from __future__ import annotations

import calendar
import re
import time
from typing import Any, Callable

from control import units
from control.units import Run, StepFailed

OP = units.RESTART_OP
PANE_STEP = "/usr/local/bin/fabric-python"
# The account's own checkout, where the unit's ExecStartPost already runs the same file from (%h/projects/agent-fabric).
PANE_FILE = "projects/agent-fabric/tools/fabric/control/harness_pane.py"
# The server forks at once; the pane step waits for it (30 s), types (up to 80 s of its own budget) and fabric-resume then
# starts claude. Generous on purpose: a read-back that gives up early fails a restart that worked.
RESUME_WAIT_S = 240
POLL_S = 5
# claude's start time is the process table's, in whole seconds of the host's clock, read through the account's agent; this
# side's clock is another machine's possibly. Slack for both, small against a restart's tens of seconds.
CLOCK_SLACK_S = 5

Probe = Callable[[str], dict]


def iso_seconds(value: Any) -> float | None:
    """Seconds since the epoch of an ISO-8601 UTC time with optional fraction and a Z; anything else is None."""
    m = re.fullmatch(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(\.\d+)?Z", value) if isinstance(value, str) else None
    if not m:
        return None
    try:
        return calendar.timegm(time.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S")) + float(m.group(2) or 0)
    except ValueError:
        return None


def home_of(run: Run, host: str, login: str, timeout: float) -> str:
    rc, out, err = units._call(run, host, ["getent", "passwd", login], timeout, "getent passwd")
    fields = out.strip().split(":")
    if rc != 0 or len(fields) != 7 or not fields[5].startswith("/"):
        raise StepFailed(f"no home for {login} on {host}: {units._say(err) or units._say(out) or f'exit {rc}'}")
    return fields[5]


def main_pid(run: Run, host: str, login: str, uid: int, timeout: float) -> int:
    rc, out, err = units.systemctl(run, host, login, uid, "show", timeout, units.HARNESS_UNIT, ("--property=MainPID", "--value"))
    word = out.strip()
    if rc != 0 or not word.isdigit():
        raise StepFailed(f"MainPID unreadable: {units._say(err) or units._say(out) or f'exit {rc}'}")
    return int(word)


def write_marker(run: Run, host: str, login: str, home: str, timeout: float) -> None:
    argv = ["sudo", "-n", "-u", login, PANE_STEP, f"{home}/{PANE_FILE}", "mark-resume"]
    rc, out, err = units._call(run, host, argv, timeout, "mark-resume")
    if rc != 0:
        raise StepFailed(f"mark-resume exit {rc}: {units._say(err) or units._say(out) or 'no output'}")


def one(placed: dict, run: Run, timeout: float, *, states_of: Probe, presence_of: Probe,
        sleep: Callable[[float], None] = time.sleep, now: Callable[[], float] = time.time) -> dict:
    login, host = placed["login"], placed["host"]
    row = lambda state, detail="": {"login": login, "state": state, "detail": detail}  # noqa: E731
    done = "nothing was stopped"
    try:
        if not units.LOGIN.fullmatch(login):
            raise StepFailed(f"{login!r} is not a login name")
        uid = units.user_uid(run, host, login, timeout)
        unit_state = units.is_active(run, host, login, uid, timeout, units.HARNESS_UNIT)
        if unit_state != "active":
            return row("refused", f"the harness unit is {unit_state}, not active (harness-start starts it); {done}")
        seen = states_of(login)
        if seen.get("state") != "idle":
            why = f" ({seen['why']})" if seen.get("why") else ""
            return row("refused", f"sessions are {seen.get('state', 'unknown')}, not idle{why}; {done}")
        pid_before = main_pid(run, host, login, uid, timeout)
        home = home_of(run, host, login, timeout)
        write_marker(run, host, login, home, timeout)
        done = "the resume marker is written, the unit was not stopped"
        began = now()
        units._act(run, host, login, uid, "stop", timeout, units.HARNESS_UNIT)
        after = units.is_active(run, host, login, uid, timeout, units.HARNESS_UNIT)
        if after not in units.STOPPED_STATES:
            raise StepFailed(f"is-active reads {after} after stop")
        done = "the unit is stopped, not started"
        units._act(run, host, login, uid, "start", timeout, units.HARNESS_UNIT)
        sleep(units.SETTLE_S)
        after = units.is_active(run, host, login, uid, timeout, units.HARNESS_UNIT)
        if after != "active":
            raise StepFailed(f"is-active reads {after} after start")
        pid_after = main_pid(run, host, login, uid, timeout)
        if pid_after in (0, pid_before):
            raise StepFailed(f"the server is not new (MainPID {pid_after}, was {pid_before})")
        done = f"the unit runs a new server (MainPID {pid_after}), no session read back"
        waited_until = now() + RESUME_WAIT_S
        last = "no answer yet"
        while True:
            p = presence_of(login)
            since = iso_seconds(p.get("since"))
            if p.get("status") == "ok" and p.get("online") is True and since is not None and since >= began - CLOCK_SLACK_S:
                return row("restarted", f"new server (MainPID {pid_after}); session running since {p['since']}")
            last = (f"presence {p.get('status')}: {p.get('error')}" if p.get("status") != "ok" else
                    "no session" if p.get("online") is not True else f"a session since {p.get('since')}, before the restart")
            if now() >= waited_until:
                raise StepFailed(f"no new session within {RESUME_WAIT_S} s ({last})")
            sleep(POLL_S)
    except StepFailed as e:
        return row("failed", f"{e}; {done}")


def run_all(expected: list[dict], *, run: Run, me: str | None, include_self: bool = False, timeout: float = units.STEP_TIMEOUT_S,
            states_of: Probe, presence_of: Probe, sleep: Callable[[float], None] = time.sleep,
            now: Callable[[], float] = time.time) -> list[dict]:
    rows: list[dict] = []
    failed = ""
    for placed in expected:
        login = placed["login"]
        if failed:
            rows.append({"login": login, "state": "not-run", "detail": f"{failed} failed before it"})
        elif login == me and not include_self:
            rows.append({"login": login, "state": "skipped", "detail": "this session's own account (--include-self restarts it)"})
        else:
            rows.append(one(placed, run, timeout, states_of=states_of, presence_of=presence_of, sleep=sleep, now=now))
            if rows[-1]["state"] == "failed":
                failed = login
    return rows


def ok(rows: list[dict]) -> bool:
    return all(r["state"] in ("restarted", "skipped") for r in rows)
