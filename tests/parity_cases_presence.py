"""Parity cases for control/presence.py against runtime/control/presence.mjs (tests/control_parity.py)."""
ON = {"status": "ok", "online": True, "role": "web-dev"}
OFF = {"status": "ok", "online": False, "role": "web-dev"}
ANSWERS = {"h/py": OFF, "h/web": ON, "h/x": {"status": "failed"}, "h/plan": {**ON, "planning": True}}
PLACED = ["h/py", "h/web", "h/x", "h/plan"]
SHAPES = [{"TO": "h/web"}, {"TO": " h/py "}, {"TO": "h/gone"}, {"TO": "h/x"}, {"TO": "h/plan"}, {"TO-ROLE": "web-dev"},
          {"TO-ROLE": "db-admin"}, {"BROADCAST": "true", "TO": "h/py"}, {}, {"TO": "\ufeffh/web"}]
CASES = [
    {"name": "check_addressees on every addressing, with the same answers", "module": "presence",
     "input": {"answers": ANSWERS, "placed": PLACED, "shapes": SHAPES},
     "node": "const ask = async ({ expect }) => Object.fromEntries(expect.map(a => [a, a in input.answers ? input.answers[a] : null]));"
             "const out = []; for (const s of input.shapes) out.push(await m.checkAddressees(s, { from: 'h/user', token: 't', placed: input.placed, ask })); return out;",
     "py": "ask = lambda *, expect, **kw: {a: input['answers'].get(a) for a in expect}\n"
           "return [m.check_addressees(s, from_='h/user', token='t', placed=input['placed'], ask=ask) for s in input['shapes']]"},
    {"name": "exit codes of every answer shape", "module": "presence",
     "input": [{"checked": False}, {"checked": True, "problems": [{"kind": "offline"}]}, {"checked": True, "problems": [{"kind": "silent"}]},
               {"checked": True, "problems": [{"kind": "no-holder", "silent": ["a"]}]}, {"checked": True, "problems": [{"kind": "unavailable"}]},
               {"error": "x", "status": None}],
     "node": "return input.map(a => m.exitCodeOf(a));", "py": "return [m.exit_code_of(a) for a in input]"},
]
