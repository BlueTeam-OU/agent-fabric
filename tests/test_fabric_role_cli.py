#!/usr/bin/env python3
"""bin/fabric-role: the contract of its dispatch, frozen from the bash
(ADR-040 §5 rule 3) and held across the port (rule 5).

The entry runs as a subprocess; FABRIC_ROLE_ENTRY names another one (a path
ending .py runs under this interpreter), default bin/fabric-role. The
interpreter the entry execs is a fake (AGENT_FABRIC_PYTHON) that prints its
argv and runs nothing real, except that it lets the dispatcher module itself
(role_cli.py) through, so the oracle is the same against the bash, the
forwarder and the module. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import sys
import tempfile

from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY = os.environ.get("FABRIC_ROLE_ENTRY") or os.path.join(ROOT, "bin", "fabric-role")
GUARDS = ("CLAUDECODE", "CLAUDE_ENV_FILE", "AGENT_FABRIC_LAUNCH_PROFILE")
INSTALL = ("fabric-role: the fleet's pinned Python is not installed at %s; as root: "
           "/usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install\n")
FAKE = """#!{python}
import os, sys
if os.path.basename(sys.argv[1]) == "role_cli.py":
    os.execv(sys.executable, [sys.executable] + sys.argv[1:])
print("ARGV", os.path.basename(sys.argv[1]), *sys.argv[2:])
print("ROOT", os.environ.get("AGENT_FABRIC_ROOT"))
"""
HELP = """bin/fabric-role — bind a role to this agent, from a login shell, before
the session that will carry it. The launcher (runtime/openrouter/launch)
reads the binding and puts the role into the session's system prompt;
a running session never changes its role — a different role is a
rebind here and a relaunch.

  agent-fabric/bin/fabric-role bind <role> [--project ID] [--workspace DIR] [--force]
  agent-fabric/bin/fabric-role status         what is this agent right now?
  agent-fabric/bin/fabric-role unbind         drop the role
  agent-fabric/bin/fabric-role list           the roles available

bind and unbind refuse inside a harness session (the environment a Claude Code
session, or a fabric launch, carries): the binding would change under a
session whose prompt still says the old role, and the two would disagree
until a relaunch. The same refusal sits in tools/fabric/role.py itself,
so a Bash tool call that bypasses this script is refused too.

The full account is in tools/fabric/role.py (bind = activate, unbind =
deactivate — the Python names are unchanged).
"""
fails = 0
tmp = tempfile.mkdtemp(prefix="fabric-role-cli-")
# The runner fails a suite whose scratch outlives it; removed however the run ends.
atexit.register(shutil.rmtree, tmp, ignore_errors=True)
fake = os.path.join(tmp, "fake-python")
with open(fake, "w") as f:
    f.write(FAKE.format(python=sys.executable))
os.chmod(fake, 0o755)


def run(*args: str, env: dict | None = None, python: str | None = fake, entry: str | None = None):
    e = {k: v for k, v in os.environ.items() if k not in GUARDS + ("AGENT_FABRIC_ROOT", "AGENT_FABRIC_PYTHON")}
    if python is not None:
        e["AGENT_FABRIC_PYTHON"] = python
    e.update(env or {})
    entry = entry or ENTRY
    cmd = [sys.executable, entry, *args] if entry.endswith(".py") else [entry, *args]
    return subprocess.run(cmd, env=e, capture_output=True, text=True, stdin=subprocess.DEVNULL)


def check(name: str, got, want) -> None:
    global fails
    if got == want:
        print("ok   " + name)
    else:
        fails += 1
        print("FAIL %s\n  want %r\n  got  %r" % (name, want, got))


def outcome(name, r, code, out, err) -> None:
    check(name, (r.returncode, r.stdout, r.stderr), (code, out, err))


def refusal(var: str) -> str:
    return ("fabric-role: this is a harness session ($%s is set). A role is bound from a\n"
            "  login shell, never inside a session: the session's prompt already carries the\n"
            "  role it was launched with. Open a terminal, run fabric-role there, then relaunch.\n" % var)


def seen(verb: str, *rest: str, root: str = ROOT) -> str:
    return "ARGV role.py %s\nROOT %s\n" % (" ".join((verb, *rest)), root)


# Mutation: a guard variable dropped from the list, or the message reworded.
for var in GUARDS:
    for verb in ("bind", "unbind"):
        outcome("%s refused under %s" % (verb, var), run(verb, "r", env={var: "1"}), 1, "", refusal(var))
# Mutation: the first set variable is not the one named.
outcome("all three set: CLAUDECODE named", run("bind", env=dict.fromkeys(GUARDS, "1")), 1, "", refusal("CLAUDECODE"))
# Mutation: the refusal tests set rather than non-empty.
for verb, py in (("bind", "activate"), ("unbind", "deactivate")):
    outcome("%s with the guards empty is not refused" % verb,
            run(verb, "r", env=dict.fromkeys(GUARDS, "")), 0, seen(py, "r"), "")
# Mutation: status or list refused, or their verb renamed.
for var in GUARDS:
    for verb in ("status", "list"):
        outcome("%s never refused under %s" % (verb, var), run(verb, "-x", env={var: "1"}), 0, seen(verb, "-x"), "")
# Mutation: bind not mapped to activate, an argument dropped or reordered.
outcome("bind maps to activate, args through",
        run("bind", "dev", "--project", "p", "--workspace", "/w", "--force"), 0,
        seen("activate", "dev", "--project", "p", "--workspace", "/w", "--force"), "")
# Mutation: unbind not mapped to deactivate.
outcome("unbind maps to deactivate", run("unbind"), 0, seen("deactivate"), "")
# Mutation: a default other than status; an argument with a space split or an empty one dropped.
outcome("no argument is status", run(), 0, seen("status"), "")
outcome("empty first argument is status", run(""), 0, seen("status"), "")
outcome("arguments are not re-split", run("status", "a b", ""), 0, seen("status", "a b", ""), "")
# Mutation: help text changed, written to stderr, or exiting non-zero.
for h in ("-h", "--help", "help"):
    outcome("%s prints the help to stdout" % h, run(h), 0, HELP, "")
# Mutation: an unknown verb passed on to role.py, or exiting 1.
outcome("unknown verb", run("frob"), 2, "",
        "fabric-role: unknown command 'frob' (bind <role> | status | unbind | list)\n")
# Mutation: AGENT_FABRIC_ROOT overwritten when set.
outcome("AGENT_FABRIC_ROOT kept when set", run("status", env={"AGENT_FABRIC_ROOT": "/else"}), 0,
        seen("status", root="/else"), "")
# Mutation: the pin checked after the verb, so a bad verb, help or a refusal wins over 127.
gone = "/nonexistent/fabric-python"
for args in (("status",), ("frob",), ("help",), ("bind",)):
    outcome("missing pin: %s is 127" % args[0], run(*args, python=gone, env={"CLAUDECODE": "1"}),
            127, "", INSTALL % gone)
# Mutation: the default pin path is not /usr/local/bin/fabric-python.
if not os.access("/usr/local/bin/fabric-python", os.X_OK):
    outcome("default pin path", run("status", python=None), 127, "", INSTALL % "/usr/local/bin/fabric-python")
# Mutation: the root taken from the symlink's directory instead of the real path.
if not ENTRY.endswith(".py"):
    link = os.path.join(tmp, "fabric-role-link")
    os.symlink(ENTRY, link)
    outcome("through a symlink the root is the repository", run("list", entry=link), 0, seen("list"), "")

print("%s: %d failed" % ("FAILED" if fails else "all passed", fails))
sys.exit(1 if fails else 0)
