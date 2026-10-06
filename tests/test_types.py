#!/usr/bin/env python3
"""The fabric's typed records are held to the values the code builds.

No type checker runs here (agent-fabric's typing is option (B): types only
where they carry behaviour, j28). An annotation nothing checks can drift
from the code and go on claiming a shape that is no longer there, so each
TypedDict is checked against real values: every required key present,
nothing undeclared. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import traceback
from typing import Any, Callable

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from gzcoord import gzmsg  # noqa: E402

CASES: list[tuple[str, Callable[[], None]]] = []
SCRATCH: list[str] = []


class Failed(AssertionError):
    pass


def case(name: str) -> Callable:
    def add(fn: Callable[[], None]) -> Callable[[], None]:
        CASES.append((name, fn))
        return fn
    return add


def scratch() -> str:
    d = tempfile.mkdtemp(prefix="types-")
    SCRATCH.append(d)
    return d


def holds(value: Any, td: type, what: str) -> None:
    """`value` is a `td`: a dict, every required key, no key undeclared."""
    if not isinstance(value, dict):
        raise Failed(f"{what}: not a dict: {value!r}")
    keys = set(value)
    missing = set(td.__required_keys__) - keys
    extra = keys - set(td.__required_keys__) - set(td.__optional_keys__)
    if missing or extra:
        raise Failed(f"{what} is no {td.__name__}: missing {sorted(missing)}, undeclared {sorted(extra)}")


MESSAGE = ("[GZCOORD/1] INFO\nFROM: h/someone\nROLE: python-dev\nPROJECT: fixture\nBROADCAST: true\n"
           "MESSAGE-ID: 01a09fc1-0000-7000-8000-000000000001\nSUBJECT: s\n\nNOTES:\nn\n")


@case("gzmsg.parse and validate return a ParsedMessage and a Validation, either way validate goes")
def _():
    holds(gzmsg.parse(MESSAGE), gzmsg.ParsedMessage, "parse")
    good = gzmsg.validate(MESSAGE)
    holds(good, gzmsg.Validation, "validate (valid)")
    holds(good["message"], gzmsg.ParsedMessage, "validate's message")
    bad = gzmsg.validate("not a message\n")
    holds(bad, gzmsg.Validation, "validate (bad first line)")
    if bad["message"] is not None:
        raise Failed(f"a bad first line still carries a message: {bad}")


@case("gzmsg.whoami returns a Whoami, from identity and from the fallback")
def _():
    holds(gzmsg.whoami(), gzmsg.Whoami, "whoami")
    real = gzmsg._identity_module
    gzmsg._identity_module = lambda _root: (_ for _ in ()).throw(RuntimeError("identity cannot answer"))
    try:
        fallback = gzmsg.whoami()
    finally:
        gzmsg._identity_module = real
    holds(fallback, gzmsg.Whoami, "whoami (fallback)")
    if fallback.get("fallback") is not True:
        raise Failed(f"the fallback was not taken: {fallback}")


@case("gzmsg.recorded_role returns a RoleRecord in each of its four outcomes")
def _():
    d = scratch()
    tax = gzmsg.Taxonomy(os.path.join(d, "catalog.json"), {"python-dev": "Python developer"})
    binding = os.path.join(d, "binding.json")
    me = {"agent": "someone", "host": "h", "role": None, "project": None, "working_copy": None, "binding": binding}
    outcomes = {"no taxonomy": gzmsg.recorded_role(None, me), "no record": gzmsg.recorded_role(tax, me)}
    with open(binding, "w", encoding="utf-8") as fh:
        fh.write("{not json")
    outcomes["unreadable"] = gzmsg.recorded_role(tax, me)
    outcomes["not in the catalogue"] = gzmsg.recorded_role(tax, dict(me, role="no-such-role"))
    outcomes["a catalogue role"] = gzmsg.recorded_role(tax, dict(me, role="python-dev"))
    for what, value in outcomes.items():
        holds(value, gzmsg.RoleRecord, f"recorded_role ({what})")
    keys = {what: sorted(set(v) - {"role"}) for what, v in outcomes.items()}
    if keys != {"no taxonomy": [], "no record": [], "unreadable": ["warning"],
                "not in the catalogue": ["error"], "a catalogue role": ["file"]}:
        raise Failed(f"the four outcomes are not told apart by their keys: {keys}")


def main() -> int:
    fails = 0
    for name, fn in CASES:
        try:
            fn()
            print(f"  ok   {name}")
        except Exception as e:  # noqa: BLE001 — a case that raises is a failure, reported
            fails += 1
            print(f"  FAIL {name}: {e}")
            if not isinstance(e, Failed):
                traceback.print_exc()
    for d in SCRATCH:
        shutil.rmtree(d, ignore_errors=True)
    print(f"test_types: {'OK' if not fails else f'FAILED — {fails}'} ({len(CASES)} cases)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
