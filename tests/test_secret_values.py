#!/usr/bin/env python3
"""tools/fabric/guards/secret_values.py and the hooks that run it (agent-fabric ADR-012 §5 rule 9): a commit or a push that holds a
value of the committing account's own secrets.env is refused, the variable named and never the value.

The value is a fixture, never a real secret (ADR-012 §5 rule 7), written into the scratch HOME the githook fixture gives every hook
run; every refusal case asserts that the output lacks it. The pre-push leg is in tests/test_githooks_prepush.py (secret_values_push),
which already pushes to a bare remote through the installed hook.

Mutations each case fails on: _check_secret_values removed from pre_commit (staged cases) or from commit_msg (message cases), or
placed after the owner's return (the owner case); a needle form dropped from needles() (the form cases); _base64_runs at one
alignment only (the base64 offsets); a value under MIN_CHARS searched (the short case); IGNORE ignored (the ignored case); the path
printed with a name hit (the name case); a missing file raising (no-file case); an unreadable one admitting (unreadable case); the
scissors' tail searched (scissors case); scan_objects reading blobs only (the history message case)."""
from __future__ import annotations

import base64
import importlib.util
import json
import os
import subprocess
import sys
import unittest
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from githook_fixtures import ROOT, Fabric, Repo  # noqa: E402

_spec = importlib.util.spec_from_file_location("secret_values", os.path.join(ROOT, "tools", "fabric", "guards", "secret_values.py"))
sv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sv)

VALUE = "fixture-not-a-secret-0123456789"
PASS = 'fixture "pass"/word+0123'   # a value whose percent-encoded and JSON forms differ from it as written


def write_secrets(home: str, text: str) -> str:
    d = os.path.join(home, ".config", "agent-fabric")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "secrets.env")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


class Needles(unittest.TestCase):
    def setUp(self):
        self.ns = sv.needles({"FAKE_TOKEN": VALUE})

    def test_each_form_is_found_and_named(self):
        ns = sv.needles({"FAKE_PASS": PASS})
        cases = {
            "as written": f"key = {PASS}\n".encode(),
            "percent-encoded": ("u=" + urllib.parse.quote("a b/" + PASS + "?", safe="")).encode(),
            "JSON-escaped": json.dumps({"k": PASS + "\\"}).encode(),
        }
        for how, data in cases.items():
            with self.subTest(how=how):
                self.assertEqual(sv.find(data, ns), [("FAKE_PASS", how)])

    def test_base64_is_found_at_every_alignment_inside_a_longer_run(self):
        for prefix in ("", "a", "ab", "abc", "abcd"):
            for alt in (False, True):
                with self.subTest(prefix=prefix, urlsafe=alt):
                    enc = (base64.urlsafe_b64encode if alt else base64.b64encode)((prefix + VALUE + "tail").encode())
                    self.assertEqual(sv.find(b"x" + enc + b"y", self.ns), [("FAKE_TOKEN", "base64")])

    def test_a_near_miss_is_not_found(self):
        self.assertEqual(sv.find(VALUE[:-1].encode() + b" " + VALUE[1:].encode(), self.ns), [])

    def test_a_name_with_several_forms_is_reported_once(self):
        self.assertEqual(sv.find(VALUE.encode() + b" " + base64.b64encode(VALUE.encode()), self.ns), [("FAKE_TOKEN", "as written")])


class Load(unittest.TestCase):
    def setUp(self):
        self.fabric = Fabric()
        self.addCleanup(self.fabric.cleanup)

    def test_short_and_ignored_values_are_not_searched_and_a_bad_line_is_skipped(self):
        write_secrets(self.fabric.home, f"export FAKE_TOKEN={VALUE}\nexport SHORT=abcdefg\nexport AGENT_LOGIN=python-dev-01\n"
                                        "export BROKEN='unterminated\n# comment\nPLAIN=not-exported-value\n")
        self.assertEqual(sv.load(self.fabric.home), {"FAKE_TOKEN": VALUE})

    def test_no_file_is_nothing_to_search(self):
        self.assertEqual(sv.load(self.fabric.home), {})

    def test_an_unreadable_file_cannot_judge(self):
        path = write_secrets(self.fabric.home, f"export FAKE_TOKEN={VALUE}\n")
        os.chmod(path, 0)
        self.addCleanup(os.chmod, path, 0o600)
        if os.access(path, os.R_OK):
            self.skipTest("running as a user who reads a mode-0 file")
        with self.assertRaises(sv.CannotJudge):
            sv.load(self.fabric.home)

    def test_the_message_body_drops_comments_and_the_scissors_tail(self):
        text = f"subject\n# {VALUE}\n{sv.SCISSORS}\ndiff {VALUE}\n"
        self.assertEqual(sv.scan_message(text, sv.needles({"FAKE_TOKEN": VALUE})), [])


