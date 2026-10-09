"""tools/fabric/control/upgrade.py — the control agent's first ACTION: bring a
piece of the account's software to the version the fabric pins, and have a
running session come back on it (ADR-009; ADR-040 Wave 8, from
runtime/control/upgrade.mjs, which this replaces).

THE SEQUENCE, for one account:
  1. already at the pin: nothing happens, and nothing restarts;
  2. wait for the host's install lease (one account at a time, below); no
     turn, or no queue, is a failure with nothing stopped;
  3. a session running: write the restart marker the launcher reads, then
     SIGTERM its `claude` — the harness's own graceful shutdown (SessionEnd
     hooks, the transcript saved) — and wait for it to be gone; never
     SIGKILL: a session that does not stop is a failure to report, not to
     force;
  4. install the pinned version with the harness's own installer and verify
     `claude --version` says it; release the lease;
  5. mark the marker done or failed; the launcher, still in the session's
     terminal, relaunches with --resume on whatever is now installed, and
     says which.
Installing under a running session is safe (each version is its own file;
the launcher's link moves); stopping is only so the session comes back ON
the new version. The requester's own session is never stopped: it is the
one waiting for this reply — it is told to relaunch itself.

Only ever reached through a request signed by the operator's key (sign,
agentd accept). Arguments are a closed set: a piece from PIECES and a
version of digits; nothing from a request reaches a shell.

THE NAMES OTHER MODULES REACH (control/secrets.py, control/accounts.py; the
spellings were agreed with their author, seq 31763): STOP_WAIT_MS,
upgrade_running(), restart_in_flight(on), marker_path(dir),
write_marker(dir, marker), session_pids(run=…), and — in control/ctl.py,
not here — placements.

THE CONTRACT, as the Node's: the replies, their key order, the marker file
(restart.json, 0600, JSON indented by two, a newline), the one-line reasons.
Every program is run through `run`, called as subprocess.run is (an
argument list, keyword options, check=True, a timeout) so a test hands in a
fake of the same shape; failures are the real ones — CalledProcessError for
a non-zero exit, TimeoutExpired, OSError for a command that is not there.

WHERE THE PORT DIFFERS ON PURPOSE
  * The version and commit patterns are matched whole (fullmatch): Python's
    `$` would accept a trailing newline where the Node's did not.
  * The marker is chmod 0600 after it is opened, not only at creation: a
    stale restart.json.tmp that a crash left readable is not reused as is.
  * The settings refresh runs `sys.executable`, the interpreter this module
    runs on (the fleet's pinned one), not whatever `python3` the daemon's
    unit finds on its PATH.
  * `alive` treats a pid it may not signal (EPERM) as alive, where the Node
    read the exception as "gone": a process that cannot be observed has not
    been shown to have stopped.
  * Waiting for the install lease is bounded at the lease's own wait plus
    LEASE_GRACE_S: a fabric-lease that never answers is a refused lease, not
    an upgrade that never replies.
  * The lease holder's stdout and stderr pipes are closed on release.
  * An empty AGENT_FABRIC_ROOT counts as unset (roots.engine_root does the
    same), where the Node's `??` kept the empty string and read a pin from
    the working directory.

KNOWN LIMIT. The interlock with secrets-sync is a check and then a set
(`upgrade_running()` then `restart_in_flight(True)` in secrets.py): safe
while agentd runs one action at a time, as the Node's single thread did. A
daemon that runs actions on threads needs one locked test-and-set; that is
the cutover's to decide, since agentd's loop is its.
"""
from __future__ import annotations

import errno
import json
import os
import re
import selectors
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from control.ops import util
from control.ops.usage import claude_bin

