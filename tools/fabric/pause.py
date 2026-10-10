#!/usr/bin/env python3
"""tools/fabric/pause.py — fabric-pause: pause agents before a host restart,
through the control plane only (ADR-029), never through another account's
files or `fabric-host run --as`.

    fabric-pause <login…|--project P|--all> [--dry-run]

For each login it decides PAUSE or REFUSE from what the control agents
report, and prints one line per login:

    <login>  pause|idle|refuse  <why>

REFUSED, with the reason named, when the login:
  * has a job in state `active` (a job blocked for another reason, or queued,
    does not refuse it; the 2026-10-09 pause blocked the active ones first);
  * has a session that is planning (a plan awaits approval);
  * did not answer, or answered a jobs/presence read that failed: unknown is
    never read as "nothing to lose".
IDLE when it has no session running: nothing to signal.

WHAT THE CONTROL AGENTS CANNOT YET SAY (the coordinator's decision of
2026-10-10, j7): nothing reports whether a login's working copies hold
uncommitted or unpushed work, and no operation signals a session. `session`
returns a count and no pid leaves an account (control/sessions.py), so a
by-pid signal from here is impossible; the control agent must signal its own
login's `claude` processes itself. Until the read operation `workcopies` and
the signed action `pause` exist (tools/fabric/control, after Wave 8's s8), every
PAUSE line says `working copies unchecked`, and without --dry-run nothing is
signalled: the passed logins are printed and the exit is 2, so the operator
sends the SIGTERM as on 2026-10-09. When `signal_login` is replaced by a call
to the action, a signalled login is read back with `presence` until it shows
no session.

Exit: 0 every login ended without a session (--dry-run: none refused);
1 a refusal, a login that stayed up, or an answer that could not be read;
2 usage, or the passed logins could not be signalled (no `pause` operation).
Stdout is the table; every `fabric-pause: ` line is on stderr.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Callable

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CTL = os.path.join(ROOT, "bin", "fabric-ctl")
# fabric-ctl's own wait for the agents' replies is bounded by --timeout; the
# process gets a little longer so its own refusal text is read, not cut.
CTL_TIMEOUT_S = 30
CALL_TIMEOUT_S = CTL_TIMEOUT_S + 15
READBACK_TIMEOUT_S = 90
READBACK_EVERY_S = 3
LOGIN = re.compile(r"[a-z][a-z0-9._-]*")
USAGE = "usage: fabric-pause <login…|--project P|--all> [--dry-run]"


class PauseError(Exception):
    """The control plane could not be asked, or its answer cannot be read."""


class Unavailable(Exception):
    """No operation exists to do this yet."""


Run = Callable[[list[str], float], "subprocess.CompletedProcess[str]"]


def run_argv(argv: list[str], timeout: float) -> "subprocess.CompletedProcess[str]":
    try:
        return subprocess.run(argv, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=timeout)
    except FileNotFoundError:
        raise PauseError(f"{os.path.basename(argv[0])} not found") from None
    except subprocess.TimeoutExpired:
        raise PauseError(f"{os.path.basename(argv[0])} did not answer within {round(timeout)} s") from None
    except OSError as e:
        raise PauseError(f"{os.path.basename(argv[0])} could not run: {e.strerror or e}") from None


def signal_login(login: str) -> int:
    """SIGTERM the login's Claude Code session through its control agent. The
    `pause` action does not exist yet (see the module header)."""
    raise Unavailable("the control agent has no pause operation yet")


def last_line(text: str) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1][:200] if lines else ""


def ctl_rows(op: str, target: str, run: Run) -> dict[str, dict]:
    """`fabric-ctl <target> <op> --json`: the rows by account. A row that says
    anything but `ok` is kept, so the caller names it."""
    p = run([CTL, target, op, "--json", "--timeout", str(CTL_TIMEOUT_S)], CALL_TIMEOUT_S)
    rows: dict[str, dict] = {}
    for ln in (p.stdout or "").splitlines():
        try:
            row = json.loads(ln)
        except ValueError:
            continue
        if isinstance(row, dict) and isinstance(row.get("account"), str):
            rows[row["account"]] = row
    if not rows:
        # fabric-ctl exits non-zero WITH rows to read when an agent is silent;
        # no rows at all is a refusal, an unreadable registry or no relay.
        raise PauseError(f"fabric-ctl {target} {op}: {last_line(p.stderr) or f'exit {p.returncode}, no rows'}")
    return rows


def op_result(row: dict | None, key: str) -> tuple[dict | None, str]:
    """(the op's result, "") or (None, why it cannot be read)."""
    if row is None:
        return None, "no row for it"
    if row.get("status") != "ok":
        return None, str(row.get("status") or "no status")
    res = row.get(key)
    if not isinstance(res, dict):
        return None, "no result"
    if res.get("status") != "ok":
        err = res.get("error")
        return None, f"{res.get('status')}{': ' + str(err) if err else ''}"
    return res, ""


@dataclass
class Verdict:
    login: str
    refusals: list[str] = field(default_factory=list)
    idle: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def word(self) -> str:
        return "refuse" if self.refusals else "idle" if self.idle else "pause"

    def line(self) -> str:
        why = "; ".join(self.refusals or self.notes)
        return f"{self.login:<22} {self.word:<7} {why}".rstrip()


def judge(login: str, jobs_row: dict | None, presence_row: dict | None) -> Verdict:
    v = Verdict(login)
    jobs, why = op_result(jobs_row, "jobs")
    if jobs is None:
        v.refusals.append(f"jobs unreadable ({why})")
    else:
        listed = jobs.get("jobs")
        if not isinstance(listed, list):
            v.refusals.append("jobs unreadable (the list is not a list)")
        else:
            for j in listed:
                if not isinstance(j, dict) or not isinstance(j.get("state"), str) or not j["state"]:
                    # An entry whose state cannot be read might be the active one.
                    v.refusals.append("jobs unreadable (an entry has no state)")
                    break
                if j["state"] == "active":
                    v.refusals.append(f"active job {j.get('id')}: {str(j.get('title'))[:60]}")
    pres, why = op_result(presence_row, "presence")
    if pres is None:
        v.refusals.append(f"presence unreadable ({why})")
    else:
        if pres.get("planning") is True:
            v.refusals.append("a session is planning: a plan awaits approval")
        if pres.get("online") is not True and not v.refusals:
            v.idle = True
            v.notes.append("no session running")
    if not v.refusals and not v.idle:
        v.notes.append("working copies unchecked: no workcopies operation yet")
    return v


def parse(argv: list[str]) -> tuple[list[str], str | None, bool, bool]:
    """(logins, project, all, dry_run); exactly one way of naming the targets."""
    logins: list[str] = []
    project: str | None = None
    every = dry = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--dry-run":
            dry = True
        elif a == "--all":
            every = True
        elif a == "--project":
            if i + 1 >= len(argv) or not argv[i + 1] or argv[i + 1].startswith("-"):
                raise ValueError("--project needs a project id")
            project = argv[i + 1]
            i += 1
        elif a.startswith("-"):
            raise ValueError(f"unknown option '{a}'")
        elif a == "all":
            raise ValueError("'all' is not a login: say --all for the whole fleet")
        elif LOGIN.fullmatch(a):
            logins.append(a)
        else:
            raise ValueError(f"'{a}' is not a login")
        i += 1
    named = sum(bool(x) for x in (logins, project, every))
    if named != 1:
        raise ValueError("name logins, or --project P, or --all: one of the three")
    return logins, project, every, dry


def targets(logins: list[str], project: str | None, every: bool, run: Run) -> tuple[list[str], dict[str, str]]:
    """(the logins to judge, the ones that cannot be attributed: login -> why)."""
    if logins:
        return list(dict.fromkeys(logins)), {}
    rows = ctl_rows("presence", "all", run)
    picked: list[str] = []
    unknown: dict[str, str] = {}
    for login in sorted(rows):
        pres, why = op_result(rows[login], "presence")
        if pres is None:
            unknown[login] = f"no answer from its control agent ({why}), so nothing is known of it"
        elif every or pres.get("project") == project:
            picked.append(login)
    if project:
        # A silent account's project is unknown, and unknown is not "not this one".
        return picked, unknown
    return sorted(set(picked) | set(unknown)), unknown


def fetch(op: str, logins: list[str], whole_fleet: bool, run: Run) -> dict[str, dict]:
    if whole_fleet:
        return ctl_rows(op, "all", run)
    out: dict[str, dict] = {}
    for login in logins:
        try:
            out.update(ctl_rows(op, login, run))
        except PauseError as e:
            out[login] = {"account": login, "status": str(e)}
    return out


def read_back(login: str, run: Run, sleep: Callable[[float], None], clock: Callable[[], float]) -> tuple[bool, str]:
    """(True, "") once presence shows no session; (False, why) when the budget is spent."""
    deadline = clock() + READBACK_TIMEOUT_S
    why = "presence not read"
    while True:
        try:
            pres, why = op_result(ctl_rows("presence", login, run).get(login), "presence")
        except PauseError as e:
            pres, why = None, str(e)
        if pres is not None:
            if pres.get("online") is not True:
                return True, ""
            why = f"still has {pres.get('sessions')} session(s)"
        if clock() >= deadline:
            return False, why
        sleep(READBACK_EVERY_S)


def pause(argv: list[str], run: Run = run_argv, signal: Callable[[str], int] | None = None,
          sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> int:
    signal = signal or signal_login
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__.strip("\n"))
        return 0
    try:
        logins, project, every, dry = parse(argv)
    except ValueError as e:
        print(f"fabric-pause: {e}\n{USAGE}", file=sys.stderr)
        return 2
    try:
        picked, unknown = targets(logins, project, every, run)
        if not picked and not unknown:
            print("fabric-pause: no login matches", file=sys.stderr)
            return 1
        whole = not logins
        jobs = fetch("jobs", picked, whole, run)
        presence = fetch("presence", picked, whole, run)
    except PauseError as e:
        print(f"fabric-pause: {e}", file=sys.stderr)
        return 1
    verdicts = []
    for login in picked:
        v = judge(login, jobs.get(login), presence.get(login))
        if login in unknown and not v.refusals:
            v.refusals.append(unknown[login])
        verdicts.append(v)
    for login, why in unknown.items():
        if login not in picked:
            verdicts.append(Verdict(login, refusals=[why]))
    for v in sorted(verdicts, key=lambda x: x.login):
        print(v.line())
    refused = [v for v in verdicts if v.refusals]
    if dry:
        return 1 if refused else 0
    passed = [v.login for v in verdicts if v.word == "pause"]
    failed = bool(refused)
    stayed: list[str] = []
    for login in passed:
        try:
            signal(login)
        except Unavailable as e:
            held = f" Refused, do not restart before they are dealt with: {' '.join(v.login for v in refused)}." if refused else ""
            print(f"fabric-pause: {e}; none of the passed logins was signalled. Passed, to be signalled by the operator: "
                  f"{' '.join(passed)}.{held}", file=sys.stderr)
            return 2
        ok, why = read_back(login, run, sleep, clock)
        print(f"{login:<22} {'paused' if ok else 'still up':<7} {why or 'presence shows no session'}")
        if not ok:
            stayed.append(login)
    return 1 if failed or stayed else 0


def main() -> int:
    return pause(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
