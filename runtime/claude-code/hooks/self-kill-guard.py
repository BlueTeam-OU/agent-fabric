#!/usr/bin/env python3
"""runtime/claude-code/hooks/self-kill-guard.py: a PreToolUse hook on Bash.

Refuses a command that kills processes chosen by a pattern
(`pkill -f PAT`, `pgrep -f PAT | xargs kill`, `kill $(pgrep -f PAT)`,
`killall -r PAT`) when PAT selects any process of the session's own tree:
its `claude` process (the nearest ancestor of this hook), the bash the
harness will run this very command in, and every process claude has
started — the harness's background tasks, its inbox watch, its servers.
And it refuses any kill whose target is a gzcoord-inbox process, by
pattern or by pid.

WHY. A session's claude process carries its opening prompt in argv, and the
prompt named the inbox watch's command. So `pgrep -f 'gzcoord-inbox
--follow' | xargs kill`, meant to clear a stale watcher, killed the session
that ran it: architect-cto-01, twice, on 2026-09-29; fabric-coordinator
earlier with a `pkill -f` pattern. Advice did not stop it; this does. The
launcher's prompt no longer names the command — and the kill still froze
sessions (python-dev-03 and the owner, 2026-10-13): every Bash call runs as
`bash -c '… eval '<the whole command>' …'`, so a pattern the command
spells matches the shell running it (pkill spares only itself), the call
never returns, and the session hangs; or it matches the harness's tracked
inbox watch. Neither is the claude process, so a guard of claude alone let
it through. An inbox watch never needs killing: it ends by itself at its
next delivery, and gzcoord-inbox itself refuses a second one.

THE SHELL. At PreToolUse the shell that will run the command does not exist
yet, so it is modelled: its command line as Claude Code writes it (seen
2026-10-13), the session's SessionStart env files inside it (the fabric's
export and sealing unset), the raw command beside it, generous on purpose;
its name bash.

TWO LAYERS. First a reading of the command: every argument of a pgrep or
pkill with -f, and killall -r's regexes, is matched against each process
of the tree's command line (or name, without -f), the modelled shell's,
and a model of an inbox watch's — generous on purpose, since a false deny
costs a rephrase. Then the ground truth: the same question put to pgrep
itself, list-only (pkill without its signals, killall as pgrep -x), against
the real processes and a stand-in carrying the modelled shell's command
line, and a deny when it names one of the tree, the stand-in or an inbox
watch. By pid it over-reports instead of reading bash's argument order:
in a command holding the word kill anywhere, every integer-looking token
is a candidate, refused when it is claude, of the tree, or an inbox watch
by its /proc command line; a negative `kill` operand (-1, a group) is
refused outright; an operand held in a variable or a substitution asks.
Seven review rounds on #69 and #70 each found a spelling a
re-implementation of procps's rules misread; procps does not misread
itself. The second layer only adds denials.

Output: a decision on stdout — deny when either layer says the tree or a
watch is selected, ask when a pattern is a variable or a command
substitution the hook cannot read — or nothing. Exit 0 always: input it
cannot read is passed, never blocked.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import signal
import subprocess
import time
import warnings
import sys

PREFIXES = {"timeout", "sudo", "env", "nohup", "nice", "xargs", "exec", "command", "builtin", "setsid", "stdbuf"}
KILL_TOOLS = {"pgrep", "pkill", "killall", "kill"}
# Words that open or continue a compound command before the command itself.
COMPOUND = {"{", "}", "!", "if", "then", "elif", "else", "while", "until", "do", "time", "coproc"}
# What a lifted $( … ), ` … ` or <( … ) leaves in its place: no real pattern
# contains it, so a pattern that does was built from a substitution.
SUBST = "__SELF_KILL_GUARD_SUBST__"
# A candidate judged against the process NAME rather than the command line.
NAME_PREFIX = "__NAME__:"
# killall -g: it kills the whole process group of what it names, which no
# pattern reading can see.
GROUP_MARK = "__GROUP__"
SESSION_NAME = "claude"   # own_claude() finds the ancestor by exactly this name
# The ground truth's whole budget: under the hook's 5 s timeout, so the ask
# after it is still reached (ninth round).
GROUND_TRUTH_BUDGET_S = 3.0
# Each prefix's own options that take a separate value. Per prefix, never
# merged: a flag that takes a value in one program is boolean in another
# (xargs -r, env -i, sudo -E), and a merged set read the kill after such a
# flag as its value and passed it (re-review of #69, N1).
VALUE_OPTIONS = {
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "sudo": {"-u", "--user", "-g", "--group", "-h", "--host", "-p", "--prompt", "-C", "--close-from",
             "-D", "--chdir", "-U", "--other-user", "-r", "--role", "-t", "--type", "-T", "--command-timeout",
             "-R", "--chroot"},
    "env": {"-u", "--unset", "-C", "--chdir", "-S", "--split-string", "-a", "--argv0"},
    "exec": {"-a"},
    "xargs": {"-I", "-L", "-n", "--max-args", "-P", "--max-procs", "-s", "--max-chars", "-d", "--delimiter",
              "-E", "-a", "--arg-file"},
    "nice": {"-n", "--adjustment"},
    "stdbuf": {"-i", "-o", "-e"},
}
KILLS = re.compile(r"\b(kill|pkill|killall|xargs\s+(?:-\S+\s+)*kill)\b")


def unquoted(command: str) -> str:
    """The command with every quote and backslash dropped: bash joins
    `k''ill`, `k"ill"`, `\\kill` into kill and `12''34`, `"12"34`, `12\\34`
    into 1234, which the raw text hides from a regex (round 3 of #242).
    A backslash-newline goes first, as bash drops it (`ki\\<NL>ll`); then
    the `$` of `$'…'` and `$"…"` and every brace, so `ki$'l'l` and
    `kill 4321{7,}` still show the word kill (round 4). Over-joins where
    bash would not; a false deny is a rephrase."""
    return re.sub(r"\$(?=['\"])|['\"\\{}]", "", command.replace("\\\n", ""))


def unevaluated(command: str) -> str | None:
    """The expansion a command that kills uses and this hook does not
    evaluate — ANSI-C or locale quoting, a backslash-newline, a brace
    expansion — or None. Chasing each spelling took four review rounds on
    #242; what is left asks instead of passing (round 4).

    Judged on the text a shell runs: a here-document's body is data unless
    a shell reads it (drop_heredoc_bodies, as kill detection does), and kill,
    pkill or killall count only as command words (KILL_TOOL_WORD), so an edit script's
    `os.kill`, a `self_kill` file name or a Python dict's braces no longer
    ask (two sessions stopped on it, 2026-10-15)."""
    command = drop_heredoc_bodies(command)
    if not KILL_TOOL_WORD.search(unquoted(command)):
        return None
    for mark, what in (("$'", "ANSI-C quoting $'…'"), ('$"', 'locale quoting $"…"'),
                       ("\\\n", "a backslash-newline")):
        if mark in command:
            return what
    if re.search(r"\{[^{}]*(,|\.\.)[^{}]*\}", command):
        return "a brace expansion {…}"
    if len(pid_candidates(command)) > MAX_PIDS:
        return f"more than {MAX_PIDS} numbers"
    return None


def kills(command: str) -> bool:
    """Whether the command kills at all, read in the raw text and with its
    quotes dropped."""
    return bool(KILLS.search(command) or KILLS.search(unquoted(command)))


def own_claude_cmdline(proc: str = "/proc", pid: int | None = None) -> str | None:
    """The command line of the nearest ancestor whose command is `claude`."""
    return own_claude(proc, pid)[1]


def own_claude(proc: str = "/proc", pid: int | None = None) -> tuple[int | None, str | None]:
    """(pid, command line) of the nearest ancestor whose command is `claude`."""
    p = pid or os.getpid()
    for _ in range(64):
        try:
            with open(f"{proc}/{p}/stat", encoding="utf-8", errors="replace") as fh:
                raw = fh.read()
            comm = raw[raw.index("(") + 1:raw.rindex(")")]
            ppid = int(raw[raw.rindex(")") + 2:].split()[1])
        except (OSError, ValueError, IndexError):
            return None, None
        if comm == "claude":
            try:
                with open(f"{proc}/{p}/cmdline", "rb") as fh:
                    return p, fh.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
            except OSError:
                return p, None
        if ppid <= 1:
            return None, None
        p = ppid
    return None, None


def kill_after_prefixes(words: list[str]) -> list[str]:
    """The words from the first killing tool behind a chain of prefixes,
    or [] when there is none: a value of the current prefix's option is
    skipped, a prefix switches the option set, anything else is passed."""
    takes: set[str] = set()
    skip = False
    for i, w in enumerate(words):
        name = os.path.basename(w)
        if skip:
            skip = False
        elif name in PREFIXES:
            takes = VALUE_OPTIONS.get(name, set())
        elif w in takes:
            skip = True
        elif name in KILL_TOOLS or name in NESTED:
            return words[i:]
    return []


# A command whose argument is itself a command line: `bash -c '…'`,
# `sudo sh -c "…"`, `eval '…'`. Every word it is given, and all of them
# joined, is judged as a command (reviews of #242: C3, then K2). Locating
# the -c operand modelled bash's option order and missed `bash -o pipefail
# -c …` and `bash -c -- …`; a word that is no command yields nothing, and
# a false deny costs a rephrase. A payload in a variable is not readable.
NESTED = {"bash", "sh", "zsh", "dash", "ksh", "eval"}
NESTED_DEPTH = 4


SHELLS = re.compile(r"(?:^|[\s|;&(/])(?:bash|sh|zsh|dash|ksh|eval|source|\.)(?=$|[\s;&|)])")


def drop_heredoc_bodies(text: str) -> str:
    """A here-document's body is data for the command that reads it — a
    commit message quoting a kill is not a kill — so it is dropped, up to
    its delimiter line. Unless a shell reads it (`bash <<EOF`, `cat <<EOF |
    sh`, eval): then the body is code, and is kept to be judged. The
    delimiter may be quoted; <<- strips leading tabs. <<< is a here-string,
    not a here-document."""
    lines, out, i = text.split("\n"), [], 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        delims = [(m.group(1) == "-", m.group(2) or m.group(3) or m.group(4))
                  for m in re.finditer(r"(?<!<)<<(-?)\s*(?:'([^']+)'|\"([^\"]+)\"|\\?([A-Za-z_][A-Za-z0-9_]*))", line)]
        if not delims or SHELLS.search(line):
            continue
        for strip_tabs, delim in delims:
            # Dropped only up to a delimiter line that is there: a `<<` that
            # is no here-document (in $((1<<n)), a quote, a comment) finds
            # none, and then nothing is dropped (review of #70, eighth round).
            end = next((j for j in range(i, len(lines))
                        if (lines[j].lstrip("\t") if strip_tabs else lines[j]) == delim), None)
            if end is not None:
                i = end + 1
    return "\n".join(out)


def strip_non_arguments(text: str) -> str:
    """What bash does not pass to a command, removed outside quotes before
    the words are split: a comment (an unquoted '#' that starts a word, to
    the end of the line; a '#' inside a word is literal), and the fd number
    written against a redirection (`2>`, `1>&`). Quotes are tracked the way
    the shell does: nothing is special inside '…', and only a backslash is
    inside "…"."""
    out, i, n, quote = [], 0, len(text), None
    # A ')' that closes a $( … ) or $(( … )) ends a word, and a '#' after it
    # is literal (`$((1+1))#`); a ')' that closes a subshell is an operator,
    # and a '#' after it starts a comment (review of #70, the seventh
    # round). The depth of open substitutions tells the two apart.
    subst_depth, closed_subst = 0, False
    while i < n:
        c = text[i]
        if quote == "'":
            quote = None if c == "'" else quote
        elif quote == '"':
            if c == "\\" and i + 1 < n:
                out.append(c)
                i += 1
                c = text[i]
            elif c == '"':
                quote = None
        elif c == "\\" and i + 1 < n:
            out.append(c)
            i += 1
            c = text[i]
        elif c in "'\"":
            quote = c
        elif c == "$" and i + 1 < n and text[i + 1] == "(":
            subst_depth += 1
            out.append("$(")
            i += 2
            continue
        elif c == "(" and subst_depth:
            subst_depth += 1
        elif c == ")":
            closed_subst = subst_depth > 0
            subst_depth = max(0, subst_depth - 1)
        elif c == "#" and (i == 0 or text[i - 1] in " \t\n;&|(" or (text[i - 1] == ")" and not closed_subst)):
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif c.isdigit() and (i == 0 or text[i - 1] in " \t\n;&|()"):
            j = i
            while j < n and text[j].isdigit():
                j += 1
            if j < n and text[j] in "<>":
                i = j          # the fd: the redirection follows, and goes below
                continue
        out.append(c)
        i += 1
    return "".join(out)


def segments(piece: str) -> list[list[str]]:
    """The simple commands of a command line, each as its words, split on
    |, ;, &, newlines and a subshell's parentheses OUTSIDE quotes (splitting
    the raw text first made a quoted argument that mentions a kill a
    command of its own). A redirection — any operator holding < or >, `>|`
    and `)>` included — and the word after it are not arguments."""
    lex = shlex.shlex(strip_non_arguments(piece), posix=True, punctuation_chars="();<>|&\n")
    lex.commenters = ""
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    out, cur = [], []
    try:
        toks = list(lex)
    except ValueError:   # an unbalanced quote: the plain words, as before
        return [seg.split() for seg in re.split(r"[|;&\n]+", piece)]
    skip = False
    for tok in toks:
        if skip:
            skip = False
            continue
        if tok and set(tok) <= set("|;&\n()<>"):
            if any(ch in tok for ch in "|;\n()") and not (set(tok) <= set("<>&|") and ("<" in tok or ">" in tok)) \
                    or tok in ("&", "&&"):
                out.append(cur)
                cur = []
            if "<" in tok or ">" in tok:
                skip = True    # the redirection's target: a file, or the fd of >&1
            continue
        cur.append(tok)
    out.append(cur)
    return out


def kill_commands(command: str) -> list[list[str]]:
    """Each pgrep, pkill or killall in a command that kills at all, as its
    words from the tool on."""
    if not kills(command):
        return []
    return [w for w in tool_commands(command) if os.path.basename(w[0]) in ("pgrep", "pkill", "killall")]


PLACEHOLDER = re.compile(re.escape(SUBST) + r"(\d+)_")
# What a pid operand may be without being read: the pid of the job this
# very command last started, a process the command itself owns.
OWN_JOB = {"$!", "${!}"}


# The word kill as a command anywhere in the text (`/bin/kill`, `command
# kill`, inside any quoting or nested shell), not pkill, killall or a
# hyphenated name; and an integer-looking token, its sign dropped.
KILL_WORD = re.compile(r"(?<![\w.-])kill(?![\w.-])")
# kill, pkill or killall as a command word: what unevaluated() asks about.
KILL_TOOL_WORD = re.compile(r"(?<![\w.-])(?:kill|pkill|killall)(?![\w.-])")
INTEGER = re.compile(r"(?<![\w.])[+-]?(\d{1,10})(?![\w.])")
MAX_PIDS = 512


def pid_candidates(command: str) -> list[int]:
    """Every integer-looking token, uncapped, in a command holding the word
    kill as bash reads it — in the raw text, with the quotes dropped, or
    as a command's unquoted word (`k''ill`, `\\kill`). Candidates come from
    every form: the raw text, the text with quotes dropped, and each
    unquoted word of every command read, nested ones included — `12''34`
    is 1234 to bash and 12, 34 to the raw text."""
    flat, commands = unquoted(command), tool_commands(command)
    if not (KILL_WORD.search(command) or KILL_WORD.search(flat)
            or any(os.path.basename(w[0]) == "kill" for w in commands)):
        return []
    texts = [command, flat, *(word for words in commands for word in words)]
    return list(dict.fromkeys(int(m.group(1)) for t in texts for m in INTEGER.finditer(t)))


def kill_operands(command: str) -> tuple[list[int], list[str]]:
    """What the command may kill by pid: (every integer-looking token in a
    command that holds the word kill anywhere; the `kill` operands it
    cannot read). Reading bash's argument order let spellings through
    twice — a sticky `-0` before `-s TERM`, a payload after `bash -o
    pipefail` (round 2 of #242) — so every number counts, signals and
    values included: a number that is a protected pid by chance is a false
    deny, a rephrase. Unreadable is a variable (`$pid`, `$PPID`, `$$`) or a
    substitution other than one plain pgrep, whose answer the ground truth
    asks list-only; `$!` is the command's own job."""
    pids = pid_candidates(command)[:MAX_PIDS]
    if not pids and not KILL_WORD.search(unquoted(command)):
        return [], []
    pieces, held = lift(command), []
    for words in tool_commands(command):
        if os.path.basename(words[0]) != "kill":
            continue
        for w in words[1:]:
            m = PLACEHOLDER.fullmatch(w)
            if w in OWN_JOB or (m and _plain_pgrep(pieces[int(m.group(1))])):
                continue
            if "$" in w or "`" in w or SUBST in w:
                held.append(PLACEHOLDER.sub("$(…)", w))
    return pids, held


def kill_groups(command: str) -> list[str]:
    """The negative operands of each `kill`: `-1` is every process the
    user may signal, `-N` a whole process group — either can hold the
    session. A negative number is read as a signal only as the first
    argument, and `-1` never (round 2 of #242). A 0 operand is the
    caller's own process group, which holds the shell running this very
    command (round 3). Every 0 is refused, also one that may be a
    signal value (`kill -s 0 <pid>`): bash also reads `kill <pid> -s 0`
    as group 0, and telling the two apart is the parsing this guard
    gave up (round 5); a false deny costs a rephrase (`kill -0 <pid>`)."""
    out = []
    for words in tool_commands(command):
        if os.path.basename(words[0]) != "kill":
            continue
        for i, w in enumerate(words[1:]):
            if (re.fullmatch(r"-\d+", w) and (w == "-1" or i > 0)) or re.fullmatch(r"\+?0+", w):
                out.append(w)
    return out


def kill_pids(command: str) -> list[int]:
    """The literal pids a `kill` in the command names (kill_operands)."""
    return kill_operands(command)[0]


def _plain_pgrep(piece: str) -> bool:
    """A substitution that is one pgrep with literal arguments: what it
    prints is what the ground truth asks, list-only."""
    cmds = [s for s in segments(piece) if s]
    return (len(cmds) == 1 and os.path.basename(cmds[0][0]) == "pgrep"
            and pgrep_argvs(cmds[0]) is not None)


def lift(command: str) -> list[str]:
    """The command's substitutions, then what is left of it: each $( … )
    (and `…`) is a command of its own, lifted out innermost first, and a
    numbered placeholder word left behind, so `pgrep -u "$(id -un)" -f P`
    keeps its pattern, `kill $(pgrep -f P)` yields the pgrep, and a kill's
    operand can say which substitution it reads. Here-document bodies
    first: a substitution inside one is data too."""
    pieces, rest = [], drop_heredoc_bodies(command)
    while True:
        m = re.search(r"[$<>]\(([^()]*)\)|`([^`]*)`", rest)
        if not m:
            break
        rest = rest[:m.start()] + f"{SUBST}{len(pieces)}_" + rest[m.end():]
        pieces.append(m.group(1) if m.group(1) is not None else m.group(2))
    return pieces + [rest]


def tool_commands(command: str) -> list[list[str]]:
    """Each killing tool (pgrep, pkill, killall, kill) in a command, as its
    words from the tool on: substitutions lifted, here-document bodies
    dropped, segments split, compound keywords, assignments and prefixes
    walked past; a nested shell's literal payload judged as a command of
    its own. The payload is not lifted again: lift() ignores quotes, so its
    substitutions were lifted with the outer command's, and their numbers
    stay the outer ones that kill_operands() reads."""
    return _tool_commands(lift(command), 0)


def _tool_commands(pieces: list[str], depth: int) -> list[list[str]]:
    out = []
    for words in (seg for piece in pieces for seg in segments(piece)):
        if not words:
            continue
        # A kill behind a prefix is still the kill (review of #68):
        # `timeout 5 pkill -f P`, sudo, env, nohup, nice, xargs, exec, and
        # prefixes nested in each other. Walked a word at a time: each
        # prefix met makes ITS options the ones whose next word is a value,
        # so `sudo timeout -s kill 5 pkill -f P` skips timeout's signal and
        # finds pkill. Choosing the option set once, from the outer prefix
        # or merged across all, let a kill through three times (reviews
        # of #69: F3, N1, M1).
        # A compound command's keywords and a leading assignment are not the
        # command: `{ pkill …; }`, `then pkill …`, `x=1 pkill …` (re-review
        # of #70, pre-existing).
        while words and (words[0] in COMPOUND or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[0])):
            words = words[1:]
        if not words:
            continue
        if os.path.basename(words[0]) in PREFIXES:
            words = kill_after_prefixes(words)
            if not words:
                continue
        if os.path.basename(words[0]) in NESTED:
            if depth < NESTED_DEPTH and len(words) > 1:
                texts = list(dict.fromkeys([" ".join(words[1:]), *words[1:]]))
                out += _tool_commands([drop_heredoc_bodies(t) for t in texts], depth + 1)
        elif os.path.basename(words[0]) in KILL_TOOLS:
            out.append(words)
    return out


