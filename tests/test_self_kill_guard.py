#!/usr/bin/env python3
"""Tests for runtime/claude-code/hooks/self-kill-guard.py: which commands
would kill the session's own claude process, judged against a planted
command line; and the hook's protocol end to end."""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(HERE, "runtime", "claude-code", "hooks", "self-kill-guard.py")
sys.path.insert(0, os.path.dirname(HOOK))
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("self_kill_guard", HOOK)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

# The command line that bit, as the launcher wrote it before the fix.
CLAUDE = ("claude --model claude-fable-5-1 --effort medium --append-system-prompt-file /x/launch-prompt.md -- "
          "Session start: arm your GZCoord inbox watch now, with Monitor(command: 'gzcoord-inbox --follow', "
          "description: 'gzcoord inbox watch', timeout_ms: 1800000); re-arm it at each expiry notice.")


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    refused = [
        ("the command that killed architect-cto-01",
         "pgrep -u \"$(id -un)\" -f 'gzcoord-inbox --follow' | xargs -r kill 2>/dev/null; pgrep -u \"$(id -un)\" -f 'gzcoord-inbox --follow' | wc -l"),
        ("pkill -f with a matching pattern", "pkill -f 'gzcoord-inbox --follow'"),
        ("combined short flags (-af)", "pgrep -af gzcoord-inbox | awk '{print $1}' | xargs kill"),
        ("kill $(pgrep -f …)", "kill $(pgrep -f 'inbox --follow')"),
        ("a pattern matching the model argument", "pkill -f 'claude-fable'"),
        ("killall -r", "killall -r 'claude'"),
        ("a kill behind timeout", "timeout 5 pkill -f 'gzcoord-inbox --follow'"),
        ("a kill behind sudo and env", "sudo env A=1 pkill -f 'claude-fable'"),
        ("xargs pkill", "echo x | xargs pkill -f 'gzcoord-inbox'"),
        ("a prefix option with its own argument (sudo -u)", "sudo -u root pkill -f 'gzcoord-inbox'"),
        ("timeout -s KILL 5", "timeout -s KILL 5 pkill -f 'claude-fable'"),
        ("timeout -s kill 5: a lowercase signal is a value, not the tool", "timeout -s kill 5 pkill -f 'claude-fable'"),
        ("sudo -u kill: a user named like a tool", "sudo -u kill pkill -f 'gzcoord-inbox'"),
        # A prefix's boolean flag is no value (re-review of #69, N1).
        ("sudo -E", "sudo -E pkill -f 'claude-fable'"),
        ("env -i", "env -i pkill -f 'claude-fable'"),
        ("sudo -n", "sudo -n pkill -f 'claude-fable'"),
        ("xargs -r", "echo x | xargs -r pkill -f 'claude-fable'"),
        ("xargs -t", "echo x | xargs -t pkill -f 'claude-fable'"),
        ("sudo -i", "sudo -i pkill -f 'claude-fable'"),
        ("sudo -S", "sudo -S pkill -f 'claude-fable'"),
        ("nice -n 5", "nice -n 5 pkill -f 'claude-fable'"),
        # Nested prefixes: each one's own options (re-review of #69, M1).
        ("sudo timeout -s kill 5", "sudo timeout -s kill 5 pkill -f 'claude-fable'"),
        ("sudo -u root timeout -s kill 5", "sudo -u root timeout -s kill 5 pkill -f 'claude-fable'"),
        ("env -i timeout -s kill 5", "env -i timeout -s kill 5 pkill -f 'claude-fable'"),
        ("nohup timeout -k kill 5", "nohup timeout -k kill 5 pkill -f 'claude-fable'"),
        ("timeout 5 sudo -u kill", "timeout 5 sudo -u kill pkill -f 'claude-fable'"),
        ("exec -a kill", "exec -a kill pkill -f 'claude-fable'"),
        ("env -u X", "env -u HOME pkill -f 'gzcoord-inbox'"),
        ("xargs -I {}", "pgrep -f 'inbox --follow' | xargs -I {} kill {}"),
    ]
    for label, cmd in refused:
        check(f"refused: {label}", g.verdict(cmd, CLAUDE) is not None, g.kill_patterns(cmd))
    allowed = [
        ("listing only, no kill", "pgrep -u \"$(id -un)\" -af 'gzcoord-inbox --follow'"),
        ("a kill by a pattern the session does not match", "pkill -f 'node .*websearch-locale'"),
        ("pgrep -x by exact name, then kill", "pgrep -x node | xargs kill"),
        ("a kill by pid", "kill 12345"),
        ("an unrelated command", "git status"),
        # The fabric's own way to end a session: fabric-fresh signals its
        # session's claude by pid (SIGTERM), a command the guard must pass.
        ("fabric-fresh ending the session for its next job", "fabric-fresh --job j3"),
        ("fabric-fresh with a note that mentions a kill", 'fabric-fresh --note "stopped: pkill -f gzcoord-inbox killed the last one"'),
        # A kill phrase inside a quoted argument is text, not a command.
        ("a quoted python -c string that mentions a kill", "python3 -c 'print(\"pkill -f claude-fable\")'"),
        ("a commit message that quotes the command", "git commit -m 'fix: pgrep -f gzcoord-inbox | xargs kill no longer runs'"),
    ]
    for label, cmd in allowed:
        check(f"allowed: {label}", g.verdict(cmd, CLAUDE) is None, g.kill_patterns(cmd))
    for cmd in ('pkill -f "$P"', "pgrep -f ${PAT} | xargs kill"):
        check(f"a variable pattern asks: {cmd}", (g.decision(cmd, CLAUDE) or ("",))[0] == "ask", g.decision(cmd, CLAUDE))
    check("a matching pattern still denies through decision()", g.decision("pkill -f claude-fable", CLAUDE)[0] == "deny")
    check("a harmless command: no decision", g.decision("git status", CLAUDE) is None)
    check("still split outside quotes: a real pipe after a quoted word",
          g.verdict("echo 'x y' | xargs pkill -f 'claude-fable'", CLAUDE) is not None)
    launch = open(os.path.join(HERE, "runtime", "openrouter", "launch"), encoding="utf-8").read()
    opening = re.search(r'^OPENING="([^"]*)"', launch, re.M).group(1)
    fixed = CLAUDE.split(" -- ")[0] + " -- " + opening   # the launcher's own text, not a copy
    check("the launcher's new prompt: the old kill no longer matches the session",
          g.verdict("pgrep -f 'gzcoord-inbox --follow' | xargs kill", fixed) is None)
    check("no claude ancestor (outside a session): nothing refused", g.verdict("pkill -f claude", None) is None)

    # The ancestor walk, on a planted /proc: hook (30) -> bash (20) -> claude (10).
    with tempfile.TemporaryDirectory() as proc:
        for pid, comm, ppid, cmd in ((30, "python3", 20, "python3 hook"), (20, "bash", 10, "bash -c x"), (10, "claude", 5, CLAUDE)):
            os.makedirs(os.path.join(proc, str(pid)))
            open(os.path.join(proc, str(pid), "stat"), "w").write(f"{pid} ({comm}) S {ppid} 0 0\n")
            open(os.path.join(proc, str(pid), "cmdline"), "wb").write(cmd.replace(" ", "\0").encode())
        found = g.own_claude_cmdline(proc=proc, pid=30)
        check("the walk finds the nearest claude ancestor's command line", found == CLAUDE, found)
        open(os.path.join(proc, "10", "stat"), "w").write("10 (node) S 5 0 0\n")
        check("…and none when no ancestor is claude", g.own_claude_cmdline(proc=proc, pid=30) is None)
    r = subprocess.run([sys.executable, HOOK], input=json.dumps({"tool_input": {"command": "git status"}}),
                       capture_output=True, text=True)
    check("the hook: a harmless command prints nothing and exits 0", r.returncode == 0 and not r.stdout.strip(), r.stdout)
    r = subprocess.run([sys.executable, HOOK], input="not json", capture_output=True, text=True)
    check("the hook: unreadable input is passed, never blocked", r.returncode == 0 and not r.stdout.strip(), r.stdout)
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
