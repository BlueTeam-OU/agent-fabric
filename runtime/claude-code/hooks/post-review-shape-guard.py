#!/usr/bin/env python3
"""runtime/claude-code/hooks/post-review-shape-guard.py: a PreToolUse hook on Bash.

Refuses a command that names `fabric-pr` and `post-review` and is not the
bare command `fabric-pr post-review [options] <n> [< <report>]` (or its
dispatcher spelling `fabric pr post-review …`), unless every mention of the
two words is in text the shell never runs; and names the bare form.

WHICH WORDS ARE `fabric-pr`. tools/fabric/cli canonical() says, never a
pattern here (agent-fabric ADR-068 §5 rule 7): it reads `fabric-pr`, `fabric
pr`, `bin/fabric-pr` and the `env`/`command` prefixes to the one command, so
a spelling the dispatcher adds is guarded the day it is added. The command
table it reads (runtime/claude-code/commands.json) is from this hook's own
checkout; one that cannot be read refuses, as any other failure to decide.

WHY. Posting the review class's report on one's own pull request is the
author's job (ADR-020), and every account allows it: user-settings.py
writes `Bash(fabric-pr *)` into its permissions. That rule is a prefix
match. A call wrapped in anything else (`cd <worktree> && …`, `… 2>&1 |
tail -8`, an env assignment, a path to the script) does not match it and
goes to the auto-mode classifier, which reads a review posted on the
poster's own pull request as [Self-Approval] and refuses — for the rest of
the session, so the owner had to post by hand: fabric-coordinator on
gateway #75 (2026-10-20) and twice on 2026-10-27, python-dev-03 on #400,
python-dev-01 twice on #449 (2026-11-01, REPLY 01a196fa). A prose allow
entry in policies/auto-mode.json (#396) did not stop it, and a memory did
not reach the other accounts. A deny here costs a rephrase and keeps the
classifier from ever being asked; the classifier's refusal costs the owner.

WHAT COUNTS AS BARE. The whole command, stripped, is `fabric-pr` (or
`fabric pr`) as its first word, then `post-review`, then words with no shell
operator in them — no `;`, `&`,
`|`, `$`, a backtick, a parenthesis, `>` or a newline — and at most one
`<` redirection from a file. Quotes are allowed around a word, not around
the command: `"fabric-pr"` and `\\fabric-pr` are not the prefix the rule
matches, and neither is a path, an assignment or `env` before it.

WHY INERT TEXT, NOT A PARSE OF WHAT RUNS. Two rounds of review on #451
found that deciding which words run misses both ways: a text regex let
`time …`, `{ …; }` and `bash -c "…"` through and denied quoted mentions;
a shlex walk of command positions let `"$(…)"`, `time -p`, `sudo -E bash
-c` and `bash <<EOF` through, and went quadratic and recursive. A guard
for a habit must not need a shell parser to be right (pipe-status-guard
learned the same). So the question is turned round: the two words are
looked for in everything except text the shell provably never runs (a
live word canonical() reads as `fabric-pr`, with `post-review` anywhere
after it) —
  - a comment (`#` beginning a word, to the end of the line);
  - a single-quoted string, or an ANSI-C `$'…'` one (a `\\'` in it does not
    close it); a quote left open is live, so a misread cannot hide what
    follows (review of #451, F10);
  - the body of a heredoc whose delimiter is quoted (`<<'EOF'`, `<<"EOF"`,
    `<<\\EOF`), wherever it stands, inside a `"$(…)"` included, ended as
    bash ends it: the delimiter alone on its line, leading tabs only after
    `<<-`;
and those two last are live after all when the command names a word that
runs its arguments (RUNNERS: a shell, `eval`, `source`, `su`, `ssh`,
`watch`, `flock`; by bare name, its quotes off, anywhere, and by a path unless
the command only reads files, since `grep … runtime/ssh` reads one) or `.` as a command
word (after `{`, `elif` or a case arm's `)` too) or before `/dev/stdin`,
since a `-c` string, a piped script or a heredoc fed to a shell runs;
`.` as an argument is a path (`grep -rn '…' .`, F9). Everything
else is live: unquoted words,
double-quoted strings (a `$(…)` in one runs), an unquoted heredoc's body.
Over-reported, on purpose, and named in the deny so the session knows the
way through: an unquoted or double-quoted mention (`echo fabric-pr
post-review`, `git commit -m "… fabric-pr post-review …"`) — put the words
in single quotes, a quoted heredoc or a file. Not seen: a script file that
runs a post-review (`bash post.sh`), and a program that runs text it was
given in a way no word here names (`python -c`, `sed …/e`) — a fence against
the habit of wrapping, not a sandbox.

COMMAND WORDS THE WALK CANNOT NAME. Inert text is only safe while nothing
can run it, and a word whose letters the shell picks can be anything,
`bash` or `fabric-pr` included: `read -r c <<< 'fabric-pr post-review 1';
$c`, `"${c}" post-review 1`, `e$c`, `/bin/${c} -c '…'`. The invariant: when
the walk meets a command word it cannot name statically, the command is
refused if it also holds text that could be post-review's input or its
words — `post-review` or `fabric-pr` anywhere (quoted, a heredoc, a comment
too), or a `<` (a redirection, a here-string, a heredoc). Without that text
the unnameable word is passed (`"$PY" -m pytest`, `$EDITOR notes.md`), so
the refusal stays rare; with it, there is a post-review the walk cannot
rule out, and a refusal costs a rephrase. A command word the walk cannot
name is
  - one with a mark anywhere outside single quotes: an unquoted or
    double-quoted expansion (`$c`, `${c}`, `e$c`, `/bin/${c}`), a `$(…)` or
    backtick, `$'…'` (its escapes spell the name), a glob (`*`, `?`, `[`) or a
    brace list (`{a,b}`) or an extglob (`@(`, `+(`, `!(`, `?(`, `*(` glued to
    the word). Failing closed: no part of such a word is trusted to
    name the command, not even the text after its last `/` (three rounds of
    review on #637 each found a spelling past a rule that said where the last
    part begins: `${c/z/z}`, `$c/`, `{fabric-pr,x,o/n}`, `$'/x/\x66…'`). The
    cost: `"$R"/bin/fabric-pr` and `$ROOT/bin/fabric-pr` are unnamed too, and
    are refused whenever the line holds `fabric-pr` (post-review text or a `<`
    is not needed); `cd "$R" && bin/fabric-pr` or the bare name is the way
    through. `[` and `[[` alone are the test builtin, not a glob;
  - the command word position itself is not trusted to the walk's reading of
    wrappers (`timeout 5s`, `sudo -u X`, `setsid`, a leading `2>/dev/null`
    all misread it): after a wrapper, or a program this file does not list
    as one that never runs its arguments (PLAIN), every later word that is
    not nameable counts, until a PLAIN command shows up (`sudo grep -n x
    "$f"` is a grep). Which words are option values the walk does not know
    (`env -vu echo $c`, `strace -o echo $c`, `env --uns echo $c`), so it fails
    closed: a word right after an option word (one starting with `-`) is never
    taken for the PLAIN command, and an unnameable word counts whether or not
    it might be an option value (`env -u $c` word-splits into value and
    command). A word starting with `-` (a glued `--chdir=/tmp/echo` too) and an
    assignment (`TAG=/tmp/echo`) are never a command's name, whatever their
    last part says. A wrapper with a positional operand before its command
    (`sg GROUP`, `chroot DIR`, `ip netns exec NAME`, `runuser`, `su`) takes the
    first word that is no option as that operand, so the next PLAIN name does
    not end the open phase either (a non-PLAIN one is still read as a command
    too, so `runuser -u me env -S '…'` sets env's flag). The cost: `xargs`,
    `parallel`, `find -exec` and `env -S`, whose command line never names a
    PLAIN command, are refused beside a `<`, `fabric-pr` or post-review text,
    expansion or not (`xargs -r rm -f < list.txt`, `git ls-files -z | xargs -0
    grep -l 'post-review'`); `xargs -n 1 grep …` is not. An expansion after
    any wrapper option (`sudo -n grep -n x "$f"`) is refused with cause
    `word`; `sudo -n grep -n x f < in` passes. The deny's reason names which of
    the four causes it fell to (the word, the wrapper, the bare-form rule, the
    guard being unable to decide). A
    redirection's fd and target are no word at all;
  - what `xargs` and `find -exec` run, unless a PLAIN command is named
    there: `xargs grep -n foo` is a grep, `xargs env` and `xargs -I X env
    -S X` run what stdin says; `env -S` runs its text.
SCOPE. This guard stops the accidental non-bare shapes a session writes. A
session that deliberately hides a command (reading it from a file, building it
at run time, `eval` of text assembled from pieces the walk cannot see) is not
stopped by any static reading of bash, and is out of this guard's scope: the
fence for that is the harness permission (only the bare `fabric-pr` form is
allowed without the classifier) and the review's identity on GitHub.

Not covered: an argument assembled from pieces (`fabric-pr ${a}${b}`), a
program not in PLAIN or RUNNERS that runs text itself. The dispatcher `fabric`
is not in PLAIN, since its noun is a command (`fabric $c` with c='pr
post-review 1'): an expansion after it counts, at the cost of a refusal of
`fabric status "$x"` beside text that names post-review. The list PLAIN is
what keeps everyday commands (`git`, `gh`, `grep`, `sed`, `printf`, `find`,
`fabric-pr gate`) passing; a name missing from it costs one false refusal
when the line also names post-review.

COST. One pass over the text, no recursion and no backtracking: each
character is looked at a bounded number of times, so the 5 s the settings
give the hook covers any command a session sends (review of #451, F3, F6,
F7). Nothing is scanned unless `post-review`, `fabric-pr` or a `<` occurs in the
text, and no table is read unless `post-review` does: the command's name is
not looked for before canonical() is asked.

Output: one deny decision on stdout, or nothing. Exit 0 always: a payload it
cannot read is passed, never blocked (a command table it cannot read is not
a payload: that refuses).
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
# The command and verb this guard is about, compared with what canonical() reads, never with the words as spelled.
COMMAND, VERB = "fabric-pr", "post-review"
# Greedy over classes that exclude `<`, so a match never backtracks: linear on any input (the lazy form was not).
# The command's words come before the `<`; whether they are `fabric-pr post-review` is canonical()'s to say.
BARE = re.compile(r"([^;&|$`()<>\n]*)(?:<[^;&|$`()<>\n]*)?")
# What ends a word of live text for canonical(): the shell's operators and quotes (a double-quoted `"fabric-pr"`
# still runs it) and the backslash (`\fabric-pr` does too).
LIVE_WORD = re.compile(r"[^\s;&|()<>`\"$\\]+")
# canonical() needs at most `fabric <noun> <verb>` to name a command; the arguments are not its question here.
NAMING_WORDS = 3
# A word that runs its arguments as commands, wherever it stands: over-reported in argument position, which costs a
# rephrase. `.` is `source` only as a command word: as an argument it is a path (`grep -rn '…' .`; review of #451, F9).
RUNNERS = {"bash", "sh", "dash", "zsh", "ksh", "eval", "source", "su", "ssh", "watch", "flock"}
# Wrappers that take positional words before the command, and how many non-option words each skips (`sg GROUP cmd`,
# `chroot DIR cmd`, `ip netns exec NAME cmd`, `runuser USER cmd`, `su USER`). The walk cannot tell the operand from the
# command, so the first non-option words are the operand and a PLAIN name among them does not end the open phase.
OPERANDS = {"sg": 1, "chroot": 1, "runuser": 1, "su": 1, "ip": 3}
WRAPPERS = {"sudo", "env", "exec", "command", "builtin", "nohup", "nice", "time", "timeout", "xargs", "then", "do",
            "else", "elif", "if", "while", "until", "!", "{"} | set(OPERANDS)
# What `.` reads a script from when it is fed a heredoc or a pipe, and any /dev/fd/N (`3<<'EOF'`). `.` followed by one of these runs that input,
# wherever the reading of command words placed it: a leading redirection (`2>/dev/null . /dev/stdin`) is a word
# the walk cannot tell from a command (j543, #451 round 4 F11). Over-reported as an argument, which costs a rephrase.
STDIN_PATHS = {"/dev/stdin", "/dev/fd/0", "/proc/self/fd/0"}
# Commands that only read the files they are given: under one of these, a path whose last part names a runner
# (`grep … runtime/ssh`) is a file, not a shell (j543, F12). Anything else keeps a runner by path live, so a command
# word the walk misreads (`2` of `2>/dev/null`, `root` of `sudo -u root`) over-reports instead of letting
# `/bin/bash -c '…'` through (review of #501 round 4, F6). find, sed and awk are not readers: each can run a command.
READERS = {"grep", "egrep", "fgrep", "rg", "ag", "ack", "git", "ls", "cat", "head", "tail", "wc", "diff", "stat",
           "file", "less", "more"}
WORD_END = set(" \t\n;&|()<>")
# Words after which the next word is a command word again, not an argument.
KEYWORDS = {"then", "do", "else", "elif", "if", "while", "until", "!", "{"}
ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\+?=")
# After `$`, what starts an expansion (a name or digit is tested apart): `${`, `$@`, `$?`, `$$`, `$!`, `$-`, `$#`, `$*`.
EXPANSION_CHARS = set("_{@*#?$!-")
# Programs that feed their command line from elsewhere: what follows is the command, or the stdin is its arguments.
FEEDERS = {"xargs", "parallel"}
EXEC_FLAGS = {"-exec", "-execdir", "-ok", "-okdir"}
# Programs known not to run their arguments as a command (as far as this fence goes: `sed`'s `e` and `python -c` run
# text too, and are no more seen than before). Under one of these an expansion is an argument; under anything else (a
# wrapper, a program the list does not know) a later word may be the command, so an expansion there is not nameable.
# Keep it to what agents run every day beside text that mentions post-review: each name is a false refusal avoided.
PLAIN = READERS | {"echo", "printf", "cd", "pwd", "gh", "sed", "awk", "jq", "python", "python3", "tee", "sort", "uniq",
                   "tr", "cut", "cp", "mv", "rm", "mkdir", "rmdir", "touch", "ln", "chmod", "test", "[", "[[", "true",
                   "false", ":", "export", "local", "declare", "readonly", "unset", "read", "set", "shift", "exit",
                   "return", "for", "case", "select", "find", "date", "sleep", "basename", "dirname", "realpath",
                   "mktemp", "tar", "curl", "make", "cargo", "npm", "pytest", COMMAND, "fabric-adr",
                   "fabric-jobs", "fabric-status", "fabric-whoami"}
REASON = ("Post the review as the bare command `fabric-pr post-review [--repo <owner/name>] [--model <m>] <n> < <report>`, "
          "and nothing else in the call: no `cd … &&` (use --repo for another repository), no `2>&1`, no pipe, no `;`, "
          "no wrapper (time, env, bash -c), no path to the script, no variable, "
          "no command word from an expansion, substitution or glob. The bare form is what the "
          "`Bash(fabric-pr *)` permission every account has matches; a wrapped one goes to the auto-mode classifier, "
          "which refuses a review on your own pull request as [Self-Approval] for the rest of the session. "
          "Read its output in the next call. If this command only mentions the two words (a grep, a commit message, "
          "a doc), put them in single quotes, a quoted heredoc (<<'EOF') or a file.")
# One short clause per cause class, appended to REASON, so a refusal says which rule it fell to.
CAUSES = {
    "word": " Refused for: a command word the walk cannot name (an expansion, substitution, glob, brace list or extglob; "
            "`\"$R\"/bin/fabric-pr` is one).",
    "wrapper": " Refused for: a command line that names no plain command (`xargs`, `parallel`, `find -exec`, `env -S`) "
               "beside a `<` or the words.",
    "bare": " Refused for: the bare-form rule, the call names fabric-pr with post-review and is not the bare command.",
    "undecided": " Refused for: the guard could not decide (its command table is unreadable).",
}


class Simple:
    """The walk's state for one simple command and the word being read in it. A `$( … )` or backtick gets a fresh one
    and the outer one is kept, so the word that holds the substitution is still seen whole when it closes."""
    __slots__ = ("first", "after_wrapper", "prev", "command", "phase", "plain_name", "fed", "env", "exec", "redir",
                 "word", "uq", "wilds", "after_option", "operands")

    def __init__(self) -> None:
        self.word: list[str] = []     # the current word, its quotes off
        self.uq: list[str] = []       # one char per char of `word`: itself if unquoted, "Q" if quoted or escaped
        self.wilds: list[int] = []    # offsets in the word where the shell, not the text, decides what it says
        self.reset()

    def clear_word(self) -> None:
        self.word.clear()
        self.uq.clear()
        self.wilds = []

    def reset(self) -> None:
        self.first, self.after_wrapper, self.prev, self.command = True, False, "", ""
        # The nameability walk, apart from the above: "cmd" (the command word is still to come), "open" (a wrapper or
        # an unknown program stands in front, so a later word may be the command), "plain" (the command is known
        # not to run its arguments).
        self.phase, self.plain_name = "cmd", ""
        self.after_option = False   # the last word was an option of a wrapper: the next may be its value
        self.operands = 0           # positional words the wrapper in front still takes before its command
        self.fed = self.env = self.exec = self.redir = False


def unnameable(uq: str) -> list[int]:
    """Offsets in an unquoted-text mask where a glob or a brace expansion makes the shell pick the word's letters.
    One pass: no regex, so no input backtracks."""
    found: list[int] = []
    brace, seen = -1, False
    for k, ch in enumerate(uq):
        if ch in "*?[":
            found.append(k)
        elif ch == "{":
            brace, seen = k, False
        elif ch == "," and brace != -1:
            seen = True
        elif ch == "." and brace != -1 and uq[k - 1:k] == ".":
            seen = True
        elif ch == "}" and brace != -1:
            if seen:
                found.append(brace)
            brace = -1
    return found


def live_text(cmd: str) -> tuple[str, str]:
    """(the text the shell may run, why a command word is one the walk cannot name: "" no, "word" or "wrapper"). The
    text is the command less comments, single-quoted strings and quoted-delimiter heredoc bodies, those two given back
    when the command names a shell, eval or source; the cause is the invariant of the header's COMMAND WORDS THE WALK
    CANNOT NAME."""
    live: list[str] = []
    inert: list[str] = []
    runner = False
    dynamic = ""
    states = [Simple()]
    stack = ["N"]               # N: unquoted (top level, $( … ) or ` … `); D: inside "…"
    depth = [0]                 # open parentheses inside each $( … )
    pending: list[tuple[str, bool, bool]] = []      # heredocs opened on this line: (delimiter, quoted, <<-)
    n, i = len(cmd), 0

    def add(text: str, plain: bool = False) -> None:
        s = states[-1]
        s.word.append(text)
        s.uq.extend(text if plain else "Q" * len(text))

    def mark() -> None:
        """An offset where the shell, not the text, picks the word's letters: any such mark makes the word unnamed."""
        s = states[-1]
        s.wilds.append(len(s.uq))

    def literal(s: Simple, name: str, full: str) -> None:
        """A word that names itself where a command (or what a wrapper runs) may be."""
        nonlocal dynamic
        if name in PLAIN:
            s.phase, s.plain_name = "plain", name
            return
        s.phase = "open"
        if name == "env":
            s.env = True
        elif name in FEEDERS:
            s.fed = True
        elif name in OPERANDS:
            s.operands = OPERANDS[name]

    def end_word() -> None:
        """Close the word: its quotes are already off (`"bash" -c` names bash), so it is a runner by its name."""
        nonlocal runner, dynamic
        s = states[-1]
        if not s.word:
            return
        full = "".join(s.word)
        wilds = s.wilds + unnameable("".join(s.uq))
        redir = s.redir
        s.clear_word()
        if redir:                   # the target of a redirection: neither a command word nor a wrapper's argument
            s.redir = False
            return
        name = full.rsplit("/", 1)[-1]
        # A runner by bare name counts anywhere (`find -exec bash -c '…'` runs it); by path, unless the command
        # only reads files (READERS says why).
        named = name in RUNNERS and ("/" not in full or s.command not in READERS)
        stdin = full in STDIN_PATHS or (full.startswith("/dev/fd/") and full[8:].isdigit())
        runner = runner or named or (s.first and name == ".") or (s.prev == "." and stdin)
        if not (s.prev == "." and full == "--"):            # `. -- /dev/stdin` reads the path after the --
            s.prev = full
        if s.first:
            option = s.after_wrapper and (name.startswith("-") or "=" in name or name.isdigit())
            s.after_wrapper = name in WRAPPERS or option
            s.first = s.after_wrapper or "=" in name         # an assignment leaves the command word still to come
            if not s.first:
                s.command = name
        # Can the walk name this word? Not with a mark anywhere in it, a part before the last `/` included: where the
        # last part begins is itself what an expansion, a brace list or `$'…'` can move (header, #637 F1).
        unnamed = bool(wilds) and not (full in ("[", "[[") and wilds == list(range(len(full))))
        if s.phase == "plain":
            if s.plain_name == "find" and full in EXEC_FLAGS:       # what `-exec` runs is a command line of its own
                s.phase, s.fed, s.exec = "open", True, True
            elif s.exec and full in (";", "+"):
                # Back to find: the exec'd command's name (`true`) must not stand for the next `-exec`.
                s.phase, s.plain_name, s.fed, s.exec = "plain", "find", False, False
            return
        if s.phase == "cmd" and ASSIGN.match(full):
            return
        # Which words are option values, and which options take one, is unknown for any wrapper (`env -vu`, `--uns`,
        # `strace -o`), so unnamed is judged first and a word straight after an option is never the PLAIN command
        # that ends the open phase: it may be the option's value (#637 F2, F10).
        after_option, s.after_option = s.after_option, False
        if unnamed:
            dynamic = dynamic or "word"
            s.phase = "open"
        elif s.phase == "cmd" and name in KEYWORDS:
            return
        elif full[:1] == "-" or ASSIGN.match(full):
            # Never a command's name, whatever the part after a `/` says (`env TAG=/tmp/echo $c`, `--chdir=/tmp/echo`): the
            # phase is open, as a wrapper's option leaves it (codex round 3 of #637, F1).
            if full in EXEC_FLAGS and s.phase == "open":
                s.fed = s.exec = True           # a find swallowed as an operand (`chroot /srv/ip find`) still runs its -exec
            s.phase = "open"
            if s.env and (full == "--split-string" or full.startswith("--split-string=")
                          or (full[:1] == "-" and full[1:2] != "-" and "S" in full)):
                dynamic = dynamic or "wrapper"      # `env -S 'text'` runs the text as a command line
        elif s.phase == "open" and s.operands and not after_option:
            s.operands -= 1                         # `sg test $c`: `test` is the group, not the command
            if name not in PLAIN:                   # but `runuser -u me env -S …` may be the command: it sets its flags
                left = s.operands
                literal(s, name, full)
                s.operands = left                   # a directory named `ip` is no wrapper: the count stays as decremented
        elif not (after_option and name in PLAIN):
            literal(s, name, full)
        if s.phase == "open":
            s.after_option = full[:1] == "-"

    def separator() -> None:
        nonlocal dynamic
        end_word()
        s = states[-1]
        if s.phase == "open" and s.fed:     # xargs, or find -exec, whose command line never named a plain command
            dynamic = dynamic or "wrapper"
        s.reset()

    def open_sub(kind: str) -> None:
        mark()                              # the word holding the substitution is not text the walk can read
        states[-1].word.append("")
        states.append(Simple())
        stack.append(kind)
        if kind == "S":
            depth.append(0)

    def close_sub(kind: str) -> None:
        separator()
        states.pop()
        stack.pop()
        if kind == "S":
            depth.pop()

    while i < n:
        c = cmd[i]
        top = stack[-1]
        s = states[-1]
        if top == "D":
            if c == "\\" and i + 1 < n:
                live.append(cmd[i:i + 2])
                i += 2
                continue
            if c == '"':
                stack.pop()
            elif cmd.startswith("$(", i):
                open_sub("S")
                live.append("$(")
                i += 2
                continue
            elif c == "`":
                open_sub("B")
            else:
                if c == "$" and i + 1 < n and (cmd[i + 1].isalnum() or cmd[i + 1] in EXPANSION_CHARS):
                    mark()
                add(c)
            live.append(c)
            i += 1
            continue
        # Unquoted: the top level, a $( … ) or a ` … `.
        if c == "\\" and i + 1 < n:
            live.append(cmd[i:i + 2])
            add(cmd[i + 1])
            i += 2
            continue
        if cmd.startswith("$'", i):
            j = i + 2                                    # ANSI-C quoting: \' does not close it (review of #451, F10)
            while j < n and cmd[j] != "'":
                j += 2 if cmd[j] == "\\" else 1
            (inert if j < n else live).append(" " + cmd[i + 2:j] + " ")
            live.append(" ")
            mark()                                       # `$'\x62ash'`: the escapes spell what the walk reads raw
            add(cmd[i + 2:j])
            i = j + 1
            continue
        if c == "$" and i + 1 < n and (cmd[i + 1].isalnum() or cmd[i + 1] in EXPANSION_CHARS):
            mark()
            add(c, True)
            live.append(c)
            i += 1
            continue
        if c == "'":
            close = cmd.find("'", i + 1)
            # A quote left open is live: bash refuses the command anyway, and an open quote must not hide what follows.
            (inert if close != -1 else live).append(" " + cmd[i + 1:(n if close == -1 else close)] + " ")
            close = n if close == -1 else close
            live.append(" ")
            add(cmd[i + 1:close])
            i = close + 1
            continue
        if c == "#" and not s.word:
            nl = cmd.find("\n", i)
            i = n if nl == -1 else nl
            continue
        if c == '"':
            stack.append("D")
            live.append(c)
            s.word.append("")                            # a word has begun: a `#` after it is no comment
            i += 1
            continue
        if cmd.startswith("<<<", i):
            # A here-string is one operator: stepping one character would leave `<< x` at i+1, read as a heredoc whose
            # body (the next lines, a live post-review among them) went inert (j830 mutation S10).
            end_word()
            s.redir = True
            live.append("<<<")
            i += 3
            continue
        if cmd.startswith("<<", i):
            end_word()
            dash = cmd.startswith("<<-", i)
            j = i + 2 + dash
            while j < n and cmd[j] in " \t":
                j += 1
            k = j
            while k < n and cmd[k] not in WORD_END:
                k += 1
            raw = cmd[j:k]
            if raw[:1] in "'\"" and raw[-1:] != raw[:1]:
                close = cmd.find(raw[0], j + 1)          # a quoted delimiter holding a space
                k = n if close == -1 else close + 1
                raw = cmd[j:k]
            delim = raw.replace("'", "").replace('"', "").replace("\\", "")
            if delim:
                pending.append((delim, raw != delim, dash))
            live.append(cmd[i:k])
            i = k
            continue
        if c == "\n" and pending:
            separator()
            live.append(c)
            i += 1
            for delim, quoted, dash in pending:
                body_start = i
                while i < n:
                    nl = cmd.find("\n", i)
                    line_end = n if nl == -1 else nl
                    line = cmd[i:line_end]
                    # bash's own rule: the delimiter alone on its line, leading tabs only after <<- (review of #451, F10).
                    if (line.lstrip("\t") if dash else line) == delim:
                        (inert if quoted else live).append(" " + cmd[body_start:i] + " ")
                        i = line_end
                        break
                    i = line_end + 1
                else:
                    (inert if quoted else live).append(" " + cmd[body_start:n] + " ")
            pending.clear()
            continue
        if c in "<>" and cmd[i + 1:i + 2] != "(":
            # A redirection: its fd number (`2` of `2>/dev/null`) and its target are not command words. Dropped here,
            # not read as a command: the walk took `2` for the command and the real one for an argument (#631 F2).
            if s.word and "".join(s.uq).isdigit():
                s.clear_word()
            else:
                end_word()
            s.redir = True
            live.append(c)
            i += 1
            continue
        if c == "&" and (cmd[i - 1:i] in ("<", ">") or cmd[i + 1:i + 2] == ">") and cmd[i + 1:i + 2] != "&":
            end_word()                                  # `>&2`, `&>file`: part of a redirection, not a separator
            s.redir = True
            live.append(c)
            i += 1
            continue
        if c == "|" and cmd[i - 1:i] == ">":
            live.append(c)                              # `>|file`
            i += 1
            continue
        if c == "(" and s.uq and s.uq[-1] in "@+!?*":
            mark()                                      # `fabric-p@(r)`: an extglob, the shell picks the letters
        if top == "S" and c == "(":
            depth[-1] += 1
        elif top == "S" and c == ")":
            if depth[-1] == 0:
                close_sub("S")
                live.append(c)
                i += 1
                continue
            depth[-1] -= 1
        elif top == "B" and c == "`":
            close_sub("B")
            live.append(c)
            i += 1
            continue
        elif c == "`":
            open_sub("B")
            live.append(c)
            i += 1
            continue
        elif cmd.startswith("$(", i):
            open_sub("S")
            live.append("$(")
            i += 2
            continue
        if c in ";&|(\n" or (c == ")" and top == "N"):        # `x) cmd`: a case arm's command word follows
            separator()
        elif c in WORD_END:
            end_word()
        else:
            add(c, True)
        live.append(c)
        i += 1
    while len(states) > 1:                  # an unclosed `$(` or backtick: what it held is judged all the same
        separator()
        states.pop()
    separator()
    return "".join(live) + ("".join(inert) if runner else ""), dynamic


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
        spec.loader.exec_module(package)
    return importlib.import_module("fabric_cli.canonical")


