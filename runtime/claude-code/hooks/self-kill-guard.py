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

Output: a decision on stdout — deny when a pattern matches, ask when a
pattern is a variable or a command substitution the hook cannot read — or
nothing. Exit 0 always: input it cannot read is passed, never blocked.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys

PREFIXES = {"timeout", "sudo", "env", "nohup", "nice", "xargs", "exec", "command", "setsid", "stdbuf"}
KILL_TOOLS = {"pgrep", "pkill", "killall", "kill"}
# Words that open or continue a compound command before the command itself.
COMPOUND = {"{", "}", "!", "if", "then", "elif", "else", "while", "until", "do", "time", "coproc"}
# pgrep's and pkill's options that take a separate value.
PGREP_VALUE_OPTIONS = {"-u", "-U", "-g", "-G", "-P", "-s", "-t", "-F", "--euid", "--uid", "--pgroup", "--group",
                       "--parent", "--session", "--terminal", "--pidfile", "--signal", "--ns", "--nslist"}
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
    p = pid or os.getpid()
    for _ in range(64):
        try:
            with open(f"{proc}/{p}/stat", encoding="utf-8", errors="replace") as fh:
                raw = fh.read()
            comm = raw[raw.index("(") + 1:raw.rindex(")")]
            ppid = int(raw[raw.rindex(")") + 2:].split()[1])
        except (OSError, ValueError, IndexError):
            return None
        if comm == "claude":
            try:
                with open(f"{proc}/{p}/cmdline", "rb") as fh:
                    return fh.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
            except OSError:
                return None
        if ppid <= 1:
            return None
        p = ppid
    return None


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


def segments(piece: str) -> list[list[str]]:
    """The simple commands of a command line, each as its words. Split on
    |, ; and & only OUTSIDE quotes: splitting the raw text first cut a
    quoted argument that merely mentions a kill (python3 -c '... pkill -f
    P ...') into a command of its own, and denied it (re-review of #69)."""
    # No comment characters: a bare shlex.shlex keeps '#', so `${#A[@]};
    # pkill -f P` and `echo a#b; pkill -f P` lost the kill (review of #70);
    # in bash a '#' inside a word is literal. A newline and a subshell's
    # parentheses end a command as ; does. A redirection and its target are
    # not arguments: `pkill -f P 2>/dev/null` read /dev/null as the pattern.
    lex = shlex.shlex(piece, posix=True, punctuation_chars="();<>|&\n")
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
        elif tok and set(tok) <= set("|;&\n()"):
            out.append(cur)
            cur = []
        elif tok and set(tok) <= set("<>&"):
            # A redirection: `2>`, `>`, `&>`, `>&` … — never & or && (the
            # separators above). The word after it (a file, or `1` of
            # 2>&1) is not an argument.
            skip = True
        else:
            cur.append(tok)
    out.append(cur)
    return out


def kill_patterns(command: str) -> list[str]:
    """Every pattern the command selects processes by for a kill: the
    argument of -f/--full's pgrep or pkill, and killall -r's regex, in a
    command that kills at all."""
    if not KILLS.search(command):
        return []
    # Each $( … ) (and `…`) is a command of its own: lifted out innermost
    # first, a placeholder word left behind, so `pgrep -u "$(id -un)" -f P`
    # keeps its pattern and `kill $(pgrep -f P)` yields the pgrep.
    pieces, rest = [], command
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
        tool = os.path.basename(words[0])
        if tool in ("pgrep", "pkill"):
            # pgrep and pkill take ONE pattern: the first word that is not an
            # option or an option's value. Taken from the END, whatever
            # trailed it — a comment, a redirection, an fd — displaced it,
            # and four review rounds on #69 and #70 patched one spelling at
            # a time (re-review of #70, R1).
            full, pattern, it = False, None, iter(words[1:])
            for w in it:
                if w == "--":
                    pattern = next(it, None)
                    break
                if w.startswith("-") and len(w) > 1:
                    if w in ("-f", "--full") or (not w.startswith("--") and "f" in w[1:]):
                        full = True
                    if w in PGREP_VALUE_OPTIONS:
                        next(it, None)
                    continue
                pattern = w
                break
            if full and pattern is not None:
                out.append(pattern)
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


UNEXPANDED = re.compile(r"\$(\{|[A-Za-z_])")


def decision(command: str, cmdline: str | None) -> tuple[str, str] | None:
    """deny when a pattern matches the session's own command line; ask when
    a pattern holds a variable or a command substitution the hook cannot
    read (`pkill -f "$P"`, `pkill -f "claude-$(id -un)"`), since its value
    decides; otherwise nothing."""
    why = verdict(command, cmdline)
    if why:
        return "deny", why
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
    d = decision(command, own_claude_cmdline())
    if d:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                 "permissionDecision": d[0],
                                                 "permissionDecisionReason": d[1]}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
