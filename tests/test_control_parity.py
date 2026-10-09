#!/usr/bin/env python3
"""The control plane's parity suite (ADR-040 Wave 8): every case of every
tests/parity_cases_*.py through Node and through Python (tests/control_parity.py),
the answers compared byte for byte. A side that cannot run fails the suite."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import control_parity  # noqa: E402


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    cases = control_parity.all_cases()
    check("every module of the wire and the security core has cases",
          {c["module"] for c in cases} >= {"sign", "protocol", "gzcoord", "jobs", "presence", "sessions", "pool", "queue"},
          sorted({c["module"] for c in cases}))
    answers = control_parity.run(cases)
    for (name, node, py), c in zip(answers, cases):
        if c.get("error"):
            import json
            check(name, json.loads(node).get("threw") is True and json.loads(py).get("threw") is True, (node, py))
        else:
            check(name, node == py, f"\n      node={node[:600]}\n      py  ={py[:600]}")
    # The harness can fail: a case whose sides differ is said, never passed.
    planted = {"name": "control: a case whose sides differ", "module": "sign", "input": None, "node": "return 1;", "py": "return 2"}
    check("a case whose sides differ is found (the harness's own control)", [d[0] for d in control_parity.compare([planted])] == [planted["name"]])
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
