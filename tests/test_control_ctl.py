#!/usr/bin/env python3
"""fabric-ctl (tools/fabric/control/ctl.py) against a fake relay: the request it
posts, the replies it collects, the table it prints, and the row for an agent
that stayed silent. A port of runtime/control/tests/ctl.test.mjs case for
case (ADR-040 Wave 8)."""
from __future__ import annotations

import base64
import datetime
import gzip
import hashlib
import http.server
import io
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import ctl  # noqa: E402
from control.gzcoord import whoami as _whoami  # noqa: E402
from control.sign import (ACTION_TTL_MAX_S, generate_operator_key, private_key_from, public_key_from, verify_request)  # noqa: E402
from control.upgrade import FABRIC_UPGRADE_BUDGET_S, UPGRADE_BUDGET_S, pinned_version  # noqa: E402

BASE = {"targets": [], "op": "status", "json": False, "timeout": 20, "out": None, "days": None, "piece": None, "version": None, "force": False,
        "expect": None, "restart": False, "title": None, "topic": None, "project": None, "priority": None, "role": None, "follow": False, "tool": None}


def base(**over):
    return {**BASE, **over}


def placed(*logins, host="h"):
    return [{"login": l, "host": host, "address": f"{host}/{l}"} for l in logins]


def reply(login, op, data, **more):
    return {"kind": "reply", "from": f"h/{login}", "op": op, "data": data, **more}


class Args(unittest.TestCase):
    def test_parse_args_targets_op_flags_defaults(self):
        self.assertEqual(ctl.parse_args(["all"]), base(targets=["all"]))
        self.assertEqual(ctl.parse_args(["db-admin", "ping", "--json"]), base(targets=["db-admin"], op="ping", json=True, timeout=5))
        self.assertEqual(ctl.parse_args(["all", "memory", "--out", "/tmp/d"]), base(targets=["all"], op="memory", timeout=120, out="/tmp/d"))
        self.assertEqual(ctl.parse_args(["all", "tokens", "--days", "3"]), base(targets=["all"], op="tokens", timeout=60, days=3))
        self.assertEqual(ctl.parse_args(["all", "tokens", "--days=14"])["days"], 14)
        with self.assertRaisesRegex(ctl.CtlError, "--days"):
            ctl.parse_args(["all", "tokens", "--days", "0"])
        with self.assertRaisesRegex(ctl.CtlError, "--days"):
            ctl.parse_args(["all", "status", "--days", "3"])   # a window belongs to tokens only
        self.assertEqual(ctl.parse_args(["all", "memory", "--out=/tmp/d"])["out"], "/tmp/d")
        with self.assertRaisesRegex(ctl.CtlError, "--out"):
            ctl.parse_args(["all", "memory"])   # a drain needs somewhere to land
        self.assertEqual(ctl.parse_args(["a", "b", "usage", "--timeout", "3"])["timeout"], 3)
        self.assertEqual(ctl.parse_args(["a", "b", "usage"])["targets"], ["a", "b"])
        with self.assertRaisesRegex(ctl.CtlError, "unknown option"):
            ctl.parse_args(["all", "--nope"])
        with self.assertRaisesRegex(ctl.CtlError, "--timeout"):
            ctl.parse_args(["all", "--timeout", "20s"])
        with self.assertRaisesRegex(ctl.CtlError, "--timeout"):
            ctl.parse_args(["all", "--timeout=0"])


