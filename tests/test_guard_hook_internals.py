#!/usr/bin/env python3
"""The internals of the Wave 9 batch 5 guard modules (ADR-040 §5 rule 5: the port adds Python tests for them).

The oracles (test_model_switch_guard.py, test_pipe_status_guard.py, test_subagent_clone_guard.py) hold each hook's
behaviour from outside; these hold what the oracles cannot reach:
  - pipe-status-guard.py decides its ERE by hand, in linear time. The ERE, compiled here as one Python pattern from
    the bash's text, must agree with it on generated commands; a 64 KiB hostile command must be decided in well
    under a second (the pattern took 9 s on 4 KB: a hook past the harness's timeout is no objection).
  - hook_jq.py reads a payload as jq 1.8 did: a stream, a failure on one value, the exit status of the last.
  - subagent-clone-guard.py splits jq's joined line as bash's `read -r` did.
They also hold what the oracles let through (the mutations that survived them, 2026-10-19): the newline or the `\ `
flattening removed, a filter matched without its word boundary, the cwd cut at its first space, `// ""` taking false
as present. Mutations each test fails on: a filter, the `;` test, an option argument or a word boundary dropped from
refused(); the flattening removed; a failed last value exiting 0; indexing a non-object giving null; a parse error
ending quietly; trailing newlines kept; a decision written loose; read -r's last name losing the rest.
"""
from __future__ import annotations

import importlib.util
import os
import random
import re
import sys
import time
import unittest

FABRIC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(FABRIC, "runtime", "claude-code", "hooks")
sys.path.insert(0, HOOKS)
import hook_jq  # noqa: E402