class Hooks(unittest.TestCase):
    def setUp(self):
        self.fabric = Fabric()
        self.addCleanup(self.fabric.cleanup)
        write_secrets(self.fabric.home, f"export FAKE_TOKEN={VALUE}\nexport FAKE_PASS='{PASS}'\n")
        self.repo = self.fabric.project()

    def assertRefusedNaming(self, r, *words):
        self.assertEqual(r.returncode, 1, r.stderr)
        for w in words or ("FAKE_TOKEN",):
            self.assertIn(w, r.stderr)
        for v in (VALUE, PASS, urllib.parse.quote(PASS, safe="")):
            self.assertNotIn(v, r.stderr + r.stdout)
        self.assertNotIn(base64.b64encode(VALUE.encode()).decode()[:12], r.stderr + r.stdout)

    def test_a_staged_value_is_refused_for_every_role_in_a_project_and_in_the_fabric(self):
        for repo in (self.repo, self.fabric.itself()):
            repo.stage("src/config.txt", f"token={VALUE}\n")
            for role in (None, "fabric-coordinator"):
                with self.subTest(repo=repo.path, role=role):
                    self.fabric.bind(role)
                    self.assertRefusedNaming(self.fabric.hook("pre-commit", repo), "FAKE_TOKEN", "src/config.txt", "ADR-012")

    def test_a_base64_value_in_a_binary_file_is_refused(self):
        self.repo.stage("img.bin", "\0\1" + base64.b64encode(VALUE.encode()).decode() + "\0")
        self.assertRefusedNaming(self.fabric.hook("pre-commit", self.repo), "FAKE_TOKEN", "img.bin", "(base64)")

    def test_a_value_in_a_file_name_is_refused_without_printing_the_name(self):
        self.repo.stage(f"notes/{VALUE}.txt", "harmless\n")
        self.assertRefusedNaming(self.fabric.hook("pre-commit", self.repo), "a file's name holds FAKE_TOKEN")

    def test_the_staged_blob_is_judged_not_the_work_tree(self):
        self.repo.stage("src/config.txt", f"token={VALUE}\n")
        self.repo.write("src/config.txt", "clean\n")
        self.assertRefusedNaming(self.fabric.hook("pre-commit", self.repo), "FAKE_TOKEN", "src/config.txt")

    def test_a_json_escaped_value_is_refused(self):
        self.repo.stage("cfg.json", json.dumps({"p": PASS}) + "\n")
        self.assertRefusedNaming(self.fabric.hook("pre-commit", self.repo), "cfg.json: FAKE_PASS (JSON-escaped)")

    def test_a_clean_commit_and_an_account_without_secrets_are_admitted(self):
        self.repo.stage("src/config.txt", "token=from-the-environment\n")
        r = self.fabric.hook("pre-commit", self.repo)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        os.remove(os.path.join(self.fabric.home, ".config", "agent-fabric", "secrets.env"))
        self.repo.stage("src/other.txt", f"token={VALUE}\n")
        r = self.fabric.hook("pre-commit", self.repo)
        self.assertEqual((r.returncode, r.stderr), (0, ""))

    def test_a_value_in_the_commit_message_is_refused_by_commit_msg(self):
        self.repo.stage("src/config.txt", "clean\n")
        r = self.fabric.commit(self.repo, f"set the key\n\nkey {urllib.parse.quote(PASS, safe='')}\n\nKind: work")
        self.assertRefusedNaming(r, "commit-msg", "the commit message: FAKE_PASS (percent-encoded)")
        r = self.fabric.commit(self.repo, "set the key from the environment\n\nKind: work")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_history_names_a_message_and_a_blob_and_exits_1(self):
        clean = Repo({"a.txt": "clean\n"}, name="history")
        self.addCleanup(clean.cleanup)
        env = {**os.environ, "HOME": self.fabric.home}
        cmd = [sys.executable, os.path.join(ROOT, "tools", "fabric", "guards", "secret_values.py"), "history"]
        r = subprocess.run(cmd, cwd=clean.path, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        clean.commit("b.txt", "ok\n", message=f"message {VALUE}")
        clean.commit("c.json", json.dumps({"k": VALUE}) + "\n")
        clean.commit("c.json", "removed\n")
        r = subprocess.run(cmd, cwd=clean.path, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"commit [0-9a-f]{12}: FAKE_TOKEN")
        self.assertRegex(r.stdout, r"c\.json \(blob [0-9a-f]{12}\): FAKE_TOKEN")
        self.assertNotIn(VALUE, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
