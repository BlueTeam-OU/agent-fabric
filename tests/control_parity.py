"""tests/control_parity.py — the control plane's parity harness (ADR-040
Wave 8): every case run through runtime/control/*.mjs and through
tools/fabric/control/*.py, against the same fixture homes, and the
answers compared byte for byte, as JSON.stringify and js.stringify write
them (signatures included).

A case file is tests/parity_cases_<module>.py holding CASES, a list of
dicts, or cases(), a function answering one (for a case that needs a
value made when it runs, such as a key pair):
  name     what the case shows
  module   the module's name, the same on both sides (sign, pool, …)
  input    any JSON value, handed to both bodies as `input`
  node     a JavaScript function body over (m, input, home): m the
           runtime/control/<module>.mjs namespace, home the fixture
           (below); it returns the answer, and may await
  py       a Python function body over (m, input, home): m the
           tools/fabric/control/<module>.py module, with control.js as
           `js` in scope; it returns the answer
  files    optional: paths under the fixture root whose bytes, after the
           case ran, are part of the answer, carried as hex (persisted
           state frozen with the wire: pool.json); never decoded, so no
           newline or invalid byte is made equal on the way
  error    optional, True: each side is expected to throw; only that it
           threw is compared, never the text (each language words its own).
           Without it a throw on either side fails the case, said with
           why: a function renamed on both sides, or a module neither has
           yet, is never parity

Each side runs every case in ONE process (node, then python), each in its
own copy of the fixture, built identically: one home per account in
ACCOUNTS, a state dir with each account's binding and job list, and a
hosts registry placing them. An op that runs a tool as "this login"
(jobs) runs as the runner's own login, which no environment changes:
`home["self"]` names it, and its list is under the fixture's state dir. A case therefore never sees what another
side's case wrote, and a case that changes a file changes it only for the
cases after it on the same side.

compare(cases) answers [(name, node, python, why)] for every case that
fails, and runs nothing it cannot run: a side that does not start, exits
non-zero or answers fewer cases is an error, never an empty list.
"""
from __future__ import annotations

import json
import os
import pwd
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTROL_MJS = os.path.join(HERE, "runtime", "control")
CONTROL_PY = os.path.join(HERE, "tools", "fabric")
HOST = "h"
ACCOUNTS = ["user", "py", "web"]          # user: the operator; py, web: placed agents
ROLES = {"user": "fabric-coordinator", "py": "python-dev", "web": "web-dev"}
TIMEOUT_S = 300


def build(root: str) -> dict:
    """One fixture: a home per account, the state dir, the registry. Answers
    `home`, the value both bodies get, and the environment both sides run in."""
    state = os.path.join(root, "state")
    for login in ACCOUNTS:
        os.makedirs(os.path.join(root, "home", login), exist_ok=True)
        agent = os.path.join(state, "agents", login)
        os.makedirs(agent, exist_ok=True)
        with open(os.path.join(agent, "binding.json"), "w", encoding="utf-8") as fh:
            json.dump({"role": ROLES[login], "project": "agent-fabric"}, fh)
        with open(os.path.join(agent, "jobs.json"), "w", encoding="utf-8") as fh:
            json.dump({"jobs": []}, fh)
    registry = os.path.join(root, "registry.json")
    with open(registry, "w", encoding="utf-8") as fh:
        json.dump({"hosts": {HOST: {"operator": "user"}}, "placement": {login: HOST for login in ACCOUNTS if login != "user"}}, fh)
    tmp = os.path.join(root, "tmp")
    os.makedirs(tmp)
    home = {"root": root, "state": state, "self": pwd.getpwuid(os.geteuid()).pw_name, "registry": registry, "host": HOST, "accounts": ACCOUNTS,
            "homes": {login: os.path.join(root, "home", login) for login in ACCOUNTS},
            "agents": {login: os.path.join(state, "agents", login) for login in ACCOUNTS}}
    # A minimal, explicit environment: never the session's credentials,
    # proxies or state (tests own their environment); TMPDIR inside the
    # fixture, so what a side leaves there goes with it.
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8", "TZ": "UTC",
           "HOME": home["homes"]["user"], "AGENT_FABRIC_STATE_DIR": state, "AGENT_FABRIC_HOSTS_REGISTRY": registry,
           "AGENT_FABRIC_ROOT": HERE, "TMPDIR": tmp}
    return {"home": home, "env": env}


_NODE = r"""
import fs from 'node:fs';
const { cases, home, dir } = JSON.parse(fs.readFileSync(0, 'utf8'));
const out = [];
for (const c of cases) {
  try {
    const m = await import(`${dir}/${c.module}.mjs`);
    const run = new Function('m', 'input', 'home', `return (async () => { ${c.node} })();`);
    const value = await run(m, c.input, home);
    const files = Object.fromEntries((c.files ?? []).map(f => [f, fs.existsSync(`${home.root}/${f}`) ? fs.readFileSync(`${home.root}/${f}`).toString('hex') : null]));
    out.push(JSON.stringify({ value: value === undefined ? null : value, files }));
  } catch (e) { out.push(JSON.stringify({ threw: true, why: String(e?.stack ?? e).split('\n').slice(0, 3).join(' | ') })); }
}
process.stdout.write(JSON.stringify(out));
"""

