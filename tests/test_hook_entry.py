#!/usr/bin/env python3
"""runtime/claude-code/managed/hook_entry.py, the program every managed hook runs (agent-fabric ADR-043 rule 2),
against a scratch snapshot reached through a `current` link, run as the managed file runs it (`python -I -S
<entry> <name>`) from a hostile session environment: fake python3, bash, sh, git, env and cat first on PATH,
PYTHONPATH and PYTHONSTARTUP naming marker-writing modules, BASH_ENV and ENV naming a marker-writing script,
AGENT_FABRIC_ROOT naming a hostile tree with a guard of its own, AGENT_FABRIC_PYTHON naming a fake interpreter.
None of them runs; the guard runs from the snapshot, resolved through the link once, with exactly the carried
variables and the fixed ones, stdin passed through; the real review fence denies the reviewer from there; an
unknown name, a missing module and a failed guard ask; plan-hold stays silent and is exec'd (the harness stays its
parent). The scratch snapshot is outside the installed prefix, so the guards run on this interpreter by the test
override, which an entry under the installed prefix ignores.
Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from instance_fixtures import own_instance_tree  # noqa: E402
own_instance_tree()

ROOT = os.path.dirname(HERE)
ENTRY = os.path.join(ROOT, "runtime", "claude-code", "managed", "hook_entry.py")
HOOKS = os.path.join(ROOT, "runtime", "claude-code", "hooks")
sys.path.insert(0, os.path.dirname(ENTRY))
import hook_entry  # noqa: E402

# A guard that reports what it was given: its path, interpreter, flags, environment, stdin and parent.
REPORT = """import json, os, sys
print(json.dumps({"argv0": sys.argv[0], "exe": sys.executable, "isolated": sys.flags.isolated,
                  "no_site": sys.flags.no_site, "env": dict(os.environ), "stdin": sys.stdin.read(),
                  "ppid": os.getppid()}))
