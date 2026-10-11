"""tools/fabric/control/restart.py — the control agent's `restart` ACTION: stop
the account's running session the way an upgrade does, so its launcher brings
it back, resumed, on the fabric as it is now (ADR-009, ADR-029 rules 3, 5, 12).

Nothing else can: `secrets-sync --restart` restarts only on a token change,
`upgrade claude` only on a version change, and a SIGTERM from outside leaves
the pane at a shell, because the launcher resumes only after a restart marker
it finds. This writes that marker, already done (nothing is left to wait for),
then SIGTERMs the session — never harder; a session that does not stop is a
failure to report, not to force.

THE REPLY, data["restart"], one of:
  restarted   a session was stopped; its launcher resumes it ("pids" names them)
  no-session  none was running; nothing was written
  yours       the sessions are the requester's own: it is waiting for this
              reply, so it is never stopped — it relaunches itself
  failed      with a `reason`: pgrep could not tell, an upgrade or a
              secrets-sync is running, or a session did not stop in time (our
              marker is removed, so it is not resumed long after)
  refused     the arguments are not the empty set (`reason`)
  busy        a restart is already running on this account

The arguments are a closed set: none. Nothing from a request reaches a shell.

The marker and the session list are control/upgrade.py's (`write_marker`,
`session_pids`); its `claim_restart` makes an upgrade on the account busy while
this runs. Two restarts are kept apart by `_restarting` here, and `running()`
lets secrets-sync refuse beside one. The requester test is the one secrets-sync
makes: the request's sender is this account's own address.
"""
from __future__ import annotations

import os
import signal
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from control.ops import util
from control.upgrade import STOP_WAIT_MS

# The stop wait plus the pgrep and write around it: what fabric-ctl waits for one account's reply.
RESTART_BUDGET_S = STOP_WAIT_MS / 1000 + 30

# One restart per account at a time.
_restarting = threading.Lock()


def running() -> bool:
    """A restart is running on this account (secrets-sync refuses to stop sessions beside it)."""
    return _restarting.locked()


def check_args(args: Any) -> str | None:
    if args is None or args == {}:
        return None
    return "restart takes no arguments"


def restart(request: dict, **opts: Any) -> dict:
    if not _restarting.acquire(blocking=False):
        return {"status": "busy", "note": "a restart is already running on this account"}
    try:
        return restart_once(request, **opts)
    finally:
        _restarting.release()


def restart_once(request: dict, *, me: str | None = None, directory: str | None = None,
                 sessions: list[int] | None = None, pgrep: Callable[..., Any] | None = None,
                 syncing: Callable[[], bool] | None = None,
                 kill: Callable[[int, int], None] = os.kill, alive: Callable[[int], bool] | None = None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
                 stop_wait_ms: int | None = None, now: Callable[[], datetime] | None = None) -> dict:
    from control import secrets as sec, upgrade as up
    bad = check_args(request["args"] if "args" in request else {})
    if bad:
        return {"status": "refused", "reason": bad}
    # The hold is taken before anything slow (pgrep can take 30 s), atomically with the upgrade test: an
    # upgrade arriving after this is told busy. Our flag is up before the secrets-sync test, theirs before
    # their restart test, so two that start together both refuse, never both stop the session.
    if not up.claim_restart():
        return {"status": "failed", "reason": "an upgrade is running on this account (it owns the restart marker); nothing stopped"}
    try:
        return _stop(request, up, sec, me=me, directory=directory, sessions=sessions, pgrep=pgrep, syncing=syncing, kill=kill,
                     alive=alive, sleep=sleep, clock=clock, stop_wait_ms=stop_wait_ms, now=now)
    finally:
        up.restart_in_flight(False)


def _stop(request, up, sec, *, me, directory, sessions, pgrep, syncing, kill, alive, sleep, clock, stop_wait_ms, now) -> dict:
    if (syncing or sec.sync_running)():
        return {"status": "failed", "reason": "a secrets-sync is running on this account; nothing stopped"}
    try:
        running = sessions if sessions is not None else up.session_pids(**({"run": pgrep} if pgrep else {}))
    except Exception as e:  # noqa: BLE001 — pgrep missing, timed out or unreadable all mean "cannot tell"
        return {"status": "failed", "reason": f"could not tell whether a session is running "
                                              f"(pgrep: {util.node_error(e, ['pgrep'])[:120]}); nothing stopped"}
    if not running:
        return {"status": "no-session"}
    # The requester's own session is waiting for this reply; stopping it would lose the answer. The
    # requester is on this account when its address is ours (the test secrets-sync makes).
    if me and request.get("from") == me:
        return {"status": "yours", "note": "the sessions here are the requester's own: relaunch it yourself"}
    directory = directory or util.state_dir()
    wait_ms = up.STOP_WAIT_MS if stop_wait_ms is None else stop_wait_ms
    alive = alive or up._alive
    now = now or (lambda: datetime.now(timezone.utc))
    # The launcher reads the marker when the session returns: written first, and done already.
    up.write_marker(directory, {
        "request_id": request.get("id"), "requested_at": now().isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "piece": "the session", "from": "-", "to": "-", "installed": "-", "pids": running, "status": "done"})
    for pid in running:
        try:
            kill(pid, signal.SIGTERM)
        except OSError:
            pass   # gone
    until = clock() + wait_ms / 1000
    while any(alive(p) for p in running) and clock() < until:
        sleep(0.5)
    left = [p for p in running if alive(p)]
    if left:
        # Only our marker goes (an upgrade may have written its own since), or the session would be
        # resumed the moment it is ended on purpose, long after this action.
        marker = up.marker_path(directory)
        written = util.read_json(marker)
        if isinstance(written, dict) and written.get("request_id") == request.get("id"):
            try:
                os.unlink(marker)
            except FileNotFoundError:
                pass
        return {"status": "failed", "reason": f"the session (pid {', '.join(map(str, left))}) did not stop within "
                                               f"{round(wait_ms / 1000)} s; nothing forced — run it again, or relaunch it"}
    return {"status": "restarted", "pids": running}