class Tables(unittest.TestCase):
    def test_rows_and_table_an_answered_account_and_a_silent_one(self):
        expected = placed("db-admin", "web-dev-01")
        replies = [{"kind": "reply", "from": "h/db-admin", "op": "status", "latency_ms": 120,
                    "data": {"identity": {"role": "db-admin", "claude_account": {"email": "x@y.z"}},
                             "usage": {"status": "ok", "five_hour": {"utilization": 12, "resets_at": "2026-09-17T10:50:00+00:00"},
                                       "seven_day": {"utilization": 80, "resets_at": "2026-09-21T16:00:00+00:00"}},
                             "fabric": {"status": "ok", "head": "abc1234", "behind": 2, "dirty": False}}}]
        rs = ctl.rows(expected, replies)
        self.assertEqual((rs[0]["status"], rs[0]["email"], rs[1]["status"]), ("ok", "x@y.z", "no answer"))
        t = ctl.table("status", rs)
        self.assertRegex(t, r"db-admin\s+ok\s+x@y.z\s+12%\s+2026-09-17T10:50\s+80%\s+2026-09-21T16:00\s+db-admin\s+abc1234 \(2 behind\)")
        self.assertRegex(t, r"web-dev-01\s+no answer")
        self.assertRegex(ctl.table("ping", rs), r"db-admin\s+ok\s+120 ms")
        # The script table: the workers column — input and answers binned — and `-` when there are none.
        sc = {"status": "ok", "turns": 3, "thinking": {"letters": 0}, "thinking_blocks": {"only": 0, "mixed": 0, "latin": 0, "empty": 3},
              "text": {"letters": 40, "georgian": 100}, "notes": {"status": "none"}}
        w = {"status": "ok", "files": 2, "other_subagents": 1, "turns": 4, "tool_uses": 0,
             "input": {"letters": 300, "georgian": 100, "blocks": {"only": 3, "mixed": 0, "latin": 1, "empty": 0},
                       "language": {"status": "ok", "paragraphs": 4, "unreliable": 1, "shares": {"ka": 71.4, "en": 28.6}, "dominant": {"ka": 3}}},
             "text": {"letters": 200, "georgian": 100, "blocks": {"only": 4, "mixed": 0, "latin": 0, "empty": 0}, "language": {"status": "unavailable"}}}

        def script(**more):
            return ctl.table("script", ctl.rows(expected, [reply("db-admin", "script", {"script": {**sc, **more}})]))
        st = script(workers=w)
        self.assertRegex(st, r"workers \(input / answers\)")
        self.assertRegex(st, r"db-admin\s+ok\s+none.*2 file\(s\): in 3 only / 0 mixed / 1 latin — lang ka 71.4%, en 28.6% \(1 unreliable\) / "
                             r"out 4 only / 0 mixed / 0 latin — lang unavailable")
        notes = {"status": "ok", "files": 1, "letters": 90, "georgian": 100, "blocks": {"only": 2, "mixed": 0, "latin": 0, "empty": 0},
                 "language": {"status": "ok", "paragraphs": 2, "unreliable": 0, "shares": {"ka": 100}, "dominant": {"ka": 2}}}
        self.assertRegex(script(notes=notes, workers={"status": "none", "other_subagents": 0}), r"1 file\(s\): 2 only / 0 mixed / 0 latin — lang ka 100% — georgian 100%")
        self.assertRegex(script(workers={"status": "none", "other_subagents": 0}), re.compile(r"db-admin\s+ok\s+none.*unreadable\s+-\s*$", re.M))
        self.assertRegex(script(notes={"status": "not measured", "reason": "the source locale"}), r"db-admin\s+ok\s+not measured: the source locale\s")   # never "none", which reads as no notes

    def test_keys_table_held_keys_whether_git_signs_and_a_refused_store_said_in_full(self):
        expected = placed("alpha", "beta", "quiet")
        t = ctl.table("keys", ctl.rows(expected, [
            reply("alpha", "keys", {"keys": [{"name": "GH_TOKEN", "present": True, "sha256_12": "x"}, {"name": "OPENAI_API_KEY", "present": False},
                                              {"name": "signing key secret", "present": True}, {"name": "store commits verified", "present": True}]}),
            reply("beta", "keys", {"keys": [{"name": "GH_TOKEN", "present": True}, {"name": "signing key secret", "present": False},
                                             {"name": "store commits verified", "present": False,
                                              "refused": {"commit": "0123456789ab", "at": "T", "reason": "not signed"}}]})])).split("\n")
        self.assertRegex(t[0], r"^account\s+status\s+keys\s+signing\s+store$")
        self.assertRegex(t[1], r"^alpha\s+ok\s+1/2\s+yes\s+verified$")
        self.assertRegex(t[2], r"^\s+absent: OPENAI_API_KEY$")
        self.assertRegex(t[3], r"^beta\s+ok\s+1/1\s+no\s+REFUSED 0123456789ab at T: not signed$")
        self.assertRegex(t[4], r"^quiet\s+no answer$")
        s = ctl.table("keys", ctl.rows(placed("gamma", "delta"), [
            reply("gamma", "keys", {"keys": [{"name": "store commits verified", "present": False, "state": "no base"}]}),
            reply("delta", "keys", {"keys": [{"name": "store commits verified", "present": False, "state": "verified",
                                              "mirrors": [{"agent_id": "kid-id", "commit": "ffff", "at": "T", "reason": "outsider"}]}]})])).split("\n")
        self.assertRegex(s[1], r"^gamma\s+ok\s+0/0\s+-\s+no base$")   # no base is said, never verified
        self.assertRegex(s[2], r"^delta\s+ok\s+0/0\s+-\s+verified$")
        self.assertRegex(s[3], r"^\s+mirror of kid-id: REFUSED ffff at T: outsider$")   # a mirror's refusal is a line of its own, named
        n = ctl.table("keys", ctl.rows(placed("eps"), [
            reply("eps", "keys", {"keys": [{"name": "store commits verified", "present": False, "state": "verified",
                                            "mirrors": [{"agent_id": "kid-2", "state": "no base"}]}]})])).split("\n")
        self.assertRegex(n[2], r"^\s+mirror of kid-2: no base$")   # a mirror with no base is a line of its own (review of #94)

    def test_keys_table_a_refusal_and_a_key_name_are_the_accounts_their_control_characters_shown_escaped(self):
        t = ctl.table("keys", ctl.rows(placed("beta"), [
            reply("beta", "keys", {"keys": [{"name": "X\u001b[2J", "present": False},
                                            {"name": "store commits verified", "present": False,
                                             "refused": {"commit": "ab\u009bc", "at": "T\u0007", "reason": "git: \u001b]0;pwned\u0007"}}]})]))
        self.assertIsNone(re.search("[\u0000-\u0009\u000b-\u001f\u007f-\u009f]", t), repr(t))
        self.assertTrue("REFUSED ab\\x9bc at T\\x07: git: \\x1b]0;pwned\\x07" in t and "absent: X\\x1b[2J" in t, repr(t))

    def test_disk_table_one_row_per_account_the_largest_home_first_partial_failed_and_silent_are_rows(self):
        G = 1048576
        expected = placed("alpha", "beta", "gamma", "delta", "quiet")

        def r(login, disk):
            return reply(login, "disk", {"disk": disk})
        rs = ctl.rows(expected, [
            r("alpha", {"status": "ok", "total_kb": 2 * G, "largest": [{"name": ".cache", "kb": G}], "targets": [], "targets_kb": 0}),
            r("beta", {"status": "ok", "total_kb": 50 * G, "largest": [{"name": "projects", "kb": 45 * G}],
                       "targets": [{"path": "projects/a/target", "kb": 30 * G}, {"path": "projects/b/target", "kb": 10 * G},
                                   {"path": "projects/c/target", "kb": 2048}, {"path": "projects/d/target", "kb": 512}], "targets_kb": 40 * G + 2560}),
            r("gamma", {"status": "partial", "total_kb": 3072, "largest": [{"name": ".local", "kb": 3072}], "targets": [], "targets_kb": 0,
                        "errors": ["home entries: du exit 1, partial"]}),
            r("delta", {"status": "failed", "error": "/home/delta could not be listed (EACCES)"})])
        t = ctl.table("disk", rs).split("\n")
        self.assertRegex(t[0], r"^account\s+status\s+total\s+largest entry\s+target/\s+target/ directories$")
        self.assertEqual([w for w in (re.split(r"\s+", l)[0] for l in t[1:]) if w], ["beta", "alpha", "gamma", "delta", "quiet"],
                         "the largest home first, then the failed and the silent")
        self.assertRegex(t[1], r"^beta\s+ok\s+50\.0G\s+projects 45\.0G\s+40\.0G\s+projects/a/target 30\.0G, projects/b/target 10\.0G, projects/c/target 2M, \+1$")
        self.assertRegex(t[2], r"^alpha\s+ok\s+2\.0G\s+\.cache 1\.0G\s+0K\s+-$")
        self.assertTrue(any(re.match(r"^gamma\s+partial\s+3M", l) for l in t) and any(re.match(r"^\s+home entries: du exit 1, partial$", l) for l in t),
                        "a partial row says why under it")
        self.assertTrue(any(re.match(r"^delta\s+failed\s+/home/delta could not be listed \(EACCES\)$", l) for l in t))
        self.assertTrue(any(re.match(r"^quiet\s+no answer$", l) for l in t), "an account that did not answer is a row")
        self.assertEqual(len(rs[1]["disk"]["targets"]), 4, "--json carries every target/, the table the first three")
        self.assertEqual(ctl.parse_args(["all", "disk"])["timeout"], 200, "a whole home takes a while: disk waits longer than a status")

    def test_disk_table_round_4_the_failed_rank_above_the_silent_whatever_their_names_control_characters_escaped(self):
        expected = placed("aaa-quiet", "mid", "zzz-failed")
        t = ctl.table("disk", ctl.rows(expected, [
            reply("zzz-failed", "disk", {"disk": {"status": "failed", "error": "no\u0007bell"}}),
            reply("mid", "disk", {"disk": {"status": "ok", "total_kb": 5, "largest": [{"name": "evil\u001b[2Jname", "kb": 5}],
                                           "targets": [{"path": "projects/x\u009b/target", "kb": 1}], "targets_kb": 1}})])).split("\n")
        self.assertEqual([re.split(r"\s+", l)[0] for l in t[1:]], ["mid", "zzz-failed", "aaa-quiet"], "ok, then failed, then silent")
        self.assertTrue("evil\\x1b[2Jname" in t[1] and "projects/x\\x9b/target" in t[1] and not re.search("[\u0000-\u001f\u007f-\u009f]", "".join(t)), repr(t))
        self.assertIn("no\\x07bell", t[2])

    def test_disk_table_a_status_and_a_size_are_the_accounts_too_escaped_and_a_size_that_is_no_number_is_not_formatted(self):
        t = ctl.table("disk", ctl.rows(placed("odd"), [
            reply("odd", "disk", {"disk": {"status": "ok\u001b[2J", "total_kb": "9\u0007", "largest": [{"name": "n", "kb": "x\u009b"}],
                                           "targets": [{"path": "p", "kb": 1}], "targets_kb": 2048}})]))
        self.assertIsNone(re.search("[\u0000-\u0009\u000b-\u001f\u007f-\u009f]", t), repr(t))
        self.assertTrue("ok\\x1b[2J" in t and "9\\x07" in t and "n x\\x9b" in t and " 2M " in t, repr(t))

    def test_host_table_one_row_per_host_from_whichever_answered_first_a_silent_host_is_a_row_leases_and_largest_under_it(self):
        expected = [{"login": "a", "host": "h1", "address": "h1/a"}, {"login": "b", "host": "h1", "address": "h1/b"}, {"login": "c", "host": "h2", "address": "h2/c"}]
        machine = {"status": "ok", "cpus": 6, "loadavg": [0.9, 1.2, 0.8], "mem_mb": {"total": 18152, "available": 12685, "swap_total": 9216, "swap_free": 9216},
                   "balloon_mb": {"current": 18345, "target": 18345, "static_max": 18363}, "disk": [{"mount": "/rw", "size_gb": 295, "avail_gb": 41, "use_pct": 87}],
                   "leases": [{"name": "backend-test", "holder": "db-admin", "pid": 42, "since": "2026-09-19T08:26:43Z"}],
                   "top_rss": [{"user": "backend-dev-02", "pid": 1, "rss_mb": 2140, "comm": "dotnet"}]}

        def hreply(frm, host):
            return {"kind": "reply", "from": frm, "op": "host", "data": {"host": host}}
        rs = ctl.rows(expected, [hreply("h1/a", machine), hreply("h1/b", {**machine, "loadavg": [9, 9, 9]})])
        self.assertEqual(rs[0]["machine"], machine)
        t = ctl.table("host", rs)
        self.assertRegex(t, re.compile(r"^h1\s+2/2\s+0\.90 1\.20 0\.80\s+6\s+12685/18152\s+9216\s+18345/18363\s+/rw 41G free \(87%\)$", re.M), "the first answer speaks for the host")
        self.assertEqual(len(re.findall(r"^h1\s", t, re.M)), 1, "one row per host, not per account")
        self.assertRegex(t, r"leases: backend-test: db-admin pid 42 since 08:26Z")
        self.assertRegex(t, r"largest: dotnet backend-dev-02 2140 MB")
        self.assertRegex(t, re.compile(r"^h2\s+0/1\s+no answer$", re.M))
        partial = ctl.table("host", ctl.rows(expected, [hreply("h1/a", machine)]))
        self.assertRegex(partial, re.compile(r"^h1\s+1/2\s", re.M))
        self.assertRegex(partial, re.compile(r"^\s+b: no answer$", re.M), "the silent account is named under its host")
        self.assertRegex(ctl.table("host", ctl.rows(expected, [hreply("h1/a", {**machine, "balloon_mb": None})])), r"\s+none\s+/rw", "no balloon: none")
        # every account failed: the failure text and each account's line, not a bare word
        failed = ctl.table("host", ctl.rows(expected, [hreply("h1/a", {"status": "failed", "error": "EACCES /proc"})]))
        self.assertRegex(failed, re.compile(r"^h1\s+1/2\s+failed: EACCES /proc$", re.M))
        self.assertRegex(failed, re.compile(r"^\s+a: failed$", re.M))
        self.assertRegex(failed, re.compile(r"^\s+b: no answer$", re.M))
        # the row with the balloon's static-max speaks for the host, whichever account answered first
        no_max = {**machine, "balloon_mb": {"current": 18345, "target": 18345, "static_max": None}}
        pref = ctl.table("host", ctl.rows(expected, [hreply("h1/a", no_max), hreply("h1/b", machine)]))
        self.assertRegex(pref, r"18345/18363", "the operator's row (the one that can read xenstore) is preferred")

    def test_tokens_table_grouped_by_claude_account_each_logins_share_the_broker_column_apart_a_login_without_records_named(self):
        expected = placed("a", "b", "c", "d")

        def tok(claude, broker, top):
            return {"status": "ok", "days": 7, "files": 1, "requests": {"session": 1, "subagent": 0},
                    "models": {top: {"equiv": claude, "requests": 1, "input": 0, "cache_write": 0, "cache_read": 0, "output": 0, "path": "claude"}},
                    "claude": {"requests": 3, "input": 0, "cache_write": 0, "cache_read": 4000000, "output": 5000, "equiv": claude},
                    "broker": {"requests": 2, "input": 0, "cache_write": 0, "cache_read": 0, "output": 0, "equiv": broker}}

        def treply(login, email, t):
            return reply(login, "tokens", {"identity": {"claude_account": {"email": email} if email else None}, "tokens": t})
        rs = ctl.rows(expected, [treply("a", "x@y.z", tok(3000000, 100000, "claude-opus-5")), treply("b", "x@y.z", tok(1000000, 0, "claude-sonnet-5")),
                                 treply("c", "q@y.z", tok(500, 0, "claude-opus-5")), treply("d", "x@y.z", {"status": "no-records", "days": 7})])
        t = ctl.table("tokens", rs)
        self.assertRegex(t, re.compile(r"^account\s+status\s+claude account\s+share\s+claude equiv.*top model \(7 days\)", re.M))
        self.assertRegex(t, re.compile(r"^a\s+ok\s+x@y.z\s+75%\s+3.0M\s+3\s+4.0M\s+5k\s+100k\s+2\s+claude-opus-5 3.0M$", re.M))
        self.assertRegex(t, re.compile(r"^b\s+ok\s+x@y.z\s+25%\s+1.0M", re.M))
        self.assertRegex(t, re.compile(r"= x@y.z\s+100%\s+4.0M\s+6$", re.M), "an account with two logins gets a sum line")
        self.assertRegex(t, re.compile(r"^c\s+ok\s+q@y.z\s+100%\s+500\b", re.M), "the only login on its account holds all of it")
        self.assertNotIn("= q@y.z", t, "no sum line for one login")
        self.assertRegex(t, re.compile(r"^d\s+ok\s+x@y.z\s+tokens no-records$", re.M))
        self.assertLess(t.index("q@y.z"), t.index("x@y.z"), "accounts in order")


