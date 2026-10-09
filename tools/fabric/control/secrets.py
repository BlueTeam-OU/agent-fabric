"""tools/fabric/control/secrets.py — the control agent's second ACTION:
re-sync this account's secrets from its own store (ADR-038; bin/fabric-secrets
sync), so a change the coordinator made to the login's store — which Claude
account it runs on (`fabric-accounts assign`, ADR-031) — reaches the account
without anyone logging in to it. The port of runtime/control/secrets.mjs
(ADR-040 Wave 8); the reply is frozen with the wire.

An action, signed, for the same reason `upgrade` is: it changes what the
account's next session runs on. What it applies is whatever the login's own
store says, opened with the login's own key; the request only says what to
expect and whether to act on it now:

  expect   the fingerprint the coordinator's template holds. The synced
           token must match it, or the sync is a failure: a move the
           account did not take is said by the account, not assumed.
  restart  a running session not already on the token — read from its own
           environment, not from the record; a broker session holds none by
           design and is left alone — is stopped (SIGTERM, never harder) and
           its launcher resumes it on the new sign-in: the upgrade's restart
           marker, written already done, so nothing is left to wait for. A
           restart asked for and not done is a failed reply. The requester's
           own session is never stopped (it is waiting for the reply).
           Without it a running session keeps the sign-in it started with,
           and the reply says it needs a relaunch.

So a move is messages end to end: `fabric-accounts assign` writes the
reference, and every account applies, verifies and restarts by itself. What
comes back names the sign-in by fingerprint, never by value.

The upgrade's restart machinery (the marker, the session list, the guard
against two restarts) is control/upgrade.py's, python-dev-03's; it is
reached through `upgrade()` so this module imports without it.
"""
from __future__ import annotations

import os
import re
import signal
import subprocess
import threading
import time
from typing import Any, Callable, Mapping

from control.ops import util
from gzcoord.inbox_parts.tokens import synced_var  # noqa: E402 — control.ops.util puts tools/fabric on sys.path

SYNC_TIMEOUT_S = 120
_SHA12 = re.compile(r"[0-9a-f]{12}")
_ARG_KEYS = ("expect", "restart")

# fabric-secrets sync's exit codes: 0 applied, 2 applied with names missing in
# the store (the env file is still written), 1 the store unreadable, 3 the
# store names another login. Only the first two changed anything.
_APPLIED = (0, 2)

# The Node's busy flag was one per daemon; a thread lock is the same here.
_syncing = threading.Lock()


def upgrade() -> Any:
    from control import upgrade as module   # python-dev-03's port
    return module


def check_args(args: Any) -> str | None:
    if not isinstance(args, dict):
        return "secrets-sync takes { expect, restart }"
    extra = [k for k in args if k not in _ARG_KEYS]
    if extra:
        return f"secrets-sync takes only expect and restart, not {', '.join(extra)}"
    # Present and null is refused, as the Node's String(null) was not a fingerprint.
    if "expect" in args and not (isinstance(args["expect"], str) and _SHA12.fullmatch(args["expect"])):
        return "expect is a 12-hex fingerprint"
    if "restart" in args and not isinstance(args["restart"], bool):
        return "restart is true or false"
    return None


def session_env(pid: int, env_of: Callable[[int], bytes | str] | None = None) -> dict[str, str | None]:
    """A running session's own environment says what it runs on: the token (the
    launcher exports it before the harness execs) and the provider the launcher
    stamped, both readable by this daemon — same uid. The session, not the
    record, says whether it is already on the account: a record synced earlier
    under a session that was never restarted must not read as "already on it"
    (review of #37). A broker session holds no Claude account by design — the
    launcher removes the token — so it is never "not on" one: restarting it
    would bring it back just as tokenless, on every run (re-review of #37). A
    session without the stamp is taken as plain claude, the only path a token
    reaches."""
    if env_of is None:
        with open(f"/proc/{pid}/environ", "rb") as fh:
            raw: bytes | str = fh.read()
    else:
        raw = env_of(pid)
    out: dict[str, str | None] = {"token": None, "provider": None}
    for kv in util.decode(raw if isinstance(raw, bytes) else raw.encode("utf-8")).split("\0"):
        if kv.startswith("CLAUDE_CODE_OAUTH_TOKEN="):
            out["token"] = kv[len("CLAUDE_CODE_OAUTH_TOKEN="):] or None
        elif kv.startswith("AGENT_FABRIC_LAUNCH_PROVIDER="):
            out["provider"] = kv[len("AGENT_FABRIC_LAUNCH_PROVIDER="):] or None
    return out


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True   # exists, not ours to signal


def secrets_sync(request: Mapping[str, Any], **opts: Any) -> dict:
    """One secrets-sync at a time per daemon."""
    if not _syncing.acquire(blocking=False):
        return {"status": "busy", "note": "a secrets-sync is already running on this account"}
    try:
        return secrets_sync_once(request, **opts)
    finally:
        _syncing.release()


