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
    for (name, node, py), c in zip(control_parity.run(cases), cases, strict=True):
        why = control_parity.verdict(c, node, py)
        check(name, why is None, f"{why}\n      node={node[:600]}\n      py  ={py[:600]}")

    print("the harness's own controls: each must fail")
    planted = [
        {"name": "sides differ", "module": "sign", "input": None, "node": "return 1;", "py": "return 2"},
        {"name": "both throw, unexpected", "module": "sign", "input": None, "node": "return m.signRequesst({}, 'k');", "py": "return m.sign_requesst({}, 'k')"},
        {"name": "a module neither side has", "module": "nosuch", "input": None, "node": "return 1;", "py": "return 1"},
        {"name": "one side throws where both should", "module": "sign", "input": None, "node": "throw new Error('x');", "py": "return 1", "error": True},
        {"name": "newlines differ in a state file", "module": "sign", "input": None, "files": ["f"],
         "node": "(await import('node:fs')).writeFileSync(home.root + '/f', 'a\\nb\\n'); return 0;",
         "py": "open(home['root'] + '/f', 'w', newline='').write('a\\r\\nb\\r')\nreturn 0"},
        {"name": "an invalid byte against its replacement", "module": "sign", "input": None, "files": ["f"],
         "node": "(await import('node:fs')).writeFileSync(home.root + '/f', Buffer.from([0xff])); return 0;",
         "py": "open(home['root'] + '/f', 'wb').write(b'\\xef\\xbf\\xbd')\nreturn 0"},
    ]
    failed = {d[0]: d[3] for d in control_parity.compare(planted)}
    for c in planted:
        check(f"control found: {c['name']}", c["name"] in failed, failed)
    positive = [{"name": "both throw, expected", "module": "sign", "input": None, "node": "throw new Error('x');", "py": "raise ValueError('x')", "error": True},
                {"name": "same bytes", "module": "sign", "input": None, "files": ["f", "absent"],
                 "node": "(await import('node:fs')).writeFileSync(home.root + '/f', 'a\\r\\n\\u00e9'); return 0;",
                 "py": "open(home['root'] + '/f', 'wb').write('a\\r\\n\\u00e9'.encode())\nreturn 0"}]
    check("and their positive controls hold", control_parity.compare(positive) == [], control_parity.compare(positive))
    check("an unexpected throw says why", "sign_requesst" in failed.get("both throw, unexpected", ""), failed)
    import tempfile
    with tempfile.TemporaryDirectory() as cwd:
        def side(code: str) -> str:
            try:
                control_parity._side([sys.executable, "-c", code], {"cases": [{}, {}]}, {"PATH": os.environ.get("PATH", "")}, cwd)
            except Exception as e:  # noqa: BLE001 — any other exception is a guard that did not hold, said by the check
                return str(e) if isinstance(e, RuntimeError) else f"{type(e).__name__}: {e}"
            return "no error"
        check("a side that exits non-zero is an error", "exit 3" in side("import sys; sys.exit(3)"))
        check("a side that answers fewer cases is an error", "answered 1 of 2" in side("print('[\"{}\"]')"))
        # Two characters: a string as long as the cases, which only the list check refuses.
        check("a side that answers no list is an error, said as such", "str, not a list" in side("print('\"ab\"')"))
        check("...a number too, never a TypeError", "int, not a list" in side("print('5')"))
        check("a side that answers no JSON is an error, said as such", "answered no JSON" in side("print('nope')"))
        check("...nothing at all too", "answered no JSON" in side("pass"))
        for bad in ("[5, 6]", "[null, null]", '["{}", "{}"]', '["5", "5"]', '["{\\"threw\\": false}", "{}"]'):
            check(f"a side whose answers are not answer objects is an error: {bad}", "case 0 with" in side(f"print({bad!r})"), side(f"print({bad!r})"))
        ok = '["{\\"value\\": 1, \\"files\\": {}}", "{\\"threw\\": true, \\"why\\": \\"x\\"}"]'
        check("a side that answers every case is read", side(f"print({ok!r})") == "no error", side(f"print({ok!r})"))
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
