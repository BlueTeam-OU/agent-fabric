#!/usr/bin/env python3
"""The fabric's status line at user scope (runtime/claude-code/user-settings.py):
a session started inside a working copy reads that project's settings, not
the workspace's, so the status line goes where every session of the account
reads it. Written to this checkout's statusline.sh, a foreign one replaced,
a second run settled."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(HERE, "runtime", "claude-code", "user-settings.py")
WANT = {"type": "command", "command": f'bash "{HERE}/runtime/claude-code/hooks/statusline.sh"'}


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    with tempfile.TemporaryDirectory(prefix="test_user_settings_status_line.") as tmp:
        fake = os.path.join(tmp, "claude")
        with open(fake, "w") as f:
            f.write('#!/bin/sh\necho \'{"environment": [], "allow": [], "soft_deny": [], "hard_deny": []}\'\n')
        os.chmod(fake, 0o755)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("GITHUB_", "AGENT_FABRIC_"))}
        env.update(AGENT_FABRIC_CLAUDE=fake, AGENT_FABRIC_LOCAL_BIN=os.path.join(tmp, "bin"))
        settings = os.path.join(tmp, "settings.json")

        def run():
            return subprocess.run([sys.executable, SCRIPT, settings], capture_output=True, text=True, env=env, timeout=120)

        def doc():
            with open(settings) as f:
                return json.load(f)

        with open(settings, "w") as f:
            json.dump({}, f)
        r = run()
        check("an account with none gets the fabric's", r.returncode == 0 and doc().get("statusLine") == WANT,
              r.stdout + r.stderr)
        r = run()
        check("a second run is settled", r.returncode == 0 and r.stdout.startswith("  =  "), r.stdout)
        d = doc()
        d["statusLine"] = {"type": "command", "command": "echo mine"}
        with open(settings, "w") as f:
            json.dump(d, f)
        r = run()
        check("another command's status line is replaced by the fabric's", doc().get("statusLine") == WANT, doc())
    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
