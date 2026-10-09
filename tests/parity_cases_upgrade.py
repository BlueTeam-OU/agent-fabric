"""Parity cases for control/upgrade.py against runtime/control/upgrade.mjs (tests/control_parity.py):
the argument check, the pin, the state directory, the marker's bytes, the session list, the
provider, the budgets, and two whole upgrades with the same fake harness on each side."""
ARGS = [None, "x", 5, [], [1], {}, {"piece": "claude"}, {"piece": "fabric"}, {"piece": "kernel"}, {"piece": 5}, {"piece": ["claude"]}, {"piece": None},
        {"piece": "claude", "version": "2.1.281"}, {"piece": "claude", "version": "2.1.281\n"}, {"piece": "claude", "version": None},
        {"piece": "claude", "version": 2}, {"piece": "claude", "version": "12345.1.1"}, {"piece": "claude", "version": "1.1.1234567"},
        {"piece": "claude", "commit": "a" * 40}, {"piece": "claude", "commit": None}, {"piece": "claude", "version": "2.1.281; rm -rf /"},
        {"piece": "a" * 40}, {"piece": "fabric", "commit": "a" * 40}, {"piece": "fabric", "commit": "A" * 40}, {"piece": "fabric", "commit": "a" * 39},
        {"piece": "fabric", "commit": "a" * 40 + "\n"}, {"piece": "fabric", "commit": 12345}, {"piece": "fabric", "commit": "a" * 40, "version": "1.1.1"},
        {"piece": "fabric", "commit": "a" * 40, "version": None}, {"piece": "fabric"}, {"piece": "fabric", "commit": None}]
PINS = ['{"claude": "2.1.281"}', '{"claude": "2.1.281\\n"}', '{"claude": null}', '{"claude": 2}', '{"claude": "x"}', '{}', '[]', 'null', '"2.1.281"',
        'not json', '', '{"claude": "0.0.0"}', '{"claude": "99999.1.1"}']
STATES = [[None, {}, "u"], ["/h", {}, "u"], ["/h", {"XDG_STATE_HOME": "/x/"}, "u"], ["/h", {"XDG_STATE_HOME": ""}, "u"], ["/h", {"XDG_STATE_HOME": "/x//y/../z"}, "u2"],
          ["/h", {"AGENT_FABRIC_STATE_DIR": "/s/a/../b"}, "u"], ["/h", {"AGENT_FABRIC_STATE_DIR": "", "XDG_STATE_HOME": "/x"}, "u"],
          ["/h", {"AGENT_FABRIC_STATE_DIR": "/s", "XDG_STATE_HOME": "/x"}, "u"]]
LASTS = [{"stderr": "Downloading\n\nError: x\n"}, {"stderr": "", "stdout": "out one\nout two\n"}, {"message": "only this"}, {"stderr": "  \n", "message": "m1\nm2"},
         {}, {"stderr": None, "stdout": None, "message": ""}, {"stderr": "a\r\nb\r\n"}, {"stdout": "x", "message": "y"}]
STATS = {"100": "100 (claude) S 50 1 1 0 -1", "200": "200 (claude) S 999 1 1 0 -1", "300": "300 (a) b) c) R 60 1 1", "500": "garbage", "600": "600 (x) S"}
ENVIRONS = {"1": "HOME=/h\0AGENT_FABRIC_LAUNCH_PROVIDER=openrouter\0", "2": "AGENT_FABRIC_LAUNCH_PROVIDER=$(x)\0", "3": "AGENT_FABRIC_LAUNCH_PROVIDER=\0",
            "4": "AGENT_FABRIC_LAUNCH_PROVIDER=Bad\0", "5": "AGENT_FABRIC_LAUNCH_PROVIDER=" + "a" * 33 + "\0", "6": "AGENT_FABRIC_LAUNCH_PROVIDER=a-b9\0"}
MARKER = {"request_id": "r", "requested_at": "2026-09-24T21:00:00.000Z", "piece": "claude", "from": "2.1.280", "to": "2.1.281", "pids": [4242, 7],
          "status": "done", "installed": "2.1.281", "note": "caf\u00e9 \u2014 \U0001F600", "empty": {}, "none": [], "nested": {"a": [1, 2.5, None, True]}}