def _sync_run(root: str, run: Callable[..., Any]) -> tuple[int, str]:
    """(exit code, stdout); -1 where the command did not run to an exit."""
    cmd = [os.path.join(root, "bin", "fabric-secrets"), "sync", "--json"]
    try:
        r = run(cmd, capture_output=True, timeout=SYNC_TIMEOUT_S, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise _NotRun(f"fabric-secrets: {util.node_error(e, cmd)[:160]}") from e
    # A negative status is a signal: no exit code, as the Node's `code` was null.
    return (r.returncode if r.returncode >= 0 else -1), util.decode(r.stdout)


class _NotRun(Exception):
    pass


def secrets_sync_once(
    request: Mapping[str, Any], *, home: str | None = None, root: str | None = None,
    run: Callable[..., Any] = subprocess.run, sessions: list[int] | None = None, me: str | None = None,
    directory: str | None = None, now: Callable[[], Any] | None = None,
    kill: Callable[[int, int], None] = os.kill, alive: Callable[[int], bool] = _alive,
    sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
    stop_wait_ms: int | None = None, env_of: Callable[[int], bytes | str] | None = None,
    upgrading: Callable[[], bool] | None = None, pgrep: Callable[..., Any] | None = None,
) -> dict:
    from datetime import datetime, timezone
    home = os.path.expanduser("~") if home is None else home
    root = root or os.environ.get("AGENT_FABRIC_ROOT") or os.path.join(home, "projects", "agent-fabric")
    now = now or (lambda: datetime.now(timezone.utc))
    args = request["args"] if "args" in request else {}   # present and null is refused, absent is nothing
    bad = check_args(args)
    if bad:
        return {"status": "refused", "reason": bad}
    expect = args.get("expect")
    restart = args.get("restart", False)
    try:
        code, out = _sync_run(root, run)
    except _NotRun as e:
        return {"status": "failed", "reason": str(e)}
    report: dict = {}
    try:
        parsed = util.loads(out)
        report = parsed if isinstance(parsed, dict) else {}
    except ValueError:
        pass   # the reason below says so
    if code not in _APPLIED:
        return {"status": "failed", "reason": str(report.get("error") or f"fabric-secrets sync exited {code}")[:200]}
    tok = synced_var("CLAUDE_CODE_OAUTH_TOKEN", home)
    sign: dict[str, str] = ({"via": "setup-token", "token_sha256_12": util.sha12(tok)} if tok
                            else {"via": "none: its next session is refused"})
    missing = {"missing": report["missing"]} if isinstance(report.get("missing"), list) and report["missing"] else {}

    def fail(reason: str) -> dict:
        return {"status": "failed", "claude_sign_in": sign, **missing, "reason": reason}

    if expect and sign.get("token_sha256_12") != expect:
        held = f"setup-token {sign['token_sha256_12']}" if sign.get("token_sha256_12") else "no token"
        return fail(f"the synced record holds {held}, not the expected {expect}; nothing restarted")
    # No token is nothing to move to: the launcher would refuse the resume.
    if restart and not tok:
        return fail("the synced record holds no token; nothing stopped")
    try:
        running = sessions if sessions is not None else upgrade().session_pids(**({"run": pgrep} if pgrep else {}))
    except ImportError:
        raise   # control.upgrade not there is not a pgrep that failed
    except Exception as e:  # noqa: BLE001 — pgrep missing, timed out or unreadable all mean "cannot tell"
        why = f"could not tell whether a session is running (pgrep: {util.node_error(e, ['pgrep'])[:120]})"
        if restart:
            return fail(f"{why}; nothing restarted")
        return {"status": "synced", "claude_sign_in": sign, **missing, "session": "unknown", "reason": why}

    def done(session: str) -> dict:
        return {"status": "synced", "claude_sign_in": sign, **missing, "session": session}

    if not running:
        return done("none")
    envs: dict[int, dict | None] = {}
    for pid in running:
        try:
            envs[pid] = session_env(pid, env_of)
        except OSError:
            envs[pid] = None
    broker = [p for p in running if envs[p] and envs[p]["provider"] and envs[p]["provider"] != "anthropic"]

    def token_of(p: int) -> str | None:
        return envs[p]["token"] if envs[p] else None

    stale = [p for p in running if p not in broker
             and not ((t := token_of(p)) and tok and util.sha12(t) == util.sha12(tok))]
    if not stale:
        return done("running (broker): no Claude account to move" if len(broker) == len(running)
                    else "running, already on it")
    if me and request.get("from") == me:
        return done("yours: relaunch to use it")
    if not restart:
        return done("running: relaunch to use it")
    up = upgrade()
    if (upgrading or up.upgrade_running)():
        return fail("an upgrade is running on this account (it owns the restart marker); synced, nothing stopped — run it again after")
    directory = directory or util.state_dir()
    wait_ms = up.STOP_WAIT_MS if stop_wait_ms is None else stop_wait_ms
    up.restart_in_flight(True)
    try:
        # The launcher reads the marker when the session returns: written first,
        # and done already, so it resumes at once on what was synced.
        before = token_of(stale[0])
        up.write_marker(directory, {
            "request_id": request.get("id"), "requested_at": now().isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "piece": "the Claude account", "from": f"setup-token {util.sha12(before)}" if before else "no token",
            "to": f"setup-token {sign['token_sha256_12']}", "installed": f"setup-token {sign['token_sha256_12']}",
            "pids": stale, "status": "done"})
        for pid in stale:
            try:
                kill(pid, signal.SIGTERM)
            except OSError:
                pass   # gone
        until = clock() + wait_ms / 1000
        while any(alive(p) for p in stale) and clock() < until:
            sleep(0.5)
        left = [p for p in stale if alive(p)]
        if left:
            # Not stopped: our marker goes (only ours — an upgrade may have written
            # its own since), or the session would be resumed the moment it is ended
            # on purpose, long after this action.
            marker = up.marker_path(directory)
            written = util.read_json(marker)
            if isinstance(written, dict) and written.get("request_id") == request.get("id"):
                try:
                    os.unlink(marker)
                except FileNotFoundError:
                    pass
            return fail(f"synced, but the session (pid {', '.join(map(str, left))}) did not stop within "
                        f"{round(wait_ms / 1000)} s; nothing forced — run it again, or relaunch it")
        return done("restarting")
    finally:
        up.restart_in_flight(False)