_VALUE_SHORT = set("dgGOPstuUFrq")
_VALUE_LONG = ("--delimiter", "--pgroup", "--group", "--older", "--parent", "--session", "--signal", "--terminal",
               "--euid", "--uid", "--pidfile", "--runstates", "--cgroup", "--ns", "--nslist", "--queue")


def _cluster(w: str) -> tuple[str, str | None, bool]:
    """A short-option cluster read as getopt reads it: (the letters that
    take no value, the value-taking letter or None, whether its value is
    the NEXT word). The first value-taking letter ends the cluster; what
    follows it in the word is its glued value (`-uuser`: u, value "user").
    Judging a cluster by its last letter swallowed the pattern after
    `-uuser` (tenth round)."""
    letters = w[1:]
    for k, ch in enumerate(letters):
        if ch in _VALUE_SHORT:
            return letters[:k], ch, k == len(letters) - 1
    return letters, None, False


def _name_candidates(args: list[str]) -> list[str]:
    out, it = [], iter(args)
    for w in it:
        if w == "--":
            out += list(it)
        elif w.startswith("--") and len(w) > 2:
            if "=" not in w and _long(w, *_VALUE_LONG):
                next(it, None)
        elif w.startswith("-") and w != "-":
            if not _is_signal_option(w) and _cluster(w)[2]:
                next(it, None)
        else:
            out.append(w)
    return out