def load(stem: str):
    spec = importlib.util.spec_from_file_location(stem.replace("-", "_"), os.path.join(HOOKS, stem + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PSG = load("pipe-status-guard")
SCG = load("subagent-clone-guard")

# The bash's expression, its [[:space:]] read as GNU grep reads it in a UTF-8 locale.
SP = r"[^\S\x1c-\x1f\x85\xa0  ]"
NSP = r"[\S\x1c-\x1f\x85\xa0  ]"
WRITE = (rf"(git({SP}+-{NSP}+({SP}+(\"[^\"]*\"|'[^']*'|(?!-){NSP}{NSP}*))?)*{SP}+(commit|push)"
         rf"|gh{SP}+pr{SP}+(merge|create))")
ERE = re.compile(rf"\|{SP}*(tail|head|grep|sed|cut|wc|awk|sort|uniq|tee)\b[^;]*&&.*\b{WRITE}\b")
TOKENS = ["|", "| ", "tail", "tail -1", "teee", "grep", "sed", "&&", "&", ";", "git", " ", "  ", "\t", " ", "\xa0",
          "\x1c", "-C", "-", "--", '"', "'", '"a b"', "'c d'", "x", "commit", "push", "commitx", "_", "gh", "pr", "merge",
          "create", "\\ ", "\n", "é", "́", "-c", "k=v", "git-push", "pgit", "|tail&&git push"]


class PipeStatus(unittest.TestCase):
    def agree(self, commands) -> int:
        refused = 0
        for cmd in commands:
            want = ERE.search(PSG.flatten(cmd)) is not None
            refused += want
            self.assertEqual(PSG.refused(cmd), want, repr(cmd))
        return refused

    def test_the_hand_decision_agrees_with_the_expression(self):
        rng = random.Random(20261019)
        loose = ("".join(rng.choice(TOKENS) for _ in range(rng.randint(1, 18))) for _ in range(20000))
        self.assertGreater(self.agree(loose), 1000, "the loose generator reaches the refusals")

    def test_it_agrees_on_commands_shaped_like_the_chain(self):
        rng = random.Random(19)
        pick = rng.choice
        filters = ["tail -1", "grep -q ok", "teee", "wc -l", "sortx", "head"]
        seps = [" && ", " ; ", " || ", " & ", " ;x && ", "&&", " && x; y && "]
        options = ["", " -C dir", ' -C "my dir"', " -C 'a b'", " -c k=v", " --no-pager", " -C", " -", " -- x", ' -c "', " -C -x"]
        writes = [" commit -m x", " push", " pushx", " status", " push", "\\\n commit", " commit_"]

        def chain():
            git = "git" + "".join(pick(options) for _ in range(rng.randint(0, 3))) + pick(writes)
            gh = "gh pr " + pick(["merge 5", "create --fill", "view", "mergex"])
            return (pick(["check", "x 2>&1", ""]) + pick([" | ", "|", " |& ", " "]) + pick(filters) + pick(seps)
                    + pick(["", "y && ", "echo ; "]) + pick([git, git, gh]))
        self.assertGreater(self.agree(chain() for _ in range(20000)), 2000, "the shaped generator reaches the refusals")

    def test_a_hostile_command_is_decided_in_linear_time(self):
        k = 64 * 1024
        for cmd in ("| tail && git -C 'a' -c " * (k // 24), "| tail " + "&& git " * (k // 7),
                    "| tail && git " + "-C git " * (k // 8), "| tail &&" + " " * k + "git push"):
            start = time.monotonic()
            PSG.refused(cmd)
            self.assertLess(time.monotonic() - start, 2.0, cmd[:40])

    def test_the_named_cases(self):
        self.assertTrue(PSG.refused('check | tail -1 && git -C "my dir" commit -m x'))
        self.assertTrue(PSG.refused("check | tail -1 && git push"), "an em space is grep's [[:space:]]")
        self.assertFalse(PSG.refused("check | tail -1 && git\xa0push"), "a no-break space is not")
        self.assertFalse(PSG.refused("check | tail -1; x && git push"))
        self.assertFalse(PSG.refused("check | teee && git push"), "a filter is a whole word")
        # A continuation between git and its subcommand: the flattening (newline, then `\ `) is what joins them.
        self.assertTrue(PSG.refused("check | tail -1 && git \\\n  commit -m x"))
        self.assertTrue(PSG.refused("check | tail -1 && git\\\ncommit -m x"))


class Jq(unittest.TestCase):
    def field(self, value):
        return [hook_jq.alt(hook_jq.index(value, "a"), "")]

    def test_a_stream_exits_by_its_last_value(self):
        self.assertEqual(hook_jq.run('[3] {"a":1}', self.field), ([1], True))
        self.assertEqual(hook_jq.run('{"a":1} [3]', self.field), ([1], False))
        self.assertEqual(hook_jq.run('{"a":1} junk', self.field), ([1], False))
        self.assertEqual(hook_jq.run('{"a":1}{"a":2}', self.field), ([1, 2], True))
        self.assertEqual(hook_jq.run("", self.field), ([], True))

    def test_null_and_false_are_absent_and_nan_is_null(self):
        self.assertEqual(hook_jq.run('{"a":false} {"a":null} null {"a":NaN}', self.field)[0], ["", "", "", ""])
        self.assertEqual(hook_jq.run('"s"', self.field), ([], False))

    def test_what_jq_refuses_to_parse(self):
        self.assertFalse(hook_jq.run('{"a":"\\ud800"}', self.field)[1], "a lone surrogate")
        self.assertFalse(hook_jq.run('{"a":"x\ty"}', self.field)[1], "a raw control character")

    def test_rendering(self):
        self.assertEqual(hook_jq.captured(["a\n\n", "b\0c\n"]), "a\n\n\nbc")
        self.assertEqual(hook_jq.raw({"x": 1}), '{\n  "x": 1\n}')
        self.assertEqual(hook_jq.compact({"r": "a\x7fé"}), '{"r":"a\\u007fé"}')


class CloneRead(unittest.TestCase):
    def test_read_r_splits_as_bash_does(self):
        self.assertEqual(SCG.read_r("a1 code-low Write /c d  e ", 4), ["a1", "code-low", "Write", "/c d  e"])
        self.assertEqual(SCG.read_r("  a\tb  ", 4), ["a", "b", "", ""])
        self.assertEqual(SCG.read_r("a b c d", 4), ["a", "b", "c", "d"])

    def test_the_join_fails_on_a_container_and_spells_a_scalar(self):
        self.assertEqual(SCG.joined({"agent_id": 5, "agent_type": True, "tool_name": None, "cwd": ""}), ["5 true - -"])
        with self.assertRaises(hook_jq.Failed):
            SCG.joined({"agent_id": [1]})


if __name__ == "__main__":
    unittest.main()
