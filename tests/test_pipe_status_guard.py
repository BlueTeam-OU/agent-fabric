#!/usr/bin/env python3
"""runtime/claude-code/hooks/pipe-status-guard.sh (Claude Code PreToolUse hook on Bash) — Wave 9 batch 5.

The oracle is test_pipe-status-guard.sh, ported case for case (its 27 refused commands and 6 allowed ones are the
first entries of the lists below, in order); the cases it missed are marked NEW. The hook is driven through ONE
constant, ENTRY, the command the harness runs (`bash "<path>"`, the payload on stdin), so this file runs unchanged
against the bash and against the Python port behind the same path.

Contract held still: a check piped into a filter and chained with && into a commit, a push, or a merge or creation
of a pull request is denied, because the chain tests the filter's exit status; the same command with the status
captured, a pipe that no write follows, and a `;` after the pipe are allowed; `pipefail` is no exemption (a hook
cannot tell a real one from one in an echo or a comment); input it cannot parse is allowed in silence; exit 0 always.
NEW: the denial's shape (event PreToolUse, the one JSON line, the advice to capture the status); `gh pr create`
chained; other filters; `||` is not `&&`; an empty or missing command and a missing jq allow in silence; exit 0
on every decision.

Mutations each list fails on: the filter alternation shortened (`tail` removed); the `&`-stripping sed removed
(the redirection spellings); the newline flattening removed (the multi-line command); a pipefail exemption
added (the pipefail spellings); `;` allowed to carry the chain; deny turned into allow; exit 2 on bad JSON.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

FABRIC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.environ.get("PIPE_STATUS_GUARD_HOOK") or os.path.join(FABRIC, "runtime", "claude-code", "hooks", "pipe-status-guard.sh")
if not os.path.isfile(HOOK):
    sys.exit(f"test: not found: {HOOK}")
# The tracked hook is what the harness runs as `bash <path>`; an override is run as a program (its shebang), the way
# tab-title's oracle runs $TAB_TITLE_HOOK, so it can name the module that replaces the script.
ENTRY = [HOOK] if os.environ.get("PIPE_STATUS_GUARD_HOOK") else ["bash", HOOK]
SAFE_PATH = "/usr/bin:/bin"

REFUSED = [
    'python3 tests/test_adr.py | tail -1 && git commit -q -m x',
    'bash tests/run.sh 2>&1 | tail -3 && git add -A && git commit -m y',
    'lint | grep -q clean && git push -q origin HEAD',
    'python3 t.py | head -5 && git -C /repo commit -m z',
    'check | tail -1 && gh pr merge 53 --merge',
    'python3 t.py \\\n  | tail -1 \\\n  && git commit -m multi',
    'set +o pipefail; false | tail -1 && git commit -m bad',
    'echo pipefail; check | tail -1 && git commit -m bad',
    'check | tail -1 && git commit -m "pipefail"',
    'set -o pipefail; set +o pipefail; x | tail -1 && git push',
    'set -o pipefail; python3 t.py | tail -1 && git commit -m x',
    'echo set -o pipefail; false | tail -1 && git commit -m x',
    '# set -o pipefail\nfalse | tail -1 && git commit -m x',
    '( set -o pipefail ); false | tail -1 && git commit -m x',
    'check | tail -3 2>&1 && git commit -m x',
    'check |& tail -3 && git commit -m x',
    'check | grep -q ok >/dev/null 2>&1 && git push',
    'check | tail -1 &> log && git commit',
    'check | tail -1 && git --no-pager commit -m x',
    'check 2>&1 | tail -1 && git -c core.hooksPath=x commit -m x',
    'check | tail -1 >& log && git commit -m x',
    'check | tail -1 >&log && git commit -m x',
    'check | tail -1 >&"$f" && git commit -m x',
    'check | tail -1 2>& 1 && git push',
    'check | tail -1 <&0 && git commit -m x',
    'echo "note: set -o pipefail"; false | tail -1 && git commit -m x',
    'check | tail -1 && git -C "my dir" commit -m x',
    # NEW: the other write the hook names, and other filters
    'check | tail -1 && gh pr create --fill',
    'check | wc -l && git push --force-with-lease',
    'check | awk 1 && git commit -m x',
    'check | tee log && git commit -m x',
]
ALLOWED = [
    'python3 t.py > log 2>&1; rc=$?; [ $rc -eq 0 ] && git commit -m x',
    'git log --oneline | head -3',
    'grep -q x file && git commit -m y',
    'python3 t.py | tail -1; echo done',
    'git commit -q -m "a message | tail with a pipe in it"',
    'git status --short | head; git push -q origin HEAD',
    # NEW: `||` is not a chain on success, and a write with no pipe before it
    'check | tail -1 || git commit -m x',
    'git add -A && git commit -m x',
    'check && git push',
    # NEW: a `;` ends what the pipe's status can reach; a later && chain is another command's
    'check | tail -1; echo done && git commit -m x',
    'git status | head; make test && git push -q',
]
CHAINED = "check | tail -1 && git commit -m x"


class Guard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="psg-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def run_hook(self, payload, path=SAFE_PATH):
        data = payload if isinstance(payload, str) else json.dumps(payload)
        env = {"PATH": path, "HOME": self.tmp, "TMPDIR": self.tmp, "LANG": "C.UTF-8"}
        return subprocess.run(ENTRY, input=data, capture_output=True, text=True, env=env, cwd=self.tmp, timeout=60, check=False)

    def decision(self, command) -> str:
        r = self.run_hook({"tool_name": "Bash", "tool_input": {"command": command}})
        self.assertEqual(r.returncode, 0, f"exit 0 always: {r.stderr!r}")
        if r.stdout == "":
            return "allow"
        return json.loads(r.stdout).get("hookSpecificOutput", {}).get("permissionDecision", "malformed")

    def test_a_filtered_check_chained_into_a_write_is_refused(self):
        for c in REFUSED:
            with self.subTest(command=c):
                self.assertEqual(self.decision(c), "deny")

    def test_the_status_captured_or_no_write_after_the_pipe_is_allowed(self):
        for c in ALLOWED:
            with self.subTest(command=c):
                self.assertEqual(self.decision(c), "allow")

    def test_the_denial_is_one_json_line_on_the_pre_tool_use_event_and_gives_the_way_through(self):   # NEW
        r = self.run_hook({"tool_name": "Bash", "tool_input": {"command": CHAINED}})
        self.assertEqual(len(r.stdout.splitlines()), 1)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual((out["hookEventName"], out["permissionDecision"]), ("PreToolUse", "deny"))
        self.assertIn("rc=$?", out["permissionDecisionReason"])
        self.assertIn("commit only on 0", out["permissionDecisionReason"])

    def test_a_malformed_input_allows_and_says_nothing(self):                                  # the first payload is the bash test's; the rest are NEW
        for payload in ("not json", "", "{}", '{"tool_input":{}}', '{"tool_input":{"command":""}}'):
            with self.subTest(payload=payload):
                r = self.run_hook(payload)
                self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_without_jq_it_allows_in_silence(self):                                            # NEW
        tools = os.path.join(self.tmp, "tools")
        os.makedirs(tools)
        for name in ("bash", "env", "python3", "cat", "tr", "sed", "grep"):
            found = shutil.which(name, path=SAFE_PATH)
            if found:
                os.symlink(found, os.path.join(tools, name))
        r = self.run_hook({"tool_name": "Bash", "tool_input": {"command": CHAINED}}, path=tools)
        self.assertEqual((r.returncode, r.stdout), (0, ""), "a fence against a habit, not a sandbox: no jq, no judgement")
        control = self.run_hook({"tool_name": "Bash", "tool_input": {"command": CHAINED}})
        self.assertIn("deny", control.stdout, "the same command with jq present is refused")


if __name__ == "__main__":
    unittest.main()
