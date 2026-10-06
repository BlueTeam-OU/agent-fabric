#!/usr/bin/env python3
"""bin/fabric-fresh — end this session at the end of a job and let the
launcher start a fresh one: the agent's own /clear (agent-fabric ADR-022).

  fabric-fresh [--note "<one line for the next session>"] [--job <id>] [--force]

A slash command is the person's, never the model's, so an agent cannot
/clear itself. It can end its own session: the session is the launcher's
child (runtime/openrouter/launch), which waits on it, reads the restart
marker this writes, and relaunches with no --resume — a new conversation
in the same terminal, with the note in its opening prompt. The finished
conversation stays on disk; `claude --resume` can still open it.

--job <id> names the job the next session is for (`fabric-jobs next`
prints it, ADR-022 rule 12): the launcher starts it in that job's working
copy, with the job in its opening prompt. An unknown job is refused
(exit 2); a working copy that is gone or has uncommitted changes is the
launcher's to refuse, and it says so and starts in the old directory.

Refused (exit 2) when the session was not started by the launcher —
nothing would bring it back — and (exit 3) when the working copy has
uncommitted changes, unless --force: a job that is not done has not
reached its artifact. The stop is SIGTERM, the harness's graceful one.
Exit 0 means the stop was sent; this process ends with the session.
Refused too (exit 2) when the launch carried its own prompt or -p: the
relaunch would replay it instead of starting anew; and when the
session's launcher predates fabric-fresh: it would resume, not start
anew — relaunch once; and when no claude process is above this one:
there is no session to stop.
"""
# The docstring above is --help, byte for byte what the bash header
# printed; the contract the port keeps (ADR-040 Wave 3, from bin/fabric-fresh):
#   - argv in order: --note V / --note=V, --job V / --job=V, --force,
#     -h/--help (prints the help, exit 0, where it is met); a flag that
#     needs a value and has none, or anything else, is exit 2. A value is
#     never read as a flag: `--note --force` is the note "--force".
#   - the checks in the bash order, each with its exit: not launched (2),
#     a launcher older than fabric-fresh (2), a launch with its own prompt
#     (2), an unknown job (2, jobs.py's own refusal on stderr), uncommitted
#     changes unless --force (3), no claude process above (2), the state
#     directory or the marker not written (1), the stop not sent (1, the
#     marker taken back if it is still ours).
#   - the marker: one JSON line, requested_at a second ahead, the note's
#     whitespace collapsed and cut at 300 characters, `job` only when given.
#   - stdout is never written; every word is on stderr.
# Changed, and said in j31's delivery:
#   - the pinned-Python check is the shim's (bin/fabric-fresh), as for
#     every forwarder: run without that Python, even --help is exit 127;
#   - the job lookup and each git call are bounded at TIMEOUT_S (the bash
#     waited for ever): a job list that does not answer is exit 2, said;
#   - a working copy git cannot answer for — a git call past TIMEOUT_S,
#     a `git status` that fails inside it, or a rev-parse that fails for
#     any reason but "not a git repository" — is exit 3, said, and
#     --force still goes ahead (the bash read a failed status as clean);
#   - a marker that cannot be written says so in a line of its own (the
#     bash left mkdir's or Python's own words, the same exit 1);
#   - the walk up to the session reads /proc, not ps.
from __future__ import annotations

import datetime
import importlib.util
import json
import os
import signal
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# The checkout this file is in, never AGENT_FABRIC_ROOT: the bash took its
# identity.py and jobs.py from beside itself, and so does this.
FABRIC = os.path.dirname(os.path.dirname(HERE))
TIMEOUT_S = 60
NOTE_MAX = 300


def say(text: str) -> None:
    print(f"fabric-fresh: {text}", file=sys.stderr)


