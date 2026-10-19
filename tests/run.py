#!/usr/bin/env python3
"""tests/run.py — every suite agent-fabric has, in one run. The port of tests/run.sh (the shell path stays a forwarder).

  tests/run.py            # all
  tests/run.py python     # only the python suites
  tests/run.py bash       # only the bash suites (launcher, guards, hooks)
  tests/run.py static     # only the static checks (tests/static.py)

Contract, frozen from run.sh:
  argv     one optional section; any other is an invocation error: stderr says so, exit 2. CI runs one section a leg, and
           a misspelt one ran nothing and said "all suites passed" (review of #68).
  stdout   `== <label>` before each suite's own output, the python suites' runner under its own headers, the leak report,
           and last `tests/run.py: <n> suite(s) FAILED` when any failed, else `tests/run.py: all suites passed` (run.sh's
           two lines under the new name). Started by the forwarder tests/run.sh, which sets AGENT_FABRIC_RUNNER=tests/run.sh,
           every line this file prints under its own name says `tests/run.sh:` instead — CI and every reader of the last
           line see what they saw — and the variable does not reach the suites.
  exit     0 every suite passed; 1 some failed (the count is on the last line, and `FAILED_SUITES=<n>` is the python
           runner's); 2 an invocation error; 128+signal when stopped by INT/TERM/HUP (130, 143, 129).

A test run leaves behind nothing it did not find (the owner, 2026-09-19). The run owns its temporary directory: a fresh
one under short_dir, exported as TMPDIR so every suite — mktemp, Node's os.tmpdir(), Python's tempfile — writes there and
nowhere else. At the end every entry in it is a failure named by path (seventy such directories per run had accumulated
to 120 MB before anyone looked, ADR-021). The directory goes when the run ends, however it ends; because it is this
run's alone, a second run, a pip install or an editor writing into the account's directory at the same time is never
mistaken for a leak. tests/test_run.py proves the report fires on a planted entry.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SECTIONS = ("all", "static", "python", "bash")
RUNNER_VARIABLE = "AGENT_FABRIC_RUNNER"
# What this run calls itself; main() says "tests/run.sh" when the forwarder started it. Only that one other name is
# accepted: the value is printed, and anything else is ignored.
PROG = "tests/run.py"
# Cleanup ends the suites' processes with TERM, KILLs what is left after this long, and waits about twice as long in all.
TERM_GRACE_S = 5.0
KILL_WAIT_S = 10.0
# The directory a watcher removes once the run is gone without cleanup (a KILL to the run's group).
WATCHER = ("import os, shutil, sys, time\n"
           "while True:\n"
           "    try:\n"
           "        os.kill(int(sys.argv[1]), 0)\n"
           "    except ProcessLookupError:\n"
           "        break\n"
           "    except PermissionError:\n"
           "        pass\n"
           "    time.sleep(0.2)\n"
           "shutil.rmtree(sys.argv[2], ignore_errors=True)\n")

# The bash-side suites and guards, in the order run.sh ran them: (label, extra environment, argv). `python3` is the
# interpreter running this file, which is the host's (CI's matrix sets it), never a pin.
PY = sys.executable
AUTHORITY_BASE = {"AGENT_FABRIC_CHARTER_BASE": "origin/main"}
BASH_SUITES: list[tuple[str, dict[str, str], list[str]]] = [
    (".agent-fabric/ authority (this branch)", AUTHORITY_BASE, [PY, "tools/fabric/guards/agent_fabric_dir_authority.py"]),
    ("charter authority (this branch)", AUTHORITY_BASE, [PY, "tools/fabric/guards/charter_authority.py", "{root}"]),
    (".agent-fabric/ authority guard", {}, [PY, "tools/fabric/github/run_suite.py", "policies/test_check_agent_fabric_dir_authority.sh"]),
    ("no-model-pins guard", {}, [PY, "tools/fabric/github/run_suite.py", "policies/test_check_repo_settings_carry_no_model_pins.sh"]),
    ("actions pinned by SHA (this tree)", {}, [PY, "policies/check_actions_pinned_by_sha.py"]),
    ("attribution (this branch)", {"AGENT_FABRIC_ATTRIBUTION_BASE": "origin/main"}, [PY, "tools/fabric/guards/ban_generated_by_attribution.py"]),
    ("signatures (this branch)", {"AGENT_FABRIC_SIGNATURES_BASE": "origin/main"}, [PY, "tools/fabric/guards/ban_unsigned_commits.py"]),
    ("decision-record amendments (this branch)", {"AGENT_FABRIC_ADR_BASE": "origin/main"}, [PY, "tools/fabric/adr.py", "range-check"]),
    ("leak check (what a run left behind)", {}, ["bash", "tests/test_leak-check.sh"]),
    ("subagent clone guard", {}, ["bash", "runtime/claude-code/hooks/test_subagent-clone-guard.sh"]),
    ("pipe status guard", {}, ["bash", "runtime/claude-code/hooks/test_pipe-status-guard.sh"]),
    ("model-switch guard", {}, ["bash", "runtime/claude-code/hooks/test_model-switch-guard.sh"]),
    ("model fallback note", {}, ["bash", "runtime/claude-code/hooks/test_model-fallback-note.sh"]),
    ("install-agent-files (the locale worker)", {}, ["bash", "runtime/claude-code/test_install-agent-files.sh"]),
    ("the fabric's user settings (attribution off, thinking summaries, verbose)", {}, ["bash", "runtime/claude-code/test_user-settings.sh"]),
]


class Signalled(BaseException):
    """A termination signal, raised so the `finally` that removes the run's directory runs."""


