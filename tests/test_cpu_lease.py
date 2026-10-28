#!/usr/bin/env python3
"""The cpu lease (ADR-010 §5 rule 9, A 2026-10-28): tools/fabric/lease.py's slots,
tools/fabric/cpu_shim.py in front of cargo and dotnet, and
tools/fabric/provisioning/install_cpu_shims.py that places it. A scratch
lease directory, a scratch policy and a fake tool that records what it was
given; nothing of the host's: the child environment is minimal and explicit
(no CI, no AGENT_FABRIC_*), so a runner's or a session's variables decide
nothing. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import contextlib
import io
import json
import os
import pwd
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
import lease  # noqa: E402
from git_env import scrub_process_env  # noqa: E402
scrub_process_env()
sys.path.insert(0, os.path.join(HERE, "tools", "fabric", "provisioning"))
import install_cpu_shims  # noqa: E402

SHIM = os.path.join(HERE, "tools", "fabric", "cpu_shim.py")
LEASE = os.path.join(HERE, "tools", "fabric", "lease.py")
INSTALLER = os.path.join(HERE, "tools", "fabric", "provisioning", "install_cpu_shims.py")
HOST = socket.gethostname().split(".")[0]
NPROC = len(os.sched_getaffinity(0))
LOGIN = pwd.getpwuid(os.geteuid()).pw_name
LAST = re.compile(r"\n?fabric-lease: reason=(\S+)\n?$")

# The fake tool. FAKE_MODE: hold (until FAKE_GO exists), leftover (starts a
# background sleeper and exits), exit3, anything else exits 0. It records its
# pid, its arguments (NUL-separated) and the variables a slot's child is given.
FAKE = """#!/bin/sh
: "${FAKE_OUT:?}"
{
  echo "pid=$$"
  echo "SigIgn=$(grep '^SigIgn' /proc/self/status | cut -f2)"
  for v in FABRIC_CPU_SLOT CARGO_BUILD_JOBS AGENT_FABRIC_TEST_JOBS DOTNET_PROCESSOR_COUNT MAKEFLAGS \\
           MSBUILDDISABLENODEREUSE DOTNET_CLI_USE_MSBUILD_SERVER UseSharedCompilation; do
    eval "if [ \\"\\${$v+set}\\" ]; then echo \\"$v=\\$$v\\"; else echo \\"$v=<unset>\\"; fi"
  done
} > "$FAKE_OUT.tmp"
: > "$FAKE_OUT.args"
[ $# -eq 0 ] || printf '%s\\0' "$@" > "$FAKE_OUT.args"
mv "$FAKE_OUT.tmp" "$FAKE_OUT"
case "$FAKE_MODE" in
  hold) while [ ! -e "$FAKE_GO" ]; do sleep 0.1; done ;;
  holdchild) sleep 120 </dev/null >/dev/null 2>&1 & echo $! > "$FAKE_OUT.child"
             while [ ! -e "$FAKE_GO" ]; do sleep 0.1; done ;;
  leftover) sleep 120 </dev/null >/dev/null 2>&1 & echo $! > "$FAKE_OUT.child" ;;
  exit3) exit 3 ;;
