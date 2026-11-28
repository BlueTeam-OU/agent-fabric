#!/usr/bin/env python3
"""runtime/claude-code/hooks/inbox-pipe-guard.py: a PreToolUse hook on Bash.

Refuses a command that pipes the output of a CONSUMING gzcoord-inbox run into anything, and names the way out.

WHY. On 2026-11-24 a session ran the bare drain piped into `head`/`tail`: it consumed three messages and the filter hid
two of them. Reproduced on 2026-11-27 with the real show_page in tools/fabric/gzcoord/inbox.py: the page is
printed, the shown ledger finished and the relay acknowledged BEFORE Python flushes stdout, so `| head -n 3` loses
the rest of the page whatever its size; the BrokenPipe surfaces only at interpreter exit, after the messages are
gone. A trailer line printed last would not survive `head` or `grep` either, so the fence is here, before the run.

THE RULE. A consuming run's stdout goes to the session or to a file, never through a pipe or into another command.
  - Consuming: every gzcoord-inbox run without --replay, --history or --held among its words: the drain (no flag),
    --wait, --until-delivery, --follow, and --help/-h too, which inbox.py does not read, so they drain. The three are
    matched as whole words, as inbox.py tests `"--replay" in argv`: `--replay=ID` drains.
  - Refused: `|` or `|&` after the run in its pipeline (`2>&1 |` included), and `tee` with it: a pipe of any kind
    keeps the rule one sentence, and a tee that is killed or filtered loses the same page. A run inside `$( … )`,
    backticks or `<( … )`/`>( … )` is refused too: the page goes into another command, not the session.
  - Allowed: the run bare, `> file`, `>> file`, `&> file` (the page is whole and can be read whole), and every run of
    the three read-only modes, piped or not. Stdout to /dev/null is allowed: it is outside the loss this guard was
    asked to fence (the page is discarded whole, not cut), and refusing it is the coordinator's call.

WHICH WORDS ARE gzcoord-inbox. tools/fabric/cli canonical()'s to say (agent-fabric ADR-068 §5 rule 7), loaded through
inbox-watch.py's loader, so `fabric gzcoord inbox …` is caught as `gzcoord-inbox …` is; a word is asked by its file
name, as inbox-watch.py and self-kill-guard.py ask, so an absolute path to the link is one too. The module's own path
(`…/gzcoord/inbox.py`) and the Node shim are known by name. A command table canonical() cannot read leaves the
spelled names (self-kill-guard.py's fallback): "unreadable" is not "no drain".

WHAT IS READ. Text the shell never runs is dropped first by post-review-shape-guard.py's live_text(): comments,
single-quoted strings, quoted-delimiter heredoc bodies, given back when a shell, eval or ssh may run them. So
`pgrep -f 'gzcoord-inbox --follow' | xargs kill` is no run, and `bash -c 'gzcoord-inbox | head'` is one. A word in
argument position under a command that only reads or prints its arguments (READERS: `grep -rn gzcoord-inbox . |
head`, `echo gzcoord-inbox | cat`) is a mention, not a run; under anything else (a wrapper, an interpreter, a
program not listed) every word is asked, so `timeout 60 gzcoord-inbox --wait 5 | head` and `python3 -I
bin/gzcoord-inbox | head` are runs. A double-quoted word is one word: `git commit -m "gzcoord-inbox | head"` holds no
pipe.

FLAT, AND CLOSED WHERE IT IS NOT. The command is judged as pipelines of simple commands, split on `;`, `&&`, `||`,
`&` and newlines. A `$( … )` or backtick span in which the loose scan below finds no consuming run is blanked to a
word first, so naming an inbox file is no capture (`f=$(mktemp -t inbox.XXXXXX); gzcoord-inbox > "$f"` passes), and
a `$(( … ))` is arithmetic, blanked once neither a substitution nor a consuming run is left inside it (`n=$((n+1))`);
a process substitution never is. Groups, compound commands, the substitutions left and runners are not followed:
when the command holds any of them (`(`, `{`, `}`, `fi`, `done`, `esac`, `$(`, a backtick, `<(`, `>(`, a word of
post-review-shape-guard's RUNNERS, `.`) and a consuming run found by a loose scan of every word (mention or run alike,
readers not exempt), it is refused if it also holds a `|` anywhere or a substitution. Runners are in the list because
live_text gives their quoted payload back at the end of the text, not where it stood, and a double-quoted `bash -c
"…"` payload is one word to the lexer. A nesting-aware reading of bash lost review rounds in both directions for the
two sibling guards that tried (their headers say so); a false deny costs a rephrase (`gzcoord-inbox; ( cd x && git
log | head )` is one), a false allow costs messages.

SCOPE. A fence against the habit of filtering the drain, not a sandbox. Not seen: a command word the shell builds
(`$c | head`, `'gzcoord-inbox' | head`, whose quotes live_text drops as inert text), a script or alias that drains, a
link to the command under another name. Each costs messages only when written on purpose.

COST. Nothing is loaded unless `inbox` occurs in the command (the hook runs on every Bash call); canonical() is asked
only where `inbox` stands in the words it reads, and with those NAMING_WORDS words only, never the rest of the command;
whether a run is read-only is one index per simple command. So every reading is linear in the words: a long run of
words that mostly hold `inbox` once took longer than the hook's 5 s timeout, which counts as no objection (#721 F1).

SUBAGENTS. Judged as the session is: a subagent's Bash call drains the same login's inbox, and a page it filters is
lost to the session the same way.

FAILURE. A payload that is not JSON, or no string command, is passed: exit 0, nothing printed, as every sibling. Any
other failure to decide exits non-zero with nothing on stdout, which hook_entry.py and the settings fallback both
turn into an ask (their cannot_run / fallback line).

Output: one deny decision on stdout, or nothing.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import sys

sys.dont_write_bytecode = True   # the siblings it loads by path leave no __pycache__ in the tree
HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
INBOX = "gzcoord-inbox"
INBOX_SPOKEN = ("fabric", "gzcoord", "inbox")
# canonical() needs at most `fabric <noun> <verb>` to name a command.
NAMING_WORDS = 3
# inbox.py reads these three as whole argv words, and each of them neither drains nor acknowledges.
READ_ONLY = {"--replay", "--history", "--held"}
MODULE_SUFFIX = "/gzcoord/inbox.py"
# Programs that only read or print their arguments: under one of these, a word that names the drain is a mention.
# Owned here, not post-review-shape-guard's PLAIN, which holds python, find and make: each runs a script or a command,
# which here is a run. sed and awk are kept although each can run a command (`e`, system()): reading the module or the
# link with them (`sed -n 1,40p tools/fabric/gzcoord/inbox.py | head`) is far more common than a drain run that way.
# A name missing from it costs one false deny beside a pipe, and the reason says how to quote a mention.
READERS = {"echo", "printf", "grep", "egrep", "fgrep", "rg", "ag", "ack", "git", "gh", "cat", "less", "more", "head",
           "tail", "wc", "ls", "stat", "file", "diff", "type", "which", "man", "jq", "gzcoord-send", "gzcoord-compose",
           "fabric-adr", "sed", "awk", "nl", "readlink", "realpath", "basename", "dirname", "sort", "uniq", "cut", "tr",
           "od", "xxd", "sha256sum", "md5sum"}
# A word that makes live_text give quoted text back (post-review-shape-guard's RUNNERS, read from it so the two
# cannot drift) and `.`, which it gives back as a command word.
DOT = "."
# Before the command word, and not it.
LEADING = {"!", "then", "do", "else", "elif", "if", "while", "until", "time"}
ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\+?=")
SEPARATORS = {";", ";;", "&", "&&", "||", "\n"}
PIPES = {"|", "|&"}
# The operators the lexer may glue into one punctuation token, longest first (self-kill-guard.py's OPERATOR).
OPERATOR = re.compile(r"&>>|<<<|<<-?|>>|\|&|&&|\|\||;;|&>|>&|<&|<>|>\||[|;&\n()<>]")
GROUP_WORDS = {"{", "}", "fi", "done", "esac"}
SUBSTITUTION = re.compile(r"\$\(|`|<\(|>\(")
# A loose word, for the closed reading: what ends it is an operator, a quote or an expansion mark.
LOOSE_WORD = re.compile(r"[^\s;&|()<>`\"'$\\{}]+")
LOOSE_CHUNK = re.compile(r"[;&|()<>`\n{}]")
REASON = ("A consuming gzcoord-inbox run acknowledges its whole page before a pipe or a capture reads it, so what the "
          "filter drops is lost: run the drain bare so its whole page reaches the session, or redirect it to a file in "
          "your scratchpad and read the whole file. A message already consumed is read again with "
          "`gzcoord-inbox --replay <MESSAGE-ID>`, never through a filter; a command that only mentions the name puts it "
          "in single quotes.")
# An innermost $( … ) or backtick span, blanked to PLACEHOLDER when no consuming run is found inside it: `f=$(mktemp
# -t inbox.XXXXXX); gzcoord-inbox > "$f"` is the way out the reason names, and `cd "$(git rev-parse --show-toplevel)"`
# beside the watch is no capture. Never a <( … ) or >( … ): `gzcoord-inbox > >(head)` is a pipe by another name.
INNER_SUBST = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")
# A $(( … )) span, one level of plain parentheses inside: arithmetic, which runs no command, so it is blanked unless a
# substitution kept by INNER_SUBST still stands in it, or the loose scan finds a consuming run in it (bash reads
# `$((gzcoord-inbox | head))` as arithmetic, but a shell that did not would drain; keeping it costs a rephrase).
# INNER_SUBST's `[^()]*` never matches it, and left whole its `$(` read as a capture.
ARITHMETIC = re.compile(r"\$\(\((?:[^()]|\([^()]*\))*\)\)")
PLACEHOLDER = "_inbox_pipe_guard_subst_"


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HOOKS_DIR, file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_LOADED: dict = {}


def _sibling(key: str):
    """post-review-shape-guard.py (live_text) and inbox-watch.py (canonical_module), each loaded once, by path."""
    if key not in _LOADED:
        _LOADED[key] = _load("fabric_inbox_pipe_" + key.replace("-", "_"), key + ".py")
    return _LOADED[key]


def _canonical():
    if "canonical" not in _LOADED:
        _LOADED["canonical"] = _sibling("inbox-watch").canonical_module()
    return _LOADED["canonical"]


def inbox_run(words: list[str], k: int) -> int | None:
    """Where the arguments of the gzcoord-inbox run that starts at words[k] begin, or None when none starts there."""
    # canonical() is asked with the naming window only, as inbox-watch.py asks it, and only where that window holds
    # the word: a copy of the rest at every word of a long command is quadratic, and a hook past its timeout is read
    # as no objection. The arguments it gives back are the window's tail, so the run's own begin where they begin.
    window = words[k:k + NAMING_WORDS]
    if not any("inbox" in w for w in window):
        return None
    word = words[k]
    if word.endswith(MODULE_SUFFIX) or os.path.basename(word) == _sibling("inbox-watch").NODE_SHIM:
        return k + 1
    named = [os.path.basename(word), *window[1:]]
    try:
        read = _canonical().canonical(named)
    except Exception:  # noqa: BLE001 - TableError or a module that cannot load: the spelled names, never "no drain"
        if named[0] == INBOX:
            return k + 1
        return k + NAMING_WORDS if tuple(named) == INBOX_SPOKEN else None
    return k + len(window) - len(read[1]) if read is not None and read[0] == INBOX else None


def consuming(words: list[str], every_word: bool) -> bool:
    """Whether a consuming run starts at any word asked: the command word, or every word when it may be a wrapper."""
    # A run is read-only when one of the three stands after its start: the last one's index, found once for the
    # simple command, answers that for every start without a copy of the rest.
    last_read_only = max((i for i, w in enumerate(words) if w in READ_ONLY), default=-1)
    for k in range(len(words) if every_word else min(1, len(words))):
        start = inbox_run(words, k)
        if start is not None and last_read_only < start:
            return True
    return False


def tokens(text: str) -> list[str] | None:
    """The words, quotes off, and the operators, each its own token; None when the lexer cannot read the text."""
    lex = shlex.shlex(text, posix=True, punctuation_chars="();<>|&\n")
    lex.commenters = ""
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    try:
        raw = list(lex)
    except ValueError:
        return None
    out: list[str] = []
    for tok in raw:
        out += OPERATOR.findall(tok) if tok and set(tok) <= set("|;&\n()<>") else [tok]
    return out


def simple_commands(toks: list[str]) -> list[tuple[list[str], bool]]:
    """Each simple command's words (redirections and their targets out) and whether a pipe follows it."""
    out: list[tuple[list[str], bool]] = []
    cur: list[str] = []
    skip = False
    for tok in toks:
        if tok in SEPARATORS or tok in PIPES or tok in ("(", ")"):
            out.append((cur, tok in PIPES))
            cur, skip = [], False
        elif "<" in tok or ">" in tok:
            skip = True          # its target, a file or an fd, is no word of the command
        elif skip:
            skip = False
        else:
            cur.append(tok)
    out.append((cur, False))
    return out