def kill_patterns(command: str) -> list[str]:
    """Every candidate pattern the command selects processes by for a kill:
    each argument of -f/--full's pgrep or pkill, and killall -r's regexes,
    in a command that kills at all."""
    out = []
    for words in kill_commands(command):
        tool = os.path.basename(words[0])
        if tool in ("pgrep", "pkill"):
            # EVERY word that is not an option is a candidate, wherever it
            # stands — an option's value included. procps's getopt takes
            # options after the pattern (`pkill claude-fable -f`), and
            # every exact reading of options tried — the pattern's place,
            # then which options take a value — let a spelling through
            # (`-TSTP -f`: a signal whose last letter looked like a value
            # option swallowed the -f). Six review rounds on #69 and #70.
            # A value that matches the session is a false deny, the safe
            # side. -f counts wherever it stands, alone or in a cluster.
            full, cands, rest_args = False, [], False
            for w in words[1:]:
                # -f counts even after a `--`: getopt may have taken that
                # `--` as an option's value (`pgrep -d -- -f P`), and a
                # candidate too many is the safe side (seventh round).
                # getopt_long takes a unique prefix: --fu, --ful are --full.
                if w.startswith("-") and w not in ("-", "--"):
                    name = w.split("=", 1)[0]
                    if name.startswith("--"):
                        full = full or (len(name) > 2 and "--full".startswith(name))
                    else:
                        full = full or "f" in w[1:]
                if rest_args or not w.startswith("-") or w == "-":
                    cands.append(w)
                elif w == "--":
                    rest_args = True
            if full:
                out += cands
            else:
                # A value of a known value-taking option is no name pattern:
                # against the short name "claude", `-u a` matched (ninth
                # round). The command-line reading above keeps every word.
                cands = _name_candidates(words[1:])
                # Without -f the pattern is matched against the process
                # NAME — the session's is `claude` — so `pkill -c claude`
                # kills it (eighth round). Marked so verdict() judges it
                # against the name, not the command line.
                out += [NAME_PREFIX + c for c in cands]
        elif tool == "killall":
            opts = [w for w in words[1:] if w.startswith("-") and w != "-"]
            regex = any(w == "--regexp" or _long(w, "--regexp") or (not w.startswith("--") and "r" in w[1:])
                        for w in opts if not _is_signal_option(w))
            names = [w for w in words[1:] if not w.startswith("-")]
            # killall matches the process name: exactly, or as a regex with
            # -r (in any cluster, or a prefix of --regexp); a path is its
            # file's basename, near enough to judge.
            out += [NAME_PREFIX + (n if regex else "^" + re.escape(os.path.basename(n)) + "$") for n in names]
            if any(w == "--process-group" or _long(w, "--process-group") or (not w.startswith("--") and "g" in w[1:])
                   for w in opts if not _is_signal_option(w)):
                out.append(GROUP_MARK)
    return out