def short_dir(environ: dict[str, str]) -> str:
    """The run's directories are made SHORT: a unix socket path is limited to 107 bytes, and the account's own TMPDIR
    (~/agent-fabric-tmp/…, /var/tmp/agent-fabric-<login>/… before 2026-10-17) plus a suite's nesting overflowed it for gpg's agent and the relay, and truncated
    paths in assertions (found by the 2026-10-11 parallel trial). The runtime directory is private to the account and
    short; /tmp is the fallback."""
    runtime = environ.get("XDG_RUNTIME_DIR", "")
    if runtime and os.path.isdir(runtime) and os.access(runtime, os.W_OK):
        return runtime
    return "/tmp"


def run_environment(environ: dict[str, str], scratch: str) -> dict[str, str]:
    env = dict(environ)
    env["TMPDIR"] = scratch
    env.pop(RUNNER_VARIABLE, None)
    # A suite that block-buffers its stdout shows nothing in a CI log until it ends (the 2026-10-11 audit could not
    # time a case from one).
    env["PYTHONUNBUFFERED"] = "1"
    # The GZCoord tools speak the READER's language, so a suite that asserts their lines depends on which login runs
    # it: green on a login with no locale directory (CI's) and red on every holder's. The run pins the default locale;
    # the cases that exercise a locale build their own dictionary and pass it explicitly (tools/fabric/gzcoord/i18n.py).
    env["GZCOORD_DEFAULT_LOCALE_ONLY"] = "1"
    # Likewise the account's commit signing: a gpg key with a timestamp that needs the network made five suites'
    # fixture commits fail offline, green in CI and red on the account that signs. Git's environment config outranks
    # every file, so the run's sandboxes never sign.
    env.update(GIT_CONFIG_COUNT="2", GIT_CONFIG_KEY_0="commit.gpgsign", GIT_CONFIG_VALUE_0="false",
               GIT_CONFIG_KEY_1="tag.gpgsign", GIT_CONFIG_VALUE_1="false")
    return env