PIECES = ["claude", "fabric"]
VERSION_RE = re.compile(r"\d{1,4}\.\d{1,4}\.\d{1,6}")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
STOP_WAIT_MS = 90000   # the harness's failsafe is the hook budget + 5 s
VERSION_TIMEOUT_MS = 30000
# One install per HOST at a time, across its accounts: `fabric-ctl all
# upgrade claude` makes every daemon install at once, and on 2026-09-25
# nine of thirteen concurrent installs on develop-qzapp failed where each
# alone succeeded. The host lease (bin/fabric-lease, ADR-010) queues them,
# and it is taken BEFORE the session is stopped and held until the new
# version is read back: a session is stopped only when its install can
# start, so the queue costs the operator's wait and never an account's
# downtime. The wait is sixteen accounts (develop-qzapp's count) at up to
# ~56 s a turn — the stop wait, the install and the read-back together; a
# larger host needs a longer one.
INSTALL_LEASE = "claude-install"
LEASE_WAIT_S = 900
LEASE_GRACE_S = 60
LEASE_HELD = 75   # fabric-lease's EX_TEMPFAIL: still held after the wait
INSTALL_TIMEOUT_MS = 300000
# What the launcher waits out after the session stopped: the install and its
# read-back. The launcher's restart wait (RESTART_WAIT_S in
# tools/fabric/launcher/base.py) must exceed it (the suite checks), or the
# session resumes on the old version while the install still runs.
POST_STOP_BUDGET_S = (INSTALL_TIMEOUT_MS + VERSION_TIMEOUT_MS) / 1000
# The longest an upgrade can take to reply: read the version, queue, stop the
# session, install, read it back. fabric-ctl waits this long.
UPGRADE_BUDGET_S = VERSION_TIMEOUT_MS / 1000 + LEASE_WAIT_S + STOP_WAIT_MS / 1000 + POST_STOP_BUDGET_S

FABRIC_GIT_TIMEOUT_MS = 60000
BOOTSTRAP_TIMEOUT_MS = 300000
FABRIC_UPGRADE_BUDGET_S = (3 * FABRIC_GIT_TIMEOUT_MS + BOOTSTRAP_TIMEOUT_MS) / 1000 + 30
SETTINGS_TIMEOUT_MS = 120000
PGREP_TIMEOUT_S = 30
LEASE_RELEASE_TIMEOUT_S = 30

_MISSING = object()


# ── small helpers ───────────────────────────────────────────────────

def last_line(e: Any) -> str:
    """The line that says what went wrong is the LAST one a failed command
    wrote; a subprocess error's message starts with the command line, which
    is all the first run's rows showed."""
    message = getattr(e, "message", None) or _command_failed(e) or (str(e) if isinstance(e, BaseException) else None)
    for s in (getattr(e, "stderr", None), getattr(e, "stdout", None), message):
        lines = [x.strip() for x in util.decode(s).split("\n") if x.strip()]
        if lines:
            return lines[-1]
    return "no output"


def _command_failed(e: Any) -> str | None:
    """execFile's message for a program that exited non-zero or timed out:
    `Command failed: <argv>` — the last line a failure with no output has."""
    if isinstance(e, (subprocess.CalledProcessError, subprocess.TimeoutExpired)) and e.cmd:
        return "Command failed: " + (e.cmd if isinstance(e.cmd, str) else " ".join(map(str, e.cmd)))
    return None


def _first_line(e: BaseException, cmd: list[str], limit: int) -> str:
    return util.node_error(e, cmd)[:limit]


def js_string(v: Any) -> str:
    """JavaScript's String(v), for the few shapes a request can carry."""
    if v is _MISSING:
        return "undefined"
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        if v.is_integer() and abs(v) < 1e21:
            return str(int(v))
        # Number::toString writes 1e+21 and up, and below 1e-6, with an exponent without leading zeros.
        return re.sub(r"e([+-])0*(\d)", r"e\1\2", repr(v))
    if isinstance(v, dict):
        return "[object Object]"
    if isinstance(v, list):
        return ",".join("" if x is None else js_string(x) for x in v)
    return str(v)


def _get(args: Any, key: str) -> Any:
    return args.get(key, _MISSING) if isinstance(args, dict) else _MISSING


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def default_run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess:
    kw.setdefault("check", True)
    kw.setdefault("capture_output", True)
    kw.setdefault("stdin", subprocess.DEVNULL)
    return subprocess.run(cmd, **kw)


# ── the host's install lease ────────────────────────────────────────

