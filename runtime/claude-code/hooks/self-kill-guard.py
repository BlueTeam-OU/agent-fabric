#!/usr/bin/env python3
"""runtime/claude-code/hooks/self-kill-guard.py: a PreToolUse hook on Bash.

Refuses a command that kills processes chosen by a pattern
(`pkill -f PAT`, `pgrep -f PAT | xargs kill`, `kill $(pgrep -f PAT)`,
`killall -r PAT`) when PAT matches the command line of the session's own
`claude` process, the nearest ancestor of this hook.

WHY. A session's claude process carries its opening prompt in argv, and the
prompt named the inbox watch's command. So `pgrep -f 'gzcoord-inbox
--follow' | xargs kill`, meant to clear a stale watcher, killed the session
that ran it: architect-cto-01, twice, on 2026-09-29; fabric-coordinator
earlier with a `pkill -f` pattern. Advice did not stop it; this does. The
launcher's prompt no longer names the command, and this guard covers every
other pattern that happens to match.

TWO LAYERS. First a reading of the command: every argument of a pgrep or
pkill with -f, and killall -r's regexes, is matched against the session's
command line — generous on purpose, since a false deny costs a rephrase.
Then the ground truth: the same question put to pgrep itself, list-only
(pkill without its signals, killall as pgrep -x), and a deny when it names
the session's own pid. Seven review rounds on #69 and #70 each found a
spelling a re-implementation of procps's rules misread; procps does not
misread itself. The second layer only adds denials.

Output: a decision on stdout — deny when either layer says the session is
selected, ask when a pattern is a variable or a command substitution the
hook cannot read — or nothing. Exit 0 always: input it cannot read is passed, never blocked.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import signal
import subprocess
import sys

PREFIXES = {"timeout", "sudo", "env", "nohup", "nice", "xargs", "exec", "command", "setsid", "stdbuf"}
KILL_TOOLS = {"pgrep", "pkill", "killall", "kill"}
# Words that open or continue a compound command before the command itself.
COMPOUND = {"{", "}", "!", "if", "then", "elif", "else", "while", "until", "do", "time", "coproc"}
# What a lifted $( … ), ` … ` or <( … ) leaves in its place: no real pattern
# contains it, so a pattern that does was built from a substitution.
SUBST = "__SELF_KILL_GUARD_SUBST__"
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
        elif name in KILL_TOOLS:
            return words[i:]
    return []


SHELLS = re.compile(r"(?:^|[\s|;&(])(?:bash|sh|zsh|dash|ksh|eval|source|\.)(?=$|[\s;&|)])")


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
            while i < len(lines) and (lines[i].lstrip("\t") if strip_tabs else lines[i]) != delim:
                i += 1
            i += 1   # the delimiter line itself
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
    words from the tool on: substitutions lifted, here-document bodies
    dropped, segments split, compound keywords, assignments and prefixes
    walked past."""
    if not KILLS.search(command):
        return []
    # Each $( … ) (and `…`) is a command of its own: lifted out innermost
    # first, a placeholder word left behind, so `pgrep -u "$(id -un)" -f P`
    # keeps its pattern and `kill $(pgrep -f P)` yields the pgrep.
    # Here-document bodies first: a substitution inside one is data too.
    pieces, rest = [], drop_heredoc_bodies(command)
    while True:
        m = re.search(r"[$<>]\(([^()]*)\)|`([^`]*)`", rest)
        if not m:
            break
        pieces.append(m.group(1) if m.group(1) is not None else m.group(2))
        rest = rest[:m.start()] + SUBST + rest[m.end():]
    pieces.append(rest)
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
        if os.path.basename(words[0]) in ("pgrep", "pkill", "killall"):
            out.append(words)
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
                elif w.startswith("--"):
                    # getopt_long takes a unique prefix: --fu, --ful are --full.
                    name = w.split("=", 1)[0]
                    full = full or (len(name) > 2 and "--full".startswith(name))
                else:
                    full = full or "f" in w[1:]
            if full:
                out += cands
        elif tool == "killall" and ("-r" in words or "--regexp" in words):
            args = [w for w in words[1:] if not w.startswith("-")]
            out += args
    return out


def verdict(command: str, cmdline: str | None) -> str | None:
    if not cmdline:
        return None
    for pat in kill_patterns(command):
        try:
            hit = re.search(pat, cmdline)
        except re.error:
            hit = pat in cmdline
        if hit:
            return (f"The pattern {pat!r} matches this session's own claude process (its command line carries the "
                    "opening prompt), so this command would kill the session running it. Select by exact name "
                    "(pgrep -x) or by pid, and never kill the inbox watch: a Monitor ends at its expiry.")
    return None