def children_of(pid: int) -> list[int]:
    """Direct children, read from /proc: the tree is walked because the suites are NOT in a group of their own — a KILL
    sent to this run's group must keep reaching them."""
    found: list[int] = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return found
    for name in entries:
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/stat", "rb") as fh:
                stat = fh.read()
        except OSError:
            continue
        # The command name may hold spaces and parentheses: the fields start after the LAST ")".
        fields = stat[stat.rfind(b")") + 2:].split()
        if len(fields) > 1 and fields[1] == str(pid).encode():
            found.append(int(name))
    return found


def descendants(pid: int) -> list[int]:
    out: list[int] = []
    for child in children_of(pid):
        out += descendants(child)
        out.append(child)
    return out


def alive(pid: int) -> bool:
    """A zombie answers kill -0 to the end, so its state is read: a reaped-by-nobody child is not alive."""
    try:
        with open(f"/proc/{pid}/stat", "rb") as fh:
            return fh.read().rsplit(b")", 1)[1].split()[0] != b"Z"
    except (OSError, IndexError):
        return False


def end_tree(root: int, sleep=time.sleep, term_grace: float = TERM_GRACE_S, kill_wait: float = KILL_WAIT_S,
             graceful: bool = False) -> None:
    """Ends `root` and everything below it, or a suite still writing would recreate the scratch directory or fail in it.
    The root is STOPPED first: a root left running starts its next child the moment one dies (a test script's next step,
    the python runner's next queued suite: 40 of 40 started after the first TERM), and that child is in no earlier
    snapshot. A stopped root starts nothing, and a KILL still ends it. Then the tree is walked again and again, not once:
    TERM until the grace is over, KILL after, until nothing alive is left below the root or the wait is over; the root is
    killed last, never before its children, or they would be reparented out of the walk.
    A root that is `graceful` (the python runner, which buffers its suites' output and ends their trees itself) is asked
    first: it gets TERM, is waited for up to `kill_wait`, and only when it is still there is it treated as above, so a stop
    loses what the running suites had printed only when the runner does not answer."""
    started = time.monotonic()
    if graceful:
        try:
            os.kill(root, signal.SIGTERM)
        except OSError:
            pass
        while alive(root) and time.monotonic() - started < kill_wait:
            sleep(0.1)
    try:
        os.kill(root, signal.SIGSTOP)
    except OSError:
        pass
    started = time.monotonic()
    termed: set[int] = set()
    while True:
        below = [p for p in descendants(root) if alive(p)]
        if not below:
            break
        elapsed = time.monotonic() - started
        for pid in below:
            # TERM once per process: a handler that cleans up outside the scratch directory must not be interrupted by
            # the next pass's TERM; KILL goes to everything alive once the grace is over.
            if elapsed < term_grace and pid in termed:
                continue
            termed.add(pid)
            try:
                os.kill(pid, signal.SIGTERM if elapsed < term_grace else signal.SIGKILL)
            except OSError:
                pass
        if elapsed > kill_wait:
            break
        sleep(0.1)
    try:
        os.kill(root, signal.SIGKILL)
    except OSError:
        pass


def invoke(label: str | None, argv: list[str], env: dict[str, str], cwd: str, graceful: bool = False) -> int:
    """One suite in the foreground, its output inherited so it appears as it is written. A command that cannot be started
    is a failed suite said by name, never a skipped one; a suite killed by a signal is a failure (negative status)."""
    if label is not None:
        print(f"\n== {label}", flush=True)
    else:
        sys.stdout.flush()
    proc = None
    already = set(children_of(os.getpid()))
    try:
        try:
            proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL)
        except OSError as e:
            print(f"{PROG}: {argv[0]} could not be started: {e}", file=sys.stderr, flush=True)
            return 127
        return proc.wait()
    except BaseException:
        # subprocess.run would kill only its child, orphaning the child's own: the tree is ended while it is still a tree.
        # A second signal must not cut that short (a runner's cancel sends INT, then TERM).
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, signal.SIG_IGN)
        # The signal may land after the child exists and before `proc` holds it (a handler runs between two bytecodes):
        # the children this call added are then the suite, found by what appeared since.
        if proc is not None:
            end_tree(proc.pid, graceful=graceful)
            proc.wait()
        else:
            for pid in sorted(set(children_of(os.getpid())) - already):
                end_tree(pid)
                try:
                    os.waitpid(pid, 0)
                except ChildProcessError:
                    pass
        raise