class LeaseRefused(Exception):
    """No turn on the lease: `code` is fabric-lease's exit status (-1 when it
    could not run or did not answer), `reason` its stable `reason=` word
    (ADR-010), `line` the prose a person reads."""

    def __init__(self, code: int, line: str, reason: str | None = None) -> None:
        super().__init__(line)
        self.code, self.line, self.reason = code, line, reason


class Lease:
    """The lease is held by a child that keeps it until its stdin closes:
    release() closes it, and a daemon that dies closes it too, so the lease
    never outlives its holder."""

    def __init__(self, child: subprocess.Popen) -> None:
        self.child = child

    def release(self) -> None:
        child = self.child
        if child.stdin and not child.stdin.closed:
            try:
                child.stdin.close()
            except OSError:
                pass   # the holder is already gone
        try:
            child.wait(timeout=LEASE_RELEASE_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
        _close_pipes(child)


def _close_pipes(child: subprocess.Popen) -> None:
    for pipe in (child.stdin, child.stdout, child.stderr):
        if pipe and not pipe.closed:
            try:
                pipe.close()
            except OSError:
                pass   # a write end that was never flushed to a holder that is gone


def hold_lease(root: str, *, spawn: Callable[..., subprocess.Popen] = subprocess.Popen, wait_s: float = LEASE_WAIT_S) -> Lease:
    """No bin/fabric-lease, or no lease directory (exit 2), is a queue that is
    unavailable — refused, not bypassed, since installing unqueued is what
    failed nine accounts."""
    cmd = [os.path.join(root, "bin", "fabric-lease"), INSTALL_LEASE, "--wait", str(wait_s), "--", "sh", "-c", "echo held; exec cat >/dev/null"]
    try:
        child = spawn(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as e:
        name = errno.errorcode.get(e.errno or 0, "")
        raise LeaseRefused(-1, f"spawn {cmd[0]} {name}".strip()) from None
    deadline = time.monotonic() + wait_s + LEASE_GRACE_S
    seen = b""
    with selectors.DefaultSelector() as sel:
        sel.register(child.stdout, selectors.EVENT_READ)
        while b"held" not in seen:
            left = deadline - time.monotonic()
            if left <= 0 or not sel.select(left):
                child.kill()
                child.wait()
                _close_pipes(child)
                raise LeaseRefused(-1, f"fabric-lease did not answer within {round(wait_s + LEASE_GRACE_S)} s")
            chunk = os.read(child.stdout.fileno(), 4096)
            if not chunk:
                break   # closed without "held": a refusal
            seen += chunk
    if b"held" in seen:
        return Lease(child)
    code = child.wait()
    err = util.decode(child.stderr.read())
    _close_pipes(child)
    # fabric-lease ends a refusal with a stable `reason=` line (ADR-010); the
    # reason is kept as data and the line a person reads is the prose above it.
    m = re.search(r"^fabric-lease: reason=(\w+)$", err, re.M)
    prose = "\n".join(line for line in err.split("\n") if not line.startswith("fabric-lease: reason="))
    raise LeaseRefused(code, last_line(_Said(prose, f"fabric-lease exited {code}")), m.group(1) if m else None)


class _Said:
    def __init__(self, stderr: str, message: str) -> None:
        self.stderr, self.message = stderr, message


# ── what the pin and the state say ──────────────────────────────────

def pin_file(root: str) -> str:
    return os.path.join(root, "runtime", "claude-code", "harness.json")


def pinned_version(root: str) -> str | None:
    try:
        with open(pin_file(root), encoding="utf-8") as fh:
            v = util.loads(fh.read()).get("claude")
    except (OSError, ValueError, AttributeError):
        return None
    return v if isinstance(v, str) and VERSION_RE.fullmatch(v) else None


def state_dir(home: str | None = None, env: dict[str, str] | None = None, login: str | None = None) -> str:
    """runtime/identity.py's agent_state_dir for an explicit home, environment
    and login (the Node's stateDir)."""
    home = os.path.expanduser("~") if home is None else home
    env = os.environ if env is None else env
    if login is None:
        import pwd
        login = pwd.getpwuid(os.getuid()).pw_name
    if env.get("AGENT_FABRIC_STATE_DIR"):
        base = os.path.abspath(env["AGENT_FABRIC_STATE_DIR"])
    else:
        base = os.path.join(env.get("XDG_STATE_HOME") or os.path.join(home, ".local", "state"), "agent-fabric")
    # path.join normalises where os.path.join does not (`..`, `//`).
    return os.path.normpath(os.path.join(base, "agents", login))


def marker_path(directory: str) -> str:
    return os.path.join(directory, "restart.json")


def write_marker(directory: str, marker: dict) -> None:
    os.makedirs(directory, exist_ok=True)
    f = marker_path(directory)
    tmp = f"{f}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(util.js_json(marker, indent=2) + "\n")
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    os.replace(tmp, f)


def _pgrep_said(e: BaseException) -> str:
    """The first line of execFileSync's message for a pgrep that failed:
    `Command failed: pgrep -u … -x claude`, `spawnSync pgrep ENOENT`."""
    said = util.node_error(e, list(getattr(e, "cmd", None) or ["pgrep"]))
    return "spawnSync " + said[len("spawn "):] if said.startswith("spawn ") else said


def _pgrep(argv: list[str]) -> str:
    return util.decode(subprocess.run(argv, capture_output=True, check=True, timeout=PGREP_TIMEOUT_S, stdin=subprocess.DEVNULL).stdout)


def session_pids(run: Callable[[list[str]], str] | None = None, uid: int | None = None, self_pid: int | None = None,
                 proc: str = "/proc") -> list[int]:
    """The account's session processes: every `claude` of this uid except the
    daemon's own children (the account observer's headless /usage runs).

    `run` takes the argument list and returns pgrep's stdout, raising
    CalledProcessError for a non-zero exit: status 1 is pgrep's "nothing
    matched" and gives []; anything else — a missing pgrep, a timeout, an
    unreadable table — propagates, since it must not read as "no session"
    (review of #34)."""
    uid = os.getuid() if uid is None else uid
    self_pid = os.getpid() if self_pid is None else self_pid
    try:
        text = (run or _pgrep)(["pgrep", "-u", str(uid), "-x", "claude"])
    except subprocess.CalledProcessError as e:
        if e.returncode == 1:
            return []
        raise
    out: list[int] = []
    for line in util.decode(text).split("\n"):
        line = line.strip()
        if not line.isdigit():
            continue
        pid = int(line)
        try:
            with open(os.path.join(proc, str(pid), "stat"), encoding="utf-8", errors="replace") as fh:
                stat_line = fh.read()
        except OSError:
            continue   # gone already
        # A stat line that does not parse has no parent to compare: the pid is
        # counted, as the Node counted it (NaN is never the daemon's pid) — a
        # live `claude` is a session until shown to be the daemon's own child.
        tail = stat_line.rsplit(") ", 1)[-1].split(" ")
        ppid = int(tail[1]) if len(tail) > 1 and tail[1].lstrip("-").isdigit() else None
        if ppid != self_pid:
            out.append(pid)
    return out


def check_args(args: Any) -> str | None:
    if not isinstance(args, (dict, list)):
        return "no arguments"
    piece = _get(args, "piece")
    if not isinstance(piece, str) or piece not in PIECES:
        return f"piece {json.dumps(js_string(piece)[:20], ensure_ascii=False)} is not one of {', '.join(PIECES)}"
    if piece == "fabric":
        if _get(args, "version") is not _MISSING:
            return "fabric takes a commit, not a version"
        if not COMMIT_RE.fullmatch(js_string(_get(args, "commit"))):
            return "commit is not a full 40-hex sha"
        return None
    if _get(args, "commit") is not _MISSING:
        return "claude takes a version, not a commit"
    version = _get(args, "version")
    if version is not _MISSING and not VERSION_RE.fullmatch(js_string(version)):
        return "version is not digits.digits.digits"
    return None


def _version(bin: str, run: Callable[..., Any]) -> str | None:  # noqa: A002
    r = run([bin, "--version"], timeout=VERSION_TIMEOUT_MS / 1000, check=True, capture_output=True, stdin=subprocess.DEVNULL)
    words = util.decode(r.stdout).strip().split()
    return words[0] if words else None


# ── one upgrade at a time per daemon ────────────────────────────────

_state = threading.Lock()
_running = False
# secrets-sync writes the same restart marker: each refuses while the other
# holds it, in both directions (re-review of #37).
_sync_restarting = False


def upgrade_running() -> bool:
    return _running


def restart_in_flight(on: bool) -> None:
    global _sync_restarting
    _sync_restarting = bool(on)


def upgrade(request: dict, **opts: Any) -> dict:
    global _running
    with _state:
        if _running:
            return {"status": "busy", "note": "an upgrade is already running on this account"}
        if _sync_restarting:
            return {"status": "busy", "note": "a secrets-sync is restarting the session on this account"}
        _running = True
    try:
        args = request.get("args")
        fabric = _get(args, "piece") == "fabric"
        return (upgrade_fabric if fabric else upgrade_once)(request, **opts)
    finally:
        with _state:
            _running = False


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True   # a process that cannot be observed has not been shown to have stopped
    return True


def _kill(pid: int, sig: int) -> None:
    os.kill(pid, sig)


def upgrade_once(request: dict, *, home: str | None = None, root: str | None = None, directory: str | None = None,
                 me: str | None = None, run: Callable[..., Any] = default_run, pgrep: Callable[[list[str]], str] | None = None,
                 kill: Callable[[int, int], None] = _kill, alive: Callable[[int], bool] = _alive,
                 sleep: Callable[[float], None] = time.sleep, now: Callable[[], datetime] | None = None,
                 clock: Callable[[], float] = time.monotonic, stop_wait_ms: float = STOP_WAIT_MS,
                 sessions: list[int] | None = None, lease: Callable[[], Lease] | None = None) -> dict:
    home = os.path.expanduser("~") if home is None else home
    root = root or os.environ.get("AGENT_FABRIC_ROOT") or os.path.join(home, "projects", "agent-fabric")
    directory = directory or state_dir(home)
    now = now or (lambda: datetime.now(timezone.utc))
    lease = lease or (lambda: hold_lease(root))
    args = request.get("args")
    args = {} if args is None else args
    bad = check_args(args)
    if bad:
        return {"status": "refused", "reason": bad}
    target = _get(args, "version")
    target = pinned_version(root) if target is _MISSING else js_string(target)
    if not target:
        return {"status": "refused", "reason": f"no pinned version in {os.path.relpath(pin_file(root), root)}"}
    bin = claude_bin(home)  # noqa: A001
    try:
        from_ = _version(bin, run)
    except (subprocess.SubprocessError, OSError) as e:
        return {"status": "failed", "piece": "claude", "to": target, "reason": f"claude --version: {_first_line(e, [bin, '--version'], 160)}"}

    def read_pids() -> list[int]:
        return list(sessions) if sessions is not None else session_pids(run=pgrep)

    def pids_failed(e: BaseException) -> dict:
        return {"status": "failed", "piece": "claude", "from": from_, "to": target,
                "reason": f"could not tell whether a session is running (pgrep: {_pgrep_said(e)[:120]}); nothing installed"}
    try:
        pids = read_pids()
    except (subprocess.SubprocessError, OSError) as e:
        return pids_failed(e)
    own = bool(me) and request.get("from") == me
    if from_ == target:
        return {"status": "current", "piece": "claude", "version": from_, "session": "running" if pids else "none"}

    try:
        held = lease()
    except LeaseRefused as e:
        return {"status": "failed", "piece": "claude", "from": from_, "to": target, "session": "running" if pids else "none",
                "reason": (f"the host's install lease ({INSTALL_LEASE}) stayed held for {LEASE_WAIT_S} s; not installed, no session stopped — run it again"
                           if e.code == LEASE_HELD else
                           f"the host's install queue is unavailable ({e.line[:160]}); not installed, no session stopped")}
    try:
        # Sessions are read again under the lease: the wait can outlast one.
        try:
            pids = read_pids()
        except (subprocess.SubprocessError, OSError) as e:
            return pids_failed(e)
        return _install_held(request, directory, bin, run, kill, alive, sleep, now, clock, stop_wait_ms, from_, target, pids, own, root, home)
    finally:
        held.release()


def _install_held(request, directory, bin, run, kill, alive, sleep, now, clock, stop_wait_ms, from_, target, pids, own, root, home) -> dict:  # noqa: A002
    stop = bool(pids) and not own
    # JSON.stringify drops a key whose value is undefined: a request with no id has no request_id.
    marker = {**({"request_id": request["id"]} if "id" in request else {}), "requested_at": iso(now()), "piece": "claude", "from": from_, "to": target,
              "pids": pids, "status": "pending"}
    if stop:
        write_marker(directory, marker)
        for pid in pids:
            try:
                kill(pid, signal.SIGTERM)
            except OSError:
                pass   # gone
        until = clock() + stop_wait_ms / 1000
        while any(alive(p) for p in pids) and clock() < until:
            sleep(0.5)
        if any(alive(p) for p in pids):
            write_marker(directory, {**marker, "status": "failed", "reason": "the session did not stop"})
            left = ", ".join(str(p) for p in pids if alive(p))
            return {"status": "failed", "piece": "claude", "from": from_, "to": target,
                    "reason": f"the session (pid {left}) did not stop within {round(stop_wait_ms / 1000)} s; not installed, nothing forced"}
    installed: str | None = None
    reason: str | None = None
    try:
        run([bin, "install", target], timeout=INSTALL_TIMEOUT_MS / 1000, check=True, capture_output=True, stdin=subprocess.DEVNULL)
        installed = _version(bin, run)
        if installed != target:
            reason = f"after install, claude --version says {installed}"
    except subprocess.TimeoutExpired:
        reason = f"claude install {target}: timed out after {INSTALL_TIMEOUT_MS // 1000} s"
    except (subprocess.SubprocessError, OSError) as e:
        reason = f"claude install {target}: {_failure_line(e, [bin, 'install', target])[:200]}"
    ok = reason is None
    # The user settings are rewritten from the harness just installed: the
    # auto-mode environment is that harness's own list with the fleet's slots
    # in it (ADR-008), and only a fabric upgrade reran bootstrap, so a claude
    # upgrade alone left the previous build's wording (review of #74). Before
    # the marker: the session restarting reads the new file. Its failure is
    # said, never a failed install.
    settings: str | None = None
    if ok and root and home:
        script = os.path.join(root, "runtime", "claude-code", "user-settings.py")
        try:
            r = run([sys.executable, script, os.path.join(home, ".claude", "settings.json")], timeout=SETTINGS_TIMEOUT_MS / 1000,
                    check=True, capture_output=True, stdin=subprocess.DEVNULL)
            # Exit 0 with a "  !  " line is a key it could not write — autoMode
            # left at the previous build's when the new one's defaults could not
            # be read — so not a refresh (re-review of #74).
            refused = next((ln for ln in util.decode(getattr(r, "stderr", None)).split("\n") if ln.startswith("  !  ")), None)
            settings = f"not refreshed: {refused[5:165]}" if refused else "refreshed"
        except (subprocess.SubprocessError, OSError) as e:
            settings = f"not refreshed: {_failure_line(e, [script]).replace(sys.executable, 'python3', 1)[:160]}"   # the message names `python3`, as the Node's did
    if stop:
        write_marker(directory, {**marker, "status": "done" if ok else "failed", "installed": installed,
                                 **({"reason": reason} if reason else {}), "finished_at": iso(now())})
    return {"status": "upgraded" if ok else "failed", "piece": "claude", "from": from_, "to": target,
            **({"reason": reason} if reason else {}), **({"settings": settings} if settings else {}),
            "session": "restarting" if stop else "yours: relaunch to use it" if own and pids else "running" if pids else "none"}


def _failure_line(e: BaseException, cmd: list[str]) -> str:
    """lastLine for a failed program; one that could not start has no output,
    so it says what Node's spawn error said."""
    if isinstance(e, (subprocess.CalledProcessError, subprocess.TimeoutExpired)):
        return last_line(e)
    return util.node_error(e, cmd)


# ── `upgrade fabric` ────────────────────────────────────────────────
#
# Distribution after a merge as a signed action (the owner, 2026-09-26:
# "distributing should be in control plane") in place of a pull-and-bootstrap
# loop per login through the host executor. The coordinator's origin/main
# travels in the request as `commit`, so one command moves every account to
# one commit, as `upgrade claude` carries one version. The checkout
# fast-forwards or is left alone: a checkout off main, or one main cannot
# fast-forward, is someone's work and is reported, never forced. Bootstrap
# runs whether or not the head moved, since a checkout the launcher pulled
# was never bootstrapped. A running session is not stopped: the fabric
# reaches it at its next launch, as a rebind does. Bootstrap does not restart
# this daemon (it would kill the process running it); the reply says
# `restart_daemon` and agentd exits after posting it, for systemd to start
# the new code.

def session_provider(pids: list[int], proc: str = "/proc") -> str | None:
    """The provider a running session was launched for: bootstrap installs the
    agent files for it, and its default (anthropic) would re-pin the review
    class under a broker session until that session's next launch."""
    prefix = "AGENT_FABRIC_LAUNCH_PROVIDER="
    for pid in pids:
        try:
            with open(os.path.join(proc, str(pid), "environ"), "rb") as fh:
                env = fh.read().decode("utf-8", "replace").split("\0")
        except OSError:
            continue   # gone, or not readable
        v = next((e[len(prefix):] for e in env if e.startswith(prefix)), None)
        if v and re.fullmatch(r"[a-z][a-z0-9-]{0,31}", v):
            return v
    return None


def upgrade_fabric(request: dict, *, home: str | None = None, root: str | None = None, run: Callable[..., Any] = default_run,
                   pgrep: Callable[[list[str]], str] | None = None, sessions: list[int] | None = None, proc: str = "/proc",
                   env: dict[str, str] | None = None, **_unused: Any) -> dict:
    home = os.path.expanduser("~") if home is None else home
    root = root or os.environ.get("AGENT_FABRIC_ROOT") or os.path.join(home, "projects", "agent-fabric")
    env = dict(os.environ) if env is None else env
    args = request.get("args")
    args = {} if args is None else args
    bad = check_args(args)
    if bad:
        return {"status": "refused", "reason": bad}
    target = js_string(_get(args, "commit"))   # a one-element list or a number that passed the check is the sha it prints as

    def git(*a: str) -> str:
        r = run(["git", "-C", root, *a], timeout=FABRIC_GIT_TIMEOUT_MS / 1000, check=True, capture_output=True, stdin=subprocess.DEVNULL)
        return util.decode(r.stdout).strip()

    def said(e: BaseException, limit: int = 160) -> str:
        return "timed out" if isinstance(e, subprocess.TimeoutExpired) else _failure_line(e, ["git"])[:limit]
    try:
        from_ = git("rev-parse", "--short", "HEAD")
        branch = git("rev-parse", "--abbrev-ref", "HEAD")
    except (subprocess.SubprocessError, OSError) as e:
        return {"status": "failed", "piece": "fabric", "reason": f"{root} is not a readable checkout: {_failure_line(e, ['git'])[:160]}"}
    if branch != "main":
        # Not moved either way: a session running on that branch would lose its
        # hooks mid-session. But a branch with nothing uncommitted and nothing
        # unpushed loses nothing by a switch, and saying so is what the person
        # needs — a locale branch left checked out kept an account a release
        # behind, and its next launch ran the stale fabric (2026-09-30).
        safe = False
        try:
            upstream = git("rev-parse", "--abbrev-ref", "@{u}")
            safe = not git("status", "--porcelain") and git("rev-list", "--count", f"{upstream}..HEAD") == "0"
        except (subprocess.SubprocessError, OSError):
            pass   # no upstream, or unreadable: not known safe
        return {"status": "refused", "piece": "fabric", "from": from_, "reason": (
            f"the checkout is on {branch}, not main; not moved — it is clean and pushed, so nothing is lost by `git switch main` on the account, then upgrade again"
            if safe else f"the checkout is on {branch}, not main; not moved — find whose work it is before moving it")}
    try:
        git("fetch", "-q", "origin", "main")
    except (subprocess.SubprocessError, OSError) as e:
        return {"status": "failed", "piece": "fabric", "from": from_, "reason": f"git fetch: {said(e)}; not moved"}
    # After the fetch, a commit this checkout does not have is not on its
    # origin/main either: that is a "no", as is merge-base's exit 1.
    not_on_main = {"status": "refused", "piece": "fabric", "from": from_, "reason": f"{target[:8]} is not on this account's origin/main; not moved"}
    try:
        git("cat-file", "-e", f"{target}^{{commit}}")
    except (subprocess.SubprocessError, OSError):
        return not_on_main
    try:
        git("merge-base", "--is-ancestor", target, "origin/main")
    except subprocess.CalledProcessError as e:
        # Exit 1 is git's "not an ancestor"; anything else (an unknown object)
        # is a failure to tell, and says git's own line.
        if e.returncode == 1:
            return not_on_main
        return {"status": "failed", "piece": "fabric", "from": from_, "reason": f"git merge-base: {said(e)}; not moved"}
    except (subprocess.SubprocessError, OSError) as e:
        return {"status": "failed", "piece": "fabric", "from": from_, "reason": f"git merge-base: {said(e)}; not moved"}
    try:
        git("merge", "--ff-only", "-q", target)
    except (subprocess.SubprocessError, OSError) as e:
        return {"status": "failed", "piece": "fabric", "from": from_, "reason": f"cannot fast-forward to {target[:8]}: {_failure_line(e, ['git'])[:160]}; not forced"}
    try:
        to = git("rev-parse", "--short", "HEAD")
    except (subprocess.SubprocessError, OSError) as e:
        return {"status": "failed", "piece": "fabric", "from": from_,
                "reason": f"moved, but HEAD could not be read back: {_failure_line(e, ['git'])[:160]}; not bootstrapped", "restart_daemon": True}
    pids: list[int] | None
    try:
        pids = list(sessions) if sessions is not None else session_pids(run=pgrep)
    except (subprocess.SubprocessError, OSError):
        pids = None   # the session column says unknown
    provider = session_provider(pids, proc) if pids else None
    reason: str | None = None
    unit_deferred = False
    marker = "restart left to the caller"
    try:
        r = run(["bash", os.path.join(root, "runtime", "claude-code", "bootstrap.sh")], timeout=BOOTSTRAP_TIMEOUT_MS / 1000,
                check=True, capture_output=True, stdin=subprocess.DEVNULL, cwd=root,
                env={**env, "AGENT_FABRIC_DEFER_AGENTD_RESTART": "1", **({"AGENT_FABRIC_LAUNCH_PROVIDER": provider} if provider else {})})
        # The one place that knows the control agent's unit changed: bootstrap
        # installed it and left the restart to us (the line is bootstrap.sh's).
        unit_deferred = marker in util.decode(r.stdout)
    except subprocess.TimeoutExpired:
        reason = f"bootstrap: timed out after {BOOTSTRAP_TIMEOUT_MS // 1000} s"
    except (subprocess.SubprocessError, OSError) as e:
        # A bootstrap that installed the unit and then failed later still left
        # the restart to us, and no rerun would see the unit change again.
        unit_deferred = marker in util.decode(getattr(e, "stdout", None))
        reason = f"bootstrap: {_failure_line(e, ['bash'])[:200]}"
    moved = from_ != to
    return {
        "status": "failed" if reason else "current" if not moved else "upgraded", "piece": "fabric", "from": from_, "to": to,
        **({"provider": provider} if provider else {}), **({"reason": reason} if reason else {}),
        "session": "unknown" if pids is None else "running: next launch uses it" if pids else "none",
        "restart_daemon": moved or unit_deferred,
        **({"note": f"the control agent restarts on the new {'unit' if unit_deferred else 'code'} after this reply"} if (moved or unit_deferred) and not reason else {}),
    }
