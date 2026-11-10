"""What a GZCoord inbox watch looks like in the process table: the one
predicate session-start.py (which says a session has none) and
watch-on-stop.py (which blocks the end of a turn without one) both ask, so
the two cannot disagree on what counts. Loaded by path from the hooks
beside it (as context-sample.py loads session-state.py); no side effects
beyond loading tools/fabric/cli/ by path, from this file's own checkout.

Which word is `gzcoord-inbox` is tools/fabric/cli canonical()'s to say
(agent-fabric ADR-068 §5 rule 7), so `fabric gzcoord inbox …` counts as
`gzcoord-inbox …` does. A command table canonical() cannot read raises
TableError out of is_watch: "unreadable" is not "no watch", and each caller
already passes on an internal error (session-start.py says nothing,
watch-on-stop.py does not block)."""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
# The command a watch runs, compared with what canonical() reads, never with a word as spelled.
WATCH_COMMAND = "gzcoord-inbox"
WATCH_FLAGS = ("--until-delivery", "--follow", "--wait")
# The Node shim some callers outside this repository still run. It is no fabric command (commands.json `replaces`
# keeps it only as gzcoord-inbox's earlier link target), so canonical() cannot name it: it is known by its file name.
NODE_SHIM = "inbox.mjs"
# canonical() needs at most `fabric <noun> <verb>` to name a command; its arguments are looked at here.
NAMING_WORDS = 3


def canonical_module():
    """tools/fabric/cli/canonical.py, its package loaded BY PATH as fabric_cli (as tools/fabric/cli/fabric.py loads
    it), so nothing on sys.path answers for the import."""
    if "fabric_cli" not in sys.modules:
        here = os.path.join(ROOT, "tools", "fabric", "cli")
        spec = importlib.util.spec_from_file_location("fabric_cli", os.path.join(here, "__init__.py"),
                                                      submodule_search_locations=[here])
        if spec is None or spec.loader is None:
            raise ImportError(f"no package at {here}")
        package = importlib.util.module_from_spec(spec)
        sys.modules["fabric_cli"] = package
        try:
            spec.loader.exec_module(package)
        except BaseException:
            del sys.modules["fabric_cli"]
            raise
    return importlib.import_module("fabric_cli.canonical")


def is_watch(cmd: str) -> bool:
    """A `gzcoord-inbox` run (in either spelling, or the Node shim `inbox.mjs`)
    with --until-delivery, --follow (a session not yet moved off it) or --wait
    after it. `cmd` is a process's command line, its arguments joined by
    spaces: an interpreter (`fabric-python -I`, `node`) may stand before the
    command, so every word is asked whether it starts one. Missing either name
    told an armed session to arm a second consumer (review of #42)."""
    if not any(flag in cmd for flag in WATCH_FLAGS):
        return False
    canonical = canonical_module()
    words = cmd.split()
    for k, word in enumerate(words):
        read = canonical.canonical(words[k:k + NAMING_WORDS])
        if (read is not None and read[0] == WATCH_COMMAND) or os.path.basename(word) == NODE_SHIM:
            if any(flag in w for w in words[k + 1:] for flag in WATCH_FLAGS):
                return True
    return False
