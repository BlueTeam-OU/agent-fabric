#!/usr/bin/env python3
"""The `fabric` permission rules of runtime/claude-code/user-settings.py (ADR-068 §5 rule 6).

Two layers. The rule derivation is driven in process over small synthetic tables (a noun with a not_allowed verb, a
noun without its own command, a noun whose own command is not_allowed), because the real table has no such noun yet
except by the shape of its entries. What reaches a settings file — the link check, `Bash(fabric *)` never written, a
re-run, a stale owned rule — is driven through the script on the real table, in the sandbox of
tests/test_user_settings_cli.py.

Mutations (planted one at a time, each killed by a test here): the broad rule appended; the ask loop dropped; the
`cmd not in blocked` filter of the else branch; the exact rules missing; the link check skipped for `fabric`; the
stale-rule filter in main() or in settled(); fabric_owned() matching `Bash(fabric-lease *)`.

Exit codes: 0 all passed, non-zero on any failure (unittest)."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests"))
import test_user_settings_cli as cli  # noqa: E402 — tests/, the script's own directory

SCRIPT = os.path.join(HERE, "runtime", "claude-code", "user-settings.py")


def load_script():
    spec = importlib.util.spec_from_file_location("user_settings_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def table_doc(nouns: dict, not_allowed: list[str]) -> dict:
    """A commands.json whose every command is `bin/fabric` (a path that exists, so only the names matter)."""
    names = {"fabric"}
    for entry in nouns.values():
        names |= {entry["command"]} if "command" in entry else set()
        names |= set(entry.get("verbs", {}).values())
    return {"commands": {n: "bin/fabric" for n in sorted(names)}, "not_allowed": {n: "why" for n in not_allowed},
            "fabric": {"nouns": nouns}}


class Derivation(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = load_script()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.symlink(os.path.join(HERE, "bin", "fabric"), os.path.join(self.tmp.name, "fabric"))
        old = os.environ.get("AGENT_FABRIC_LOCAL_BIN")
        os.environ["AGENT_FABRIC_LOCAL_BIN"] = self.tmp.name
        self.addCleanup(lambda: os.environ.pop("AGENT_FABRIC_LOCAL_BIN") if old is None
                        else os.environ.__setitem__("AGENT_FABRIC_LOCAL_BIN", old))

    def forms(self, nouns: dict, not_allowed: list[str]) -> tuple[list[str], list[str]]:
        return self.mod.fabric_forms(table_doc(nouns, ["fabric", *not_allowed]))

    def test_noun_with_allowed_command_is_allowed_whole(self) -> None:
        allow, ask = self.forms({"jobs": {"command": "fabric-jobs"}}, [])
        self.assertIn("Bash(fabric jobs *)", allow)
        self.assertEqual(ask, [])

    def test_not_allowed_verb_under_allowed_noun_asks(self) -> None:
        allow, ask = self.forms({"x": {"command": "fabric-x", "verbs": {"run": "fabric-x-run", "read": "fabric-x-read"}}},
                                ["fabric-x-run"])
        self.assertIn("Bash(fabric x *)", allow)
        self.assertEqual(ask, ["Bash(fabric x run *)"])
        self.assertNotIn("Bash(fabric x run *)", allow)

    def test_noun_without_command_allows_only_its_allowed_verbs(self) -> None:
        allow, ask = self.forms({"y": {"verbs": {"a": "y-a", "b": "y-b"}}}, ["y-b"])
        self.assertIn("Bash(fabric y a *)", allow)
        self.assertNotIn("Bash(fabric y b *)", allow)
        self.assertNotIn("Bash(fabric y *)", allow)
        self.assertEqual(ask, [])

    def test_noun_with_not_allowed_command_gets_no_noun_rule(self) -> None:
        allow, ask = self.forms({"lease": {"command": "fabric-lease"}}, ["fabric-lease"])
        self.assertEqual([r for r in allow if "lease" in r], [])
        self.assertEqual(ask, [])

    def test_not_allowed_command_noun_still_allows_its_allowed_verbs_by_name(self) -> None:
        # The verbs are dispatched before the noun's own command (table.resolve), so a verb rule never reaches the
        # blocked command; each is as narrow as the command it names.
        allow, ask = self.forms({"z": {"command": "fabric-z", "verbs": {"ok": "z-ok", "no": "z-no"}}},
                                ["fabric-z", "z-no"])
        self.assertIn("Bash(fabric z ok *)", allow)
        self.assertEqual([r for r in allow if r.startswith("Bash(fabric z")], ["Bash(fabric z ok *)"])
        self.assertEqual(ask, [])

    def test_bare_and_help_are_exact_rules_and_the_broad_rule_is_never_derived(self) -> None:
        allow, _ = self.forms({"jobs": {"command": "fabric-jobs"}}, [])
        self.assertIn("Bash(fabric)", allow)
        self.assertIn("Bash(fabric help)", allow)
        self.assertNotIn("Bash(fabric *)", allow)

    def test_foreign_fabric_link_derives_nothing(self) -> None:
        os.remove(os.path.join(self.tmp.name, "fabric"))
        with open(os.path.join(self.tmp.name, "fabric"), "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\n")
        self.assertEqual(self.forms({"jobs": {"command": "fabric-jobs"}}, []), ([], []))

    def test_missing_fabric_link_derives_nothing(self) -> None:
        os.remove(os.path.join(self.tmp.name, "fabric"))
        self.assertEqual(self.forms({"jobs": {"command": "fabric-jobs"}}, []), ([], []))

    def test_owned_namespace_is_the_word_fabric_not_its_prefix(self) -> None:
        for rule in ("Bash(fabric)", "Bash(fabric help)", "Bash(fabric *)", "Bash(fabric jobs *)"):
            self.assertTrue(self.mod.fabric_owned(rule), rule)
        for rule in ("Bash(fabric-lease *)", "Bash(fabricx *)", "Bash(ls *)", "mcp__fabric-memory__memory_find"):
            self.assertFalse(self.mod.fabric_owned(rule), rule)


class SettingsFile(cli.Base):
    def write(self, seed: dict | None = None) -> dict:
        self.put_json(seed or {})
        self.run_raw(self.s)
        return self.doc()["permissions"]

    def test_real_table_rules_are_written_and_the_broad_rule_is_not(self) -> None:
        perm = self.write()
        allow = perm["allow"]
        for want in ("Bash(fabric)", "Bash(fabric help)", "Bash(fabric jobs *)", "Bash(fabric gzcoord inbox *)",
                     "Bash(fabric memory check *)", "Bash(fabric reflect *)", "Bash(fabric repo settings *)"):
            self.assertIn(want, allow)
        self.assertNotIn("Bash(fabric *)", allow)
        for refused in ("lease", "host", "secret-run", "genimage", "resume", "watch", "sign"):
            self.assertEqual([r for r in allow if r.startswith(f"Bash(fabric {refused}")], [], refused)
        self.assertEqual([r for r in perm["ask"] if r.startswith("Bash(fabric")], [])

    def test_every_allowed_noun_of_the_table_has_its_rule(self) -> None:
        # Against the table read here, not a list copied from it: a noun added without a rule is a failure.
        with open(cli.COMMANDS, encoding="utf-8") as fh:
            doc = json.load(fh)
        allow = self.write()["allow"]
        for noun, entry in doc["fabric"]["nouns"].items():
            own = entry.get("command")
            if own and own not in doc["not_allowed"]:
                self.assertIn(f"Bash(fabric {noun} *)", allow)
            for verb, cmd in entry.get("verbs", {}).items():
                if cmd not in doc["not_allowed"] and not (own and own not in doc["not_allowed"]):
                    self.assertIn(f"Bash(fabric {noun} {verb} *)", allow)

    def test_link_check_off_writes_no_fabric_rule(self) -> None:
        link = os.path.join(self.bin, "fabric")
        os.remove(link)
        with open(link, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\necho mine\n")
        perm = self.write()
        self.assertEqual([r for r in perm["allow"] + perm.get("ask", []) if cli_owned(r)], [])
        self.assertIn("Bash(fabric-status *)", perm["allow"])         # positive control: the other commands are unaffected

    def test_rerun_changes_nothing(self) -> None:
        self.write()
        before = self.text()
        self.assertEqual(self.run_s(self.s), self.current)
        self.assertEqual(self.text(), before)

    def test_stale_owned_rules_are_removed_and_the_accounts_own_kept(self) -> None:
        self.write()
        d = self.doc()
        d["permissions"]["allow"] += ["Bash(fabric *)", "Bash(fabric gone *)", "Bash(fabric-lease *)", "Bash(ls *)"]
        d["permissions"]["ask"] += ["Bash(fabric jobs old *)", "Bash(rm *)"]
        self.put_json(d)
        self.assertEqual(self.run_s(self.s), self.wrote)               # settled() sees the stale rules
        perm = self.doc()["permissions"]
        for gone in ("Bash(fabric *)", "Bash(fabric gone *)"):
            self.assertNotIn(gone, perm["allow"])
        self.assertNotIn("Bash(fabric jobs old *)", perm["ask"])
        # fabric-lease is another word: the namespace test must not take it, and the withheld logic is not its business.
        for kept in ("Bash(fabric-lease *)", "Bash(ls *)"):
            self.assertIn(kept, perm["allow"])
        self.assertIn("Bash(rm *)", perm["ask"])
        self.assertEqual(self.run_s(self.s), self.current)

    def test_stale_ask_rule_alone_makes_the_file_unsettled(self) -> None:
        self.write()
        d = self.doc()
        d["permissions"]["ask"].append("Bash(fabric jobs old *)")
        self.put_json(d)
        self.assertEqual(self.run_s(self.s), self.wrote)

    def test_malformed_table_raises_table_error_which_main_refuses(self) -> None:
        # The table is the checkout's file; a shape the parser refuses must not become a traceback.
        mod = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "commands.json")
            with open(cli.COMMANDS, encoding="utf-8") as fh:
                doc = json.load(fh)
            doc["fabric"] = {"nouns": {"jobs": 3}}
            with open(bad, "w", encoding="utf-8") as fh:
                json.dump(doc, fh)
            os.symlink(os.path.join(HERE, "bin", "fabric"), os.path.join(tmp, "fabric"))
            os.environ["AGENT_FABRIC_LOCAL_BIN"] = tmp
            self.addCleanup(os.environ.pop, "AGENT_FABRIC_LOCAL_BIN", None)
            mod.COMMANDS = bad
            with self.assertRaises(mod.table.TableError):
                mod.rules()


def cli_owned(rule: str) -> bool:
    return rule == "Bash(fabric)" or rule.startswith("Bash(fabric ")


if __name__ == "__main__":
    unittest.main()
