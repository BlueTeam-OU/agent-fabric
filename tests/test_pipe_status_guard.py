#!/usr/bin/env python3
"""runtime/claude-code/hooks/pipe-status-guard.sh (Claude Code PreToolUse hook on Bash) — Wave 9 batch 5.

The oracle is the bash test test_pipe-status-guard.sh (deleted with the port), ported case for case (its 27 refused commands and 6 allowed ones are the
first entries of the lists below, in order); the cases it missed are marked NEW. The hook is driven through ONE
constant, ENTRY, the command the harness runs (`bash "<path>"`, the payload on stdin), so this file runs unchanged
against the bash and against the Python port behind the same path.
$PIPE_STATUS_GUARD_HOOK aims it at another file (the module that replaces the script): that file is then run as a program,
by its shebang, from its absolute path.

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
import hook_harness  # noqa: E402 — tests/, the script's own directory
HOOK = os.path.abspath(os.environ.get("PIPE_STATUS_GUARD_HOOK") or hook_harness.unmanaged("pipe-status-guard.sh"))
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


def _load_guard():
    """The guard module itself, for the oracle, which asks drain_piped directly."""
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runtime", "claude-code", "hooks", "pipe-status-guard.py")
    spec = importlib.util.spec_from_file_location("pipe_status_guard_oracle", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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

    def test_a_gzcoord_inbox_drain_piped_into_anything_is_refused(self):                     # python-dev-01, 2026-11-24
        drains = ["gzcoord-inbox | head -15", "gzcoord-inbox 2>&1 | tail", "timeout 60 gzcoord-inbox | grep REQUEST",
                  "fabric gzcoord inbox | head", "/srv/af/bin/gzcoord-inbox | head", "cd x && gzcoord-inbox | wc -l",
                  "ls\ngzcoord-inbox | head", "FOO=1 gzcoord-inbox|head", "gzcoord-inbox --wait 3 | head",
                  "gzcoord-inbox --until-delivery | tail -5",
                  # review of #703: F2, the = form is no mode word to gzcoord-inbox, so it drains; F3, the shapes a
                  # shell still runs as a piped drain; F4, a real drain after a here-document whose body has a quote.
                  "gzcoord-inbox --replay=3 | head", "gzcoord-inbox --history=5|head",
                  "gzcoord-inbox \\\n  | head", "if gzcoord-inbox | grep -q x; then echo; fi", "(gzcoord-inbox) | head",
                  "{ gzcoord-inbox; } | head", "2>/dev/null gzcoord-inbox | head", "timeout -s KILL 60 gzcoord-inbox | head",
                  "env timeout 5 gzcoord-inbox | head", "nice -n 5 gzcoord-inbox | head", "! gzcoord-inbox | head",
                  "cat <<EOF\ndon't\nEOF\ngzcoord-inbox | head",
                  # review of #703 round 2: F3, a fused `)|`; F10, `<<` that opens no here-document drops no line;
                  # F11, `time -p`.
                  "(gzcoord-inbox)|head", "(gzcoord-inbox)| head",
                  'jq . <<< "hello"\ngzcoord-inbox | head', "echo $((1<<N))\ngzcoord-inbox | head",
                  'echo "a <<EOF"\ngzcoord-inbox | head', "time -p gzcoord-inbox | head",
                  # a here-string is no here-document even when a later line equals its word
                  "cat <<< X\ngzcoord-inbox | head\nX",
                  # review of #703 round 3: F14 and the comment hole, and the shapes the real-bash oracle below found.
                  "time { gzcoord-inbox; } | head", "time ! gzcoord-inbox | head", "# note\ngzcoord-inbox | head",
                  "ls # x\ngzcoord-inbox | head", "echo a#b; gzcoord-inbox | head", "exec gzcoord-inbox | head",
                  'echo "usage: cat <<EOF"\ngzcoord-inbox | head -5\ncat > n <<EOF\nx\nEOF',
                  "for i in 1; do gzcoord-inbox; done | head", "{ gzcoord-inbox; echo done; } | head",
                  # refused by design: the rule errs on refusing. A pipe after a drain that does not read it, and a
                  # here-document body or comment that holds a piped drain, are refused like a piped drain.
                  "gzcoord-inbox; ls | head", "cat > notes.md <<'EOF'\ngzcoord-inbox | head hid two of three\nEOF",
                  "git commit -F - <<'EOF'\ngzcoord-inbox | head\nEOF"]
        for c in drains:
            with self.subTest(command=c):
                r = self.run_hook({"tool_name": "Bash", "tool_input": {"command": c}})
                out = json.loads(r.stdout)["hookSpecificOutput"]
                self.assertEqual(out["permissionDecision"], "deny")
                self.assertIn("DRAINS the inbox", out["permissionDecisionReason"])
                self.assertIn("fabric-history", out["permissionDecisionReason"])
        # The journal and relay readers consume nothing; a drain unpiped or to a file hides nothing; a word that is
        # not the command (grep's pattern, an echo's string) is no drain.
        for c in ("gzcoord-inbox", "gzcoord-inbox > log; cat log",
                  "gzcoord-inbox --history 5 | head", "gzcoord-inbox --held | head", "gzcoord-inbox --replay 3 | head",
                  "grep gzcoord-inbox x | head", "grep -rn gzcoord-inbox . | head", "ls | gzcoord-inbox",
                  "( cd x; ls ) | head", "echo 'gzcoord-inbox | head'", "gzcoord-inbox || echo none",
                  "cat <<'EOF'\nno pipe here: gzcoord-inbox\nEOF"):
            with self.subTest(command=c):
                self.assertEqual(self.decision(c), "allow")

    def test_real_bash_never_pipes_a_drain_the_guard_allows(self):                         # review of #703 round 3
        """The oracle: a stub gzcoord-inbox records whether its stdout is a pipe; each command runs under real bash with
        its own stdout a file, and wherever the stub ran piped (and moved a cursor) the guard must refuse. The rounds of
        #703 found a bypass each time the guard was read against a list; this reads it against bash."""
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("no bash")
        pipe_guard = _load_guard()
        stub_dir = os.path.join(self.tmp, "oracle-bin")
        os.makedirs(stub_dir)
        stub = os.path.join(stub_dir, "gzcoord-inbox")
        with open(stub, "w", encoding="utf-8") as fh:
            fh.write('#!/bin/sh\nif [ -p /dev/stdout ]; then echo piped >> "$ORACLE_LOG"; else echo plain >> "$ORACLE_LOG"; fi\necho m\n')
        os.chmod(stub, 0o755)
        heads = ["", "time ", "time -p ", "! ", "2>/dev/null ", "FOO=1 ", "env ", "exec "]
        cores = ["gzcoord-inbox", "{ gzcoord-inbox; }", "(gzcoord-inbox)", "{ gzcoord-inbox; echo x; }",
                 "for i in 1; do gzcoord-inbox; done", "gzcoord-inbox 2>&1"]
        tails = [" | head -1", "| head -1", " |& head -1", "\n"]
        pre = ["", "# c\n", "cat <<EOF\ndon't\nEOF\n", "echo \"x <<EOF\"\n"]
        piped_seen = 0
        for p in pre:
            for h in heads:
                for c in cores:
                    for t in tails:
                        cmd = p + h + c + t
                        log = os.path.join(self.tmp, "oracle.log")
                        with open(os.path.join(self.tmp, "oracle.out"), "w") as out:
                            subprocess.run([bash, "-c", cmd], env={"PATH": stub_dir + ":/usr/bin:/bin", "ORACLE_LOG": log},
                                           stdout=out, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=20)
                        runs = open(log).read().split() if os.path.exists(log) else []
                        if os.path.exists(log):
                            os.remove(log)
                        if "piped" in runs:
                            piped_seen += 1
                            with self.subTest(command=cmd):
                                self.assertTrue(pipe_guard.drain_piped(cmd), "bash piped the drain and the guard allowed it")
        self.assertGreater(piped_seen, 100, "the oracle's control: bash did pipe the stub")

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
