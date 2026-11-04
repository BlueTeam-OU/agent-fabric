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

SEAL = os.path.join(HERE, "runtime", "claude-code", "hooks", "session-seal.py")
seal_spec = importlib.util.spec_from_file_location("session_seal", SEAL)
seal = importlib.util.module_from_spec(seal_spec)
seal_spec.loader.exec_module(seal)

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

        # A value that is not UTF-8 must cost neither its own name nor any other; the positive control is the
        # same file read as text, which raises.
        with open(os.path.join(home, ".config", "agent-fabric", "secrets.env"), "ab") as fh:
            fh.write(b"export LATIN_KEY='caf\xe9'\nexport AFTER_KEY=1\n")
        try:
            open(os.path.join(home, ".config", "agent-fabric", "secrets.env"), encoding="utf-8").read()
            check("control: the planted byte is not UTF-8", False)
        except UnicodeDecodeError:
            check("control: the planted byte is not UTF-8", True)
        s = ls.secret_names(home)
        check("a non-UTF-8 byte in secrets.env: report's names keep the line's own and the later ones",
              {"LATIN_KEY", "AFTER_KEY", "OPENAI_API_KEY"} <= s, sorted(s))

        # The seal cannot import this module, so its copies are held equal here, on the same non-UTF-8 file and on a
        # lone CR inside a value (which the old text-mode read split into a made-up name).
        check("the seal's credential tuple is this module's", seal.HARNESS_CREDENTIALS == ls.HARNESS_CREDENTIALS,
              (seal.HARNESS_CREDENTIALS, ls.HARNESS_CREDENTIALS))
        secrets_env = os.path.join(home, ".config", "agent-fabric", "secrets.env")
        check("the seal reads the same names from the non-UTF-8 file",
              seal.synced_names(secrets_env) == ls.exported_names(secrets_env), seal.synced_names(secrets_env))
        cr = os.path.join(tmp, "cr.env")
        with open(cr, "wb") as fh:
            fh.write(b"export A='x\rexport B=1'\nexport C=2\r\n")
        check("…and from a lone CR in a value: A and C, no name made up from the value",
              seal.synced_names(cr) == ls.exported_names(cr) == ["A", "C"], (seal.synced_names(cr), ls.exported_names(cr)))

        put("latin", {"env": {"LATIN_KEY": VALUE, "AFTER_KEY": VALUE, "MY_FLAG": "1"}})
        rl = ls.report(home)["files"][0]
        check("…report names the secrets on both sides of the bad line", rl["secrets"] == ["AFTER_KEY", "LATIN_KEY"], rl)
        pl = ls.prune(home)["files"][0]
        check("…prune removes them and keeps the rest", pl["status"] == "pruned" and pl["removed"] == ["AFTER_KEY", "LATIN_KEY"], pl)
        os.unlink(os.path.join(home, "projects", "latin", ".claude", "settings.local.json"))
        os.rmdir(os.path.join(home, "projects", "latin", ".claude"))
        os.rmdir(os.path.join(home, "projects", "latin"))

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
        elsewhere = os.path.join(tmp, "elsewhere-dir")
        os.makedirs(elsewhere)
        with open(os.path.join(elsewhere, "settings.local.json"), "w") as fh:
            json.dump({"env": {"GH_TOKEN": VALUE}}, fh)
        os.makedirs(os.path.join(home, "projects", "dirlinked"))
        os.symlink(elsewhere, os.path.join(home, "projects", "dirlinked", ".claude"))
        f = put("alpha", {"env": {"GH_TOKEN": VALUE}})

        def harness_writes() -> None:
            with open(f, "w") as fh:
                json.dump({"env": {"GH_TOKEN": VALUE}, "permissions": {"allow": ["Read"]}}, fh)
        r = ls.prune(home, before_rename=harness_writes)
        check("a concurrent write is never overwritten (busy), a symlink never followed (skipped); the run fails",
              r["status"] == "failed" and [(x["working_copy"], x["status"]) for x in r["files"]] ==
              [("alpha", "busy"), ("dirlinked", "skipped"), ("linked", "skipped")], r)
        check("…a symlinked .claude directory is never followed either (review of #101)",
              VALUE in open(os.path.join(elsewhere, "settings.local.json")).read())
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