def tar_with(manifest: dict, filler: int = 1200) -> bytes:
    """A tar as the harvester writes it: manifest.json first (ustar header, size in octal), then padding."""
    body = (json.dumps(manifest) + "\n").encode()
    h = bytearray(512)

    def put(text: str, at: int) -> None:
        h[at:at + len(text)] = text.encode()
    put("manifest.json", 0)
    put("0000644\0", 100)
    put("0000000\0", 108)
    put("0000000\0", 116)
    put(f"{len(body):o}".rjust(11, "0") + "\0", 124)
    put("00000000000\0", 136)
    put("        ", 148)
    put("0", 156)
    put("ustar\0", 257)
    put("00", 263)
    put(f"{sum(h):o}".rjust(6, "0") + "\0 ", 148)
    return bytes(h) + body + bytes((512 - len(body) % 512) % 512) + os.urandom(filler)


class Bundles(unittest.TestCase):
    def scratch(self, prefix: str) -> str:
        d = tempfile.mkdtemp(prefix=prefix)
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        return d

    # The bundles a drain answers with, put back together: by slug and part,
    # gunzipped, checked against the sha the report named, written under the
    # login; anything short, corrupt or wrong-sha is a status, not a file.
    def test_write_bundles_the_projects_roots_bundle_and_the_checkouts_are_two_files_a_second_for_one_file_is_refused(self):
        out = self.scratch("drain-root-")
        tar = tar_with({"format": "agent-fabric-drain/1", "agent": "db-admin", "host": "h"})
        sha = hashlib.sha256(tar).hexdigest()
        b64 = base64.b64encode(gzip.compress(tar)).decode()
        wc = "/h/db-admin/projects/agent-fabric"

        def bundle(slug, **over):
            return {"slug": slug, "working_copy": wc, "files": 1, "status": "ok", "bytes": len(tar), "sha256": sha, "parts": 1, **over}
        expected = placed("db-admin")
        replies = [{"from": "h/db-admin", "data": {"memory": {"status": "ok", "bundles": [bundle("s-fabric"), bundle("s-root", projects_root=True), bundle("s-again")]}}}]
        parts = {"h/db-admin": {ctl.part_key("h/db-admin", {"slug": s, "part": 1}): {"slug": s, "part": 1, "parts": 1, "chunk": b64} for s in ("s-fabric", "s-root", "s-again")}}
        ctl.write_bundles(out, expected, replies, parts)
        fabric, root, again = replies[0]["data"]["memory"]["bundles"]
        self.assertEqual(fabric["written"], os.path.join(out, "db-admin", "agent-fabric.tar"))
        self.assertEqual(root["written"], os.path.join(out, "db-admin", "agent-fabric-projects-root.tar"))
        self.assertEqual((again["status"], again["written"]), ("duplicate-target", None))
        self.assertEqual(sorted(os.listdir(os.path.join(out, "db-admin"))), ["agent-fabric-projects-root.tar", "agent-fabric.tar"])

    def test_write_bundles_makes_every_directory_it_creates_private(self):
        base = self.scratch("drain-new-")
        out = os.path.join(base, "not", "yet", "there")
        tar = tar_with({"format": "agent-fabric-drain/1", "agent": "db-admin", "host": "h"})
        b64 = base64.b64encode(gzip.compress(tar)).decode()
        replies = [{"from": "h/db-admin", "data": {"memory": {"status": "ok", "bundles": [
            {"slug": "s", "working_copy": "/h/db-admin/projects/gzapp", "files": 1, "status": "ok", "sha256": hashlib.sha256(tar).hexdigest(), "parts": 1}]}}}]
        parts = {"h/db-admin": {ctl.part_key("h/db-admin", {"slug": "s", "part": 1}): {"slug": "s", "part": 1, "parts": 1, "chunk": b64}}}
        ctl.write_bundles(out, placed("db-admin"), replies, parts)
        self.assertEqual(replies[0]["data"]["memory"]["bundles"][0]["status"], "ok")
        for d in (os.path.join(base, "not"), os.path.join(base, "not", "yet"), out, os.path.join(out, "db-admin")):
            self.assertEqual(stat.S_IMODE(os.stat(d).st_mode), 0o700, d)   # a drain is other people's memory: no directory of it is group- or world-readable

    def test_write_bundles_reassembly_and_the_three_ways_a_bundle_is_refused(self):
        out = self.scratch("drain-out-")
        tar = tar_with({"format": "agent-fabric-drain/1", "agent": "db-admin", "host": "h"})
        sha = hashlib.sha256(tar).hexdigest()
        self.assertEqual(ctl.manifest_agent(tar), "db-admin")
        self.assertIsNone(ctl.manifest_agent(os.urandom(2000)))
        b64 = base64.b64encode(gzip.compress(tar)).decode()
        cut = -(-len(b64) // 2)
        chunks = [b64[:cut], b64[cut:]]

        def bundle(slug, wc, **over):
            return {"slug": slug, "working_copy": wc, "files": 2, "status": "ok", "bytes": len(tar), "sha256": sha, "parts": 2, **over}
        expected = placed("db-admin", "web-dev-01", "silent")
        replies = [
            {"from": "h/db-admin", "data": {"memory": {"status": "ok", "bundles": [
                bundle("s-a", "/h/db-admin/projects/gzapp"), bundle("s-b", "/h/db-admin/projects/other", sha256="not-the-sha"),
                bundle("s-c", "/h/db-admin/projects/short"), {"slug": "s-d", "files": 1, "status": "no-working-copy"}]}}},
            {"from": "h/web-dev-01", "data": {"memory": {"status": "ok", "bundles": [bundle("s-e", "/h/web-dev-01/projects/gzapp")]}}}]

        def as_map(frm, lst):
            m: dict = {}
            for p in lst:
                m.setdefault(ctl.part_key(frm, p), p)
            return m
        parts = {"h/db-admin": as_map("h/db-admin", [
                     {"slug": "s-b", "part": 1, "parts": 2, "chunk": chunks[0]}, {"slug": "s-a", "part": 2, "parts": 2, "chunk": chunks[1]},
                     {"slug": "s-b", "part": 2, "parts": 2, "chunk": chunks[1]}, {"slug": "s-a", "part": 1, "parts": 2, "chunk": chunks[0]},
                     {"slug": "s-a", "part": 1, "parts": 2, "chunk": "a replayed copy of part 1"}, {"slug": "s-c", "part": 1, "parts": 2, "chunk": chunks[0]}]),
                 "h/web-dev-01": as_map("h/web-dev-01", [
                     {"slug": "s-e", "part": 1, "parts": 2, "chunk": "not base64 of a gzip!!"}, {"slug": "s-e", "part": 2, "parts": 2, "chunk": ""},
                     {"slug": "s-f", "part": 1, "parts": 2, "chunk": chunks[0]}, {"slug": "s-f", "part": 2, "parts": 2, "chunk": chunks[1]}])}
        replies[1]["data"]["memory"]["bundles"].append(bundle("s-f", "/h/web-dev-01/projects/gzapp2"))   # a bundle whose manifest says db-admin, under web-dev-01's name
        ctl.write_bundles(out, expected, replies, parts)
        a, b, c, d = replies[0]["data"]["memory"]["bundles"]
        self.assertEqual(a["status"], "ok")
        self.assertEqual(a["written"], os.path.join(out, "db-admin", "gzapp.tar"))
        with open(a["written"], "rb") as fh:
            self.assertEqual(fh.read(), tar, "parts out of order on the wire, a replayed one ignored, in order in the file")
        self.assertEqual(stat.S_IMODE(os.stat(a["written"]).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(out, "db-admin")).st_mode), 0o700)
        # A tree an earlier drain left world-readable is tightened on the next write, not kept.
        os.chmod(a["written"], 0o644)
        os.chmod(os.path.join(out, "db-admin"), 0o755)
        a["status"] = "ok"
        del a["written"]
        ctl.write_bundles(out, expected, replies, parts)
        self.assertEqual(stat.S_IMODE(os.stat(a["written"]).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(out, "db-admin")).st_mode), 0o700)
        self.assertEqual((b["status"], c["status"], d["status"]), ("sha-mismatch", "incomplete", "no-working-copy"))
        self.assertEqual(replies[1]["data"]["memory"]["bundles"][0]["status"], "unreadable")
        self.assertEqual(replies[1]["data"]["memory"]["bundles"][1]["status"], "wrong-agent")
        self.assertEqual(replies[1]["data"]["memory"]["bundles"][1]["manifest_agent"], "db-admin")
        self.assertEqual(os.listdir(os.path.join(out, "db-admin")), ["gzapp.tar"], "a refused bundle leaves no file")
        self.assertFalse(os.path.exists(os.path.join(out, "web-dev-01")) or os.path.exists(os.path.join(out, "silent")))
        t = ctl.table("memory", ctl.rows(expected, replies))
        self.assertRegex(t, r"db-admin\s+ok\s+gzapp\s+2 memories\s+ok -> .*gzapp\.tar")
        self.assertRegex(t, r"db-admin\s+ok\s+other\s+2 memories\s+sha-mismatch")
        self.assertRegex(t, r"web-dev-01\s+ok\s+gzapp2\s+2 memories\s+wrong-agent: manifest names db-admin")
        failed = ctl.table("memory", ctl.rows(expected, [
            {"from": "h/silent", "data": {"memory": {"status": "failed", "error": "boom"}}},
            {"from": "h/db-admin", "data": {"memory": {"status": "ok", "bundles": [
                {"slug": "x", "working_copy": "/h/db-admin/projects/gzapp", "files": 3, "status": "harvest-failed",
                 "error": "harvest_memory: refusing rather than guessing where these belong:\n  leaky.md: carries a credential by shape"}]}}}]))
        self.assertRegex(failed, r"silent\s+ok\s+memory failed: boom")
        self.assertRegex(failed, r"db-admin\s+ok\s+gzapp\s+3 memories\s+harvest-failed: .*leaky\.md: carries a credential by shape")
        self.assertRegex(t, r"db-admin\s+ok\s+s-d\s+1 memories\s+no-working-copy")
        self.assertRegex(t, r"silent\s+no answer")
        self.assertRegex(ctl.table("memory", ctl.rows(expected, [{"from": "h/silent", "data": {"memory": {"status": "ok", "bundles": []}}}])), r"silent\s+ok\s+no memory")
        root_row = ctl.table("memory", ctl.rows(expected, [{"from": "h/db-admin", "data": {"memory": {"status": "ok", "bundles": [
            {"slug": "-h-db-admin-projects", "working_copy": "/h/db-admin/projects/agent-fabric", "projects_root": True, "files": 2, "status": "harvest-failed", "error": "x"}]}}}]))
        self.assertRegex(root_row, r"db-admin\s+ok\s+agent-fabric \(projects root\)\s+2 memories", "the projects root's memory is named as such")


