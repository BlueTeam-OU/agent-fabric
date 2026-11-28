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
`&` and newlines. A `$( … )` or backtick span in which the loose scan below finds no consuming run, and no runner or
process substitution stands, is blanked to a word first, so naming an inbox file is no capture (`f=$(mktemp -t
inbox.XXXXXX); gzcoord-inbox > "$f"` passes), and a `$(( … ))` is arithmetic, blanked on the same test
(`n=$((n+1))`); a process substitution never is. Where one span is kept, or a `)` in a span may not close it (a
quoted one), nothing is blanked and the text is read as written (#721 F7); from the first mark after which a `)` may
not close what it seems to (an escape, an unquoted heredoc, a case, a `$[`, a quote inside a `${ … }`) the text is
read as written, and the spans closed before it are blanked still (#721 F9). Groups,
compound commands, the substitutions left and runners are not followed: when the command holds any of them (`(`, `{`,
`}`, `fi`, `done`, `esac`, `$(`, a backtick, `<(`, `>(`, a word of post-review-shape-guard's RUNNERS, `.`) and a
consuming run found by a loose scan of every word (mention or run alike, readers not exempt), it is refused if it also
holds a `|` anywhere or a substitution. Runners are in the list because live_text gives their quoted payload back at
the end of the text, not where it stood, and a double-quoted `bash -c "…"` payload is one word to the lexer. A
nesting-aware reading of bash lost review rounds in both directions for the two sibling guards that tried (their
headers say so); a false deny costs a rephrase (`gzcoord-inbox; ( cd x && git log | head )` is one), a false allow
costs messages.

SCOPE. A fence against the habit of filtering the drain, not a sandbox. Not seen: a command word the shell builds
(`$c | head`, `'gzcoord-inbox' | head`, whose quotes live_text drops as inert text), a script or alias that drains, a
link to the command under another name. Each costs messages only when written on purpose.

COST. Nothing is loaded unless `inbox` occurs in the command (the hook runs on every Bash call); canonical() is asked
only where `inbox` stands in the words it reads, and with those NAMING_WORDS words only, never the rest of the command;
whether a run is read-only is one index per simple command; blanking joins each span's body once and stops at the
first span kept. So every reading is linear in the text: a long run of words that mostly hold `inbox`, and a deep
nesting of kept substitutions, each once took longer than the hook's 5 s timeout, which counts as no objection
(#721 F1, F8).

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
# A $( … ) or backtick span is blanked to PLACEHOLDER when the loose scan finds no consuming run in it and no runner
# or process substitution stands in it (_kept):
# `f=$(mktemp -t inbox.XXXXXX); gzcoord-inbox > "$f"` is the way out the reason names, and
# `cd "$(git rev-parse --show-toplevel)"` beside the watch is no capture. A $(( … )) span is arithmetic, which runs no
# command, blanked on the same test (bash reads `$((gzcoord-inbox | head))` as arithmetic, but a shell that did not
# would drain; keeping it costs a rephrase). A `$((` whose first `)` is not `))` opens a substitution of a subshell, as
# bash reads `$((cd x); gzcoord-inbox)`. Never a <( … ) or >( … ): `gzcoord-inbox > >(head)` is a pipe by another name.
# The text is given back as written, nothing blanked, the moment one span is kept (its `$(` decides the command, and
# blanking the rest would only cost time, #721 F8). Quotes are not parsed here, so a `)` is not trusted to close a
# span (#721 F7: a quoted one or a case pattern's ended a span early, its `$(` was blanked away and the run after it
# read as bare) when the span's body holds an odd count of `"` or when a `)` meets no open span: nothing is blanked
# then either. From _untrusted()'s offset on, nothing is trusted: a span whose closing `)` or backtick stands before
# it is judged as above, and everything from it on, a span still open there included, is left as written. Only that
# far, not the whole text: a heredoc, an escaped quote or the word esac after the way out's `$(mktemp …)` closed
# leaves that span blanked (#721 F9), and no quote parity is asked across the offset, where an escaped `"` stands.
SUBST_MARK = re.compile(r"\$\(\(|\$\(|[()`]")
# A `(`, `)`, `}` or quote that may be no such thing: after a backslash, in the body of a heredoc whose delimiter is
# unquoted (live_text drops a quoted one's body; its delimiter is let through here), or inside the old arithmetic
# `$[ … ]`, which bash nests to its `]` (`$[0)]` closes no `$(`, and `${y:-$[}]}` no `${`); the offset is the
# backslash, the `<<` or the `$[`, before what they change. A delimiter may itself begin with `-` (`<<--EOF`, `<<- -EOF`
# read `-EOF`, #721 round 4): only the one `-` after `<<` is the tab-stripping flag, so it is not a quote.
UNTRUSTED = re.compile(r"\\[()`\"$]|(?<!<)<<(?:-|(?!-))[ \t]*(?![<'\"\\ \t])|\$\[")
# A case pattern's `)` closes nothing. It stands after its `case` word, so where an `esac` stands the earliest `case`
# word, or the `esac` when it comes first, is the offset: a `case` that is no reserved word only moves it earlier.
ESAC = re.compile(r"\besac\b")
CASE = re.compile(r"\bcase\b")
# Inside a parameter expansion, a `(`, `)`, backslash, `"` or backtick is untrusted, which BRACE_MARK finds in one
# forward pass (a regex from every `${` to its `}` was quadratic in their nesting). A quote or backtick because this
# scan does not read them: a quoted or backticked `}` ended the depth early and a later `(` or `)` read as trusted
# (#721 F7, `${y:-"}")}`). The scan stops at the first one, so the offset is that mark.
BRACE_MARK = re.compile(r"\$\{|[{}()\\\"`]")
# Holds no `inbox`, so a command whose every mention was blanked passes before the lexer runs.
PLACEHOLDER = "_pipe_guard_subst_"


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
    """The text with every substitution and arithmetic span blanked that closes before _untrusted()'s offset, the
    rest as written; or all of it as written when a span is kept (_kept) or the pairing cannot be trusted
    (SUBST_MARK's comment says when). One pass over the text, each
    span's body joined and judged once, when it closes, its children already blanked; the pass stops at the first span
    kept, so nothing is re-joined level after level and the cost is linear whatever the nesting (#721, #721 F8)."""
    blanked = _blanked(text, _untrusted(text))
    return text if blanked is None else blanked


def _untrusted(text: str) -> int | None:
    """The first offset from which a `(`, `)`, backtick or quote may be no such thing, or None (SUBST_MARK's comment)."""
    offsets = []
    if (m := UNTRUSTED.search(text)) is not None:
        offsets.append(m.start())
    if (m := ESAC.search(text)) is not None:
        case = CASE.search(text)
        offsets.append(m.start() if case is None else min(case.start(), m.start()))
    depth = 0       # open `${`, and the plain braces inside them
    for m in BRACE_MARK.finditer(text):
        mark = m.group(0)
        if mark == "${" or (mark == "{" and depth):
            depth += 1
        elif mark == "}":
            depth = max(depth - 1, 0)
        elif depth and mark != "{":
            offsets.append(m.start())   # a paren, a backslash, a quote or a backtick inside a parameter expansion
            break
    return min(offsets, default=None)


def _blanked(text: str, untrusted: int | None) -> str | None:
    """blank_substitutions' reading, up to `untrusted`; the text from there on is given back as written."""
    limit = len(text) if untrusted is None else untrusted
    out: list[str] = []
    # One output list and a stack of the open spans: (the mark, where it stands in out, the `"` count before it). A
    # span's body is out after its mark; a plain `(` span is only paired, never judged, so it joins nothing.
    stack: list[tuple[str, int, int]] = []
    quotes = at = 0
    # A mark is searched only before the limit, so every `)` paired here closes before it.
    while (m := SUBST_MARK.search(text, at, limit)) is not None:
        chunk = text[at:m.start()]
        out.append(chunk)
        quotes += chunk.count('"')
        mark, at = m.group(0), m.end()
        if mark == "`":
            close = text.find("`", at)
            if close < 0:
                return None
            if close >= limit:
                at = m.start()      # its closing backtick is untrusted: the span is left as written
                break
            inner = text[at:close]
            # Unreachable while the limit is _untrusted's over this same text (a mark in the body would be the offset);
            # kept so a caller passing another limit cannot blank a body nobody judged.
            if _untrusted(inner) is not None:
                return None
            body = _blanked(inner, None)
            if body is None or _kept(body):
                return None
            at = close + 1
            out.append(PLACEHOLDER)
        elif mark != ")":
            stack.append((mark, len(out), quotes))
            out.append(mark)
        elif not stack or (quotes - stack[-1][2]) % 2:
            return None
        else:
            opened, mark_at, quotes_before = stack.pop()
            # No `at < limit` test: at the limit stands the start of an untrusted mark, never a `)` (#721 F11, measured with
            # at == limit for `$((cd x)\"y\"`), so the second `)` of `))` is only ever found before it.
            if opened == "$((" and not text.startswith(")", at):
                # `$((cd x); …)`: the `(` after `$(` opened a subshell, closed here, in a substitution still open.
                stack.append(("$(", mark_at, quotes_before))
                out.append(")")
            elif opened == "(":
                out.append(")")
            else:
                if opened == "$((":
                    at += 1
                body = "".join(out[mark_at + 1:])
                if opened == "$(" and out[mark_at] == "$((":
                    body = "(" + body
                if _kept(body):
                    return None
                del out[mark_at:]
                quotes = quotes_before
                out.append(PLACEHOLDER)
    rest = text[at:]
    if untrusted is not None:
        # A span still open here keeps its mark in out, so the command still reads as captured; a quote open here may
        # close on an escaped `"`, which is why the offset is one, so its parity is not asked.
        out.append(rest)
        return "".join(out)
    if stack or (quotes + rest.count('"')) % 2:
        return None
    out.append(rest)
    return "".join(out)


def _kept(body: str) -> bool:
    """A span is kept when a process substitution or a runner stands in it or a consuming run is found in it."""
    return bool(SUBSTITUTION.search(body)) or _runner(body) or loosely_consuming(body)


def _runner(body: str) -> bool:
    """A runner, or `.` as a command word: live_text gave its quoted payload back at the end of the text, so the body
    is not what the shell runs there (`x=$(bash -c 'gzcoord-inbox')` was blanked to no capture, the run read as bare)."""
    runners = _sibling("post-review-shape-guard").RUNNERS
    if any(os.path.basename(w) in runners for w in LOOSE_WORD.findall(body)):
        return True
    for chunk in LOOSE_CHUNK.split(body):
        words = LOOSE_WORD.findall(chunk)
        if words[command_word(words):][:1] == [DOT]:
            return True
    return False


def refused(command: str) -> bool:
    if "inbox" not in command:
        return False
    shape = _sibling("post-review-shape-guard")
    live = blank_substitutions(shape.live_text(command)[0].replace("\\\n", ""))
    if "inbox" not in live:
        return False
    piped_or_captured = "|" in live or bool(SUBSTITUTION.search(live))
    # A substitution left standing makes the reading closed and the command captured: the loose scan alone decides,
    # before the lexer reads a text that may be long (#721 F8).
    if SUBSTITUTION.search(live) and loosely_consuming(live):
        return True
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
