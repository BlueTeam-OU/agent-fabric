#!/usr/bin/env python3
"""The oracle for runtime/claude-code/user-settings.py: the fabric's keys in a
login's Claude Code user settings — what it writes, keeps, replaces and
refuses, the one line it prints, and its exit status. It was
runtime/claude-code/test_user-settings.sh, case for case (the bash test is
gone, Wave 9 batch 8), driven through ONE
constant, USER_SETTINGS (default runtime/claude-code/user-settings.py;
$USER_SETTINGS names another entry), so the same file runs against the
script and against any shim in front of it (ADR-040 §5 rule 5). The auto
mode defaults are tests/test_user_settings_auto_mode.py's; this file is the
rest of the command-line contract.

Nothing it runs reaches this account: HOME, the local bin the rules are
granted from and the stand-in for `claude` are under one mkdtemp, and the
environment is rebuilt from PATH plus what the script reads (no
AGENT_FABRIC_*, GITHUB_*, CLAUDE_* from the session).

The bash test's cases, each a test method here:
  a login with no settings file
    test_dry_run_names_it_and_writes_nothing, test_write_creates_directory_and_every_key,
    test_second_run_changes_nothing
  a login with settings of its own
    test_merge_keeps_every_other_key_and_removes_the_deprecated_switch,
    test_deprecated_switch_beside_the_keys_is_still_removed,
    test_attribution_off_but_display_keys_missing_is_rewritten,
    test_settings_from_before_the_autoupdate_key_get_it,
    test_unreadable_file_is_refused_in_one_line_and_not_overwritten,
    test_non_object_json_is_refused, test_no_path_is_usage_exit_2
  the memory-write check at user scope
    test_memory_check_one_entry_at_this_checkouts_path, test_memory_check_second_run_changes_nothing,
    test_memory_check_sharing_an_entry_keeps_the_neighbour,
    test_malformed_post_tool_use_is_refused_untouched (both shapes, both modes),
    test_unparseable_entry_in_the_list_is_kept
  bootstrap runs it
    test_bootstrap_wiring (calls it; the retired writer is gone)
  a flag is never a path
    test_help_prints_usage_on_stdout_and_writes_nothing (--help, -h),
    test_unknown_flag_is_refused_by_name (--verbose, -x, -),
    test_unknown_flag_beside_dry_run, test_usage_survives_python_OO
  the permission rules
    test_allow_rules_beside_the_accounts_own, test_ask_and_deny_untouched_fabric_ask_added,
    test_wrappers_get_no_rule, test_moli_fetch_allowed_serve_asked,
    test_permissions_second_run_changes_nothing, test_settled_file_without_allow_rules_gets_them,
    test_foreign_name_gets_no_rule_and_loses_one, test_missing_permission_mode_is_set_to_auto

Added where a refactor could break the contract and the bash test is silent:
  test_dry_run_exit_status_and_streams (0, nothing on stderr),
  test_refused_write_leaves_stdout_empty_stderr_one_line,
  test_deprecated_switch_in_an_otherwise_settled_file_is_removed,
  test_display_key_off_in_an_otherwise_settled_file_is_rewritten,
  test_autoupdate_key_missing_from_an_otherwise_settled_file_is_rewritten (the bash cases
  of the same names start from files unsettled in other keys too, so they were rewritten
  whatever settled() did with the one key under test), and test_non_object_json_is_refused
  now asks for the one-line refusal (a traceback also exits 1).

Mutations (planted one at a time on the source as formatted, 2026-10-19, when the bash test
was retired; each killed by a test of this file unless it says otherwise): the dry run's text
and return; os.makedirs in save(); doc.pop("includeCoAuthoredBy"); each clause of settled()
(deprecated switch, display keys, autoupdate env, defaultMode, allow rules, withheld rules);
ATTRIBUTION, TOP_LEVEL and ENV values; the merge of env, attribution and the account's other
keys; load()'s ValueError and non-object tests; the refusal's status and stream; the usage
status, the flag test, -h, the -OO fallback and the flag named; hooks_problem and its call in
main(); the memory check's entry, its old-path removal, its neighbour, its odd entries and its
matcher; the allow rules (own kept, withheld dropped, not_allowed, the link test, also_allowed);
the ask rules (own kept, fabric's added); deny kept; defaultMode. In bootstrap.py, the entry
name and the refused write's count are killed by tests/test_bootstrap_cli.py.

Exit codes: 0 all passed, non-zero on any failure (unittest)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree, write_operator_policy  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

USER_SETTINGS = os.path.abspath(os.environ.get("USER_SETTINGS")
                                or os.path.join(HERE, "runtime", "claude-code", "user-settings.py"))
if not os.path.isfile(USER_SETTINGS):
    sys.exit(f"test: script under test not found at {USER_SETTINGS}")
IS_PY = USER_SETTINGS.endswith(".py")
COMMANDS = os.path.join(HERE, "runtime", "claude-code", "commands.json")
BOOT = os.path.join(HERE, "tools", "fabric", "bootstrap.py")   # Python behind bootstrap.sh's shim
TIMEOUT_S = 60
STAND_IN_CLAUDE = ('#!/bin/sh\necho \'{"environment": ["**Organization**: None configured"], '
                   '"allow": [], "soft_deny": [], "hard_deny": []}\'\n')


def check_base(t: unittest.TestCase, d: dict) -> None:
    a = d["attribution"]
    t.assertEqual((a["commit"], a["pr"], a["sessionUrl"]), ("", "", False), d)
    t.assertIs(d["showThinkingSummaries"], True, d)
    t.assertIs(d["verbose"], True, d)
    t.assertEqual(d["tui"], "default", d)
    t.assertEqual(d["env"]["DISABLE_AUTOUPDATER"], "1", d)


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.sandbox = os.path.realpath(tempfile.mkdtemp(prefix="us."))
        self.addCleanup(shutil.rmtree, self.sandbox, ignore_errors=True)
        self.s = os.path.join(self.sandbox, ".claude", "settings.json")
        # Inside .claude/: the flag cases assert nothing else appears in the sandbox.
        self.bin = os.path.join(self.sandbox, ".claude", "local-bin")
        os.makedirs(self.bin)
        with open(COMMANDS, encoding="utf-8") as fh:
            for name, rel in json.load(fh)["commands"].items():
                os.symlink(os.path.join(HERE, rel), os.path.join(self.bin, name))
        # A runner without claude would otherwise make every write say the
        # defaults could not be read.
        claude = os.path.join(self.sandbox, ".claude", "claude")
        with open(claude, "w", encoding="utf-8") as fh:
            fh.write(STAND_IN_CLAUDE)
        os.chmod(claude, 0o755)
        self.env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": self.sandbox, "LANG": "C.UTF-8",
                    # Importing roots would write tools/fabric/__pycache__ (and an opt-2 one for -OO) into the checkout.
                    "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": self.sandbox, "AGENT_FABRIC_LOCAL_BIN": self.bin, "AGENT_FABRIC_CLAUDE": claude,
                    # The auto-mode policy is the operator's file; a fixture one, never the checkout's.
                    "AGENT_FABRIC_OPERATOR": write_operator_policy(os.path.join(self.sandbox, ".claude"))}

    def cmd(self, *argv: str, flags: tuple[str, ...] = ()) -> list[str]:
        return ([sys.executable, *flags, USER_SETTINGS] if IS_PY else [USER_SETTINGS]) + list(argv)

    def run_raw(self, *argv: str, flags: tuple[str, ...] = ()) -> subprocess.CompletedProcess:
        return subprocess.run(self.cmd(*argv, flags=flags), capture_output=True, text=True, env=self.env,
                              cwd=self.sandbox, timeout=TIMEOUT_S, check=False)

    def run_s(self, *argv: str) -> str:
        """stdout and stderr merged, stripped of the final newline, as `$(…) 2>&1` reads them."""
        p = self.run_raw(*argv)
        return (p.stdout + p.stderr).rstrip("\n")

    def put(self, text: str) -> None:
        os.makedirs(os.path.dirname(self.s), exist_ok=True)
        with open(self.s, "w", encoding="utf-8") as fh:
            fh.write(text)

    def put_json(self, doc: object) -> None:
        self.put(json.dumps(doc) + "\n")

    def doc(self) -> dict:
        with open(self.s, encoding="utf-8") as fh:
            return json.load(fh)

    def text(self) -> str:
        with open(self.s, encoding="utf-8") as fh:
            return fh.read()

    @property
    def wrote(self) -> str:
        return f"  +  {self.s} fabric user settings"

    @property
    def current(self) -> str:
        return f"  =  {self.s} fabric user settings"


class NoSettingsFile(Base):
    def test_dry_run_names_it_and_writes_nothing(self) -> None:
        self.assertEqual(self.run_s(self.s, "--dry-run"), self.wrote + " (would write)")
        self.assertFalse(os.path.exists(self.s))

    def test_dry_run_exit_status_and_streams(self) -> None:
        p = self.run_raw(self.s, "--dry-run")
        self.assertEqual((p.returncode, p.stderr), (0, ""))

    def test_write_creates_directory_and_every_key(self) -> None:
        target = os.path.join(self.sandbox, "new", "dir", "settings.json")
        p = self.run_raw(target)
        self.assertEqual((p.returncode, p.stdout.rstrip("\n"), p.stderr), (0, f"  +  {target} fabric user settings", ""))
        with open(target, encoding="utf-8") as fh:
            check_base(self, json.load(fh))

    def test_second_run_changes_nothing(self) -> None:
        self.run_raw(self.s)
        self.assertEqual(self.run_s(self.s), self.current)


class SettingsOfItsOwn(Base):
    def test_merge_keeps_every_other_key_and_removes_the_deprecated_switch(self) -> None:
        self.put_json({"theme": "dark", "includeCoAuthoredBy": False,
                       "attribution": {"commit": "Co-Authored-By: x", "extra": 1},
                       "permissions": {"deny": ["WebSearch"]}, "env": {"KEEP_ME": "yes"}})
        out = self.run_s(self.s)
        self.assertTrue(out.startswith("  +  "), out)
        d = self.doc()
        check_base(self, d)
        self.assertEqual(d["theme"], "dark")
        self.assertEqual(d["permissions"]["deny"], ["WebSearch"])
        self.assertEqual(d["attribution"]["extra"], 1)
        self.assertNotIn("includeCoAuthoredBy", d)
        self.assertEqual(d["env"]["KEEP_ME"], "yes")

    def test_deprecated_switch_beside_the_keys_is_still_removed(self) -> None:
        self.put_json({"attribution": {"commit": "", "pr": "", "sessionUrl": False},
                       "includeCoAuthoredBy": True, "showThinkingSummaries": True, "verbose": True})
        out = self.run_s(self.s)
        self.assertTrue(out.startswith("  +  "), out)
        d = self.doc()
        check_base(self, d)
        self.assertNotIn("includeCoAuthoredBy", d)

    def test_attribution_off_but_display_keys_missing_is_rewritten(self) -> None:
        # An account bootstrapped before 2026-09-20: attribution already off,
        # nothing else set. Rewritten, not reported settled (verbose false overridden).
        self.put_json({"attribution": {"commit": "", "pr": "", "sessionUrl": False}, "verbose": False})
        self.assertTrue(self.run_s(self.s).startswith("  +  "))
        check_base(self, self.doc())

    def test_settings_from_before_the_autoupdate_key_get_it(self) -> None:
        self.put_json({"attribution": {"commit": "", "pr": "", "sessionUrl": False},
                       "showThinkingSummaries": True, "verbose": True})
        self.assertTrue(self.run_s(self.s).startswith("  +  "))
        check_base(self, self.doc())

    def settled(self) -> dict:
        """What a first run writes to a fresh account: every key in place, so a
        change made to it afterwards is the only reason to write again."""
        self.run_raw(self.s)
        return self.doc()

    def test_deprecated_switch_in_an_otherwise_settled_file_is_removed(self) -> None:
        # The file above is unsettled in other keys too, so it is rewritten whatever
        # the switch does. Kills: dropping the includeCoAuthoredBy clause from settled().
        d = self.settled()
        d["includeCoAuthoredBy"] = True
        self.put_json(d)
        self.assertTrue(self.run_s(self.s).startswith("  +  "))
        self.assertNotIn("includeCoAuthoredBy", self.doc())

    def test_display_key_off_in_an_otherwise_settled_file_is_rewritten(self) -> None:
        # Kills: dropping the TOP_LEVEL clause from settled().
        d = self.settled()
        d["verbose"] = False
        self.put_json(d)
        self.assertTrue(self.run_s(self.s).startswith("  +  "))
        check_base(self, self.doc())

    def test_autoupdate_key_missing_from_an_otherwise_settled_file_is_rewritten(self) -> None:
        # Kills: dropping the env clause from settled().
        d = self.settled()
        del d["env"]["DISABLE_AUTOUPDATER"]
        self.put_json(d)
        self.assertTrue(self.run_s(self.s).startswith("  +  "))
        check_base(self, self.doc())

    def test_unreadable_file_is_refused_in_one_line_and_not_overwritten(self) -> None:
        self.put("not json\n")
        p = self.run_raw(self.s)
        out = p.stdout + p.stderr
        self.assertEqual(p.returncode, 1, out)
        self.assertTrue(out.startswith("  !  ") and "NOT written" in out, out)
        self.assertNotIn("Traceback", out)
        self.assertEqual(len(out.rstrip("\n").splitlines()), 1, out)
        self.assertEqual(self.text().rstrip("\n"), "not json")

    def test_non_object_json_is_refused(self) -> None:
        self.put("[1]\n")
        p = self.run_raw(self.s)
        out = p.stdout + p.stderr
        self.assertEqual(p.returncode, 1, out)
        # One line by the writer's own check: a traceback also exits 1, and
        # the bash test's exit status alone could not tell the two apart.
        self.assertTrue(out.startswith("  !  ") and "not a JSON object" in out and "NOT written" in out, out)
        self.assertNotIn("Traceback", out)
        self.assertEqual(self.text().rstrip("\n"), "[1]")

    def test_no_path_is_usage_exit_2(self) -> None:
        p = self.run_raw()
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertNotIn("Traceback", p.stderr)


MEMORY_CHECK = "memory-write-check.py"


class MemoryWriteCheck(Base):
    def entries(self, d: dict) -> list:
        return d["hooks"]["PostToolUse"]

    def test_memory_check_one_entry_at_this_checkouts_path(self) -> None:
        old = f'python3 "/old/place/runtime/claude-code/hooks/{MEMORY_CHECK}"'
        self.put_json({"hooks": {"PostToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "mine.sh"}]},
            {"matcher": "Write|Edit", "hooks": [{"type": "command", "command": old}]}],
            "Stop": [{"hooks": [{"type": "command", "command": "stop.sh"}]}]}})
        self.run_s(self.s)
        d = self.doc()
        check_base(self, d)
        p = self.entries(d)
        mc = [e for e in p if MEMORY_CHECK in e["hooks"][0]["command"]]
        self.assertEqual(len(mc), 1, p)
        self.assertEqual(mc[0]["matcher"], "Write|Edit")
        self.assertIn(os.path.join(HERE, "runtime", "claude-code", "hooks", MEMORY_CHECK), mc[0]["hooks"][0]["command"])
        self.assertNotIn("/old/place/", json.dumps(p))
        self.assertTrue(any(e["hooks"][0]["command"] == "mine.sh" for e in p), p)
        self.assertEqual(d["hooks"]["Stop"][0]["hooks"][0]["command"], "stop.sh")

    def test_memory_check_second_run_changes_nothing(self) -> None:
        # On the file the first run rewrote (the account's own hook, an old
        # path, a Stop hook), not on a fresh one: the merge of the account's
        # entries must be idempotent too.
        self.put_json({"hooks": {"PostToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "mine.sh"}]},
            {"matcher": "Write|Edit", "hooks": [{"type": "command", "command": f'python3 "/old/place/runtime/claude-code/hooks/{MEMORY_CHECK}"'}]}],
            "Stop": [{"hooks": [{"type": "command", "command": "stop.sh"}]}]}})
        self.assertTrue(self.run_s(self.s).startswith("  +  "))
        self.assertEqual(self.run_s(self.s), self.current)
        cmds = [h["command"] for e in self.entries(self.doc()) for h in e["hooks"]]
        self.assertEqual(cmds.count("mine.sh"), 1, cmds)

    def test_memory_check_sharing_an_entry_keeps_the_neighbour(self) -> None:
        # A hand-merged entry holding the check beside a hook of the account's
        # own: only the check is replaced; the neighbour stays.
        self.put_json({"hooks": {"PostToolUse": [{"matcher": "Write|Edit", "hooks": [
            {"type": "command", "command": f'python3 "/old/runtime/claude-code/hooks/{MEMORY_CHECK}"'},
            {"type": "command", "command": "neighbour.sh"}]}]}})
        self.run_s(self.s)
        d = self.doc()
        check_base(self, d)
        cmds = [h["command"] for e in self.entries(d) for h in e["hooks"]]
        self.assertIn("neighbour.sh", cmds)
        self.assertEqual(sum(MEMORY_CHECK in c for c in cmds), 1, cmds)
        self.assertFalse(any("/old/" in c for c in cmds), cmds)

    def test_malformed_post_tool_use_is_refused_untouched(self) -> None:
        # PostToolUse that is not a list is the account's own mistake: left
        # exactly as it is and said, never iterated into junk entries. Every
        # other key is unset too, so "settled" is false before the hooks are
        # reached: the refusal must come from the check itself, not by luck.
        for shape in ({"matcher": "x", "hooks": []}, "ab"):
            for mode in ((), ("--dry-run",)):
                with self.subTest(shape=shape, mode=mode):
                    self.put_json({"hooks": {"PostToolUse": shape}})
                    p = self.run_raw(self.s, *mode)
                    out = (p.stdout + p.stderr).rstrip("\n")
                    self.assertEqual(self.doc()["hooks"]["PostToolUse"], shape)
                    self.assertEqual(p.returncode, 1, out)
                    self.assertTrue(out.startswith("  !  ") and "PostToolUse is not a list" in out
                                    and out.endswith("NOT written"), out)
                    self.assertEqual(len(out.splitlines()), 1, out)
                    self.assertNotIn("Traceback", out)

    def test_refused_write_leaves_stdout_empty_stderr_one_line(self) -> None:
        # Which stream carries the refusal is read by bootstrap, which counts it.
        self.put("not json\n")
        p = self.run_raw(self.s)
        self.assertEqual((p.stdout, p.stderr.count("\n")), ("", 1), (p.stdout, p.stderr))

    def test_unparseable_entry_in_the_list_is_kept(self) -> None:
        self.put_json({"hooks": {"PostToolUse": ["odd", {"matcher": "Bash", "hooks": [
            {"type": "command", "command": "mine.sh"}]}]}})
        self.run_s(self.s)
        d = self.doc()
        check_base(self, d)
        p = self.entries(d)
        self.assertEqual(p[0], "odd")
        self.assertTrue(any(e != "odd" and e["hooks"][0]["command"] == "mine.sh" for e in p), p)
        self.assertEqual(sum(1 for e in p if isinstance(e, dict) and MEMORY_CHECK in e["hooks"][0]["command"]), 1, p)


class BootstrapWiring(unittest.TestCase):
    # Source-text checks of bootstrap.py, as the bash test made them; the
    # behaviour of bootstrap itself is tests/test_bootstrap_cli.py's.
    def test_bootstrap_wiring(self) -> None:
        with open(BOOT, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn('"runtime/claude-code/user-settings.py", path', src, "bootstrap calls it on the login's user settings")
        self.assertNotIn("attribution-off", src, "bootstrap still names the retired writer")
        # That a refused write is counted, not read as already current, is
        # tests/test_bootstrap_cli.py's (a source grep for the counter could not fail: it occurs 16 times).


class Flags(Base):
    def only_claude_dir(self) -> bool:
        return not [n for n in os.listdir(self.sandbox) if n != ".claude"]

    def test_help_prints_usage_on_stdout_and_writes_nothing(self) -> None:
        for flag in ("--help", "-h"):
            with self.subTest(flag=flag):
                p = self.run_raw(flag)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertIn("user-settings.py <settings.json> [--dry-run]", p.stdout)
                self.assertTrue(self.only_claude_dir(), os.listdir(self.sandbox))

    def test_unknown_flag_is_refused_by_name(self) -> None:
        for flag in ("--verbose", "-x", "-"):
            with self.subTest(flag=flag):
                p = self.run_raw(flag)
                self.assertEqual(p.returncode, 2, p.stderr)
                self.assertEqual(p.stdout, "")
                self.assertFalse(os.path.exists(os.path.join(self.sandbox, flag)))
                self.assertIn(f"{flag}: not an option and not a path", p.stderr)

    def test_unknown_flag_beside_dry_run(self) -> None:
        p = self.run_raw("--dry-run", "--bogus")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.sandbox, "--bogus")))

    @unittest.skipUnless(IS_PY, "-OO is a Python interpreter flag")
    def test_usage_survives_python_OO(self) -> None:
        # The usage is the module's docstring; -OO strips docstrings.
        p = self.run_raw("--help", flags=("-OO",))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("<settings.json>", p.stdout + p.stderr)


class PermissionRules(Base):
    """The fabric's commands are allowed by a narrow rule each; the account's
    own allow, deny and ask rules stay as they were, and a wrapper that runs
    another command is never allowed (the owner, 2026-09-26)."""

    def written(self) -> dict:
        self.put_json({"permissions": {"allow": ["Bash(ls *)"], "ask": ["Bash(gzcoord-send *)"], "deny": ["Bash(rm *)"]}})
        self.run_raw(self.s)
        return self.doc()["permissions"]

    def test_allow_rules_beside_the_accounts_own(self) -> None:
        allow = self.written()["allow"]
        for want in ("Bash(ls *)", "Bash(gzcoord-inbox *)", "Bash(fabric-status *)"):
            self.assertIn(want, allow)

    def test_ask_and_deny_untouched_fabric_ask_added(self) -> None:
        perm = self.written()
        self.assertEqual(perm["ask"], ["Bash(gzcoord-send *)", "Bash(moli serve *)"])
        self.assertEqual(perm["deny"], ["Bash(rm *)"])

    def test_wrappers_get_no_rule(self) -> None:
        allow = self.written()["allow"]
        self.assertEqual([r for r in allow if r in ("Bash(fabric-lease *)", "Bash(fabric-host *)")], [])
        self.assertIn("Bash(gzcoord-inbox *)", allow)       # positive control: the filter is not matching nothing

    def test_moli_fetch_allowed_serve_asked(self) -> None:
        perm = self.written()
        self.assertEqual([r for r in perm["allow"] if r.startswith("Bash(moli")], ["Bash(moli fetch *)"])
        self.assertIn("Bash(moli serve *)", perm.get("ask", []))

    def test_memory_tools_allowed_by_name(self) -> None:
        # Mutation: rules() ignores tools_allowed, and a plan-mode session asks for every memory lookup.
        allow = self.written()["allow"]
        for tool in ("memory_find", "memory_read", "memory_index", "memory_mark"):
            self.assertIn(f"mcp__fabric-memory__{tool}", allow)
        self.assertNotIn("_comment", allow)

    def test_permissions_second_run_changes_nothing(self) -> None:
        self.written()
        self.assertTrue(self.run_s(self.s).startswith("  =  "))

    def test_settled_file_without_allow_rules_gets_them(self) -> None:
        # An account the earlier bootstrap settled — every other key in place,
        # no allow rule yet — still gets the rules: a check that ignored them
        # would print "=" and never write them (review of #42).
        self.written()
        d = self.doc()
        del d["permissions"]["allow"]
        self.put_json(d)
        out = self.run_s(self.s)
        self.assertTrue(out.startswith("  +  "), out)
        self.assertIn("Bash(gzcoord-inbox *)", self.doc()["permissions"]["allow"])

    def test_foreign_name_gets_no_rule_and_loses_one(self) -> None:
        # A foreign file at a command's name (bootstrap refused to replace it)
        # gets no rule, and a rule granted before is withdrawn: the name would
        # run that file under the fabric's approval (review of #42).
        self.written()
        self.assertIn("Bash(gzmsg *)", self.doc()["permissions"]["allow"])        # positive control
        link = os.path.join(self.bin, "gzmsg")
        os.remove(link)
        with open(link, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\necho mine\n")
        self.run_s(self.s)
        allow = self.doc()["permissions"]["allow"]
        self.assertNotIn("Bash(gzmsg *)", allow)
        self.assertIn("Bash(gzcoord-send *)", allow)

    def test_missing_permission_mode_is_set_to_auto(self) -> None:
        # Every session starts in auto mode (the owner, 2026-09-26): a file
        # settled in every other key but the mode is written.
        self.written()
        d = self.doc()
        del d["permissions"]["defaultMode"]
        self.put_json(d)
        out = self.run_s(self.s)
        self.assertTrue(out.startswith("  +  "), out)
        self.assertEqual(self.doc()["permissions"]["defaultMode"], "auto")


if __name__ == "__main__":
    unittest.main()
