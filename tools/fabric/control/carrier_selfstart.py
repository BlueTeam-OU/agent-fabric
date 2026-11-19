"""tools/fabric/control/carrier_selfstart.py — `gzcoord-carrier self-start`: the account's own login starts its own
carrier and daemon units, with no operator's signature (agent-fabric ADR-064 §5 rule 14, A 2026-11-18). The one
start an account makes itself; install, update, restart and stop stay control-plane actions.

THE CONDITIONS, all of them, else a refusal that touches nothing (no unit, no file, no mark):
  1. the account's one install/start/stop lock (ADR-029 rule 12) is free: it never runs beside a signed action;
  2. no failure mark of an earlier self-start stands (carrier_install.SELFSTART_MARK);
  3. both units are inactive or failed (control/units.STOPPED_STATES): a unit that is activating, systemd's
     auto-restart included, counts as running, and a state the manager does not say is not a stopped one;
  4. both units are enabled: `systemctl --user is-enabled` prints exactly `enabled` (the owner's decision,
     2026-11-19: `enabled-runtime`, `linked`, `static`, `indirect`, `alias`, `generated`, `masked`, `disabled`, an
     unreadable answer and the rest all refuse). A signed stop, a drill and a failed signed start leave the
     units disabled; a crash and an upgrade's restart leave them enabled, so only what fell over is restarted and an
     operator's stop is never undone;
  5. the installed programs print what release.json pins (the signed start's check);
  6. the profile's config.yaml exists: this command renders none, and a daemon without one cannot come up, so
     the start would only write a mark (an addition to the rule's list, a refusal where the rule would fail).

THE START, under the lock: the failure mark is written first, `systemctl --user start` the daemon unit, then the
client unit (neither `enable` nor `disable` is ever run: each unit stays as it was), then the signed start's own
channel check (carrier_install.channel_check, polled the same way). On a pass the mark is removed. On a failure the
units this command started are stopped (the client first) and the mark stays, so does it when the command is
killed in between: only a signed install, start or stop removes it (carrier_install.clear_selfstart_mark), which
keeps the account off the channel until an operator acts and never starts a broken carrier again and again.

THE REPLY, a dict: status "started" | "refused" | "failed"; reason on the last two; units (unit -> state) once
anything was read; on a failure `check`, `stopped` (whether both units are inactive now) and `mark` (the path).
"""
from __future__ import annotations

import errno
import json
import os
import subprocess
import time
from typing import Any, Callable

from control import opsutil as util
from control import carrier_install as ci
from control.units import STOPPED_STATES

ENABLED = "enabled"


def unit_enabled(unit: str, run: Callable[..., Any], home: str) -> str | None:
    """The word `is-enabled` prints, or None when it printed none or could not be run. The status is not read: it is
    non-zero for every word but the enabled ones, and what the word is, is the question. A manager that does not
    answer in time raises ChannelUnknown."""
    try:
        r = run(["systemctl", "--user", "is-enabled", unit], capture_output=True, encoding="utf-8", errors="replace",
                timeout=ci.SYSTEMCTL_TIMEOUT_S, check=False, stdin=subprocess.DEVNULL, cwd="/", env=ci.child_env(home))
    except subprocess.TimeoutExpired:
        raise ci.ChannelUnknown(f"the user manager did not answer within {ci.SYSTEMCTL_TIMEOUT_S} s") from None
    except OSError:
        return None
    lines = (r.stdout or "").splitlines()
    return lines[0].strip() or None if lines else None


