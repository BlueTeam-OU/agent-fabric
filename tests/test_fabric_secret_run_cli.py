#!/usr/bin/env python3
"""bin/fabric-secret-run (tools/fabric/secret_run.py): the named entries of
this login's own store reach the command's environment and nothing else;
a managed, absent, undecryptable or malformed name fails closed with exit 2
and runs nothing; the wrapper becomes the command (its pid, its exit status,
the signals the caller left it).

Against a scratch keyring, store and fabric, never the account's: the
keyring sits OUTSIDE the scratch HOME (tests/test_secret_store.py says why),
and its agent is killed at the end. The store needs no git here: the
command reads env/<NAME>.gpg as it stands, with no pull."""
from __future__ import annotations

import hashlib
import os
import shutil
import signal
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CMD = os.path.join(ROOT, "bin", "fabric-secret-run")
CANARY = "canary-7f3a\nsecond line, 'quoted' $NOT"
# What the child is told to print: the SHA-256 of each named variable it
# was given, so a value is compared without ever being printed.
DIGESTS = ("import hashlib, os, sys\n"
           "for n in sys.argv[1:]:\n"
           "    v = os.environb.get(n.encode())\n"
           "    print(n, hashlib.sha256(v).hexdigest() if v is not None else 'unset')\n")


def sha(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {str(detail)[:400]}"))
        fails += not good

    with tempfile.TemporaryDirectory() as tmp:
        home, gnupg, other_gnupg = (os.path.join(tmp, d) for d in ("home", "gnupg", "other-gnupg"))
        fabric, store = os.path.join(tmp, "fabric"), os.path.join(tmp, "store")
        os.makedirs(home)
        for d in (gnupg, other_gnupg):
            os.makedirs(d, mode=0o700)
        os.makedirs(os.path.join(fabric, "projects"))
        shutil.copy(os.path.join(ROOT, "projects", "registry.json"), os.path.join(fabric, "projects", "registry.json"))
        os.makedirs(os.path.join(store, "env"), mode=0o700)
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": home, "GNUPGHOME": gnupg, "LANG": "C.UTF-8",
               "AGENT_FABRIC_ROOT": fabric, "AGENT_FABRIC_SECRET_STORE": store, "AGENT_FABRIC_PYTHON": sys.executable}
        gpg = lambda home_dir, *a, stdin=None: subprocess.run(  # noqa: E731
            ["gpg", "--batch", "--yes", "--no-tty", "--pinentry-mode", "loopback", "--passphrase", "", "--homedir", home_dir, *a],
            input=stdin, capture_output=True, timeout=120, check=True)
        try:
            gpg(gnupg, "--quick-gen-key", "secret-run test <run@test.invalid>", "future-default", "default", "never")
            gpg(other_gnupg, "--quick-gen-key", "someone else <else@test.invalid>", "future-default", "default", "never")

            def put(name: str, value: bytes, keyring: str = gnupg, uid: str = "run@test.invalid") -> None:
                gpg(keyring, "--trust-model", "always", "--encrypt", "--recipient", uid,
                    "--output", os.path.join(store, "env", f"{name}.gpg"), stdin=value)
            put("OWN_A", CANARY.encode())
            put("OWN_B", b"bee")
            put("GH_TOKEN", b"managed-" + CANARY.encode())   # present, so a refusal is not "absent"
            put("FOREIGN", b"x", other_gnupg, "else@test.invalid")
            put("WITH_NUL", b"a\0b")

            def run(*args: str, extra: dict | None = None, **kw) -> subprocess.CompletedProcess:
                return subprocess.run([CMD, *args], env={**env, **(extra or {})}, capture_output=True, text=True,
                                      timeout=120, **kw)

            p = run("OWN_A,OWN_B", "--", sys.executable, "-c", DIGESTS, "OWN_A", "OWN_B", "OWN_C")
            check("each named entry reaches the command's environment, exactly, multi-line included",
                  p.returncode == 0 and p.stdout.splitlines() == [f"OWN_A {sha(CANARY)}", f"OWN_B {sha('bee')}", "OWN_C unset"],
                  p.stdout + p.stderr)
            check("…and nothing of the value is printed", "canary" not in (p.stdout + p.stderr).lower())
            p = run("OWN_A", "--", sys.executable, "-c", DIGESTS, "OWN_B")
            check("only the names asked for", p.returncode == 0 and p.stdout.strip() == "OWN_B unset", p.stdout + p.stderr)
            p = run("OWN_A", "--", sys.executable, "-c", DIGESTS, "OWN_A", extra={"OWN_A": "the caller's"})
            check("a variable the caller has is replaced by the store's",
                  p.stdout.strip() == f"OWN_A {sha(CANARY)}", p.stdout + p.stderr)
            p = run("OWN_A", "--", sys.executable, "-c",
                    "import os; print(os.environ['OWN_A'].split()[0] in open('/proc/self/cmdline').read())")
            check("the value is in no argv", p.returncode == 0 and p.stdout.strip() == "False", p.stdout + p.stderr)

            marker = os.path.join(tmp, "ran")
            touch = [sys.executable, "-c", f"open({marker!r}, 'w').close()"]
            for label, args, said in (
                    ("an absent name", ["OWN_A,MISSING"], "MISSING: absent from this login's store"),
                    ("an entry this key cannot decrypt", ["FOREIGN"], "FOREIGN: could not be decrypted"),
                    ("a managed name, though present", ["OWN_A,GH_TOKEN"], "GH_TOKEN is managed by"),
                    ("a CLAUDE_ name", ["CLAUDE_ANY"], "CLAUDE_ANY is managed by"),
                    ("a registry agent_env name", ["OPENAI_API_KEY"], "OPENAI_API_KEY is managed by"),
                    ("a value with a NUL byte", ["WITH_NUL"], "WITH_NUL: holds a NUL byte"),
                    ("a malformed name", ["own_a"], "'own_a' is not a secret name")):
                p = run(*args, "--", *touch)
                check(f"{label}: exit 2, named, nothing run, no value",
                      p.returncode == 2 and said in p.stderr and not os.path.exists(marker)
                      and "canary" not in (p.stdout + p.stderr).lower() and p.stdout == "", f"{p.returncode} {p.stderr}")
            only_bash = os.path.join(tmp, "only-bash")   # the wrapper's shebang, and no gpg
            os.makedirs(only_bash)
            os.symlink(shutil.which("bash"), os.path.join(only_bash, "bash"))
            p = run("OWN_A", "--", *touch, extra={"PATH": only_bash})
            check("no gpg to decrypt with: exit 2, the name, nothing run",
                  p.returncode == 2 and "OWN_A: could not be decrypted" in p.stderr and "Traceback" not in p.stderr
                  and not os.path.exists(marker), f"{p.returncode} {p.stderr}")
            p = run("GH_TOKEN", "--", *touch)
            check("…a managed name points at sync", "fabric-secrets sync" in p.stderr, p.stderr)
            p = run("OWN_A", "--", *touch, extra={"AGENT_FABRIC_ROOT": os.path.join(tmp, "no-fabric")})
            check("a registry that cannot be read: exit 2, nothing run (unknown is not own)",
                  p.returncode == 2 and "cannot tell whether OWN_A is managed" in p.stderr and not os.path.exists(marker), p.stderr)
            for args in (["OWN_A"], ["OWN_A", "--"], ["OWN_A", sys.executable, "-c", "pass"]):
                p = run(*args)
                check(f"usage {args[1:2] or '(no --)'}: exit 2", p.returncode == 2 and "usage: fabric-secret-run" in p.stderr, p.stderr)

            p = run("OWN_A", "--", "no-such-command-anywhere")
            check("a command not found: 127", p.returncode == 127 and "command not found" in p.stderr, p.stderr)
            plain = os.path.join(tmp, "not-exec")
            open(plain, "w").close()
            p = run("OWN_A", "--", plain)
            check("a command not executable: 126", p.returncode == 126 and "not executable" in p.stderr, p.stderr)
            p = run("OWN_A", "--", sys.executable, "-c", "raise SystemExit(7)")
            check("the command's exit status is the wrapper's", p.returncode == 7, p.stderr)
            pr = subprocess.Popen([CMD, "OWN_A", "--", sys.executable, "-c", "import os; print(os.getpid())"],
                                  env=env, stdout=subprocess.PIPE, text=True)
            out, _ = pr.communicate(timeout=120)
            check("the wrapper becomes the command (exec: one pid)", out.strip() == str(pr.pid), f"{out!r} {pr.pid}")

            # Read by cat, which changes no disposition at start-up (a Python
            # probe would report the SIG_IGN its own start-up set).
            def ignored(p: subprocess.CompletedProcess) -> tuple[bool, bool] | str:
                line = next((l for l in p.stdout.splitlines() if l.startswith("SigIgn:")), None)
                if line is None:
                    return p.stdout + p.stderr
                mask = int(line.split()[1], 16)
                return bool(mask >> (signal.SIGPIPE - 1) & 1), bool(mask >> (signal.SIGXFSZ - 1) & 1)
            p = run("OWN_A", "--", "cat", "/proc/self/status")
            check("SIGPIPE and SIGXFSZ as the caller left them: default", ignored(p) == (False, False), ignored(p))

            def ignoring() -> None:
                signal.signal(signal.SIGPIPE, signal.SIG_IGN)
                signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
            p = run("OWN_A", "--", "cat", "/proc/self/status", restore_signals=False, preexec_fn=ignoring)
            check("…and ignored, when the caller ignored them", ignored(p) == (True, True), ignored(p))
            p = run("OWN_A", "--", sys.executable, "-c", "import os; print('_FABRIC_SECRET_RUN_IGNORED' in os.environ)",
                    restore_signals=False, preexec_fn=ignoring)
            check("…and the hand-over variable is not passed on", p.stdout.strip() == "False", p.stdout + p.stderr)
            p = run("--help")
            check("--help: exit 0, the usage", p.returncode == 0 and "usage: fabric-secret-run" in p.stdout, p.stdout + p.stderr)
        finally:
            for d in (gnupg, other_gnupg):
                subprocess.run(["gpgconf", "--homedir", d, "--kill", "all"], capture_output=True, timeout=30)
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