def command_word(words: list[str]) -> int:
    k = 0
    while k < len(words) and (words[k] in LEADING or ASSIGN.match(words[k])):
        k += 1
    return k


def loosely_consuming(text: str) -> bool:
    """A consuming run anywhere, by word, whatever stands before it: the closed reading's question."""
    for chunk in LOOSE_CHUNK.split(text):
        words = LOOSE_WORD.findall(chunk)
        if consuming(words, True):
            return True
    return False


def blank_substitutions(text: str) -> str:
    """The text with every substitution that runs no consuming gzcoord-inbox, and every arithmetic span, blanked,
    innermost first, until none is left to blank. Each round shortens the text, so it ends; the spans left each hold a
    consuming run (or an arithmetic span one of them), and stay for the closed reading."""
    def inner(m: re.Match) -> str:
        return m.group(0) if loosely_consuming(m.group(1) if m.group(1) is not None else m.group(2)) else PLACEHOLDER

    def arithmetic(m: re.Match) -> str:
        body = m.group(0)[3:-2]
        return m.group(0) if SUBSTITUTION.search(body) or loosely_consuming(body) else PLACEHOLDER

    while True:
        out = ARITHMETIC.sub(arithmetic, INNER_SUBST.sub(inner, text))
        if out == text:
            return text
        text = out


