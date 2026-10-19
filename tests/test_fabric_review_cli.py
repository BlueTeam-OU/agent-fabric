#!/usr/bin/env python3
"""bin/fabric-review: the contract of its dispatch, frozen from the bash
(ADR-040 §5 rule 3) and held across the port (rule 5).

The entry runs as a subprocess; FABRIC_REVIEW_ENTRY names another one (a path
ending .py runs under this interpreter), default bin/fabric-review. The
interpreter the entry execs is a fake (AGENT_FABRIC_PYTHON) that prints its
argv and runs nothing real, except that it lets the dispatcher module itself
(review_cli.py) through, so the oracle is the same against the bash, the
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
ENTRY = os.environ.get("FABRIC_REVIEW_ENTRY") or os.path.join(ROOT, "bin", "fabric-review")
INSTALL = ("fabric-review: the fleet's pinned Python is not installed at %s; as root: "
           "/usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install\n")
FAKE = """#!{python}
import os, sys
if os.path.basename(sys.argv[1]) == "review_cli.py":
    os.execv(sys.executable, [sys.executable] + sys.argv[1:])
print("ARGV", os.path.basename(sys.argv[1]), *sys.argv[2:])
print("ROOT", os.environ.get("AGENT_FABRIC_ROOT"))
"""
HELP = """bin/fabric-review — brief a blind review: render the facts of one change
into the prompt a code-review dispatch carries.

  fabric-review brief  REQUEST[.yaml|.json|-] [--allow-rationale]   the brief, to stdout; a pinned range
                                      also checks its head out, detached (ADR-020)
  fabric-review check  REQUEST                                        validate only, say what it is
  fabric-review lenses                                                 the lens vocabulary
  fabric-review save PR ROUND [--repo NAME] < report                  keep a round's report; remove its head worktree
  fabric-review next REQUEST (--report F | --pr PR) [--head REV] [--keep-lenses]
                                      the re-review's request, derived and rendered
                                      (tools/fabric/review_rounds.py)
  fabric-review --engine codex PR REQUEST [--gateway chatgpt] [--model M] [--timeout MIN] [--no-post]
                                      the second engine: Codex reviews the PR's head
                                      one-shot and posts, through a gateway of its own
                                      (tools/fabric/review_codex.py, agent-fabric ADR-053)

Then dispatch, exactly as the guard requires (it never reads the prompt):

  Agent(subagent_type: "code-review", model: "fable",
        description: "Review <what>" (or "Re-review <what>"),
        prompt: <the rendered brief, verbatim>)      — and NO isolation

A request names WHAT must be true (mode, repository, range, objective,
requirements, invariants, compatibility, threat model, scope, out of
scope, lenses; previous_findings on a re-review) and never how the
change makes it true: a verdict-shaped sentence refuses the render,
named. tools/fabric/review_brief.py; runtime/claude-code/review/README.md.
"""
fails = 0
tmp = tempfile.mkdtemp(prefix="fabric-review-cli-")
# The runner fails a suite whose scratch outlives it; removed however the run ends.
atexit.register(shutil.rmtree, tmp, ignore_errors=True)
fake = os.path.join(tmp, "fake-python")
with open(fake, "w") as f:
    f.write(FAKE.format(python=sys.executable))
os.chmod(fake, 0o755)


def run(*args: str, env: dict | None = None, python: str | None = fake, entry: str | None = None):
    e = {k: v for k, v in os.environ.items() if k not in ("AGENT_FABRIC_ROOT", "AGENT_FABRIC_PYTHON")}
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


def seen(module: str, *rest: str, root: str = ROOT) -> str:
    return "ARGV %s\nROOT %s\n" % (" ".join((module, *rest)), root)


# Mutation: brief not prefixed with render, or its arguments dropped or reordered.
outcome("brief renders", run("brief", "req.yaml", "--allow-rationale"), 0,
        seen("review_brief.py", "render", "req.yaml", "--allow-rationale"), "")
outcome("brief alone", run("brief"), 0, seen("review_brief.py", "render"), "")
# Mutation: the verb dropped (check/lenses) or shifted away like brief's.
outcome("check keeps its verb", run("check", "req.json"), 0, seen("review_brief.py", "check", "req.json"), "")
outcome("lenses keeps its verb", run("lenses"), 0, seen("review_brief.py", "lenses"), "")
# Mutation: save/next sent to review_brief.py, or their verb dropped.
outcome("save to rounds", run("save", "12", "3", "--repo", "r"), 0,
        seen("review_rounds.py", "save", "12", "3", "--repo", "r"), "")
outcome("next to rounds", run("next", "req", "--pr", "7", "--keep-lenses"), 0,
        seen("review_rounds.py", "next", "req", "--pr", "7", "--keep-lenses"), "")
# Mutation: --engine kept in the argv, or sent to another module.
outcome("--engine drops itself", run("--engine", "codex", "5", "req", "--no-post"), 0,
        seen("review_codex.py", "codex", "5", "req", "--no-post"), "")
outcome("--engine alone", run("--engine"), 0, seen("review_codex.py"), "")
# Mutation: arguments re-split or an empty one dropped.
outcome("arguments are not re-split", run("check", "a b", ""), 0, seen("review_brief.py", "check", "a b", ""), "")
# Mutation: help to stderr, truncated or cut at another line, or exiting non-zero.
for h in ("-h", "--help"):
    outcome("%s prints the help to stdout" % h, run(h), 0, HELP, "")
# Mutation: no argument treated as -h (stdout, exit 0).
outcome("no argument: help to stderr, exit 2", run(), 2, "", HELP)
outcome("empty argument: help to stderr, exit 2", run(""), 2, "", HELP)
# Mutation: an unknown verb passed on, quoted differently, or exiting 1.
outcome("unknown verb", run("frob", "x"), 2, "",
        "fabric-review: unknown command frob (brief | check | lenses | save | next | --engine)\n")
# Mutation: "help" accepted (the bash takes only -h and --help).
outcome("help is not a verb", run("help"), 2, "",
        "fabric-review: unknown command help (brief | check | lenses | save | next | --engine)\n")
# Mutation: AGENT_FABRIC_ROOT overwritten when set.
outcome("AGENT_FABRIC_ROOT kept when set", run("lenses", env={"AGENT_FABRIC_ROOT": "/else"}), 0,
        seen("review_brief.py", "lenses", root="/else"), "")
# Mutation: the pin checked after the verb, so help or a bad verb wins over 127.
gone = "/nonexistent/fabric-python"
for args in (("lenses",), ("frob",), ("-h",), ()):
    outcome("missing pin: %s is 127" % (args[0] if args else "no argument"), run(*args, python=gone),
            127, "", INSTALL % gone)
# Mutation: the default pin path is not /usr/local/bin/fabric-python.
if not os.access("/usr/local/bin/fabric-python", os.X_OK):
    outcome("default pin path", run("lenses", python=None), 127, "", INSTALL % "/usr/local/bin/fabric-python")
# Mutation: the root taken from the symlink's directory instead of the real path;
# help read from the link's own file.
if not ENTRY.endswith(".py"):
    link = os.path.join(tmp, "fabric-review-link")
    os.symlink(ENTRY, link)
    outcome("through a symlink the root is the repository", run("lenses", entry=link), 0,
            seen("review_brief.py", "lenses"), "")
    outcome("through a symlink the help is whole", run("-h", entry=link), 0, HELP, "")

print("%s: %d failed" % ("FAILED" if fails else "all passed", fails))
sys.exit(1 if fails else 0)
