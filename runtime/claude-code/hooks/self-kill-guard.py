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

Output: a deny decision on stdout, or nothing. Exit 0 always: input it
cannot read is passed, never blocked.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys

PREFIXES = {"timeout", "sudo", "env", "nohup", "nice", "xargs", "exec", "command", "setsid", "stdbuf"}
KILL_TOOLS = {"pgrep", "pkill", "killall", "kill"}
# The prefixes' options whose next word is a value, never a command.
VALUE_OPTIONS = {"-s", "--signal", "-k", "--kill-after", "-u", "--user", "-g", "--group", "-U", "-C", "-h", "-p",
                 "-r", "-t", "-D", "-I", "-i", "-n", "-P", "-L", "-E", "-d", "-a", "-S", "--unset", "--chdir"}
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
        m = re.search(r"\$\(([^()]*)\)|`([^`]*)`", rest)
        if not m:
            break
        pieces.append(m.group(1) if m.group(1) is not None else m.group(2))
        rest = rest[:m.start()] + "SUBST" + rest[m.end():]
    pieces.append(rest)
    out = []
    for segment in (seg for piece in pieces for seg in re.split(r"[|;&]+", piece)):
        try:
            words = shlex.split(segment)
        except ValueError:
            words = segment.split()
        if not words:
            continue
        # A kill behind a prefix is still the kill (review of #68):
        # `timeout 5 pkill -f P`, sudo, env, nohup, nice, xargs, exec. A
        # prefix's options may take a separate argument (`sudo -u root`,
        # `timeout -s KILL 5`, `xargs -I {}`), which no rule for skipping
        # options can know: the kill is the first killing tool after it
        # that is not an option's value — `timeout -s kill 5 pkill -f P`
        # names the signal `kill` before the tool (review of #69, F3).
        if os.path.basename(words[0]) in PREFIXES:
            at = next((i for i, w in enumerate(words)
                       if os.path.basename(w) in KILL_TOOLS and not (i and words[i - 1] in VALUE_OPTIONS)), None)
            if at is None:
                continue
            words = words[at:]
        tool = os.path.basename(words[0])
        if tool in ("pgrep", "pkill"):
            full = any(w in ("-f", "--full") or (w.startswith("-") and not w.startswith("--") and "f" in w[1:]) for w in words[1:])
            args = [w for w in words[1:] if not w.startswith("-")]
            # -u/-g/-P take a value: drop the word after each.
            vals = set()
            for i, w in enumerate(words[1:], 1):
                if w in ("-u", "-U", "-g", "-G", "-P", "-s", "-t", "--euid", "--uid", "--pgroup", "--group", "--parent", "--session", "--terminal") and i + 1 < len(words):
                    vals.add(i + 1)
            args = [w for i, w in enumerate(words[1:], 1) if not w.startswith("-") and i not in vals]
            if full and args:
                out.append(args[-1])
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


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        command = (payload.get("tool_input") or {}).get("command") or ""
    except (ValueError, AttributeError):
        return 0
    why = verdict(command, own_claude_cmdline())
    if why:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                 "permissionDecision": "deny",
                                                 "permissionDecisionReason": why}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