CLAUDE_LABEL = "this session's own claude process (its command line carries the opening prompt)"
SHELL_LABEL = ("this session's own shell (the bash this very command runs in: the call would never return "
               "and the session would freeze)")
WATCH_LABEL = "the harness's inbox watch (gzcoord-inbox)"
INBOX = "gzcoord-inbox"
# The shell the harness runs a Bash call in, as Claude Code wrote it on
# 2026-10-13: the snapshot, then the session's env files (shell_prefix),
# then the harness's own guards, then the command — its single quotes
# escaped the way the harness escapes them — then the cwd capture.
SHELL_SOURCE = "/bin/bash -c source /home/login/.claude/shell-snapshots/snapshot-bash.sh 2>/dev/null || true && "
SHELL_GUARDS = (": && shopt -u extglob 2>/dev/null || true && { \\builtin unalias -- 'unsetenv'; "
                "\\builtin unset -f -- 'unsetenv'; } >/dev/null 2>&1 || true && eval '")
SHELL_HEAD = SHELL_SOURCE + SHELL_GUARDS
SHELL_TAIL = "' < /dev/null && pwd -P >| /tmp/claude-cwd"
HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))


def shell_prefix(session_id: str | None) -> str:
    """What the harness puts between the snapshot and its guards: the
    session's SessionStart env files, in order (the fabric's own:
    `export AGENT_FABRIC_ROOT=…` and session-start.py's sealing unset).
    Without them, the fabric's lines rebuilt from session-start.py; with
    neither, nothing. A pattern matching only these words still kills the
    shell (review of #242)."""
    if session_id and re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9._-]*", session_id):
        root = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
        d = os.path.join(root, "session-env", session_id)
        try:
            names = [n for n in os.listdir(d) if re.fullmatch(r"sessionstart-hook-\d+\.sh", n)]
            parts = []
            for n in sorted(names, key=lambda n: int(re.sub(r"\D", "", n))):
                with open(os.path.join(d, n), encoding="utf-8", errors="replace") as fh:
                    parts.append(fh.read(65536))
            if parts:
                return "".join(parts)
        except OSError:
            pass
    try:
        spec = importlib.util.spec_from_file_location("fabric_session_start", os.path.join(HOOKS_DIR, "session-start.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        root = os.environ.get("AGENT_FABRIC_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(HOOKS_DIR)))
        return f"export AGENT_FABRIC_ROOT={root}\nunset {' '.join(mod.HARNESS_CREDENTIALS)}  {mod.SHELL_SEAL}\n"
    except Exception:  # noqa: BLE001 - a model that cannot be built is a shorter model, never a failure
        return ""
