#!/usr/bin/env python3
"""Tests for the `autoMode` and `skillOverrides` keys runtime/claude-code/
user-settings.py writes from policies/auto-mode.json (agent-fabric
ADR-008): the fleet's slots replace Claude Code's own by name and keep its
order, the other built-in entries are kept as worded, the lists add to the
built-in ones, and with no defaults to read an existing autoMode is kept."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(HERE, "runtime", "claude-code", "user-settings.py")
POLICY = json.load(open(os.path.join(HERE, "policies", "auto-mode.json"), encoding="utf-8"))
DEFAULTS = {
    "environment": ["**Organization**: None configured", "**Cloud provider(s)**: None configured",
                    "**Host containment**: None configured — assume an ordinary machine"],
    "allow": ["built-in allow"], "soft_deny": ["built-in soft"], "hard_deny": ["built-in hard"],
}


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    with tempfile.TemporaryDirectory(prefix="test_user_settings_auto_mode.") as tmp:
        fake = os.path.join(tmp, "claude")
        with open(fake, "w") as f:
            f.write("#!/bin/sh\n[ \"$1 $2\" = 'auto-mode defaults' ] || exit 3\ncat <<'EOF'\n"
                    + json.dumps(DEFAULTS) + "\nEOF\n")
        os.chmod(fake, 0o755)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("GITHUB_", "AGENT_FABRIC_"))}
        env.update(AGENT_FABRIC_CLAUDE=fake, AGENT_FABRIC_LOCAL_BIN=os.path.join(tmp, "bin"))
        settings = os.path.join(tmp, "settings.json")

        def run(**extra):
            return subprocess.run([sys.executable, SCRIPT, settings], capture_output=True, text=True,
                                  env={**env, **extra}, timeout=120)

        print("the fleet's slots in Claude Code's list")
        with open(settings, "w") as f:
            json.dump({"skillOverrides": {"some-skill": "off"}, "theme": "dark"}, f)
        r = run()
        doc = json.load(open(settings))
        a = doc.get("autoMode", {})
        envl = a.get("environment", [])
        check("written", r.returncode == 0 and r.stdout.startswith("  +  "), r.stdout + r.stderr)
        check("Organization replaced in place, first", envl[0] == f"**Organization**: {POLICY['environment']['Organization']}",
              envl[:1])
        check("a slot the policy does not name keeps Claude Code's wording", envl[1] == DEFAULTS["environment"][1], envl[1:2])
        check("Host containment replaced in its own place",
              envl[2] == f"**Host containment**: {POLICY['environment']['Host containment']}", envl[2:3])
        named = set(POLICY["environment"]) - {"Organization", "Host containment"}
        check("the policy's other slots added after, each once",
              sorted(e.split("**")[1] for e in envl[3:]) == sorted(named), envl[3:])
        check("no \"$defaults\" in the environment: it would bring back the replaced slots",
              "$defaults" not in envl)
        for key in ("soft_deny", "hard_deny"):
            check(f"{key}: the built-in list, then the policy's", a.get(key) == ["$defaults", *POLICY[key]], a.get(key))
        check("allow: absent while the policy adds none, so the built-in list stands",
              ("allow" not in a) == (not POLICY["allow"]), a.get("allow"))
        check("the setup wizard off, other overrides kept",
              doc["skillOverrides"] == {"some-skill": "off", "auto-mode-setup": "off"}, doc.get("skillOverrides"))
        check("every other key kept", doc.get("theme") == "dark")
        r = run()
        check("a second run changes nothing", r.stdout.startswith("  =  "), r.stdout + r.stderr)

        print("the policy changed: the next run writes it")
        doc["autoMode"]["environment"][0] = "**Organization**: edited by hand"
        json.dump(doc, open(settings, "w"))
        r = run()
        check("a hand edit is put back", r.stdout.startswith("  +  ")
              and json.load(open(settings))["autoMode"]["environment"][0].endswith(POLICY["environment"]["Organization"]))

        print("no defaults to read: autoMode kept as it is, and said")
        doc = json.load(open(settings))
        doc["autoMode"] = {"environment": ["**Organization**: an earlier write"]}
        doc["verbose"] = False
        json.dump(doc, open(settings, "w"))
        r = run(AGENT_FABRIC_CLAUDE=os.path.join(tmp, "absent"))
        after = json.load(open(settings))
        check("exit 0, the rest written", r.returncode == 0 and after["verbose"] is True, r.stdout + r.stderr)
        check("autoMode as it was", after["autoMode"] == {"environment": ["**Organization**: an earlier write"]},
              after.get("autoMode"))
        check("…and the line says why", "auto-mode defaults could not be read" in r.stderr, r.stderr)

        print("claude off PATH but in ~/.local/bin, as a control daemon runs bootstrap")
        os.makedirs(os.path.join(tmp, "bin"), exist_ok=True)
        os.symlink(fake, os.path.join(tmp, "bin", "claude"))
        doc = json.load(open(settings))
        doc["autoMode"] = {"environment": ["stale"]}
        json.dump(doc, open(settings, "w"))
        bare = {k: v for k, v in env.items() if k != "AGENT_FABRIC_CLAUDE"}
        r = subprocess.run([sys.executable, SCRIPT, settings], capture_output=True, text=True,
                           env={**bare, "PATH": "/usr/bin:/bin"}, timeout=120)
        check("found there, and autoMode written", r.returncode == 0
              and json.load(open(settings))["autoMode"]["environment"][0].startswith("**Organization**: gzapi-org"),
              r.stdout + r.stderr)

        print("the pinned claude in ~/.local/bin wins over another on PATH")
        other = os.path.join(tmp, "elsewhere")
        os.makedirs(other)
        with open(os.path.join(other, "claude"), "w") as f:
            f.write("#!/bin/sh\necho '{\"environment\": [\"**Organization**: from another claude\"]}'\n")
        os.chmod(os.path.join(other, "claude"), 0o755)
        r = subprocess.run([sys.executable, SCRIPT, settings], capture_output=True, text=True,
                           env={**bare, "PATH": other + ":/usr/bin:/bin"}, timeout=120)
        envl = json.load(open(settings))["autoMode"]["environment"]
        check("the defaults are the pinned harness's, not the other claude's",
              envl[1] == DEFAULTS["environment"][1] and "from another claude" not in json.dumps(envl), envl[:3])

        print("a file settled but for the wizard switch is written")
        doc = json.load(open(settings))
        doc["skillOverrides"].pop("auto-mode-setup")
        json.dump(doc, open(settings, "w"))
        r = run()
        check("written, and the switch is back", r.stdout.startswith("  +  ")
              and json.load(open(settings))["skillOverrides"].get("auto-mode-setup") == "off", r.stdout)

        print("a policy the writer cannot read is refused, never half-applied")
        # A scratch policy, named by the override: the checkout's own file is
        # never written, so a killed run cannot leave it broken.
        policy_path = os.path.join(tmp, "auto-mode.json")
        env["AGENT_FABRIC_AUTO_MODE_POLICY"] = policy_path
        try:
            for label, text in (("a misspelled key", json.dumps({**POLICY, "soft_denies": ["x"]})),
                                ("a string where a list belongs", json.dumps({**POLICY, "hard_deny": "one rule"})),
                                ("\"$defaults\" written by hand", json.dumps({**POLICY, "allow": ["$defaults"]})),
                                ("not JSON", "{")):
                open(policy_path, "w", encoding="utf-8").write(text)
                before = open(settings).read()
                r = run()
                check(f"{label}: exit 1, one '!' line, the file untouched",
                      r.returncode == 1 and r.stderr.startswith("  !  ") and "NOT written" in r.stderr
                      and open(settings).read() == before, r.stdout + r.stderr)
        finally:
            env.pop("AGENT_FABRIC_AUTO_MODE_POLICY")

        print("the policy itself")
        check("every slot has text", all(isinstance(v, str) and v.strip() for v in POLICY["environment"].values()))
        check("the public repositories are named as such",
              "PUBLIC: gzapi-org/agent-fabric and gzapi-org/InterWeave" in POLICY["environment"]["Repository visibility"])
        check("lists hold prose, never \"$defaults\" (the writer adds it)",
              all("$defaults" not in POLICY[k] for k in ("allow", "soft_deny", "hard_deny")))

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