esac
"""


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    procs: list[subprocess.Popen] = []
    strays: list[int] = []
    sandbox = tempfile.mkdtemp(prefix="cpu-lease-test-")
    try:
        leases = f"{sandbox}/leases"
        tools = f"{sandbox}/tools"
        for d in (leases, tools):
            os.mkdir(d)
        os.chmod(leases, 0o1777)
        for name in ("cargo", "dotnet"):
            with open(f"{tools}/{name}", "w") as fh:
                fh.write(FAKE)
            os.chmod(f"{tools}/{name}", 0o755)
        policy = f"{sandbox}/host-load.json"

        def write_policy(doc: object) -> None:
            with open(policy, "w") as fh:
                fh.write(doc if isinstance(doc, str) else json.dumps(doc))

        write_policy({"cores_per_slot": 4, "wait_s": 1500, "hosts": {HOST: {"cpu_slots": 2}}})
        J = NPROC // 2
        seq = [0]

        def env(**extra: str) -> dict[str, str]:
            e = {"PATH": "/usr/bin:/bin", "HOME": sandbox, "LC_ALL": "C.UTF-8",
                 "AGENT_FABRIC_LEASES": leases, "AGENT_FABRIC_HOST_LOAD": policy,
                 "AGENT_FABRIC_CPU_TOOLS": tools}
            e.update(extra)
            return e

        def shim(tool: str, *args: str, mode: str = "", **extra: str) -> subprocess.Popen:
            seq[0] += 1
            out = f"{sandbox}/run{seq[0]}"
            p = subprocess.Popen([sys.executable, "-I", SHIM, tool, *args], stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, stdin=subprocess.DEVNULL,
                                 env=env(FAKE_OUT=out, FAKE_MODE=mode, FAKE_GO=f"{sandbox}/go{seq[0]}", **extra))
            p.out = out  # type: ignore[attr-defined]
            p.go = f"{sandbox}/go{seq[0]}"  # type: ignore[attr-defined]
            procs.append(p)
            return p

        def started(p: subprocess.Popen, within: float = 20) -> dict[str, str]:
            """What the fake tool recorded, once it is running."""
            end = time.monotonic() + within
            while time.monotonic() < end:
                if os.path.exists(p.out):  # type: ignore[attr-defined]
                    with open(p.out) as fh:  # type: ignore[attr-defined]
                        return dict(line.rstrip("\n").split("=", 1) for line in fh)
                if p.poll() is not None:
                    break
                time.sleep(0.05)
            return {}

        def finish(p: subprocess.Popen, within: float = 30) -> tuple[int, str, str]:
            out, errs = p.communicate(timeout=within)
            return p.returncode, out, errs

        def release(p: subprocess.Popen) -> None:
            open(p.go, "w").close()  # type: ignore[attr-defined]

        def argv_of(p: subprocess.Popen) -> list[str]:
            with open(p.out + ".args", "rb") as fh:  # type: ignore[attr-defined]
                return fh.read().decode().split("\0")[:-1]

        def who(**extra: str) -> tuple[int, list[str]]:
            r = subprocess.run([sys.executable, "-I", LEASE, "cpu", "--who"], env=env(**extra),
                               capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
            return r.returncode, r.stdout.splitlines()

        def reason(errs: str) -> str:
            m = LAST.search(errs)
            return m.group(1) if m else ""

        def hold_two() -> list[subprocess.Popen]:
            held = [shim("cargo", "test", mode="hold"), shim("dotnet", "build", mode="hold")]
            for p in held:
                started(p)
            return held

        def drain(held: list[subprocess.Popen]) -> None:
            for p in held:
                release(p)
                finish(p)

        # ---- slots counted: two takers hold cpu.1 and cpu.2, --who lists both
        rc, lines = who()
        check("--who, nothing held: a line per slot, exit 0", rc == 0 and lines == ["free: cpu.1", "free: cpu.2"], f"{rc} {lines}")
        a = shim("cargo", "test", "-p", "x y", mode="hold")
        info_a = started(a)
        rc, lines = who()
        check("one holder: slot 1 held, slot 2 free, exit 0 while any is free",
              rc == 0 and len(lines) == 2 and lines[0].startswith(f"held: {LOGIN} {info_a.get('pid')} ")
              and lines[0].endswith(" cpu.1 (cargo test)") and lines[1] == "free: cpu.2", f"{rc} {lines}")
        b = shim("dotnet", "build", mode="hold")
        info_b = started(b)
        rc, lines = who()
        check("two holders: both slots held, exit 1",
              rc == 1 and lines[0].startswith("held: ") and lines[1].startswith("held: ") and lines[1].endswith(" cpu.2 (dotnet build)"),
              f"{rc} {lines}")
        check("the record's pid is the tool's own (the shim became it)",
              info_a.get("pid") != "" and lines[0].split()[2] == info_a.get("pid") and lines[1].split()[2] == info_b.get("pid"),
              f"{lines} {info_a} {info_b}")
        check("the tool got its arguments untouched, an argument with a space whole",
              argv_of(a) == ["test", "-p", "x y"], str(argv_of(a)))
        check("a slot's child: FABRIC_CPU_SLOT, the budget J=nproc//N, the build-server switches",
              info_a.get("FABRIC_CPU_SLOT") == "1/2" and info_b.get("FABRIC_CPU_SLOT") == "2/2"
              and info_a.get("CARGO_BUILD_JOBS") == str(J) and info_a.get("DOTNET_PROCESSOR_COUNT") == str(J)
              and info_a.get("AGENT_FABRIC_TEST_JOBS") == str(J) and info_a.get("MAKEFLAGS") == f"-j{J}"
              and info_a.get("MSBUILDDISABLENODEREUSE") == "1" and info_a.get("DOTNET_CLI_USE_MSBUILD_SERVER") == "0"
              and info_a.get("UseSharedCompilation") == "false", str(info_a))

        # ---- a third taker waits and gets the first slot that is freed
        c = shim("cargo", "check", AGENT_FABRIC_CPU_WAIT="60")
        time.sleep(1.5)
        check("a third taker waits (running, nothing recorded)", c.poll() is None and not os.path.exists(c.out))  # type: ignore[attr-defined]
        release(b)  # slot 2, not slot 1
        rc_c, _out_c, err_c = finish(c)
        waiting = [ln for ln in err_c.splitlines() if "waiting for cpu" in ln]
        grant = [ln for ln in err_c.splitlines() if "cpu slot" in ln]
        check("the third taker is told who holds the slots, once at the start",
              len(waiting) == 1 and re.fullmatch(
                  rf"fabric-lease: waiting for cpu \(2/2 held: {LOGIN} cargo test \d+[smh], {LOGIN} dotnet build \d+[smh]\)", waiting[0]) is not None,
              err_c)
        check("the third taker gets the slot that was freed (2/2), with its budget, and runs",
              rc_c == 0 and len(grant) == 1 and re.fullmatch(rf"fabric-lease: cpu slot 2/2 after \d+s, jobs={J}", grant[0]) is not None
              and started(c).get("FABRIC_CPU_SLOT") == "2/2", f"{rc_c} {err_c}")
        finish(b)
        release(a)
        finish(a)
        rc, lines = who()
        check("every slot is free again when the holders have gone", rc == 0 and lines == ["free: cpu.1", "free: cpu.2"], str(lines))

        # ---- timeout, and a refusal without a wait
        held = hold_two()
        t0 = time.monotonic()
        p = shim("cargo", "build", AGENT_FABRIC_CPU_WAIT="1")
        rc, _o, errs = finish(p)
        check("wait over: exit 75, reason=timeout last, the holders named",
              rc == 75 and reason(errs) == "timeout" and "still held after 1s (2/2 held: " in errs and time.monotonic() - t0 < 20,
              f"{rc} {errs}")
        check("the timed-out tool never ran", not os.path.exists(p.out))  # type: ignore[attr-defined]
        p = shim("cargo", "build", AGENT_FABRIC_CPU_WAIT="0")
        rc, _o, errs = finish(p)
        check("no wait: exit 75, reason=held, and no waiting line", rc == 75 and reason(errs) == "held" and "waiting for cpu" not in errs, f"{rc} {errs}")
        for bad in ("soon", "-1", "1.5"):
            p = shim("cargo", "build", AGENT_FABRIC_CPU_WAIT=bad)
            rc, _o, errs = finish(p)
            check(f"AGENT_FABRIC_CPU_WAIT={bad}: exit 2, reason=cpu-wait", rc == 2 and reason(errs) == "cpu-wait", f"{rc} {errs}")

        # ---- nesting, CI and the opt-out pass through, with every slot held
        for label, extra, line in (("nested in a slot's child", {"FABRIC_CPU_SLOT": "1/2"}, False),
                                   ("CI set", {"CI": "true"}, False),
                                   ("AGENT_FABRIC_CPU_LEASE=0", {"AGENT_FABRIC_CPU_LEASE": "0"}, True)):
            p = shim("cargo", "test", **extra)
            rc, _o, errs = finish(p)
            ran = started(p, 1)
            check(f"{label}: runs at once with both slots held, takes none",
                  rc == 0 and ran.get("pid") is not None and "waiting" not in errs and ran.get("CARGO_BUILD_JOBS") == "<unset>",
                  f"{rc} {errs} {ran}")
            check(f"{label}: {'one stderr line says so' if line else 'nothing on stderr'}",
                  (errs.count("\n") == 1 and "AGENT_FABRIC_CPU_LEASE=0" in errs) if line else errs == "", errs)
        p = shim("cargo", "test", FABRIC_CPU_SLOT="", AGENT_FABRIC_CPU_WAIT="0")
        rc, _o, errs = finish(p)
        check("control: an EMPTY FABRIC_CPU_SLOT is not nesting (refused as before)", rc == 75 and reason(errs) == "held", f"{rc} {errs}")
        p = shim("cargo", "test", CI="", AGENT_FABRIC_CPU_WAIT="0")
        rc, _o, errs = finish(p)
        check("control: an EMPTY CI is not CI", rc == 75 and reason(errs) == "held", f"{rc} {errs}")
        p = shim("cargo", "test", AGENT_FABRIC_CPU_LEASE="1", AGENT_FABRIC_CPU_WAIT="0")
        rc, _o, errs = finish(p)
        check("control: AGENT_FABRIC_CPU_LEASE=1 is not the opt-out", rc == 75 and reason(errs) == "held", f"{rc} {errs}")

        # ---- other subcommands are untouched, with the slots held and no lease directory at all
        light = [("cargo", ["fmt"]), ("cargo", ["metadata", "--format-version", "1"]), ("cargo", ["tree"]), ("cargo", ["--version"]),
                 ("cargo", ["-V"]), ("cargo", ["+nightly", "fmt", "--check"]), ("cargo", ["--list"]), ("cargo", []),
                 ("cargo", ["help", "build"]), ("cargo", ["-q", "metadata"]), ("cargo", ["--config", "build.jobs=3", "tree"]),
                 ("cargo", ["build", "--help"]), ("cargo", ["test", "-h"]), ("cargo", ["--help", "build"]), ("cargo", ["myalias"]),
                 ("dotnet", ["new", "console"]), ("dotnet", ["add", "package", "x"]), ("dotnet", ["restore"]), ("dotnet", ["--info"]),
                 ("dotnet", ["--version"]), ("dotnet", ["app.dll", "build"]), ("dotnet", ["build", "-h"]), ("dotnet", [])]
        bad_light = []
        for tool, args in light:
            p = shim(tool, *args, mode="exit3", AGENT_FABRIC_LEASES=f"{sandbox}/no-such-dir", AGENT_FABRIC_HOST_LOAD=f"{sandbox}/no-policy")
            rc, _o, errs = finish(p)
            if not (rc == 3 and errs == "" and argv_of(p) == args and started(p, 1).get("FABRIC_CPU_SLOT") == "<unset>"):
                bad_light.append((tool, args, rc, errs))
        check("not heavy (and any -h/--help): the tool's own exit status, arguments and streams, no policy or directory read",
              not bad_light, str(bad_light))
        p = shim("cargo", "run", "--", "--help", mode="exit3", AGENT_FABRIC_LEASES=f"{sandbox}/no-such-dir")
        rc, _o, errs = finish(p)
        check("control: --help after a bare `--` is the program's, so `cargo run` is heavy (refused: no directory)",
              rc == 2 and reason(errs) == "nodir", f"{rc} {errs}")
        heavy = [("cargo", [s]) for s in "build b test t check c clippy run r bench doc install nextest llvm-cov".split()] + \
                [("cargo", ["+stable", "-q", "--locked", "build"]), ("cargo", ["--color", "never", "test"]),
                 ("cargo", ["--color=never", "-Z", "unstable-options", "test"]), ("cargo", ["-C", "dir", "build"])] + \
                [("dotnet", [s]) for s in "build test publish run pack".split()] + [("dotnet", ["-d", "build"])]
        not_heavy = []
        for tool, args in heavy:
            p = shim(tool, *args, AGENT_FABRIC_LEASES=f"{sandbox}/no-such-dir")
            rc, _o, errs = finish(p)
            if not (rc == 2 and reason(errs) == "nodir"):
                not_heavy.append((tool, args, rc))
        check("heavy subcommands (cargo, with its toolchain and global options before them; dotnet) take the lease", not not_heavy, str(not_heavy))
        drain(held)

        # ---- the tool's own exit status and a missing tool
        p = shim("cargo", "test", mode="exit3")
        rc, _o, errs = finish(p)
        check("a slot's tool: its exit status is the shim's", rc == 3 and errs == "", f"{rc} {errs}")
        p = shim("cargo", "test", AGENT_FABRIC_CPU_TOOLS=f"{sandbox}/absent")
        rc, _o, errs = finish(p)
        check("the real tool absent: 127 and a line naming it, the slot not kept", rc == 127 and "absent/cargo: No such file" in errs and who()[0] == 0, f"{rc} {errs}")

        # ---- a tool's leftover child keeps the slot, a KILL of the tool does not free it
        p = shim("cargo", "build", mode="leftover")
        rc, _o, errs = finish(p)
        child = int(open(p.out + ".child").read())  # type: ignore[attr-defined]
        strays.append(child)
        rc2, lines = who()
        check("the tool exited and left a child: the slot stays held",
              rc == 0 and rc2 == 0 and lines[0].startswith("held: ") and lines[1] == "free: cpu.2", f"{rc} {rc2} {lines}")
        check("--who says so: orphan, because the recorded pid is gone", lines[0].endswith(" (orphan: a child still runs)"), str(lines))
        q = shim("dotnet", "test", mode="holdchild")
        qpid = int(started(q)["pid"])
        rc2, lines = who()
        check("a live holder is not called an orphan", rc2 == 1 and lines[1].endswith("cpu.2 (dotnet test)") and "orphan" not in lines[1], str(lines))
        qchild = int(open(q.out + ".child").read())  # type: ignore[attr-defined]
        strays.append(qchild)
        os.kill(qpid, signal.SIGKILL)
        q.communicate(timeout=30)
        rc2, lines = who()
        check("KILL to the holder with its child running: the slot stays held, and is an orphan",
              rc2 == 1 and lines[1].startswith("held: ") and lines[1].endswith("(orphan: a child still runs)"), str(lines))
        for pid in (child, qchild):
            os.kill(pid, signal.SIGKILL)
        end = time.monotonic() + 20
        while time.monotonic() < end and who()[0] == 1:
            time.sleep(0.1)
        end = time.monotonic() + 20
        while time.monotonic() < end and not all(x.startswith("free: ") for x in who()[1]):
            time.sleep(0.1)
        rc2, lines = who()
        check("the children gone: both slots are free", rc2 == 0 and all(x.startswith("free: ") for x in lines), f"{rc2} {lines}")

        # ---- the child environment: a lower bound is kept, a higher one lowered with a line
        p = shim("cargo", "test", AGENT_FABRIC_TEST_JOBS=str(J + 7), MAKEFLAGS="-j1")
        rc, _o, errs = finish(p)
        ran = started(p)
        check("AGENT_FABRIC_TEST_JOBS above the budget is lowered, with a line; MAKEFLAGS set is kept",
              ran.get("AGENT_FABRIC_TEST_JOBS") == str(J) and ran.get("MAKEFLAGS") == "-j1"
              and f"AGENT_FABRIC_TEST_JOBS={J + 7} lowered to {J}" in errs, f"{ran} {errs}")
        p = shim("cargo", "test", AGENT_FABRIC_TEST_JOBS="1", MAKEFLAGS="", CARGO_BUILD_JOBS="99")
        rc, _o, errs = finish(p)
        ran = started(p)
        check("AGENT_FABRIC_TEST_JOBS below the budget is kept, silently; an empty MAKEFLAGS is unset; CARGO_BUILD_JOBS is set to J",
              ran.get("AGENT_FABRIC_TEST_JOBS") == "1" and ran.get("MAKEFLAGS") == f"-j{J}" and ran.get("CARGO_BUILD_JOBS") == str(J) and errs == "",
              f"{ran} {errs}")

        # ---- the policy: a host with no entry, a policy that does not read
        write_policy({"cores_per_slot": 4, "wait_s": 1500, "hosts": {"another-host": {"cpu_slots": 7}}})
        rc, lines = who()
        check("a host absent from the policy: max(1, nproc // cores_per_slot) slots", rc == 0 and len(lines) == max(1, NPROC // 4), str(lines))
        write_policy({"cores_per_slot": 1000, "hosts": {}})
        rc, lines = who()
        check("fewer cores than cores_per_slot: one slot, never none", rc == 0 and lines == ["free: cpu.1"], str(lines))
        for label, doc in (("not JSON", "{"), ("not an object", "[]"), ("cpu_slots 0", {"hosts": {HOST: {"cpu_slots": 0}}}),
                           ("cpu_slots true", {"hosts": {HOST: {"cpu_slots": True}}}), ("cpu_slots '2'", {"hosts": {HOST: {"cpu_slots": "2"}}}),
                           ("cores_per_slot 0", {"cores_per_slot": 0}), ("wait_s -1", {"wait_s": -1}), ("hosts a list", {"hosts": []}),
                           ("host entry a number", {"hosts": {HOST: 2}})):
            write_policy(doc)
            p = shim("cargo", "build")
            rc, _o, errs = finish(p)
            rc2 = subprocess.run([sys.executable, "-I", LEASE, "cpu", "--who"], env=env(), capture_output=True, text=True, timeout=60).returncode
            check(f"policy {label}: exit 2, reason=cpu-policy, the tool not run (and --who refuses alike)",
                  rc == 2 and reason(errs) == "cpu-policy" and not os.path.exists(p.out) and rc2 == 2, f"{rc} {rc2} {errs}")  # type: ignore[attr-defined]
        p = shim("cargo", "build", AGENT_FABRIC_HOST_LOAD=f"{sandbox}/absent.json")
        rc, _o, errs = finish(p)
        check("a policy file that is absent: exit 2, reason=cpu-policy", rc == 2 and reason(errs) == "cpu-policy", f"{rc} {errs}")
        write_policy({"cores_per_slot": 4, "wait_s": 1, "hosts": {HOST: {"cpu_slots": 1}}})
        h1 = shim("cargo", "test", mode="hold")
        started(h1)
        p = shim("cargo", "test")
        rc, _o, errs = finish(p)
        check("wait_s of the policy is the default wait (and one slot is one slot)", rc == 75 and reason(errs) == "timeout" and "after 1s (1/1 held" in errs, f"{rc} {errs}")
        drain([h1])
        write_policy({"cores_per_slot": 4, "wait_s": 1500, "hosts": {HOST: {"cpu_slots": 2}}})

        # ---- fixture hygiene: no lease directory, an unopenable slot
        p = shim("cargo", "build", AGENT_FABRIC_LEASES=f"{sandbox}/nowhere")
        rc, _o, errs = finish(p)
        check("no lease directory: exit 2, reason=nodir, naming the fix", rc == 2 and reason(errs) == "nodir" and "persist" in errs, f"{rc} {errs}")
        os.chmod(f"{leases}/cpu.1", 0)
        p = shim("cargo", "build")
        rc, _o, errs = finish(p)
        check("a slot file that cannot be opened (mode 000): exit 2, reason=unopenable", rc == 2 and reason(errs) == "unopenable", f"{rc} {errs}")
        os.chmod(f"{leases}/cpu.1", 0o666)

        # ---- fabric-lease cpu has no command form
        r = subprocess.run([sys.executable, "-I", LEASE, "cpu", "--", "true"], env=env(), capture_output=True, text=True, timeout=60)
        check("fabric-lease cpu -- <cmd> is a usage error (the slot is the tool's, not a child's)",
              r.returncode == 2 and "usage:" in r.stderr and "cpu is taken by" in r.stderr, f"{r.returncode} {r.stderr}")

        # ---- acquire_cpu in this process, with a clock the test controls
        pol = lease.CpuPolicy(HOST, NPROC, 2, 1500)
        one = lease.acquire_cpu(leases, pol, "tests-run", 0)
        two = lease.acquire_cpu(leases, pol, "tests-run", 0)
        check("in-process holders take slots 1 and 2", (one.k, two.k) == (1, 2) and one.n == 2 and one.jobs == NPROC // 2)
        check("the slot's descriptor is not inheritable until hold_and_exec hands it on", not os.get_inheritable(one.fd))
        clock = [1000.0]
        sleeps: list[float] = []
        said: list[tuple[float, str]] = []
        spans: list[tuple[float, float]] = []

        def fake_sleep(s: float) -> None:
            sleeps.append(s)
            clock[0] += s

        def run_wait(wait_s: int, free_at: float | None = None) -> tuple[lease.CpuSlot | None, int]:
            clock[0] = 1000.0
            sleeps.clear()
            said.clear()
            spans.clear()

            def sleeper(s: float) -> None:
                fake_sleep(s)
                if free_at is not None and clock[0] - 1000.0 >= free_at:
                    two.release()

            def uni(lo: float, hi: float) -> float:
                spans.append((lo, hi))
                return (lo + hi) / 2

            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    return lease.acquire_cpu(leases, pol, "x", wait_s, sleep=sleeper, monotonic=lambda: clock[0], uniform=uni,
                                             say=lambda t: said.append((clock[0] - 1000.0, t))), 0
            except lease.Exit as e:
                return None, e.code

        slot, code = run_wait(130)
        check("the wait polls every 2 s with jitter, never past the deadline: 75 after exactly wait_s",
              slot is None and code == 75 and abs(sum(sleeps) - 130) < 1e-6 and max(sleeps) <= 2.5 and all(s == (1.5, 2.5) for s in spans),
              f"{code} {sum(sleeps)} {set(spans)}")
        check("a line at the start of a wait and every 60 s after, no more", [round(t) for t, _ in said] == [0, 60, 120], str(said))
        slot, code = run_wait(10)
        check("a wait shorter than a poll sleeps only what is left", slot is None and code == 75 and abs(sum(sleeps) - 10) < 1e-6 and sleeps[-1] <= 2.0, str(sleeps))
        two = lease.acquire_cpu(leases, pol, "tests-run", 0) if two.fd < 0 else two
        slot, code = run_wait(130, free_at=7)
        check("a slot freed during the wait is taken, with the grant line naming the wait",
              slot is not None and slot.k == 2 and 6 <= slot.waited_s <= 9
              and re.fullmatch(rf"fabric-lease: cpu slot 2/2 after {slot.waited_s}s, jobs={NPROC // 2}\n", said[-1][1]) is not None, f"{slot} {said}")
        if slot:
            slot.release()
        one.release()
        slot, code = run_wait(0)
        check("a free slot is taken at once, silently, even with a wait", slot is not None and slot.waited_s == 0 and said == [] and sleeps == [], f"{slot} {said}")
        if slot:
            slot.release()

        # ---- the installer and the forwarders it places, through the real entry point
        pfx = f"{sandbox}/prefix"
        os.makedirs(f"{pfx}/bin")
        os.symlink(sys.executable, f"{pfx}/bin/fabric-python")
        root = f"{sandbox}/repo"
        for src, _ in install_cpu_shims.PAYLOAD:
            os.makedirs(os.path.dirname(f"{root}/{src}"), exist_ok=True)
            shutil.copy(f"{HERE}/{src}", f"{root}/{src}")
        first = install_cpu_shims.install(pfx, root)
        again = install_cpu_shims.install(pfx, root)
        directory = first.split(": ", 1)[1]
        check("install: places the copy and both forwarders; a second run changes nothing and says so",
              first.startswith("cpu shims installed: ") and again == f"cpu shims already in place: {directory}"
              and sorted(os.listdir(directory)) == ["cpu_shim.py", "host-load.json", "lease.py"]
              and all(os.stat(f"{pfx}/bin/{t}").st_mode & 0o777 == 0o755 for t in ("cargo", "dotnet"))
              and all(os.stat(f"{directory}/{n}").st_mode & 0o777 == 0o644 for n in os.listdir(directory)), f"{first} / {again}")
        before = {t: os.stat(f"{pfx}/bin/{t}").st_ino for t in ("cargo", "dotnet")}
        install_cpu_shims.install(pfx, root)
        check("install, repeated: the forwarders are not rewritten", before == {t: os.stat(f"{pfx}/bin/{t}").st_ino for t in ("cargo", "dotnet")})
        fe = env(FAKE_OUT=f"{sandbox}/fwd", FAKE_MODE="exit3")
        r = subprocess.run([f"{pfx}/bin/cargo", "test", "a b"], env=fe, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        with open(f"{sandbox}/fwd") as fh:
            ran = dict(line.rstrip("\n").split("=", 1) for line in fh)
        check("the installed cargo forwarder takes a slot and runs the tool: its status, its arguments",
              r.returncode == 3 and ran["FABRIC_CPU_SLOT"].endswith("/2") and ran["CARGO_BUILD_JOBS"] == str(J), f"{r.returncode} {r.stderr} {ran}")
        r = subprocess.run([f"{pfx}/bin/dotnet", "--info"], env=fe, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        with open(f"{sandbox}/fwd") as fh:
            ran = dict(line.rstrip("\n").split("=", 1) for line in fh)
        check("the installed dotnet forwarder: a light subcommand takes no slot", r.returncode == 3 and ran["FABRIC_CPU_SLOT"] == "<unset>", f"{r.returncode} {r.stderr}")
        def sigign(trap: bool, *args: str) -> int:
            subprocess.run(["bash", "-c", f'{"trap \"\" PIPE; " if trap else ""}exec "$@"', "x", f"{pfx}/bin/cargo", *args],
                           env=env(FAKE_OUT=f"{sandbox}/sig", FAKE_MODE=""), capture_output=True, timeout=60, stdin=subprocess.DEVNULL)
            with open(f"{sandbox}/sig") as fh:
                return int(dict(line.rstrip("\n").split("=", 1) for line in fh)["SigIgn"], 16)

        pipe_bit = 1 << (signal.SIGPIPE - 1)
        check("SIGPIPE: ignored by the caller stays ignored for the tool, default stays default, for a slot's tool and a light one",
              all(bool(sigign(t, *a) & pipe_bit) == t for t in (True, False) for a in (("test",), ("fmt",)))
              and not sigign(False, "test") & (1 << (signal.SIGXFSZ - 1)))
        os.unlink(f"{pfx}/share/agent-fabric/{os.path.basename(directory)}/cpu_shim.py")
        r = subprocess.run([f"{pfx}/bin/cargo", "test"], env=fe, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        check("forwarder, copy gone: a line on stderr, then the real tool (/usr/bin) runs without a slot",
              "the cpu lease shim is not installed" in r.stderr and "/usr/bin/cargo without a slot" in r.stderr, f"{r.returncode} {r.stderr}")
        # a changed payload is a new directory, the forwarders move, the old one goes
        with open(f"{root}/policies/host-load.json", "w") as fh:
            fh.write(json.dumps({"hosts": {HOST: {"cpu_slots": 3}}}))
        third = install_cpu_shims.install(pfx, root)
        newdir = third.split(": ", 1)[1]
        with open(f"{pfx}/bin/cargo") as fh:
            text = fh.read()
        check("a changed policy: a new directory, forwarders name it, the old one is removed, nothing half-made left",
              third.startswith("cpu shims installed: ") and newdir != directory and newdir in text and directory not in text
              and sorted(os.listdir(f"{pfx}/share/agent-fabric")) == [os.path.basename(newdir)], f"{third} {os.listdir(f'{pfx}/share/agent-fabric')}")
        r = subprocess.run([sys.executable, INSTALLER], env=env(), capture_output=True, text=True, timeout=60)
        check("install without root and without a test prefix: exit 1, one line, no traceback",
              r.returncode == 1 and "run it as root" in r.stderr and "Traceback" not in r.stderr and r.stdout == "", f"{r.returncode} {r.stderr}")
        with open(f"{root}/policies/host-load.json", "w") as fh:
            fh.write("{}")
        snapshot = {t: open(f"{pfx}/bin/{t}").read() for t in ("cargo", "dotnet")}
        os.unlink(f"{root}/policies/host-load.json")
        try:
            install_cpu_shims.install(pfx, root)
            failed = False
        except OSError:
            failed = True
        check("install, a source file missing: it raises before anything is changed",
              failed and snapshot == {t: open(f"{pfx}/bin/{t}").read() for t in ("cargo", "dotnet")}
              and sorted(os.listdir(f"{pfx}/share/agent-fabric")) == [os.path.basename(newdir)])
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()
            try:
                p.communicate(timeout=10)
            except (subprocess.TimeoutExpired, ValueError):
                pass
        for pid in strays:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        shutil.rmtree(sandbox, ignore_errors=True)

    print("test_cpu_lease:", "OK" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
