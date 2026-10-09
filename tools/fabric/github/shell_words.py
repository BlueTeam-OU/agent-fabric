"""tools/fabric/github/shell_words.py — reading shell text for
guards_wired: a glob as a regex, a segment's words and the command it runs
past keywords, assignments and prefixes, a line without its comment. Split
out of guards_wired.py, unchanged; the pinned limits and the rule that
unknown is never a pass are that module's header."""
from __future__ import annotations

import os
import re
import shlex

GLOB_CHARS = re.compile(r"[*?\[]")


def glob_regex(pattern: str) -> re.Pattern:
    """A shell glob as a regex over a path: * and ? never cross a /."""
    out, i = [], 0
    while i < len(pattern):
        c = pattern[i]
        if c == "*":
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "[":
            j = pattern.find("]", i + 2)
            if j < 0:
                out.append(re.escape(c))
            else:
                body = pattern[i + 1:j]
                out.append("[" + ("^" + body[1:] if body.startswith("!") else body) + "]")
                i = j
        else:
            out.append(re.escape(c))
        i += 1
    try:
        return re.compile("".join(out))
    except re.error:
        # Not a pattern bash could expand either ([z-a]): it names
        # nothing, so it wires nothing — never a traceback that reads as
        # a finding.
        return re.compile(r"(?!)")


def _globs(line: str) -> list[str]:
    return [t for t in (w.strip("'\"").rstrip(";") for w in line.split()) if GLOB_CHARS.search(t)]


def glob_matches(glob: str, rel: str) -> bool:
    """The glob, or its tail from any /, matches the whole path: as a
    literal may carry a prefix (./tools/x.sh, $ROOT/tools/x.sh), so may a
    glob, but never a different directory."""
    starts = [0] + [i + 1 for i, c in enumerate(glob) if c == "/"]
    return any(glob_regex(glob[s:]).fullmatch(rel) for s in starts)


def _literal(rel: str) -> re.Pattern:
    # Path-qualified, as ANY argument: `tools/checks/x.sh` cannot be
    # satisfied by `tools/checks/test_x.sh`, and a suite run through a
    # wrapper is still run.
    return re.compile(r"(^|\s)\S*" + re.escape(rel) + r"(\s|$)")


FOR_HEAD = re.compile(r"\bfor\s+([A-Za-z_]\w*)\s+in\s")


def _runs_bare(segment: str, ref: set[str], runner: str) -> bool:
    """The segment runs the loop's suite without the runner: `"$t"`,
    `./"$t"`, or bash/sh with $t among its arguments and no runner there.
    A command this cannot read that names $t counts as bare: unknown is
    never a pass."""
    cmd = command(segment)
    if not cmd:
        return False
    if cmd == [UNREADABLE]:
        return any(r in segment for r in ref)
    if cmd[0] in ref or (cmd[0].startswith("./") and cmd[0][2:] in ref):
        return True
    if os.path.basename(cmd[0]) in ("bash", "sh"):
        return any(a in ref for a in cmd[1:]) and not any(os.path.basename(a) == runner for a in cmd[1:])
    return False


# Words that open a compound command before the command itself.
KEYWORDS = {"then", "do", "else", "elif", "if", "while", "until", "{", "(", "!", "time"}


# Words that run the word after them as the command (by basename:
# /usr/bin/env is env); timeout's first argument is its duration.
PREFIXES = {"env", "command", "builtin", "exec", "nohup", "timeout"}


# What command() answers for a command it cannot read with certainty —
# an option to a prefix, whose argument count it does not know. It is
# never "echo" and never a path, so nothing behind it counts as run.
UNREADABLE = "\0unreadable"


def words(segment: str) -> list[str]:
    """A segment's words as the shell splits and unquotes them; a segment
    shlex cannot read (an unclosed quote) splits on whitespace."""
    try:
        return shlex.split(segment, comments=False)
    except ValueError:
        return segment.split()


def command(segment: str) -> list[str]:
    """The command a segment runs and its arguments: past its leading
    keywords, VAR=value assignments and prefixes (env, command, exec…).
    [UNREADABLE] when a prefix carries an option: what it runs then
    depends on an argument count this does not know."""
    ws, i, prefixed = words(segment), 0, False
    while i < len(ws):
        w = ws[i]
        if w in KEYWORDS or re.fullmatch(r"[A-Za-z_]\w*=.*", w, re.S):
            i += 1
        elif os.path.basename(w) in PREFIXES:
            prefixed = True
            if os.path.basename(w) == "timeout":
                # Its duration, unless an option comes first: then how
                # many words it takes is unknown, and so is the command.
                if i + 1 < len(ws) and ws[i + 1].startswith("-"):
                    return [UNREADABLE]
                i += 1
            i += 1
        elif prefixed and w.startswith("-"):
            return [UNREADABLE]
        else:
            return ws[i:]
    return []


def command_word(segment: str) -> str:
    cmd = command(segment)
    return cmd[0] if cmd else ""


def strip_comment(line: str) -> str:
    """The line without its shell comment: a # that starts a word, outside
    quotes. `true # bash tools/checks/x.sh` runs nothing of x; a # inside
    ${#arr} or a quoted string is no comment."""
    quote, escaped = "", False
    for i, c in enumerate(line):
        if escaped:
            escaped = False
        elif c == "\\" and quote != "'":
            escaped = True
        elif quote:
            if c == quote:
                quote = ""
        elif c in "'\"":
            quote = c
        elif c == "#" and (i == 0 or line[i - 1].isspace()):
            return line[:i]
    return line


DONE = re.compile(r"(^|[;\s])done([;\s]|$)")