def _identity():
    spec = importlib.util.spec_from_file_location("fabric_identity", os.path.join(FABRIC, "runtime", "identity.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class Usage(Exception):
    """A bad command line; the message is the whole answer (exit 2)."""


def parse(argv: list[str]) -> dict | None:
    """The options, or None when --help was met (and printed)."""
    opts = {"note": "", "job": "", "force": False}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--note", "--job"):
            if i + 1 >= len(argv):
                raise Usage("--note needs a value" if a == "--note" else "--job needs a job id")
            opts[a[2:]] = argv[i + 1]
            i += 2
            continue
        if a.startswith(("--note=", "--job=")):
            key, _, value = a[2:].partition("=")
            opts[key] = value
        elif a == "--force":
            opts["force"] = True
        elif a in ("-h", "--help"):
            sys.stdout.write(__doc__)
            return None
        else:
            raise Usage(f"unknown argument '{a}' (--note \"…\", --job <id>, --force)")
        i += 1
    return opts


def launch_refusal(env: dict) -> str | None:
    """Why this session cannot be started anew, or None."""
    if not env.get("AGENT_FABRIC_LAUNCH_PROFILE"):
        return "this session was not started by the launcher, so nothing would start a fresh one; use /clear"
    # Unset is a launcher older than fabric-fresh (an upgrade moves the
    # checkout, never a running launcher): it cannot read a fresh marker.
    opening = env.get("AGENT_FABRIC_LAUNCH_OPENING", "unset")
    if opening == "1":
        return None
    if opening == "unset":
        return ("this session's launcher predates fabric-fresh and would resume it, not start anew; "
                "relaunch once, or end it with /exit")
    return ("this session was launched with its own prompt (or -p); a fresh launch would replay it, "
            "not start anew — end it with /exit")


def job_known(job: str) -> bool:
    """jobs.py's own answer, its refusal on our stderr."""
    env = {**os.environ, "AGENT_FABRIC_ROOT": FABRIC}
    try:
        r = subprocess.run([sys.executable, os.path.join(FABRIC, "tools", "fabric", "jobs.py"), "show", job],
                           env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        say(f"the job list did not answer within {TIMEOUT_S} s; job {job} is not known to exist")
        return False
    return r.returncode == 0


class Unknown(Exception):
    """Whether the working copy has uncommitted changes cannot be told."""


def _git(*args: str) -> subprocess.CompletedProcess:
    """`git <args>`, decoded with replacement: only emptiness and the
    toplevel are read, and a file name that is not UTF-8 is still a change.
    No git at all is a failed call (the bash's `command not found`); git
    that does not answer is Unknown. LC_ALL=C: git's own words are read
    ("not a git repository"), and git translates them."""
    try:
        return subprocess.run(["git", *args], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              errors="replace", timeout=TIMEOUT_S, env={**os.environ, "LC_ALL": "C"})
    except OSError as e:
        return subprocess.CompletedProcess(["git", *args], 127, "", str(e))
    except subprocess.TimeoutExpired:
        raise Unknown(f"git {args[0]} did not answer within {TIMEOUT_S} s") from None


def dirty_toplevel() -> str | None:
    """The working copy's toplevel when it has uncommitted changes, None
    when it has none or this is no working copy; Unknown when git cannot
    say. Untracked files count: a new file never added is work not yet at
    its artifact, as much as an edit is (fabric-branches counts them too).
    A `git status` that fails inside a working copy is Unknown, never
    clean: the bash read it as clean, and a session ended over work it
    could not see (review of j31)."""
    # `false` with exit 0 is a bare repository or a directory inside .git:
    # no working copy, as outside one (the bash went on to a status that
    # failed there, and read it as clean). Of rev-parse's failures, only
    # "not a git repository" says there is none, and no git at all (127)
    # stays the bash's; any other — dubious ownership, a broken config —
    # is git not answering for a working copy that may be there (#100's
    # review, round 7).
    inside = _git("rev-parse", "--is-inside-work-tree")
    if inside.returncode not in (0, 127) and "not a git repository" not in inside.stderr:
        raise Unknown(f"git rev-parse failed: {(inside.stderr.strip().splitlines() or ['exit ' + str(inside.returncode)])[-1]}")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return None
    status = _git("status", "--porcelain")
    if status.returncode != 0:
        raise Unknown(f"git status failed: {(status.stderr.strip().splitlines() or ['exit ' + str(status.returncode)])[-1]}")
    if not status.stdout.strip("\n"):
        return None
    return _git("rev-parse", "--show-toplevel").stdout.rstrip("\n")


def _parent(pid: int) -> int | None:
    try:
        with open(f"/proc/{pid}/status", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith("PPid:"):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return None


def _comm(pid: int) -> str | None:
    try:
        with open(f"/proc/{pid}/comm", encoding="utf-8", errors="replace") as fh:
            return fh.read().rstrip("\n")
    except OSError:
        return None


def session_pid(comm: str) -> int | None:
    """The session: the nearest `comm` up this process's parent chain (the
    Bash tool runs as its descendant). The kernel truncates a process name
    to fifteen bytes, and the bash compared against it as read."""
    pid: int | None = os.getpid()
    while pid is not None and pid > 1:
        if _comm(pid) == comm:
            return pid
        pid = _parent(pid)
    return None


def write_marker(path: str, note: str, job: str) -> str:
    """The marker the launcher reads, as written (to take back only if it is
    still ours). requested_at a second ahead: the launcher obeys only a
    marker newer than its own start, and a job can end within the second
    the session began. Written through runtime/identity.py, like all
    per-agent state (ADR-003)."""
    at = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    marker = {"requested_at": at, "piece": "a fresh session", "status": "done", "fresh": True,
              "note": " ".join(note.split())[:NOTE_MAX]}
    if job:
        marker["job"] = job
    body = json.dumps(marker)
    _identity().atomic_write(path, body + "\n")
    return body


def stop(pid: int) -> bool:
    """SIGTERM to the session. AGENT_FABRIC_FRESH_KILL names a command run
    as `<cmd> -TERM <pid>` instead, for the suite (which runs inside a
    real session and must never stop it)."""
    hook = os.environ.get("AGENT_FABRIC_FRESH_KILL")
    if not hook:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError as e:
            say(f"kill: ({pid}) - {e.strerror}")
            return False
        return True
    try:
        return subprocess.run([hook, "-TERM", str(pid)], stdin=subprocess.DEVNULL, timeout=TIMEOUT_S).returncode == 0
    except (OSError, subprocess.TimeoutExpired) as e:
        say(f"{hook}: {e}")
        return False


def run(argv: list[str]) -> int:
    try:
        opts = parse(argv)
    except Usage as e:
        say(str(e))
        return 2
    if opts is None:
        return 0
    why = launch_refusal(dict(os.environ))
    if why:
        say(why)
        return 2
    note, job = opts["note"], opts["job"]
    if job and not job_known(job):
        return 2
    if not opts["force"]:
        try:
            top = dirty_toplevel()
        except Unknown as e:
            say(f"cannot tell whether this working copy has uncommitted changes ({e}); "
                "commit or stash them, or pass --force")
            return 3
        if top is not None:
            say(f"{top} has uncommitted changes; commit or stash them, or pass --force")
            return 3
    # AGENT_FABRIC_FRESH_COMM exists for the suite, which runs inside a
    # real session: it looks for a fake name, so a test can never stop the
    # session above it.
    comm = os.environ.get("AGENT_FABRIC_FRESH_COMM") or "claude"
    target = session_pid(comm)
    if target is None:
        say(f"no {comm} process above this one; nothing to stop")
        return 2
    identity = _identity()
    state = identity.agent_state_dir()
    marker = os.path.join(state, "restart.json")
    try:
        os.makedirs(state, exist_ok=True)
        written = write_marker(marker, note, job)
    except OSError as e:
        say(f"the restart marker was not written: {e}")
        return 1
    say("ending this session; the launcher starts a fresh one"
        + (f" for job {job}" if job else "") + (f" with: {note}" if note else ""))
    if not stop(target):
        # A marker whose stop failed would turn the session's next plain
        # exit into a fresh relaunch: take it back — only our own, since an
        # upgrade may have written its own since.
        try:
            with open(marker, encoding="utf-8") as fh:
                ours = fh.read().rstrip("\n") == written
        except (OSError, UnicodeDecodeError):
            ours = False
        if ours:
            try:
                os.remove(marker)
            except OSError:
                pass
        say(f"could not stop process {target}; nothing changed")
        return 1
    return 0


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
