"""tools/fabric/cli/canonical.py — one reading of "which fabric command does this Bash segment run" (agent-fabric
ADR-068 §5 rule 7). A hook or guard that recognises a command by name asks canonical(), never keeps a pattern for the
name: the `fabric` spelling exists only because every guard reads it as the old one.

canonical(words) -> (command, args) or None. `words` are one simple command's shell words, already split and unquoted
(the caller's tokenizer and segmenter; this reads no shell syntax). Pure: no filesystem, no PATH, no environment.

Read, in order:
- leading NAME=value words;
- `env` with its options (`-i`, `-`, `-0`, `-u NAME`, `-uNAME`, `--unset=NAME`, `-C DIR`, `--chdir=DIR`, `--`) and
  NAME=value words, and `command` / `command -p` / `command --`: they run the next word. `env -S`, any other option,
  and `command -v` / `-V` (which run nothing) make the segment None, as does a prefix with no command after it;
- the command word: a bare name, or a path whose directory is named `bin` (`bin/x`, `./bin/x`, `~/.local/bin/x`,
  `/abs/checkout/bin/x`), the name being a key of `commands` or `fabric`. The checkout is not checked, so a path into
  another tree reads as the command: a guard over-reports, which is the side it fails on;
- `fabric <noun> [<verb>] …` through the table (table.resolve), a refused form being None because it runs nothing.

None is for everything else, including a word with an expansion (`$X`, a backquote, a glob): it names no command we can
read, and the caller decides what an unreadable segment means."""
from __future__ import annotations

import os
import re

from . import table

ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
UNREADABLE = re.compile(r"[$`*?\[\]{}\\]")
ENV_FLAGS = frozenset({"-i", "-", "-0", "--ignore-environment", "--null"})
ENV_VALUED = frozenset({"-u", "-C"})
ENV_FUSED = ("-u", "--unset=", "-C", "--chdir=")
ENV_LONG_VALUED = frozenset({"--unset", "--chdir"})
DISPATCHER = "fabric"

_cache: dict[str, tuple[dict[str, str], dict[str, dict]]] = {}


def _tables(doc: dict | None, root: str) -> tuple[dict[str, str], dict[str, dict]]:
    if doc is not None:
        return table.commands_of(doc), (table.nouns_of(doc) if "fabric" in doc else {})
    if root not in _cache:
        loaded = table.load(root)
        _cache[root] = (table.commands_of(loaded), table.nouns_of(loaded) if "fabric" in loaded else {})
    return _cache[root]


def _after_prefix(words: list[str]) -> int | None:
    """Index of the command word, or None when the prefix runs something else or nothing."""
    i, n = 0, len(words)
    while i < n:
        w = words[i]
        if ASSIGNMENT.match(w):
            i += 1
        elif w == "env":
            i += 1
            while i < n:
                o = words[i]
                if o == "--":
                    i += 1
                    break
                if ASSIGNMENT.match(o) or o in ENV_FLAGS:
                    i += 1
                elif o in ENV_VALUED or o in ENV_LONG_VALUED:
                    i += 2
                elif o.startswith(ENV_FUSED):
                    i += 1
                elif o.startswith("-"):
                    return None
                else:
                    break
        elif w == "command":
            i += 1
            if i < n and words[i] == "--":
                i += 1
            elif i < n and words[i] == "-p":
                i += 1
            elif i < n and words[i].startswith("-"):
                return None
        else:
            return i
    return None


def _name_of(word: str) -> str | None:
    if not word or UNREADABLE.search(word.removeprefix("~")):
        return None
    head, name = os.path.split(word)
    if not head:
        return name
    return name if os.path.basename(head) == "bin" else None


def canonical(words: list[str], doc: dict | None = None, root: str = table.ROOT) -> tuple[str, list[str]] | None:
    """`doc` is a parsed commands.json (tests, lint); None reads the checkout's. A commands.json that cannot be read
    raises table.TableError: a hook must not take "unreadable" for "no fabric command here"."""
    commands, nouns = _tables(doc, root)
    at = _after_prefix(words)
    if at is None:
        return None
    name = _name_of(words[at])
    rest = words[at + 1:]
    if name == DISPATCHER and nouns:
        outcome = table.resolve(nouns, rest)
        if isinstance(outcome, table.Run) and outcome.command in commands:
            return outcome.command, list(outcome.args)
        return None
    if name in commands and name != DISPATCHER:
        return name, list(rest)
    return None
