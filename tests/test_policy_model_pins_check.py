#!/usr/bin/env python3
"""policies/check_repo_settings_carry_no_model_pins.sh: the guard that a repository's COMMITTED Claude Code settings carry no
model pin, no effort pin and no provider routing (Wave 9 batch 3; ADR-040 rule 5). Written to run unchanged against the bash
today and against its Python port later: the entry point is ONE constant, ENTRY (the path a harness or CI invokes; override
with MODEL_PINS_CHECK_ENTRY), run as a command, never sourced.

The bash oracle policies/test_check_repo_settings_carry_no_model_pins.sh (deleted, Wave 9 batch 3), case for case (each is a method here):
  clean_file_passes                          "a clean file passes": exit 0
  each_pin_shape_is_caught                   "each pin shape is caught": the ten shapes of its list, each non-zero
  unparseable_json_fails                     "unparseable JSON fails loudly": non-zero
  missing_file_is_ok                         "a missing file is OK": exit 0
Cases the bash test does not carry, where a port could break the contract: the exact stdout line of a pass and of an absent
file; the FAIL report's shape (header with the count, numbered reasons, the closing two lines) on stdout with nothing on stderr;
several pins in one file counted and numbered in the script's order; a key whose value is null still pinned; env keys matched
by prefix (ANTHROPIC_) or by name, lower case and a bare ANTHROPIC not matched; `env: null` clean; the file chosen by
AGENT_FABRIC_SETTINGS_FILE, else REPO_ROOT/.claude/settings.json, else <git toplevel>/.claude/settings.json, else
<cwd>/.claude/settings.json, in that order; a directory where the file should be reads as absent; the pinned Python missing is
exit 127 on stderr, but only once the file exists; a top-level JSON array is not an object (today: a traceback, exit 1).

Mutations each case fails on (one per behaviour; planted on the script as formatted): dropping "effortLevel" from the refused
keys (pin shapes); dropping the `startswith("ANTHROPIC_")` test (env prefix); printing the report on stderr (report shape);
reading REPO_ROOT before AGENT_FABRIC_SETTINGS_FILE (file order); `exit 0` on unreadable JSON (broken JSON); checking the pinned
Python before the file exists (python only when the file exists).

The environment is built from scratch: PATH, HOME, LANG and the one documented test hook AGENT_FABRIC_PYTHON (the fleet's pinned
Python is /usr/local/bin/fabric-python by default; a host or CI runner without it points the guard at the interpreter running
this test). No AGENT_FABRIC_*, GITHUB_*, CLAUDE_* or git variable of the session reaches the guard."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY = os.environ.get("MODEL_PINS_CHECK_ENTRY") or os.path.join(ROOT, "policies", "check_repo_settings_carry_no_model_pins.sh")
NAME = "check_repo_settings_carry_no_model_pins"
PIN_SHAPES = [
    {"model": "claude-opus-5"},
    {"modelOverrides": {"claude-opus-5": "z-ai/glm-5.3"}},
    {"env": {"ANTHROPIC_DEFAULT_OPUS_MODEL": "x"}},
    {"env": {"ANTHROPIC_API_KEY": "x"}},
    {"env": {"CLAUDE_CODE_SUBAGENT_MODEL": "x"}},
    {"env": {"ANTHROPIC_BASE_URL": "http://x"}},
    {"effortLevel": "low"},
    {"maxEffortLevel": "low"},
    {"modelSettings": {"claude-opus-5": {"effort": "low"}}},
    {"env": {"CLAUDE_CODE_EFFORT_LEVEL": "max"}},
]


class Guard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="model-pins-check-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.file = os.path.join(self.tmp, "settings.json")

    def env(self, **extra) -> dict:
        env = {"PATH": "/usr/bin:/bin", "HOME": self.tmp, "LANG": "C.UTF-8", "AGENT_FABRIC_PYTHON": sys.executable, "PYTHONDONTWRITEBYTECODE": "1"}
        env.update(extra)
        return {k: v for k, v in env.items() if v is not None}

    def run_guard(self, cwd=None, **extra) -> subprocess.CompletedProcess:
        return subprocess.run([ENTRY], capture_output=True, text=True, cwd=cwd or self.tmp, timeout=60, env=self.env(**extra))

    def put(self, doc, path=None) -> str:
        path = path or self.file
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(doc if isinstance(doc, str) else json.dumps(doc))
        return path

    def check_file(self, doc, **extra) -> subprocess.CompletedProcess:
        self.put(doc)
        return self.run_guard(AGENT_FABRIC_SETTINGS_FILE=self.file, **extra)


class OracleCases(Guard):
    """The four sections of policies/test_check_repo_settings_carry_no_model_pins.sh."""

    def test_clean_file_passes(self):
        r = self.check_file({"env": {"GZAPP_ACTIONS_INCLUDED_MINUTES": "50000"}, "enabledMcpjsonServers": ["dart"]})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_each_pin_shape_is_caught(self):
        for shape in PIN_SHAPES:
            with self.subTest(shape=shape):
                r = self.check_file(shape)
                self.assertEqual(r.returncode, 1, f"{shape}: {r.stdout}{r.stderr}")

    def test_unparseable_json_fails(self):
        r = self.check_file("{broken")
        self.assertNotEqual(r.returncode, 0, r.stdout)

    def test_missing_file_is_ok(self):
        r = self.run_guard(AGENT_FABRIC_SETTINGS_FILE=os.path.join(self.tmp, "absent"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class Output(Guard):
    def test_a_clean_file_says_so_on_stdout_alone(self):
        r = self.check_file({"enabledMcpjsonServers": ["dart"]})
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, f"{NAME}: OK — {self.file} carries no model pins.\n", ""))

    def test_an_absent_file_says_so_on_stdout_alone(self):
        absent = os.path.join(self.tmp, "absent.json")
        r = self.run_guard(AGENT_FABRIC_SETTINGS_FILE=absent)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, f"{NAME}: OK — {absent} does not exist.\n", ""))

    def test_a_failure_report_has_a_counted_header_numbered_reasons_and_two_closing_lines_on_stdout(self):
        r = self.check_file({"model": "m", "effortLevel": "low", "env": {"ANTHROPIC_API_KEY": "x", "CLAUDE_CODE_SUBAGENT_MODEL": "y"}})
        self.assertEqual((r.returncode, r.stderr), (1, ""))
        lines = r.stdout.splitlines()
        self.assertEqual(lines[0], f"FAIL: {self.file} carries model pins (4):")
        body = [ln for ln in lines[1:5]]
        self.assertEqual([ln.split(".", 1)[0].strip() for ln in body], ["1", "2", "3", "4"])
        self.assertIn('top-level "model" is set', body[0])
        self.assertIn('"effortLevel" present', body[1])
        self.assertIn("env.ANTHROPIC_API_KEY present", body[2])         # env keys in sorted order
        self.assertIn("env.CLAUDE_CODE_SUBAGENT_MODEL present", body[3])
        self.assertEqual(lines[5:], ["      Shape D puts model choice in the launcher + routing files;",
                                     "      remove these from the committed settings file."])

    def test_each_key_is_named_in_its_own_reason(self):
        expect = {"modelOverrides": '"modelOverrides" present', "maxEffortLevel": '"maxEffortLevel" present',
                  "modelSettings": '"modelSettings" present'}
        for key, text in expect.items():
            with self.subTest(key=key):
                r = self.check_file({key: {}})
                self.assertEqual(r.returncode, 1)
                self.assertIn(text, r.stdout)

    def test_unreadable_json_says_which_file_and_why_on_stdout(self):
        r = self.check_file("{broken")
        self.assertEqual((r.returncode, r.stderr), (1, ""))
        first = r.stdout.splitlines()[0]
        self.assertTrue(first.startswith(f"FAIL: {self.file} is not readable JSON ("), first)
        self.assertIn("silently disables every setting it carries", r.stdout)


class WhatIsMatched(Guard):
    def test_a_key_that_is_present_is_pinned_whatever_its_value(self):
        for key in ("model", "modelOverrides", "effortLevel", "maxEffortLevel", "modelSettings"):
            with self.subTest(key=key):
                self.assertEqual(self.check_file({key: None}).returncode, 1)

    def test_env_keys_match_by_prefix_or_by_name_and_only_those(self):
        for env, pinned in (({"ANTHROPIC_ANYTHING": "x"}, True), ({"CLAUDE_CODE_SUBAGENT_MODEL": "x"}, True),
                            ({"CLAUDE_CODE_EFFORT_LEVEL": "x"}, True), ({"anthropic_lower": "x"}, False), ({"ANTHROPIC": "x"}, False),
                            ({"CLAUDE_CODE_OTHER": "x"}, False), ({"MY_ANTHROPIC_KEY": "x"}, False), ({}, False)):
            with self.subTest(env=env):
                self.assertEqual(self.check_file({"env": env}).returncode, 1 if pinned else 0)

    def test_env_null_is_clean_and_other_top_level_keys_are_not_looked_at(self):
        self.assertEqual(self.check_file({"env": None, "permissions": {"allow": ["Bash(ls)"]}, "hooks": {}}).returncode, 0)

    def test_a_top_level_array_is_not_an_object_today_a_traceback(self):
        # Characterisation, not endorsement: a settings file that is a JSON array makes the guard crash (exit 1, a traceback on
        # stderr) rather than report. A port may do better; it must still not exit 0.
        r = self.check_file([1, 2])
        self.assertEqual(r.returncode, 1)
        self.assertNotEqual(r.stderr, "")


class WhichFile(Guard):
    def make_repo(self, pinned=True) -> str:
        repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(repo, "sub"))
        subprocess.run(["git", "init", "-q", repo], check=True, capture_output=True, env=self.env(GIT_CONFIG_GLOBAL=os.devnull))
        self.put({"model": "x"} if pinned else {}, os.path.join(repo, ".claude", "settings.json"))
        return repo

    def test_the_default_is_the_git_toplevel_settings_whatever_the_cwd(self):
        repo = os.path.realpath(self.make_repo())
        r = self.run_guard(cwd=os.path.join(repo, "sub"))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(r.stdout.splitlines()[0], f"FAIL: {os.path.join(repo, '.claude', 'settings.json')} carries model pins (1):")

    def test_outside_a_repository_the_default_is_the_current_directory(self):
        plain = os.path.realpath(os.path.join(self.tmp, "plain"))
        self.put({"model": "x"}, os.path.join(plain, ".claude", "settings.json"))
        r = self.run_guard(cwd=plain, GIT_CEILING_DIRECTORIES=self.tmp)       # a TMPDIR inside a work tree must not be found
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(r.stdout.splitlines()[0], f"FAIL: {os.path.join(plain, '.claude', 'settings.json')} carries model pins (1):")

    def test_repo_root_names_the_repository_and_the_settings_file_variable_names_the_file_over_it(self):
        pinned = os.path.join(self.tmp, "a")
        clean = os.path.join(self.tmp, "b")
        self.put({"model": "x"}, os.path.join(pinned, ".claude", "settings.json"))
        self.put({}, os.path.join(clean, ".claude", "settings.json"))
        self.assertEqual(self.run_guard(REPO_ROOT=pinned).returncode, 1)
        self.assertEqual(self.run_guard(REPO_ROOT=clean).returncode, 0)
        direct = self.put({"modelSettings": {}}, os.path.join(self.tmp, "direct.json"))
        r = self.run_guard(REPO_ROOT=clean, AGENT_FABRIC_SETTINGS_FILE=direct)
        self.assertEqual(r.returncode, 1)
        self.assertIn(direct, r.stdout)

    def test_a_directory_where_the_file_should_be_reads_as_absent(self):
        d = os.path.join(self.tmp, "adir")
        os.makedirs(d)
        r = self.run_guard(AGENT_FABRIC_SETTINGS_FILE=d)
        self.assertEqual((r.returncode, r.stdout), (0, f"{NAME}: OK — {d} does not exist.\n"))


class PinnedPython(Guard):
    def test_a_missing_pinned_python_is_exit_127_on_stderr_naming_the_path(self):
        self.put({})
        r = self.run_guard(AGENT_FABRIC_SETTINGS_FILE=self.file, AGENT_FABRIC_PYTHON="/nonexistent/fabric-python")
        self.assertEqual((r.returncode, r.stdout), (127, ""))
        self.assertIn("the fleet's pinned Python is not installed at /nonexistent/fabric-python", r.stderr)

    def test_the_python_is_asked_for_only_once_the_file_exists(self):
        r = self.run_guard(AGENT_FABRIC_SETTINGS_FILE=os.path.join(self.tmp, "absent"), AGENT_FABRIC_PYTHON="/nonexistent/fabric-python")
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