CTL = os.path.join(HERE, "tools", "fabric", "control", "ctl.py")


class Relay:
    """A fake relay, in the shape the real one answers: /api/messages (since_id
    -> the rows after it, or the warning when it is not there) and /api/send."""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.hits: list[str] = []
        self.seq = 0
        self.lock = threading.Lock()
        relay = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_a):
                pass

            def _json(self, obj, status=200):
                body = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                import urllib.parse as up
                u = up.urlsplit(self.path)
                q = dict(up.parse_qsl(u.query))
                with relay.lock:
                    relay.hits.append(u.path + ("?" + u.query if u.query else ""))
                    if u.path == "/api/messages":
                        since = q.get("since_id")
                        ids = [r["id"] for r in relay.rows]
                        i = ids.index(since) if since in ids else -1
                        if since and i < 0:
                            return self._json({"messages": [], "warning": "since_id_not_found"})
                        return self._json({"messages": relay.rows[i + 1:] if since else list(relay.rows)})
                self._json({}, 404)

            def do_POST(self):
                n = int(self.headers.get("content-length") or 0)
                body = self.rfile.read(n)
                with relay.lock:
                    relay.hits.append(self.path)
                if self.path == "/api/send":
                    j = json.loads(body)
                    r = relay.add(j["sender"], j["content"])
                    return self._json({"seq": r["seq"], "id": r["id"]})
                self._json({}, 404)
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def add(self, sender: str, content: str) -> dict:
        with self.lock:
            self.seq += 1
            r = {"seq": self.seq, "id": f"id-{self.seq}", "sender": sender, "content": content, "timestamp": "T"}
            self.rows.append(r)
            return r

    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def request(self) -> dict | None:
        """The first request record posted."""
        with self.lock:
            for r in self.rows:
                try:
                    if json.loads(r["content"]).get("kind") == "request":
                        return json.loads(r["content"])
                except ValueError:
                    continue
        return None


def run_ctl(tc: unittest.TestCase, url: str, registry: str, args: list[str], extra_env: dict | None = None, timeout: float = 120) -> subprocess.CompletedProcess:
    home = tempfile.mkdtemp(prefix="ctl-home-")
    tc.addCleanup(lambda: __import__("shutil").rmtree(home, ignore_errors=True))
    env = {"PATH": os.environ["PATH"], "HOME": home, "CLAUDE_BRIDGE_URL": url, "CLAUDE_BRIDGE_AUTH_TOKEN": "tok", "FABRIC_CONTROL_CHANNEL": "test:control",
           "AGENT_FABRIC_HOSTS_REGISTRY": registry, **(extra_env or {})}
    return subprocess.run([sys.executable, CTL, *args], capture_output=True, text=True, env=env, timeout=timeout, stdin=subprocess.DEVNULL, check=False)


def after(delay: float, fn) -> threading.Timer:
    t = threading.Timer(delay, fn)
    t.daemon = True
    t.start()
    return t


ME = _whoami()
H = ME["host"]


def registry_file(tc: unittest.TestCase, operator: str | None = None) -> str:
    """The placements live on THIS host with THIS login as its operator, whatever
    they are (CI runs as runner): fabric-ctl refuses to send as a non-operator."""
    d = tempfile.mkdtemp(prefix="reg-")
    tc.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
    f = os.path.join(d, "registry.json")
    with open(f, "w") as fh:
        json.dump({"hosts": {H: {"operator": operator or ME["agent"]}}, "placement": {"db-admin": H, "web-dev-01": H, "edge-hosting": H}}, fh)
    return f


class Answering:
    """A responder that waits for the request on the relay and answers it once."""

    def __init__(self, relay: Relay, respond) -> None:
        self.relay, self.respond, self.done = relay, respond, False
        self.timer: threading.Timer | None = None
        self.arm()

    def arm(self) -> None:
        self.done = False
        self.timer = after(0.05, self.poll)

    def poll(self) -> None:
        if self.done:
            return
        req = self.relay.request()
        if req is None:
            self.timer = after(0.05, self.poll)
            return
        self.done = True
        self.respond(req["id"])

    def stop(self) -> None:
        self.done = True


def reply_record(relay: Relay, from_: str, rid: str, op: str, data: dict, **more) -> None:
    relay.add(from_, json.dumps({"v": 1, "kind": "reply", "id": "r-" + os.urandom(4).hex(), "in_reply_to": rid, "from": from_, "op": op, "ok": True, "data": data, **more}))