CASES = [
    {"name": "check_args over every shape of argument a request can carry", "module": "upgrade", "input": ARGS,
     "node": "return input.map(a => m.checkArgs(a));", "py": "return [m.check_args(a) for a in input]"},
    {"name": "the pinned version over every harness.json body", "module": "upgrade", "input": PINS,
     "node": "const fs = await import('node:fs'); const os = await import('node:os'); const path = await import('node:path');"
             "const out = []; for (const body of input) { const root = fs.mkdtempSync(path.join(os.tmpdir(), 'pin-')); fs.mkdirSync(path.join(root, 'runtime', 'claude-code'), { recursive: true });"
             "fs.writeFileSync(path.join(root, 'runtime', 'claude-code', 'harness.json'), body); out.push(m.pinnedVersion(root)); fs.rmSync(root, { recursive: true }); }"
             "out.push(m.pinnedVersion('/nonexistent/root')); return out;",
     "py": "import os, shutil, tempfile\nout = []\nfor body in input:\n    root = tempfile.mkdtemp(prefix='pin-')\n    os.makedirs(os.path.join(root, 'runtime', 'claude-code'))\n"
           "    with open(os.path.join(root, 'runtime', 'claude-code', 'harness.json'), 'w') as fh:\n        fh.write(body)\n    out.append(m.pinned_version(root))\n    shutil.rmtree(root)\n"
           "out.append(m.pinned_version('/nonexistent/root'))\nreturn out"},
    {"name": "the state directory for a home, an environment and a login", "module": "upgrade", "input": STATES,
     "node": "return input.map(([h, e, l]) => m.stateDir(h ?? undefined, e, l));", "py": "return [m.state_dir(h, e, l) for h, e, l in input]"},
    {"name": "the last line that says what went wrong", "module": "upgrade", "input": LASTS,
     "node": "return input.map(e => m.lastLine(e));",
     "py": "from types import SimpleNamespace\nreturn [m.last_line(SimpleNamespace(**e)) for e in input]"},
    {"name": "the session list: this uid's claude except the daemon's children, over odd stat lines", "module": "upgrade", "input": STATS,
     "node": "const fs = await import('node:fs'); const os = await import('node:os'); const path = await import('node:path');"
             "const proc = fs.mkdtempSync(path.join(os.tmpdir(), 'proc-')); for (const [pid, s] of Object.entries(input)) { fs.mkdirSync(path.join(proc, pid)); fs.writeFileSync(path.join(proc, pid, 'stat'), s); }"
             "const out = [m.sessionPids({ self: 999, proc, exec: () => '100\\n200\\n300\\n400\\n500\\n600\\nabc\\n\\n' }), m.sessionPids({ self: 50, proc, exec: () => '100\\n' })];"
             "try { m.sessionPids({ self: 1, proc, exec: () => { const e = new Error('x'); e.status = 1; throw e; } }); out.push('none'); } catch { out.push('threw'); }"
             "fs.rmSync(proc, { recursive: true }); return out;",
     "py": "import os, shutil, subprocess, tempfile\nproc = tempfile.mkdtemp(prefix='proc-')\nfor pid, s in input.items():\n    os.mkdir(os.path.join(proc, pid))\n"
           "    with open(os.path.join(proc, pid, 'stat'), 'w') as fh:\n        fh.write(s)\n"
           "out = [m.session_pids(self_pid=999, proc=proc, run=lambda a: '100\\n200\\n300\\n400\\n500\\n600\\nabc\\n\\n'), m.session_pids(self_pid=50, proc=proc, run=lambda a: '100\\n')]\n"
           "def one(a):\n    raise subprocess.CalledProcessError(1, a)\n"
           "out.append(m.session_pids(self_pid=1, proc=proc, run=one) == [] and 'none')\nshutil.rmtree(proc)\nreturn out"},
    {"name": "the provider a running session was launched for", "module": "upgrade", "input": ENVIRONS,
     "node": "const fs = await import('node:fs'); const os = await import('node:os'); const path = await import('node:path');"
             "const proc = fs.mkdtempSync(path.join(os.tmpdir(), 'env-')); for (const [pid, s] of Object.entries(input)) { fs.mkdirSync(path.join(proc, pid)); fs.writeFileSync(path.join(proc, pid, 'environ'), s); }"
             "const out = Object.keys(input).map(p => m.sessionProvider([Number(p)], proc)); out.push(m.sessionProvider([99, 1], proc), m.sessionProvider([], proc)); fs.rmSync(proc, { recursive: true }); return out;",
     "py": "import os, shutil, tempfile\nproc = tempfile.mkdtemp(prefix='env-')\nfor pid, s in input.items():\n    os.mkdir(os.path.join(proc, pid))\n"
           "    with open(os.path.join(proc, pid, 'environ'), 'wb') as fh:\n        fh.write(s.encode())\n"
           "out = [m.session_provider([int(p)], proc) for p in input]\nout += [m.session_provider([99, 1], proc), m.session_provider([], proc)]\nshutil.rmtree(proc)\nreturn out"},
    {"name": "the budgets and the closed sets", "module": "upgrade", "input": None,
     "node": "return [m.PIECES, m.STOP_WAIT_MS, m.VERSION_TIMEOUT_MS, m.INSTALL_LEASE, m.LEASE_WAIT_S, m.LEASE_HELD, m.INSTALL_TIMEOUT_MS, m.POST_STOP_BUDGET_S, m.UPGRADE_BUDGET_S,"
             " m.FABRIC_GIT_TIMEOUT_MS, m.BOOTSTRAP_TIMEOUT_MS, m.FABRIC_UPGRADE_BUDGET_S];",
     "py": "return [m.PIECES, m.STOP_WAIT_MS, m.VERSION_TIMEOUT_MS, m.INSTALL_LEASE, m.LEASE_WAIT_S, m.LEASE_HELD, m.INSTALL_TIMEOUT_MS, m.POST_STOP_BUDGET_S, m.UPGRADE_BUDGET_S,"
           " m.FABRIC_GIT_TIMEOUT_MS, m.BOOTSTRAP_TIMEOUT_MS, m.FABRIC_UPGRADE_BUDGET_S]"},
    {"name": "the marker's bytes: indent two, a newline, non-ASCII as itself, empty containers", "module": "upgrade", "input": MARKER,
     "files": ["marker/restart.json"],
     "node": "m.writeMarker(`${home.root}/marker`, input); return m.markerPath('/d');",
     "py": "import os\nm.write_marker(os.path.join(home['root'], 'marker'), input)\nreturn m.marker_path('/d')"},
    {"name": "a whole upgrade: a session stopped, the install verified, the marker written; then one whose install fails", "module": "upgrade", "input": None,
     "files": ["up1/restart.json", "up2/restart.json"],
     "node": "const fs = await import('node:fs'); const path = await import('node:path');"
             "const mk = (name, fail) => { const root = `${home.root}/${name}-root`; fs.mkdirSync(`${root}/runtime/claude-code`, { recursive: true }); fs.writeFileSync(`${root}/runtime/claude-code/harness.json`, '{\"claude\":\"2.1.281\"}'); let cur = '2.1.280';"
             "const calls = []; const exec = async (b, a) => { calls.push(path.basename(b) + ' ' + a.join(' ')); if (a[0] === '--version') return { stdout: cur + ' (Claude Code)\\n' }; if (a[0] === 'install') { if (fail) { const e = new Error('Command failed'); e.stderr = 'Install failed: network\\n'; throw e; } cur = a[1]; return { stdout: '' }; } return { stdout: '', stderr: '' }; };"
             "return { root, exec, calls }; };"
             "const out = []; for (const [name, fail] of [['up1', false], ['up2', true]]) { const x = mk(name, fail); let up = true; const sigs = [];"
             "const r = await m.upgradeOnce({ id: 'r1', from: 'h/user', args: { piece: 'claude' } }, { home: `${home.root}/${name}-home`, root: x.root, dir: `${home.root}/${name}`, exec: x.exec, lease: async () => ({ release: async () => { sigs.push('released'); } }),"
             "sessions: [4242], kill: (p, s) => { sigs.push(`${p} ${s}`); up = false; }, alive: () => up, sleep: async () => {}, me: 'h/x', now: () => new Date('2026-09-24T21:00:00Z') });"
             "out.push(r, x.calls.filter(c => !c.startsWith('python3')), sigs); } return out;",
     "py": "import os, subprocess, sys\nfrom datetime import datetime, timezone\nfrom types import SimpleNamespace\nout = []\n"
           "for name, fail in (('up1', False), ('up2', True)):\n    root = os.path.join(home['root'], name + '-root')\n    os.makedirs(os.path.join(root, 'runtime', 'claude-code'))\n"
           "    with open(os.path.join(root, 'runtime', 'claude-code', 'harness.json'), 'w') as fh:\n        fh.write('{\"claude\":\"2.1.281\"}')\n"
           "    cur, calls, sigs, up = ['2.1.280'], [], [], [True]\n"
           "    def run(cmd, cur=cur, calls=calls, fail=fail, **kw):\n        if cmd[0] == sys.executable:\n            return SimpleNamespace(stdout=b'', stderr=b'')\n"
           "        calls.append(os.path.basename(cmd[0]) + ' ' + ' '.join(cmd[1:]))\n"
           "        if cmd[1] == '--version':\n            return SimpleNamespace(stdout=(cur[0] + ' (Claude Code)\\n').encode(), stderr=b'')\n"
           "        if cmd[1] == 'install':\n            if fail:\n                raise subprocess.CalledProcessError(1, cmd, b'', b'Install failed: network\\n')\n            cur[0] = cmd[2]\n            return SimpleNamespace(stdout=b'', stderr=b'')\n"
           "    class L:\n        def release(self, sigs=sigs):\n            sigs.append('released')\n"
           "    def kill(p, s, sigs=sigs, up=up):\n        sigs.append(f'{p} SIGTERM')\n        up[0] = False\n"
           "    r = m.upgrade_once({'id': 'r1', 'from': 'h/user', 'args': {'piece': 'claude'}}, home=os.path.join(home['root'], name + '-home'), root=root, directory=os.path.join(home['root'], name),"
           " run=run, lease=lambda: L(), sessions=[4242], kill=kill, alive=lambda p, up=up: up[0], sleep=lambda s: None, me='h/x', now=lambda: datetime(2026, 9, 24, 21, 0, tzinfo=timezone.utc))\n"
           "    out += [r, calls, sigs]\nreturn out"},
]
