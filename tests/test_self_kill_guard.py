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
import time
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
        # A '#' inside a word is literal in bash (review of #70, F2).
        ("${#…} before the kill", "n=${#PIDS[@]}; pkill -f 'claude-fable'"),
        ("a#b before the kill", "echo a#b; pkill -f 'claude-fable'"),
        # A redirection's target is not the pattern; subshells and newlines
        # separate commands (review of #70, pre-existing).
        ("a kill with 2>/dev/null", "pkill -f 'claude-fable' 2>/dev/null"),
        ("a kill with >/dev/null 2>&1", "pkill -f 'claude-fable' >/dev/null 2>&1"),
        ("a kill in a subshell", "( pkill -f 'claude-fable' )"),
        ("a kill on the next line", "git status\npkill -f 'claude-fable'"),
        # The pattern is the FIRST argument: what trails it does not
        # displace it (re-review of #70, R1, R5).
        ("a trailing comment", "pkill -f claude-fable # zzqx yyqx"),
        ("a bare trailing #", "pkill -f claude-fable #"),
        ("a comment after two spaces", "pkill -f claude-fable  # zzqx"),
        ("a redirection glued to a subshell", "(pkill -f claude-fable)>out"),
        ("a clobbering redirection", "pkill -f claude-fable >| out"),
        ("-- before the pattern", "pkill -f -- claude-fable"),
        # Compound commands and process substitution (pre-existing).
        ("a brace group", "{ pkill -f claude-fable; }"),
        ("an if's then", "if true; then pkill -f claude-fable; fi"),
        ("a leading assignment", "x=1 pkill -f claude-fable"),
        ("process substitution", "diff <(pgrep -f claude-fable) /dev/null | xargs kill"),
        # getopt takes options after the pattern, and procps has options
        # the list lacked (re-review of #70, the fifth round).
        ("-f after the pattern", "pkill claude-fable -f"),
        ("--full after the pattern", "pkill claude-fable --full"),
        ("pgrep with -f after the pattern", "pgrep claude-fable -f | xargs kill"),
        ("a second word after the first", "pkill -f zzqx claude-fable"),
        ("a cluster ending in a value option", "pkill -fu root claude-fable"),
        ("-fd ,", "pkill -fd , claude-fable"),
        ("-d , apart", "pgrep -f -d , claude-fable | xargs kill"),
        ("--delimiter", "pgrep -f --delimiter , claude-fable | xargs kill"),
        ("-q 5", "pkill -f -q 5 claude-fable"),
        ("-r S", "pkill -f -r S claude-fable"),
        ("-O 5", "pkill -f -O 5 claude-fable"),
        ("--older 5", "pkill -f --older 5 claude-fable"),
        ("--cgroup g", "pkill -f --cgroup g claude-fable"),
        ("--logpidfile takes no value", "pkill -f --logpidfile claude-fable"),
        ("a redirection before the pattern", "pkill 2>/dev/null -f claude-fable"),
        ("a redirection between -f and the pattern", "pkill -f 2>/dev/null claude-fable"),
        # A signal option is not a value option, whatever its letters
        # (re-review of #70, the sixth round).
        ("-TSTP before -f", "pkill -TSTP -f claude-fable"),
        ("-TRAP before -f", "pkill -TRAP -f claude-fable"),
        ("-int before -f", "pkill -int -f claude-fable"),
        ("-cont before -f", "pkill -cont -f claude-fable"),
        ("a signal and -f after the pattern", "pkill claude-fable -TSTP -f"),
        # A '#' after $((…))'s ')' is literal: the kill after it runs.
        ("$((…))# before the kill", "echo $((1+1))#; pkill -f claude-fable"),
        ("n=$((n+1))#x before the kill", "n=$((n+1))#x; pkill -f claude-fable"),
        ("a value that is the pattern, -d", "pgrep -f -d claude-fable | xargs kill"),
        ("--fu, a prefix of --full", "pkill --fu claude-fable"),
        # Seventh round: `--` as an option's value; a comment after a
        # subshell's ')' holding a quote.
        ("-d -- -f", "pgrep -d -- -f claude-fable | xargs kill"),
        ("--delimiter -- -f", "pgrep --delimiter -- -f claude-fable | xargs kill"),
        ("a comment after a subshell, a quote in it", "(true)# it's here\npkill -f claude-fable\necho x # '"),
        # A here-document read by a shell is code (a heredoc's body is
        # otherwise data, below).
        ("a heredoc fed to bash", "bash <<'EOF'\npkill -f claude-fable\nEOF"),
        ("a heredoc piped to sh", "cat <<EOF | sh\npkill -f claude-fable\nEOF"),
        ("a kill after a heredoc ends", "git commit -F - <<'EOF'\nmsg\nEOF\npkill -f claude-fable"),
        # Eighth round: a `<<` that is no here-document drops nothing; a
        # shell by its path reads a heredoc; a pattern without -f is a NAME.
        ("a << in arithmetic, then a kill", "echo $((1<<n))\npkill -f claude-fable"),
        ("a << in a quote, then a kill", "grep -n 'x <<EOF' README.md\npkill -f claude-fable"),
        ("a heredoc fed to /bin/sh", "/bin/sh <<EOF\npkill -f claude-fable\nEOF"),
        ("pkill -c by the session's name", "pkill -c claude"),
        # A value glued to its option ends the cluster: the pattern after
        # it is the pattern (tenth round).
        ("a glued -u value, then the name", "pkill -e -uuser claude"),
        ("a glued -t value, then the name", "pkill -tpts/1 claude"),
        ("a loop killing what pgrep names by the session's name", "for p in $(pgrep claude); do kill $p; done"),
        ("pkill by the session's name", "pkill claude"),
        ("killall by the session's name", "killall claude"),
        ("killall -qr, a cluster with -r", "killall -qr claud"),
        ("killall by a path to the session's binary", "killall /home/user/.local/share/claude/versions/9.9.9/claude"),
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
        # What a redirection brings is not a pattern: a fd, a target, `>|`.
        ("killall -r with 2>/dev/null", "killall -r zzqx 2>/dev/null"),
        ("killall -r with >|", "killall -r zzqx >| /dev/null"),
        ("pkill -f of another pattern, 2>/dev/null", "pkill -f zzqx 2>/dev/null"),
        ("a real comment naming the kill", "git status # pkill -f claude-fable"),
        ("a commit message in a heredoc quoting a kill",
         "git commit -q -F - <<'EOF'\nfix: `pgrep -d -- -f claude-fable` and pkill -f claude-fable\nEOF"),
        ("a <<- heredoc with a tab-indented delimiter", "cat <<-EOF > f\n\tpkill -f claude-fable\n\tEOF"),
        ("pkill by name with a short option value that is in 'claude'", "pkill -u a sleep"),
        ("a listing pgrep by the session's name, no kill anywhere",
         "for c in $(pgrep -x claude); do ls -l /proc/$c/exe; done"),
    ]
    for label, cmd in allowed:
        check(f"allowed: {label}", g.verdict(cmd, CLAUDE) is None, g.kill_patterns(cmd))
    check("killall -g asks: the group it kills is not in the command", (g.decision("killall -g bash", CLAUDE) or ("",))[0] == "ask")
    for cmd in ('pkill -f "$P"', "pgrep -f ${PAT} | xargs kill", 'pkill -f "$(cat pattern.txt)"',
                'pkill -f "claude-$(id -un)"', "pkill -f claude-`whoami`"):
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

    # Ground truth: pgrep itself is asked, against a real process standing
    # in for the session (argv0 claude-zzqk, name "sleep"). The reading
    # above gets a command line WITHOUT the token, so every deny here is
    # procps's answer (the owner's choice after seven rounds, 2026-09-30).
    dummy = subprocess.Popen(["bash", "-c", "exec -a claude-zzqk sleep 60"])
    try:
        time.sleep(0.3)
        pid, other = dummy.pid, "claude --model x unrelated"
        truth = [
            ("pkill -f claude-zzqk", True),
            ("pkill claude-zzqk -f", True),                 # getopt permutes; procps decides
            ("pkill -TSTP -f claude-zzqk", True),            # the signal dropped for pgrep
            # -c and -d change what pgrep prints, not what it selects: the
            # hook drops them and reads plain pids (ninth round).
            ("pgrep -d -- -f claude-zzqk | xargs kill", True),
            ("pkill -c -f claude-zzqk", True),
            # POSIX classes: procps's ERE, which Python's re misreads; a kill
            # reading pgrep's output through a loop or a variable (ninth).
            ("for p in $(pgrep -f 'claude-zzqk [[:digit:]]+'); do kill $p; done", True),
            ("pids=$(pgrep -f 'claude-zzqk [[:digit:]]+'); kill $pids", True),
            ("pgrep -f 'claude-zzqk [[:digit:]]+' | while read p; do kill $p; done", True),
            ("pkill -f 'claude-zz.k'", True),                # a regex, matched by procps
            ("killall -r slee", True),                       # by process name
            ("killall sleep", True),
            ("pkill -f zzqk-matches-nothing-here", False),
            ("pgrep -x node | xargs kill", False),
        ]
        for cmd, want in truth:
            d = g.decision(cmd, other, pid)
            check(f"ground truth: {cmd} -> {'deny' if want else 'allowed'}", (d is not None and d[0] == "deny") == want, d)
        real_selects, ran = g.selects, []
        g.selects = lambda argv, p: ran.append(argv) or False
        try:
            d = g.decision('pkill -f "$P"', other, pid)
        finally:
            g.selects = real_selects
        check("a pattern it cannot read: pgrep is never run for it, and the hook asks",
              ran == [] and (d or ("",))[0] == "ask", (ran, d))
        check("-c and -d leave the selection intact: a glued value and a pattern after -- are untouched",
              g._without_output_options(["-uarchitect-cto-01", "-cf", "x"]) == ["-uarchitect-cto-01", "-f", "x"]
              and g._without_output_options(["-f", "--", "-cx"]) == ["-f", "--", "-cx"]
              and g._without_output_options(["-fd", ",", "p"]) == ["-f", "p"]
              and g._without_output_options(["-cu", "root", "p"]) == ["-u", "root", "p"],
              (g._without_output_options(["-uarchitect-cto-01", "-cf", "x"]), g._without_output_options(["-cu", "root", "p"])))
        check("pgrep_argvs: pkill loses its signal options, killall NAME becomes pgrep -x",
              g.pgrep_argvs(["pkill", "-TERM", "-9", "-f", "p"]) == [["pgrep", "-f", "p"]]
              and g.pgrep_argvs(["killall", "a", "b"]) == [["pgrep", "-x", "a"], ["pgrep", "-x", "b"]])
        # The budget holds across every pgrep, killall's names included.
        real_selects, budget = g.selects, g.GROUND_TRUTH_BUDGET_S
        g.selects = lambda argv, p, timeout=2.0: time.sleep(min(timeout, 0.4)) or False
        g.GROUND_TRUTH_BUDGET_S = 0.5
        try:
            t0 = time.monotonic()
            g.ground_truth("killall a b c d e f", pid)
            took = time.monotonic() - t0
        finally:
            g.selects, g.GROUND_TRUTH_BUDGET_S = real_selects, budget
        check("the ground truth stops within its budget, across killall's names", took < 1.5, took)
        # selects() hands its bound to the process it starts: a pgrep that
        # hangs is killed at the timeout, never waited on (#70, tenth re-review).
        real_run, seen = g.subprocess.run, []

        def recording(argv, **kw):
            seen.append(kw.get("timeout"))
            raise g.subprocess.TimeoutExpired(argv, kw.get("timeout") or 0)
        g.subprocess.run = recording
        try:
            answer = g.selects(["pgrep", "-f", "x"], pid, timeout=0.7)
        finally:
            g.subprocess.run = real_run
        check("selects passes its timeout to subprocess.run, and a timeout is no answer",
              seen == [0.7] and answer is None, (seen, answer))
        check("the dummy was not killed by any of this", dummy.poll() is None)
    finally:
        dummy.kill()
        dummy.wait()

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