class Commands(unittest.TestCase):
    def setUp(self) -> None:
        self.relay = Relay()
        self.addCleanup(self.relay.close)

    def test_fabric_ctl_all_usage_two_of_three_answer_table_a_no_answer_row_exit_1_json_one_line_each(self):
        r = self.relay
        reg = registry_file(self)

        def respond(rid: str) -> None:
            reply_record(r, f"{H}/db-admin", rid, "usage", {"usage": {"status": "ok", "five_hour": {"utilization": 4, "resets_at": "2026-09-17T10:50:00+00:00"},
                                                                       "seven_day": {"utilization": 14, "resets_at": "2026-09-21T16:00:00+00:00"}}})
            reply_record(r, f"{H}/web-dev-01", rid, "usage", {"usage": {"status": "no-credentials"}})
            r.add(f"{H}/edge-hosting", json.dumps({"v": 1, "kind": "reply", "id": "x", "in_reply_to": "someone-else", "from": f"{H}/edge-hosting", "op": "usage", "ok": True, "data": {}}))   # not our request
        a = Answering(r, respond)
        self.addCleanup(a.stop)
        out = run_ctl(self, r.url(), reg, ["all", "usage", "--timeout", "3"])
        self.assertEqual(out.returncode, 1, out.stderr)
        self.assertRegex(out.stdout, r"db-admin\s+ok\s+-\s+4%\s+2026-09-17T10:50\s+14%")
        self.assertRegex(out.stdout, r"web-dev-01\s+ok\s+-\s+no-credentials")
        self.assertRegex(out.stdout, r"edge-hosting\s+no answer")
        req = json.loads(r.rows[0]["content"])
        self.assertEqual((req["kind"], req["op"], req["to"]), ("request", "usage", "*"))
        self.assertRegex(req["from"], r"^[^/]+/[^/]+$", "from is this login's own address, whatever the login is (CI runs as runner)")
        self.assertFalse(any(h.startswith("/api/ack") or h.startswith("/api/wait") for h in r.hits), "history reads only, no cursor")
        j = run_ctl(self, r.url(), reg, ["db-admin", "ping", "--json", "--timeout", "1"])
        self.assertEqual(j.returncode, 1)
        self.assertEqual(json.loads(j.stdout.strip()), {"account": "db-admin", "host": H, "status": "no answer"})
        # Not the operator: refused before anything is posted.
        n = len(r.rows)
        no = run_ctl(self, r.url(), registry_file(self, "someone-else"), ["db-admin", "ping", "--timeout", "1"])
        self.assertEqual(no.returncode, 2, no.stderr)
        self.assertRegex(no.stderr, r"not a host operator")
        self.assertEqual(len(r.rows), n, "nothing was sent")
        # The relay lost the request (history cleared): said, and the run ends early.
        r.rows.clear()   # the earlier runs' records
        stop = threading.Event()

        def clear() -> None:
            if stop.is_set():
                return
            if any('"request"' in x["content"] for x in list(r.rows)):
                r.rows.clear()
                return
            after(0.02, clear)
        after(0.02, clear)
        self.addCleanup(stop.set)
        lost = run_ctl(self, r.url(), reg, ["db-admin", "ping", "--timeout", "5"])
        # Ended early, read from the run's own words rather than the clock (a
        # loaded host failed a 4 s bound): a run that kept reading after the
        # warning would see it again every half second until the timeout.
        self.assertEqual(lost.returncode, 1)
        self.assertEqual(len(re.findall(r"history cleared", lost.stderr)), 1, lost.stderr)

    def test_fabric_ctl_memory_out_the_report_record_then_the_parts_the_tar_lands_under_the_login(self):
        r = self.relay
        reg = registry_file(self)
        tar = tar_with({"format": "agent-fabric-drain/1", "agent": "db-admin", "host": H}, 4000)
        sha = hashlib.sha256(tar).hexdigest()
        b64 = base64.b64encode(gzip.compress(tar)).decode()
        cut = -(-len(b64) // 3)
        chunks = [b64[:cut], b64[cut:2 * cut], b64[2 * cut:]]
        frm = f"{H}/db-admin"
        out = tempfile.mkdtemp(prefix="drain-")
        self.addCleanup(lambda: __import__("shutil").rmtree(out, ignore_errors=True))

        def full(rid: str) -> None:
            reply_record(r, frm, rid, "memory", {"memory": {"status": "ok", "bundles": [{
                "slug": "s-1", "working_copy": "/home/db-admin/projects/gzapp", "files": 7, "status": "ok", "bytes": len(tar), "gzip_bytes": 4100, "sha256": sha, "parts": 3,
                "report": {"claims": 5, "counts": {"in_scope": 7, "total": 7}, "needs_rendering": ["ka-a", "ka-b"], "skipped_no_roles_class": ["private"]}}]}, "parts": 3})
            reply_record(r, frm, rid, "memory", {"part": {"slug": "s-1", "part": 1, "parts": 3, "chunk": chunks[0]}})
            reply_record(r, frm, rid, "memory", {"part": {"slug": "s-1", "part": 1, "parts": 3, "chunk": chunks[0]}})   # replayed: must not count as the second part

            def late() -> None:
                reply_record(r, frm, rid, "memory", {"part": {"slug": "s-1", "part": 2, "parts": 3, "chunk": chunks[1]}})
                reply_record(r, frm, rid, "memory", {"part": {"slug": "s-1", "part": 3, "parts": 3, "chunk": chunks[2]}})
            after(0.8, late)   # the last two parts arrive a moment later: the poll must keep going past the first record
        a = Answering(r, full)
        self.addCleanup(a.stop)
        res = run_ctl(self, r.url(), reg, ["db-admin", "memory", "--out", out, "--timeout", "8"])
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        self.assertEqual(json.loads(r.rows[0]["content"])["op"], "memory")
        file = os.path.join(out, "db-admin", "gzapp.tar")
        with open(file, "rb") as fh:
            self.assertEqual(fh.read(), tar)
        self.assertRegex(res.stdout, r"db-admin\s+ok\s+gzapp\s+7 memories\s+ok -> .*gzapp\.tar\s+5 claim\(s\), 2 need rendering, 1 skipped")
        # --json: the row carries the report and where the tar went, never a chunk
        r.rows.clear()
        a.arm()
        j = run_ctl(self, r.url(), reg, ["db-admin", "memory", "--out", out, "--json", "--timeout", "8"])
        self.assertEqual(j.returncode, 0, j.stderr)
        row = json.loads(j.stdout.strip())
        self.assertEqual(row["memory"]["bundles"][0]["written"], file)
        self.assertEqual(row["memory"]["bundles"][0]["report"]["needs_rendering"], ["ka-a", "ka-b"])
        self.assertNotIn(chunks[0][:40], j.stdout, "no chunk in the output")
        # One announced part never arrives: the run waits to its timeout, the bundle is incomplete, nothing is written, exit 1.
        __import__("shutil").rmtree(os.path.join(out, "db-admin"))
        r.rows.clear()

        def short(rid: str) -> None:
            reply_record(r, frm, rid, "memory", {"memory": {"status": "ok", "bundles": [{
                "slug": "s-1", "working_copy": "/home/db-admin/projects/gzapp", "files": 7, "status": "ok", "bytes": len(tar), "sha256": sha, "parts": 3, "report": None}]}, "parts": 3})
            reply_record(r, frm, rid, "memory", {"part": {"slug": "s-1", "part": 1, "parts": 3, "chunk": chunks[0]}})
            reply_record(r, frm, rid, "memory", {"part": {"slug": "s-1", "part": 3, "parts": 3, "chunk": chunks[2]}})
        a2 = Answering(r, short)
        self.addCleanup(a2.stop)
        s = run_ctl(self, r.url(), reg, ["db-admin", "memory", "--out", out, "--timeout", "2"])
        self.assertTrue(a2.done)
        self.assertEqual(s.returncode, 1, s.stderr + s.stdout)
        self.assertRegex(s.stdout, r"db-admin\s+ok\s+gzapp\s+7 memories\s+incomplete")
        self.assertFalse(os.path.exists(file), "nothing written for a short bundle")
        # A daemon whose whole memory section failed: the row says so and the exit code is 1, as for a refused bundle.
        r.rows.clear()
        a3 = Answering(r, lambda rid: reply_record(r, frm, rid, "memory", {"memory": {"status": "failed", "error": "boom"}, "parts": 0}))
        self.addCleanup(a3.stop)
        f = run_ctl(self, r.url(), reg, ["db-admin", "memory", "--out", out, "--timeout", "5"])
        self.assertEqual(f.returncode, 1, f.stderr + f.stdout)
        self.assertRegex(f.stdout, r"db-admin\s+ok\s+memory failed: boom")


class Operator:
    """The operator's own store as fabric-ctl reads it at signing time: a
    scratch keyring outside the scratch HOME (gpg treats GNUPGHOME equal to
    $HOME/.gnupg as the default and puts its agent's socket elsewhere) and a
    pass-layout store whose env/FABRIC_CONTROL_SIGNING_KEY.gpg, when a key is
    given, is encrypted to it. The keyring's agent is the caller's to end:
    done() at cleanup, so the run leaves no process it did not find."""

    def __init__(self, tc: unittest.TestCase, private_spec: str | None) -> None:
        self.gnupg = tempfile.mkdtemp(prefix="ctl-gnupg-")
        self.store = tempfile.mkdtemp(prefix="ctl-store-")
        tc.addCleanup(self.done)
        self.env = {"GNUPGHOME": self.gnupg, "AGENT_FABRIC_SECRET_STORE": self.store}
        self._gpg(["--quick-gen-key", "operator <operator@agents.agent-fabric>", "future-default", "default", "never"])
        os.mkdir(os.path.join(self.store, "env"))
        if private_spec:
            self._gpg(["--trust-model", "always", "-r", "operator@agents.agent-fabric", "--output",
                       os.path.join(self.store, "env", "FABRIC_CONTROL_SIGNING_KEY.gpg"), "--encrypt"], private_spec.encode())

    def _gpg(self, args: list[str], data: bytes | None = None) -> bytes:
        r = subprocess.run(["gpg", "--batch", "--yes", "--no-tty", "--pinentry-mode", "loopback", "--passphrase", "", *args], input=data,
                           capture_output=True, timeout=60, env={**os.environ, "GNUPGHOME": self.gnupg}, check=False)
        if r.returncode != 0:
            raise RuntimeError(f"gpg {args[0]}: {r.stderr.decode(errors='replace')}")
        return r.stdout

    def done(self) -> None:
        subprocess.run(["gpgconf", "--homedir", self.gnupg, "--kill", "all"], stdin=subprocess.DEVNULL, capture_output=True, timeout=30, check=False)
        for d in (self.gnupg, self.store):
            __import__("shutil").rmtree(d, ignore_errors=True)


class Said:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, m: str) -> None:
        self.lines.append(m)

    def text(self) -> str:
        return "\n".join(self.lines)


