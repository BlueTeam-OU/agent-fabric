#!/usr/bin/env python3
"""agentd records each account's weekly usage reset (tools/fabric/control/usage_resets.py, wired by agentd.keep_accounts):
one key, "usage_resets", set in the store's account file, every other byte kept; a read that carries no reset leaves the
field as it was. The store is faked at its three seams (path, lock, put); the sign-in report's shape is read_account's."""
from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import agentd, usage_resets as R  # noqa: E402

OWNER_FILE = (
    '{\n'
    '    "account": "claude-a",\n'
    '    "plan": "Max 20x",\n'
    '    "payment": {"card": "visa \\u2022\\u2022\\u2022\\u2022 4242",   "note": "caf\\u00e9"},\n'
    '    "api_credit": 12.50\n'
    '}\n')
WEEKLY = {"weekday": "thursday", "time_utc": "12:00", "next": "2026-10-01T12:00:00.000Z"}


def row(slug="claude-a", status="ok", resets="2026-10-01T12:00:00.000Z", kind="weekly_all"):
    return {"slug": slug, "status": status, "limits": [
        {"kind": "session", "percent": 4, "resets_at": "2026-09-24T23:00:00.000Z", "model": None},
        {"kind": kind, "percent": 76, "resets_at": resets, "model": None},
        {"kind": "weekly_scoped", "percent": 1, "resets_at": "2026-10-02T00:00:00.000Z", "model": "Fable"}]}