def bare(cmd: str, canonical) -> bool:
    """The words before the one `<` are the post-review itself, its command word first: not a prefix canonical()
    reads through (`env`, `LC_ALL=C`), not a path, not quoted — none of those is what `Bash(fabric-pr *)` (or
    `Bash(fabric pr *)`) matches."""
    shape = BARE.fullmatch(cmd)
    words = shape.group(1).split() if shape else []
    read = canonical.canonical(words) if words else None
    return (read is not None and read[0] == COMMAND and read[1][:1] == [VERB]
            and words[0] in (COMMAND, canonical.DISPATCHER))


def refusal(cmd: str) -> str:
    """"" when the command passes, else the key of CAUSES it is refused for."""
    named = VERB in cmd
    # The trigger (header, COMMAND WORDS THE WALK CANNOT NAME): either word, or any text a command could read as input.
    if not (named or COMMAND in cmd or "<" in cmd):
        return ""
    canonical = canonical_module() if named else None
    if named and bare(cmd.strip(), canonical):
        return ""
    text, dynamic = live_text(cmd)
    if dynamic or not named:
        return dynamic
    last = text.rfind(VERB)                 # a run names the subcommand after the script: `grep post-review bin/fabric-pr` runs none
    if last == -1:
        return ""
    words = LIVE_WORD.findall(text, 0, last)
    # Every live word before the last `post-review` is asked whether it starts `fabric-pr`: a text walk, not a parse of
    # command positions (the header says why), so `echo fabric-pr post-review` is over-reported as it always was. By
    # its last part, so a path outside a `bin` (`./fabric-pr`, `/opt/x/fabric-pr`) stays the script it always was here.
    return "bare" if any((read := canonical.canonical([os.path.basename(words[k]), *words[k + 1:k + NAMING_WORDS]]))
                         is not None and read[0] == COMMAND for k in range(len(words))) else ""


def refused(cmd: str) -> bool:
    return bool(refusal(cmd))


def main() -> int:
    try:
        cmd = json.loads(sys.stdin.read())["tool_input"]["command"]
    except (ValueError, KeyError, TypeError):
        return 0
    try:
        cause = refusal(cmd) if isinstance(cmd, str) else ""
    except Exception:                       # a guard that cannot decide refuses: over-reporting costs a rephrase
        cause = "undecided"
    if cause:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": REASON + CAUSES[cause]}},
                         separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
