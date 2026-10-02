#!/usr/bin/env python3
"""bin/fabric-lease holds one lease per name across processes: a second
caller is refused fast and told who holds it, or waits when asked; the
lease outlives nothing the command leaves behind and is gone when the
holder exits; --need-mem refuses under a forged /proc/meminfo; the
missing directory is a refusal that names the fix. Against a scratch
lease directory. Ported from tests/test_fabric-lease.sh (ADR-040 Wave 6),
case for case. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import errno
import fcntl
import os
import pwd
import re
import signal
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CMD = os.path.abspath(os.environ.get("FABRIC_LEASE") or os.path.join(ROOT, "bin", "fabric-lease"))
if not os.path.isfile(CMD):
    sys.exit(f"test: script under test not found at {CMD}")
LOGIN = pwd.getpwuid(os.geteuid()).pw_name


def clean_env(**extra: str) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_")) and k != "GIT_DIR"}
    env.update(extra)
    return env


def session_members(sid: int) -> list[int]:
    found = []
    for entry in os.listdir("/proc"):
        try:
            with open(f"/proc/{entry}/stat", encoding="ascii", errors="replace") as fh:
                if entry.isdigit() and int(fh.read().rsplit(")", 1)[1].split()[3]) == sid:
                    found.append(int(entry))
        except (OSError, ValueError, IndexError):
            pass
    return found


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    holders: list[subprocess.Popen] = []
    with tempfile.TemporaryDirectory() as sandbox:
        d = f"{sandbox}/leases"
        os.mkdir(d)
        os.chmod(d, 0o1777)
        holder_out = f"{sandbox}/holder.out"

        def lease(*args: str, leases: str = d, merged: bool = True, stdin: str | None = None,
                  **env: str) -> tuple[int, str, str]:
            """rc, stdout (stderr merged into it unless merged=False), stderr."""
            r = subprocess.run(["bash", CMD, *args], env=clean_env(AGENT_FABRIC_LEASES=leases, **env),
                               input=stdin, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT if merged else subprocess.PIPE, text=True,
                               errors="replace", timeout=60)
            return r.returncode, r.stdout.rstrip("\n"), (r.stderr or "").rstrip("\n")

        def free(name: str = "backend-test") -> int:
            return lease(name, "--who")[0]

        def last(text: str) -> str:
            return text.split("\n")[-1]

        def read(path: str) -> str:
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    return fh.read()
            except OSError:
                return ""

        def hold(*args: str, **env: str) -> subprocess.Popen:
            """A holder in the background, its output in holder.out, waited
            for until it prints `started` (five seconds at most)."""
            with open(holder_out, "w") as out:
                p = subprocess.Popen(["bash", CMD, *args], env=clean_env(AGENT_FABRIC_LEASES=d, **env),
                                     stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
            holders.append(p)
            for _ in range(50):
                if "started" in read(holder_out):
                    break
                time.sleep(0.1)
            return p

        def wait_for(text: str, tries: int = 30) -> bool:
            for _ in range(tries):
                if text in read(holder_out):
                    return True
                time.sleep(0.1)
            return False

        try:
            print("fabric-lease: usage")
            rc, _, err = lease(merged=False)
            check("no name: exit 2, usage on stderr", rc == 2 and re.search(r"^usage:", err, re.M) is not None,
                  f"rc={rc} {err}")
            check("…and nothing on stdout", lease(merged=False)[1] == "")
            check("a name with a space is refused", lease("bad name", "--", "true")[0] == 2)
            check("--wait must be a number", lease("x", "--wait", "abc", "--", "true")[0] == 2)
            rc, out, _ = lease("x", "--", "true", leases=f"{sandbox}/absent")
            check("no lease directory: refused; the operator's action named, nothing the agent cannot run",
                  rc == 2 and "operator" in out and "sudo" not in out, out)

            print("fabric-lease: a free lease runs the command and returns its status")
            rc, out, _ = lease("backend-test", "--", "sh", "-c", "echo ran; exit 3")
            check("command ran, exit status passed through", rc == 3 and out == "ran", f"rc={rc} {out}")
            mode = oct(os.stat(f"{d}/backend-test").st_mode & 0o7777)[2:]
            check("the lease file is 0666 (any login may record itself)", mode == "666", mode)
            check("--who: free after the holder exited", free() == 0)
            # The orphan's output goes nowhere (a pipe it held would keep
            # this run waiting for its sleep), and it is ended once checked.
            orphan = f"{sandbox}/orphan.pid"
            subprocess.run(["bash", CMD, "backend-test", "--", "sh", "-c", f'sleep 30 & echo $! > "{orphan}"; exit 0'],
                           env=clean_env(AGENT_FABRIC_LEASES=d), stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=60)
            check("a process the command left behind does not keep the lease", free() == 0)
            try:
                os.kill(int(read(orphan)), signal.SIGKILL)
            except (ValueError, ProcessLookupError):
                pass

            print("fabric-lease: a held lease")
            h = hold("backend-test", "--", "sh", "-c", "echo started; sleep 20")
            rc, out, _ = lease("backend-test", "--", "echo", "second")
            check("a second caller is refused fast, exit 75, command not run",
                  rc == 75 and "second" not in out, f"rc={rc} {out}")
            check("…told who holds it (login, pid, since, name)",
                  f"held by {LOGIN} " in out and "backend-test" in out, out)
            rc, out, _ = lease("backend-test", "--who")
            check("--who: held, exit 1, the record",
                  rc == 1 and re.search(rf"^held: {re.escape(LOGIN)} ", out, re.M) is not None, f"rc={rc} {out}")
            rc, out, _ = lease("backend-test", "--wait", "1", "--", "echo", "second")
            check("--wait 1: waits, then says it is still held", rc == 75 and "still held" in out, f"rc={rc} {out}")
            out = lease("other-thing", "--", "echo", "other")[1]
            check("another name is another lease", out == "other", out)
            h.terminate()
            h.wait()
            check("the holder killed: the lease is free (the kernel released it)", free() == 0)
            # A waiting caller gets it when the holder finishes.
            h = hold("backend-test", "--", "sh", "-c", "echo started; sleep 1.5")
            out = lease("backend-test", "--wait", "10", "--", "echo", "got-it", merged=False)[1]
            check("--wait: runs once the holder finishes", out == "got-it", out)
            h.wait()

            print("fabric-lease: --need-mem")
            meminfo = f"{sandbox}/meminfo"
            with open(meminfo, "w") as fh:
                fh.write("MemTotal:       18152000 kB\nMemAvailable:    2048000 kB\n")
            rc, out, _ = lease("backend-test", "--need-mem", "4096", "--", "echo", "ran", AGENT_FABRIC_MEMINFO=meminfo)
            check("short of memory: refused, exit 75, the numbers said",
                  rc == 75 and "ran" not in out.split("\n") and "needs 4096 MB" in out and "2000 MB available" in out,
                  f"rc={rc} {out}")
            check("…and the lease released", free() == 0)
            out = lease("backend-test", "--need-mem", "1024", "--", "echo", "ran", AGENT_FABRIC_MEMINFO=meminfo)[1]
            check("enough memory: runs", out == "ran", out)
            rc, out, _ = lease("backend-test", "--need-mem", "1024", "--", "echo", "ran",
                               AGENT_FABRIC_MEMINFO=f"{sandbox}/absent")
            check("MemAvailable unreadable: refused, exit 2, never skipped",
                  rc == 2 and "ran" not in out.split("\n") and "MemAvailable cannot be read" in out, f"rc={rc} {out}")
            with open(f"{sandbox}/meminfo-noavail", "w") as fh:
                fh.write("MemTotal:       18152000 kB\n")
            rc, out, _ = lease("backend-test", "--need-mem", "1024", "--", "echo", "ran",
                               AGENT_FABRIC_MEMINFO=f"{sandbox}/meminfo-noavail")
            check("no MemAvailable line: the same refusal", rc == 2 and "ran" not in out.split("\n"), f"rc={rc} {out}")

            print("fabric-lease: a probe is not an acquisition")
            # --who holds a shared lock for its lifetime; a caller landing in
            # that window must still acquire. 40 probes in a burst and a
            # caller in the middle.
            probes = [subprocess.Popen(["bash", CMD, "backend-test", "--who"], env=clean_env(AGENT_FABRIC_LEASES=d),
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for _ in range(40)]
            rc, out, _ = lease("backend-test", "--", "echo", "got-through")
            for p in probes:
                p.wait()
            check("a caller is not refused by a burst of --who probes", rc == 0 and out == "got-through",
                  f"rc={rc} {out}")
            # Two probes at once both say free (shared locks coexist).
            pair = [subprocess.Popen(["bash", CMD, "backend-test", "--who"], env=clean_env(AGENT_FABRIC_LEASES=d),
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True) for _ in range(2)]
            said = [p.communicate(timeout=60)[0].strip() for p in pair]
            check("two simultaneous probes both read free", said == ["free: backend-test"] * 2, repr(said))
            # A shared lock held by an observer never reads as "held" (the
            # deterministic pin for the shared-probe design; the burst above
            # is the same fact, timing-dependent).
            with open(f"{d}/backend-test") as observer:
                fcntl.flock(observer, fcntl.LOCK_SH)
                rc = free()
            check("--who reads free under another observer's shared lock", rc == 0, f"rc={rc}")
            # The record is written before the memory check: a caller refused
            # WHILE a --need-mem evaluation runs is told THIS holder. The check
            # is made observable by a fifo as MEMINFO: the holder blocks on it
            # until the test writes, and in that window the record must
            # already be the new holder's.
            lease("backend-test", "--", "true")   # a previous holder's record
            prev = read(f"{d}/backend-test").split("\n")[0]
            fifo = f"{sandbox}/meminfo.fifo"
            os.mkfifo(fifo)
            with open(holder_out, "w") as hout:
                h = subprocess.Popen(["bash", CMD, "backend-test", "--need-mem", "1024", "--", "sh", "-c", "echo started"],
                                     env=clean_env(AGENT_FABRIC_LEASES=d, AGENT_FABRIC_MEMINFO=fifo),
                                     stdout=hout, stderr=subprocess.STDOUT, start_new_session=True)
            holders.append(h)
            # Wait for the NEW holder's line, not merely for a change: the
            # record is truncated and rewritten in place (the file is the
            # lock, so it cannot be replaced by rename), and a read in that
            # instant is empty — which is a change, and made this case flake
            # under load.
            mine = f"{LOGIN} {h.pid} "
            for _ in range(50):
                if read(f"{d}/backend-test").split("\n")[0].startswith(mine):
                    break
                time.sleep(0.1)
            now = read(f"{d}/backend-test").split("\n")[0]
            refused = lease("backend-test", "--", "echo", "second")[1]
            check("the record names the new holder while its memory check is still running", now.startswith(mine),
                  f"prev={prev} now={now} holder={h.pid}")
            check("…and a caller refused in that window is told the new holder", f"held by {mine}" in refused, refused)
            # Opening a fifo for writing blocks until a reader opens it:
            # bounded, so a regression that made the holder exit before it
            # ever read the fifo fails the suite instead of hanging it.
            fd, deadline = -1, time.monotonic() + 5
            while fd < 0 and time.monotonic() < deadline:
                try:
                    fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
                except OSError as e:
                    if e.errno != errno.ENXIO:
                        raise
                    time.sleep(0.05)
            if fd < 0:
                check("the holder never opened the fifo (exited before its memory check)", False)
            else:
                os.set_blocking(fd, True)
                os.write(fd, b"MemTotal:       18152000 kB\nMemAvailable:   12000000 kB\n")
                os.close(fd)
            rc = h.wait(timeout=60)
            check("…the holder then ran once the meminfo arrived", rc == 0 and "started" in read(holder_out),
                  f"rc={rc} {read(holder_out)}")

            print("fabric-lease: signals and names")
            h = hold("backend-test", "--", "sh", "-c",
                     'echo started; trap "echo child-got-term; exit 0" TERM; while :; do sleep 0.2; done')
            h.send_signal(signal.SIGTERM)
            h.wait(timeout=60)
            check("TERM to the wrapper reaches the command", wait_for("child-got-term"), read(holder_out))
            check("…and the lease is free afterwards", free() == 0)
            rc, out, _ = lease("backend-test", "--", "record")
            check("a function of the script is not a command (exit 127)", rc == 127, f"rc={rc} {out}")
            rc, out, _ = lease("backend-test", "--", "-v", "ls")
            check("a first word of -v is not an option of command (exit 127)", rc == 127, f"rc={rc} {out}")
            out = lease("backend-test", "--", "cat", stdin="hello-from-stdin\n", merged=False)[1]
            check("the command inherits the wrapper's stdin", out == "hello-from-stdin", out)
            # INT (2) and QUIT (3) — bits 0x6 — must not be ignored in the
            # command: a plain `&` in a script sets both to SIG_IGN. Other
            # bits are the caller's own inheritance and pass through.
            out = lease("backend-test", "--", "grep", "SigIgn", "/proc/self/status", merged=False)[1]
            mask = out.split()[1] if len(out.split()) > 1 else ""
            check(f"INT and QUIT are not ignored in the command (SigIgn {mask})",
                  bool(mask) and int(mask, 16) & 0x6 == 0, f"SigIgn {mask}")
            # The teardown: a child whose TERM handler takes time and exits
            # 7. The lease stays held while it runs; the wrapper returns 7.
            h = hold("backend-test", "--", "sh", "-c",
                     'echo started; trap "sleep 1.5; echo child-done; exit 7" TERM; while :; do sleep 0.2; done')
            h.send_signal(signal.SIGTERM)
            time.sleep(0.6)
            check("TERM: the lease stays held while the command tears down", free() == 1)
            rc = h.wait(timeout=60)
            check("…the wrapper's status is the command's (7), after its teardown",
                  rc == 7 and "child-done" in read(holder_out), f"rc={rc} {read(holder_out)}")
            check("…and the lease is free once it is gone", free() == 0)
            # HUP is forwarded like TERM.
            h = hold("backend-test", "--", "sh", "-c",
                     'echo started; trap "echo child-got-hup; exit 0" HUP; while :; do sleep 0.2; done')
            h.send_signal(signal.SIGHUP)
            h.wait(timeout=60)
            check("HUP to the wrapper reaches the command", "child-got-hup" in read(holder_out), read(holder_out))

            print("fabric-lease: every refusal ends with one stable reason line; --label names the job")
            # The contract callers match (ADR-010): the LAST stderr line,
            # whatever the prose above it says.
            out = lease("x", "--", "true", leases=f"{sandbox}/absent")[1]
            check("no lease directory: reason=nodir, last", last(out) == "fabric-lease: reason=nodir", out)
            out = lease("heavy", "--need-mem", "4096", "--", "true", AGENT_FABRIC_MEMINFO=meminfo)[1]
            check("short of memory: reason=memory, last", last(out) == "fabric-lease: reason=memory", out)
            h = hold("heavy", "--label", "backend-test", "--", "sh", "-c", "echo started; sleep 20")
            rc, out, _ = lease("heavy", "--label", "stack-up", "--", "true")
            check("held, no wait: exit 75, reason=held, last", rc == 75 and last(out) == "fabric-lease: reason=held",
                  f"rc={rc} {out}")
            check("…and the holder's job is named: heavy (backend-test)",
                  re.search(rf"held by {re.escape(LOGIN)} .* heavy \(backend-test\)", out) is not None, out)
            rc, out, _ = lease("heavy", "--wait", "1", "--", "true")
            check("the wait ran out: exit 75, reason=timeout, last",
                  rc == 75 and last(out) == "fabric-lease: reason=timeout", f"rc={rc} {out}")
            out = lease("heavy", "--who")[1]
            check("--who shows the label too", re.search(r"^held: .* heavy \(backend-test\)$", out, re.M) is not None, out)
            h.terminate()
            h.wait()
            check("a label with a space is refused (it is written into a shared file)",
                  lease("heavy", "--label", "two words", "--", "true")[0] == 2)
            check("a label with a control character is refused",
                  lease("heavy", "--label", "x\x1b]0;y", "--", "true")[0] == 2)
            out = lease("heavy", "--", "sh", "-c", "echo ran")[1]
            check("a run that is not refused prints no reason line", out == "ran", out)
            rc, out, _ = lease("heavy", "--need-mem", "1024", "--", "true", AGENT_FABRIC_MEMINFO="/dev/null")
            check("MemAvailable unreadable: exit 2, reason=memory-unknown, last",
                  rc == 2 and last(out) == "fabric-lease: reason=memory-unknown", f"rc={rc} {out}")
            # A holder record another login wrote by hand reaches a refused
            # caller's terminal: control characters never do.
            with open(f"{d}/rogue", "wb") as fh:
                fh.write(b"x 1 T heavy \x1b]0;PWNED\x07\xc2\x9b(bad)\n")
            os.chmod(f"{d}/rogue", 0o666)
            with open(f"{d}/rogue") as rogue:
                fcntl.flock(rogue, fcntl.LOCK_EX)
                r = subprocess.run(["bash", CMD, "rogue", "--", "true"], env=clean_env(AGENT_FABRIC_LEASES=d),
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
            raw = r.stdout
            check("the holder record is printed as printable ASCII only (C0, DEL and C1 dropped)",
                  b"\x1b" not in raw and b"\x07" not in raw and b"\xc2\x9b" not in raw and b"held by x 1 T heavy" in raw,
                  repr(raw))
            # A lease file in the sandbox that its owner cannot read. Not a
            # file of the host's: /proc/kcore is absent here, readable under a
            # container's default mask, and the case passed or failed with
            # the machine (the review of #39). Root reads a mode-000 file, so
            # the case is skipped there.
            open(f"{d}/sealed", "w").close()
            os.chmod(f"{d}/sealed", 0)
            if os.geteuid() == 0:
                check("unopenable: skipped under root, which opens a mode-000 file", True)
            else:
                rc, out, _ = lease("sealed", "--", "true")
                check("a lease file that cannot be opened: exit 2, reason=unopenable, last",
                      rc == 2 and last(out) == "fabric-lease: reason=unopenable", f"rc={rc} {out}")
            os.chmod(f"{d}/sealed", 0o600)
        finally:
            # Each holder leads a session of its own, and the lease runs its
            # command in a group of its own inside it: ending the session
            # ends what a regression would otherwise leave looping.
            for p in holders:
                for pid in session_members(p.pid):
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                if p.poll() is None:
                    p.kill()
                p.wait()

    print(f"\ntest_fabric_lease_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