class Actions(unittest.TestCase):
    def test_accounts_one_row_per_observed_claude_account_the_observer_named_none_observed_is_said(self):
        expected = placed("user", "db-admin", "web-dev-01")
        limits = [{"kind": "session", "percent": 11, "resets_at": "2026-09-24T18:49:59Z"}, {"kind": "weekly_all", "percent": 83, "resets_at": "2026-09-28T15:59:59Z"},
                  {"kind": "weekly_scoped", "percent": 86, "resets_at": "2026-09-28T15:59:59Z", "model": "Opus"}]
        rs = ctl.rows(expected, [
            reply("user", "accounts", {"accounts": {"status": "ok", "accounts": [
                {"slug": "claude-a", "email": "a@example.org", "status": "ok", "limits": limits, "read_at": "2026-09-24T20:00:00Z"},
                {"slug": "claude-b", "email": None, "status": "not-signed-in", "read_at": "2026-09-24T20:00:00Z"}]}}),
            reply("db-admin", "accounts", {"accounts": {"status": "none"}})])
        t = ctl.table("accounts", rs).split("\n")
        self.assertEqual(len(t), 4, "\n".join(t))
        self.assertRegex(t[1], r"^a@example\.org\s+ok\s+11% 2026-09-24T18:49\s+83% 2026-09-28T15:59\s+86% 2026-09-28T15:59 Opus\s+2026-09-24T20:00\s+user$")
        self.assertRegex(t[2], r"^claude-b\s+not-signed-in\s", "an account with no email yet is named by its slug, its state said")
        silent = ctl.table("accounts", ctl.rows(expected, []))
        self.assertNotRegex(silent, r"no Claude account is observed", 'nobody answered is not "nothing is observed"')
        self.assertRegex(silent, r"no answer\s+\(user\)", "a login that did not answer is a row saying so")
        self.assertRegex(ctl.table("accounts", ctl.rows(expected, [reply("db-admin", "accounts", {"accounts": {"status": "none"}})])),
                         r"no Claude account is observed", "said only when a daemon answered none")
        self.assertEqual(ctl.parse_args(["user", "accounts"])["timeout"], 300, "a first read runs the harness per account")

    def test_upgrade_the_word_after_it_is_the_piece_version_is_digits_one_row_per_account_with_from_to_and_the_session(self):
        a = ctl.parse_args(["all", "upgrade", "claude"])
        self.assertEqual([a["targets"], a["op"], a["piece"], a["version"], a["timeout"]], [["all"], "upgrade", "claude", None, UPGRADE_BUDGET_S])
        self.assertGreater(UPGRADE_BUDGET_S, ACTION_TTL_MAX_S, "a queued fleet upgrade outlasts the action's acceptance window; the wait is for replies, not the TTL")
        self.assertEqual(ctl.parse_args(["db-admin", "web-dev-01", "upgrade", "claude", "--version=2.1.282"])["version"], "2.1.282")
        self.assertEqual(ctl.parse_args(["db-admin", "web-dev-01", "upgrade", "claude"])["targets"], ["db-admin", "web-dev-01"], "the piece is not a login")
        for argv, pattern in ((["all", "upgrade"], "upgrade takes a piece: claude"), (["all", "upgrade", "kernel"], "upgrade takes a piece: claude, fabric"),
                              (["all", "upgrade", "claude", "--version", "latest"], "digits"), (["all", "status", "--version", "2.1.282"], "with upgrade only")):
            with self.assertRaisesRegex(ctl.CtlError, pattern):
                ctl.parse_args(argv)
        expected = placed("db-admin", "web-dev-01", "user")

        def up(login, **u):
            return reply(login, "upgrade", {"upgrade": u})
        t = ctl.table("upgrade", ctl.rows(expected, [
            up("db-admin", status="upgraded", **{"from": "2.1.280"}, to="2.1.281", session="restarting"),
            up("web-dev-01", status="failed", **{"from": "2.1.280"}, to="2.1.281", session="none", reason="claude install 2.1.281: network")])).split("\n")
        self.assertRegex(t[1], r"^db-admin\s+upgraded\s+2\.1\.280 → 2\.1\.281\s+restarting$")
        self.assertRegex(t[2], r"^web-dev-01\s+failed\s+2\.1\.280 → 2\.1\.281\s+none\s+claude install 2\.1\.281: network$")
        self.assertRegex(t[3], r"^user\s+no answer$")
        busy = ctl.table("upgrade", ctl.rows(expected[:1], [up("db-admin", status="busy", note="an upgrade is already running on this account")])).split("\n")
        self.assertRegex(busy[1], r"^db-admin\s+busy\s.*an upgrade is already running on this account$", "a busy row shows its note")
        bare = ctl.table("upgrade", ctl.rows(expected[:1], [up("db-admin", **{"from": "2.1.280"}, to="2.1.281")])).split("\n")
        self.assertRegex(bare[1], r"^db-admin\s+no status\s+2\.1\.280 → 2\.1\.281", 'a reply with no status says so, never "undefined"')
        settings = ctl.table("upgrade", ctl.rows(expected[:2], [
            up("db-admin", status="upgraded", **{"from": "2.1.282"}, to="2.1.285", session="none", settings="refreshed"),
            up("web-dev-01", status="upgraded", **{"from": "2.1.282"}, to="2.1.285", session="none", reason="r", settings="not refreshed: defaults unreadable")])).split("\n")
        self.assertRegex(settings[1], r"\snone\s+settings refreshed$", "the settings refresh is in the row")
        self.assertRegex(settings[2], r"\snone\s+r; settings not refreshed: defaults unreadable$", "…after the reason, and a failed one says why")

    def test_upgrade_fabric_no_version_its_own_wait_a_current_row_names_main_the_commit_sent_is_origin_main_never_head(self):
        a = ctl.parse_args(["all", "upgrade", "fabric"])
        self.assertEqual([a["piece"], a["timeout"]], ["fabric", FABRIC_UPGRADE_BUDGET_S])
        with self.assertRaisesRegex(ctl.CtlError, "takes no --version"):
            ctl.parse_args(["all", "upgrade", "fabric", "--version", "2.1.282"])
        expected = placed("db-admin", "web-dev-01")

        def up(login, **u):
            return reply(login, "upgrade", {"upgrade": u})
        t = ctl.table("upgrade", ctl.rows(expected, [
            up("db-admin", status="current", piece="fabric", **{"from": "188ed8b"}, to="188ed8b", session="none"),
            up("web-dev-01", status="refused", piece="fabric", **{"from": "057b5fc"}, session="none", reason="the checkout is on x, not main; not moved")])).split("\n")
        self.assertRegex(t[1], r"^db-admin\s+current\s+188ed8b \(main\)\s+none$")
        self.assertRegex(t[2], r"^web-dev-01\s+refused\s+057b5fc → -\s+none\s+the checkout is on x, not main; not moved$")
        calls = []

        def run(cmd, **kw):
            calls.append(" ".join(cmd[3:]))
            return subprocess.CompletedProcess(cmd, 0, ("c" * 40 + "\n") if cmd[3] == "rev-parse" else "", "")
        self.assertEqual(ctl.origin_main("/fabric", run), "c" * 40)
        self.assertEqual(calls, ["fetch -q origin main", "rev-parse origin/main"])

        def offline(cmd, **kw):
            raise subprocess.CalledProcessError(1, cmd)
        self.assertIsNone(ctl.origin_main("/fabric", offline), "a failed fetch sends nothing")

    def test_keygen_the_private_half_goes_into_the_store_on_stdin_and_nowhere_else_the_public_half_into_operator_key_an_existing_key_is_kept(self):
        d = tempfile.mkdtemp(prefix="ctl-keygen-")
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        reg = os.path.join(d, "registry.json")
        with open(reg, "w") as fh:
            json.dump({"hosts": {"h": {"operator": "user"}}, "placement": {}}, fh)
        calls = []

        def run(cmd, **kw):
            calls.append({"cmd": cmd, "input": kw.get("input"), "kw": kw})
            return subprocess.CompletedProcess(cmd, 0, "", "")
        say = Said()
        self.assertEqual(ctl.keygen({"force": False}, registry=reg, run=run, who={"host": "h", "agent": "web-dev-01"}, out=say, err=say), 2, "only the host operator makes the key")
        self.assertEqual(ctl.keygen({"force": False}, registry=reg, run=run, who={"host": "h", "agent": "user"}, out=say, err=say), 0)
        self.assertEqual(len(calls), 1, "one call: the store")
        s = calls[0]
        self.assertRegex(s["cmd"][0], r"bin/fabric-secrets$")
        self.assertEqual(s["cmd"][1:], ["store", "set", "--managed", "FABRIC_CONTROL_SIGNING_KEY"], "a managed name, on purpose (secretstore/reserved.py)")
        self.assertTrue(private_key_from(s["input"]), "a usable private key went to the store on stdin")
        self.assertFalse(any("pkcs8" in a for a in s["cmd"]), "never on the command line")
        self.assertNotIn(s["input"][14:40], say.text(), "never printed")
        self.assertTrue(any("next: commit the registry change" in l for l in say.lines) and "fabric-secrets sync" not in say.text(),
                        "the next step is the registry commit alone: sync no longer carries the key (review of #96)")
        with open(reg) as fh:
            saved = json.load(fh)["hosts"]["h"]["operator_key"]
        self.assertTrue(public_key_from(saved), "the public half is in the registry")
        self.assertEqual(ctl.keygen({"force": False}, registry=reg, run=run, who={"host": "h", "agent": "user"}, out=Said(), err=Said()), 2, "a registered key is kept")
        with open(reg) as fh:
            self.assertEqual(json.load(fh)["hosts"]["h"]["operator_key"], saved)

    def test_fabric_ctl_upgrade_the_coordinators_pin_travels_in_the_signed_request_no_key_in_the_store_nothing_is_sent(self):
        r = Relay()
        self.addCleanup(r.close)
        k = generate_operator_key()
        with_key, without = Operator(self, k["privateKeySpec"]), Operator(self, None)
        reg = registry_file(self)
        # The environment's key, valid and someone else's, is set on every run:
        # a signature by it, or a run that sends with it, is the leak back.
        env_key = generate_operator_key()

        def run_key(held: Operator, args: list[str]):
            return run_ctl(self, r.url(), reg, args, {"FABRIC_CONTROL_SIGNING_KEY": env_key["privateKeySpec"], **held.env})
        none = run_key(without, ["db-admin", "upgrade", "claude", "--timeout", "1"])
        self.assertEqual(none.returncode, 3, none.stderr)
        self.assertEqual(none.stderr, "fabric-ctl: no FABRIC_CONTROL_SIGNING_KEY in this login's store — fabric-ctl keygen makes it — an action is signed or not sent\n", "one line, naming keygen")
        self.assertEqual(len(r.rows), 0, "nothing was sent: the key in the environment is not read")
        sent = run_key(with_key, ["db-admin", "upgrade", "claude", "--timeout", "1"])
        req = json.loads(r.rows[0]["content"])
        self.assertFalse(verify_request(req, public_key_from(env_key["publicKeySpec"])), "not signed with the environment's key")
        self.assertEqual(req["args"], {"piece": "claude", "version": pinned_version(ctl.FABRIC_ROOT)}, "one command, one version: the pin is named, not left to each account")
        self.assertRegex(req["args"]["version"], r"^\d+\.\d+\.\d+$")
        self.assertTrue(verify_request(req, public_key_from(k["publicKeySpec"])), "signed, over the version too")
        self.assertTrue(k["privateKeySpec"][20:50] not in sent.stderr and k["privateKeySpec"][20:50] not in sent.stdout)
        run_key(with_key, ["db-admin", "upgrade", "claude", "--version", "2.1.279", "--timeout", "1"])
        self.assertEqual(json.loads(r.rows[-1]["content"])["args"]["version"], "2.1.279", "--version overrides the pin")

    def test_signing_key_each_way_the_store_can_fail_is_its_own_line_none_carries_a_value(self):
        self.assertEqual(ctl.store_dir({"AGENT_FABRIC_SECRET_STORE": "/s"}, "/h"), "/s")
        self.assertEqual(ctl.store_dir({"AGENT_FABRIC_SECRET_STORE": ""}, "/h"), "/h/.local/share/agent-fabric/secrets", "empty is unset, as in secret_store.py")
        d = tempfile.mkdtemp(prefix="ctl-sk-")
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        self.assertRegex(ctl.signing_key(os.path.join(d, "none"))["error"], r"^no secret store at .*none \(fabric-secrets store init\)$")
        os.mkdir(os.path.join(d, "env"))
        self.assertRegex(ctl.signing_key(d)["error"], r"fabric-ctl keygen makes it$", "a store without the entry names keygen")
        gpg = os.path.join(d, "env", "FABRIC_CONTROL_SIGNING_KEY.gpg")
        with open(gpg, "w") as fh:
            fh.write("ciphertext")
        calls = []

        def run(result):
            def go(cmd, **kw):
                calls.append({"cmd": cmd, "kw": kw})
                if isinstance(result, BaseException):
                    raise result
                return result
            return go

        def done(code, out="", err=""):
            return subprocess.CompletedProcess([], code, out, err)
        self.assertEqual(ctl.signing_key(d, run(FileNotFoundError(2, "gpg")))["error"], "gpg not found; the signing key cannot be decrypted")
        self.assertRegex(ctl.signing_key(d, run(subprocess.TimeoutExpired("gpg", 30)))["error"], r"timed out after 30 s$")
        self.assertEqual(ctl.signing_key(d, run(done(2, "", "gpg: encrypted with cv25519 key\ngpg: decryption failed: No secret key\n")))["error"],
                         "gpg --decrypt of FABRIC_CONTROL_SIGNING_KEY failed: gpg: decryption failed: No secret key", "gpg's last line says why")
        self.assertRegex(ctl.signing_key(d, run(done(-9)))["error"], r"failed: killed by SIGKILL$")
        self.assertRegex(ctl.signing_key(d, run(done(0, "\n")))["error"], r"is empty — fabric-ctl keygen --force replaces it$")
        self.assertEqual(ctl.signing_key(d, run(done(0, "ed25519-pkcs8:AAAA\nsecond line\n"))), {"key": "ed25519-pkcs8:AAAA"}, "the first line, as pass reads it")
        c = calls[-1]
        self.assertEqual(c["cmd"][0], "gpg")
        self.assertEqual(c["cmd"][-2:], ["--decrypt", gpg])
        self.assertEqual((c["kw"]["stdin"], c["kw"]["capture_output"]), (subprocess.DEVNULL, True), "the value comes back on a pipe")
        self.assertGreater(c["kw"]["timeout"], 0, "a decrypt that hangs is cut off")
        if os.getuid() != 0:
            os.chmod(gpg, 0)
            try:
                self.assertRegex(ctl.signing_key(d, run(done(0, "x")))["error"], r"^cannot read .*FABRIC_CONTROL_SIGNING_KEY\.gpg \(EACCES\)$")
            finally:
                os.chmod(gpg, 0o600)

    def test_secrets_sync_takes_expect_a_fingerprint_and_restart_and_nothing_else_takes_them(self):
        a = ctl.parse_args(["flutter-dev-01", "secrets-sync", "--expect", "183a68e97389", "--restart"])
        self.assertEqual([a["op"], a["expect"], a["restart"], a["timeout"]], ["secrets-sync", "183a68e97389", True, 240])
        with self.assertRaisesRegex(ctl.CtlError, "12-hex"):
            ctl.parse_args(["all", "secrets-sync", "--expect", "sk-ant-oat01-x"])
        with self.assertRaisesRegex(ctl.CtlError, "secrets-sync only"):
            ctl.parse_args(["all", "status", "--restart"])

    def test_fabric_ctl_upgrade_exits_1_when_any_account_failed_0_when_every_answer_is_upgraded_or_current(self):
        r = Relay()
        self.addCleanup(r.close)
        k = generate_operator_key()
        op = Operator(self, k["privateKeySpec"])
        reg = registry_file(self)
        last_ttl: list = [None]

        def go(statuses: dict, extra=("--timeout", "5")):
            answered = threading.Event()

            def answer() -> None:
                if answered.is_set():
                    return
                found = None
                with r.lock:
                    for x in reversed(r.rows):
                        try:
                            j = json.loads(x["content"])
                        except ValueError:
                            continue
                        if j.get("kind") == "request" and j.get("op") == "upgrade" and not x.get("answered"):
                            found = (x, j)
                            break
                if found is None:
                    after(0.03, answer)
                    return
                found[0]["answered"] = True
                answered.set()
                last_ttl[0] = found[1]["ttl_s"]
                for login, st in statuses.items():
                    reply_record(r, f"{H}/{login}", found[1]["id"], "upgrade", {"upgrade": {**({"status": st} if st else {}), "from": "2.1.281", "to": "2.1.282", "session": "none"}})
            after(0.03, answer)
            self.addCleanup(answered.set)
            return run_ctl(self, r.url(), reg, ["db-admin", "web-dev-01", "upgrade", "claude", *extra], op.env)
        bad = go({"db-admin": "upgraded", "web-dev-01": "failed"})
        self.assertEqual(bad.returncode, 1, bad.stdout)
        self.assertRegex(bad.stdout, r"web-dev-01\s+failed")
        self.assertEqual(go({"db-admin": "upgraded", "web-dev-01": "current"}).returncode, 0)
        self.assertEqual(go({"db-admin": "upgraded", "web-dev-01": None}).returncode, 1, "a reply with no status is not a success")
        self.assertEqual(go({"db-admin": "upgraded", "web-dev-01": "current"}, ["--timeout", "3600"]).returncode, 0)
        self.assertEqual(last_ttl[0], ACTION_TTL_MAX_S, "a long wait for replies does not stretch the signed action's lifetime")

    def test_presence_one_row_per_account_running_since_when_as_what_none_a_failed_read_says_unknown(self):
        expected = placed("web-dev-01", "db-admin", "edge-hosting", "user")

        def pres(frm, presence):
            return {"kind": "reply", "from": frm, "op": "presence", "data": {"presence": presence}}
        t = ctl.table("presence", ctl.rows(expected, [
            pres("h/web-dev-01", {"status": "ok", "online": True, "sessions": 2, "since": "2026-09-25T09:57:22.000Z", "role": "web-dev", "project": "gzapp"}),
            pres("h/db-admin", {"status": "ok", "online": False, "sessions": 0, "since": None, "role": "db-admin", "project": "gzapp"}),
            pres("h/edge-hosting", {"status": "failed", "error": "pgrep: spawn pgrep ENOENT"})])).split("\n")
        planning = ctl.table("presence", ctl.rows(expected[:1], [pres("h/web-dev-01", {
            "status": "ok", "online": True, "sessions": 2, "since": "2026-09-25T09:57:22.000Z", "role": "web-dev", "project": "gzapp", "planning": True})])).split("\n")
        self.assertRegex(planning[1], r"^web-dev-01\s+planning ×2\s+2026-09-25", "a session that is planning says so")
        self.assertEqual(planning[1].index("2026-09-25"), planning[0].index("since (UTC)"), "and the columns stay aligned at its widest")
        self.assertRegex(t[1], r"^web-dev-01\s+running ×2\s+2026-09-25 09:57:22\s+web-dev\s+gzapp$")
        self.assertRegex(t[2], r"^db-admin\s+none\s+-\s+db-admin\s+gzapp$")
        self.assertRegex(t[3], r"^edge-hosting\s+unknown\s+pgrep: spawn pgrep ENOENT$")
        self.assertRegex(t[4], r"^user\s+no answer$")

    def test_a_placed_non_operator_may_ask_presence_and_nothing_else_an_unplaced_one_not_even_that(self):
        r = Relay()
        self.addCleanup(r.close)
        # this login is placed, and not the host's operator
        d = tempfile.mkdtemp(prefix="reg-")
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        reg = os.path.join(d, "registry.json")
        with open(reg, "w") as fh:
            json.dump({"hosts": {H: {"operator": "someone-else"}}, "placement": {"db-admin": H, ME["agent"]: H}}, fh)
        asked = run_ctl(self, r.url(), reg, ["db-admin", "presence", "--timeout", "1"])
        reqs = [json.loads(x["content"]) for x in r.rows if json.loads(x["content"]).get("kind") == "request"]
        self.assertEqual([[x["op"], x["to"]] for x in reqs], [["presence", [f"{H}/db-admin"]]], asked.stderr)
        n = len(r.rows)
        refused = run_ctl(self, r.url(), reg, ["db-admin", "status", "--timeout", "1"])
        self.assertEqual(refused.returncode, 2)
        self.assertRegex(refused.stderr, r"not a host operator")
        self.assertEqual(len(r.rows), n, "nothing posted for an op only an operator may ask")
        stranger = run_ctl(self, r.url(), registry_file(self, "someone-else"), ["db-admin", "presence", "--timeout", "1"])
        self.assertEqual(stranger.returncode, 2, "neither operator nor placed: no daemon would answer, nothing sent")
        self.assertEqual(len(r.rows), n)


