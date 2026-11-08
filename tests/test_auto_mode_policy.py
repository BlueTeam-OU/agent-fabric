#!/usr/bin/env python3
"""The operator's own policies/auto-mode.json, as it is: a fact about the
operator's data, not about the writer (tests/test_user_settings_auto_mode.py,
which runs on a fixture policy). Reads the checkout's live file on purpose,
so it is one of the cases a stripped run reports as the instance's own."""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POLICY = json.load(open(os.path.join(HERE, "policies", "auto-mode.json"), encoding="utf-8"))


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    print("the policy itself")
    check("every slot has text", all(isinstance(v, str) and v.strip() for v in POLICY["environment"].values()))
    check("the public repositories are named as such",
          "PUBLIC: BlueTeam-OU/agent-fabric and BlueTeam-OU/InterWeave" in POLICY["environment"]["Repository visibility"])
    check("lists hold prose, never \"$defaults\" (the writer adds it)",
          all("$defaults" not in POLICY[k] for k in ("allow", "soft_deny", "hard_deny")))
    # The apply writes GitHub's rulesets: the entry must keep it to the policy's keeper and to registered
    # projects, or the classifier reads it as a licence for any session and any repository.
    applies = [a for a in POLICY["allow"] if "fabric-repo-policy apply" in a]
    check("one entry allows fabric-repo-policy apply", len(applies) == 1, applies)
    check("the apply entry is bound to fabric-coordinator, registered projects, never --fleet-default",
          all("bound to fabric-coordinator" in a and "projects/registry.json" in a and "never with --fleet-default" in a
              for a in applies), applies)
    # An uninstall or a pm clear deletes; the entry must keep it to InterWeave's packages, inside the wrapper
    # that holds a phone's lease, aimed at that phone, for one job. A lease is held only while the command it
    # wraps runs, so the classifier can check the wrapper, never "a session holding a lease". Any entry that
    # names adb is selected, so a second, unbounded one cannot sit beside it unchecked.
    adb_entries = [a for a in POLICY["allow"] if "adb " in a]
    check("one entry allows adb uninstall or pm clear", len(adb_entries) == 1, adb_entries)
    bounds = ("`org.interweave.`", "`.agent-fabric/bin/phone-run`", "`pixel-9a`", "`fabric-lease samsung-a40 -- ...`",
              "192.168.100.6", "j648", "removes this entry when j648 is delivered",
              "An adb command outside that wrapper, a wrapper aimed at the other phone, or any other package, device or host path is not covered")
    for bound in bounds:
        check(f"the adb entry keeps its bound: {bound}", all(bound in a for a in adb_entries), adb_entries)

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
