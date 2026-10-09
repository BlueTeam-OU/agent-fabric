#!/usr/bin/env python3
"""tools/fabric/tools_install.py (fabric-tools --install): the account tool
a project pins is installed from its pinned release into ~/.local/bin, only
where a working copy of the declaring project exists, hash first, proof
before the rename. No network and no real gh: the fetch is a function the
test hands in. A negative case runs beside its positive control."""
from __future__ import annotations

import hashlib
import http.client
import io
import os
import signal
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request
from git_env import git_env, scrub_process_env  # noqa: E402 — tests/, the script's own directory
scrub_process_env()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import tools_check  # noqa: E402
import tools_install  # noqa: E402

URL = "https://example.invalid/faketool_1.2.3_linux_amd64"
SCRIPT = b'#!/bin/sh\necho "faketool v1.2.3"\n'
OLD = b'#!/bin/sh\necho "faketool v1.0.0"\n'


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def tgz(members: dict[str, bytes], link: str | None = None) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o755
            tar.addfile(info, io.BytesIO(data))
        if link:
            info = tarfile.TarInfo(link)
            info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
            tar.addfile(info)
    return buf.getvalue()


def entry(body: bytes = SCRIPT, **over: object) -> dict:
    pin = {"version": "1.2.3", "url": URL, "sha256": sha(body)}
    pin.update(over)
    return {"name": "faketool", "proof": "faketool --version", "version": "any", "why": "t", "where": "account",
            "install": {k: v for k, v in pin.items() if v is not None}}