"""


def write(path: str, text: str, mode: int = 0o644) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(path, mode)


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    with tempfile.TemporaryDirectory() as tmp:
        tmp = os.path.realpath(tmp)
        marks = os.path.join(tmp, "marks")
        os.makedirs(marks)
        managed = os.path.join(tmp, "lib", "managed")
        snap = os.path.join(managed, "fabric-" + "a" * 40)
        os.makedirs(os.path.join(snap, "runtime", "claude-code", "managed"))
        os.makedirs(os.path.join(snap, "runtime", "claude-code", "hooks"))
        shutil.copy(ENTRY, os.path.join(snap, "runtime", "claude-code", "managed", "hook_entry.py"))
        for name in ("review-fence.py", "hook_jq.py"):
            shutil.copy(os.path.join(HOOKS, name), os.path.join(snap, "runtime", "claude-code", "hooks", name))
        write(os.path.join(snap, "runtime", "claude-code", "hooks", "pipe-status-guard.py"), REPORT)
        write(os.path.join(snap, "tools", "fabric", "plan_hold.py"), REPORT)
        write(os.path.join(snap, "runtime", "claude-code", "hooks", "job-copy-guard.py"), "import sys\nsys.exit(3)\n")
        os.symlink(os.path.basename(snap), os.path.join(managed, "current"))
        entry = os.path.join(managed, "current", "runtime", "claude-code", "managed", "hook_entry.py")

        evil = os.path.join(tmp, "evil")
        for prog in ("python3", "python", "bash", "sh", "git", "env", "cat", "fabric-python"):
            write(os.path.join(evil, "bin", prog), f"#!/bin/sh\ntouch {marks}/bin-{prog}\nexit 1\n", 0o755)
        write(os.path.join(evil, "bashenv"), f"touch {marks}/bash-env\n", 0o755)
        for mod in ("sitecustomize", "usercustomize", "json", "subprocess", "hook_jq", "os"):
            write(os.path.join(evil, "pylib", f"{mod}.py"), f"open({os.path.join(marks, 'py-' + mod)!r}, 'w').close()\n")
        write(os.path.join(evil, "startup.py"), f"open({os.path.join(marks, 'py-startup')!r}, 'w').close()\n")
        hostile_root = os.path.join(evil, "fabric")
        for rel in ("runtime/claude-code/hooks/pipe-status-guard.py", "runtime/claude-code/hooks/review-fence.py",
                    "tools/fabric/plan_hold.py"):
            write(os.path.join(hostile_root, rel), f"open({os.path.join(marks, 'hostile-root')!r}, 'w').close()\n")
        home = os.path.join(tmp, "home")
        os.makedirs(home)
        kept = {"HOME": home, "USER": "u", "LOGNAME": "u", "XDG_STATE_HOME": os.path.join(home, "state"),
                "CLAUDE_CODE_SESSION_ID": "sess-1", "CLAUDE_PID": "4242", "CLAUDE_CONFIG_DIR": os.path.join(home, "cc"),
                "AGENT_FABRIC_LAUNCH_PROVIDER": "anthropic", "AGENT_FABRIC_LAUNCH_PROFILE": "p", "LANG": "C.UTF-8",
                "TMPDIR": tmp, "TERM": "xterm"}
        hostile = {"PATH": f"{evil}/bin:/usr/local/bin:/usr/bin:/bin", "BASH_ENV": f"{evil}/bashenv",
                   "ENV": f"{evil}/bashenv", "PYTHONPATH": f"{evil}/pylib", "PYTHONSTARTUP": f"{evil}/startup.py",
                   "PYTHONHOME": f"{evil}/pyhome-not-there", "PYTHONINSPECT": "", "BASH_FUNC_cat%%": "() { touch x; }",
                   "AGENT_FABRIC_ROOT": hostile_root, "AGENT_FABRIC_PYTHON": f"{evil}/bin/python3",
                   "AGENT_FABRIC_OPERATOR": hostile_root, "HOSTILE_VAR": "1", "GIT_DIR": evil, "LD_PRELOAD": "",
                   hook_entry.TEST_PY: sys.executable}
        hostile.pop("PYTHONHOME")      # a PYTHONHOME would stop this interpreter before -I is read; not the entry's
        env = {**kept, **hostile}

        def run(*args: str, payload: object = None, environ: dict = env) -> subprocess.CompletedProcess:
            data = json.dumps(payload if payload is not None else {"hook_event_name": "PreToolUse"}).encode()
            return subprocess.run([sys.executable, "-I", "-S", entry, *args], input=data, capture_output=True,
                                  env=environ, cwd=os.path.join(evil, "pylib"), timeout=60)

        def report(r):
            try:
                return json.loads(r.stdout)
            except ValueError:
                return {}

        def said(r):
            try:
                return json.loads(r.stdout)["hookSpecificOutput"]
            except (ValueError, KeyError, TypeError):
                return {}

        print("hook_entry: the hostile environment")
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}}
        r = run("pipe-status-guard", payload=payload)
        got = report(r)
        check("the guard runs from the snapshot, resolved through current to fabric-<sha>",
              r.returncode == 0 and got.get("argv0") == os.path.join(snap, "runtime/claude-code/hooks/pipe-status-guard.py"),
              (r.stdout, r.stderr))
        check("…isolated and without site (-I -S)", got.get("isolated") == 1 and got.get("no_site") == 1, got)
        genv = got.get("env", {})
        want = {**kept, "AGENT_FABRIC_ROOT": snap, "AGENT_FABRIC_PYTHON": sys.executable,
                "PATH": "/usr/local/bin:/usr/bin:/bin"}
        check("its environment: the carried variables and the fixed ones, nothing else",
              {k: v for k, v in genv.items() if k != "LC_CTYPE"} == want, sorted(set(genv) ^ set(want)))
        check("stdin passed through", got.get("stdin") == json.dumps(payload), got.get("stdin"))
        check("nothing hostile ran: no fake program, no BASH_ENV, no PYTHON* module, not the hostile root's guard",
              os.listdir(marks) == [], os.listdir(marks))
        r = run("review-fence", payload={**payload, "agent_type": "code-review", "agent_id": "a1"})
        check("the real review fence, from the snapshot: the reviewer's Bash denied",
              said(r).get("permissionDecision") == "deny" and "ADR-065" in said(r).get("permissionDecisionReason", ""),
              (r.stdout, r.stderr))
        r = run("review-fence", payload=payload)
        check("…the main session's passes in silence", (r.returncode, r.stdout) == (0, b""), r.stdout)
        check("…and still nothing hostile ran", os.listdir(marks) == [], os.listdir(marks))

        print("hook_entry: the table and its fallbacks")
        for args in (("no-such-guard",), ("../../evil",), (), ("pipe-status-guard", "extra")):
            r = run(*args)
            check(f"argv {list(args)}: asks, exit 0", r.returncode == 0 and said(r).get("permissionDecision") == "ask"
                  and said(r).get("hookEventName") == "PreToolUse", (r.stdout, r.stderr))
        r = run("self-kill-guard")
        check("a gate whose module is missing asks, the self-kill guard included (it passed in silence before)",
              said(r).get("permissionDecision") == "ask" and "could not run" in said(r).get("permissionDecisionReason", "")
              and "not in the managed snapshot" in said(r)["permissionDecisionReason"], r.stdout)
        r = run("model-switch-guard")
        check("…on its own event: the model-switch guard asks as PreModelSwitch",
              said(r).get("hookEventName") == "PreModelSwitch" and said(r).get("permissionDecision") == "ask", r.stdout)
        r = run("job-copy-guard")
        check("a guard that fails (exit 3, nothing said) asks, never passes",
              said(r).get("permissionDecision") == "ask" and "the guard failed" in said(r).get("permissionDecisionReason", ""),
              r.stdout)
        r = run("plan-hold")
        got = report(r)
        check("plan-hold is exec'd: its parent is the harness (here, this test), its environment the fixed one",
              r.returncode == 0 and got.get("ppid") == os.getpid() and got.get("env", {}).get("AGENT_FABRIC_ROOT") == snap,
              (r.stdout, r.stderr))
        os.remove(os.path.join(snap, "tools", "fabric", "plan_hold.py"))
        r = run("plan-hold")
        check("…and missing, it stays silent: it never refuses", (r.returncode, r.stdout) == (0, b""), r.stdout)
        r = run("pipe-status-guard", environ={**env, hook_entry.TEST_PY: os.path.join(tmp, "no-python")})
        check("an interpreter that is not there: the gate asks", said(r).get("permissionDecision") == "ask", r.stdout)

        print("hook_entry: the test override")
        check("outside the installed prefix, a test may name the guards' interpreter",
              hook_entry.interpreter(snap, {hook_entry.TEST_PY: "/x/python"}) == "/x/python")
        check("under /usr/local/lib/agent-fabric/, never: the pin, whatever the environment says",
              hook_entry.interpreter("/usr/local/lib/agent-fabric/managed/fabric-" + "a" * 40,
                                     {hook_entry.TEST_PY: "/x/python"}) == hook_entry.PY == "/usr/local/bin/fabric-python")
        check("…nor a prefix that merely starts with its name",
              hook_entry.interpreter("/usr/local/lib/agent-fabric-x/managed/fabric-a", {hook_entry.TEST_PY: "/x"}) == "/x")
        check("with no override, the pin", hook_entry.interpreter(snap, {}) == hook_entry.PY)

    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