def refused(command: str) -> bool:
    if "inbox" not in command:
        return False
    shape = _sibling("post-review-shape-guard")
    live = blank_substitutions(shape.live_text(command)[0].replace("\\\n", ""))
    if "inbox" not in live:
        return False
    piped_or_captured = "|" in live or bool(SUBSTITUTION.search(live))
    toks = tokens(live)
    if toks is None:
        return piped_or_captured and loosely_consuming(live)
    # live_text gives a runner's quoted payload back at the end of the text, not where it stood, and a double-quoted
    # payload is one word here: beside a runner, as beside a group or a substitution, positions are not read.
    commands = [(words[command_word(words):], piped) for words, piped in simple_commands(toks)]
    # `.` only as a command word: as an argument it is a path (`grep -rn gzcoord-inbox . | head`).
    closed = (SUBSTITUTION.search(live) or "(" in toks or any(t in GROUP_WORDS for t in toks)
              or any(os.path.basename(t) in shape.RUNNERS for t in toks)
              or any(words[:1] == [DOT] for words, _ in commands))
    if closed and piped_or_captured and loosely_consuming(live):
        return True
    for words, piped in commands:
        if piped and words and consuming(words, os.path.basename(words[0]) not in READERS):
            return True
    return False


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        command = (payload.get("tool_input") or {}).get("command")
    except (ValueError, AttributeError):
        return 0
    if not isinstance(command, str) or not refused(command):
        return 0
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": REASON}}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
