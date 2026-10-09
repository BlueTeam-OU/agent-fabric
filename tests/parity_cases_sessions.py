"""Parity cases for control/sessions.py against runtime/control/sessions.mjs (tests/control_parity.py):
each side reads the same state files in its fixture home."""
FILES = ['{"sessions": {"b": {"state": "working", "since": "t1"}, "a": {"state": "idle", "since": "2026-10-08T11:59:00Z"}}}',
         '{broken', '{}', '{"sessions": []}', '{"sessions": {}}', '\ufeff{"sessions": {}}', '[]', 'null',
         '{"sessions": {"z": {"state": "sleeping"}, "y": {"state": "blocked", "since": 5}}}']
CASES = [
    {"name": "read_sessions on files of every shape (none; unknown as null)", "module": "sessions", "input": FILES,
     "node": "const fs = await import('node:fs'); const f = `${home.root}/s.json`; const out = [];"
             "for (const t of input) { fs.writeFileSync(f, t); out.push(m.readSessions(f, { now: Date.parse('2026-10-08T12:00:00Z') })); }"
             "fs.rmSync(f); out.push(m.readSessions(f)); return out;",
     "py": "import os\nf = os.path.join(home['root'], 's.json')\nout = []\nfor t in input:\n    open(f, 'w', encoding='utf-8').write(t)\n"
           "    out.append(m.read_sessions(f, now_ms=m.date_parse('2026-10-08T12:00:00Z')))\nos.remove(f)\nout.append(m.read_sessions(f))\nreturn out"},
    {"name": "waits_on from job lists of every shape", "module": "sessions",
     "input": ['{"jobs": [{"state": "blocked", "waits_on": "01a11a19-0bea-70c7-b667-1e1e5a74dbe1"}, {"state": "blocked", "waits_on": "01a11a18-4728-7d8b-afd9-0edb2d30a59c"}, {"state": "queued", "waits_on": "01a11a20-0000-7000-8000-000000000000"}]}',
               '{broken', '{"jobs": 3}', '{"jobs": []}'],
     "node": "const fs = await import('node:fs'); const f = `${home.root}/j.json`; const out = [];"
             "for (const t of input) { fs.writeFileSync(f, t); out.push(m.waitsOn(f)); } out.push(m.waitsOn(`${home.root}/none.json`)); return out;",
     "py": "import os\nf = os.path.join(home['root'], 'j.json')\nout = []\nfor t in input:\n    open(f, 'w', encoding='utf-8').write(t)\n"
           "    out.append(m.waits_on(f))\nout.append(m.waits_on(os.path.join(home['root'], 'none.json')))\nreturn out"},
    {"name": "state_record with and without a binding", "module": "sessions",
     "input": [{"sessions": [], "role": None, "project": None}, {"sessions": [{"session": "s", "state": "idle", "since": "t"}], "role": "web-dev",
               "project": "gzapp", "last_session": "0f0e0d0c-1111-4222-8333-444455556666", "resumable": True,
               "waits_on": ["01a11a18-4728-7d8b-afd9-0edb2d30a59c"]}],
     "node": "return input.map(s => m.stateRecord('h/py', s, 't'));", "py": "return [m.state_record('h/py', s, 't') for s in input]"},
]
