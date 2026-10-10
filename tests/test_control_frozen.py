#!/usr/bin/env python3
"""The control plane's parity cases for ctl, upgrade, sessions and queue
(ADR-040 Wave 8), kept after the Node was deleted (step s8). Each case was run
through runtime/control/<module>.mjs and through the Python module, against
the same fixture homes, and the two answers compared byte for byte; the Node's
answers are frozen in tests/fixtures/node-oracle-ctl-upgrade-sessions-queue.json
beside the case's input and its Python body, and the Python side is run here
and compared with them. The cases are the old parity suite's, unchanged
(tests/parity_cases_{ctl,upgrade,sessions,queue}.py at origin/main before s8):
ctl's argv and every table over answered, forged and partial replies, upgrade's
argument check and marker bytes, the sessions' state records, the queue's CLI.
The cases of sign, protocol, presence, pool, jobs and gzcoord are frozen in
the test_control_* file of each module. A new input has no Node to ask: it is a
case of its own with an expected value written by hand."""
from __future__ import annotations

import json
import os
import pwd
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTROL_PY = os.path.join(HERE, "tools", "fabric")
FIXTURE = os.path.join(HERE, "tests", "fixtures", "node-oracle-ctl-upgrade-sessions-queue.json")
HOST = "h"
FIXTURE_OPERATOR = os.path.join(HERE, "tests", "fixtures", "gzcoord-operator")
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
           "AGENT_FABRIC_ROOT": HERE, "TMPDIR": tmp,
           # The role catalogue is the operator's instance file: a pool-add case
           # names a role, and reads this fixture's catalogue, not the checkout's.
           "AGENT_FABRIC_OPERATOR": FIXTURE_OPERATOR}
    return {"home": home, "env": env}


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
    try:
        answers = json.loads(r.stdout)
    except ValueError:
        raise RuntimeError(f"{cmd[0]} answered no JSON: {r.stdout.strip()[:200]!r}") from None
    if not isinstance(answers, list):
        raise RuntimeError(f"{cmd[0]} answered {type(answers).__name__}, not a list of answers")
    if len(answers) != len(payload["cases"]):
        raise RuntimeError(f"{cmd[0]} answered {len(answers)} of {len(payload['cases'])} cases")
    for i, a in enumerate(answers):
        # Each is a case's answer as its side wrote it: an object holding
        # `value` (with `files`) or `threw`. Anything else, the same on both
        # sides, would compare equal and pass.
        try:
            parsed = json.loads(a) if isinstance(a, str) else None
        except ValueError:
            parsed = None
        if not (isinstance(parsed, dict) and (("value" in parsed and isinstance(parsed.get("files"), dict)) or parsed.get("threw") is True)):
            raise RuntimeError(f"{cmd[0]} answered case {i} with {a!r:.200}, not an answer object")
    return answers


def run_python(cases: list[dict]) -> list[str]:
    """Python's answer to every case, in one process and one fixture built
    as the Node's was; a path inside the fixture is said as <root>."""
    with tempfile.TemporaryDirectory(prefix="control-frozen.") as tmp:
        fx = build(os.path.join(tmp, "py"))
        payload = {"cases": [{k: c[k] for k in ("module", "input", "py", "files") if k in c} for c in cases],
                   "home": fx["home"]}
        # -I: no '' on sys.path and no PYTHON* variable reaches the side.
        answers = _side([sys.executable, "-I", "-c", _PY, CONTROL_PY], payload, fx["env"], fx["home"]["root"])
        return [a.replace(os.path.join(tmp, "py"), "<root>") for a in answers]


def verdict(case: dict, frozen: str, py: str) -> str | None:
    """None when the case holds, else why it fails."""
    n, p = json.loads(frozen), json.loads(py)
    if case.get("error"):
        return None if n.get("threw") is True and p.get("threw") is True else "expected both sides to throw"
    threw = [f"{side} threw ({a.get('why')})" for side, a in (("node", n), ("python", p)) if a.get("threw")]
    if threw:
        return "; ".join(threw)
    if case.get("lenient_node_throw"):
        nv, pv = n.get("value"), p.get("value")
        if not (isinstance(nv, list) and isinstance(pv, list) and len(nv) == len(pv)):
            return "a lenient case answers a list of the same length on both sides"
        refused = lambda a: isinstance(a, dict) and "threw" in a  # noqa: E731
        compared = [i for i, a in enumerate(nv) if not refused(a)]
        if not compared:
            return "node refused every element: nothing was compared"
        bad = [i for i in compared if nv[i] != pv[i]]
        return None if not bad else f"{len(bad)} of {len(compared)} compared elements differ, the first at index {bad[0]}"
    return None if frozen == py else "the answers differ"




def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    with open(FIXTURE, encoding="utf-8") as fh:
        cases = json.load(fh)
    check("every module the fixture was frozen for has cases",
          {c["name"].split(":")[0] for c in cases} == {"ctl", "upgrade", "sessions", "queue"}, len(cases))
    answers = run_python(cases)
    for c, py in zip(cases, answers, strict=True):
        why = verdict(c, c["node"], py)
        check(c["name"], why is None, f"{why}\n      node={c['node'][:600]}\n      py  ={py[:600]}")

    print("the frozen answers can fail: a changed answer is found, an untouched one holds")
    probe = next(c for c in cases if not c.get("error") and not c.get("lenient_node_throw") and "threw" not in json.loads(c["node"]))
    p_answer = run_python([probe])[0]
    check("positive control: the probe holds as frozen", verdict(probe, probe["node"], p_answer) is None, p_answer[:200])
    mutated = json.dumps({**json.loads(probe["node"]), "value": ["changed"]})
    check("a frozen answer that differs is found", verdict(probe, mutated, p_answer) == "the answers differ")
    check("a lenient case needs some element Node answered",
          verdict({"lenient_node_throw": True}, json.dumps({"value": [{"threw": "x"}], "files": {}}),
                  json.dumps({"value": ["z"], "files": {}})) == "node refused every element: nothing was compared")
    with tempfile.TemporaryDirectory() as cwd:
        def side(code: str) -> str:
            try:
                _side([sys.executable, "-c", code], {"cases": [{}, {}]}, {"PATH": os.environ.get("PATH", "")}, cwd)
            except RuntimeError as e:
                return str(e)
            return "no error"
        check("a side that exits non-zero is an error", "exit 3" in side("import sys; sys.exit(3)"))
        check("a side that answers fewer cases is an error", "answered 1 of 2" in side("print('[\"{}\"]')"))
        check("a side that answers no JSON is an error", "answered no JSON" in side("print('nope')"))
        check("answers that are not answer objects are an error", "case 0 with" in side("print('[5, 6]')"))
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
