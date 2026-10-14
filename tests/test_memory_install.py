#!/usr/bin/env python3
"""tests/test_memory_install.py: runtime/mcp/fabric-memory/install.py, the fabric-memory entry in a login's Claude Code
user configuration (ADR-049 §5 rule 1). Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALL = os.path.join(HERE, "runtime", "mcp", "fabric-memory", "install.py")
ENTRY = {"type": "stdio", "command": "fabric-memory-mcp", "args": [], "env": {}}
MINE = {"command": "x", "args": ["--mine"]}


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    with tempfile.TemporaryDirectory() as t:
        n = [0]

        def config(doc, mode: int = 0o600) -> str:
            n[0] += 1
            path = os.path.join(t, f"c{n[0]}.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(doc if isinstance(doc, str) else json.dumps(doc))
            os.chmod(path, mode)
            return path

        def run(path: str, *args: str):
            r = subprocess.run([sys.executable, "-I", INSTALL, path, "set", *args], capture_output=True, text=True, timeout=60)
            return r.returncode, r.stdout, r.stderr

        def read(path: str):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)

        print("fresh file")
        path = os.path.join(t, "absent.json")
        rc, out, err = run(path)
        check("a file that is not there is created with the entry, said with a +",
              rc == 0 and out == f"  +  {path} mcpServers.fabric-memory\n" and read(path) == {"mcpServers": {"fabric-memory": ENTRY}}, out + err)
        check("…private", oct(os.stat(path).st_mode & 0o777) == "0o600")
        path = config({"theme": "dark"})
        rc, out, err = run(path)
        check("a file with no servers keeps its keys and gets the entry", rc == 0 and read(path) == {"theme": "dark", "mcpServers": {"fabric-memory": ENTRY}}, err)

        print("other servers")
        other = {"theme": "dark", "mcpServers": {"mine": MINE, "websearch-locale": {"type": "stdio", "command": "w", "args": [], "env": {"K": "v"}}},
                 "projects": {"/p": {"a": 1}}}
        path = config(other, 0o640)
        rc, out, err = run(path)
        got = read(path)
        check("the login's other servers and keys are kept as read",
              rc == 0 and got["mcpServers"]["fabric-memory"] == ENTRY and got["mcpServers"]["mine"] == MINE
              and got["mcpServers"]["websearch-locale"] == other["mcpServers"]["websearch-locale"]
              and got["theme"] == "dark" and got["projects"] == other["projects"], str(got))
        check("an existing file keeps its mode", oct(os.stat(path).st_mode & 0o777) == "0o640", oct(os.stat(path).st_mode & 0o777))
        check("no temporary file is left beside it", not any(f.endswith(".tmp") for f in os.listdir(t)), str(os.listdir(t)))

        print("idempotent")
        before = open(path, encoding="utf-8").read()
        rc, out, err = run(path)
        check("the same again changes nothing, said with a =", (rc, out) == (0, f"  =  {path} mcpServers.fabric-memory\n"), out + err)
        check("…byte for byte", open(path, encoding="utf-8").read() == before)
        path = config({"mcpServers": {"fabric-memory": {**ENTRY, "command": "fabric-memory-mcp", "args": ["old"]}}})
        rc, out, err = run(path)
        check("our entry with a stale shape is rewritten", rc == 0 and out.startswith("  +  ") and read(path)["mcpServers"]["fabric-memory"] == ENTRY, out + err)

        print("the login's own entry of that name")
        path = config({"mcpServers": {"fabric-memory": MINE}})
        rc, out, err = run(path)
        check("is left as it is, and said", rc == 0 and out.startswith("  !  ") and read(path)["mcpServers"]["fabric-memory"] == MINE, out + err)

        print("dry run")
        path = config({"mcpServers": {}})
        rc, out, err = run(path, "--dry-run")
        check("--dry-run says what it would write and writes nothing", rc == 0 and "would write" in out and read(path) == {"mcpServers": {}}, out)

        print("malformed")
        for label, doc in (("not JSON", "{not json"), ("a JSON list", "[1, 2]"), ("empty", ""),
                           ("mcpServers a list", '{"mcpServers": []}'), ("mcpServers a string", '{"mcpServers": "x"}'),
                           ("mcpServers null", '{"mcpServers": null}')):
            path = config(doc)
            rc, out, err = run(path)
            check(f"{label}: exit 3, one line on stderr, the file untouched", rc == 3 and out == "" and err.count("\n") == 1
                  and open(path, encoding="utf-8").read() == doc and not [f for f in os.listdir(t) if f.endswith(".tmp")], f"{rc} {out!r} {err!r}")

        print("a file that cannot be read")
        unreadable = config("{}")
        os.chmod(unreadable, 0)
        directory = os.path.join(t, "adir.json")
        os.mkdir(directory)
        cases = [("a directory", directory)]
        if os.geteuid() != 0:   # root reads a mode-000 file
            cases.insert(0, ("mode 000", unreadable))
        for label, path in cases:
            rc, out, err = run(path)
            check(f"{label}: exit 3, one line naming the path and why, nothing written, no traceback",
                  rc == 3 and out == "" and "Traceback" not in err and err.count("\n") == 1 and path in err and "unreadable" in err
                  and not [f for f in os.listdir(t) if f.endswith(".tmp")], f"{rc} {out!r} {err!r}")
        check("mode 000 file or directory: still as it was", os.path.isdir(directory) and os.stat(unreadable).st_mode & 0o777 == 0)
        os.chmod(unreadable, 0o600)

        print("the temporary file")
        import importlib.util
        spec = importlib.util.spec_from_file_location("fabric_memory_install", INSTALL)
        inst = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(inst)
        opened: list[tuple] = []
        real_open = os.open

        def spy(p, flags, mode=0o777, **kw):
            opened.append((p, flags, mode))
            return real_open(p, flags, mode, **kw)
        path = os.path.join(t, "spy.json")
        os.open = spy
        try:
            old_umask = os.umask(0)             # the widest umask: only the explicit 0600 can keep the file private
            try:
                inst.save(path, {"a": 1})
            finally:
                os.umask(old_umask)
        finally:
            os.open = real_open
        want = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        check("the temp file is created with O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW and mode 0600",
              len(opened) == 1 and opened[0][1] == want and opened[0][2] == 0o600, str(opened))
        check("...named with this process's pid, so a concurrent install has its own", f".{os.getpid()}." in opened[0][0], str(opened))
        check("...and the result is private and the temp is gone", oct(os.stat(path).st_mode & 0o777) == "0o600"
              and not [f for f in os.listdir(t) if f.endswith(".tmp")])

        print("a stale temp under this pid")
        for kind in ("a 0644 file", "a symlink"):
            d = os.path.join(t, "stale-" + kind.split()[-1])
            os.makedirs(d)
            path = os.path.join(d, "config.json")
            stale = f"{path}.agent-fabric.{os.getpid()}.tmp"
            victim = os.path.join(d, "victim.txt")
            with open(victim, "w", encoding="utf-8") as fh:
                fh.write("untouched")
            if kind == "a symlink":
                os.symlink(victim, stale)
            else:
                with open(stale, "w", encoding="utf-8") as fh:
                    fh.write("leftover of a killed run, wider than 0600")
                os.chmod(stale, 0o644)
            keeper = os.path.join(d, "keeper")
            if kind != "a symlink":
                os.link(stale, keeper)          # a second name for the leftover: written through, it would change too
            inst.save(path, {"a": 1})
            with open(path, encoding="utf-8") as fh:
                saved = fh.read()
            with open(victim, encoding="utf-8") as fh:
                victim_text = fh.read()
            check(f"{kind} at the temp name is replaced: the result is the new JSON, private, the temp gone, the link's target untouched",
                  json.loads(saved) == {"a": 1} and oct(os.stat(path).st_mode & 0o777) == "0o600" and not os.path.lexists(stale)
                  and victim_text == "untouched", f"{saved!r} {victim_text!r}")
            if kind != "a symlink":
                with open(keeper, encoding="utf-8") as fh:
                    kept = fh.read()
                check("...and the leftover was unlinked, not written through: its other name still holds the old text at 0644",
                      kept == "leftover of a killed run, wider than 0600" and oct(os.stat(keeper).st_mode & 0o777) == "0o644", kept)

        print("usage")
        r = subprocess.run([sys.executable, "-I", INSTALL, os.path.join(t, "x.json"), "remove"], capture_output=True, text=True, timeout=60)
        check("an op other than set exits 2", r.returncode == 2, r.stderr[:100])

    print(f"{'FAIL' if fails else 'ok'}: {fails} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