# An inbox watch as the fleet runs it — the pinned interpreter, the link in
# ~/.local/bin, each mode — and by the script's own name and its shell. A
# real watch these miss is still asked of pgrep by the ground truth.
INBOX_MODELS = tuple(
    [("fabric-python", f"/usr/local/bin/fabric-python -I /home/login/.local/bin/{INBOX} {mode}")
     for mode in ("--until-delivery", "--follow", "--wait")]
    + [(INBOX, f"{INBOX} --until-delivery"), ("bash", f"{SHELL_HEAD}{INBOX} --until-delivery{SHELL_TAIL}")])

# (what a deny message calls it, process name, command line, is an inbox watch)
Target = tuple[str, str, str, bool]
Tree = dict[int, tuple[str, list[str]]]   # pid -> (name, argv)


def shell_texts(command: str, prefix: str = "") -> list[str]:
    """The modelled command line of the shell that will run `command`, and
    the bare command beside it in case the harness's quoting changes."""
    return [SHELL_SOURCE + prefix + SHELL_GUARDS + command.replace("'", "'\"'\"'") + SHELL_TAIL, command]


def is_inbox(argv: list[str]) -> bool:
    """An inbox watch: any word of its argv is gzcoord-inbox, wherever it
    stands; or it is the harness's shell whose command the watch is.

    Any word, because each narrower reading missed a spelling: the first
    four words missed `python3 -I -u -B -X utf8 <path>` (C4), and a walk of
    the interpreter's options missed `timeout 600 <path>`, nohup, setsid,
    `sh <path>` and `--check-hash-based-pycs default` (round 2 of #242,
    N1). The walk could only ever answer yes where this does, so it is
    gone. An editor open on the script is a false deny, a rephrase."""
    return any(os.path.basename(a) == INBOX for a in argv) or f"eval '{INBOX}" in " ".join(argv)


