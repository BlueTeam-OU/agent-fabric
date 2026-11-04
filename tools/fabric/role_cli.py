#!/usr/bin/env python3
"""tools/fabric/role_cli.py — the whole dispatch of bin/fabric-role, which is
a forwarder to this module (ADR-040 §5 rule 1, Wave 9 batch 2). Standard
library only; it runs no logic of role.py's, it execs it.

CONTRACT, frozen from the bash (tests/test_fabric_role_cli.py is the oracle):
  argv      [bind <role> [--project ID] [--workspace DIR] [--force]
            | status | unbind | list | -h | --help | help]; no argument,
            or an empty first one, is `status`.
  env       AGENT_FABRIC_PYTHON (default /usr/local/bin/fabric-python), the
            interpreter role.py runs on; AGENT_FABRIC_ROOT, exported to this
            repository's root when unset or empty; CLAUDECODE,
            CLAUDE_ENV_FILE, AGENT_FABRIC_LAUNCH_PROFILE, any one non-empty
            of which refuses bind and unbind.
  stdout    USAGE for -h, --help and help; nothing else of its own.
  stderr    the pin's install line; the refusal; the unknown-command line.
  exit      the pin is checked first, before the verb: absent, 127. bind and
            unbind inside a harness session: 1. An unknown verb: 2. Else
            role.py's own, which it is exec'd as: bind is its `activate`,
            unbind its `deactivate`, status and list their own names,
            the rest of the argv passed through.
"""
from __future__ import annotations

import os
import sys

USAGE = """\
bin/fabric-role — bind a role to this agent, from a login shell, before
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
PINNED = "/usr/local/bin/fabric-python"
# The harness's own markers: a session carries one of them, a login shell none.
SESSION_VARS = ("CLAUDECODE", "CLAUDE_ENV_FILE", "AGENT_FABRIC_LAUNCH_PROFILE")
# What role.py is called with for each verb; bind and unbind keep their
# Python names there (activate, deactivate).
VERBS = {"bind": "activate", "unbind": "deactivate", "status": "status", "list": "list"}
GUARDED = ("bind", "unbind")


def say(stream, text: str) -> None:
    stream.flush()
    stream.buffer.write(text.encode("utf-8"))
    stream.buffer.flush()


def main(argv: list[str]) -> int:
    here = os.path.dirname(os.path.realpath(__file__))
    root = os.path.dirname(os.path.dirname(here))
    if not os.environ.get("AGENT_FABRIC_ROOT"):
        os.environ["AGENT_FABRIC_ROOT"] = root
    py = os.environ.get("AGENT_FABRIC_PYTHON") or PINNED
    # Before the verb, so a host without the pin says so whatever it was asked.
    if not os.access(py, os.X_OK):
        say(sys.stderr, "fabric-role: the fleet's pinned Python is not installed at %s; as root: "
            "/usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install\n" % py)
        return 127
    cmd = argv[0] if argv and argv[0] else "status"
    rest = argv[1:]
    if cmd in VERBS:
        if cmd in GUARDED:
            for var in SESSION_VARS:
                if os.environ.get(var):
                    say(sys.stderr, "fabric-role: this is a harness session ($%s is set). A role is bound from a\n"
                        "  login shell, never inside a session: the session's prompt already carries the\n"
                        "  role it was launched with. Open a terminal, run fabric-role there, then relaunch.\n" % var)
                    return 1
        target = os.path.join(root, "tools", "fabric", "role.py")
        try:
            os.execv(py, [py, target, VERBS[cmd], *rest])
        except OSError as e:
            say(sys.stderr, "fabric-role: cannot run %s: %s\n" % (py, e.strerror))
            return 126
    if cmd in ("-h", "--help", "help"):
        say(sys.stdout, USAGE)
        return 0
    say(sys.stderr, "fabric-role: unknown command '%s' (bind <role> | status | unbind | list)\n" % cmd)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
