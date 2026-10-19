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
import json
import os
import pwd
import signal
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import types
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
        # Not the real account's ~/.local/bin: a tool the account already has there answers a proof as current
        # and the install under test never runs (a Codex installed by hand failed two cases, review of #222).
        real_bin = os.path.realpath(os.path.join(pwd.getpwuid(os.getuid()).pw_dir, ".local", "bin"))
        scrubbed_path = ":".join(d for d in saved_path.split(":") if os.path.realpath(d) != real_bin)
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
            os.environ["PATH"] = f"{home}/.local/bin:{scrubbed_path}"
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

        print("installed — a member one directory down, as release tarballs keep it")
        body = tgz({"faketool-1.0.0/faketool": SCRIPT, "faketool-1.0.0/README.md": b"x"})
        home = account("pa")
        r = run(home, registry(("pa", entry(body, member="faketool-1.0.0/faketool", url=URL + ".tar.gz"))), serving(body))
        check("a nested member is placed under the tool's own name", r["status"] == "installed"
              and open(os.path.join(home, ".local", "bin", "faketool"), "rb").read() == SCRIPT and listing(home) == ["faketool"], (r, listing(home)))
        for odd in ("a/../faketool", "/faketool", "a//faketool", "./faketool", "a/"):
            r = run(home, registry(("pa", entry(body, member=odd, url=URL + ".tar.gz"))), serving(body))
            check(f"member {odd!r} is refused before any fetch", r["status"] == "refused", r)

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
                                    env={**os.environ, "HOME": home, "PATH": f"{home}/.local/bin:{scrubbed_path}"},
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

        print("the SIGTERM handler is one-shot")
        before = signal.getsignal(signal.SIGTERM)
        tools_install.exit_on_sigterm()
        try:
            os.kill(os.getpid(), signal.SIGTERM)
            first = False
        except tools_install.Terminated as t:
            first = t.code == 128 + signal.SIGTERM
        try:
            os.kill(os.getpid(), signal.SIGTERM)
            second_raised = False
        except tools_install.Terminated:
            second_raised = True
        finally:
            signal.signal(signal.SIGTERM, before)
        check("the first SIGTERM raises Terminated(143)", first)
        check("a second one does not: nothing outside the one handler can catch it", not second_raised)

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

        print("the size bound admits the pinned Codex CLI (a 158 MiB tarball around a 281 MiB binary)")
        check("the bound is above the largest pinned asset", tools_install.MAX_ASSET_BYTES >= 300 * 1024 * 1024, tools_install.MAX_ASSET_BYTES)

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

        print("codex — the pin the registry carries (ADR-053 rule 7)")
        with open(os.path.join(ROOT, "projects", "registry.json")) as fh:  # this tree's, not the account's resolved one
            real = json.load(fh)
        decl = tools_install.declarations(real, "codex")
        check("agent-fabric declares codex as an account tool", [pid for pid, _ in decl] == ["agent-fabric"], decl)
        if not decl:   # codex_reg and the size-bound cases below index decl[0]: stop here, the failure above says why
            print(f"{fails} FAILED")
            return 1
        pin = decl[0][1]["install"]
        root = "package/vendor/x86_64-unknown-linux-musl"
        # Measured on the pinned tarball (2026-10-12): Codex spawns bin/codex-code-mode-host beside its resolved
        # executable for every tool call, and uses codex-path/rg (bwrap where the host has none) only through
        # codex-package.json. Installed as bin/codex alone it ran no command at all.
        check("the pin is a tree: the vendor directory, its entrypoint the binary the gateway's CI runs (its CODEX_BIN)",
              pin.get("root") == root and pin.get("entrypoint") == "bin/codex" and "member" not in pin, pin)
        check("the tree holds the tool host, the layout manifest and the helpers it names",
              {"bin/codex", "bin/codex-code-mode-host", "codex-package.json", "codex-path/rg", "codex-resources/bwrap"}
              <= set(pin.get("members") or []), pin.get("members"))
        check("…and not the voice resources a review never uses",
              not any("voice" in m for m in pin.get("members") or []), pin.get("members"))
        check("the pin is one the installer can act on, at the released version",
              tools_install.check_pin(pin) is None and pin.get("version") == "0.162.1" and decl[0][1].get("version") == "0.162.1", pin)
        check("the proof's first line, as Codex prints it, is the pinned version",
              tools_install.prints_version("codex-cli 0.162.1", pin.get("version", "")) and not tools_install.prints_version("codex-cli 0.162.10", pin.get("version", "")))

        print("a tree pin — the npm layout, stood in for")
        fake = b'#!/bin/sh\necho "codex-cli 0.162.1"\n'
        members = pin.get("members") or []
        layout = {f"{root}/{m}": (fake if m == "bin/codex" else f"helper {m}\n".encode()) for m in members}
        extra = {f"{root}/codex-resources/voice/bin/codex-voice-host": b"voice", "package/package.json": b"{}",
                 "package/README.md": b"x"}
        npm = tgz({**layout, **extra})
        # tgz marks every member executable; the manifest's real mode is 0644.
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for name, data in {**layout, **extra}.items():
                info = tarfile.TarInfo(name)
                info.size, info.mode = len(data), (0o4755 if name.endswith("/rg") else 0o644 if name.endswith(".json") else 0o755)
                tar.addfile(info, io.BytesIO(data))
        npm = buf.getvalue()

        def codex_reg(body: bytes, **over: object) -> dict:
            p = {**pin, "sha256": sha(body), **over}
            return {"projects": {"agent-fabric": {"tools": [{**decl[0][1], "proof": "codex --version",
                                                             "install": {k: v for k, v in p.items() if v is not None}}]}}}

        def tree_files(home: str) -> list[str]:
            base = os.path.join(home, ".local", "lib")
            return sorted(os.path.relpath(os.path.join(d, f), base) for d, _, fs in os.walk(base) for f in fs)

        def tree_entries(home: str) -> list[str]:
            base = os.path.join(home, ".local", "lib")
            return sorted(os.path.relpath(os.path.join(d, n), base) for d, ds, fs in os.walk(base) for n in ds + fs)
        tree = lambda home: os.path.join(home, ".local", "lib", "agent-fabric-tools", "codex", "0.162.1")  # noqa: E731
        home = account("agent-fabric")
        r = tools_install.install("codex", reg=codex_reg(npm), home=home, fetch=serving(npm))
        link = os.path.join(home, ".local", "bin", "codex")
        check("installed, ~/.local/bin/codex the path it names",
              r["status"] == "installed" and r.get("path") == link and listing(home) == ["codex"], (r, listing(home)))
        check("~/.local/bin/codex is a symlink to the tree's entrypoint",
              os.path.islink(link) and os.readlink(link) == os.path.join(tree(home), "bin", "codex"), os.path.realpath(link))
        check("every member is placed at its own path under the versioned tree, and nothing else",
              tree_files(home) == sorted(f"agent-fabric-tools/codex/0.162.1/{m}" for m in members), tree_files(home))
        check("the voice resources and the package's other files are not placed",
              not any("voice" in f or "package.json" in f.replace("codex-package.json", "") for f in tree_files(home)), tree_files(home))
        check("the members keep their content",
              all(open(os.path.join(tree(home), m), "rb").read() == layout[f"{root}/{m}"] for m in members))
        modes = {m: os.stat(os.path.join(tree(home), m)).st_mode & 0o7777 for m in members}
        check("an executable member is 0755, the manifest 0644, and a setuid bit is never kept",
              modes.get("bin/codex") == 0o755 and modes.get("codex-package.json") == 0o644 and modes.get("codex-path/rg") == 0o755, modes)
        r = subprocess.run([link, "--version"], capture_output=True, text=True, timeout=30)
        check("the link runs the tree's codex", r.stdout.strip() == "codex-cli 0.162.1", r)
        again = tools_install.install("codex", reg=codex_reg(npm), home=home, fetch=never)
        check("a second run is current and fetches nothing", again["status"] == "current", again)
        os.unlink(os.path.join(tree(home), "bin", "codex-code-mode-host"))
        again = tools_install.install("codex", reg=codex_reg(npm), home=home, fetch=serving(npm))
        check("a tree missing a member is not current: it is installed again, whole",
              again["status"] == "installed" and os.path.isfile(os.path.join(tree(home), "bin", "codex-code-mode-host"))
              and tree_files(home) == sorted(f"agent-fabric-tools/codex/0.162.1/{m}" for m in members), (again, tree_files(home)))
        check("…and the tree it replaced leaves no set-aside copy",
              sorted(os.listdir(os.path.dirname(tree(home)))) == ["0.162.1"], os.listdir(os.path.dirname(tree(home))))

        print("a tree pin — the single-file install of the same version is not current")
        home = account("agent-fabric")
        with open(os.path.join(home, ".local", "bin", "codex"), "wb") as fh:
            fh.write(fake)
        os.chmod(os.path.join(home, ".local", "bin", "codex"), 0o755)
        r = tools_install.install("codex", reg=codex_reg(npm), home=home, fetch=serving(npm))
        check("codex 0.162.1 alone in ~/.local/bin (it prints the version) is replaced by the tree",
              r["status"] == "installed" and os.path.islink(os.path.join(home, ".local", "bin", "codex"))
              and listing(home) == ["codex"], (r, listing(home)))

        print("a tree pin — an upgrade removes the older version's tree")
        old_tree = os.path.join(home, ".local", "lib", "agent-fabric-tools", "codex", "0.161.0")
        os.makedirs(os.path.join(old_tree, "bin"))
        open(os.path.join(old_tree, "bin", "codex"), "w").close()
        os.unlink(os.path.join(tree(home), "codex-package.json"))
        r = tools_install.install("codex", reg=codex_reg(npm), home=home, fetch=serving(npm))
        check("only the pinned version's tree is left", r["status"] == "installed"
              and sorted(os.listdir(os.path.dirname(tree(home)))) == ["0.162.1"], (r, os.listdir(os.path.dirname(tree(home)))))

        print("a tree pin — failures leave nothing of the run, and the previous install stands")
        home = account("agent-fabric")
        r = tools_install.install("codex", reg=codex_reg(npm), home=home, fetch=serving(npm + b"x"))
        check("a tarball that is not the pinned one is refused by the hash: nothing unpacked or placed",
              r["status"] == "failed" and "sha256" in r["reason"] and listing(home) == [] and tree_entries(home) == [],
              (r, listing(home), tree_entries(home)))
        partial = tgz({k: v for k, v in layout.items() if not k.endswith("codex-code-mode-host")})
        r = tools_install.install("codex", reg=codex_reg(partial), home=home, fetch=serving(partial))
        check("an archive without one of the members: failed, named, and no member of the others is left behind",
              r["status"] == "failed" and "codex-code-mode-host" in r["reason"] and listing(home) == [] and tree_entries(home) == [],
              (r, listing(home), tree_entries(home)))
        linked = tgz({k: v for k, v in layout.items() if not k.endswith("/rg")}, link=f"{root}/codex-path/rg")
        r = tools_install.install("codex", reg=codex_reg(linked), home=home, fetch=serving(linked))
        check("a member that is a symlink in the archive: failed, nothing left",
              r["status"] == "failed" and "not a regular file" in r["reason"] and tree_entries(home) == [], (r, tree_entries(home)))
        liar = tgz({**layout, f"{root}/bin/codex": b'#!/bin/sh\necho "codex-cli 9.9.9"\n'})
        r = tools_install.install("codex", reg=codex_reg(liar), home=home, fetch=serving(liar))
        check("a tree whose entrypoint proves another version: failed, nothing left",
              r["status"] == "failed" and "does not prove" in r["reason"] and listing(home) == [] and tree_entries(home) == [],
              (r, listing(home), tree_entries(home)))
        r = tools_install.install("codex", reg=codex_reg(npm), home=home, fetch=serving(npm))
        check("the same account installs the good tree afterwards (positive control)", r["status"] == "installed", r)
        os.unlink(os.path.join(tree(home), "codex-package.json"))   # not current, so the next run fetches
        r = tools_install.install("codex", reg=codex_reg(liar), home=home, fetch=serving(liar))
        check("a bad tree over an install: failed, and the installed tree and its link are as they were",
              r["status"] == "failed" and os.path.realpath(os.path.join(home, ".local", "bin", "codex")) == os.path.join(os.path.realpath(tree(home)), "bin", "codex")
              and tree_files(home) == sorted(f"agent-fabric-tools/codex/0.162.1/{m}" for m in members if m != "codex-package.json")
              and listing(home) == ["codex"], (r, tree_entries(home), listing(home)))

        print("a tree pin — the link step fails: the new tree goes, the previous one stands (review of #229, F1)")
        home = account("agent-fabric")
        bindir = os.path.join(home, ".local", "bin")
        os.chmod(bindir, 0o555)
        try:
            r = tools_install.install("codex", reg=codex_reg(npm), home=home, fetch=serving(npm))
        finally:
            os.chmod(bindir, 0o755)
        check("~/.local/bin not writable: failed, the reason names ~/.local/bin, and no tree is left",
              r["status"] == "failed" and r["reason"].startswith(bindir + "/") and "agent-fabric-tools" not in r["reason"]
              and listing(home) == [] and tree_entries(home) == [], (r, listing(home), tree_entries(home)))
        r = tools_install.install("codex", reg=codex_reg(npm), home=home, fetch=serving(npm))
        check("…the same account installs once it is writable (positive control)", r["status"] == "installed", r)
        os.unlink(os.path.join(tree(home), "codex-package.json"))   # not current, so the next run fetches
        before = tree_files(home)
        os.chmod(bindir, 0o555)
        try:
            r = tools_install.install("codex", reg=codex_reg(npm), home=home, fetch=serving(npm))
        finally:
            os.chmod(bindir, 0o755)
        check("over an install: failed, the previous tree put back as it was, its link still resolving into it",
              r["status"] == "failed" and tree_files(home) == before
              and os.path.realpath(os.path.join(bindir, "codex")) == os.path.join(os.path.realpath(tree(home)), "bin", "codex")
              and sorted(os.listdir(os.path.dirname(tree(home)))) == ["0.162.1"], (r, tree_entries(home)))
        home = account("agent-fabric")
        os.makedirs(os.path.join(home, ".local", "bin", "codex"))
        r = tools_install.install("codex", reg=codex_reg(npm), home=home, fetch=serving(npm))
        check("~/.local/bin/codex a directory: failed, named, no tree and no temporary left",
              r["status"] == "failed" and r["reason"].startswith(os.path.join(home, ".local", "bin", "codex") + ":")
              and listing(home) == ["codex"] and tree_entries(home) == [], (r, listing(home), tree_entries(home)))

        print("a tree pin — refused before any fetch")
        home = account("agent-fabric")
        for label, over in (("a member and a tree", {"member": f"{root}/bin/codex"}),
                            ("no entrypoint", {"entrypoint": None}),
                            ("no root", {"root": None}),
                            ("an entrypoint that is not a member", {"entrypoint": "bin/other"}),
                            ("members that are not a list", {"members": "bin/codex"}),
                            ("no members", {"members": []}),
                            ("a member climbing out", {"members": [*members, "../x"]}),
                            ("an absolute member", {"members": [*members, "/etc/x"]}),
                            ("a member twice", {"members": [*members, "bin/codex"]}),
                            ("a member inside another", {"members": [*members, "bin/codex/x"]}),
                            ("a root climbing out", {"root": "package/../x"}),
                            ("a version that is a path", {"version": "0.162.1/../../x"})):
            r = tools_install.install("codex", reg=codex_reg(npm, **over), home=home, fetch=never)
            check(f"{label}: refused, nothing written", r["status"] == "refused" and listing(home) == [] and tree_entries(home) == [],
                  (r, tree_entries(home)))

        print("a tree pin — a killed run's staged and set-aside trees are swept, a live one's kept")
        home = account("agent-fabric")
        tooldir = os.path.join(home, ".local", "lib", "agent-fabric-tools", "codex")
        dead = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True, timeout=30).stdout.strip()
        for name in (f".0.162.1.{dead}.tmp", f".0.162.1.{dead}.old", f".0.162.1.{os.getpid()}.tmp"):
            os.makedirs(os.path.join(tooldir, name, "bin"))
        tools_install.sweep_trees(tooldir)
        check("the dead run's go, the live one's stays", sorted(os.listdir(tooldir)) == [f".0.162.1.{os.getpid()}.tmp"], os.listdir(tooldir))

        print("the size bound — a member past it is refused before it is placed; one under it, larger than its archive, installs")
        single = {k: v for k, v in pin.items() if k not in tools_install.TREE_FIELDS}
        single["member"] = f"{root}/bin/codex"
        saved_bound = tools_install.MAX_ASSET_BYTES
        tools_install.MAX_ASSET_BYTES = 4096
        try:
            for size, want in ((5000, "failed"), (3000, "installed")):
                body = b'#!/bin/sh\necho "codex-cli 0.162.1"\n' + b"#" * size
                arc = tgz({single["member"]: body})
                bound_reg = {"projects": {"agent-fabric": {"tools": [{**decl[0][1], "proof": "codex --version",
                                                                      "install": {**single, "sha256": sha(arc)}}]}}}
                home = account("agent-fabric")
                r = tools_install.install("codex", reg=bound_reg, home=home, fetch=serving(arc))
                check(f"a {size}-byte member under a 4096-byte bound is {'refused, and nothing is placed' if want == 'failed' else 'installed'}",
                      r["status"] == want and (listing(home) == ["codex"] if want == "installed" else listing(home) == [] and "is over" in str(r)),
                      (r, listing(home)))
            arc = tgz({**{f"{root}/{m}": b"#" * 1500 for m in members}, f"{root}/bin/codex": fake})
            home = account("agent-fabric")
            r = tools_install.install("codex", reg=codex_reg(arc), home=home, fetch=serving(arc))
            check("a tree whose members together pass the bound is refused, nothing left",
                  r["status"] == "failed" and "over" in r["reason"] and tree_entries(home) == [] and listing(home) == [], (r, tree_entries(home)))
        finally:
            tools_install.MAX_ASSET_BYTES = saved_bound

        print("fetch_https — the read cap: one byte past the bound is read and refused, never the whole stream")
        class Endless:
            """A response with no end that remembers how much was asked of it."""
            asked: list = []
            def __enter__(self): return self
            def __exit__(self, *exc): return False
            def read(self, n=None):
                assert n is not None and n >= 0, "an unbounded read of a response"
                Endless.asked.append(n)
                return b"#" * n
        real_opener, real_bound = tools_install.urllib.request.build_opener, tools_install.MAX_ASSET_BYTES
        tools_install.MAX_ASSET_BYTES = 4096
        try:
            tools_install.urllib.request.build_opener = lambda *handlers: types.SimpleNamespace(open=lambda req, timeout=None: Endless())
            try:
                tools_install.fetch_https("https://example.invalid/asset")
                refused = None
            except (ValueError, AssertionError) as e:   # the stand-in asserts on an unbounded read
                refused = str(e)
            check("an endless body is refused after reading one byte past the bound",
                  refused == "the asset is over 4096 bytes" and Endless.asked == [4097], (refused, Endless.asked))
            Endless.read = lambda self, n=None: b"#" * min(4097 if n is None else n, 4096)   # the control: a body exactly at the bound
            try:
                whole = len(tools_install.fetch_https("https://example.invalid/asset"))
            except ValueError as e:
                whole = str(e)
            check("a body of exactly the bound is returned whole", whole == 4096, whole)
        finally:
            tools_install.urllib.request.build_opener, tools_install.MAX_ASSET_BYTES = real_opener, real_bound

        print("zig — the pin the registry carries (j45)")
        zdecl = tools_install.declarations(real, "zig")
        check("herdr declares zig as an account tool", [pid for pid, _ in zdecl] == ["herdr"], zdecl)
        zpin = zdecl[0][1]["install"] if zdecl else {}
        check("the pin is the whole 0.16.0 tree from ziglang.org, by the digest ziglang.org's index.json gives",
              tools_install.check_pin(zpin) is None and zpin.get("version") == "0.16.0" and zpin.get("whole") is True
              and zpin.get("url") == "https://ziglang.org/download/0.16.0/zig-x86_64-linux-0.16.0.tar.xz"
              and zpin.get("sha256") == "70e49664a74374b48b51e6f3fdfbf437f6395d42509050588bd49abe52ba3d00"
              and zpin.get("root") == "zig-x86_64-linux-0.16.0" and zpin.get("entrypoint") == "zig" and "members" not in zpin, zpin)

        print("archives — the format is the url's, and the bytes must agree")

        def archive(entries: list[tuple], fmt: str = "xz") -> bytes:
            """entries: (name, kind, payload, mode); kind f file, d directory, s symlink (payload the target),
            h hardlink, p fifo."""
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode=f"w:{fmt}") as tar:
                for name, kind, payload, mode in entries:
                    info = tarfile.TarInfo(name)
                    info.mode = mode
                    if kind == "f":
                        info.size = len(payload)
                        tar.addfile(info, io.BytesIO(payload))
                    else:
                        info.type = {"d": tarfile.DIRTYPE, "s": tarfile.SYMTYPE, "h": tarfile.LNKTYPE, "p": tarfile.FIFOTYPE}[kind]
                        info.linkname = payload if kind in "sh" else ""
                        tar.addfile(info)
            return buf.getvalue()

        member_xz = archive([("faketool", "f", SCRIPT, 0o755), ("LICENSE", "f", b"x", 0o644)])
        home = account("pa")
        r = run(home, registry(("pa", entry(member_xz, member="faketool", url=URL + ".tar.xz"))), serving(member_xz))
        check(".tar.xz with a member: the member is placed",
              r["status"] == "installed" and open(os.path.join(home, ".local", "bin", "faketool"), "rb").read() == SCRIPT
              and listing(home) == ["faketool"], (r, listing(home)))
        member_gz = archive([("faketool", "f", SCRIPT, 0o755)], "gz")
        for url, arc_bytes, why in ((URL + ".tgz", member_gz, "a .tgz url over gzip bytes (positive control)"),
                                    (URL + ".tar.gz", member_gz, ".tar.gz over gzip bytes (positive control)")):
            home = account("pa")
            r = run(home, registry(("pa", entry(arc_bytes, member="faketool", url=url))), serving(arc_bytes))
            check(why + ": installed", r["status"] == "installed", r)
        for url, arc_bytes, want, why in ((URL + ".tar.gz", member_xz, "not gz data", "a .tar.gz url over xz bytes"),
                                          (URL + ".tar.xz", member_gz, "not xz data", "a .tar.xz url over gzip bytes"),
                                          (URL + ".tgz", member_xz, "not gz data", "a .tgz url over xz bytes")):
            home = account("pa")
            r = run(home, registry(("pa", entry(arc_bytes, member="faketool", url=url))), serving(arc_bytes))
            check(f"{why}: failed naming the mismatch, nothing placed",
                  r["status"] == "failed" and want in r["reason"] and listing(home) == [], (r, listing(home)))
        for url in (URL, URL + ".zip", URL + ".tar", "https://example.invalid/x.tar.xz.exe", "https://example.invalid/a.tar.xz/b"):
            home = account("pa")
            r = run(home, registry(("pa", entry(member_xz, member="faketool", url=url))), serving(member_xz))
            check(f"xz bytes under the url {url[-20:]!r}, which does not end .tar.xz: failed as not gz data, nothing placed",
                  r["status"] == "failed" and "not gz data" in r["reason"] and listing(home) == [], (r, listing(home)))
            home = account("pa")
            r = run(home, registry(("pa", entry(member_gz, member="faketool", url=url))), serving(member_gz))
            check(f"gzip bytes under {url[-20:]!r}: installed, as a member pin has always read (positive control)", r["status"] == "installed", r)
        home = account("pa")
        r = run(home, registry(("pa", entry(member_xz, member="faketool", url=URL + ".tar.xz?download=1"))), serving(member_xz))
        check("a query string after the suffix does not hide the format (the url's path decides)", r["status"] == "installed", r)
        truncated = member_xz[:len(member_xz) // 2]
        home = account("pa")
        r = run(home, registry(("pa", entry(truncated, member="faketool", url=URL + ".tar.xz"))), serving(truncated))
        check("an xz stream cut short (its digest matches what was served): failed as unreadable, nothing placed",
              r["status"] == "failed" and "not a readable archive" in r["reason"] and listing(home) == [], (r, listing(home)))

        print("a whole-tree pin — a directory installed under its root")
        ROOTD = "ft-1.2.3"
        W = {"root": ROOTD, "whole": True, "entrypoint": "faketool", "url": "https://example.invalid/ft-1.2.3.tar.xz", "members": None}
        base = [(ROOTD, "d", "", 0o755), (f"{ROOTD}/faketool", "f", SCRIPT, 0o755),
                (f"{ROOTD}/lib/deep/er/a.txt", "f", b"a", 0o644), (f"{ROOTD}/lib/__underscore.h", "f", b"u", 0o644),
                (f"{ROOTD}/lib/empty", "d", "", 0o755), (f"{ROOTD}/lib/alias.txt", "s", "deep/er/a.txt", 0o777),
                (f"{ROOTD}/lib/suid", "f", b"s", 0o4755), (f"{ROOTD}/lib/wide", "f", b"w", 0o666),
                ("elsewhere/x", "f", b"outside", 0o644), ("README", "f", b"outside", 0o644)]
        wtree = lambda h: os.path.join(h, ".local", "lib", "agent-fabric-tools", "faketool", "1.2.3")  # noqa: E731

        def wreg(body: bytes, **over: object) -> dict:
            return registry(("pa", entry(body, **{**W, **over})))

        def left(h: str) -> list[str]:
            base_dir = os.path.join(h, ".local", "lib")
            return sorted(os.path.relpath(os.path.join(d, n), base_dir) for d, ds, fs in os.walk(base_dir) for n in ds + fs)

        whole = archive(base)
        home = account("pa")
        r = run(home, wreg(whole), serving(whole))
        link = os.path.join(home, ".local", "bin", "faketool")
        check("installed, ~/.local/bin/faketool a link to the tree's entrypoint",
              r["status"] == "installed" and os.path.islink(link) and os.path.realpath(link) == os.path.realpath(os.path.join(wtree(home), "faketool")), (r, left(home)))
        placed = sorted(p[len(wtree(home)) + 1:] for p in (os.path.join(d, n) for d, ds, fs in os.walk(wtree(home)) for n in ds + fs))
        check("everything under the root is placed at its relative path, an empty directory and an underscore name too",
              placed == ["faketool", "lib", "lib/__underscore.h", "lib/alias.txt", "lib/deep", "lib/deep/er", "lib/deep/er/a.txt",
                         "lib/empty", "lib/suid", "lib/wide"], placed)
        check("entries outside the root are not placed", not os.path.exists(os.path.join(wtree(home), "..", "elsewhere"))
              and not any("elsewhere" in p or "README" in p for p in left(home)), left(home))
        modes = {n: os.stat(os.path.join(wtree(home), n)).st_mode & 0o7777 for n in ("faketool", "lib/suid", "lib/wide", "lib/deep/er/a.txt")}
        check("modes: execute kept, setuid and group/world write dropped",
              modes == {"faketool": 0o755, "lib/suid": 0o755, "lib/wide": 0o644, "lib/deep/er/a.txt": 0o644}, modes)
        check("a link inside the tree is kept, relative, and reads through",
              os.readlink(os.path.join(wtree(home), "lib", "alias.txt")) == "deep/er/a.txt"
              and open(os.path.join(wtree(home), "lib", "alias.txt"), "rb").read() == b"a")
        check("the link in ~/.local/bin runs the tree's tool",
              subprocess.run([link, "--version"], capture_output=True, text=True, timeout=30).stdout.strip() == "faketool v1.2.3")
        again = tools_install.install("faketool", reg=wreg(whole), home=home, fetch=never)
        check("a second run is current and fetches nothing", again["status"] == "current", again)
        os.unlink(os.path.join(wtree(home), "faketool"))
        # The link dangles, and a faketool earlier on PATH still proves as 1.2.3: only the missing entrypoint says not current.
        shadow = os.path.join(home, "shadow")
        os.makedirs(shadow)
        with open(os.path.join(shadow, "faketool"), "wb") as fh:
            fh.write(SCRIPT)
        os.chmod(os.path.join(shadow, "faketool"), 0o755)
        os.environ["PATH"] = f"{shadow}:{os.environ['PATH']}"
        again = tools_install.install("faketool", reg=wreg(whole), home=home, fetch=serving(whole))
        check("a tree whose entrypoint is gone is installed again, whole, with no set-aside copy",
              again["status"] == "installed" and os.path.isfile(os.path.join(wtree(home), "faketool"))
              and sorted(os.listdir(os.path.dirname(wtree(home)))) == ["1.2.3"], (again, left(home)))
        gz_whole = archive(base, "gz")
        home = account("pa")
        r = run(home, wreg(gz_whole, url="https://example.invalid/ft-1.2.3.tgz"), serving(gz_whole))
        check("the same tree as a .tgz installs too (the format is the url's, not the pin's kind)", r["status"] == "installed", r)
        bad_hash = run(account("pa"), wreg(whole), serving(whole + b"x"))
        check("a tree whose bytes are not the pinned digest: failed on the hash, nothing unpacked or placed",
              bad_hash["status"] == "failed" and "sha256" in bad_hash["reason"], bad_hash)

        print("a whole-tree pin — each refusal fails the run and leaves nothing (each has the good tree beside it)")
        refusals = {
            "an absolute path in the archive": (base + [("/etc/evil", "f", b"x", 0o644)], "absolute"),
            "a '..' part under the root": (base + [(f"{ROOTD}/../escape", "f", b"x", 0o644)], "'..'"),
            "a '..' part outside the root": (base + [("other/../escape", "f", b"x", 0o644)], "'..'"),
            "a symlink to an absolute path": (base + [(f"{ROOTD}/lib/abs", "s", "/etc/passwd", 0o777)], "absolute path"),
            "a symlink out of the root": (base + [(f"{ROOTD}/lib/out", "s", "../../../etc", 0o777)], "leaves the tree"),
            # Each target alone looks inside the tree (x/a -> .. is the root; l -> x/a/../.. is the root lexically);
            # only resolving l through x/a, which is a link, reaches the root's parent.
            "a symlink that reaches out through another link": (base + [(f"{ROOTD}/x", "d", "", 0o755), (f"{ROOTD}/x/a", "s", "..", 0o777),
                                                                         (f"{ROOTD}/l", "s", "x/a/../..", 0o777)], "l is a link that leaves"),
            "a file written through a link": (base + [(f"{ROOTD}/lib/via", "s", "deep", 0o777),
                                                      (f"{ROOTD}/lib/via/b.txt", "f", b"x", 0o644)], "passes through a link"),
            "a hard link": (base + [(f"{ROOTD}/lib/hard", "h", f"{ROOTD}/faketool", 0o755)], "neither a file"),
            "a fifo": (base + [(f"{ROOTD}/lib/fifo", "p", "", 0o644)], "neither a file"),
            "a file listed twice": (base + [(f"{ROOTD}/lib/deep/er/a.txt", "f", b"again", 0o644)], "twice"),
            "a file under a file": (base + [(f"{ROOTD}/lib/deep/er/a.txt/sub", "f", b"x", 0o644)], "under a file"),
            "a directory over a file": (base + [(f"{ROOTD}/lib/deep/er/a.txt", "d", "", 0o755)], "over something else"),
            "an empty path part": (base + [(f"{ROOTD}/lib//dup", "f", b"x", 0o644)], "not a clean path"),
            "no entrypoint": ([e for e in base if e[0] != f"{ROOTD}/faketool"], "holds no"),
        }
        for label, (entries, want) in refusals.items():
            bad = archive(entries)
            home = account("pa")
            r = run(home, wreg(bad), serving(bad))
            check(f"{label}: failed ({want!r}), no tree, no link, no stage",
                  r["status"] == "failed" and want in r["reason"] and left(home) == [] and listing(home) == [], (r, left(home), listing(home)))
        for label, (entries, want) in refusals.items():
            if label not in ("a symlink out of the root", "a file written through a link"):
                continue
            # The same refusal over a tree already installed leaves that install as it was.
            home = account("pa")
            run(home, wreg(whole), serving(whole))
            before = left(home)
            os.unlink(link := os.path.join(home, ".local", "bin", "faketool"))
            bad = archive(entries)
            r = run(home, wreg(bad), serving(bad))
            check(f"{label}, over an installed tree: failed, and the installed tree is as it was",
                  r["status"] == "failed" and left(home) == before and not os.path.lexists(link), (r, left(home)))
        # An escape that would have worked is the control for the three link refusals: if the check is off, the file lands.
        saved_links = tools_install._check_link
        tools_install._check_link = lambda *a: None
        try:
            bad = archive(refusals["a symlink out of the root"][0])
            home = account("pa")
            r = run(home, wreg(bad), serving(bad))
        finally:
            tools_install._check_link = saved_links
        check("(control) with the target check off, the final resolution still refuses a link out of the tree",
              r["status"] == "failed" and "leaves the tree" in r["reason"] and left(home) == [], (r, left(home)))

        print("a whole-tree pin — the bounds")
        saved_entries, saved_bytes = tools_install.MAX_TREE_ENTRIES, tools_install.MAX_ASSET_BYTES
        try:
            tools_install.MAX_TREE_ENTRIES = len([e for e in base if e[0].startswith(ROOTD + "/")])
            home = account("pa")
            r = run(home, wreg(whole), serving(whole))
            check("a tree at the entry bound installs (positive control)", r["status"] == "installed", r)
            tools_install.MAX_TREE_ENTRIES -= 1
            home = account("pa")
            r = run(home, wreg(whole), serving(whole))
            check("one entry over the bound: failed, nothing left",
                  r["status"] == "failed" and "entries" in r["reason"] and left(home) == [], (r, left(home)))
        finally:
            tools_install.MAX_TREE_ENTRIES = saved_entries
        try:
            tools_install.MAX_ASSET_BYTES = len(SCRIPT) + 4   # the sum of the files under the root, exactly
            home = account("pa")
            r = run(home, wreg(whole), serving(whole))
            check("files exactly at the size bound install (positive control)", r["status"] == "installed", r)
            tools_install.MAX_ASSET_BYTES -= 1
            home = account("pa")
            r = run(home, wreg(whole), serving(whole))
            check("files one byte past the size bound: failed, nothing left",
                  r["status"] == "failed" and "is over" in r["reason"] and left(home) == [], (r, left(home)))
        finally:
            tools_install.MAX_ASSET_BYTES = saved_bytes

        print("a whole-tree pin — the pin itself is checked")
        good = {"version": "1.2.3", "url": "https://example.invalid/x.tar.xz", "sha256": "0" * 64, **{k: v for k, v in W.items() if k not in ("url", "members")}}
        check("a whole pin as the registry would carry it is acceptable (positive control)", tools_install.check_pin(good) is None, tools_install.check_pin(good))
        for label, pin_ in (("members and whole together", {**good, "members": ["faketool"]}),
                            ("whole that is not true", {**good, "whole": "yes"}),
                            ("whole: false", {**good, "whole": False}),
                            ("no root", {k: v for k, v in good.items() if k != "root"}),
                            ("no entrypoint", {k: v for k, v in good.items() if k != "entrypoint"}),
                            ("an entrypoint with a '..' part", {**good, "entrypoint": "../x"}),
                            ("an absolute entrypoint", {**good, "entrypoint": "/bin/sh"}),
                            ("a root with a '..' part", {**good, "root": "a/../b"}),
                            ("a member beside it", {**good, "member": "faketool"})):
            check(f"{label}: refused", tools_install.check_pin(pin_) is not None, pin_)

        print("program-running pins — rustup's installer and a cargo install")
        # The fakes are real programs run by the real code: the installer dispatches on its own name
        # (rustup-init installs, anything else is a proxy), as rustup does.
        PROXY = """#!/bin/sh
case "$(basename "$0")" in
rustup) echo "rustup %(ver)s (fake)" ;;
cargo)
  if [ "$2" = install ]; then
    { printf '%%s\\n' "$0" "$@"; env | sort; } >> "$HOME/install.record"
    echo junk > "$TMPDIR/build-junk"
    [ -e "$HOME/.fake-cargo-fails" ] && { echo "error: no space left" >&2; exit 101; }
    [ -e "$HOME/.fake-cargo-sleeps" ] && { sleep 300 & echo $! > "$HOME/cargo-child.pid"; sleep 30; }
    printf '#!/bin/sh\\n' > "$CARGO_HOME/bin/cargo-ndk"; chmod +x "$CARGO_HOME/bin/cargo-ndk"
  elif [ "$2" = ndk ]; then
    [ "$RUSTUP_AUTO_INSTALL" = 0 ] || echo "$RUSTUP_AUTO_INSTALL" > "$HOME/proof-would-download-toolchain"
    [ -x "$CARGO_HOME/bin/cargo-ndk" ] && echo "cargo-ndk %(nver)s" || { echo "no such command: ndk" >&2; exit 101; }
  fi ;;
esac
"""
        INIT = """#!/bin/sh
{ printf 'name=%%s\\n' "$(basename "$0")"; printf 'arg=%%s\\n' "$@"; env | sort; } > "$HOME/init.record"
[ -e "$HOME/.fake-init-fails" ] && { echo "error: could not create $CARGO_HOME" >&2; exit 1; }
[ -e "$HOME/.fake-init-sleeps" ] && { trap '' TERM; ( trap '' TERM; sleep 300 ) & echo $! > "$HOME/init-child.pid"; wait; }
mkdir -p "$CARGO_HOME/bin"
cat > "$CARGO_HOME/bin/rustup" <<'PROXY_EOF'
%(proxy)s
PROXY_EOF
chmod +x "$CARGO_HOME/bin/rustup"
ln -sf rustup "$CARGO_HOME/bin/cargo"; ln -sf rustup "$CARGO_HOME/bin/rustc"
"""

        def init_body(ver: str = "1.29.1") -> bytes:
            proxy = PROXY % {"ver": ver, "nver": "4.1.2"}
            return (INIT % {"proxy": proxy.rstrip("\n").replace("%%", "%")}).encode()

        RURL = "https://example.invalid/rustup-init"
        NDK = {"kind": "cargo", "version": "4.1.2", "locked": True, "toolchain": "1.98.1"}

        def rustup_entry(body: bytes) -> dict:
            return {"name": "rustup", "proof": "rustup --version", "version": "per toolchain file", "why": "t", "where": "account",
                    "install": {"kind": "installer", "version": "1.29.1", "url": RURL, "sha256": sha(body)}}

        def ndk_entry(**over: object) -> dict:
            pin_ = {**NDK, **over}
            return {"name": "cargo-ndk", "proof": "cargo +1.98.1 ndk --version", "why": "t", "where": "account",
                    "install": {k: v for k, v in pin_.items() if v is not None}}

        def run_tool(tool: str, home: str, e: dict, fetch=never) -> dict:
            return tools_install.install(tool, reg=registry(("pa", e)), home=home, fetch=fetch)

        def record(home: str, name: str) -> list[str]:
            try:
                return open(os.path.join(home, name), encoding="utf-8").read().splitlines()
            except OSError:
                return []

        def flag(home: str, name: str) -> None:
            open(os.path.join(home, name), "w").close()

        def alive(pid_file: str) -> bool:
            """Whether the child a fake recorded is running; a live one is killed, so a failing run leaves none.
            A zombie is dead: in a container whose pid 1 does not reap, a killed grandchild stays one, and kill -0 says yes."""
            try:
                pid_ = int(open(pid_file).read())
                with open(f"/proc/{pid_}/stat", encoding="ascii", errors="replace") as fh:
                    state = fh.read().rsplit(")", 1)[1].split()[0]
            except (OSError, ValueError, IndexError):
                return False
            if state == "Z":
                return False
            os.kill(pid_, signal.SIGKILL)
            return True

        body = init_body()
        # The session's own values must not reach the program: a hostile CARGO_HOME would move the install
        # where the links and the proof do not look.
        hostile = {"CARGO_HOME": "/nonexistent-hostile-cargo", "RUSTUP_HOME": "/nonexistent-hostile-rustup",
                   "GITHUB_TOKEN": "ghp_hostile", "ANTHROPIC_API_KEY": "sk-hostile",
                   "HTTPS_PROXY": "http://user:hostile@proxy.invalid:3128", "SSL_CERT_FILE": "/tmp/hostile-ca.pem"}
        saved_env = {k: os.environ.get(k) for k in hostile}
        saved_bound = dict(tools_install.RUN_TIMEOUT_S)
        os.environ.update(hostile)
        calls: list[tuple] = []
        real_popen = tools_install.subprocess.Popen

        class SpyPopen(real_popen):  # type: ignore[misc, valid-type]
            def __init__(self, *a: object, **kw: object) -> None:
                calls.append((a, kw))
                super().__init__(*a, **kw)

        tools_install.subprocess.Popen = SpyPopen
        try:
            home = account("pa")
            r = run_tool("rustup", home, rustup_entry(body), serving(body))
            check("rustup: installed, naming version and path",
                  (r["status"], r.get("version"), r.get("path")) == ("installed", "1.29.1", os.path.join(home, ".local", "bin", "rustup")), r)
            rec = record(home, "init.record")
            check("the installer ran as rustup-init with exactly the fixed argv",
                  rec[0] == "name=rustup-init" and [x for x in rec if x.startswith("arg=")]
                  == ["arg=" + a for a in tools_install.RUSTUP_INIT_ARGV], rec[:9])
            check("...argv is the module's: -y --no-modify-path --profile minimal --default-toolchain none",
                  tools_install.RUSTUP_INIT_ARGV == ("-y", "--no-modify-path", "--profile", "minimal", "--default-toolchain", "none"))
            ran = [c for c in calls if os.path.basename(c[0][0][0]) == "rustup-init"]
            check("...never through a shell: an argument list, no shell=True",
                  len(ran) == 1 and isinstance(ran[0][0][0], list) and not ran[0][1].get("shell"), ran)
            check("the program's CARGO_HOME and RUSTUP_HOME are the account's, not the session's",
                  f"CARGO_HOME={home}/.cargo" in rec and f"RUSTUP_HOME={home}/.rustup" in rec and f"HOME={home}" in rec, rec)
            check("...and the session's token and key did not reach it", not any("hostile" in x for x in rec), rec)
            check("rustup, cargo and rustc are links into ~/.cargo/bin in ~/.local/bin, and nothing else is left there",
                  listing(home) == ["cargo", "rustc", "rustup"]
                  and all(os.readlink(os.path.join(home, ".local", "bin", n)) == os.path.join(home, ".cargo", "bin", n) for n in tools_install.RUSTUP_LINKS),
                  listing(home))
            check("the proof reaches rustup through those links", subprocess.run(
                [os.path.join(home, ".local", "bin", "rustup"), "--version"], capture_output=True, text=True, timeout=30).stdout.startswith("rustup 1.29.1"))
            again = run_tool("rustup", home, rustup_entry(body))
            check("a second run is current and fetches and runs nothing (the fetch is `never`)",
                  again["status"] == "current" and len([c for c in calls if os.path.basename(c[0][0][0]) == "rustup-init"]) == 1, again)
            os.unlink(os.path.join(home, ".local", "bin", "cargo"))
            half = run_tool("rustup", home, rustup_entry(body), serving(body))
            check("with a proxy link missing, rustup answering is not current: the install runs and completes the links",
                  half["status"] == "installed" and tools_install.links_in_place(home), half)

            home = account("pa")
            r = run_tool("rustup", home, rustup_entry(body), serving(body + b"#"))
            check("a digest mismatch runs nothing and places nothing",
                  r["status"] == "failed" and "sha256" in r["reason"] and record(home, "init.record") == [] and listing(home) == [], (r, listing(home)))

            home = account("pa")
            flag(home, ".fake-init-fails")
            r = run_tool("rustup", home, rustup_entry(body), serving(body))
            check("an installer that exits non-zero: failed with its last line, no link, no staging",
                  r["status"] == "failed" and "exited 1" in r["reason"] and "could not create" in r["reason"] and listing(home) == [], (r, listing(home)))

            home = account("pa")
            bad = init_body("1.0.0")
            r = run_tool("rustup", home, rustup_entry(bad), serving(bad))
            check("an installer whose result proves as another version: failed, naming both",
                  r["status"] == "failed" and "not 1.29.1" in r["reason"], r)

            home = account("pa")
            foreign = os.path.join(home, ".local", "bin", "cargo")
            with open(foreign, "w") as fh:
                fh.write("#!/bin/sh\necho mine\n")
            r = run_tool("rustup", home, rustup_entry(body), serving(body))
            check("a file at ~/.local/bin/cargo that is not a link is refused, and left as it was",
                  r["status"] == "failed" and "not a link" in r["reason"] and open(foreign).read().endswith("mine\n"), r)
            os.unlink(foreign)
            r = run_tool("rustup", home, rustup_entry(body), serving(body))
            check("...and with it gone the same install goes through (positive control)", r["status"] == "installed" and tools_install.links_in_place(home), r)

            home = account("pa")
            tools_install.RUN_TIMEOUT_S["installer"] = 1
            flag(home, ".fake-init-sleeps")
            t0 = time.monotonic()
            r = run_tool("rustup", home, rustup_entry(body), serving(body))
            took = time.monotonic() - t0
            tools_install.RUN_TIMEOUT_S.update(saved_bound)
            time.sleep(0.2)
            check("an installer past its bound (and deaf to SIGTERM) is stopped, with what it started, and the verdict says so",
                  r["status"] == "failed" and "did not finish within 1 s" in r["reason"] and took < 20
                  and not alive(os.path.join(home, "init-child.pid")) and listing(home) == [], (r, took, listing(home)))

            home = account("pa")
            bindir = os.path.join(home, ".local", "bin")
            stale, live = os.path.join(bindir, f".rustup.{2**22 + 1}.tmp"), os.path.join(bindir, f".rustup.{os.getppid()}.tmp")
            for d in (stale, live):
                os.mkdir(d)
            run_tool("rustup", home, rustup_entry(body), serving(body))
            check("the staging directory of a killed run is swept; a live pid's is left",
                  not os.path.exists(stale) and os.path.isdir(live), listing(home))
            os.rmdir(live)

            print("cargo pin — cargo install of the tool's crate")
            home = account("pa")
            r = run_tool("cargo-ndk", home, ndk_entry())
            check("without rustup it fails, saying what to install, and runs nothing",
                  r["status"] == "failed" and "tools-install rustup" in r["reason"] and record(home, "install.record") == [], r)
            run_tool("rustup", home, rustup_entry(body), serving(body))
            r = run_tool("cargo-ndk", home, ndk_entry())
            check("after rustup: installed", r["status"] == "installed" and r.get("version") == "4.1.2", r)
            rec = record(home, "install.record")
            argv = rec[:7]  # $0 and the six arguments, then the environment
            check("cargo ran as: cargo +1.98.1 install --locked --version =4.1.2 cargo-ndk (a pinned, exact, locked install)",
                  argv == [os.path.join(home, ".cargo", "bin", "cargo"), "+1.98.1", "install", "--locked", "--version", "=4.1.2", "cargo-ndk"], argv)
            check("...with the account's CARGO_HOME and not the session's", f"CARGO_HOME={home}/.cargo" in rec and not any("hostile" in x for x in rec), rec)
            n_before = len(record(home, "install.record"))
            again = run_tool("cargo-ndk", home, ndk_entry())
            check("a second run is current (the proof decides) and installs nothing",
                  again["status"] == "current" and len(record(home, "install.record")) == n_before, again)
            check("no proof ran with rustup's auto-install on, and the install itself did not turn it off",
                  not os.path.exists(os.path.join(home, "proof-would-download-toolchain"))
                  and not any(x == "RUSTUP_AUTO_INSTALL=0" for x in record(home, "install.record")), record(home, "install.record")[-12:])
            os.unlink(os.path.join(home, ".cargo", "bin", "cargo-ndk"))
            gone = run_tool("cargo-ndk", home, ndk_entry())
            check("with the tool gone the proof fails and the install runs again (the proof is not decorative)",
                  gone["status"] == "installed" and len(record(home, "install.record")) > n_before, gone)

            flag(home, ".fake-cargo-fails")
            os.unlink(os.path.join(home, ".cargo", "bin", "cargo-ndk"))
            r = run_tool("cargo-ndk", home, ndk_entry())
            os.unlink(os.path.join(home, ".fake-cargo-fails"))
            check("a failing cargo install: failed with its last line", r["status"] == "failed" and "exited 101" in r["reason"] and "no space left" in r["reason"], r)
            cargohome = os.path.join(home, ".cargo")
            check("...and its build directory is gone, though the program wrote into its TMPDIR",
                  [n for n in os.listdir(cargohome) if n.startswith(".build.")] == [], os.listdir(cargohome))
            check("...its TMPDIR was that run's own directory under ~/.cargo, not /tmp",
                  any(x.startswith(f"TMPDIR={cargohome}/.build.cargo-ndk.") for x in record(home, "install.record")), record(home, "install.record")[-20:])

            tools_install.RUN_TIMEOUT_S["cargo"] = 1
            flag(home, ".fake-cargo-sleeps")
            t0 = time.monotonic()
            r = run_tool("cargo-ndk", home, ndk_entry())
            took = time.monotonic() - t0
            os.unlink(os.path.join(home, ".fake-cargo-sleeps"))
            tools_install.RUN_TIMEOUT_S.update(saved_bound)
            time.sleep(0.2)
            check("a cargo install past its bound is stopped with its children",
                  r["status"] == "failed" and "did not finish within 1 s" in r["reason"] and took < 20
                  and not alive(os.path.join(home, "cargo-child.pid"))
                  and [n for n in os.listdir(os.path.join(home, ".cargo")) if n.startswith(".build.")] == [], (r, took))

            r = run_tool("cargo-ndk", home, {**ndk_entry(), "proof": "cargo ndk --version"})
            check("a proof that does not name the pin's toolchain is refused (the proxy has no default)",
                  r["status"] == "refused" and "cargo +1.98.1" in r["reason"], r)

            stale_build = os.path.join(home, ".cargo", f".build.cargo-ndk.{2**22 + 1}")
            os.mkdir(stale_build)
            run_tool("cargo-ndk", home, ndk_entry())
            check("the build directory of a killed run is swept", not os.path.exists(stale_build))

            os.makedirs(os.path.join(home, ".cargo", f".build.cargo-ndk.{os.getpid()}"))
            os.unlink(os.path.join(home, ".cargo", "bin", "cargo-ndk"))
            r = run_tool("cargo-ndk", home, ndk_entry())
            check("a leftover build directory of this pid (an earlier call in the process) does not fail the install",
                  r["status"] == "installed", r)

            print("a proof never lets rustup download a toolchain")
            check("tools_check.prove runs every proof with RUSTUP_AUTO_INSTALL=0, the caller's own environment or one given",
                  tools_check.prove("sh -c 'echo $RUSTUP_AUTO_INSTALL'") == ("ok", "0")
                  and tools_check.prove("sh -c 'echo $RUSTUP_AUTO_INSTALL'", env={"PATH": "/usr/bin:/bin"}) == ("ok", "0")
                  and tools_check.prove("sh -c 'echo $RUSTUP_AUTO_INSTALL'", env={"PATH": "/usr/bin:/bin", "RUSTUP_AUTO_INSTALL": "1"}) == ("ok", "0"),
                  tools_check.prove("sh -c 'echo $RUSTUP_AUTO_INSTALL'"))

            print("the link temporaries")
            home = account("pa")
            bindir = os.path.join(home, ".local", "bin")
            os.makedirs(os.path.join(home, ".cargo", "bin"))
            real_replace = tools_install.os.replace
            def interrupted(*a: object, **kw: object) -> None:
                raise tools_install.Terminated(143)
            tools_install.os.replace = interrupted
            try:
                tools_install.link_proxies(home, ("rustup",))
            except tools_install.Terminated:
                pass
            finally:
                tools_install.os.replace = real_replace
            check("a link interrupted between its symlink and its replace leaves no temporary", listing(home) == [], listing(home))
            dead_link = os.path.join(bindir, f".cargo.{2**22 + 1}.link.tmp")
            os.symlink("/nonexistent", dead_link)
            body2 = init_body()
            run_tool("rustup", home, rustup_entry(body2), serving(body2))
            check("a killed run's link temporary is swept by the next", not os.path.lexists(dead_link), listing(home))

            print("the pins themselves are checked")
            good_installer = rustup_entry(body)["install"]
            for label, pin_ in (("an installer pin", good_installer), ("a cargo pin", NDK)):
                check(f"{label} as the registry carries it is acceptable (positive control)", tools_install.check_pin(pin_) is None, tools_install.check_pin(pin_))
            for label, pin_ in (("a cargo pin without locked", {k: v for k, v in NDK.items() if k != "locked"}),
                                ("a cargo pin with locked: false", {**NDK, "locked": False}),
                                ("a cargo pin with locked: 'yes'", {**NDK, "locked": "yes"}),
                                ("a cargo pin without a version", {k: v for k, v in NDK.items() if k != "version"}),
                                ("a cargo version that is a caret range", {**NDK, "version": "^4.1.2"}),
                                ("a cargo version of two numbers", {**NDK, "version": "4.1"}),
                                ("a cargo version with an operator", {**NDK, "version": "=4.1.2"}),
                                ("a floating toolchain", {**NDK, "toolchain": "stable"}),
                                ("no toolchain", {k: v for k, v in NDK.items() if k != "toolchain"}),
                                ("a cargo pin with an extra argument field", {**NDK, "args": ["--git", "x"]}),
                                ("a cargo pin that also names a url", {**NDK, "url": RURL}),
                                ("an installer pin with a member", {**good_installer, "member": "x"}),
                                ("an installer pin with arguments", {**good_installer, "args": ["--default-toolchain", "stable"]}),
                                ("an installer pin with a bad digest", {**good_installer, "sha256": "abc"}),
                                ("an installer pin over http", {**good_installer, "url": "http://example.invalid/x"}),
                                ("an installer version of two numbers", {**good_installer, "version": "1.29"}),
                                ("a kind this installer does not know", {**good_installer, "kind": "shell"}),
                                ("a null kind", {**good_installer, "kind": None})):
                check(f"{label}: refused", tools_install.check_pin(pin_) is not None, pin_)

            check("an unknown kind is named as such, not as a stray field",
                  "kind 'shell' is not one this installer knows" in (tools_install.check_pin({**good_installer, "kind": "shell"}) or ""))

            home = account("pa")
            tools_install.exit_on_sigterm()
            tools_install.RUN_TIMEOUT_S["installer"] = 1
            saved_grace = tools_install.STOP_GRACE_S
            tools_install.STOP_GRACE_S = 3
            flag(home, ".fake-init-sleeps")
            term_timer = threading.Timer(2.0, os.kill, (os.getpid(), signal.SIGTERM))
            term_timer.start()
            t0 = time.monotonic()
            try:
                run_tool("rustup", home, rustup_entry(body), serving(body))
                stopped = False
            except tools_install.Terminated:
                stopped = True
            finally:
                term_timer.cancel()  # a run that ended early must not leave a SIGTERM for the runner
                signal.signal(signal.SIGTERM, signal.SIG_DFL)
                tools_install.STOP_GRACE_S = saved_grace
                tools_install.RUN_TIMEOUT_S.update(saved_bound)
            took = time.monotonic() - t0
            time.sleep(0.2)
            check("SIGTERM during the grace wait after a timeout still ends a TERM-deaf program with KILL (its child runs 300 s)",
                  stopped and took < 15 and not alive(os.path.join(home, "init-child.pid")), (stopped, took))

            print("an end to the run ends the program")
            home = account("pa")
            tools_install.exit_on_sigterm()
            run_tool("rustup", home, rustup_entry(body), serving(body))
            flag(home, ".fake-cargo-sleeps")
            threading.Timer(1.0, os.kill, (os.getpid(), signal.SIGTERM)).start()
            t0 = time.monotonic()
            try:
                run_tool("cargo-ndk", home, ndk_entry())
                stopped = False
            except tools_install.Terminated:
                stopped = True
            finally:
                signal.signal(signal.SIGTERM, signal.SIG_DFL)
            time.sleep(0.2)
            check("SIGTERM to the installer ends the cargo build with it, at once (the build's leader runs 30 s, its child 300 s)",
                  stopped and time.monotonic() - t0 < 15 and not alive(os.path.join(home, "cargo-child.pid")), (stopped, time.monotonic() - t0))

            print("rustup-target pin — rustup target add, proved by the list")
            TGT = {"kind": "rustup-target", "toolchain": "1.98.1", "target": "aarch64-linux-android"}
            # The decoy is a longer name that contains the target: a substring test would find it.
            RUSTUP_FAKE = """#!/bin/sh
case "$1 $2" in
"target add")
  { printf '%s\\n' "$0" "$@"; env | sort; } >> "$HOME/target.record"
  [ -e "$HOME/.fake-add-fails" ] && { echo "error: toolchain '$5' is not installed" >&2; exit 1; }
  [ -e "$HOME/.fake-add-sleeps" ] && { sleep 300 & echo $! > "$HOME/target-child.pid"; sleep 30; }
  [ -e "$HOME/.fake-add-silent" ] || echo "$3" >> "$HOME/.targets" ;;
"target list")
  echo x86_64-unknown-linux-gnu; echo aarch64-linux-androideabi
  cat "$HOME/.targets" 2>/dev/null; exit 0 ;;
esac
"""

            def target_entry(**over: object) -> dict:
                pin_ = {**TGT, **over}
                return {"name": "rust-std-aarch64-linux-android", "proof": tools_install.target_proof(TGT), "why": "t",
                        "where": "account", "install": {k: v for k, v in pin_.items() if v is not None}}

            def with_rustup(home: str) -> None:
                bin_ = os.path.join(home, ".cargo", "bin")
                os.makedirs(bin_, exist_ok=True)
                with open(os.path.join(bin_, "rustup"), "w") as fh:
                    fh.write(RUSTUP_FAKE)
                os.chmod(os.path.join(bin_, "rustup"), 0o755)

            T = "rust-std-aarch64-linux-android"
            home = account("pa")
            r = run_tool(T, home, target_entry())
            check("no rustup: failed, naming the rustup tool", r["status"] == "failed" and "tools-install rustup" in r["reason"], r)
            with_rustup(home)
            r = run_tool(T, home, target_entry())
            rec = record(home, "target.record")
            check("absent (a decoy name that contains it is listed): installed", r["status"] == "installed", r)
            check("rustup ran as: rustup target add aarch64-linux-android --toolchain 1.98.1",
                  rec[:5] == [os.path.join(home, ".cargo", "bin", "rustup"), "target", "add", "aarch64-linux-android", "--toolchain"]
                  and rec[5] == "1.98.1", rec[:7])
            check("...with the account's CARGO_HOME and RUSTUP_HOME and none of the session's",
                  f"CARGO_HOME={home}/.cargo" in rec and f"RUSTUP_HOME={home}/.rustup" in rec and not any("hostile" in x for x in rec), rec)
            args_ = [c for c in calls if c[0][0][1:3] == ["target", "add"]]
            check("...an argument list and no shell", len(args_) == 1 and isinstance(args_[0][0][0], list) and not args_[0][1].get("shell"), args_)
            again = run_tool(T, home, target_entry())
            check("a second run is current and runs rustup target add no more", again["status"] == "current"
                  and len([x for x in record(home, "target.record") if x == "add"]) == 1, again)
            home = account("pa")
            with_rustup(home)
            flag(home, ".fake-add-fails")
            r = run_tool(T, home, target_entry())
            check("a failing rustup: failed with its last line", r["status"] == "failed" and "exited 1" in r["reason"] and "not installed" in r["reason"], r)
            home = account("pa")
            with_rustup(home)
            flag(home, ".fake-add-silent")
            r = run_tool(T, home, target_entry())
            check("rustup exiting 0 without the target in the list is failed, not installed", r["status"] == "failed" and "not there" in r["reason"], r)
            home = account("pa")
            with_rustup(home)
            r = run_tool(T, home, {**target_entry(), "proof": "rustup --version"})
            check("a proof that is not the list is refused", r["status"] == "refused" and "target list --installed" in r["reason"], r)
            home = account("pa")
            with_rustup(home)
            tools_install.RUN_TIMEOUT_S["rustup-target"] = 1
            flag(home, ".fake-add-sleeps")
            r = run_tool(T, home, target_entry())
            tools_install.RUN_TIMEOUT_S.update(saved_bound)
            time.sleep(0.2)
            check("rustup past its bound is stopped with its children", r["status"] == "failed" and "did not finish within 1 s" in r["reason"]
                  and not alive(os.path.join(home, "target-child.pid")), r)
            for label, pin_ in (("a target with a space", {**TGT, "target": "x y-z"}),
                                ("an option as the target", {**TGT, "target": "--toolchain-x-y"}),
                                ("a target with a shell word", {**TGT, "target": "a-b-c;id"}),
                                ("a target of one word", {**TGT, "target": "android"}),
                                ("an uppercase target", {**TGT, "target": "Aarch64-linux-android"}),
                                ("no target", {k: v for k, v in TGT.items() if k != "target"}),
                                ("no toolchain", {k: v for k, v in TGT.items() if k != "toolchain"}),
                                ("a floating toolchain", {**TGT, "toolchain": "stable"}),
                                ("a toolchain option", {**TGT, "toolchain": "--force"}),
                                ("an extra field", {**TGT, "args": ["--force"]}),
                                ("a version field", {**TGT, "version": "1.0.0"})):
                check(f"{label}: refused", tools_install.check_pin(pin_) is not None, pin_)
            check("the pin as the registry carries it is acceptable (positive control)", tools_install.check_pin(TGT) is None, tools_install.check_pin(TGT))
            check("a triple with three words and the Android eabi form are acceptable", all(
                tools_install.check_pin({**TGT, "target": t}) is None for t in ("armv7-linux-androideabi", "x86_64-unknown-linux-gnu", "wasm32-wasip1-threads")))
        finally:
            tools_install.subprocess.Popen = real_popen
            tools_install.RUN_TIMEOUT_S.update(saved_bound)
            for k, v in saved_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

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