def registry(*projects: tuple[str, dict]) -> dict:
    return {"projects": {pid: {"tools": [e]} for pid, e in projects}}


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail!r}"))
        fails += not good

    class Calls:
        urls: list[str] = []

    def serving(body: bytes):
        def fetch(url: str) -> bytes:
            Calls.urls.append(url)
            return body
        return fetch

    def never(url: str) -> bytes:
        raise AssertionError(f"fetched {url}")

    def listing(home: str) -> list[str]:
        d = os.path.join(home, ".local", "bin")
        return sorted(os.listdir(d)) if os.path.isdir(d) else []

    with tempfile.TemporaryDirectory(prefix="test_tools_install.") as tmp:
        saved_path = os.environ.get("PATH", "")
        n = 0

        def account(*projects: str, old: bytes | None = None) -> str:
            """A home with working copies of `projects`, and `old` installed."""
            nonlocal n
            n += 1
            home = os.path.join(tmp, f"home{n}")
            for pid in projects:
                wc = os.path.join(home, "projects", f"{pid}-wc")
                os.makedirs(wc)
                subprocess.run(["git", "init", "-q", wc], env=git_env(), check=True, timeout=30)
                with open(os.path.join(wc, ".agent-fabric-project"), "w") as fh:
                    fh.write(pid + "\n")
            os.makedirs(os.path.join(home, ".local", "bin"))
            if old is not None:
                with open(os.path.join(home, ".local", "bin", "faketool"), "wb") as fh:
                    fh.write(old)
                os.chmod(os.path.join(home, ".local", "bin", "faketool"), 0o755)
            os.environ["PATH"] = f"{home}/.local/bin:{saved_path}"
            return home

        def run(home: str, reg: dict, fetch=never) -> dict:
            return tools_install.install("faketool", reg=reg, home=home, fetch=fetch)

        reg = registry(("pa", entry()))

        print("installed — a raw binary asset")
        home = account("pa")
        r = run(home, reg, serving(SCRIPT))
        target = os.path.join(home, ".local", "bin", "faketool")
        check("verdict installed, naming the version and path", (r["status"], r.get("version"), r.get("path")) == ("installed", "1.2.3", target), r)
        check("the file is the asset, executable by its owner, and no temporary is left",
              open(target, "rb").read() == SCRIPT and os.access(target, os.X_OK) and listing(home) == ["faketool"], listing(home))
        check("it was fetched from the pinned url, once", Calls.urls == [URL], Calls.urls)
        again = run(home, reg)
        check("a second run is current and fetches nothing (idempotent)", again["status"] == "current", again)

        print("installed — a .tar.gz asset, one named member")
        body = tgz({"faketool": SCRIPT, "LICENSE": b"x"})
        home = account("pa")
        r = run(home, registry(("pa", entry(body, member="faketool", url=URL + ".tar.gz"))), serving(body))
        check("the member, not the archive, is placed", r["status"] == "installed" and open(os.path.join(home, ".local", "bin", "faketool"), "rb").read() == SCRIPT
              and listing(home) == ["faketool"], (r, listing(home)))

        print("installed — an older version is replaced")
        home = account("pa", old=OLD)
        r = run(home, reg, serving(SCRIPT))
        check("old v1.0.0 is upgraded to the pin", r["status"] == "installed" and open(os.path.join(home, ".local", "bin", "faketool"), "rb").read() == SCRIPT, r)

        print("installed — ~/.local/bin is made when absent")
        home = account("pa")
        os.rmdir(os.path.join(home, ".local", "bin"))
        r = run(home, reg, serving(SCRIPT))
        check("the directory is created", r["status"] == "installed", r)

        print("skipped — no working copy of a declaring project")
        home = account("other")
        r = run(home, reg)
        check("skipped, the declaring project named, nothing fetched or written",
              r["status"] == "skipped" and "pa" in r["reason"] and listing(home) == [], (r, listing(home)))
        r = run(account(), reg)
        check("an account with no working copies at all is skipped too", r["status"] == "skipped", r)
        r = run(os.path.join(tmp, "no-such-home"), reg)
        check("no ~/projects directory is skipped, not an error", r["status"] == "skipped", r)

        print("refused")
        home = account("pa")
        for odd in ("../x", "a/b", "Faketool", "", "-x"):
            odd_reg = registry(("pa", {**entry(), "name": odd}))
            r = tools_install.install(odd, reg=odd_reg, home=home, fetch=never)
            check(f"{odd!r} is not a tool name, though a project declares it", r["status"] == "refused" and r["reason"] == "not a tool name", r)
        check("a tool no project declares", tools_install.install("nope", reg=reg, home=home, fetch=never)["status"] == "refused")
        host_tool = registry(("pa", {**entry(), "where": "host"}))
        check("a host tool is not an account tool", run(home, host_tool)["status"] == "refused")
        for label, bad in (("http url", entry(url="http://example.invalid/x")), ("short sha", entry(sha256="abc")),
                           ("upper-case sha", entry(sha256=sha(SCRIPT).upper())), ("member with a path", entry(member="../x")),
                           ("no version", entry(version=None)), ("a field it does not know", entry(post="rm -rf")),
                           ("no pin at all", {k: v for k, v in entry().items() if k != "install"})):
            r = run(home, registry(("pa", bad)))
            check(f"a pin with {label}", r["status"] == "refused" and listing(home) == [], (r, listing(home)))
        home = account("pa", "pb")
        r = run(home, registry(("pa", entry()), ("pb", entry(version="2.0.0"))))
        check("two declaring projects with different pins disagree", r["status"] == "refused", r)
        r = run(home, registry(("pa", entry()), ("pb", entry())), serving(SCRIPT))
        check("...and with the same pin they do not (positive control)", r["status"] == "installed", r)

        print("failed — nothing wrong is placed, nothing right is touched")
        home = account("pa", old=OLD)
        r = run(home, reg, serving(SCRIPT + b"# tampered\n"))
        check("a wrong hash: failed, the old file stands, no temporary", r["status"] == "failed" and "sha256" in r["reason"]
              and open(os.path.join(home, ".local", "bin", "faketool"), "rb").read() == OLD and listing(home) == ["faketool"], (r, listing(home)))
        liar = b'#!/bin/sh\necho "faketool v9.9.9"\n'
        r = run(home, registry(("pa", entry(liar))), serving(liar))
        check("a file whose proof prints another version is not placed", r["status"] == "failed" and "does not prove" in r["reason"]
              and open(os.path.join(home, ".local", "bin", "faketool"), "rb").read() == OLD and listing(home) == ["faketool"], (r, listing(home)))
        broken = b"not a program"
        r = run(home, registry(("pa", entry(broken))), serving(broken))
        check("a file that does not run is not placed", r["status"] == "failed" and listing(home) == ["faketool"], (r, listing(home)))

        def refuses(url: str) -> bytes:
            raise urllib.error.URLError("unreachable")
        r = run(home, reg, refuses)
        check("an unreachable release is failed, with the cause", r["status"] == "failed" and "unreachable" in r["reason"], r)
        arch = tgz({"other": SCRIPT})
        r = run(home, registry(("pa", entry(arch, member="faketool"))), serving(arch))
        check("an archive without the member", r["status"] == "failed" and "holds no faketool" in r["reason"], r)
        arch = tgz({}, link="faketool")
        r = run(home, registry(("pa", entry(arch, member="faketool"))), serving(arch))
        check("an archive whose member is a symlink", r["status"] == "failed" and "not a regular file" in r["reason"], r)
        r = run(home, registry(("pa", entry(b"plain", member="faketool"))), serving(b"plain"))
        check("a member named for something that is not a .tar.gz", r["status"] == "failed", r)
        check("through all of it the old file stands", open(os.path.join(home, ".local", "bin", "faketool"), "rb").read() == OLD
              and listing(home) == ["faketool"], listing(home))

        print("every error path ends in a verdict")
        home = account("pa")

        def bad_status(url: str) -> bytes:
            raise http.client.BadStatusLine("garbage")
        r = run(home, reg, bad_status)
        check("a malformed reply from the release host is failed, not a traceback", r["status"] == "failed" and "BadStatusLine" in r["reason"], r)
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        threading.Thread(target=lambda: (lambda c: (c.recv(4096), c.sendall(b"garbage\r\n\r\n"), c.close()))(srv.accept()[0]), daemon=True).start()
        r = tools_install.install("faketool", reg=registry(("pa", entry(url=f"https://127.0.0.1:{srv.getsockname()[1]}/x"))),
                                  home=home, fetch=tools_install.fetch_https)
        srv.close()
        check("...and through the real fetch (a host that does not speak TLS)", r["status"] == "failed" and listing(home) == [], (r, listing(home)))
        home = account("pa")
        import shutil
        shutil.rmtree(os.path.join(home, ".local"))
        with open(os.path.join(home, ".local"), "w") as fh:
            fh.write("a file")
        r = run(home, reg, serving(SCRIPT))
        check("~/.local that is a file is failed, with the path", r["status"] == "failed" and ".local" in r["reason"], r)
        home = account("pa")
        for odd in ("a string", ["x"], 7):
            bad = {**entry(), "install": odd}
            r = run(home, registry(("pa", bad)))
            check(f"an install pin that is {odd!r} is refused", r["status"] == "refused", r)
        home = account("pa", "pb")
        for first, second in ((["x"], entry()), (entry(), ["x"])):
            r = run(home, registry(("pa", first if isinstance(first, dict) else {**entry(), "install": first}),
                                   ("pb", second if isinstance(second, dict) else {**entry(), "install": second})))
            check("...whichever project holds it", r["status"] == "refused", r)
        home = account("pa", "pb")
        other_proof = {**entry(), "proof": "faketool -V"}
        r = run(home, registry(("pa", entry()), ("pb", other_proof)))
        check("projects that agree on the pin but not on the proof are told apart", r["status"] == "refused" and "proofs" in r["reason"], r)

        print("a pre-release is not the pinned version")
        check("3.69.0-rc1 does not print 3.69.0", not tools_install.prints_version("doppler v3.69.0-rc1", "3.69.0"))
        check("...and v3.69.0 does (positive control)", tools_install.prints_version("doppler v3.69.0", "3.69.0")
              and not tools_install.prints_version("v13.69.0", "3.69.0") and not tools_install.prints_version("3.69.01", "3.69.0"))

        print("temporaries")
        home = account("pa")
        bindir = os.path.join(home, ".local", "bin")
        dead = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True, timeout=30).stdout.strip()
        for name in (f".faketool.{dead}.tmp", f".faketool.{os.getpid()}.tmp", f".other.{dead}.tmp", ".faketool.x.tmp"):
            open(os.path.join(bindir, name), "w").close()
        tools_install.sweep_temporaries(bindir, "faketool")
        check("a dead run's temporary goes; a live one's, another tool's and a non-pid name stay",
              sorted(os.listdir(bindir)) == sorted([f".faketool.{os.getpid()}.tmp", f".other.{dead}.tmp", ".faketool.x.tmp"]), sorted(os.listdir(bindir)))
        os.unlink(os.path.join(bindir, f".faketool.{os.getpid()}.tmp"))
        home = account("pa")
        bindir = os.path.join(home, ".local", "bin")
        open(os.path.join(bindir, f".faketool.{dead}.tmp"), "w").close()
        r = run(home, reg, serving(SCRIPT))
        open(os.path.join(os.path.join(home, ".local", "bin"), ".faketool.2147483648.tmp"), "w").close()
        huge = os.path.join(home, ".local", "bin", ".faketool.2147483648.tmp")
        check("a pid-shaped name past any pid does not crash the sweep, and is not a temporary of ours",
              tools_install.sweep_temporaries(os.path.join(home, ".local", "bin"), "faketool") is None and os.path.exists(huge))
        os.unlink(huge)
        check("an install sweeps what a killed run left", r["status"] == "installed" and listing(home) == ["faketool"], (r, listing(home)))

        print("SIGTERM, through fabric-tools --install itself")
        import json
        slow = b"#!/bin/sh\nsleep 30\n"
        driver = ("import sys, json, time; sys.path.insert(0, sys.argv[1]); import tools_install, tools_check, workingcopy\n"
                  "reg = json.loads(sys.argv[2]); home = sys.argv[3]\n"
                  "tools_check.registry = lambda: reg\n"
                  "def hang(p):\n"
                  "    open(home + '/scanning', 'w').close(); time.sleep(30)\n"
                  "if sys.argv[5] == 'scan': workingcopy.toplevel = hang\n"
                  "def fetch(u):\n"
                  "    open(home + '/fetched', 'w').close(); return bytes.fromhex(sys.argv[4])\n"
                  "orig = tools_install.install\n"
                  "tools_install.install = lambda *a, **k: orig(*a, fetch=fetch, **k)\n"
                  "sys.exit(tools_check.main(['--install', 'faketool']))\n")

        def terminated(at: str, home: str) -> tuple[int, bool, bool]:
            """(exit status, a temporary was seen, anything was fetched)."""
            proc = subprocess.Popen([sys.executable, "-c", driver, os.path.join(ROOT, "tools", "fabric"),
                                     json.dumps(registry(("pa", entry(slow)))), home, slow.hex(), at],
                                    env={**os.environ, "HOME": home, "PATH": f"{home}/.local/bin:{saved_path}"},
                                    stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            seen = False
            deadline = time.time() + 30
            while time.time() < deadline:
                if at == "proof" and any(n.endswith(".tmp") for n in listing(home)):
                    seen = True
                    break
                if at == "scan" and os.path.exists(os.path.join(home, "scanning")):
                    seen = True
                    break
                time.sleep(0.05)
            proc.send_signal(signal.SIGTERM)
            rc = proc.wait(timeout=30)
            return rc, seen, os.path.exists(os.path.join(home, "fetched"))
        home = account("pa")
        rc, seen, fetched = terminated("proof", home)
        check("the temporary existed while the proof ran (positive control)", seen and fetched, (seen, fetched))
        check("after SIGTERM in the proof: exit 143, no temporary, nothing installed", rc == 128 + signal.SIGTERM and listing(home) == [], (rc, listing(home)))
        home = account("pa")
        rc, seen, fetched = terminated("scan", home)
        check("SIGTERM during the working-copy scan stops the run: 143, nothing fetched or written",
              seen and rc == 128 + signal.SIGTERM and not fetched and listing(home) == [], (seen, rc, fetched, listing(home)))

        print("a SIGTERM outside main's own try is still 143")
        real_main = tools_check.main
        tools_check.main = lambda argv: (_ for _ in ()).throw(tools_install.Terminated(143))
        try:
            check("entry turns a Terminated that escaped main into its exit status", tools_check.entry(["--install", "x"]) == 143)
        finally:
            tools_check.main = real_main
        tools_check.main = lambda argv: 7
        try:
            check("...and passes any other status through (positive control)", tools_check.entry([]) == 7)
        finally:
            tools_check.main = real_main

        print("fabric-tools --install arms the SIGTERM exit before it works")
        probe = ("import sys, signal; sys.path.insert(0, sys.argv[1]); import tools_check, tools_install\n"
                 "tools_check.registry = lambda: {'projects': {}}\n"
                 "tools_install.install = lambda *a, **k: print(signal.getsignal(signal.SIGTERM) is signal.SIG_DFL) or {'status': 'skipped', 'tool': 'x'}\n"
                 "sys.exit(tools_check.main(['--install', 'faketool']))\n")
        r = subprocess.run([sys.executable, "-c", probe, os.path.join(ROOT, "tools", "fabric")], capture_output=True, text=True, timeout=60)
        check("the handler is not the default by the time install runs", r.returncode == 0 and r.stdout.startswith("False\n"), (r.returncode, r.stdout, r.stderr[:200]))

        print("the https-only redirect")
        h = tools_install._HttpsOnly()
        try:
            h.redirect_request(None, None, 302, "Found", {}, "http://example.invalid/x")
            refused_redirect = False
        except urllib.error.URLError:
            refused_redirect = True
        check("a redirect off https is refused", refused_redirect)
        follows = h.redirect_request(urllib.request.Request("https://example.invalid/a"), io.BytesIO(), 302, "Found", {},
                                     "https://cdn.example.invalid/b")
        check("...and one that stays on https is followed (positive control)", follows is not None and follows.full_url == "https://cdn.example.invalid/b", follows)

        print("fabric-tools --install — the command")
        os.environ["PATH"] = saved_path
        env = {k: v for k, v in os.environ.items() if not k.startswith(("AGENT_FABRIC_", "GITHUB_", "GIT_"))}
        env.update(HOME=os.path.join(tmp, "cli-home"), GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        os.makedirs(env["HOME"])
        cli = [sys.executable, os.path.join(ROOT, "tools", "fabric", "tools_check.py")]
        for argv, rc in ((["--install", "nope"], 2), (["--install", "nope", "--json"], 2), (["--install", "x", "--all"], 2),
                         (["--install"], 2)):
            r = subprocess.run([*cli, *argv], capture_output=True, text=True, env=env, timeout=60, stdin=subprocess.DEVNULL)
            check(f"{' '.join(argv)}: exit {rc}", r.returncode == rc and r.stdout.count("\n") <= 40, (r.returncode, r.stdout[:200], r.stderr[:200]))
        r = subprocess.run([*cli, "--install", "nope", "--json"], capture_output=True, text=True, env=env, timeout=60, stdin=subprocess.DEVNULL)
        check("--json prints the verdict as one object", '"status": "refused"' in r.stdout, r.stdout)

    print("pass" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