class Store(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(prefix="usage-resets-")
        self.addCleanup(t.cleanup)
        self.dir = t.name
        self.puts: list[dict[str, str]] = []
        self.said: list[str] = []

    def path(self, slug):
        return os.path.join(self.dir, f"{slug}.json")

    def seed(self, slug, text):
        with open(self.path(slug), "w", encoding="utf-8") as fh:
            fh.write(text)

    def text(self, slug):
        with open(self.path(slug), encoding="utf-8") as fh:
            return fh.read()

    def put(self, tree, expect_head=None):
        self.assertEqual(expect_head, "head-1", "the write is pinned to the head the files were read at")
        files = {}
        for f in os.listdir(os.path.join(tree, "accounts")):
            with open(os.path.join(tree, "accounts", f), encoding="utf-8") as fh:
                files[f] = fh.read()
        self.puts.append(files)
        for f, t in files.items():
            self.seed(f[:-5], t)
        return {"changed": True}

    @contextlib.contextmanager
    def locked(self):
        yield "head-1"

    def record(self, rows, **kw):
        return R.record(rows, path_of=self.path, put=kw.pop("put", self.put), locked=kw.pop("locked", self.locked), say=self.said.append)


class Record(Store):
    def test_a_read_with_a_reset_writes_usage_resets_and_keeps_every_other_byte(self):
        self.seed("claude-a", OWNER_FILE)
        self.assertEqual(self.record({"accounts": [row()]}), {"claude-a": "updated"})
        out = self.text("claude-a")
        self.assertEqual(json.loads(out)["usage_resets"], {"weekly": WEEKLY})
        self.assertTrue(out.startswith(OWNER_FILE[:OWNER_FILE.index("\n}")] + ",\n    \"usage_resets\""), out)
        self.assertIn('visa \\u2022\\u2022', out)
        self.assertIn('4242",   "note"', out)
        self.assertEqual({k: v for k, v in json.loads(out).items() if k != "usage_resets"}, json.loads(OWNER_FILE))

    def test_a_read_without_a_reset_leaves_the_file_and_the_field_as_they_were(self):
        keep = OWNER_FILE.replace('"api_credit": 12.50', '"api_credit": 12.50,\n    "usage_resets": {"weekly": {"old": 1}}')
        for no_reset in (row(status="failed"), row(status="busy"), row(status="not-signed-in"), row(kind="session2"),
                         row(resets=None), row(resets="soon"), row(resets=12345), {"slug": "claude-a", "status": "ok"},
                         {"slug": "claude-a", "status": "ok", "limits": "x"}, "junk", None):
            with self.subTest(no_reset=no_reset):
                self.seed("claude-a", keep)
                self.assertEqual(self.record({"accounts": [no_reset]}), {})
                self.assertEqual(self.text("claude-a"), keep)
        self.assertEqual(self.puts, [])
        for rows in (None, [], {"accounts": "x"}, {"status": "none"}):
            self.assertEqual(self.record(rows), {})
        self.assertEqual(self.puts, [])

    def test_positive_control_the_same_file_changes_when_the_read_carries_a_reset(self):
        keep = OWNER_FILE.replace('"api_credit": 12.50', '"api_credit": 12.50,\n    "usage_resets": {"weekly": {"old": 1}}')
        self.seed("claude-a", keep)
        self.record({"accounts": [row()]})
        self.assertEqual(json.loads(self.text("claude-a"))["usage_resets"], {"weekly": WEEKLY})

    def test_an_unchanged_reset_makes_no_commit(self):
        self.seed("claude-a", OWNER_FILE)
        self.record({"accounts": [row()]})
        self.assertEqual(self.record({"accounts": [row()]}), {"claude-a": "unchanged"})
        self.assertEqual(len(self.puts), 1)
        self.record({"accounts": [row(resets="2026-10-08T12:00:00.000Z")]})
        self.assertEqual(len(self.puts), 2, "the next week's reset is a new value")
        self.assertEqual(json.loads(self.text("claude-a"))["usage_resets"]["weekly"]["next"], "2026-10-08T12:00:00.000Z")

    def test_the_report_s_59_second_is_rounded_to_the_hour(self):
        self.seed("claude-a", OWNER_FILE)
        self.record({"accounts": [row(resets="2026-09-28T15:59:59Z")]})
        w = json.loads(self.text("claude-a"))["usage_resets"]["weekly"]
        self.assertEqual((w["weekday"], w["time_utc"], w["next"]), ("monday", "16:00", "2026-09-28T15:59:59Z"))

    def test_a_missing_file_is_created_with_the_account_and_the_key_only(self):
        self.assertEqual(self.record({"accounts": [row("claude-b")]}), {"claude-b": "created"})
        self.assertEqual(json.loads(self.text("claude-b")), {"account": "claude-b", "usage_resets": {"weekly": WEEKLY}})

    def test_one_commit_for_every_changed_file_and_a_refused_file_does_not_stop_the_others(self):
        self.seed("claude-a", OWNER_FILE)
        self.seed("claude-c", "{ not json")
        out = self.record({"accounts": [row("claude-a"), row("claude-c"), row("claude-b"), row("claude-d", status="failed")]})
        self.assertEqual(out, {"claude-a": "updated", "claude-b": "created", "claude-c": "refused: not valid JSON"})
        self.assertEqual(len(self.puts), 1)
        self.assertEqual(sorted(self.puts[0]), ["claude-a.json", "claude-b.json"])
        self.assertEqual(self.text("claude-c"), "{ not json")
        self.assertEqual(self.said, ["agentd: usage resets: claude-c: refused: not valid JSON"])

    def test_a_slug_that_is_no_file_name_is_ignored(self):
        self.assertEqual(self.record({"accounts": [row("../x"), row("A b"), row("")]}), {})
        self.assertEqual(self.puts, [])

    def test_a_store_failure_is_one_line_and_never_raised(self):
        self.seed("claude-a", OWNER_FILE)

        def boom(tree, expect_head=None):
            raise RuntimeError("the store moved while the files were being prepared; nothing written")
        self.assertEqual(self.record({"accounts": [row()]}, put=boom), {})
        self.assertEqual(self.text("claude-a"), OWNER_FILE)
        self.assertEqual(len(self.said), 1)
        self.assertIn("nothing written", self.said[0])

        @contextlib.contextmanager
        def no_store():
            raise OSError("no store")
            yield
        self.assertEqual(self.record({"accounts": [row()]}, locked=no_store), {})
        self.assertEqual(len(self.said), 2)


class Keep(unittest.TestCase):
    class Keeper:
        def __init__(self, r=None, exc=None):
            self.r, self.exc, self.n = r, exc, 0

        def refresh(self):
            self.n += 1
            if self.exc:
                raise self.exc
            return self.r

    def run_keep(self, keeper, present=True, record=None):
        said, got = [], []
        agentd.keep_accounts(keeper, lambda: present, record or got.append, said.append)
        return said, got

    def test_the_read_goes_to_the_record_and_a_failed_row_is_said(self):
        r = {"accounts": [row(), {"slug": "claude-b", "status": "failed", "error": "boom"}]}
        said, got = self.run_keep(self.Keeper(r))
        self.assertEqual(got, [r])
        self.assertEqual(said, ["agentd: account claude-b: failed (boom)"])

    def test_no_sign_in_reads_nothing_and_records_nothing(self):
        k = self.Keeper({"accounts": [row()]})
        said, got = self.run_keep(k, present=False)
        self.assertEqual((k.n, said, got), (0, [], []))

    def test_a_failed_read_records_nothing(self):
        said, got = self.run_keep(self.Keeper(exc=RuntimeError("x")))
        self.assertEqual((said, got), (["agentd: accounts: x"], []))

    def test_a_record_that_raises_does_not_end_the_tick(self):
        def bad(r):
            raise RuntimeError("no store")
        said, _ = self.run_keep(self.Keeper({"accounts": []}), record=bad)
        self.assertEqual(said, ["agentd: usage resets: no store"])


if __name__ == "__main__":
    unittest.main()
