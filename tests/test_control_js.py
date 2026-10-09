#!/usr/bin/env python3
"""Tests for tools/fabric/control/js.py: each helper held to what Node itself
answers on the same inputs, batteries random and named. Node is the
oracle: without it these fail, they are never skipped."""
from __future__ import annotations

import json
import math
import os
import random
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import js  # noqa: E402


def node(body: str, data):
    r = subprocess.run(["node", "-e", "const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));\n"
                        f"process.stdout.write(JSON.stringify((() => {{ {body} }})()));"],
                       input=json.dumps(data), capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-400:])
    return json.loads(r.stdout)


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    rnd = random.Random(20261009)

    def diff(label, cases, mine, theirs):
        bad = [(c, t, m) for c, t, m in zip(cases, theirs, mine) if t != m]
        check(f"{label} on {len(cases)} inputs", not bad, bad[:4])

    def norm(x):
        return "NaN" if math.isnan(x) else ("Inf" if x == math.inf else ("-Inf" if x == -math.inf else x))
    nums = ["0x10", "0b11", "1_0", " 5 ", "\ufeff5", "\u0661\u0660", "\x1c5", "", "Infinity", "-Infinity", "inf", ".5", "5.", "0x0x10",
            "0o8", "0x" + "f" * 300, "1e400", "-0", "+5", "0X1f", "0B1", "1e", "--5"]
    nums += ["".join(rnd.choice("0123456789xXoObB.eE+- _\t\ufeffaInfity") for _ in range(rnd.randint(0, 6))) for _ in range(3000)]
    diff("number is Number()", nums, [norm(js.number(n)) for n in nums],
         node("return input.map(s => { const n = Number(s); return Number.isNaN(n) ? 'NaN' : n === Infinity ? 'Inf' : n === -Infinity ? '-Inf' : n; });", nums))

    texts = ["", "  a ", "\ufeffa\ufeff", "\u180ea", "\x1ca\x1f", "\u3000a\u2028", "\u00a0\u1680x\u205f", "\t\n\v\f\r x"]
    texts += ["".join(rnd.choice(" \t\n\u00a0\u2000\u2028\ufeff\u180e\x1cab\u3000") for _ in range(rnd.randint(0, 6))) for _ in range(1000)]
    diff("trim is String.prototype.trim()", texts, [js.trim(t) for t in texts], node("return input.map(s => s.trim());", texts))
    wide = ["", "a", "\U0001F600", "a\U0001F600b", "\ud800", "x" * 5, "\u00e9\U0001F600" * 3]
    diff("length is .length, in UTF-16 units", wide, [js.length(w) for w in wide], node("return input.map(s => s.length);", wide))
    diff("slice(s, 3) is .slice(0, 3)", wide, [js.slice(w, 3) for w in wide], node("return input.map(s => s.slice(0, 3));", wide))
    diff("well_formed is what toWellFormed() makes (a lone half as U+FFFD)", wide + ["a\udc00b", "\ud83d"],
         [js.well_formed(w) for w in wide + ["a\udc00b", "\ud83d"]],
         node("return input.map(s => s.toWellFormed());", wide + ["a\udc00b", "\ud83d"]))

    values = [None, True, False, 0, -0.0, 5, 5.5, 1e21, 1e-7, "x", [], [1, None, [2, 3]], {}, {"a": 1}, [None], ["a", ["b", None]], float("inf"), -float("inf")]
    sent = [v if not (isinstance(v, float) and math.isinf(v)) else ("Inf" if v > 0 else "-Inf") for v in values]
    diff("string is String()", values, [js.string(v) for v in values],
         node("return input.map(v => String(v === 'Inf' ? Infinity : v === '-Inf' ? -Infinity : v));", sent))
    check("string(UNDEFINED) is 'undefined', truthy(UNDEFINED) False", js.string(js.UNDEFINED) == "undefined" and not js.truthy(js.UNDEFINED))
    tv = [None, False, True, 0, 1, -1, 0.0, "", "0", " ", "false", [], {}, [0]]
    diff("truthy is !!v", tv, [js.truthy(v) for v in tv], node("return input.map(v => !!v);", tv))

    objs = [{"b": 1, "a": 2, "2": 3, "1": 4}, {"01": 1, "10": 2, "4294967295": 3, "4294967294": 4, "-1": 5, "x": 6}, {"z": 1}, {}]
    diff("keys is Object.keys()", objs, [js.keys(o) for o in objs], node("return input.map(o => Object.keys(o));", objs))

    doc_texts = ['{"b":1,"a":[1,2,{"2":0,"1":1}],"s":"\\ud800 \\u2028 \\u00e9"}', '[1e21,0.1,-0,5.0,1e-7]', '"x"', 'null',
                 '{"n":12345678901234567890}', '[[[[{}]]]]']
    diff("stringify(json_parse(t)) is JSON.stringify(JSON.parse(t))", doc_texts,
         [js.stringify(js.json_parse(t)) for t in doc_texts], node("return input.map(t => JSON.stringify(JSON.parse(t)));", doc_texts))
    pretty = ['{}', '[]', '{"a":{},"b":[],"c":[[],{}]}', '{"2":1,"1":[1,2.5,-0,1e21,1e-7]}', '"\\ud800"', '{"__proto__":1,"4294967295":2,"4294967294":3}',
              '[1e400]', '{"x":{"y":{"z":[null,true,false,"\\u00e9"]}}}']
    diff("stringify(v, 2) is JSON.stringify(v, null, 2)", pretty, [js.stringify(js.json_parse(t), indent=2) for t in pretty],
         node("return input.map(t => JSON.stringify(JSON.parse(t), null, 2));", pretty))
    check("stringify writes NaN and the infinities as null, drops UNDEFINED from an object, writes it null in a list",
          js.stringify([math.nan, math.inf, {"a": js.UNDEFINED, "b": 1}, js.UNDEFINED]) == '[null,null,{"b":1},null]')
    check("stringify writes a lone surrogate escaped, so the text encodes", js.stringify("a\ud800").encode("utf-8") == b'"a\\ud800"')
    bad = ["NaN", "Infinity", "-Infinity", '{"a": NaN}', "[1,]", "", "{'a':1}", "[" * 100000]
    refused = node("return input.map(t => { try { JSON.parse(t); return false; } catch { return true; } });", bad)
    mine = []
    for t in bad:
        try:
            js.json_parse(t)
            mine.append(False)
        except ValueError:
            mine.append(True)
    diff("json_parse refuses what JSON.parse refuses, as a ValueError", bad, mine, refused)
    big = ["9007199254740992", "9007199254740993", "-9007199254740993", "12345678901234567890", "1" + "0" * 400, "-" + "9" * 5000, "0", "-0", "5"]
    diff("json_parse reads an integer as JavaScript's double", big,
         [js.stringify(js.json_parse(b)) for b in big], node("return input.map(t => JSON.stringify(JSON.parse(t)));", big))
    check("...as the value itself, not only as text: 2**53 + 1 is 2**53, 1e400 is Infinity, 2**53 stays an exact int",
          js.json_parse("9007199254740993") == 9007199254740992.0 and isinstance(js.json_parse("9007199254740993"), float)
          and js.json_parse("1" + "0" * 400) == math.inf and js.json_parse("9007199254740992") == 2**53
          and isinstance(js.json_parse("9007199254740992"), int))
    deep = "[" * 300000 + "]" * 300000
    read_by_node = node("try { JSON.parse(input); return true; } catch { return false; }", deep)
    # 3.12 and 3.13 stop near 10,000 levels on any stack; 3.14 stops where
    # its stack ends, which a runner sets (an unlimited one reads it all).
    # So: 8 MiB, the default, in a child whose limit is set before it
    # starts, and a depth far past 3.14's ~52,000 there, whatever a build's
    # frame size.
    import resource
    soft, hard = resource.getrlimit(resource.RLIMIT_STACK)
    eight = 8 << 20 if hard == resource.RLIM_INFINITY else min(8 << 20, hard)
    r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); from control import js\n"
                        "try:\n    js.json_parse(sys.stdin.read()); print('read')\nexcept ValueError:\n    print('ValueError')",
                        os.path.join(HERE, "tools", "fabric")], input=deep, capture_output=True, text=True, timeout=120,
                       preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_STACK, (eight, hard)))
    check("the named gap: JSON 300,000 deep is read by Node, and on an 8 MiB stack refused here as a ValueError, never a RecursionError",
          read_by_node is True and r.returncode == 0 and r.stdout.strip() == "ValueError", (read_by_node, r.returncode, r.stdout, r.stderr[-300:]))

    pairs = [["k", v] for v in ["fabric:control", "a b", "~*-._!'()", "\u00e9\U0001F600", "a&b=c", "%", "+", "\u2028", ""]]
    pairs += [[f"k{i}", "".join(rnd.choice("  !'()*+-._~=&%/:?#\u00e9") for _ in range(6))] for i in range(500)]
    diff("search_params is URLSearchParams().toString()", pairs, [js.search_params([p]) for p in pairs],
         node("return input.map(p => new URLSearchParams([p]).toString());", pairs))
    iso = js.iso_now()
    check("iso_now is toISOString()'s shape", re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", iso) is not None, iso)

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
