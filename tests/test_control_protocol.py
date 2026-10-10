#!/usr/bin/env python3
"""Tests for tools/fabric/control/protocol.py, the port of runtime/control/protocol.mjs.

ENVELOPE_KEYS is held to Node's, and each typed dict to ENVELOPE_KEYS.
protocol.test.mjs holds the envelopes the code builds to the keys: of
its cases, the one whose builder is ported (a signed request,
control/sign.py) runs here; the others move with agentd, presence,
queue, sessions and ctl, each in its own port.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import protocol, sign  # noqa: E402



def holds(value: dict, kind: str) -> list[str]:
    """protocol.test.mjs holds(): what is missing or undeclared, and a
    wrong kind or v; empty when the value is a <kind>."""
    keys = protocol.ENVELOPE_KEYS[kind]
    problems = [f"missing {k}" for k in keys["required"] if k not in value]
    problems += [f"undeclared {k}" for k in value if k not in keys["required"] and k not in keys["optional"]]
    if value.get("kind") != kind:
        problems.append(f"kind {value.get('kind')!r}")
    if value.get("v") != 1:
        problems.append(f"v {value.get('v')!r}")
    return problems


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    with open(os.path.join(HERE, "tests", "fixtures", "node-oracle-protocol.json"), encoding="utf-8") as fh:
        node = json.load(fh)["envelope_keys"]
    mine = {k: {"required": list(v["required"]), "optional": list(v["optional"])} for k, v in protocol.ENVELOPE_KEYS.items()}
    check("ENVELOPE_KEYS is the Node's (frozen), kind for kind, key for key, in order", mine == node, (mine, node))
    for kind, typed in protocol.TYPES.items():
        want = protocol.ENVELOPE_KEYS[kind]
        got_required, got_optional = set(typed.__required_keys__), set(typed.__optional_keys__)
        check(f"the {kind} typed dict declares its keys, required and optional apart",
              got_required == set(want["required"]) and got_optional == set(want["optional"]),
              (sorted(got_required), sorted(got_optional)))
    check("ENVELOPE_KEYS cannot be changed by a caller",
          all(isinstance(v["required"], tuple) and isinstance(v["optional"], tuple) for v in protocol.ENVELOPE_KEYS.values()))
    try:
        protocol.ENVELOPE_KEYS["request"] = {}
        check("...nor a kind added", False)
    except TypeError:
        check("...nor a kind added", True)

    print("protocol.test.mjs: the envelopes the ported code builds")
    request = {"v": 1, "kind": "request", "id": "q1", "from": "h/user", "to": ["h/a"], "op": "ping", "ts": "2026-10-09T02:00:00.000Z",
               "ttl_s": 30}
    check("a request is a Request", holds(request, "request") == [], holds(request, "request"))
    signed = sign.sign_request(request, sign.generate_operator_key()["privateKeySpec"])
    check("a signed one too", holds(signed, "request") == [], holds(signed, "request"))
    check("holds() sees a missing key, an undeclared one and a wrong kind",
          holds({k: v for k, v in request.items() if k != "op"}, "request") == ["missing op"]
          and holds({**request, "extra": 1}, "request") == ["undeclared extra"]
          and holds({**request, "kind": "reply"}, "request") == ["kind 'reply'"])

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
