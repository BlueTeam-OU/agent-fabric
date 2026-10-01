#!/usr/bin/env python3
"""tools/fabric/workspace_trust.py on scratch .claude.json files: the named
folders become trusted, every other key stays as read, the file keeps its
mode, and nothing is written when nothing changes."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(HERE, "tools", "fabric", "workspace_trust.py")


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        ws, wc = os.path.join(home, "projects"), os.path.join(home, "projects", "demo")
        os.makedirs(wc)
        cfg = os.path.join(home, ".claude.json")
        before = {"oauthAccount": {"x": 1}, "projects": {wc: {"allowedTools": ["a"], "hasTrustDialogAccepted": False}}}
        with open(cfg, "w") as f:
            json.dump(before, f)
        os.chmod(cfg, 0o600)
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CONFIG_DIR"}
        env["HOME"] = home

        def run(*a: str, e: dict | None = None) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, TOOL, *a], env=e or env, capture_output=True, text=True, timeout=60)

        r = run("--dry-run", ws, wc)
        check("--dry-run says what it would do and writes nothing", r.returncode == 0 and "(would write)" in r.stdout
              and json.load(open(cfg)) == before, r.stdout)
        r = run(ws, wc, os.path.join(home, "missing"))
        doc = json.load(open(cfg))
        check("the folders are trusted", doc["projects"][ws]["hasTrustDialogAccepted"] is True
              and doc["projects"][wc]["hasTrustDialogAccepted"] is True, doc)
        check("…every other key kept as read", doc["oauthAccount"] == {"x": 1} and doc["projects"][wc]["allowedTools"] == ["a"])
        check("…a folder that does not exist is skipped, never recorded",
              os.path.join(home, "missing") not in doc["projects"] and "not a directory" in r.stdout, r.stdout)
        check("…and the file keeps its mode", os.stat(cfg).st_mode & 0o777 == 0o600, oct(os.stat(cfg).st_mode))
        mtime = os.stat(cfg).st_mtime_ns
        r = run(ws, wc)
        check("a re-run changes nothing and writes nothing", r.returncode == 0 and "+" not in r.stdout
              and os.stat(cfg).st_mtime_ns == mtime, r.stdout)

        with open(cfg, "w") as f:
            f.write("[1, 2]")
        r = run(ws)
        check("a file that is not a JSON object: exit 1, nothing written", r.returncode == 1 and open(cfg).read() == "[1, 2]", r.stderr)

        other = os.path.join(tmp, "cfgdir")
        os.makedirs(other)
        r = run(ws, e={**env, "CLAUDE_CONFIG_DIR": other})
        check("CLAUDE_CONFIG_DIR is where the file lives when set, as Claude Code reads it",
              r.returncode == 0 and json.load(open(os.path.join(other, ".claude.json")))["projects"][ws]["hasTrustDialogAccepted"] is True)
        check("usage: exit 2", run().returncode == 2)
    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
