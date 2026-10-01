#!/usr/bin/env python3
"""Tests for tools/fabric/lease.py's internals; the behaviour is
tests/test_fabric-lease.sh's, run against the bin/fabric-lease shim (ADR-040
§5 rule 5). What that oracle cannot reach is here: a bash holder and a Python
holder excluding each other on one file, the signals and descriptors the
command gets, the exit statuses of a command that cannot run, bash's
arithmetic on --wait and --need-mem, the record's rules."""
from __future__ import annotations

import contextlib
import io
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import lease  # noqa: E402

SHIM = os.path.join(HERE, "bin", "fabric-lease")
MODULE = os.path.join(HERE, "tools", "fabric", "lease.py")
# The commit this port starts from: the bash it replaced.
BASH_ORIGINAL = "0d84041"
TIMEOUT = 60


def base_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith(("GITHUB_", "AGENT_FABRIC_"))}


def run(args: list[str], leases: str, env: dict[str, str] | None = None, exe: str = SHIM, **kw):
    e = {**base_env(), "AGENT_FABRIC_LEASES": leases, **(env or {})}
    return subprocess.run([exe, *args], capture_output=True, text=True, timeout=TIMEOUT, env=e, **kw)


def wait_for(path: str, text: str, seconds: float = 10) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            if text in open(path).read():
                return True
        except OSError:
            pass
        time.sleep(0.05)
    return False


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + (f"\n       {detail}" if detail and not good else ""))
        fails += not good

    scratch = tempfile.mkdtemp(prefix="test_lease.")
    holders: list[subprocess.Popen] = []
    try:
        leases = os.path.join(scratch, "leases")
        os.mkdir(leases, 0o1777)
        os.chmod(leases, 0o1777)

        print("argument parsing: bash's case, option values taken whatever they look like")
        a = lease.parse(["x", "--wait", "--", "--label=job", "--need-mem=5", "--", "echo", "--who"])
        check("--wait takes `--` as its value, the rest follows", a.wait == "--" and a.label == "job" and a.need == "5"
              and a.cmd == ["echo", "--who"] and a.name == "x")
        check("--wait last: an empty value, not an error here", lease.parse(["x", "--wait"]).wait == "")
        for argv, why in ((["x", "--help"], "no help option"), (["x", "-"], "a lone dash"), (["x", "y"], "a second name"),
                          (["x", "--who=1"], "--who takes no value")):
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    lease.parse(argv)
                check(f"usage error: {why}", False)
            except lease.Exit as e:
                check(f"usage error: {why}", e.code == 2)
        check("an empty positional is a name that is still empty", lease.parse(["", "x"]).name == "x")

        print("bash's arithmetic on whole numbers")
        check("plain decimal", lease.bash_int("12") == 12 and lease.bash_int("0") == 0)
        check("leading zero is octal", lease.bash_int("010") == 8 and lease.bash_int("00") == 0)
        check("invalid octal is an error, which reads false", lease.bash_int("08") is None)
        r = run(["x", "--need-mem", "08", "--", "echo", "ran"], leases)
        check("--need-mem 08 skips the check, as bash did", r.returncode == 0 and r.stdout == "ran\n")
        r = run(["x", "--need-mem", "99999999", "--", "echo", "ran"], leases, {"AGENT_FABRIC_MEMINFO": os.devnull})
        check("a floor that cannot be read is refused: exit 2, reason last",
              r.returncode == 2 and r.stderr.splitlines()[-1] == "fabric-lease: reason=memory-unknown", r.stderr)

        print("the holder record: first line, printable ASCII, 512 bytes, unrecorded when empty")
        p = os.path.join(scratch, "rec")
        for body, want in ((b"a b\x1b[0m c\nsecond\n", "a b[0m c"), (b"", "(holder unrecorded)"), (b"\n\nx\n", "(holder unrecorded)"),
                           (b"\xc2\x9b(bad)\x7f ok\n", "(bad) ok"), (b"y" * 600, "y" * 512)):
            open(p, "wb").write(body)
            check(f"holder of {body[:12]!r}", lease.holder(p) == want, lease.holder(p))
        check("a path that is not there is unrecorded", lease.holder(os.path.join(scratch, "absent")) == "(holder unrecorded)")
        fifo = os.path.join(scratch, "fifo")
        os.mkfifo(fifo)
        check("a fifo does not hang the read", lease.holder(fifo) == "(holder unrecorded)")

        print("record: written by an open that cannot create, truncating; best effort")
        gone = os.path.join(scratch, "never-made")
        lease.record(gone, "n", "")
        check("a file that does not exist is not created", not os.path.exists(gone))
        open(p, "w").write("old old old old old old old old old old old old\n")
        lease.record(p, "heavy", "job")
        line = open(p).read()
        parts = line.split()
        check("one line: login pid since name (label), the old record gone",
              line.count("\n") == 1 and parts[1] == str(os.getpid()) and parts[3:] == ["heavy", "(job)"] and parts[2].endswith("Z"), line)
        os.chmod(p, 0o444)
        lease.record(p, "heavy", "")
        check("a file it cannot write is left alone, no error", open(p).read() == line)

        print("meminfo: awk's reading")
        mi = os.path.join(scratch, "meminfo")
        open(mi, "w").write("MemTotal: 10 kB\nMemAvailable:   4096 kB\nMemAvailableX: 3\n")
        check("the second field of the matching line", lease.mem_field(mi, "MemAvailable") == "4096")
        open(mi, "w").write("MemAvailable: 1 kB\nMemAvailable: 2 kB\n")
        check("two lines read as two (and so are refused as not a number)", lease.mem_field(mi, "MemAvailable") == "1\n2")
        check("an unreadable file is empty", lease.mem_field(os.path.join(scratch, "absent"), "MemAvailable") == "")

        print("the largest processes: awk's layout")
        real = subprocess.run
        fake = type("R", (), {"stdout": b"USER                   PID   RSS COMMAND\nroot                     1  2048 init\n"
                                        b"a                      2 3145728 Web Content\n"})
        lease.subprocess.run = lambda *a, **k: fake
        try:
            table = lease.largest_processes()
        finally:
            lease.subprocess.run = real
        check("header indented, rows in MB with the first word of the command",
              table == "   USER                   PID   RSS COMMAND\n"
                       + "   %-20s %7s %6d MB %s\n" % ("root", "1", 2, "init")
                       + "   %-20s %7s %6d MB %s\n" % ("a", "2", 3072, "Web"), repr(table))

        print("a Python holder and a bash holder exclude each other on one resource")
        flock_sh = ('exec 9<"$1"; flock -w 1 9 || exit 75; echo held; read -r _; exit 0')
        # The mechanism of the bash original: a read-only descriptor, flock(1).
        out = os.path.join(scratch, "h.out")
        open(os.path.join(leases, "mix"), "a").close()
        os.chmod(os.path.join(leases, "mix"), 0o666)
        h = subprocess.Popen(["bash", "-c", flock_sh, "_", os.path.join(leases, "mix")], stdout=open(out, "w"),
                             stdin=subprocess.PIPE, env=base_env())
        holders.append(h)
        check("a flock(1) holder starts", wait_for(out, "held"))
        r = run(["mix", "--", "echo", "second"], leases)
        check("the Python caller is refused: 75, reason=held", r.returncode == 75 and r.stderr.splitlines()[-1] == "fabric-lease: reason=held", r.stderr)
        r = run(["mix", "--who"], leases)
        check("--who reads it held", r.returncode == 1 and r.stdout.startswith("held: "))
        h.stdin.close()
        h.wait(timeout=TIMEOUT)
        check("released: the Python caller runs", run(["mix", "--", "echo", "third"], leases).stdout == "third\n")

        py = subprocess.Popen([SHIM, "mix2", "--", "sh", "-c", "echo started; sleep 30"], stdout=open(out, "w"),
                              env={**base_env(), "AGENT_FABRIC_LEASES": leases})
        holders.append(py)
        check("a Python holder starts", wait_for(out, "started"))
        r = subprocess.run(["bash", "-c", flock_sh, "_", os.path.join(leases, "mix2")], capture_output=True, text=True,
                           timeout=TIMEOUT, input="", env=base_env())
        check("a flock(1) holder is refused by it (75)", r.returncode == 75, r.stdout)
        py.terminate()
        py.wait(timeout=TIMEOUT)

        original = os.path.join(scratch, "fabric-lease.orig")
        git = subprocess.run(["git", "-C", HERE, "show", f"{BASH_ORIGINAL}:bin/fabric-lease"], capture_output=True, timeout=TIMEOUT)
        if git.returncode != 0 or not git.stdout.startswith(b"#!/usr/bin/env bash"):
            check(f"the original bash is readable from {BASH_ORIGINAL} (a shallow clone lacks it)", False, git.stderr.decode()[:200])
        else:
            open(original, "wb").write(git.stdout)
            os.chmod(original, 0o755)
            ob = subprocess.Popen(["bash", original, "orig", "--", "sh", "-c", "echo started; sleep 30"], stdout=open(out, "w"),
                                  env={**base_env(), "AGENT_FABRIC_LEASES": leases})
            holders.append(ob)
            check("the original bash holds a lease", wait_for(out, "started"))
            r = run(["orig", "--", "echo", "second"], leases)
            check("the Python caller is refused by the bash holder, and told who",
                  r.returncode == 75 and f"held by {lease.login()} {ob.pid} " in r.stderr, r.stderr)
            ob.terminate()
            ob.wait(timeout=TIMEOUT)
            py = subprocess.Popen([SHIM, "orig", "--", "sh", "-c", "echo pystarted; sleep 30"], stdout=open(out, "w"),
                                  env={**base_env(), "AGENT_FABRIC_LEASES": leases})
            holders.append(py)
            check("the Python holder holds the same file", wait_for(out, "pystarted"))
            r = subprocess.run(["bash", original, "orig", "--", "echo", "second"], capture_output=True, text=True,
                               timeout=TIMEOUT, env={**base_env(), "AGENT_FABRIC_LEASES": leases})
            check("the original bash caller is refused by it, and told who",
                  r.returncode == 75 and f"held by {lease.login()} {py.pid} " in r.stderr, r.stderr)
            py.terminate()
            py.wait(timeout=TIMEOUT)

        print("the command's exit status and signals")
        r = run(["s", "--", "sh", "-c", "exit 75"], leases)
        check("a command that exits 75 itself: 75, and no reason line", r.returncode == 75 and r.stderr == "")
        r = run(["s", "--", "sh", "-c", "kill -KILL $$"], leases)
        check("killed by KILL: 137", r.returncode == 137, r.stderr)
        r = run(["s", "--", "sh", "-c", "kill -TERM $$"], leases)
        check("killed by TERM: 143", r.returncode == 143)
        check("no such command: 127, said", (lambda r: r.returncode == 127 and "nosuch-cmd-x: command not found" in r.stderr)(run(["s", "--", "nosuch-cmd-x"], leases)))
        check("a directory: 126", run(["s", "--", "/"], leases).returncode == 126)
        check("an empty command word: 127", run(["s", "--", ""], leases).returncode == 127)
        r = run(["s", "--", "exit", "4"], leases)
        check("a bash builtin with no program is run by bash, as `command --` did: 4", r.returncode == 4, r.stderr)
        script = os.path.join(scratch, "noshebang")
        open(script, "w").write("echo from-a-script\n")
        os.chmod(script, 0o755)
        r = run(["s", "--", script], leases)
        check("a program that is not an executable format runs as a bash script", r.returncode == 0 and r.stdout == "from-a-script\n", r.stderr)

        print("what the command inherits")
        r = run(["s", "--", "sh", "-c", 'echo "[${_FABRIC_LEASE_PIPE_IGNORED-unset}]"'], leases, {"_FABRIC_LEASE_PIPE_IGNORED": "1"})
        check("the shim's own variable is not handed on", r.stdout == "[unset]\n", r.stdout)
        dev = open(os.path.join(scratch, "seven"), "w+")
        dev.write("seven\n")
        dev.flush()

        def to7() -> None:
            os.dup2(dev.fileno(), 7)
            os.dup2(dev.fileno(), 9)
            os.set_inheritable(7, True)
            os.set_inheritable(9, True)

        r = run(["s", "--", "sh", "-c", "test -e /proc/self/fd/7 && echo has7; test -e /proc/self/fd/9 && echo has9; echo end"],
                leases, preexec_fn=to7, pass_fds=(7, 9))
        check("a caller's descriptor 7 reaches the command, its 9 does not (the bash closed 9)", r.stdout == "has7\nend\n", r.stdout)
        r = run(["s", "--", "sh", "-c", "test -e /proc/self/fd/3 && echo lease-fd-open; echo end"], leases)
        check("the lease's own descriptor is closed in the command", r.stdout == "end\n", r.stdout)

        def sigign(setup, extra=None) -> int:
            r = run(["s", "--", "grep", "SigIgn", "/proc/self/status"], leases, extra, preexec_fn=setup)
            return int(r.stdout.split()[1], 16)

        ign = lambda *sigs: (lambda: [signal.signal(s, signal.SIG_IGN) for s in sigs])  # noqa: E731
        check("SIGINT ignored on entry stays ignored in the command (a background job's inheritance)",
              sigign(ign(signal.SIGINT)) & (1 << (signal.SIGINT - 1)) != 0)
        check("SIGPIPE ignored on entry stays ignored in the command, through the shim",
              sigign(ign(signal.SIGPIPE)) & (1 << (signal.SIGPIPE - 1)) != 0)
        check("SIGPIPE not ignored on entry is default in the command",
              sigign(lambda: signal.signal(signal.SIGPIPE, signal.SIG_DFL)) & (1 << (signal.SIGPIPE - 1)) == 0)
        check("the variable a caller sets cannot ignore SIGPIPE for it",
              sigign(lambda: signal.signal(signal.SIGPIPE, signal.SIG_DFL), {"_FABRIC_LEASE_PIPE_IGNORED": "1"}) & (1 << (signal.SIGPIPE - 1)) == 0)

        print("signals to the wrapper: forwarded to the group; ignored on entry, not")
        out = os.path.join(scratch, "sig.out")
        child = 'echo started pid=$$; trap "echo got-term; exit 9" TERM; while :; do sleep 0.2; done'
        w = subprocess.Popen([SHIM, "sg", "--", "sh", "-c", child], stdout=open(out, "w"), env={**base_env(), "AGENT_FABRIC_LEASES": leases})
        holders.append(w)
        check("a holder to signal", wait_for(out, "started"))
        w.send_signal(signal.SIGTERM)
        check("TERM: the wrapper returns the command's 9", w.wait(timeout=TIMEOUT) == 9 and "got-term" in open(out).read())
        w = subprocess.Popen([SHIM, "sg", "--", "sh", "-c", child], stdout=open(out, "w"),
                             env={**base_env(), "AGENT_FABRIC_LEASES": leases}, preexec_fn=ign(signal.SIGTERM))
        holders.append(w)
        check("a holder with TERM ignored on entry", wait_for(out, "started"))
        w.send_signal(signal.SIGTERM)
        time.sleep(0.6)
        check("TERM was ignored: the wrapper and its command run on", w.poll() is None)
        pid = int(open(out).read().split("pid=")[1].split()[0])
        os.kill(pid, signal.SIGKILL)  # the command first: its group outlives a killed wrapper
        check("the command gone, the wrapper returns its status (137)", w.wait(timeout=TIMEOUT) == 137)

        print("before the command exists a signal kills the wrapper, as it did the bash; the lease goes with it")
        fifo2 = os.path.join(scratch, "meminfo.fifo")
        os.mkfifo(fifo2)
        w = subprocess.Popen([SHIM, "sg2", "--need-mem", "10", "--", "true"], env={**base_env(), "AGENT_FABRIC_LEASES": leases,
                             "AGENT_FABRIC_MEMINFO": fifo2})
        holders.append(w)
        time.sleep(0.8)
        w.send_signal(signal.SIGTERM)
        check("TERM during the memory check: killed by it", w.wait(timeout=TIMEOUT) == -signal.SIGTERM)
        check("…and the lease is free", run(["sg2", "--who"], leases).returncode == 0)

        print("through a symlink in another directory, as ~/.local/bin/fabric-lease is")
        linkdir = os.path.join(scratch, "elsewhere")
        os.mkdir(linkdir)
        link = os.path.join(linkdir, "fabric-lease")
        os.symlink(SHIM, link)
        r = run(["ln", "--", "sh", "-c", "echo via-link; exit 6"], leases, exe=link)
        check("the shim found its module through the link; the status is the command's", r.returncode == 6 and r.stdout == "via-link\n", r.stderr)
        link2 = os.path.join(linkdir, "second")
        os.symlink(link, link2)
        check("…and through a link to a link", run(["ln", "--who"], leases, exe=link2).stdout == "free: ln\n")
        shadow = os.path.join(scratch, "shadow")
        os.mkdir(shadow)
        open(os.path.join(shadow, "signal.py"), "w").write("raise SystemExit('shadowed')\n")
        r = run(["ln", "--who"], leases, exe=link, cwd=shadow, env={"PYTHONPATH": shadow})
        check("a signal.py in the working directory, or PYTHONPATH, does not shadow the standard library", r.returncode == 0 and r.stdout == "free: ln\n", r.stderr)
        w = subprocess.Popen([link, "ln", "--", "sh", "-c", "echo started pid=$$; trap 'exit 8' TERM; while :; do sleep 0.2; done"],
                             stdout=open(out, "w"), env={**base_env(), "AGENT_FABRIC_LEASES": leases})
        holders.append(w)
        check("a holder started through the link", wait_for(out, "started"))
        w.send_signal(signal.SIGTERM)
        check("TERM to it (the exec'd wrapper itself, not a layer above) reaches the command: 8", w.wait(timeout=TIMEOUT) == 8)

        print("the held refusal after a wait, a probe that does not exclude, a signal that comes early")
        out2 = os.path.join(scratch, "h2.out")
        open(os.path.join(leases, "hw"), "a").close()
        os.chmod(os.path.join(leases, "hw"), 0o666)
        h = subprocess.Popen(["bash", "-c", 'exec 9<"$1"; flock -s 9; echo held; read -r _', "_", os.path.join(leases, "hw")],
                             stdout=open(out2, "w"), stdin=subprocess.PIPE, env=base_env())
        holders.append(h)
        check("a shared-lock observer", wait_for(out2, "held"))
        check("--who reads free under it", run(["hw", "--who"], leases).returncode == 0)
        h.stdin.close()
        h.wait(timeout=TIMEOUT)
        h = subprocess.Popen([SHIM, "hw2", "--", "sh", "-c", "echo started; sleep 20"], stdout=open(out2, "w"), env={**base_env(), "AGENT_FABRIC_LEASES": leases})
        holders.append(h)
        check("a holder to wait on", wait_for(out2, "started"))
        t0 = time.monotonic()
        r = run(["hw2", "--wait", "2", "--", "echo", "no"], leases)
        check("--wait 2 on a held lease: 75, reason=timeout, after the two seconds and the first one",
              r.returncode == 75 and r.stderr.splitlines()[-1] == "fabric-lease: reason=timeout" and "waiting up to 2s" in r.stderr
              and 2.5 < time.monotonic() - t0 < 10, r.stderr)
        h.terminate()
        h.wait(timeout=TIMEOUT)
        # a TERM that arrives before the command exists is held and forwarded once it does
        real_start = lease.start
        handlers = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}

        def early(argv, pipe_ignored):
            os.kill(os.getpid(), signal.SIGTERM)
            return real_start(argv, pipe_ignored)

        lease.start = early
        try:
            a = lease.Args()
            a.cmd = ["sleep", "5"]
            t0 = time.monotonic()
            rc = lease.run_command(a, False, set())
        finally:
            lease.start = real_start
            for sig, hdl in handlers.items():
                signal.signal(sig, hdl)
        check("TERM in the gap before the fork is forwarded to the command afterwards (143, not five seconds)", rc == 143 and time.monotonic() - t0 < 4, f"rc={rc}")

        print("a closed stdout")
        p2 = subprocess.Popen([SHIM, "x", "--who"], stdout=subprocess.PIPE, env={**base_env(), "AGENT_FABRIC_LEASES": leases})
        p2.stdout.close()
        check("--who into a closed pipe ends 141, not a traceback", p2.wait(timeout=TIMEOUT) == 141)

        print("names and the lease directory")
        for bad in ("a/b", ".hidden", "-x", "a" * 65, "tail\n"):
            r = run([bad, "--", "true"], leases)
            check(f"name {bad!r} refused: 2" if not bad.startswith("-") else "a leading dash is an option: 2", r.returncode == 2)
        for good in ("a.b", "a-b_c", "A1", "a" * 64):
            check(f"name {good[:12]!r} accepted", run([good, "--", "true"], leases).returncode == 0)
        os.mkdir(os.path.join(scratch, "ro"), 0o555)
        r = run(["x", "--", "true"], os.path.join(scratch, "ro"))
        check("an unwritable lease directory, file absent: unopenable, 2, reason last",
              r.returncode == 2 and r.stderr.splitlines()[-1] == "fabric-lease: reason=unopenable", r.stderr)
        os.chmod(os.path.join(scratch, "ro"), 0o755)
        check("the file was created 0666 under umask 077", (lambda: (run(["m", "--", "true"], leases, preexec_fn=lambda: os.umask(0o77)),
                                                                      oct(os.stat(os.path.join(leases, "m")).st_mode & 0o777))[1])() == "0o666")
        check("the module run directly, without the shim, is the same", run(["m", "--", "echo", "d"], leases, exe=MODULE).stdout == "d\n")
    finally:
        for h in holders:
            if h.poll() is None:
                h.kill()
                h.wait(timeout=10)
        shutil.rmtree(scratch, ignore_errors=True)
    if fails:
        print(f"test_lease: {fails} FAILED")
        return 1
    print("test_lease: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
