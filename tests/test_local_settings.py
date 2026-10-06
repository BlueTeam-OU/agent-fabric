#!/usr/bin/env python3
"""Tests for tools/fabric/local_settings.py: what `report` says of each
account's .claude/settings.local.json (names and counts, never a value)
and what `prune` removes (the synced-secret env entries, nothing else),
against a scratch home."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(HERE, "tools", "fabric", "local_settings.py")
spec = importlib.util.spec_from_file_location("local_settings", TOOL)
ls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ls)

VALUE = "planted-value-never-reported"


def make_home(tmp: str) -> tuple[str, callable]:
    home = os.path.join(tmp, "home")
    cfg = os.path.join(home, ".config", "agent-fabric")
    os.makedirs(cfg)
    with open(os.path.join(cfg, "secrets.env"), "w") as fh:
        fh.write(f"# agent-fabric secrets\nexport OPENAI_API_KEY='{VALUE}'\nexport DEMO_PORT_OFFSET=640\n")
    with open(os.path.join(cfg, "env.sh"), "w") as fh:
        fh.write("# agent-fabric secrets\nexport DEMO_PORT_OFFSET=640\n")

    def put(wc: str, doc, mode: int = 0o600) -> str:
        path = os.path.join(home, "projects", wc, ".claude", "settings.local.json") if wc else \
            os.path.join(home, "projects", ".claude", "settings.local.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(doc if isinstance(doc, str) else json.dumps(doc, indent=2))
        os.chmod(path, mode)
        return path
    return home, put


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    with tempfile.TemporaryDirectory() as tmp:
        home, put = make_home(tmp)
        s = ls.secret_names(home)
        check("a synced secret: a secrets.env name that is not plain, or a harness credential",
              {"OPENAI_API_KEY", "CLAUDE_BRIDGE_AUTH_TOKEN", "GH_TOKEN"} <= s and "DEMO_PORT_OFFSET" not in s, sorted(s))

        put("alpha", {"env": {"CLAUDE_BRIDGE_AUTH_TOKEN": VALUE, "DEMO_PORT_OFFSET": "640", "MY_FLAG": "1"},
                      "permissions": {"allow": ["Bash(ls)", "Read"], "deny": ["Bash(rm)"]}, "enableAllProjectMcpServers": True})
        put("beta", {})
        put("gamma", "{not json")
        put("", {"env": {"GH_TOKEN": VALUE}})
        os.makedirs(os.path.join(home, "projects", "delta"))
        r = ls.report(home)
        check("one row per settings file, the projects root first; a clone without one is not listed",
              [f["working_copy"] for f in r["files"]] == [ls.ROOT_LABEL, "alpha", "beta", "gamma"], r)
        a = r["files"][1]
        check("names, secrets marked, permission counts, other keys",
              (a["env"], a["secrets"], a["permissions"], a["keys"]) ==
              (["CLAUDE_BRIDGE_AUTH_TOKEN", "DEMO_PORT_OFFSET", "MY_FLAG"], ["CLAUDE_BRIDGE_AUTH_TOKEN"],
               {"allow": 2, "deny": 1, "ask": 0}, ["enableAllProjectMcpServers"]), a)
        check("an unparsable file is said, not a crash", r["files"][3]["status"] == "not json", r["files"][3])
        check("no value in the report", VALUE not in json.dumps(r))

    with tempfile.TemporaryDirectory() as tmp:
        home, put = make_home(tmp)
        f = put("alpha", {"env": {"CLAUDE_BRIDGE_AUTH_TOKEN": VALUE, "OPENAI_API_KEY": VALUE, "MY_FLAG": "1"},
                          "permissions": {"allow": ["Read"]}}, 0o640)
        solo = put("beta", {"env": {"GH_TOKEN": VALUE}})
        put("gamma", {"permissions": {"allow": []}})
        r = ls.prune(home)
        check("prune: each file's secret entries removed, the rest clean",
              r["status"] == "pruned" and [(x["working_copy"], x["status"], x.get("removed")) for x in r["files"]] ==
              [("alpha", "pruned", ["CLAUDE_BRIDGE_AUTH_TOKEN", "OPENAI_API_KEY"]), ("beta", "pruned", ["GH_TOKEN"]),
               ("gamma", "clean", [])], r)
        check("…the other entries and keys kept", json.load(open(f)) == {"env": {"MY_FLAG": "1"}, "permissions": {"allow": ["Read"]}},
              open(f).read())
        check("…the mode kept", os.stat(f).st_mode & 0o777 == 0o640, oct(os.stat(f).st_mode))
        check("…an env left empty goes", json.load(open(solo)) == {}, open(solo).read())
        check("…no temporary file left", os.listdir(os.path.dirname(f)) == ["settings.local.json"], os.listdir(os.path.dirname(f)))
        check("…no value in the reply", VALUE not in json.dumps(r))
        check("a second prune is clean", ls.prune(home)["status"] == "clean")

    with tempfile.TemporaryDirectory() as tmp:
        home, put = make_home(tmp)
        target = os.path.join(tmp, "elsewhere.json")
        with open(target, "w") as fh:
            json.dump({"env": {"GH_TOKEN": VALUE}}, fh)
        link = os.path.join(home, "projects", "linked", ".claude", "settings.local.json")
        os.makedirs(os.path.dirname(link))
        os.symlink(target, link)
        f = put("alpha", {"env": {"GH_TOKEN": VALUE}})

        def harness_writes() -> None:
            with open(f, "w") as fh:
                json.dump({"env": {"GH_TOKEN": VALUE}, "permissions": {"allow": ["Read"]}}, fh)
        r = ls.prune(home, before_rename=harness_writes)
        check("a concurrent write is never overwritten (busy), a symlink never followed (skipped); the run fails",
              r["status"] == "failed" and [(x["working_copy"], x["status"]) for x in r["files"]] == [("alpha", "busy"), ("linked", "skipped")], r)
        check("…the concurrent write stands", json.load(open(f)).get("permissions") == {"allow": ["Read"]})
        check("…the link's target is untouched", VALUE in open(target).read())
        check("…no temporary file left", sorted(os.listdir(os.path.dirname(f))) == ["settings.local.json"])

        p = subprocess.run([sys.executable, TOOL, "report", "--home", home], capture_output=True, text=True)
        check("the CLI: JSON on stdout, exit 0, no value", p.returncode == 0 and json.loads(p.stdout)["status"] == "ok"
              and VALUE not in p.stdout + p.stderr, p.stderr)
        p = subprocess.run([sys.executable, TOOL, "wipe"], capture_output=True, text=True)
        check("an unknown command is usage, exit 2", p.returncode == 2 and "usage" in p.stderr, p.stderr)

    print("all passed" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
