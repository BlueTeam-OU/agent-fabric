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
from collections.abc import Sequence

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


def is_watch(cmd: str | Sequence[str]) -> bool:
    """A `gzcoord-inbox` run (in either spelling, or the Node shim `inbox.mjs`)
    with --until-delivery, --follow (a session not yet moved off it) or --wait
    after it. `cmd` is a process's argv, one string per argument: an argument
    that holds a space (`grep -r "gzcoord-inbox --follow" .`) must stay one word,
    or it reads as a watch. A plain string is split on spaces, for a caller that
    only has a printed command line. An interpreter (`fabric-python -I`, `node`)
    may stand before the command, so every word is asked whether it starts one.
    Missing either name told an armed session to arm a second consumer (review of #42)."""
    words = cmd.split() if isinstance(cmd, str) else list(cmd)
    if not any(flag in w for w in words for flag in WATCH_FLAGS):
        return False
    canonical = canonical_module()
    for k, word in enumerate(words):
        # By its file name: canonical() reads a path only in a `bin` directory, which a guard may over-report on, but
        # a watch linked from anywhere else (a test's scratch links) unseen here would tell an armed session to arm a
        # second consumer.
        read = canonical.canonical([os.path.basename(word), *words[k + 1:k + NAMING_WORDS]])
        if (read is not None and read[0] == WATCH_COMMAND) or os.path.basename(word) == NODE_SHIM:
            if any(flag in w for w in words[k + 1:] for flag in WATCH_FLAGS):
                return True
    return False


# The modes that move no cursor: --replay, --history and --held read the journal or the relay without a consumer id. A
# drain, --wait and both watches mark what they print delivered (tools/fabric/gzcoord/inbox.py CONTRACT).
NON_CONSUMING = ("--replay", "--history", "--held")
# Words that run the word after them (and their own options) as the command, which canonical() does not skip.
LAUNCHERS = ("timeout", "nice", "nohup", "stdbuf", "time")


def is_consumer(words: Sequence[str]) -> bool:
    """A `gzcoord-inbox` run (in either spelling) that moves the inbox's cursor past what it prints: any mode but
    NON_CONSUMING. `words` is one command's words from its first (one pipe stage), as a shell splits them. The
    pipe-status guard asks it: a filter after a consumer hides messages that will not come again (python-dev-01,
    2026-11-24). Raises TableError as is_watch does."""
    words = list(words)
    i = 0
    while i < len(words) and os.path.basename(words[i]) in LAUNCHERS:
        i += 1
        while i < len(words) and (words[i].startswith("-") or words[i][:1].isdigit()):
            i += 1
    read = canonical_module().canonical(words[i:])
    if read is None or read[0] != WATCH_COMMAND:
        return False
    return not any(arg.split("=", 1)[0] in NON_CONSUMING for arg in read[1])