_PY = r"""
import importlib, json, os, sys
sys.path.insert(0, sys.argv[1])
from control import js
req = json.load(sys.stdin)
out = []
for c in req["cases"]:
    try:
        m = importlib.import_module(f"control.{c['module']}")
        scope = {"js": js}
        body = "\n".join("    " + line for line in c["py"].splitlines()) or "    pass"
        exec("def run(m, input, home):\n" + body, scope)
        value = scope["run"](m, js.json_parse(json.dumps(c["input"])), req["home"])
        files = {}
        for f in c.get("files") or []:
            p = os.path.join(req["home"]["root"], f)
            if os.path.exists(p):
                with open(p, "rb") as fh:
                    files[f] = fh.read().hex()
            else:
                files[f] = None
        out.append(js.stringify({"value": value, "files": files}))
    except Exception as e:
        out.append(js.stringify({"threw": True, "why": f"{type(e).__name__}: {e}"[:300]}))
sys.stdout.write(json.dumps(out))
"""


def _side(cmd: list[str], payload: dict, env: dict, cwd: str) -> list[str]:
    # UTF-8, never the locale: Node writes its answers' text raw. The
    # fixture is the cwd, so nothing in the caller's directory is imported.
    r = subprocess.run(cmd, input=json.dumps(payload), capture_output=True, encoding="utf-8", env=env, cwd=cwd, timeout=TIMEOUT_S)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} could not run the cases (exit {r.returncode}): {r.stderr.strip()[-400:]}")
    answers = json.loads(r.stdout)
    if not isinstance(answers, list) or len(answers) != len(payload["cases"]):
        raise RuntimeError(f"{cmd[0]} answered {len(answers)} of {len(payload['cases'])} cases")
    return answers


def run(cases: list[dict]) -> list[tuple[str, str, str]]:
    """[(name, node answer, python answer)] for every case, each side in its own fixture."""
    with tempfile.TemporaryDirectory(prefix="control-parity.") as tmp:
        sides = {}
        for side in ("node", "py"):
            fx = build(os.path.join(tmp, side))
            payload = {"cases": [{k: c[k] for k in ("module", "input", "node", "py", "files") if k in c} for c in cases],
                       "home": fx["home"], "dir": CONTROL_MJS}
            # -I: no '' on sys.path and no PYTHON* variable reaches the side.
            cmd = ["node", "--input-type=module", "-e", _NODE] if side == "node" else [sys.executable, "-I", "-c", _PY, CONTROL_PY]
            sides[side] = _side(cmd, payload, fx["env"], fx["home"]["root"])
        # A path inside a fixture names that side's root: said the same on both.
        node = [a.replace(os.path.join(tmp, "node"), "<root>") for a in sides["node"]]
        py = [a.replace(os.path.join(tmp, "py"), "<root>") for a in sides["py"]]
        return [(c["name"], n, p) for c, n, p in zip(cases, node, py, strict=True)]


def verdict(case: dict, node: str, py: str) -> str | None:
    """None when the case holds, else why it fails."""
    n, p = json.loads(node), json.loads(py)
    if case.get("error"):
        return None if n.get("threw") is True and p.get("threw") is True else "expected both sides to throw"
    threw = [f"{side} threw ({a.get('why')})" for side, a in (("node", n), ("python", p)) if a.get("threw")]
    if threw:
        return "; ".join(threw)
    return None if node == py else "the answers differ"


def compare(cases: list[dict]) -> list[tuple[str, str, str, str]]:
    out = []
    for (name, n, p), c in zip(run(cases), cases, strict=True):
        why = verdict(c, n, p)
        if why:
            out.append((name, n, p, why))
    return out


def all_cases() -> list[dict]:
    """Every tests/parity_cases_*.py's CASES, in file order."""
    import importlib.util
    cases = []
    for f in sorted(os.listdir(os.path.dirname(os.path.abspath(__file__)))):
        if f.startswith("parity_cases_") and f.endswith(".py"):
            spec = importlib.util.spec_from_file_location(f[:-3], os.path.join(os.path.dirname(os.path.abspath(__file__)), f))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            listed = mod.cases() if hasattr(mod, "cases") else mod.CASES
            cases += [{**c, "name": f"{f[len('parity_cases_'):-3]}: {c['name']}"} for c in listed]
    return cases


if __name__ == "__main__":
    sys.exit("control_parity is a library: run tests/test_control_parity.py")
