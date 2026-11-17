#!/usr/bin/env python3
"""Tests for runtime/claude-code/hooks/post-review-shape-guard.py: which
`fabric-pr post-review` calls are refused as not bare, which pass, and the
hook's protocol end to end (j540)."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(HERE, "runtime", "claude-code", "hooks", "post-review-shape-guard.py")
spec = importlib.util.spec_from_file_location("post_review_shape_guard", HOOK)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)


def run(payload: str) -> str:
    return subprocess.run([sys.executable, HOOK], input=payload, capture_output=True, text=True, check=True).stdout


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    refused = [
        ("python-dev-01's call on #449, refused twice as [Self-Approval]",
         "cd /home/python-dev-01/projects/agent-fabric-j195 && fabric-pr post-review 449 --model fable "
         "< /home/python-dev-01/scratchpad/review1.md 2>&1 | tail -8"),
        ("fabric-coordinator's on 2026-10-27, with a command after it",
         "cd /home/user/projects/agent-fabric-x && fabric-pr post-review 437 < r.md; git log --oneline -1"),
        ("a pipe alone", "fabric-pr post-review 12 < r.md | tail -3"),
        ("2>&1 alone", "fabric-pr post-review 12 < r.md 2>&1"),
        ("a command before it on its own line", "cd /x\nfabric-pr post-review 12 < r.md"),
        ("an env assignment", "LC_ALL=C fabric-pr post-review 12 < r.md"),
        ("the script by path", "bin/fabric-pr post-review 12 < r.md"),
        ("a variable for the report", 'fabric-pr post-review 12 < "$f"'),
        ("a heredoc", "fabric-pr post-review 12 <<'EOF'\nreport\nEOF"),
        ("an option before the subcommand, then a pipe", "fabric-pr --repo o/n post-review 3 < r | cat"),
        ("inside a substitution", "out=$(fabric-pr post-review 12 < r.md)"),
        ("after ||", "false || fabric-pr post-review 12 < r.md"),
        # Wrappers with no separator before the script (review of #451, F1).
        ("a brace group", "{ fabric-pr post-review 12 < r.md; } 2>&1"),
        ("time", "time fabric-pr post-review 12 < r.md"),
        ("timeout with a duration", "timeout 60 fabric-pr post-review 12 < r.md"),
        ("timeout with a signal and a duration", "timeout -s KILL 60 fabric-pr post-review 12 < r.md"),
        ("env", "env X=1 fabric-pr post-review 12 < r.md"),
        ("sudo with a user", "sudo -u x fabric-pr post-review 12 < r.md"),
        ("nohup", "nohup fabric-pr post-review 12 < r.md"),
        ("negated", "! fabric-pr post-review 12 < r.md"),
        ("inside if/then", "if true; then fabric-pr post-review 12 < r.md; fi"),
        ("bash -c", 'bash -c "fabric-pr post-review 12 < r.md"'),
        ("sudo sh -lc", "sudo sh -lc 'fabric-pr post-review 12 < r.md'"),
        ("bash -c --", 'bash -c -- "fabric-pr post-review 12 < r.md"'),
        ("eval", 'eval "fabric-pr post-review 12 < r.md"'),
        ("a backslash before the name", "\\fabric-pr post-review 12 < r.md"),
        ("the name quoted", '"fabric-pr" post-review 12 < r.md'),
        ("in backticks", "x=`fabric-pr post-review 12 < r.md`"),
        ("wrapped, with an unclosed quote", "cd /x && fabric-pr post-review 12 < 'r.md"),
        # Round 2 of #451: a quoted substitution (F5), and the wrappers a parse of command positions missed (F1).
        ("a quoted substitution assigned", 'out="$(fabric-pr post-review 12 < r.md)"; echo "$out"'),
        ("a quoted substitution echoed", 'echo "$(fabric-pr post-review 12 < r.md)"'),
        ("quoted backticks", 'x="`fabric-pr post-review 12 < r.md`"'),
        ("time -p", "time -p fabric-pr post-review 12 < r.md"),
        ("sudo -E bash -c", 'sudo -E bash -c "fabric-pr post-review 12 < r.md"'),
        ("env -i bash -c", 'env -i bash -c "fabric-pr post-review 12 < r.md"'),
        ("nice -10 bash -c", 'nice -10 bash -c "fabric-pr post-review 12 < r.md"'),
        # Mutation: post-review-shape-guard.py bare(), drop its `read[1][:1] == [VERB]` clause (an option before the verb is not bare)
        ("an option before the subcommand, no pipe", "fabric-pr --repo o/n post-review 3 < r.md"),
        ("the same through the dispatcher", "fabric pr --repo o/n post-review 3 < r.md"),
        ("a heredoc fed to bash", "bash <<EOF\nfabric-pr post-review 12 < r.md\nEOF"),
        ("a quoted heredoc fed to bash", "bash <<'EOF'\nfabric-pr post-review 12 < r.md\nEOF"),
        # Mutation S10 (j830): `<<<` stepped one character at a time, so `<< 'x'` at i+1 opened a heredoc that hid the
        # next line; bash reads a here-string, and the line after it runs.
        ("a quoted here-string, then the command", "cat <<< 'x'\nfabric-pr post-review 1 < r.md"),
        ("a double-quoted here-string, then the command", 'cat <<< "a b"\nfabric-pr post-review 1 < r.md'),
        ("a quoted here-string with no space, then the command", "cat <<<'x'\nfabric-pr post-review 1 < r.md"),
        ("single quotes piped to a shell", "printf '%s' 'fabric-pr post-review 12 < r.md' | sh"),
        ("1500 nested evals (F7)", "eval " * 1500 + "fabric-pr post-review 1"),
        # Round 3 of #451: quoting read differently from bash hid a later call (F10), and runners it did not name.
        ("ANSI-C quoting with an escaped quote", "echo $'it\\'s' ; fabric-pr post-review 12 < r.md"),
        ("an indented delimiter inside a quoted heredoc",
         "cat > d.md <<'EOF'\n  EOF\nit's\nEOF\nfabric-pr post-review 12 < r.md"),
        ("an indented delimiter after <<- is spaces, not tabs", "cat <<-'EOF'\n  EOF\nit's\n\tEOF\nfabric-pr post-review 1|x"),
        ("su -c", "su -c 'fabric-pr post-review 12 < r.md' me"),
        ("ssh", "ssh h 'fabric-pr post-review 12 < r.md'"),
        ("the shell's name quoted", "\"bash\" -c 'fabric-pr post-review 12 < r.md'"),
        ("source as a command word", ". /dev/stdin <<'EOF'\nfabric-pr post-review 12 < r.md\nEOF"),
        ("a quote left open over the words", "cd /x; 'fabric-pr post-review 12 < r.md"),
        # `.` reading stdin where the command word was misread (j543, #451 round 4 F11): a brace group, an elif, a
        # case arm, a leading redirection.
        ("source in a brace group", "{ . /dev/stdin <<'EOF'\nfabric-pr post-review 12 < r.md\nEOF\n}"),
        ("source after elif", "if false; then :; elif . /dev/stdin <<'EOF'\nfabric-pr post-review 12 < r.md\nEOF\nthen :; fi"),
        ("source in a case arm", "case x in x) . /dev/stdin <<'EOF'\nfabric-pr post-review 12 < r.md\nEOF\n;; esac"),
        ("source after a leading redirection", "2>/dev/null . /dev/stdin <<'EOF'\nfabric-pr post-review 12 < r.md\nEOF"),
        # A runner by path is one only as a command word (j543, F12); by bare name it still counts anywhere.
        ("a shell by path as the command word", "/bin/bash -c 'fabric-pr post-review 12 < r.md'"),
        ("a shell by path after a wrapper", "sudo /usr/bin/bash -c 'fabric-pr post-review 12 < r.md'"),
        ("a bare shell name as an argument: find -exec", "find . -exec bash -c 'fabric-pr post-review 1' \\;"),
        # A shell by path where the walk misreads the command word: refused unless a reader is the command
        # (review of #501 round 4, F6: each passed at 393cd13c).
        ("a shell by path after sudo -u", "sudo -u root /bin/bash -c 'fabric-pr post-review 12 < r.md'"),
        ("a shell by path after a leading redirection", "2>/dev/null /bin/bash -c 'fabric-pr post-review 12 < r.md'"),
        ("a shell by path after timeout 5s", "timeout 5s /bin/sh -c 'fabric-pr post-review 12 < r.md'"),
        ("a shell by path after timeout -s KILL 60", "timeout -s KILL 60 /bin/bash -c 'fabric-pr post-review 12 < r.md'"),
        ("source -- after a leading redirection (round 4 risk)",
         "2>/dev/null . -- /dev/stdin <<'EOF'\nfabric-pr post-review 12 < r.md\nEOF"),
        ("source of another fd's heredoc (round 4 risk)", "2>/dev/null . /dev/fd/3 3<<'EOF'\nfabric-pr post-review 12 < r.md\nEOF"),
        ("a heredoc fed to a shell by path after 2>&1",
         "2>&1 /usr/bin/bash <<'EOF'\nfabric-pr post-review 12 < r.md\nEOF"),
    ]
    # A command word the walk cannot name, with post-review text or an input on the line (#631 reviews F1, F2; j830).
    # Mutation: post-review-shape-guard.py refused(), `return dynamic` made `return False` (and live_text's flag ignored).
    held = "read -r c <<< 'fabric-pr post-review 1'; "
    unnameable = [
        # What the reviews of #631 named.
        ("a command held in a variable", "x='fabric-pr post-review 1'; $x < r.md"),
        ("read into a variable, run", held + "$c"),
        ("$SHELL -c", "$SHELL -c 'fabric-pr post-review 1 < r.md'"),
        ("an expansion glued to a letter", "read -r c <<< 'abric-pr post-review 1'; f$c < r.md"),
        ("an expansion glued to a letter, the text after it", "c=val; e$c 'fabric-pr post-review 1 < r.md'"),
        ("after timeout 5s", held + "timeout 5s $c < r.md"),
        ("after sudo -u root", held + "sudo -u root $c < r.md"),
        ("after a leading redirection", held + "2>/dev/null $c < r.md"),
        ("after setsid, a wrapper nobody listed", held + "setsid $c < r.md"),
        ("after stdbuf -oL", held + "stdbuf -oL $c < r.md"),
        ("xargs with another replace string", "xargs -0 -I X env -S X <<< 'fabric-pr post-review 1'"),
        ("xargs with {} and env", "xargs -0 -I{} env {} <<< 'fabric-pr post-review 1'"),
        ("the name in a variable, the verb after it", "c='fabric-pr'; \"${c}\" post-review 1"),
        ("a redirection before an expansion holding the whole line", "c='fabric-pr post-review 1'; 2>/dev/null $c"),
        ("an expansion in the shell's path", "c=bash; /bin/${c} -c 'fabric-pr post-review 1'"),
        # Review of #637, F1: a `/` the shell moves or splits around is no boundary of the command's last part.
        ("a slash in a substitution operator", held + "${c/z/z} < r.md"),
        ("a slash in a trailing-slash strip", held + "${c%/} < r.md"),
        ("a slash in a prefix strip", held + "${c##*/} < r.md"),
        ("a slash after a word-split expansion", "c='fabric-pr post-review 1 .'; $c/ < r.md"),
        ("a slash inside a double-quoted operator", held + '"${c//z/z}" < r.md'),
        ("a slash in a default, after the word split", held + "${d:-x/y}$c/ < r.md"),
        ("an unquoted root before the script", "R='fabric-pr post-review 1 .'; $R/bin/fabric-pr < r.md"),
        # F2: a wrapper's option value is no command, whatever PLAIN says of the word.
        ("env -u with a plain value", held + "env -u echo $c < r.md"),
        ("exec -a with a plain value", held + "exec -a echo $c < r.md"),
        ("sudo -u with a plain value", held + "sudo -u test $c < r.md"),
        ("xargs -I with a plain replace string", "xargs -I echo env -S echo <<< 'fabric-pr post-review 1'"),
        ("timeout -s with a plain value", held + "timeout -s true 5 $c < r.md"),
        ("nice -n then exec, with a plain value", held + "nice -n true exec -a printf $c"),
        # F3: a second `-exec` is judged as the first is.
        ("a second find -exec of an expansion",
         "c='fabric-pr post-review 1'; find . -maxdepth 0 -exec true \\; -exec $c \\;"),
        ("a third find -exec of an expansion",
         "c='fabric-pr post-review 1'; find . -exec true \\; -exec echo {} + -exec $c \\;"),
        # F4: the dispatcher runs its noun as a command.
        ("the dispatcher with its noun held", "read -r c <<< 'pr post-review 1'; fabric $c < r.md"),
        ("the dispatcher with the whole line held", "read -r c <<< 'pr post-review 1'; fabric \"$c\" < r.md"),
        # Shapes they did not name.
        ("a command substitution as the command word", "$(echo fabric-pr) post-review 12 < r.md"),
        ("backticks as the command word", "`printf fabric-pr` post-review 12 < r.md"),
        ("ANSI-C quoting spelling the name", "$'\\x66abric-pr' post-review 12 < r.md"),
        ("a glob in the command word", "fabric-p? post-review 12 < r.md"),
        ("a bracket glob in the command word", "/opt/bin/fabric-p[r] post-review 12 < r.md"),
        ("a brace expansion in the command word", "{fabric-pr,x} post-review 12 < r.md"),
        ("xargs feeding a wrapper", "xargs env <<< 'fabric-pr post-review 1'"),
        ("xargs with a command it does not name", "xargs nice -n 5 <<< 'fabric-pr post-review 1'"),
        ("find -exec of an expansion", "c='fabric-pr post-review 1'; find . -maxdepth 0 -exec $c \\;"),
        ("find -exec of a wrapper", "find . -maxdepth 0 -exec env -S 'fabric-pr post-review 1' \\;"),
        ("env -S", "env -S 'fabric-pr post-review 1 < r.md'"),
        ("a loop over quoted lines", "for c in 'fabric-pr post-review 1'; do $c < r.md; done"),
        ("a substitution held in a variable", "cmd=$(echo 'fabric-pr post-review 1'); $cmd < r.md"),
        ("an expansion after exec and nice", held + "nice -n 5 exec $c"),
        ("a parameter operator in the command word", held + "${c%% *} 1 < r.md"),
        ("an expansion in a pipeline's second command", "echo 'fabric-pr post-review 1' | $SHELL"),
        ("after a here-string and a brace group", "{ read -r c <<< 'fabric-pr post-review 1'; }; \"$c\""),
        ("a substitution glued into the name", "fabric-$(echo pr) post-review 12 < r.md"),
    ]
    # Mentions the shell may run, refused on purpose: the deny names the way through (single quotes, a quoted heredoc,
    # a file). Pinned so a change to what is over-reported is a decision, not a drift.
    over_reported = [
        ("an unquoted echo", "echo fabric-pr post-review 12"),
        ("an unquoted echo after a separator", "cd /x && echo fabric-pr post-review 12"),
        ("an unquoted heredoc body", "cat > doc.md <<EOF\nPost with\nfabric-pr post-review 12 < r.md\nEOF"),
        ("a double-quoted commit message", 'git commit -m "post-review: bare form\n\nfabric-pr post-review 12 < r.md"'),
        ("a double-quoted grep", 'grep -E "arm|fabric-pr post-review" docs'),
        ("a redirection target named post-review", "fabric-pr arm 3 > post-review.log"),
        ("a bare runner name as an argument", "grep -rn 'fabric-pr post-review' bash"),
    ]
    allowed = [
        ("the bare form", "fabric-pr post-review 449 --model fable < /home/a/scratchpad/review1.md"),
        ("with --repo", "fabric-pr post-review --repo BlueTeam-OU/agent-fabric-gateway 75 --model fable < report"),
        ("surrounding whitespace", "  fabric-pr post-review 12 < r.md\n"),
        ("a quoted path with spaces", "fabric-pr post-review 12 < '/home/a/my report.md'"),
        ("no report redirected", "fabric-pr post-review 12"),
        ("another fabric-pr subcommand, wrapped", "cd /x && fabric-pr arm 12 --dry-run 2>&1 | tail -5"),
        ("post-review before fabric-pr", "grep -n post-review bin/fabric-pr"),
        # Mentions the shell never runs (review of #451, F2 and F8).
        ("a single-quoted grep", "grep -rn 'fabric-pr post-review' docs/ | head"),
        ("a single-quoted echo with a separator", "echo 'x; fabric-pr post-review 12'"),
        ("a single-quoted gh comment body", "gh pr comment 1 --body '(fabric-pr post-review 12)'"),
        ("a quoted heredoc body, then a command", "cat > d.md <<'EOF'\nx; fabric-pr post-review 1\nEOF\ngit add d.md"),
        ("the commit idiom: a quoted heredoc in a quoted substitution",
         "git commit -F- <<'EOF'\nit's the bare form\n\nfabric-pr post-review 12 < r.md\nEOF"),
        ("the commit idiom with -m \"$(cat <<'EOF' … )\"",
         "git commit -m \"$(cat <<'EOF'\nit's the bare form: fabric-pr post-review 12 < r.md\nEOF\n)\""),
        ("a comment with an apostrophe", "cd x\n# don't use fabric-pr post-review wrapped\nls"),
        ("${VAR} before single-quoted words", "printf %s ${A} 'fabric-pr post-review'"),
        # `.` as an argument is a path, not source (review of #451, F9).
        ("a single-quoted grep of .", "grep -rn 'fabric-pr post-review' ."),
        ("rg of .", "rg 'fabric-pr post-review' ."),
        ("git grep -- .", "git grep -n 'fabric-pr post-review' -- ."),
        ("find . piped to xargs grep", "find . -name '*.md' | xargs grep -l 'fabric-pr post-review'"),
        ("git add . then a quoted-heredoc commit", "git add . && git commit -F- <<'EOF'\nfabric-pr post-review 12\nEOF"),
        ("a <<- heredoc ended by a tab-indented delimiter", "cat <<-'EOF'\n\tfabric-pr post-review 1\n\tEOF\nls"),
        # Each decided by one reading alone, so each is pinned on its own (the F10 cases above fall to the open quote too).
        ("ANSI-C quoting, then a single-quoted mention", "echo $'a\\'b' 'fabric-pr post-review'"),
        ("an indented line like the delimiter inside a quoted heredoc", "cat <<'EOF'\n  EOF\nfabric-pr post-review 1\nEOF\nls"),
        # A path whose last part names a runner, as an argument, runs nothing (j543, #451 round 4 F12).
        ("a single-quoted grep of a directory named ssh", "grep -rn 'fabric-pr post-review' runtime/ssh"),
        ("a single-quoted grep of tests/bash/", "grep -rln 'fabric-pr post-review' tests/bash/x.sh docs/flock"),
        ("git log of a path ending in sh", "git log -S 'fabric-pr post-review' -- policies/watch"),
        # Expansions that are arguments, or a command the walk can name, beside text that mentions the words.
        ("xargs of a plain command", "xargs grep -n foo"),
        ("xargs of grep over the words", "git ls-files | xargs grep -ln 'fabric-pr post-review'"),
        ("fabric-pr gate", "fabric-pr gate 12"),
        ("fabric-pr with an expanded argument", 'fabric-pr arm "$n" --dry-run'),
        ("the script under an expanded directory", 'cd "$d" && "$R"/bin/fabric-pr arm 3 --dry-run'),
        ("an ordinary pipeline", "git log --oneline | head -5 | wc -l"),
        ("an ordinary pipeline with an input and expansions", 'sort < "$f" | uniq -c | head -3'),
        ("a while-read loop over a file", 'while read -r l; do echo "$l"; done < list.txt'),
        ("a commit message from a heredoc in a substitution, the words in it",
         "git commit -m \"$(cat <<'EOF'\nfabric-pr post-review 12 < r.md\nEOF\n)\" && git status"),
        ("an assignment from a substitution", "x=$(date +%s) && git log -S 'post-review' -- docs"),
        ("sudo of a plain command with an expansion", 'sudo grep -n \'fabric-pr post-review\' "$f"'),
        ("timeout of a plain command with an expansion", 'timeout 60 grep -rn \'post-review\' "$d"'),
        ("find -exec of grep with an expanded -name", 'find . -name "$p" -exec grep -l \'fabric-pr post-review\' {} +'),
        ("gh comment with an expanded number", 'gh pr comment "$n" --body \'fabric-pr post-review 12\''),
        ("a for loop over an expansion", 'for f in $files; do grep -l \'post-review\' "$f"; done'),
        ("sed over a variable file", 'sed -i \'s/post-review/x/\' "$f"'),
        ("the test builtin with a glob-looking bracket", "[ -f x ] && grep -n 'post-review' x < /dev/null"),
        ("a stderr redirect before a plain command", "2>/dev/null grep -n 'post-review' bin/fabric-pr"),
        # F5: `[[` is the test builtin, as `[` is.
        ("the [[ test beside post-review text", "[[ -f x ]] && grep -n 'post-review' x"),
        ("the [[ test beside a redirection", "[[ -f x ]] && cat < x"),
        # F1, F2 and F3 must not refuse what they name correctly.
        ("a double-quoted expansion before the slash", 'c=x; "${c}"/bin/fabric-pr arm 3 < /dev/null'),
        ("a slash in an argument's operator", "c=x; grep -n 'post-review' ${c//a/b}"),
        ("sudo -u with a value, then a plain command", 'sudo -u test grep -n \'post-review\' "$f"'),
        ("a second find -exec of grep", "find . -exec true \\; -exec grep -l 'post-review' \"$f\" {} +"),
    ]
    for label, cmd in refused + unnameable:
        check(f"refused: {label}", g.refused(cmd), cmd[:200])
    for label, cmd in over_reported:
        check(f"over-reported: {label}", g.refused(cmd), cmd)
    for label, cmd in allowed:
        check(f"passed: {label}", not g.refused(cmd), cmd)

    # Every command is decided well inside the 5 s the settings give the hook: a hook past its timeout is read as no
    # objection. Each input below took a former version past it (review of #451: F3 22 s, F6 5.7 s and 21 s, F7 a
    # RecursionError), and the last one would make a lazy BARE backtrack.
    for label, cmd in (("100 000 glued separators", ";" * 100000 + " fabric-pr post-review 1 | x"),
                       ("50 000 short commands", "x;" * 50000 + "fabric-pr post-review 1"),
                       ("20 000 unterminated heredocs", "<<a\n" * 20000 + "fabric-pr post-review 1|x"),
                       ("20 000 quoted heredocs and lines", "cat <<'E'\nx\nE\n" * 20000 + "fabric-pr post-review 1|x"),
                       ("100 000 nested evals", "eval " * 100000 + "fabric-pr post-review 1"),
                       ("100 000 spaces after the bare prefix", "fabric-pr post-review" + " " * 100000 + ";"),
                       ("100 000 separators, neither word", ";" * 100000)):
        t = time.monotonic()
        g.refused(cmd)
        took = time.monotonic() - t
        check(f"fast: {label} ({took:.2f} s)", took < 2.0, took)

    # The hook end to end: a deny line on a refused command, nothing otherwise, exit 0 on what it cannot read.
    out = run(json.dumps({"tool_input": {"command": refused[0][1]}}))
    try:
        d = json.loads(out)["hookSpecificOutput"]
        good = (d["hookEventName"], d["permissionDecision"]) == ("PreToolUse", "deny") and "bare" in d["permissionDecisionReason"]
    except (ValueError, KeyError) as e:
        good, d = False, e
    check("hook: a deny decision naming the bare form", good, d)
    check("hook: nothing on the bare form", run(json.dumps({"tool_input": {"command": allowed[0][1]}})) == "")
    for label, payload in (("not JSON", "{"), ("no tool_input", "{}"), ("tool_input a string", '{"tool_input": "x"}'),
                           ("command a number", '{"tool_input": {"command": 3}}')):
        check(f"hook: nothing on {label}", run(payload) == "")

    # A command table it cannot read is no answer "not fabric-pr": the guard refuses a command naming post-review,
    # and still says nothing on one that does not (ADR-068 rule 7; canonical() raises TableError).
    with tempfile.TemporaryDirectory() as tree:
        hooks = os.path.join(tree, "runtime", "claude-code", "hooks")
        os.makedirs(hooks)
        shutil.copy(HOOK, hooks)
        shutil.copytree(os.path.join(HERE, "tools", "fabric", "cli"), os.path.join(tree, "tools", "fabric", "cli"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        with open(os.path.join(tree, "runtime", "claude-code", "commands.json"), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        copy = os.path.join(hooks, os.path.basename(HOOK))

        def run_copy(command: str) -> str:
            payload = json.dumps({"tool_input": {"command": command}})
            return subprocess.run([sys.executable, copy], input=payload, capture_output=True, text=True, check=True).stdout

        out = run_copy(allowed[0][1])
        check("unreadable commands.json: the bare form is refused, not passed",
              '"permissionDecision":"deny"' in out, out)
        check("unreadable commands.json: a command without post-review is passed", run_copy("ls -la") == "")

    # Control: the guard is registered where every session runs it, in both settings files.
    for rel in (".claude/settings.json", "runtime/claude-code/workspace/settings.json"):
        with open(os.path.join(HERE, rel), encoding="utf-8") as fh:
            pre = json.load(fh)["hooks"]["PreToolUse"]
        hooked = [h["command"] for e in pre if e.get("matcher") == "Bash" for h in e["hooks"]]
        check(f"registered on Bash in {rel}", any("post-review-shape-guard.py" in c for c in hooked), hooked)

    print(f"{'PASS' if not fails else 'FAIL'}: post-review shape guard ({fails} failed)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
