#!/usr/bin/env python3
"""Tests for runtime/claude-code/hooks/post-review-shape-guard.py: which
`fabric-pr post-review` calls are refused as not bare, which pass, and the
hook's protocol end to end (j540)."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
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
        ("wrapped, with an unclosed quote shlex cannot split", "cd /x && fabric-pr post-review 12 < 'r.md"),
    ]
    allowed = [
        ("the bare form", "fabric-pr post-review 449 --model fable < /home/a/scratchpad/review1.md"),
        ("with --repo", "fabric-pr post-review --repo BlueTeam-OU/agent-fabric-gateway 75 --model fable < report"),
        ("surrounding whitespace", "  fabric-pr post-review 12 < r.md\n"),
        ("a quoted path with spaces", "fabric-pr post-review 12 < '/home/a/my report.md'"),
        ("no report redirected", "fabric-pr post-review 12"),
        ("another fabric-pr subcommand, wrapped", "cd /x && fabric-pr arm 12 --dry-run 2>&1 | tail -5"),
        ("a grep for the words", "grep -rn 'fabric-pr post-review' docs/ | head"),
        ("an echo of the words", "echo fabric-pr post-review 12"),
        ("post-review before fabric-pr", "grep -n post-review bin/fabric-pr"),
        # Words that only name a post-review after a separator inside quotes or a heredoc (review of #451, F2).
        ("a heredoc body line", "cat > doc.md <<EOF\nPost with\nfabric-pr post-review 12 < r.md\nEOF"),
        ("a quoted heredoc body, then a command", "cat > d.md <<'EOF'\nx; fabric-pr post-review 1\nEOF\ngit add d.md"),
        ("a commit message body", 'git commit -m "post-review: bare form\n\nfabric-pr post-review 12 < r.md"'),
        ("an echo with a separator inside quotes", 'echo "x; fabric-pr post-review 12"'),
        ("a grep alternation", 'grep -E "arm|fabric-pr post-review" docs'),
        ("a gh comment body", 'gh pr comment 1 --body "(fabric-pr post-review 12)"'),
        ("an unquoted echo after a separator", "cd /x && echo fabric-pr post-review 12"),
        ("a redirection target", "fabric-pr arm 3 > post-review.log"),
    ]
    for label, cmd in refused:
        check(f"refused: {label}", g.refused(cmd), cmd)
    for label, cmd in allowed:
        check(f"passed: {label}", not g.refused(cmd), cmd)

    # A long separator-dense command is decided well inside the 5 s the settings give the hook (review of #451, F3:
    # the regex this replaced took 22 s on 100 000 separators, and a hook past its timeout is read as no objection).
    for label, cmd in (("100 000 separators naming both words", ";" * 100000 + " fabric-pr post-review 1 | x"),
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