def label_of(pid: int, comm: str, argv: list[str], in_tree: bool = True) -> tuple[str, bool]:
    """What a deny message calls a process, and whether it is an inbox
    watch: by pid and process name only. Its argv never reaches the
    message, which the session's transcript keeps: a command line can
    carry a token (review of #242, C6)."""
    if is_inbox(argv):
        return (f"the harness's inbox watch (pid {pid}, {comm})" if in_tree
                else f"an inbox watch (pid {pid}, {comm})"), True
    return f"a process of this session's tree (pid {pid}, {comm})", False


def read_comm(pid: int, proc: str = "/proc") -> str:
    try:
        with open(f"{proc}/{pid}/comm", encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    except OSError:
        return "?"


def targets(command: str, cmdline: str | None, tree: Tree | None, shell: bool, prefix: str = "") -> list[Target]:
    """What the first layer judges a pattern against beyond the claude
    process: the modelled shell, each process of the tree, and the inbox
    watch's models — those whatever the session, since a watch never
    needs a kill."""
    out: list[Target] = []
    if shell:
        out += [(SHELL_LABEL, "bash", t, False) for t in shell_texts(command, prefix)]
    for p, (comm, argv) in (tree or {}).items():
        label, inbox = label_of(p, comm, argv)
        out.append((label, comm, " ".join(argv), inbox))
    out += [(WATCH_LABEL if cmdline else f"an inbox watch ({INBOX})", name, text, True)
            for name, text in INBOX_MODELS]
    return out


def _matches(pat: str, target: str) -> bool:
    try:
        with warnings.catch_warnings():
            # procps's ERE ([[:digit:]]) makes Python warn of a nested
            # set; a hook's stderr reaches every session.
            warnings.simplefilter("ignore")
            return re.search(pat, target) is not None
    # A repeat count past sre's limit (`a{99999999999}`) overflows, a deep
    # nesting recurses: neither is a reason to exit non-zero.
    except (re.error, OverflowError, RecursionError):
        return pat in target


def unresolved(pat: str) -> bool:
    """A pattern holding a variable or a command substitution: its text is
    not what pgrep will be given, so it is never matched as written."""
    return bool(UNEXPANDED.search(pat)) or SUBST in pat


def hits(command: str, tgts: list[Target]) -> list[tuple[str, str, bool]]:
    """(pattern, label, is an inbox watch) for each target a kill pattern
    of the command selects: a -f pattern judged against the command line,
    any other against the process name. An unresolved pattern takes no
    part: `"$PAT["` is an invalid regex whose substring fallback denied
    before the ask could say why (review of #242, C5); it asks instead."""
    out = []
    for pat in kill_patterns(command):
        if pat == GROUP_MARK or unresolved(pat):
            continue
        by_name = pat.startswith(NAME_PREFIX)
        pat = pat[len(NAME_PREFIX):] if by_name else pat
        out += [(pat, label, inbox) for label, name, text, inbox in tgts if _matches(pat, name if by_name else text)]
    return out


def message(found: list[tuple[str, bool]], pats: list[str] | None = None) -> str:
    """One line: what the command would kill, and what to do instead."""
    what = " and ".join(dict.fromkeys(label for label, _ in found))
    by = f" (pattern {', '.join(repr(p) for p in dict.fromkeys(pats))})" if pats else ""
    if any(inbox for _, inbox in found):
        return (f"This command would kill {what}{by}. Never kill an inbox watch: it ends by itself at its next "
                "delivery, and gzcoord-inbox itself refuses a second watch, so there is nothing to kill.")
    if all(label == SHELL_LABEL for label, _ in found):
        return (f"This command would kill {what}{by}. Select by the exact pid of a process you started "
                "(kill <pid>), never by a -f pattern or a name.")
    return (f"This command would kill {what}{by}. A background task of this session stops with TaskStop or "
            "ends by itself; kill by exact pid only a process outside this session's tree, never by a pattern.")


def verdict(command: str, cmdline: str | None) -> str | None:
    """The deny message when a kill pattern matches the session's own
    claude process: its command line, or its name without -f."""
    if not cmdline:
        return None
    found = hits(command, [(CLAUDE_LABEL, SESSION_NAME, cmdline, False)])
    return message([(label, inbox) for _, label, inbox in found], [p for p, _, _ in found]) if found else None


SIGNAL_NAMES = {sig.name[3:] for sig in signal.Signals} | {"IOT", "CLD", "POLL"}


def _is_signal_option(w: str) -> bool:
    """pkill's `-<sig>`: a number or a signal name, any case, SIG optional
    (procps's signal_option). pgrep has no such option."""
    m = re.fullmatch(r"-(\d+|(?:SIG)?([A-Za-z]+[0-9+-]*))", w, re.I)
    if not m:
        return False
    name = (m.group(2) or "").upper()
    return m.group(1).isdigit() or name in SIGNAL_NAMES or name.startswith("RTMIN") or name.startswith("RTMAX")


def _long(w: str, *names: str) -> bool:
    """`w` is one of these long options, or a unique prefix getopt takes."""
    name = w.split("=", 1)[0]
    return len(name) > 2 and any(n.startswith(name) for n in names)


# killall's options the translation understands; any other — a cluster, a
# process group (-g), a user or an age — and it steps aside.
_KILLALL_KNOWN = {"-r", "--regexp", "-I", "--ignore-case", "-q", "--quiet", "-v", "--verbose", "-e", "--exact",
                  "-w", "--wait"}


def _without_output_options(args: list[str]) -> list[str]:
    """The arguments without -c/--count and -d/--delimiter (and -d's value,
    apart or glued): they change what pgrep PRINTS, never what it selects,
    so the list-only question drops them and reads plain pids (ninth
    round: stepping aside on them lost a denial)."""
    out, it = [], iter(args)
    for w in it:
        if w == "--":
            out += [w, *it]      # after it, every word is a pattern, untouched
        elif w.startswith("--") and len(w) > 2:
            if _long(w, "--count"):
                continue
            if _long(w, "--delimiter"):
                if "=" not in w:
                    next(it, None)
                continue
            out.append(w)
        elif w.startswith("-") and w != "-" and not _is_signal_option(w):
            plain, opt, next_is_value = _cluster(w)
            kept = plain.replace("c", "")
            if opt == "d":
                if next_is_value:
                    next(it, None)   # -d's value is the next word, dropped with it
            elif opt:
                kept += w[1 + len(plain):]   # the value option and its glued value, intact
            if kept:
                out.append("-" + kept)
            if opt and opt != "d" and next_is_value:
                out.append(next(it, ""))     # its value, intact
        else:
            out.append(w)
    return out


def pgrep_argvs(words: list[str]) -> list[list[str]] | None:
    """The list-only pgrep calls that select what this kill command would:
    pgrep as it is; pkill without its signal options; `killall NAME` as
    `pgrep -x NAME` per name, `killall -r RE` as `pgrep RE`; -c and -d,
    which change only what pgrep prints, are removed. None — the first
    layer stands — when a word is not literal, or when killall's spelling
    is not one the translation is sure of (a cluster, -g, a path as a
    name): an answer that does not mean "these pids" must not read as "not
    selected" (review of #70, eighth and ninth rounds)."""
    tool, args = os.path.basename(words[0]), words[1:]
    if any("$" in w or "`" in w or SUBST in w for w in args):
        return None
    if tool in ("pgrep", "pkill"):
        return [["pgrep", *_without_output_options([w for w in args if tool == "pgrep" or not _is_signal_option(w)])]]
    names, it = [], iter(args)
    regex = icase = False
    for w in it:
        if w in ("-s", "--signal"):
            next(it, None)
        elif w.startswith("--signal=") or _is_signal_option(w):
            continue
        elif w.startswith("-") and w != "-":
            if w not in _KILLALL_KNOWN:
                return None
            regex = regex or w in ("-r", "--regexp")
            icase = icase or w in ("-I", "--ignore-case")
        elif "/" in w:
            return None
        else:
            names.append(w)
    return [["pgrep", *(["-i"] if icase else []), *([] if regex else ["-x"]), n] for n in names] or None


def listed(argv: list[str], timeout: float = 2.0) -> set[int] | None:
    """The pids procps itself names, asked this list-only question; an
    empty set when it names none. None when it could not answer (an option
    pgrep refuses, no pgrep, a timeout): then the checks above are what
    stands."""
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode == 1:
        return set()
    if r.returncode != 0:
        return None
    # -l and -a print the name or command line after the pid: the first
    # word of each line is the pid.
    return {int(line.split()[0]) for line in r.stdout.splitlines() if line.split() and line.split()[0].isdigit()}


def selects(argv: list[str], pid: int, timeout: float = 2.0) -> bool | None:
    """Whether procps, asked this list-only question, names `pid`."""
    got = listed(argv, timeout)
    return None if got is None else pid in got


def read_argv(pid: int, proc: str = "/proc") -> list[str]:
    try:
        with open(f"{proc}/{pid}/cmdline", "rb") as fh:
            return [a.decode("utf-8", "replace") for a in fh.read().split(b"\0") if a]
    except OSError:
        return []


def session_tree(root: int, proc: str = "/proc", me: int | None = None) -> Tree:
    """Every descendant of the session's claude process, as (name, argv),
    except this hook, what it started and the shells between it and
    claude: those are gone when the command runs. Read only when the
    command kills at all."""
    me = me or os.getpid()
    ppid_of: dict[int, int] = {}
    comm_of: dict[int, str] = {}
    try:
        entries = os.listdir(proc)
    except OSError:
        return {}
    for d in entries:
        if not d.isdigit():
            continue
        try:
            with open(f"{proc}/{d}/stat", encoding="utf-8", errors="replace") as fh:
                raw = fh.read()
            comm_of[int(d)] = raw[raw.index("(") + 1:raw.rindex(")")]
            ppid_of[int(d)] = int(raw[raw.rindex(")") + 2:].split()[1])
        except (OSError, ValueError, IndexError):
            continue
    children: dict[int, list[int]] = {}
    for p, pp in ppid_of.items():
        children.setdefault(pp, []).append(p)

    def below(p: int) -> set[int]:
        seen, todo = set(), list(children.get(p, []))
        while todo:
            c = todo.pop()
            if c not in seen:
                seen.add(c)
                todo += children.get(c, [])
        return seen

    drop, p = {me} | below(me), ppid_of.get(me)
    while p and p != root and p not in drop:
        drop.add(p)
        p = ppid_of.get(p)
    return {p: (comm_of[p], read_argv(p, proc)) for p in below(root) - drop}


def _stand_in(command: str, prefix: str = "") -> subprocess.Popen | None:
    """A process carrying the modelled shell's command line, for pgrep to
    be asked about: the real shell does not exist yet. Its program is
    sleep, so nothing of the command ever runs."""
    try:
        return subprocess.Popen([shell_texts(command, prefix)[0].replace("\0", " "), "30"], executable="/bin/sleep",
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, ValueError):
        return None


def ground_truth(command: str, pid: int | None, tree: Tree | None = None,
                 shell: bool = False, prefix: str = "") -> list[tuple[str, bool]] | bool | None:
    """What a kill in the command would select of the session — its
    claude process, its tree, its shell's stand-in — or of any inbox watch,
    as procps answers it: a list of (label, is an inbox watch); False when
    every kill was asked and none would; None when one could not be asked.
    Seven review rounds on #69 and #70 each found a spelling that a
    re-implementation of procps's option and pattern rules misread (the
    owner chose this, 2026-09-30): the tool that will do the matching is
    asked instead. Only pgrep ever runs here, never the kill."""
    known: dict[int, tuple[str, bool]] = {p: label_of(p, comm, argv) for p, (comm, argv) in (tree or {}).items()}
    if pid:
        known[pid] = (CLAUDE_LABEL, False)
    # Every pgrep in a command that kills at all: recognising which pgrep's
    # output a kill reads (`| xargs kill`, `kill $(…)`) missed a loop and a
    # variable (ninth round); a listing pgrep beside a kill word is a false
    # deny, the safe side.
    deadline = time.monotonic() + GROUND_TRUTH_BUDGET_S
    answer: bool | None = False
    stand_in = None
    try:
        for words in kill_commands(command):
            argvs = pgrep_argvs(words)
            if argvs is None:
                answer = None
                continue
            if shell and stand_in is None:
                stand_in = _stand_in(command, prefix)
                if stand_in:
                    known[stand_in.pid] = (SHELL_LABEL, False)
            for argv in argvs:
                left = deadline - time.monotonic()
                if left <= 0:
                    return None
                got = listed(argv, min(2.0, left))
                if got is None:
                    answer = None
                    continue
                # The stand-in's name is sleep, not the shell's bash: it
                # answers only a question asked of command lines (-f).
                full = any(_long(w, "--full") if w.startswith("--") else w.startswith("-") and "f" in w[1:]
                           for w in argv[1:])
                found = [known[p] for p in sorted(got)
                         if p in known and (full or not stand_in or p != stand_in.pid)]
                found += [label_of(p, read_comm(p), argv_p, in_tree=False) for p in sorted(got)
                          if p not in known and is_inbox(argv_p := read_argv(p))]
                if found:
                    return found
    finally:
        if stand_in:
            stand_in.kill()
            stand_in.wait()
    return answer


def protected_pids(command: str, pid: int | None = None, tree: Tree | None = None) -> list[tuple[str, bool]]:
    """What a `kill` names by a literal pid that the session must keep: its
    claude process, any process of its tree (review of #242, C1), or an
    inbox watch anywhere, read from /proc."""
    tree, out = tree or {}, []
    for p in kill_pids(command):
        if pid and p == pid:
            out.append((CLAUDE_LABEL, False))
        elif p in tree:
            out.append(label_of(p, *tree[p]))
        elif is_inbox(argv := read_argv(p)):
            out.append(label_of(p, read_comm(p), argv, in_tree=False))
    return out


UNEXPANDED = re.compile(r"\$(\{|[A-Za-z_])")


def decision(command: str, cmdline: str | None, pid: int | None = None, tree: Tree | None = None,
             shell: bool | None = None, session_id: str | None = None) -> tuple[str, str] | None:
    """deny when a kill would select the session's claude process, its
    shell, a process of its tree or an inbox watch; ask when a pattern
    holds a variable or a command substitution the hook cannot read
    (`pkill -f "$P"`, `pkill -f "claude-$(id -un)"`), since its value
    decides; otherwise nothing. `shell` models the shell the command will
    run in: by default, inside a session (a claude ancestor found)."""
    why = verdict(command, cmdline)
    if why:
        return "deny", why
    if not kills(command):
        return None
    shell = bool(cmdline) if shell is None else shell
    prefix = shell_prefix(session_id) if shell else ""
    found = hits(command, targets(command, cmdline, tree, shell, prefix))
    if found:
        return "deny", message([(label, inbox) for _, label, inbox in found], [p for p, _, _ in found])
    by_pid = protected_pids(command, pid, tree)
    if by_pid:
        return "deny", message(by_pid)
    groups = kill_groups(command)
    if groups:
        return "deny", (f"This command kills by a negative or zero operand ({groups[0]}): -1 is every process "
                        "you may signal, 0 the command's own process group (a signal 0 is spelt -0) and -N a whole process group, any "
                        "of which can hold this session's claude process, its shell and its tasks. Kill by the "
                        "exact pid of a process outside this session's tree.")
    # procps's own answer, when it can be asked: it adds denials, never
    # removes one — the reading above stays as the floor.
    truth = ground_truth(command, pid, tree, shell, prefix)
    if truth:
        return "deny", message(truth) + " (pgrep, asked the same question, says so.)"
    # An expansion this hook does not evaluate: neither a pass nor a deny,
    # whatever the session (round 4 of #242). First among the asks: the
    # word reader takes `$"1234"` for a variable, which it is not.
    expansion = unevaluated(command)
    if expansion:
        return "ask", (f"This kill uses an expansion the guard does not evaluate ({expansion}), so what it "
                       "would kill cannot be checked against this session's claude process, its shell, its "
                       "tasks or an inbox watch; say the pid plainly.")
    if cmdline:
        pats = kill_patterns(command)
        if GROUP_MARK in pats:
            return "ask", ("killall -g kills the whole process group of what it names, and which group this "
                           "session is in is not something this hook can read from the command; allow it "
                           "knowing that, or name processes by pid.")
        held = [p for p in pats if unresolved(p)]
        if held:
            return "ask", (f"This command kills by a pattern held in a variable or a command substitution "
                           f"({PLACEHOLDER.sub('$(…)', held[0])}), whose value this hook cannot see; if it matches "
                           "this session's claude process, its shell or a process it started, the session dies. "
                           "Kill by the exact pid of a process you started instead, or allow it knowing the value.")
        # A pid held the same way ($PPID, $$, $(head lock)) can be the
        # session's own (review of #242, pre-existing B).
        held = kill_operands(command)[1]
        if held:
            return "ask", (f"This command kills a pid held in a variable or a command substitution ({held[0]}), "
                           "whose value this hook cannot see; if it is this session's claude process, its shell "
                           "or a process of its tree, the session dies. Kill by a literal pid outside this "
                           "session's tree, or allow it knowing the value.")
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        command = (payload.get("tool_input") or {}).get("command") or ""
    except (ValueError, AttributeError):
        return 0
    pid, cmdline = own_claude()
    # The tree is read only for a command that kills: the hook runs on
    # every Bash call.
    tree = session_tree(pid) if pid and kills(command) else {}
    d = decision(command, cmdline, pid, tree, session_id=payload.get("session_id"))
    if d:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                 "permissionDecision": d[0],
                                                 "permissionDecisionReason": d[1]}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
