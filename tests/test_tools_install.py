#!/usr/bin/env python3
"""tools/fabric/tools_install.py (fabric-tools --install): the account tool
a project pins is installed from its pinned release into ~/.local/bin, only
where a working copy of the declaring project exists, hash first, proof
before the rename. No network and no real gh: the fetch is a function the
test hands in. A negative case runs beside its positive control."""
from __future__ import annotations

import hashlib
import io
import os
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
from git_env import git_env, scrub_process_env  # noqa: E402 — tests/, the script's own directory
scrub_process_env()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import tools_check  # noqa: E402,F401
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

        print("the https-only redirect")
        h = tools_install._HttpsOnly()
        try:
            h.redirect_request(None, None, 302, "Found", {}, "http://example.invalid/x")
            refused_redirect = False
        except urllib.error.URLError:
            refused_redirect = True
        check("a redirect off https is refused", refused_redirect)

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
