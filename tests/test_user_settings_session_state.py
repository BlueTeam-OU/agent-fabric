#!/usr/bin/env python3
"""Tests for the session-state hook's registration in a login's user
settings (runtime/claude-code/user-settings.py, agent-fabric ADR-029 §5
rule 16): one entry on each of its seven events at this checkout's path,
an old path replaced, the account's own hooks kept, a second run settled,
and an event that is not a list refused and left as it is."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

from instance_fixtures import write_operator_policy

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(HERE, "runtime", "claude-code", "user-settings.py")
HOOK = f'python3 "{HERE}/runtime/claude-code/hooks/session-state.py"'
EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PermissionRequest", "Notification", "Stop", "SessionEnd")


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    with tempfile.TemporaryDirectory(prefix="test_user_settings_session_state.") as tmp:
        fake = os.path.join(tmp, "claude")
        with open(fake, "w") as f:
            f.write('#!/bin/sh\necho \'{"environment": [], "allow": [], "soft_deny": [], "hard_deny": []}\'\n')
        os.chmod(fake, 0o755)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("GITHUB_", "AGENT_FABRIC_"))}
        env.update(AGENT_FABRIC_CLAUDE=fake, AGENT_FABRIC_LOCAL_BIN=os.path.join(tmp, "bin"),
                   AGENT_FABRIC_OPERATOR=write_operator_policy(tmp))
        settings = os.path.join(tmp, "settings.json")

        def run():
            return subprocess.run([sys.executable, SCRIPT, settings], capture_output=True, text=True, env=env, timeout=120)

        def write(doc):
            with open(settings, "w") as f:
                json.dump(doc, f)

        write({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "stop.sh"}]},
                                  {"hooks": [{"type": "command", "command": 'python3 "/old/runtime/claude-code/hooks/session-state.py"'}]}]}})
        r = run()
        hooks = json.load(open(settings))["hooks"]
        cmds = {ev: [h["command"] for e in hooks.get(ev, []) for h in e["hooks"]] for ev in EVENTS}
        check("written", r.returncode == 0 and r.stdout.startswith("  +  "), r.stdout + r.stderr)
        # The fixture's Organization text is in no live policy: a reader of
        # this checkout's policies/auto-mode.json would write another.
        check("the operator tree's policy is the one written",
              (json.load(open(settings)).get("autoMode") or {}).get("environment", [""])[0]
              == "**Organization**: the fixture operator", r.stderr)
        check("one entry on each of the seven events, at this checkout's path",
              all([c for c in cmds[ev] if "session-state.py" in c] == [HOOK] for ev in EVENTS), cmds)
        check("the account's own Stop hook kept", "stop.sh" in cmds["Stop"], cmds["Stop"])
        r = run()
        check("a second run changes nothing", r.stdout.startswith("  =  "), r.stdout + r.stderr)

        # The freshness hook (hooks/freshness.py) rides UserPromptSubmit: one
        # entry, at this checkout's path, beside the account's own; an old
        # checkout's entry replaced (review of the carried-109 branch, 5).
        fresh = f'python3 "{HERE}/runtime/claude-code/hooks/freshness.py"'
        doc = json.load(open(settings))
        doc["hooks"]["UserPromptSubmit"] = doc["hooks"].get("UserPromptSubmit", []) + [
            {"hooks": [{"type": "command", "command": "mine.sh"}]},
            {"hooks": [{"type": "command", "command": 'python3 "/old/runtime/claude-code/hooks/freshness.py"'}]}]
        write(doc)
        r = run()
        ups = [h["command"] for e in json.load(open(settings))["hooks"]["UserPromptSubmit"] for h in e["hooks"]]
        check("freshness: one entry on UserPromptSubmit, this checkout's, the old one gone",
              [c for c in ups if "freshness.py" in c] == [fresh], ups)
        check("freshness: the account's own UserPromptSubmit hook kept", "mine.sh" in ups, ups)
        r = run()
        check("freshness: a second run changes nothing", r.stdout.startswith("  =  "), r.stdout + r.stderr)

        # The PR-counts guard (hooks/pr-counts.py) rides Stop: one entry, at
        # this checkout's path, beside the account's own Stop hook and the
        # session-state one; an old checkout's entry replaced.
        counts = f'python3 "{HERE}/runtime/claude-code/hooks/pr-counts.py"'
        doc = json.load(open(settings))
        doc["hooks"]["Stop"] = doc["hooks"]["Stop"] + [
            {"hooks": [{"type": "command", "command": 'python3 "/old/runtime/claude-code/hooks/pr-counts.py"'}]}]
        write(doc)
        r = run()
        stops = [h["command"] for e in json.load(open(settings))["hooks"]["Stop"] for h in e["hooks"]]
        check("pr-counts: one entry on Stop, this checkout's, the old one gone",
              [c for c in stops if "pr-counts.py" in c] == [counts], stops)
        check("pr-counts: the account's own Stop hook and session-state kept",
              "stop.sh" in stops and HOOK in stops, stops)
        r = run()
        check("pr-counts: a second run changes nothing", r.stdout.startswith("  =  "), r.stdout + r.stderr)

        raw = '{"hooks": {"Notification": {"hooks": []}}}'
        with open(settings, "w") as f:
            f.write(raw)
        r = run()
        out = r.stdout + r.stderr
        check("a Notification that is not a list is refused in one line, untouched",
              r.returncode == 1 and "Notification is not a list" in out and "NOT written" in out
              and out.count("\n") == 1 and open(settings).read() == raw, (r.returncode, out))

    print("all passed" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
