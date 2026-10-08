#!/usr/bin/env python3
"""runtime/claude-code/hooks/pr-counts.py: a reply that states a pull
request's status without "(N work, M fix)" is sent back once; a reply with
the counts, with no status, or with the PR only inside fenced code passes;
a reply the hook is already continuing passes whatever it says."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(HERE, "runtime", "claude-code", "hooks", "pr-counts.py")


def run(payload) -> tuple[int, dict | None]:
    r = subprocess.run([sys.executable, HOOK], input=json.dumps(payload) if not isinstance(payload, str) else payload,
                       capture_output=True, text=True, timeout=30)
    return r.returncode, (json.loads(r.stdout) if r.stdout.strip() else None)


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    def reply(text: str, active: bool = False):
        return run({"hook_event_name": "Stop", "last_assistant_message": text, "stop_hook_active": active})

    rc, out = reply("#115 is MERGEABLE and waits for your word to arm.")
    check("a status with no counts: blocked, naming the PR", rc == 0 and out and out.get("decision") == "block"
          and "#115" in out.get("reason", ""), out)
    rc, out = reply("#115 (10 work, 12 fix) is MERGEABLE and waits for your word to arm.")
    check("the same with its counts: passes", rc == 0 and out is None, out)
    rc, out = reply("gzapi-org/agent-fabric-gateway#8 is merged.")
    check("another repository's PR, merged, no counts: blocked",
          out and "gzapi-org/agent-fabric-gateway#8" in out.get("reason", ""), out)
    rc, out = reply("I read the description of #116 and the code it ports.")
    check("a PR named with no status word: passes", out is None, out)
    rc, out = reply("Run this:\n```\ngh pr merge 115 --auto\n# then check #115 is armed\n```\nDone.")
    check("a PR inside fenced code: passes", out is None, out)
    rc, out = reply("#115 is MERGEABLE.", active=True)
    check("already continuing because of a stop hook: passes, never a loop", out is None, out)
    rc, out = run("not json")
    check("an unreadable payload: passes, exit 0", rc == 0 and out is None, (rc, out))
    rc, out = reply("| #115 | merged | 10 work |\n#116 is open (7 work, 1 fix).")
    check("a table row with a status and no '(N work, M fix)': blocked; the counted line passes",
          out and "#115" in out["reason"] and "#116" not in out["reason"], out)
    big = ("word " * 50 + "#1 " * 20 + "\n") * 2000
    t0 = time.monotonic()
    rc, out = reply(big + "#9 is armed.")
    check("a long reply is read in well under the hook's 5 s", time.monotonic() - t0 < 3, time.monotonic() - t0)
    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