class StopStates(BaseException):
    """What a scripted `call` raises when its script is spent: the follow loop
    would wait for ever, as the Node's never-resolving promise did."""


def iso(ms: float) -> str:
    return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def ms_of(text: str) -> float:
    from control.ops import util
    return util.date_parse_ms(text)


CFG = {"channel": "fabric:control", "state_channel": "fabric:state:control", "relay_url": "x"}


def scripted(script: list, seen: list | None = None):
    items = iter(script)

    def call(p, **_kw):
        if seen is not None:
            seen.append(p)
        try:
            step = next(items)
        except StopIteration:
            raise StopStates() from None
        return step() if callable(step) else step
    return call


class States(unittest.TestCase):
    def test_states_the_newest_state_record_per_account_the_state_that_most_wants_a_person_stale_as_unknown(self):
        now = ms_of("2026-10-07T12:00:00Z")

        def rec(frm, sessions, ts="2026-10-07T11:59:00Z", **extra):
            return {"id": f"{frm}-{ts}", "content": json.dumps({"v": 1, "kind": "state", "from": frm, "ts": ts, "sessions": sessions, **extra})}
        messages = [
            rec("h/a", [{"session": "s1", "state": "working", "since": "t0"}], "2026-10-07T11:50:00Z"),
            {"id": "r", "content": json.dumps({"v": 1, "kind": "reply", "from": "h/a", "sessions": []})},
            {"id": "junk", "content": "not json"},
            rec("h/a", [{"session": "s1", "state": "idle", "since": "t1"}, {"session": "s2", "state": "blocked", "since": "t2"}], "2026-10-07T11:59:00Z", role="web-dev", project="gzapp"),
            rec("h/b", [], iso(now - ctl.STATES_STALE_MS - 1000)),
            rec("h/other", [{"session": "x", "state": "working", "since": "t"}])]
        out: list = []
        calls: list = []

        def call(p, **_kw):
            calls.append(p)
            return {"messages": messages}
        rc = ctl.states({"json": True, "follow": False}, [{"address": "h/a"}, {"address": "h/b"}, {"address": "h/c"}], call=call, cfg=CFG,
                        out=lambda m: out.append(json.loads(m)), now=lambda: now)
        self.assertEqual(rc, 1, "an account with no record is a short table")
        self.assertEqual(len(calls), 1)
        self.assertNotIn("/api/send", calls[0], "a read, nothing sent")
        self.assertEqual([[r["address"], r["state"], r.get("since"), r.get("role")] for r in out],
                         [["h/a", "blocked", "t2", "web-dev"], ["h/b", "unknown", None, None], ["h/c", "unknown", None, None]])
        self.assertEqual(ctl.state_row("h/d", {"ts": iso(now), "sessions": []}, now)["state"], "none", "no session: none, not unknown")

    def test_states_carries_last_session_and_resumable_as_agentd_wrote_them_and_drops_a_record_whose_are_forged(self):
        now = ms_of("2026-10-07T12:00:00Z")
        want = {"h/a"}

        def rec(**extra):
            return {"content": json.dumps({"v": 1, "kind": "state", "from": "h/a", "ts": "2026-10-07T11:59:00Z", "sessions": [], **extra})}
        ok = ctl.state_record_of(rec(last_session="0f0e0d0c-1111-4222-8333-444455556666", resumable=True), want)
        row = ctl.state_row("h/a", ok, now)
        self.assertEqual([row["last_session"], row["resumable"]], ["0f0e0d0c-1111-4222-8333-444455556666", True])
        self.assertNotIn("last_session", ctl.state_row("h/a", ctl.state_record_of(rec(), want), now), "none written, none shown")
        for bad in ({"last_session": "../../etc/x"}, {"last_session": "abc\u001b]0;t\u0007def"}, {"last_session": 7}, {"last_session": "0f0e0d0c-1111", "resumable": "yes"}):
            self.assertIsNone(ctl.state_record_of(rec(**bad), want), json.dumps(bad))

    def test_states_follow_prints_each_new_record_for_an_expected_account_and_survives_a_relay_outage(self):
        now = ms_of("2026-10-07T12:00:00Z")

        def st(id_, frm, state):
            return {"id": id_, "content": json.dumps({"v": 1, "kind": "state", "from": frm, "ts": "2026-10-07T12:00:00Z", "sessions": [{"session": "s", "state": state, "since": "t"}]})}

        def down():
            raise ConnectionError("ECONNREFUSED")
        seen: list = []
        out: list = []
        err: list = []
        script = [{"messages": [st("1", "h/a", "idle")]}, down, {"messages": [st("2", "h/z", "working"), st("3", "h/a", "working")]},
                  {"warning": "since_id_not_found"}, {"messages": [{"id": "9"}]}, {"messages": [st("10", "h/a", "blocked")]}]
        with self.assertRaises(StopStates):
            ctl.states({"json": True, "follow": True}, [{"address": "h/a"}], call=scripted(script, seen), cfg=CFG,
                       out=lambda m: out.append(json.loads(m)["state"]), err=err.append, now=lambda: now, sleep=lambda _s: None)
        self.assertEqual(out, ["idle", "working", "blocked"], "the snapshot, then each change of h/a only")
        self.assertEqual(len(err), 2, f"down once, back once: {err}")
        self.assertTrue("since_id=1" in seen[1] and any("since_id=9" in p for p in seen), f"waits after the last id, re-anchors after a lost one: {seen}")

    def test_states_takes_follow_and_follow_goes_with_nothing_else(self):
        self.assertEqual(ctl.parse_args(["all", "states", "--follow", "--json"])["op"], "states")
        self.assertIs(ctl.parse_args(["all", "states", "--follow"])["follow"], True)
        with self.assertRaisesRegex(ctl.CtlError, "--follow goes with states only"):
            ctl.parse_args(["all", "status", "--follow"])

    def test_states_a_forged_record_can_mislead_a_row_never_stop_the_table_or_reach_the_terminal_raw(self):
        now = ms_of("2026-10-07T12:00:00Z")
        ts = "2026-10-07T11:59:00Z"
        forged = [{"id": f"f{i}", "content": json.dumps(r)} for i, r in enumerate([
            {"v": 1, "kind": "state", "from": "h/a", "ts": ts, "sessions": [None]},
            {"v": 1, "kind": "state", "from": "h/a", "ts": ts, "sessions": [{"session": "s", "state": {"x": 1}}]},
            {"v": 1, "kind": "state", "from": "h/a", "ts": 5, "sessions": []},
            {"v": 1, "kind": "state", "from": "h/a", "ts": ts, "sessions": [], "role": ["x"]},
            {"v": True, "kind": "state", "from": "h/a", "ts": ts, "sessions": []},
            {"v": 1, "kind": "state", "from": ["h/a"], "ts": ts, "sessions": []}])]
        good = {"id": "g", "content": json.dumps({"v": 1, "kind": "state", "from": "h/b", "ts": ts, "role": "web\x1b]52;c;ZXZpbA==\x07dev",
                                                  "sessions": [{"session": "s", "state": "idle", "since": "t"}]})}
        out: list = []
        rc = ctl.states({"json": False, "follow": False}, [{"address": "h/a"}, {"address": "h/b"}], call=lambda *_a, **_k: {"messages": [*forged, good]},
                        cfg={"channel": "c", "state_channel": "c:state", "relay_url": "x"}, out=out.append, now=lambda: now)
        self.assertEqual(rc, 1)
        self.assertEqual(len(out), 2, "every account has its row")
        self.assertRegex(out[0], r"unknown", "a malformed record is no record")
        self.assertIsNone(re.search("[\x00-\x1f\x7f]", "".join(out)), f"no control character reaches the terminal: {out!r}")
        # --follow: a forged record is skipped, never read as a relay outage.
        err: list = []
        lines: list = []
        script = [{"messages": [{"id": "z"}]}, {"messages": [*forged, {"id": "ok", "content": json.dumps({"v": 1, "kind": "state", "from": "h/a", "ts": ts, "sessions": []})}]}]
        with self.assertRaises(StopStates):
            ctl.states({"json": True, "follow": True}, [{"address": "h/a"}], call=scripted(script), cfg={"channel": "c", "state_channel": "c:state", "relay_url": "x"},
                       out=lambda m: lines.append(json.loads(m)["state"]), err=err.append, now=lambda: now, sleep=lambda _s: None)
        self.assertEqual(lines, ["unknown", "none"])
        self.assertEqual(err, [], "no outage said")

    def test_states_follow_a_row_goes_unknown_when_its_account_falls_silent_a_heartbeat_prints_nothing_the_reanchor_is_read(self):
        t = [ms_of("2026-10-07T12:00:00Z")]

        def st(id_, state, at=None):
            return {"id": id_, "content": json.dumps({"v": 1, "kind": "state", "from": "h/a", "ts": at or iso(t[0]), "sessions": [{"session": "s", "state": state, "since": "x"}]})}

        def silence():
            t[0] += ctl.STATES_STALE_MS + 1000
            return {"messages": []}
        paths: list = []
        script = [lambda: {"messages": [st("1", "working")]},          # snapshot
                  lambda: {"messages": [st("2", "working")]},          # a heartbeat: nothing new
                  silence,                                     # silence past the deadline
                  {"warning": "since_id_not_found"},           # the cursor is lost
                  lambda: {"messages": [st("5", "blocked")]},          # the re-anchor holds the news (its ts is read when it arrives)
                  {"messages": []},
                  {"messages": [None, {"content": "x"}, {"id": "6", "content": "{}"}]},   # odd replies the relay may give
                  None]
        out: list = []
        err: list = []
        with self.assertRaises(StopStates):
            ctl.states({"json": True, "follow": True}, [{"address": "h/a"}], call=scripted(script, paths), cfg=CFG,
                       out=lambda m: out.append(json.loads(m)["state"]), err=err.append, now=lambda: t[0], sleep=lambda _s: None)
        self.assertEqual(out, ["working", "unknown", "blocked"], "the snapshot, the staleness, the re-anchored record; no line for the heartbeat or the odd replies")
        self.assertEqual(err, [])
        self.assertTrue(all("channel=fabric%3Astate%3Acontrol" in p for p in paths), f"the state channel only: {paths}")
        self.assertTrue(any("since_id=6" in p for p in paths), "an odd reply with an id still moves the cursor")

    def test_states_follow_a_row_goes_unknown_while_the_relay_itself_is_unreachable(self):
        t = [ms_of("2026-10-07T12:00:00Z")]
        rec = {"id": "1", "content": json.dumps({"v": 1, "kind": "state", "from": "h/a", "ts": iso(t[0]), "sessions": [{"session": "s", "state": "working", "since": "x"}]})}

        def refused():
            t[0] += ctl.STATES_STALE_MS + 1000
            raise ConnectionError("ECONNREFUSED")
        out: list = []
        err: list = []
        with self.assertRaises(StopStates):
            ctl.states({"json": True, "follow": True}, [{"address": "h/a"}], call=scripted([{"messages": [rec]}, refused]), cfg=CFG,
                       out=lambda m: out.append(json.loads(m)["state"]), err=err.append, now=lambda: t[0], sleep=lambda _s: None)
        self.assertEqual(out, ["working", "unknown"], "stale during the outage, not after it")
        self.assertEqual(len(err), 1, "the outage is said once")