SIGNAL_NAMES = {sig.name[3:] for sig in signal.Signals} | {"IOT", "CLD", "POLL"}


def _is_signal_option(w: str) -> bool:
    """pkill's `-<sig>`: a number or a signal name, any case, SIG optional
    (procps's signal_option). pgrep has no such option."""
    m = re.fullmatch(r"-(\d+|(?:SIG)?([A-Za-z]+[0-9+-]*))", w, re.I)
    if not m:
        return False
    name = (m.group(2) or "").upper()
    return m.group(1).isdigit() or name in SIGNAL_NAMES or name.startswith("RTMIN") or name.startswith("RTMAX")


def pgrep_argvs(words: list[str]) -> list[list[str]] | None:
    """The list-only pgrep calls that select what this kill command would:
    pgrep as it is; pkill without its signal options; `killall NAME` as
    `pgrep -x NAME` per name, `killall -r RE` as `pgrep RE`. None when a
    word is not literal (a variable, a substitution): its value decides,
    and the hook cannot know it."""
    tool, args = os.path.basename(words[0]), words[1:]
    if any("$" in w or "`" in w or SUBST in w for w in args):
        return None
    if tool == "pgrep":
        return [["pgrep", *args]]
    if tool == "pkill":
        return [["pgrep", *[w for w in args if not _is_signal_option(w)]]]
    regex = any(w in ("-r", "--regexp") for w in args)
    icase = any(w in ("-I", "--ignore-case") for w in args)
    names = [w for w in args if not w.startswith("-")]
    return [["pgrep", *(["-i"] if icase else []), *([] if regex else ["-x"]), n] for n in names] or None


def selects(argv: list[str], pid: int) -> bool | None:
    """Whether procps itself, asked this list-only question, names `pid`.
    None when it could not answer (an option pgrep refuses, no pgrep, a
    timeout): then the checks above are what stands."""
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=2, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode == 1:
        return False
    if r.returncode != 0:
        return None
    return str(pid) in r.stdout.split()


def ground_truth(command: str, pid: int | None) -> bool | None:
    """True when a kill in the command would select the session's own
    claude process, as procps answers it; False when every kill was asked
    and none would; None when one could not be asked. Seven review rounds
    on #69 and #70 each found a spelling that a re-implementation of
    procps's option and pattern rules misread (the owner chose this,
    2026-09-30): the tool that will do the matching is asked instead. Only
    pgrep ever runs here, never the kill."""
    if not pid:
        return None
    answer: bool | None = False
    for words in kill_commands(command):
        argvs = pgrep_argvs(words)
        if argvs is None:
            answer = None
            continue
        for argv in argvs:
            got = selects(argv, pid)
            if got:
                return True
            if got is None:
                answer = None
    return answer


UNEXPANDED = re.compile(r"\$(\{|[A-Za-z_])")


def decision(command: str, cmdline: str | None, pid: int | None = None) -> tuple[str, str] | None:
    """deny when a pattern matches the session's own command line; ask when
    a pattern holds a variable or a command substitution the hook cannot
    read (`pkill -f "$P"`, `pkill -f "claude-$(id -un)"`), since its value
    decides; otherwise nothing."""
    why = verdict(command, cmdline)
    if why:
        return "deny", why
    # procps's own answer, when it can be asked: it adds denials, never
    # removes one — the reading above stays as the floor.
    if KILLS.search(command) and ground_truth(command, pid):
        return "deny", ("pgrep, asked the same question this command asks, names this session's own claude "
                        "process, so the command would kill the session running it. Select by pid, or by a "
                        "pattern pgrep does not match against this session.")
    if cmdline:
        held = [p for p in kill_patterns(command) if UNEXPANDED.search(p) or SUBST in p]
        if held:
            return "ask", (f"This command kills by a pattern held in a variable or a command substitution "
                           f"({held[0].replace(SUBST, '$(…)')}), whose value this hook "
                           "cannot see; if it matches this session's own claude command line, the session dies. "
                           "Kill by pid or pgrep -x instead, or allow it knowing the value.")
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        command = (payload.get("tool_input") or {}).get("command") or ""
    except (ValueError, AttributeError):
        return 0
    pid, cmdline = own_claude()
    d = decision(command, cmdline, pid)
    if d:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                 "permissionDecision": d[0],
                                                 "permissionDecisionReason": d[1]}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
