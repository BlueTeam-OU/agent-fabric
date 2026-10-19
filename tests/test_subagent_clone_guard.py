#!/usr/bin/env python3
"""runtime/claude-code/hooks/subagent-clone-guard.sh (Claude Code PreToolUse hook) — Wave 9 batch 5.

The oracle is test_subagent-clone-guard.sh, ported case for case; the cases it missed are marked NEW. The hook is
driven through ONE constant, ENTRY, the command the harness runs (`bash "<path>"`, the payload on stdin), so this
file runs unchanged against the bash and against the Python port behind the same path. The review Bash fence
(review-bash-guard.sh) sits beside the hook and is not under test here: only that the hook hands Bash to it.

Contract held still: a capability-class subagent (agent_id present, agent_type one of code-low, code-medium,
code-high, code-plan, code-review, general-purpose, claude, Explore, Plan) whose cwd is not under
.claude/worktrees/ may not use Write, Edit, MultiEdit or NotebookEdit (deny) and gets the review fence on Bash;
the main session (no agent_id), a fork, an unknown type, an isolated subagent and any other tool are untouched; a
guard that cannot run asks, never allows; exit 0 always.
Cases of the bash test: main session (2), nine types denied Write, three other write tools, Bash fence (4 denied,
2 allowed read-only), isolated worktree (3), types left alone (2), other tools (2), the denial's two facts, jq
missing asks, malformed payloads never exit 2 (3).
NEW: a writing class's refusals name its type, the clone and the way out, the review class's keep the fence's wording (j228,
added to the bash test after the first port); exit status 0 and one JSON line on a denial; a worktree boundary (a path that only ends at .claude/worktrees
is not inside one); an absent cwd, agent_type or tool_name; the denial names the type and the tool; the Bash
decision of the fence passes through unchanged (an allowed command is rewritten to run with a clean environment).

Mutations each case set fails on: the agent_id test removed (main session); a type dropped from the case list;
the worktree test inverted or loosened to `*/.claude/*`; Write dropped from the denied tools; Bash not handed to
the fence; the jq ask replaced by an allow; exit 2 on bad JSON.
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
HOOK = os.environ.get("SUBAGENT_CLONE_GUARD_HOOK") or os.path.join(FABRIC, "runtime", "claude-code", "hooks", "subagent-clone-guard.sh")
if not os.path.isfile(HOOK):
    sys.exit(f"test: not found: {HOOK}")
# The tracked hook is what the harness runs as `bash <path>`; an override is run as a program (its shebang), the way
# tab-title's oracle runs $TAB_TITLE_HOOK, so it can name the module that replaces the script.
ENTRY = [HOOK] if os.environ.get("SUBAGENT_CLONE_GUARD_HOOK") else ["bash", HOOK]
SAFE_PATH = "/usr/bin:/bin"
TYPES = ["code-low", "code-medium", "code-high", "code-plan", "code-review", "general-purpose", "claude", "Explore", "Plan"]


class Guard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sc-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.clone = os.path.join(self.tmp, "fixture-clone")
        self.worktree = os.path.join(self.clone, ".claude", "worktrees", "agent-abc")

    def run_hook(self, payload, path=SAFE_PATH):
        data = payload if isinstance(payload, str) else json.dumps(payload)
        env = {"PATH": path, "HOME": self.tmp, "TMPDIR": self.tmp, "LANG": "C.UTF-8"}
        return subprocess.run(ENTRY, input=data, capture_output=True, text=True, env=env, cwd=self.tmp, timeout=60, check=False)

    def payload(self, tool, agent_type, cwd, command=""):
        p = {"tool_name": tool, "cwd": cwd, "tool_input": {"command": command}}
        if agent_type is not None:
            p.update(agent_id="a1", agent_type=agent_type)
        return p

    def decision(self, tool, agent_type, cwd, command="") -> str:
        r = self.run_hook(self.payload(tool, agent_type, cwd, command))
        self.assertEqual(r.returncode, 0, f"exit 0 always: {r.stderr!r}")
        if r.stdout == "":
            return "allow"
        out = json.loads(r.stdout)["hookSpecificOutput"]
        # a command rewritten to run with a clean environment, and no decision, is an allow
        return out.get("permissionDecision") or ("allow" if "updatedInput" in out else "malformed")

    def test_the_main_session_is_never_touched(self):
        self.assertEqual(self.decision("Write", None, self.clone), "allow")
        self.assertEqual(self.decision("Bash", None, self.clone, "git push"), "allow", "the session's own rules apply")

    def test_a_class_subagent_in_the_session_clone_may_not_write(self):
        for t in TYPES:
            with self.subTest(agent_type=t):
                self.assertEqual(self.decision("Write", t, self.clone), "deny")
        for tool in ("Edit", "MultiEdit", "NotebookEdit"):
            with self.subTest(tool=tool):
                self.assertEqual(self.decision(tool, "code-medium", self.clone), "deny")

    def test_its_bash_gets_the_review_fence(self):
        # (command, agent_type) as the bash test pairs them
        for cmd, agent in (("git push origin x", "code-high"), ("git commit -m x", "code-low"), ("pnpm install", "code-high"), ("echo x > notes.md", "code-medium")):
            with self.subTest(command=cmd):
                self.assertEqual(self.decision("Bash", agent, self.clone, cmd), "deny")
        for cmd, agent in (("git log --oneline -3", "code-high"), ("git diff main..HEAD", "code-low")):
            with self.subTest(command=cmd):
                self.assertEqual(self.decision("Bash", agent, self.clone, cmd), "allow")

    def test_the_fence_s_answer_passes_through_unchanged(self):                                   # NEW
        r = self.run_hook(self.payload("Bash", "code-high", self.clone, "git log --oneline -3"))
        self.assertEqual(r.returncode, 0)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "PreToolUse")
        self.assertNotIn("permissionDecision", out)
        self.assertIn("git log --oneline -3", out["updatedInput"]["command"], "the command is kept")
        denied = self.run_hook(self.payload("Bash", "code-high", self.clone, "git push origin x"))
        self.assertEqual(json.loads(denied.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_isolated_in_a_worktree_the_same_subagent_may_write(self):
        self.assertEqual(self.decision("Write", "code-high", self.worktree), "allow")
        self.assertEqual(self.decision("Bash", "code-low", self.worktree, "git add -A"), "allow", "isolation is the fence there")
        self.assertEqual(self.decision("Write", "code-medium", os.path.join(self.worktree, "apps", "x")), "allow", "nested deeper still counts")

    def test_only_a_path_inside_a_worktree_counts_as_isolated(self):                                # NEW
        for cwd in (os.path.join(self.clone, ".claude", "worktrees"), os.path.join(self.clone, ".claude"), self.clone + "/worktrees/agent-1",
                    self.clone + "/.claude-worktrees/agent-1"):
            with self.subTest(cwd=cwd):
                self.assertEqual(self.decision("Write", "code-high", cwd), "deny")
        self.assertEqual(self.decision("Write", "code-high", "/a/b/.claude/worktrees/c"), "allow", "any parent holds the worktrees")

    def test_types_this_control_plane_does_not_dispatch_are_left_alone(self):
        self.assertEqual(self.decision("Write", "fork", self.clone), "allow")
        self.assertEqual(self.decision("Write", "some-other-agent", self.clone), "allow")
        self.assertEqual(self.decision("Write", "Code-High", self.clone), "allow", "a type is matched exactly")             # NEW

    def test_a_tool_it_is_not_matched_on_passes_through(self):
        self.assertEqual(self.decision("Read", "code-high", self.clone), "allow")
        self.assertEqual(self.decision("Grep", "code-high", self.clone), "allow")

    def test_absent_fields_are_read_as_the_bash_reads_them(self):                                  # NEW
        r = self.run_hook({"tool_name": "Write", "agent_id": "a1", "agent_type": "code-high", "tool_input": {}})
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "deny", "no cwd: not isolated")
        self.assertEqual(self.run_hook({"tool_name": "Write", "agent_id": "a1", "cwd": self.clone, "tool_input": {}}).stdout, "", "no agent_type: left alone")
        self.assertEqual(self.run_hook({"agent_id": "a1", "agent_type": "code-high", "cwd": self.clone, "tool_input": {}}).stdout, "", "no tool_name: not a tool it is matched on")
        self.assertEqual(self.run_hook({"tool_name": "Write", "agent_id": "", "agent_type": "code-high", "cwd": self.clone}).stdout, "", "an empty agent_id is the main session")

    def test_the_denial_says_why(self):
        r = self.run_hook(self.payload("Write", "code-high", self.clone))
        self.assertEqual(len(r.stdout.splitlines()), 1)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual((out["hookEventName"], out["permissionDecision"]), ("PreToolUse", "deny"))
        reason = out["permissionDecisionReason"]
        self.assertIn("session clone", reason)
        self.assertIn("isolation worktree", reason)
        self.assertIn("This code-high subagent runs in the session clone", reason)
        self.assertIn("may not use Write", reason)
        self.assertIn("resumed by SendMessage", reason)                                                # j228: why it is here

    def reason(self, tool, agent_type, command="") -> str:
        r = self.run_hook(self.payload(tool, agent_type, self.clone, command))
        return json.loads(r.stdout)["hookSpecificOutput"].get("permissionDecisionReason", "")

    def test_a_writing_class_resumed_in_the_clone_is_told_why_in_every_refusal(self):          # j228; in the bash test, not the first port
        r = self.reason("Bash", "code-medium", "git commit -m x")
        self.assertIn(f"This code-medium subagent runs in the session clone ({self.clone})", r)
        self.assertIn("dispatch a new one with isolation worktree", r)
        self.assertIn("The read-only fence says: ", r)
        r = self.reason("Write", "code-low")
        self.assertIn("This code-low subagent runs in the session clone", r)
        self.assertIn("It may not use Write.", r)

    def test_the_review_class_keeps_the_fence_s_own_wording(self):                              # j228; in the bash test, not the first port
        self.assertIn("The review class runs in the session clone and is read-only: it may not use Write.", self.reason("Write", "code-review"))
        r = self.reason("Bash", "code-review", "git commit -m x")
        self.assertNotIn("subagent runs in the session clone", r)
        self.assertIn("The review class", r)

    def test_a_guard_that_cannot_run_asks_it_never_silently_allows(self):
        tools = os.path.join(self.tmp, "tools")
        os.makedirs(tools)
        for name in ("bash", "env", "python3", "cat"):
            found = shutil.which(name, path=SAFE_PATH)
            if found:
                os.symlink(found, os.path.join(tools, name))
        r = self.run_hook(self.payload("Write", "code-high", self.clone), path=tools)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "ask", "with jq unavailable")
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["hookEventName"], "PreToolUse")

    def test_malformed_input_never_exits_2(self):
        for payload in ("{}", "not json", ""):
            with self.subTest(payload=payload):
                self.assertNotEqual(self.run_hook(payload).returncode, 2)


if __name__ == "__main__":
    unittest.main()