class Humans(unittest.TestCase):
    def test_a_human_login_is_placed_with_its_kind_all_asks_only_agents_and_naming_one_is_refused(self):
        d = tempfile.mkdtemp(prefix="reg-")
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        f = os.path.join(d, "registry.json")
        with open(f, "w") as fh:
            json.dump({"hosts": {H: {"operator": ME["agent"]}}, "placement": {"db-admin": H, "deck-human": H}, "kinds": {"deck-human": "human"}}, fh)
        self.assertEqual([[p["login"], p["kind"]] for p in ctl.placements(f)], [["db-admin", "agent"], ["deck-human", "human"]])
        r = run_ctl(self, "http://127.0.0.1:9", f, ["deck-human", "ping", "--timeout", "1"])
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertRegex(r.stderr, r"deck-human is a human login \(ADR-044\)")
        self.assertEqual([p["login"] for p in ctl.targets_of(["all"], ctl.placements(f))["expected"]], ["db-admin"], "all asks the agent, never the human")


class Refusals(unittest.TestCase):
    # One wording for what became of a relay call (gzcoord relay_failure): a
    # refusal, and a relay nobody listens on, on the request's send and on
    # states' snapshot.
    def test_a_relay_that_refuses_or_is_not_there_is_said_in_relay_failures_words(self):
        class Refuse(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_a):
                pass

            def do_GET(self):
                self.send_response(401)
                self.send_header("content-length", "2")
                self.end_headers()
                self.wfile.write(b"{}")
            do_POST = do_GET
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Refuse)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_address[1]}"
        reg = registry_file(self)
        try:
            sent = run_ctl(self, url, reg, ["db-admin", "ping", "--timeout", "1"])
            self.assertEqual(sent.returncode, 3, sent.stderr)
            self.assertRegex(sent.stderr, r"fabric-ctl: the relay refused \(HTTP 401\)")
            snap = run_ctl(self, url, reg, ["db-admin", "states"])
            self.assertEqual(snap.returncode, 3, snap.stderr)
            self.assertRegex(snap.stderr, r"fabric-ctl: the relay refused \(HTTP 401\)")
        finally:
            server.shutdown()
            server.server_close()
        dead = run_ctl(self, url, reg, ["db-admin", "ping", "--timeout", "1"])
        self.assertEqual(dead.returncode, 3, dead.stderr)
        self.assertRegex(dead.stderr, f"fabric-ctl: the relay is unreachable at {re.escape(url)}")


if __name__ == "__main__":
    unittest.main()
