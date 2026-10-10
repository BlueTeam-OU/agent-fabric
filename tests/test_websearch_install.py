#!/usr/bin/env python3
"""runtime/mcp/websearch-locale/install.py: the locale search server's entry in a login's Claude Code user
configuration. The entry's command is the Python server (bin/fabric-websearch-locale); an entry that ran the Node
server is this fabric's too, so a re-install switches each locale login, and every other key and server of the file
is kept as read. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALL = os.path.join(HERE, "runtime", "mcp", "websearch-locale", "install.py")
SERVER = "/home/x/projects/agent-fabric/bin/fabric-websearch-locale"
NODE_SERVER = "/home/x/projects/agent-fabric/runtime/mcp/websearch-locale/server.mjs"
LOCALE = "/home/x/projects/agent-fabric/identities/roles/language-culture/locale/ge/locale.json"
NODE_ENTRY = {"type": "stdio", "command": "node", "args": [NODE_SERVER], "env": {"WEBSEARCH_LOCALE_FILE": LOCALE}}
PY_ENTRY = {"type": "stdio", "command": SERVER, "args": [], "env": {"WEBSEARCH_LOCALE_FILE": LOCALE}}
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

        def config(doc) -> str:
            n[0] += 1
            path = os.path.join(t, f"c{n[0]}.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(doc if isinstance(doc, str) else json.dumps(doc))
            return path

        def run(path: str, *args: str):
            r = subprocess.run([sys.executable, "-I", INSTALL, path, *args], capture_output=True, text=True, timeout=60)
            return r.returncode, r.stdout, r.stderr

        def read(path: str):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)

        print("set")
        other = {"theme": "dark", "mcpServers": {"mine": MINE, "websearch-locale": NODE_ENTRY}, "projects": {"/p": {"a": 1}}}
        path = config(other)
        rc, out, err = run(path, "set", SERVER, LOCALE)
        got = read(path)
        check("a Node entry is rewritten to the Python one, said with a +", rc == 0 and out == f"  +  {path} mcpServers.websearch-locale\n", out + err)
        check("…and the login's other servers and keys are untouched", got["mcpServers"]["websearch-locale"] == PY_ENTRY
              and got["mcpServers"]["mine"] == MINE and got["theme"] == "dark" and got["projects"] == other["projects"], str(got))
        check("…the file stays private", oct(os.stat(path).st_mode & 0o777) == "0o600")
        rc, out, err = run(path, "set", SERVER, LOCALE)
        check("the same again changes nothing, said with a =", (rc, out) == (0, f"  =  {path} mcpServers.websearch-locale\n"), out + err)
        rc, out, err = run(path, "set", SERVER, LOCALE + ".other")
        check("another locale file rewrites it", rc == 0 and out.startswith("  +  ") and read(path)["mcpServers"]["websearch-locale"]["env"]["WEBSEARCH_LOCALE_FILE"] == LOCALE + ".other")
        path = config({"mcpServers": {"websearch-locale": MINE}})
        rc, out, err = run(path, "set", SERVER, LOCALE)
        check("an entry of that name that is the login's own is left as it is, and said", rc == 0 and out.startswith("  !  ") and read(path)["mcpServers"]["websearch-locale"] == MINE, out)
        path = config({"theme": "dark"})
        rc, out, err = run(path, "set", SERVER, LOCALE)
        check("a file with no servers gets the entry", read(path) == {"theme": "dark", "mcpServers": {"websearch-locale": PY_ENTRY}})
        path = os.path.join(t, "absent.json")
        rc, out, err = run(path, "set", SERVER, LOCALE)
        check("a file that is not there is created", rc == 0 and read(path) == {"mcpServers": {"websearch-locale": PY_ENTRY}})
        path = config({"mcpServers": {}})
        rc, out, err = run(path, "set", SERVER, LOCALE, "--dry-run")
        check("--dry-run says what it would write and writes nothing", rc == 0 and "would write" in out and read(path) == {"mcpServers": {}}, out)

        print("remove")
        for label, entry in (("the Python entry", PY_ENTRY), ("the Node entry", NODE_ENTRY)):
            path = config({"mcpServers": {"mine": MINE, "websearch-locale": entry}})
            rc, out, err = run(path, "remove")
            check(f"{label} is removed, the login's own server stays", rc == 0 and out.startswith("  -  ") and read(path) == {"mcpServers": {"mine": MINE}}, out)
        path = config({"mcpServers": {"websearch-locale": MINE}})
        rc, out, err = run(path, "remove")
        check("an entry of that name the login wrote itself is never removed", (rc, out) == (0, "") and read(path)["mcpServers"]["websearch-locale"] == MINE)
        path = config({"mcpServers": {"websearch-locale": NODE_ENTRY}})
        rc, out, err = run(path, "remove", "--dry-run")
        check("--dry-run names the removal and keeps it", "would remove" in out and "websearch-locale" in read(path)["mcpServers"], out)

        print("the harness's own WebSearch")
        path = config({"theme": "dark", "permissions": {"deny": ["Bash(rm:*)"]}})
        rc, out, err = run(path, "deny-websearch")
        got = read(path)
        check("deny adds WebSearch and the fabric's marker beside the login's own rules", got["permissions"]["deny"] == ["Bash(rm:*)", "WebSearch", "WebSearch(agent-fabric)"] and got["theme"] == "dark", str(got))
        rc, out, err = run(path, "deny-websearch")
        check("…and again changes nothing", out.startswith("  =  "), out)
        rc, out, err = run(path, "allow-websearch")
        check("allow removes both and keeps the login's own rule", read(path)["permissions"]["deny"] == ["Bash(rm:*)"], out)
        path = config({"permissions": {"deny": ["WebSearch"]}})
        rc, out, err = run(path, "allow-websearch")
        check("a WebSearch the login denied itself (no marker) is left alone", (rc, out) == (0, "") and read(path)["permissions"]["deny"] == ["WebSearch"])

        print("a file that is not JSON")
        for op, want_rc in (("set", 1), ("deny-websearch", 1), ("remove", 0), ("allow-websearch", 0)):
            path = config("{ nope")
            args = [op] + ([SERVER, LOCALE] if op == "set" else [])
            rc, out, err = run(path, *args)
            check(f"{op}: left alone, one line on stderr, exit {want_rc}, no traceback", rc == want_rc and open(path).read() == "{ nope" and "Traceback" not in err
                  and err.count("\n") == 1 and "not JSON" in err, err)
        rc, out, err = run(config({}))
        check("too few arguments: usage on stderr, exit 2", rc == 2 and "install.py" in err)

    print("test_websearch_install:", "OK" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