def _write_mark(state: str, body: dict) -> None:
    os.makedirs(state, mode=0o700, exist_ok=True)
    tmp = os.path.join(state, f".{ci.SELFSTART_MARK}.{os.getpid()}.tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(body, indent=2) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, os.path.join(state, ci.SELFSTART_MARK))
        ci._fsync_dir(state)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def carrier_selfstart(root: str | None = None, home: str | None = None, state: str | None = None,
                      run: Callable[..., Any] = subprocess.run, machine: str | None = None,
                      sleep: Callable[[float], None] = time.sleep) -> dict:
    root = ci._code_root() if root is None else root
    home = os.path.expanduser("~") if home is None else home
    state = util.state_dir() if state is None else state
    try:
        _, build = ci.pinned_build(ci.load_pin(root), machine)
        profile = ci.roster_profile(root)
    except (ci.PinError, ci.InstallError) as e:
        return ci._refused(f"{e}; nothing was started")
    fd, busy = ci._lock(state)
    if fd is None:
        return busy or ci._refused(ci.LOCK_BUSY)
    try:
        return _selfstart(build, profile, root, home, state, run, sleep)
    finally:
        os.close(fd)


def _selfstart(build: dict, profile: str, root: str, home: str, state: str, run: Callable[..., Any],
               sleep: Callable[[float], None]) -> dict:
    refuse = lambda why, units=None: {**ci._refused(f"{why}; nothing was started"), **({"units": units} if units else {})}  # noqa: E731
    mark = os.path.join(state, ci.SELFSTART_MARK)
    if os.path.lexists(mark):
        return refuse(f"an earlier self-start failed or was interrupted ({mark} stands); an operator's signed "
                      f"{ci.INSTALL_OP}, {ci.START_OP} or {ci.STOP_OP} clears it")
    daemon, client = ci.unit_names(profile)
    both = [daemon, client]
    try:
        states = {u: ci.unit_state(u, run, home) for u in both}
        if None in states.values():
            return refuse("the user manager does not answer, so whether the units are down is not known")
        up = [f"{u} is {st}" for u, st in states.items() if st not in STOPPED_STATES]
        if up:
            return refuse(f"the units are not both down ({', '.join(up)})", states)
        words = {u: unit_enabled(u, run, home) for u in both}
    except ci.ChannelUnknown as e:
        return refuse(f"whether the units are down is not known ({e})")
    off = [f"{u} reads {w!r}" if w else f"{u} gave no answer" for u, w in words.items() if w != ENABLED]
    if off:
        return refuse(f"both units must be enabled ({', '.join(off)}); a unit an operator stopped is not this command's to start", states)
    bad = ci.check_reports(ci.bin_dir(home), build["reports"], run, home)
    if bad:
        return refuse(f"the installed programs are not the pin's ({bad}); an operator runs {ci.INSTALL_OP}", states)
    if not os.path.isfile(ci.config_path(home, profile)):
        return refuse(f"{ci.config_path(home, profile)} does not exist and this command renders none; an operator runs {ci.START_OP}", states)
    try:
        _write_mark(state, {"state": "started", "at": _iso_now(), "pid": os.getpid()})
    except OSError as e:
        return refuse(f"the failure mark cannot be written ({errno.errorcode.get(e.errno or 0) or e})", states)
    problem = None
    for u in both:
        problem = ci._systemctl(["start", u], run, home)
        if problem:
            break
    check = ({"status": "failed", "reason": problem, "units": {}} if problem
             else ci.channel_check(profile, both, build, root, run, home, sleep, status_polls=ci.STARTUP_STATUS_POLLS))
    if check["status"] == "passed":
        try:
            os.unlink(mark)
        except OSError as e:
            return {"status": "failed", "units": check["units"], "check": check, "mark": mark,
                    "reason": f"the units run and the check passed, but the mark {mark} could not be removed ({errno.errorcode.get(e.errno or 0) or e})"}
        return {"status": "started", "units": check["units"], "check": "passed"}
    why = f"the {ci.CARRIER_LABEL} units did not come up ({ci._channel_text(check)})"
    stop_problems = [p for p in (ci._systemctl(["stop", u], run, home) for u in (client, daemon)) if p]
    after, still = ci._settled(both, run, home, sleep)
    stopped = not stop_problems and not still
    try:
        _write_mark(state, {"state": "failed", "at": _iso_now(), "reason": why[:300]})
    except OSError:
        pass        # the mark written before the start stands
    return {"status": "failed", "units": after, "check": check, "mark": mark, "stopped": stopped,
            "reason": why + ("; both units are stopped, as enabled as they were" if stopped
                             else f"; stopping them failed ({'; '.join(stop_problems) or still}): the units may still run")
            + f"; {mark} stands until an operator's signed {ci.INSTALL_OP}, {ci.START_OP} or {ci.STOP_OP}"}
