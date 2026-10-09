"""Parity cases for control/pool.py against runtime/control/pool.mjs (tests/control_parity.py):
the same adds, lists and claims on each side's pool file, whose bytes are compared."""
STEPS = [["add", {"role": "python-dev", "title": "  port  \u00e9 it ", "topic": "t", "priority": "high"}],
         ["add", {"role": "web-dev", "title": "x", "project": "gzapp"}], ["add", {"role": "python-dev", "title": "low", "priority": "low"}],
         ["add", {"role": "nobody", "title": "x"}], ["list", "python-dev"], ["claim", "p1", "h/py", "python-dev"],
         ["claim", "p1", "h/web", "web-dev"], ["claim", "p1", "h/py", "python-dev"], ["claim", "p3", "h/web", "web-dev"], ["list", "python-dev"]]
CASES = [
    {"name": "adds, lists and claims answer alike and write the same pool.json", "module": "pool", "input": STEPS,
     "files": ["pool.json"],
     "node": "const file = `${home.root}/pool.json`; const known = new Set(['python-dev', 'web-dev']); let n = 0; const out = [];"
             "for (const s of input) { const now = () => `2026-10-08T00:00:0${n++}Z`;"
             " if (s[0] === 'add') out.push(m.poolAdd({ from: 'h/user', to: ['h/user'], args: s[1] }, { me: 'h/user', holder: 'h/user', file, known, now }));"
             " else if (s[0] === 'list') out.push(m.poolList({ from: 'h/py', args: { role: s[1] } }, { me: 'h/user', holder: 'h/user', file }));"
             " else out.push(await m.poolClaim({ from: s[2], args: { id: s[1] } }, { me: 'h/user', holder: 'h/user', file, now, roleOf: async () => ({ role: s[3] }) })); }"
             "return out;",
     "py": "import os\nfile = os.path.join(home['root'], 'pool.json')\nknown = {'python-dev', 'web-dev'}\nn = [0]\nout = []\n"
           "def now():\n    s = f'2026-10-08T00:00:0{n[0]}Z'\n    n[0] += 1\n    return s\n"
           "for s in input:\n    if s[0] == 'add':\n        out.append(m.pool_add({'from': 'h/user', 'to': ['h/user'], 'args': s[1]}, me='h/user', holder='h/user', file=file, known=known, now=now))\n"
           "    elif s[0] == 'list':\n        out.append(m.pool_list({'from': 'h/py', 'args': {'role': s[1]}}, me='h/user', holder='h/user', file=file))\n"
           "    else:\n        out.append(m.pool_claim({'from': s[2], 'args': {'id': s[1]}}, me='h/user', holder='h/user', file=file, now=now, role_of=lambda a, r=s[3]: {'role': r}))\n"
           "return out"},
    {"name": "the holder from the fixture's registry", "module": "pool", "input": None,
     "node": "return [m.poolHolder({}, home.registry), m.poolHolder({ pool_holder: 'k/c' }, home.registry)];",
     "py": "return [m.pool_holder({}, home['registry']), m.pool_holder({'pool_holder': 'k/c'}, home['registry'])]"},
]
