#!/usr/bin/env python3
"""tools/fabric/cli/fabric.py — the command `bin/fabric` forwards to: `fabric <noun> [<verb>] [args…]` runs the command
the `fabric` table of runtime/claude-code/commands.json names, as that command's own process (agent-fabric ADR-068).

The contract is in table.py (resolution, listings, what is refused). This module adds the process:

- the target is the path `commands` gives for the command, under THIS checkout (the one this file is in), never a PATH
  lookup, and it replaces this process (os.execv), argv[0] that path, the arguments after the resolved words unchanged:
  the pid, the inherited environment and ignored signals, and the process a guard or a watch looks for are the direct
  call's. A child process would change all of them.
- exit 2: a refusal (table.py); 127: the target is not in the checkout; 126: it is there and cannot be executed;
  70: commands.json or its `fabric` table is unreadable or malformed. 70 is not a caller's mistake and is kept apart.
"""
from __future__ import annotations

import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.realpath(__file__))
if "fabric_cli" not in sys.modules:   # by path, as jobs.py loads its parts: nothing on sys.path answers for the import
    _spec = importlib.util.spec_from_file_location("fabric_cli", os.path.join(_HERE, "__init__.py"),
                                                   submodule_search_locations=[_HERE])
    sys.modules["fabric_cli"] = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(sys.modules["fabric_cli"])
from fabric_cli import table  # noqa: E402

EX_SOFTWARE = 70
NOT_FOUND = 127
NOT_EXECUTABLE = 126


def main(argv: list[str], root: str = table.ROOT, execv=os.execv) -> int:
    try:
        doc = table.load(root)
        nouns = table.nouns_of(doc)
        commands = table.commands_of(doc)
        outcome = table.resolve(nouns, argv)
        if isinstance(outcome, table.Run) and outcome.command not in commands:
            raise table.TableError(f"the table names {outcome.command!r}, which `commands` does not")
    except table.TableError as exc:
        print(f"fabric: {exc}", file=sys.stderr)
        return EX_SOFTWARE
    if isinstance(outcome, table.Say):
        print(outcome.text, end="", file=sys.stdout if outcome.stream == "out" else sys.stderr)
        return outcome.status
    target = os.path.join(root, commands[outcome.command])
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        execv(target, [target, *outcome.args])
    except FileNotFoundError:
        print(f"fabric: {outcome.command}: {target} is not in this checkout", file=sys.stderr)
        return NOT_FOUND
    except OSError as exc:
        print(f"fabric: {outcome.command}: cannot execute {target} ({exc.strerror or exc.__class__.__name__})", file=sys.stderr)
        return NOT_EXECUTABLE
    return 0   # execv returned: only a test's stand-in does


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
