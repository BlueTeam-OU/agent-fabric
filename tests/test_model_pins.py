#!/usr/bin/env python3
"""Tests for tools/fabric/guards/model_pins.py's internals (ADR-040 §5 rule 5: the port's pull request adds them);
the behaviour through the entry is tests/test_policy_model_pins_check.py's. Each case names the one-line mutation it
catches, chosen where the CLI oracle cannot: it inserts env keys already in sorted order, so a dropped sort survives it.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from guards import model_pins as mp  # noqa: E402


class SettingsPath(unittest.TestCase):
    def test_the_file_variable_wins_over_the_repository(self):
        # mutation: REPO_ROOT read before AGENT_FABRIC_SETTINGS_FILE
        self.assertEqual(mp.settings_path({"AGENT_FABRIC_SETTINGS_FILE": "/x/s.json", "REPO_ROOT": "/r"}), "/x/s.json")

    def test_an_empty_file_variable_is_unset(self):
        # mutation: `if "AGENT_FABRIC_SETTINGS_FILE" in env` (an empty value would name the cwd's "")
        self.assertEqual(mp.settings_path({"AGENT_FABRIC_SETTINGS_FILE": "", "REPO_ROOT": "/r"}),
                         os.path.join("/r", ".claude", "settings.json"))

    def test_outside_a_repository_the_current_directory_holds_it(self):
        # mutation: the toplevel's None returned as the root
        with tempfile.TemporaryDirectory() as d:
            old = os.getcwd()
            os.chdir(d)
            try:
                env = {"GIT_CEILING_DIRECTORIES": os.path.dirname(d)}
                os.environ.update(env)
                got = mp.settings_path({})
            finally:
                os.chdir(old)
                os.environ.pop("GIT_CEILING_DIRECTORIES", None)
            self.assertEqual(got, os.path.join(os.path.realpath(d), ".claude", "settings.json"))


class PinsOf(unittest.TestCase):
    def test_env_findings_come_sorted_whatever_the_file_order(self):
        # mutation: `sorted(...)` dropped (the oracle's keys arrive sorted already)
        got = mp.pins_of({"env": {"ANTHROPIC_Z": "1", "CLAUDE_CODE_EFFORT_LEVEL": "high", "ANTHROPIC_A": "1"}})
        self.assertEqual([g.split()[0] for g in got], ["env.ANTHROPIC_A", "env.ANTHROPIC_Z", "env.CLAUDE_CODE_EFFORT_LEVEL"])

    def test_a_clean_file_has_no_finding_and_unrelated_env_is_not_one(self):
        # mutation: `startswith("ANTHROPIC")` without the underscore, or ENV_NAMES read as a prefix
        self.assertEqual(mp.pins_of({"env": {"ANTHROPICX": "1", "CLAUDE_CODE_EFFORT_LEVELX": "1", "PATH": "/b"},
                                     "permissions": {}}), [])

    def test_findings_follow_model_overrides_effort_then_env(self):
        # mutation: the env loop moved before the effort keys
        got = mp.pins_of({"env": {"ANTHROPIC_MODEL": "m"}, "effortLevel": "high", "modelOverrides": {}, "model": "x"})
        self.assertEqual(len(got), 4)
        self.assertTrue(got[0].startswith('top-level "model"'), got)
        self.assertTrue(got[1].startswith('"modelOverrides"'), got)
        self.assertTrue(got[2].startswith('"effortLevel"'), got)
        self.assertTrue(got[3].startswith("env.ANTHROPIC_MODEL"), got)


class NotAnObject(unittest.TestCase):
    def test_a_json_array_is_one_line_on_stderr_and_exit_1(self):
        # mutation: the isinstance(dict) check dropped (a list answers "in", but its `d.get("env")` traces back)
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "settings.json")
            with open(f, "w", encoding="utf-8") as fh:
                fh.write("[1, 2]")
            r = subprocess.run([sys.executable, os.path.join(HERE, "tools", "fabric", "guards", "model_pins.py")],
                               capture_output=True, text=True, env={**os.environ, "AGENT_FABRIC_SETTINGS_FILE": f},
                               timeout=60)
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertNotIn("Traceback", r.stderr)
            self.assertEqual(len(r.stderr.strip().splitlines()), 1, r.stderr)


if __name__ == "__main__":
    unittest.main()
