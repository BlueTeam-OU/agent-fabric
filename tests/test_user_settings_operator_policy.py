#!/usr/bin/env python3
"""runtime/claude-code/user-settings.py reads policies/auto-mode.json as
instance data (ADR-045 §5 rule 2): from the operator's tree when
AGENT_FABRIC_OPERATOR names one, never this checkout's copy then. A
fixture operator tree, a fake `claude`, a scratch settings file; nothing
of the live tree is read or written."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(HERE, "runtime", "claude-code", "user-settings.py")
DEFAULTS = {"environment": ["**Organization**: None configured"], "allow": [], "soft_deny": [], "hard_deny": []}


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    with tempfile.TemporaryDirectory(prefix="test_user_settings_operator_policy.") as tmp:
        fake = os.path.join(tmp, "claude")
        with open(fake, "w") as f:
            f.write("#!/bin/sh\n[ \"$1 $2\" = 'auto-mode defaults' ] || exit 3\ncat <<'EOF'\n" + json.dumps(DEFAULTS) + "\nEOF\n")
        os.chmod(fake, 0o755)
        operator = os.path.join(tmp, "operator")
        os.makedirs(os.path.join(operator, "policies"))
        policy = os.path.join(operator, "policies", "auto-mode.json")
        with open(policy, "w", encoding="utf-8") as f:
            json.dump({"environment": {"Organization": "the fixture operator"}, "allow": [], "soft_deny": [], "hard_deny": []}, f)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("GITHUB_", "AGENT_FABRIC_"))}
        env.update(AGENT_FABRIC_CLAUDE=fake, AGENT_FABRIC_LOCAL_BIN=os.path.join(tmp, "bin"), AGENT_FABRIC_OPERATOR=operator)
        settings = os.path.join(tmp, "settings.json")
        with open(settings, "w") as f:
            json.dump({}, f)

        r = subprocess.run([sys.executable, SCRIPT, settings], capture_output=True, text=True, env=env, timeout=120)
        org = (json.load(open(settings)).get("autoMode") or {}).get("environment", [""])[0]
        check("the operator's policy is the one written", r.returncode == 0 and org == "**Organization**: the fixture operator",
              (org, r.stderr[-300:]))

        with open(policy, "w", encoding="utf-8") as f:
            f.write("{broken")
        r = subprocess.run([sys.executable, SCRIPT, settings], capture_output=True, text=True, env=env, timeout=120)
        check("a broken operator policy is named by its own path, never replaced by the checkout's",
              r.returncode != 0 and policy in r.stderr, (r.returncode, r.stderr[-300:]))
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