def leak_snapshot(directory: str) -> list[str]:
    try:
        return sorted(os.listdir(directory))
    except OSError:
        return []


def leak_report(directory: str, before: list[str]) -> bool:
    """Prints every entry not in the snapshot, indented; True if there was one. Names are whole lines: an entry with a
    space or a glob character is printed as itself."""
    left = [n for n in leak_snapshot(directory) if n not in set(before)]
    if not left:
        return False
    print(f"== scratch left behind under {directory} (a suite did not clean up):")
    for name in left:
        print(f"   {name}")
    return True


def main(argv: list[str] | None = None, environ: dict[str, str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    environ = dict(os.environ if environ is None else environ)
    global PROG
    PROG = "tests/run.sh" if environ.get(RUNNER_VARIABLE) == "tests/run.sh" else "tests/run.py"
    what = args[0] if args else "all"
    if len(args) > 1 or what not in SECTIONS:
        print(f"{PROG}: no section '{' '.join(args)}' (all, static, python, bash)", file=sys.stderr)
        return 2
    scratch = tempfile.mkdtemp(prefix="af-t.", dir=short_dir(environ))
    env = run_environment(environ, scratch)
    watcher = None
    previous = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
    failed = 0
    try:
        def stop(signum, _frame):
            raise Signalled(signum)
        for s in previous:
            signal.signal(s, stop)
        # KILL cannot be trapped, and a group KILL (timeout -s KILL, a harness killing by group) ends the suites with
        # this process but runs no cleanup. A watcher in its own session, so that group KILL misses it, removes the
        # directory once this process is gone; cleanup stops it on every other ending.
        watcher = subprocess.Popen([sys.executable, "-c", WATCHER, str(os.getpid()), scratch], stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        before = leak_snapshot(scratch)
        if what in ("all", "static"):
            failed += invoke("static (bash -n, shellcheck, ruff)", [PY, os.path.join(HERE, "static.py")], env, ROOT) != 0
        if what in ("all", "python"):
            failed += invoke(None, [PY, os.path.join(HERE, "run_python_suites.py")], env, ROOT, graceful=True) != 0
            failed += invoke("corpus lint", [PY, "tools/fabric/lint.py"], env, ROOT) != 0
            failed += invoke("routing check", [PY, "tools/fabric/routing.py", "check"], env, ROOT) != 0
        if what in ("all", "bash"):
            # The branch's authority, from the branch's own copy of the guards: the local check. CI's verdict is main's
            # copy, run isolated in a step before this script (ci.yml), since a contributor's tests and modules run
            # here first (docs/live-checks/2026-10-01-guard-shadowing.md).
            for label, extra, cmd in BASH_SUITES:
                failed += invoke(label, [ROOT if a == "{root}" else a for a in cmd], {**env, **extra}, ROOT) != 0
        print(flush=True)
        failed += leak_report(scratch, before)
        if failed:
            print(f"{PROG}: {failed} suite(s) FAILED")
            return 1
        print(f"{PROG}: all suites passed")
        return 0
    except Signalled as s:
        return 128 + int(s.args[0])
    finally:
        # Cleanup must not be interrupted by a second signal. Every suite's tree was ended by invoke() as the signal
        # passed through it; the watcher is the only other child, and is killed below.
        for sig in previous:
            signal.signal(sig, signal.SIG_IGN)
        shutil.rmtree(scratch, ignore_errors=True)
        if watcher is not None:
            watcher.kill()
            watcher.wait()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    sys.exit(main())
