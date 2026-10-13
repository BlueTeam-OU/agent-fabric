#!/usr/bin/env python3
"""Tests for runtime/claude-code/hooks/self-kill-guard.py: which commands
would kill the session's own claude process, judged against a planted
command line; and the hook's protocol end to end."""
from __future__ import annotations

import json
import os
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
    check("killall -g asks: the group it kills is not in the command", (g.decision("killall -g zzqx", CLAUDE) or ("",))[0] == "ask")
    for cmd in ('pkill -f "$P"', "pgrep -f ${PAT} | xargs kill", 'pkill -f "$(cat pattern.txt)"',
                'pkill -f "claude-$(id -un)"', "pkill -f claude-`whoami`",
                # An invalid regex in an unresolved pattern: its substring
                # fallback once matched and denied (review of #242, C5).
                'pkill -f "$PAT["', 'pkill -f "${P}("'):
        check(f"a variable pattern asks: {cmd}", (g.decision(cmd, CLAUDE) or ("",))[0] == "ask", g.decision(cmd, CLAUDE))
    # A pid operand the hook cannot read asks, like a pattern (review of
    # #242, pre-existing B); one it can read, or the command's own job,
    # does not.
    for cmd in ("kill $PPID", "kill $$", "kill -9 \"$pid\"", "kill $(head -1 /run/x.lock)", "kill `cat pidfile`",
                "kill $(pgrep -x zzqx | head -1)"):
        check(f"an unreadable pid asks: {cmd}", (g.decision(cmd, CLAUDE, shell=False) or ("",))[0] == "ask",
              g.decision(cmd, CLAUDE, shell=False))
    for cmd in ("sleep 9 & kill $!", "kill -l", "kill -l 9", "echo the word kill, no number", "kill $(pgrep -x zzqx-nothing-qx)", "kill 999999999"):
        check(f"a readable or harmless kill: no decision: {cmd}", g.decision(cmd, CLAUDE, shell=False) is None,
              g.decision(cmd, CLAUDE, shell=False))
    check("kill_operands: every number, its sign dropped", g.kill_operands("kill -s TERM +42 -- -43")
          == ([42, 43], []), g.kill_operands("kill -s TERM +42 -- -43"))
    # -1 is every process the user may signal, -N a process group (round 2).
    for cmd in ("kill -9 -1", "kill -- -1", "kill -1", "kill -- -4242", "kill -TERM -4242", "kill -s KILL -4242",
                "bash -c 'kill -9 -1'"):
        d = g.decision(cmd, CLAUDE, shell=False)
        check(f"a negative operand is refused: {cmd}", d is not None and d[0] == "deny" and "negative" in d[1], d)
    check("…but a negative first argument is a signal: kill -9 999999999",
          g.decision("kill -9 999999999", CLAUDE, shell=False) is None)
    # A repeat count past sre's limit overflows (pre-existing, review of #242).
    r = subprocess.run([sys.executable, HOOK], input=json.dumps({"tool_input": {"command": "pkill -f 'a{99999999999}'"}}),
                       capture_output=True, text=True)
    check("a regex that overflows the compiler: the hook still exits 0", r.returncode == 0 and not r.stderr,
          (r.returncode, r.stderr[-300:]))
    check("…and judges it as text", g._matches("a{99999999999}", "x a{99999999999} y") is True)
    check("a matching pattern still denies through decision()", g.decision("pkill -f claude-fable", CLAUDE)[0] == "deny")
    check("a harmless command: no decision", g.decision("git status", CLAUDE) is None)
    check("still split outside quotes: a real pipe after a quoted word",
          g.verdict("echo 'x y' | xargs pkill -f 'claude-fable'", CLAUDE) is not None)
    spec = importlib.util.spec_from_file_location("fabric_launch", os.path.join(HERE, "tools", "fabric", "launch.py"))
    launch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launch)
    opening = launch.OPENING
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
            d = g.decision(cmd, other, pid, shell=False)
            check(f"ground truth: {cmd} -> {'deny' if want else 'allowed'}", (d is not None and d[0] == "deny") == want, d)
        check("by name, the shell's stand-in (a sleep) is not the shell: killall sleep passes with the shell modelled",
              g.decision("killall sleep", other, None, {}, shell=True) is None)
        real_listed, ran = g.listed, []
        g.listed = lambda argv, timeout=2.0: ran.append(argv) or set()
        try:
            d = g.decision('pkill -f "$P"', other, pid)
        finally:
            g.listed = real_listed
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
        real_listed, budget = g.listed, g.GROUND_TRUTH_BUDGET_S
        g.listed = lambda argv, timeout=2.0: time.sleep(min(timeout, 0.4)) or set()
        g.GROUND_TRUTH_BUDGET_S = 0.5
        try:
            t0 = time.monotonic()
            g.ground_truth("killall a b c d e f", pid)
            took = time.monotonic() - t0
        finally:
            g.listed, g.GROUND_TRUTH_BUDGET_S = real_listed, budget
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

    # The session's tree, end to end. A stand-in session — bash under the
    # name `claude` — starts what the harness would (a background task, an
    # inbox watch) and runs the hook through a shell, as the settings do;
    # the hook finds it as its nearest claude. Distinctive words reach the
    # children by the environment, never the stand-in's own argv, so a
    # pattern matching a child does not match "claude" too.
    tmp = tempfile.mkdtemp()
    os.symlink("/bin/bash", os.path.join(tmp, "claude"))
    os.symlink("/bin/sleep", os.path.join(tmp, INBOX := "gzcoord-inbox"))
    script = ('(exec -a "$SIB" sleep 60) & s=$!; "$INB" 61 & i=$!; echo "$s $i"; '
              'while read -r f; do sh -c \'python3 "$0" < "$1"\' "$HOOK" "$f"; echo @@END; done; '
              'kill "$s" "$i"; wait')
    env = dict(os.environ, SIB="zzsib-bg-task-qx --token=zzSENTINEL-c6", INB=os.path.join(tmp, INBOX), HOOK=HOOK)
    session = subprocess.Popen([os.path.join(tmp, "claude"), "-c", script], env=env, text=True,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, start_new_session=True)
    outside = subprocess.Popen(["zzout-unrelated-qx", "60"], executable="/bin/sleep")
    try:
        sib, inbox = map(int, session.stdout.readline().split())
        time.sleep(0.2)
        reasons: list[str] = []

        def hook_in_session(cmd: str) -> tuple[str, str] | None:
            path = os.path.join(tmp, "payload.json")
            with open(path, "w") as fh:
                json.dump({"tool_input": {"command": cmd}}, fh)
            session.stdin.write(path + "\n")
            session.stdin.flush()
            out = []
            for line in session.stdout:
                if line.strip() == "@@END":
                    break
                out.append(line)
            if not "".join(out).strip():
                return None
            o = json.loads("".join(out))["hookSpecificOutput"]
            reasons.append(o["permissionDecisionReason"])
            return o["permissionDecision"], o["permissionDecisionReason"]

        tree_cases = [
            # (a) Only the shell the command runs in: the harness's
            # `bash -c '… eval …'` carries the pattern. Then the same, seen
            # only by procps: Python reads [[:alpha:]] as a set, so the
            # first layer misses and the stand-in shell is asked about.
            ("a pattern only the command's own shell carries", "pkill -f zzshell-only-qx", "own shell"),
            ("…the same through pgrep and the stand-in shell",
             "pkill -f 'zz[[:alpha:]]hell-qx' # zzshell-qx", "own shell"),
            # (b) A background process the session started.
            ("a sibling background task by [x]-pattern", "pgrep -f '[z]zsib-bg' | xargs kill", f"pid {sib}"),
            ("…the same through pgrep alone", "pkill -f '[z]zsib-[[:alpha:]]+-task'", f"pid {sib}"),
            # (c) An inbox watch: by pattern, by name, by explicit pid.
            ("gzcoord-inbox by pattern", "pkill -f gzcoord-inbox", "Never kill an inbox watch"),
            ("gzcoord-inbox by a pattern the shell does not carry", "pkill -f '[g]zcoord-inbox'",
             "Never kill an inbox watch"),
            ("gzcoord-inbox by its pid", f"kill {inbox}", "Never kill an inbox watch"),
            ("gzcoord-inbox by its pid, with a signal", f"kill -s TERM {inbox}", "Never kill an inbox watch"),
            ("gzcoord-inbox through $(pgrep -x)", "kill $(pgrep -x gzcoord-inbox)", "Never kill an inbox watch"),
            # A literal pid of the session's own: its root, a descendant,
            # spelt with a sign or behind -- (review of #242, C1, C2).
            ("the claude process by its pid", f"kill {session.pid}", "own claude process"),
            ("a background task by its exact pid", f"kill {sib}", f"pid {sib}"),
            ("a background task by +pid", f"kill +{sib}", f"pid {sib}"),
            ("a background task by pid behind -9 --", f"kill -9 -- {sib}", f"pid {sib}"),
            # A nested shell's literal payload is a command (review of #242, C3).
            ("a watch killed inside bash -c", f"bash -c 'kill {inbox}'", "Never kill an inbox watch"),
            ("a watch killed inside sudo sh -lc", f'sudo sh -lc "kill -9 {inbox}"', "Never kill an inbox watch"),
            ("a watch killed inside eval", f"eval 'kill {inbox}'", "Never kill an inbox watch"),
            ("a watch killed two shells deep", f"""bash -c "sh -c 'kill {inbox}'" """, "Never kill an inbox watch"),
            ("a sibling by pattern inside sh -c", "sh -c \"pkill -f '[z]zsib-bg'\"", f"pid {sib}"),
            # Every number in a command holding the word kill counts, whatever
            # option order bash would read (round 2, K1).
            ("a sticky -s 0 before -s TERM", f"kill -s 0 -s TERM {inbox}", "Never kill an inbox watch"),
            ("a sticky -0 before -s TERM", f"kill -0 -s TERM {inbox}", "Never kill an inbox watch"),
            ("kill -0 of a background task (no exemption)", f"kill -0 {sib}", f"pid {sib}"),
            ("/bin/kill", f"/bin/kill {sib}", f"pid {sib}"),
            ("command kill", f"command kill {sib}", f"pid {sib}"),
            ("builtin kill", f"builtin kill -9 {sib}", f"pid {sib}"),
            ("a protected number beside the word kill, even printed", f"bash -c 'echo kill {inbox}'",
             "Never kill an inbox watch"),
            # Wherever the payload stands among the shell's options (round 2, K2).
            ("a watch killed inside bash -o pipefail -c", f"bash -o pipefail -c 'kill {inbox}'",
             "Never kill an inbox watch"),
            ("a watch killed inside bash -c --", f"bash -c -- 'kill {inbox}'", "Never kill an inbox watch"),
            ("a sibling by pattern inside bash -e -o pipefail -c", "bash -e -o pipefail -c \"pkill -f '[z]zsib-bg'\"",
             f"pid {sib}"),
        ]
        for label, cmd, want in tree_cases:
            d = hook_in_session(cmd)
            check(f"in a session, refused: {label}",
                  d is not None and d[0] == "deny" and want in d[1] and "\n" not in d[1], d)
        # (d) What lies outside the tree passes, by pattern or by pid; the
        # same pattern unbracketed is refused, for the shell carries it.
        for label, cmd in (("a pattern matching only an unrelated process", "pgrep -f '[z]zout-unrelated' | xargs kill"),
                           ("an unrelated process by its pid", f"kill {outside.pid}"),
                           ("an unrelated process by +pid", f"kill +{outside.pid}"),
                           ("an unrelated process by pid inside bash -c", f"bash -c 'kill {outside.pid}'"),
                           ("a nested shell that only prints a kill", f"bash -c 'echo kill {outside.pid}'"),
                           ("kill -l, which lists signals", "kill -l")):
            d = hook_in_session(cmd)
            check(f"in a session, allowed: {label}", d is None, d)
        d = hook_in_session("pkill -f zzout-unrelated")
        check("in a session, refused: the unrelated pattern unbracketed (the shell carries it)",
              d is not None and "own shell" in d[1], d)
        check("an inbox watch by pid is refused outside a session too",
              (g.decision(f"kill {inbox}", None) or ("",))[0] == "deny")
        # A watch by its pid, however it was started: after any number of
        # interpreter options (C4), under timeout, nohup or setsid, run by
        # sh, behind an option that takes a value (round 2, N1, N2).
        flags = os.path.join(tmp, "flags")
        os.makedirs(os.path.join(flags, "sh"))
        py, sh = os.path.join(flags, INBOX), os.path.join(flags, "sh", INBOX)
        with open(py, "w") as fh:
            fh.write(f"#!{sys.executable}\nimport time\ntime.sleep(60)\n")
        os.chmod(py, 0o755)
        with open(sh, "w") as fh:
            fh.write("sleep 60\n:\n")
        spellings = (("python3 -I -u -B -X utf8 <path>", [sys.executable, "-I", "-u", "-B", "-X", "utf8", py, "--wait"]),
                     ("timeout 600 <path>", ["timeout", "600", py, "--until-delivery"]),
                     ("nohup <path>", ["nohup", py, "--until-delivery"]),
                     ("setsid <path>", ["setsid", py, "--until-delivery"]),
                     ("sh <path>", ["sh", sh]),
                     ("python3 --check-hash-based-pycs default <path>",
                      [sys.executable, "--check-hash-based-pycs", "default", py, "--until-delivery"]))
        watches = [(label, subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL)) for label, argv in spellings]
        try:
            time.sleep(0.5)
            for label, w in watches:
                d = g.decision(f"kill {w.pid}", None)
                check(f"an inbox watch run as {label}: refused by its pid",
                      d is not None and d[0] == "deny" and "inbox watch" in d[1], (d, g.read_argv(w.pid)))
        finally:
            for _, w in watches:
                w.kill()
                w.wait()
            os.unlink(py)
            os.unlink(sh)
            os.rmdir(os.path.join(flags, "sh"))
            os.rmdir(flags)
        for argv, want in ((["/usr/bin/env", "python3", "-I", "/x/gzcoord-inbox"], True),
                           (["fabric-python", "-I", "-u", "-B", "-W", "ignore", "/x/gzcoord-inbox", "--wait"], True),
                           (["python3", "--check-hash-based-pycs", "default", "/x/gzcoord-inbox"], True),
                           (["vim", "/x/notes.txt"], False),
                           (["sleep", "60"], False)):
            check(f"is_inbox {argv}: {want}", g.is_inbox(argv) is want)
        # A process is named by pid and name, never by its argv, which may
        # carry a token (review of #242, C6): the sibling's sentinel is in
        # no reason, though the sibling is refused by name in several.
        check("no reason quotes a protected process's argv",
              any(f"pid {sib}" in r for r in reasons) and not any("zzSENTINEL" in r for r in reasons),
              [r for r in reasons if "zzSENTINEL" in r])
        check("the processes the hook judged are all alive",
              session.poll() is None and outside.poll() is None
              and all(os.path.exists(f"/proc/{p}") for p in (sib, inbox)))
    finally:
        outside.kill()
        outside.wait()
        try:
            session.stdin.close()
            session.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass
        try:
            os.killpg(session.pid, 9)
        except OSError:
            pass
        session.wait()
        for name in ("claude", INBOX, "payload.json"):
            if os.path.lexists(os.path.join(tmp, name)):
                os.unlink(os.path.join(tmp, name))
        os.rmdir(tmp)

    # session_tree on a planted /proc: claude (10) has the hook's shell (20)
    # and the hook (30), which the command outlives, and a task (40) with a
    # child (50); 60 is another session's.
    with tempfile.TemporaryDirectory() as proc:
        for pid, comm, ppid in ((10, "claude", 5), (20, "sh", 10), (30, "python3", 20), (31, "pgrep", 30),
                                (40, "bash", 10), (50, "sleep", 40), (60, "sleep", 1)):
            os.makedirs(os.path.join(proc, str(pid)))
            open(os.path.join(proc, str(pid), "stat"), "w").write(f"{pid} ({comm}) S {ppid} 0 0\n")
            open(os.path.join(proc, str(pid), "cmdline"), "wb").write(f"{comm}\0x".encode())
        tree = g.session_tree(10, proc=proc, me=30)
        check("session_tree: the descendants, without the hook, its shell and its children",
              sorted(tree) == [40, 50] and tree[50] == ("sleep", ["sleep", "x"]), tree)
    check("the shell model escapes single quotes as the harness does",
          g.shell_texts("echo 'a'")[0].endswith("eval 'echo '\"'\"'a'\"'\"'' < /dev/null && pwd -P >| /tmp/claude-cwd"))
    # The fabric's own part of the shell: the session's SessionStart env
    # files, in their order, else session-start.py's lines (review of #242).
    with tempfile.TemporaryDirectory() as cfg:
        sid = "0000-planted-session"
        envd = os.path.join(cfg, "session-env", sid)
        os.makedirs(envd)
        for n, text in ((10, "unset X  # ten\n"), (2, "export ZZ_PLANTED=/zz-planted-root\n")):
            with open(os.path.join(envd, f"sessionstart-hook-{n}.sh"), "w") as fh:
                fh.write(text)
        real_cfg = os.environ.get("CLAUDE_CONFIG_DIR")
        os.environ["CLAUDE_CONFIG_DIR"] = cfg
        try:
            check("shell_prefix: the session's env files, in numeric order",
                  g.shell_prefix(sid) == "export ZZ_PLANTED=/zz-planted-root\nunset X  # ten\n", g.shell_prefix(sid))
            d = g.decision("pkill -f '[z]z-planted-root'", CLAUDE, shell=True, session_id=sid)
            check("a pattern only the session's env file carries: the shell is refused",
                  d is not None and "own shell" in d[1], d)
            check("…and not without the env file", g.decision("pkill -f '[z]z-planted-root'", CLAUDE, shell=True,
                                                              session_id="no-such-session") is None)
            fallback = g.shell_prefix("no-such-session")
            check("shell_prefix without env files: session-start.py's seal",
                  "unset CLAUDE_CODE_OAUTH_TOKEN" in fallback and "no secret in the session shell" in fallback, fallback)
            check("shell_prefix: a session id that is a path is not followed", g.shell_prefix("..") == fallback)
        finally:
            if real_cfg is None:
                os.environ.pop("CLAUDE_CONFIG_DIR", None)
            else:
                os.environ["CLAUDE_CONFIG_DIR"] = real_cfg
    d = g.decision("pkill -f '[s]hopt -u extglob'", CLAUDE, shell=True)
    check("a pattern only the harness's guards carry: the shell is refused", d is not None and "own shell" in d[1], d)

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
