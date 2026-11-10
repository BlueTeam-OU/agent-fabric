"""tools/fabric/cli/table.py — the `fabric` table of runtime/claude-code/commands.json and the resolution of a word line
through it (ADR-068 §5 rules 2 and 5).

Contract (the dispatcher and canonical() both stand on it):

- `nouns` maps a noun to `{"command": C}`, `{"verbs": {V: C}}` or both. A word after the noun is a table verb only if the
  noun lists it; otherwise it and everything after it go to the noun's own command, whose verbs stay in its module. A noun
  without its own command refuses an unlisted verb.
- Before the noun only `help` and `--help` are accepted, alone; any other option is refused, so a permission rule's prefix
  always starts at the noun. Nothing is guessed: a word that is no noun is refused, never matched by prefix.
- `help` and `--help` (and `<noun> help` / `<noun> --help` for a noun without its own command) say the forms on stdout,
  status 0. Bare `fabric`, a bare noun without its own command, an unknown noun or verb and a refused option say them on
  stderr, status 2.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

COMMANDS_FILE = os.path.join("runtime", "claude-code", "commands.json")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
USAGE = 2
HELP_WORDS = ("help", "--help")


class TableError(Exception):
    """commands.json is unreadable or its `fabric` section is not the shape this module reads: a fault of the checkout,
    not of the caller's words, so the dispatcher says it apart from a refusal."""


@dataclass(frozen=True)
class Run:
    command: str
    args: tuple[str, ...]


@dataclass(frozen=True)
class Say:
    text: str
    status: int

    @property
    def stream(self) -> str:
        return "out" if self.status == 0 else "err"


def load(root: str = ROOT) -> dict:
    path = os.path.join(root, COMMANDS_FILE)
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise TableError(f"{path}: cannot be read as JSON ({exc.__class__.__name__})") from exc
    if not isinstance(doc, dict):
        raise TableError(f"{path}: not a JSON object")
    return doc


def commands_of(doc: dict) -> dict[str, str]:
    """{command: path relative to the checkout}, every entry a string pair."""
    commands = doc.get("commands")
    if not isinstance(commands, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in commands.items()):
        raise TableError("commands.json: `commands` is not a map of command to path")
    return commands


def nouns_of(doc: dict) -> dict[str, dict]:
    """The validated noun map: each noun {"command": str?, "verbs": {str: str}?}, at least one of the two."""
    section = doc.get("fabric")
    nouns = section.get("nouns") if isinstance(section, dict) else None
    if not isinstance(nouns, dict):
        raise TableError("commands.json: no `fabric` table (`fabric.nouns`)")
    for noun, entry in nouns.items():
        verbs = entry.get("verbs", {}) if isinstance(entry, dict) else None
        ok = (isinstance(entry, dict) and set(entry) <= {"command", "verbs"} and ("command" in entry or entry.get("verbs"))
              and isinstance(entry.get("command", ""), str)
              and isinstance(verbs, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in verbs.items()))
        if not ok:
            raise TableError(f"commands.json: `fabric.nouns.{noun}` is not {{command?, verbs?}} with a string command and verbs")
    return nouns


def forms(nouns: dict[str, dict]) -> list[tuple[str, str]]:
    """[(form, command)] in noun order, a noun's own command first."""
    out: list[tuple[str, str]] = []
    for noun in sorted(nouns):
        entry = nouns[noun]
        if "command" in entry:
            out.append((f"fabric {noun} [args…]", entry["command"]))
        out += [(f"fabric {noun} {verb} [args…]", cmd) for verb, cmd in sorted(entry.get("verbs", {}).items())]
    return out


def listing(nouns: dict[str, dict], only: str | None = None) -> str:
    rows = forms({only: nouns[only]} if only else nouns)
    width = max((len(f) for f, _ in rows), default=0)
    head = "fabric <noun> [<verb>] [args…] — runs the command each form names:\n"
    return head + "".join(f"  {f.ljust(width)}  {c}\n" for f, c in rows)


def _refuse(why: str, nouns: dict[str, dict], only: str | None = None) -> Say:
    return Say(f"fabric: {why}\n{listing(nouns, only)}", USAGE)


def resolve(nouns: dict[str, dict], args: list[str]) -> Run | Say:
    if not args:
        return _refuse("no noun given", nouns)
    first = args[0]
    if first in HELP_WORDS:
        return Say(listing(nouns), 0) if len(args) == 1 else _refuse(f"`{first}` takes no argument", nouns)
    if first.startswith("-"):
        return _refuse(f"{first!r} is not accepted before the noun", nouns)
    entry = nouns.get(first)
    if entry is None:
        return _refuse(f"unknown noun {first!r}", nouns)
    rest = args[1:]
    verbs = entry.get("verbs", {})
    if rest and rest[0] in verbs:
        return Run(verbs[rest[0]], tuple(rest[1:]))
    if "command" in entry:
        return Run(entry["command"], tuple(rest))
    if not rest:
        return _refuse(f"`fabric {first}` needs a verb", nouns, first)
    if rest[0] in HELP_WORDS and len(rest) == 1:
        return Say(listing(nouns, first), 0)
    return _refuse(f"unknown verb {rest[0]!r} for {first!r}", nouns, first)
