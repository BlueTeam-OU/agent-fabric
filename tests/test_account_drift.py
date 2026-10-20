#!/usr/bin/env python3
"""bin/fabric-drift (tools/fabric/account_drift.py): what in an account
differs from what the fabric wrote — ok, edited, missing, unreadable and
stale, the streams and the exit status, and that it only reads.

Two kinds of fixture. The classes are driven through the installed wrapper
copied, with the module and fabric_writes.py, into a scratch checkout whose
tools/fabric/bootstrap.py is a stand-in printing the dry run's lines the case
chooses (its output grammar is the contract the module reads; the real one
is run in the last cases, against a scratch HOME). Nothing here reads this
account: HOME, the state directory and TMPDIR are under one mkdtemp, and the
environment of every child is built here, not inherited.

Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import account_drift  # noqa: E402

STUB = '''import os, sys
d = os.environ["STUB_DIR"]
sys.stdout.write(open(os.path.join(d, "out")).read())
sys.stderr.write(open(os.path.join(d, "err")).read())
if os.path.exists(os.path.join(d, "child")):
    import subprocess
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
    open(os.path.join(d, "child-pid"), "w").write(str(p.pid))
    time.sleep(600)
sys.exit(int(open(os.path.join(d, "rc")).read()))
'''
fails = 0


def check(label: str, good: bool, detail: str = "") -> None:
    global fails
    print(f"  {'ok  ' if good else 'FAIL'} {label}")
    if not good and detail:
        print("      " + str(detail).replace("\n", "\n      "))
    fails += not good


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class World:
    """A scratch account and a scratch checkout holding the wrapper."""

    def __init__(self, tmp: str) -> None:
        self.tmp = tmp
        self.home = os.path.join(tmp, "home")
        self.state = os.path.join(tmp, "state")
        self.stub = os.path.join(tmp, "stub")
        self.root = os.path.join(tmp, "root")
        for d in (self.home, self.state, self.stub, os.path.join(self.root, "bin"), os.path.join(self.root, "tools", "fabric")):
            os.makedirs(d)
        shutil.copy(os.path.join(ROOT, "bin", "fabric-drift"), os.path.join(self.root, "bin", "fabric-drift"))
        for m in ("account_drift.py", "fabric_writes.py"):
            shutil.copy(os.path.join(ROOT, "tools", "fabric", m), os.path.join(self.root, "tools", "fabric", m))
        with open(os.path.join(self.root, "tools", "fabric", "bootstrap.py"), "w") as f:
            f.write(STUB)
        self.dry("", rc=0)
        self.record_dir = os.path.join(self.state, "agents", self.login())

    @staticmethod
    def login() -> str:
        import pwd
        return pwd.getpwuid(os.geteuid()).pw_name

    def dry(self, out: str, err: str = "", rc: int = 0) -> None:
        for name, v in (("out", out), ("err", err), ("rc", str(rc))):
            with open(os.path.join(self.stub, name), "w") as f:
                f.write(v)

    def write(self, rel: str, content: bytes) -> str:
        p = os.path.join(self.home, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(content)
        return p

    def record(self, entries: dict[str, str] | str) -> None:
        os.makedirs(self.record_dir, exist_ok=True)
        with open(os.path.join(self.record_dir, "fabric-written.json"), "w") as f:
            f.write(entries if isinstance(entries, str) else json.dumps(entries))

    def env(self) -> dict[str, str]:
        return {"HOME": self.home, "PATH": "/usr/bin:/bin", "AGENT_FABRIC_STATE_DIR": self.state,
                "STUB_DIR": self.stub, "TMPDIR": self.tmp, "LC_ALL": "C.UTF-8"}

    def run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([os.path.join(self.root, "bin", "fabric-drift"), *args], capture_output=True, text=True,
                              env=self.env(), timeout=120, check=False, stdin=subprocess.DEVNULL)

    def tree(self) -> list[tuple[str, int, str]]:
        """Every file under the scratch account, state and checkout, with its size and mtime, to show a run changed none."""
        out = []
        for base in (self.home, self.state, self.root):
            for d, _, files in os.walk(base):
                for n in files:
                    p = os.path.join(d, n)
                    st = os.stat(p)
                    out.append((p, st.st_size, str(st.st_mtime_ns)))
        return sorted(out)


def lines(r: subprocess.CompletedProcess) -> list[str]:
    return r.stdout.splitlines()


def classes(tmp: str) -> None:
    w = World(tmp)
    a = w.write(".claude/agents/a.md", b"agent a\n")
    b = w.write(".claude/agents/b.md", b"agent b\n")
    c = w.write(".claude/hooks/c.py", b"hook c\n")
    w.record({a: sha(b"agent a\n"), b: sha(b"agent b\n"), c: sha(b"hook c\n")})
    w.dry(f"agent-fabric bootstrap for agent x\n  =  {a}\n  =  {b}\n  =  {c}\nbootstrap: 0 written, 3 already current.\n")

    w.run()   # warm: the first run leaves the checkout's bytecode, which is not the account
    before = w.tree()
    r = w.run()
    check("clean account: counts only, exit 0, nothing on stderr",
          (r.returncode, r.stdout, r.stderr) == (0, "ok 3, edited 0, missing 0, unreadable 0, retired 0, stale 0\n", ""), (r.returncode, r.stdout, r.stderr))
    check("a run changes no file of the account, the state or the checkout", w.tree() == before)

    with open(a, "wb") as f:
        f.write(b"agent a, edited by a person\n")
    r = w.run()
    check("edited: the path is named, counts last, exit 1",
          (r.returncode, lines(r)) == (1, [f"edited     {a}", "ok 2, edited 1, missing 0, unreadable 0, retired 0, stale 0"]), (r.returncode, r.stdout))
    with open(a, "wb") as f:
        f.write(b"agent a\n")

    os.unlink(b)
    w.dry(f"  +  {b} (would write)\n")
    r = w.run()
    check("missing: the path is named, exit 1",
          (r.returncode, lines(r)) == (1, [f"missing    {b}", "ok 2, edited 0, missing 1, unreadable 0, retired 0, stale 0"]), (r.returncode, r.stdout))
    with open(b, "wb") as f:
        f.write(b"agent b\n")

    w.dry(f"  =  {a}\n  +  {c} (would write)\n")
    r = w.run()
    check("stale: the dry run would rewrite a path the account holds as the fabric wrote it",
          (r.returncode, lines(r)) == (1, [f"stale      {c}", "ok 3, edited 0, missing 0, unreadable 0, retired 0, stale 1"]), (r.returncode, r.stdout))

    new = os.path.join(w.home, ".claude", "new.md")
    link = os.path.join(w.home, ".local", "bin", "tool")
    w.dry(f"  +  {new} (would write)\n  +  {link} -> {w.root}/bin/tool (would link)\n"
          f"  +  {w.home}/.claude/settings.json fabric user settings (would write)\n"
          "  +  episodic journal: would import this account's GZCoord history, once\n"
          "  =  /somewhere/else\n  !  something (would write)\n")
    r = w.run()
    check("stale: a path never recorded, a link, a path with words after it; the line that is not a file is not a finding",
          (r.returncode, lines(r)) == (1, [f"stale      {new}", f"stale      {link} -> {w.root}/bin/tool",
                                           f"stale      {w.home}/.claude/settings.json fabric user settings",
                                           "ok 3, edited 0, missing 0, unreadable 0, retired 0, stale 3"]), (r.returncode, r.stdout))

    os.unlink(b)
    with open(a, "wb") as f:
        f.write(b"edited\n")
    w.dry(f"  +  {a} (would write)\n  +  {b} (would write)\n  +  {a}.extra (would write)\n")
    r = w.run()
    check("a would-write that an edited or missing path explains is not counted a second time; a longer name is not explained by a prefix",
          (r.returncode, lines(r)) == (1, [f"edited     {a}", f"missing    {b}", f"stale      {a}.extra",
                                           "ok 1, edited 1, missing 1, unreadable 0, retired 0, stale 1"]), (r.returncode, r.stdout))
    with open(a, "wb") as f:
        f.write(b"agent a\n")
    with open(b, "wb") as f:
        f.write(b"agent b\n")

    with open(a, "wb") as f:
        f.write(b"edited\n")
    spaced = f"{a} dir/f"
    w.dry(f"  +  {spaced} (would write)\n")
    r = w.run()
    check("a longer name with a space after an edited path is not explained by it",
          (r.returncode, lines(r)) == (1, [f"edited     {a}", f"stale      {spaced}", "ok 2, edited 1, missing 0, unreadable 0, retired 0, stale 1"]), (r.returncode, r.stdout))
    with open(a, "wb") as f:
        f.write(b"agent a\n")

    gone = os.path.join(w.home, ".claude", "commands", "role.md")
    w.record({a: sha(b"agent a\n"), gone: sha(b"x")})
    w.dry(f"  -  {gone} (would remove: /role is retired)\n")
    r = w.run()
    check("retired: a recorded path the fabric removed itself and no longer writes is counted, not a finding, exit 0",
          (r.returncode, r.stdout) == (0, "ok 1, edited 0, missing 0, unreadable 0, retired 1, stale 0\n"), (r.returncode, r.stdout))
    w.dry(f"  +  {gone} (would write)\n")
    r = w.run()
    check("the same absent path is missing once the fabric would write it",
          (r.returncode, lines(r)) == (1, [f"missing    {gone}", "ok 1, edited 0, missing 1, unreadable 0, retired 0, stale 0"]), (r.returncode, r.stdout))

    w.dry(f"  +  {w.home}/.claude.json mcpServers.fabric-memory (would write)\n  +  {w.home}/p: trusted in Claude Code, its external imports approved (would write)\n")
    w.record({a: sha(b"agent a\n")})
    r = w.run()
    check("the dry run's lines about ~/.claude.json are not read",
          (r.returncode, r.stdout) == (0, "ok 1, edited 0, missing 0, unreadable 0, retired 0, stale 0\n"), (r.returncode, r.stdout))

    fifo = os.path.join(w.home, "fifo")
    os.mkfifo(fifo)
    zero = os.path.join(w.home, "zero")
    os.symlink("/dev/zero", zero)
    w.record({a: sha(b"agent a\n"), fifo: sha(b"x"), zero: sha(b"x")})
    w.dry("")
    t0 = time.monotonic()
    r = subprocess.run([os.path.join(w.root, "bin", "fabric-drift")], capture_output=True, text=True, env=w.env(), timeout=30, check=False, stdin=subprocess.DEVNULL)
    check("a recorded pipe, or a link to an endless device, is unreadable at once and is not opened",
          (r.returncode, r.stdout.splitlines()) == (1, [f"unreadable {fifo}: not a regular file", f"unreadable {zero}: not a regular file",
                                                        "ok 1, edited 0, missing 0, unreadable 2, retired 0, stale 0"]) and time.monotonic() - t0 < 20, (r.returncode, r.stdout))
    os.unlink(fifo)
    os.unlink(zero)
    w.record({a: sha(b"agent a\n"), b: sha(b"agent b\n"), c: sha(b"hook c\n")})

    d = os.path.join(w.home, "adir")
    os.mkdir(d)
    w.record({a: sha(b"agent a\n"), d: sha(b"x")})
    w.dry("")
    r = w.run()
    check("unreadable: a recorded path that is there and cannot be read is its own kind, with the error",
          (r.returncode, lines(r)) == (1, [f"unreadable {d}: not a regular file", "ok 1, edited 0, missing 0, unreadable 1, retired 0, stale 0"]), (r.returncode, r.stdout))

    w.record({a: sha(b"agent a\n"), os.path.join(w.home, "no-such-dir", "x"): sha(b"x")})
    w.dry(f"  +  {os.path.join(w.home, 'no-such-dir', 'x')} (would write)\n")
    r = w.run()
    check("a recorded path under a parent that is a file or absent reads missing, not unreadable",
          (r.returncode, lines(r)[0]) == (1, f"missing    {os.path.join(w.home, 'no-such-dir', 'x')}"), (r.returncode, r.stdout))

    w.record({a: sha(b"agent a\n"), b: sha(b"agent b\n")})
    w.dry(f"  +  {new} (would write)\n  +  {b} (would write)\n")
    os.unlink(b)
    r = w.run("--json")
    try:
        doc = json.loads(r.stdout)
    except ValueError:
        doc = None
    check("--json is the same data: status, counts, findings in the text's order",
          r.returncode == 1 and doc == {"status": "drift", "counts": {"ok": 1, "edited": 0, "missing": 1, "unreadable": 0, "retired": 0, "stale": 1},
                                        "findings": [{"kind": "missing", "path": b}, {"kind": "stale", "path": new}]}, (r.returncode, r.stdout))
    with open(b, "wb") as f:
        f.write(b"agent b\n")
    w.dry("")
    r = w.run("--json")
    check("--json on a clean account: status ok, no findings, exit 0",
          (r.returncode, json.loads(r.stdout)) == (0, {"status": "ok", "counts": {"ok": 2, "edited": 0, "missing": 0, "unreadable": 0, "retired": 0, "stale": 0}, "findings": []}), (r.returncode, r.stdout))

    r = w.run("--help")
    check("--help: the usage on stdout, exit 0", r.returncode == 0 and "usage: fabric-drift [--json]" in r.stdout and r.stderr == "", (r.returncode, r.stderr))
    for argv in (["--bogus"], ["--json", "extra"], ["--fix"]):
        r = w.run(*argv)
        check(f"{' '.join(argv)}: unknown argument, nothing on stdout, exit 2",
              (r.returncode, r.stdout, r.stderr) == (2, "", f"fabric-drift: unknown argument {argv[-1]}\n"), (r.returncode, r.stdout, r.stderr))


def cannot_be_checked(tmp: str) -> None:
    """Exit 2, one line, nothing on stdout: unknown is never ok."""
    w = World(tmp)
    a = w.write("a", b"a")
    good = {a: sha(b"a")}

    def refused(label: str, part: str) -> None:
        r = w.run()
        check(label, r.returncode == 2 and r.stdout == "" and r.stderr.startswith("fabric-drift: ") and part in r.stderr
              and len(r.stderr.splitlines()) == 1, (r.returncode, r.stdout, r.stderr))

    refused("no record: the account has not been bootstrapped", "no record at")
    w.record("not json {")
    refused("a record that is not JSON", "cannot read the record")
    w.record("[]")
    refused("a record that is a list", "is not a map of absolute paths to hashes")
    w.record({"relative/path": sha(b"a")})
    refused("a record naming a relative path", "is not a map of absolute paths to hashes")
    w.record({a: 7})
    refused("a record whose hash is not a string", "is not a map of absolute paths to hashes")
    os.makedirs(w.record_dir, exist_ok=True)
    rec = os.path.join(w.record_dir, "fabric-written.json")
    os.unlink(rec)
    os.mkdir(rec)
    refused("a record that is a directory", "cannot read the record")
    os.rmdir(rec)

    w.record(good)
    w.dry("  +  /x (would write)\n", err="bootstrap: install: cannot read /y\n", rc=3)
    refused("bootstrap --dry-run failing: its status and last stderr line, no partial report", "exited 3: bootstrap: install: cannot read /y")
    w.dry("", rc=1)
    refused("bootstrap --dry-run failing silent: its status", "exited 1")
    os.unlink(os.path.join(w.root, "tools", "fabric", "bootstrap.py"))
    refused("bootstrap.py missing from the checkout", "exited 2")


def bounded(tmp: str) -> None:
    w = World(tmp)
    a = w.write("a", b"a")
    w.record({a: sha(b"a")})
    open(os.path.join(w.stub, "child"), "w").close()
    t0 = time.monotonic()
    os.environ["STUB_DIR"] = w.stub   # the in-process call reads the environment the wrapper's caller would hand it
    try:
        account_drift.check(state=w.record_dir, root=w.root, home=w.home, timeout=1.0)
        msg = None
    except account_drift.DriftError as e:
        msg = str(e)
    finally:
        del os.environ["STUB_DIR"]
    took = time.monotonic() - t0
    check("a dry run that outlasts its bound is a DriftError naming the bound, and returns near it", msg == "bootstrap --dry-run did not finish in 1 s" and took < 30, (msg, took))
    pid = None
    for _ in range(100):
        try:
            pid = int(open(os.path.join(w.stub, "child-pid")).read())
            break
        except (OSError, ValueError):
            time.sleep(0.05)
    gone = False
    for _ in range(200):
        try:
            with open(f"/proc/{pid}/stat") as f:
                gone = f.read().rsplit(")", 1)[1].split()[0] == "Z"   # nobody reaps an orphan in a container whose pid 1 does not wait
        except OSError:
            gone = True
        if gone:
            break
        time.sleep(0.05)
    check("the child bootstrap started is killed with it, not left running", pid is not None and gone, f"child pid {pid}")
    if pid and not gone:
        os.kill(pid, signal.SIGKILL)


def real_dry_run(tmp: str) -> None:
    """The real bootstrap --dry-run against a scratch HOME: the line grammar
    the module reads is the one bootstrap prints, and a dry run writes nothing."""
    home = os.path.join(tmp, "home")
    state = os.path.join(tmp, "state")
    os.makedirs(home)
    login = World.login()
    explained = os.path.join(home, ".claude", "agents", "code-low.md")
    os.makedirs(os.path.join(state, "agents", login))
    with open(os.path.join(state, "agents", login, "fabric-written.json"), "w") as f:
        json.dump({explained: sha(b"x")}, f)
    env = {"HOME": home, "PATH": "/usr/bin:/bin", "AGENT_FABRIC_STATE_DIR": state, "TMPDIR": tmp, "LC_ALL": "C.UTF-8"}
    r = subprocess.run([os.path.join(ROOT, "bin", "fabric-drift"), "--json"], capture_output=True, text=True, env=env, timeout=120, check=False,
                       stdin=subprocess.DEVNULL)
    try:
        doc = json.loads(r.stdout)
    except ValueError:
        doc = {"findings": [], "counts": {}}
    by = {f["path"]: f["kind"] for f in doc["findings"]}
    other = os.path.join(home, ".claude", "agents", "code-high.md")
    check("real dry run: exit 1 and a document on stdout", r.returncode == 1 and doc.get("status") == "drift", (r.returncode, r.stderr[-300:]))
    check("real dry run: a recorded path the fabric would write is missing, and not also stale",
          by.get(explained) == "missing" and doc["counts"].get("stale", 0) > 0 and explained not in [f["path"] for f in doc["findings"] if f["kind"] == "stale"], by.get(explained))
    check("real dry run: a path the fabric would write and the record does not hold is stale", by.get(other) == "stale", by.get(other))
    check("real dry run: a link line is stale too, named with its target",
          any(f["kind"] == "stale" and " -> " in f["path"] and f["path"].startswith(os.path.join(home, ".local", "bin") + "/") for f in doc["findings"]))
    left = sorted(os.listdir(home)), sorted(os.listdir(state))
    check("real dry run: nothing is written to the account's home or the state directory", left == ([], ["agents"]), left)


def main() -> int:
    for case in (classes, cannot_be_checked, bounded, real_dry_run):
        tmp = tempfile.mkdtemp(prefix="drift-test-")
        try:
            case(tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"{fails} failed" if fails else "all passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
