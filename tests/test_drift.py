#!/usr/bin/env python3
"""tools/fabric/drift.py and what says it (job j113): the Claude Code installed against runtime/claude-code/
harness.json, and the account's GZCoord read position against the relay's newest message, in the status op's
`harness` and `inbox` sections, in `fabric-ctl status`'s rows and table, and in `fabric-status`. Every source is
a fake: `claude --version` a script, the relay a function that records what it was asked. Plain script: unittest."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402

own_instance_tree()
import drift  # noqa: E402
import status  # noqa: E402
from control import ctl  # noqa: E402
from control import ops  # noqa: E402
from control import upgrade  # noqa: E402

NOW = 1_800_000_000.0


def iso(t: float) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(t, datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def done(out: str = "", rc: int = 0):
    return subprocess.CompletedProcess([], rc, out, "")


def fabric_with_pin(tmp: str, pin) -> str:
    root = os.path.join(tempfile.mkdtemp(dir=tmp), "fabric")
    os.makedirs(os.path.join(root, "runtime", "claude-code"))
    if pin is not ...:
        with open(os.path.join(root, "runtime", "claude-code", "harness.json"), "w", encoding="utf-8") as fh:
            json.dump({"claude": pin} if not isinstance(pin, dict) else pin, fh)
    return root


class Harness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drift-")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))

    def run_with(self, pin, version_out="2.1.286 (Claude Code)\n", **kw):
        root = fabric_with_pin(self.tmp, pin)
        seen: list = []

        def run(cmd, **k):
            seen.append(cmd)
            if isinstance(version_out, BaseException):
                raise version_out
            return done(version_out, kw.get("rc", 0)) if kw.get("rc", 0) == 0 else (_ for _ in ()).throw(subprocess.CalledProcessError(kw["rc"], cmd))
        return drift.harness("/home/x", root, run), seen

    def test_the_installed_version_equal_to_the_pin_is_not_drift(self):
        h, seen = self.run_with("2.1.286")
        self.assertEqual(h, {"status": "ok", "installed": "2.1.286", "pinned": "2.1.286", "drift": False})
        self.assertEqual(seen, [["claude", "--version"]], "no ~/.local/bin/claude here: the PATH's, as upgrade's")

    def test_a_different_installed_version_is_drift_and_names_both(self):
        h, _ = self.run_with("2.1.286", "2.1.288 (Claude Code)\n")
        self.assertEqual((h["installed"], h["pinned"], h["drift"]), ("2.1.288", "2.1.286", True))

    def test_an_unpinned_fleet_is_drift_null_never_false(self):
        for pin in (None, "latest", "", "2.1", 7, ...):
            h, _ = self.run_with(pin)
            self.assertEqual((h["status"], h["pinned"], h["drift"]), ("ok", None, None), repr(pin))

    def test_a_version_that_cannot_be_read_is_failed_and_never_taken_for_the_pin(self):
        for out in ("", "not a version\n", "２.1.286\n", "2.1.286.9\n"):
            h, _ = self.run_with("2.1.286", out)
            self.assertEqual(h["status"], "failed", repr(out))
            self.assertNotIn("drift", h)
            self.assertEqual(h["pinned"], "2.1.286")

    def test_claude_that_will_not_run_is_failed_with_its_cause(self):
        h, _ = self.run_with("2.1.286", FileNotFoundError(2, "No such file or directory"))
        self.assertEqual((h["status"], h["error"]), ("failed", "claude --version: No such file or directory"))
        h, _ = self.run_with("2.1.286", subprocess.TimeoutExpired("claude", 10))
        self.assertIn("no answer within 10 s", h["error"])
        h, _ = self.run_with("2.1.286", rc=3)
        self.assertEqual(h["error"], "claude --version: exit 3")

    def test_the_pin_reader_and_the_binary_path_are_control_upgrades(self):
        for pin in ("2.1.286", None, "latest", "2.1.286-rc1", "1.2.3", 7, ["2.1.286"]):
            root = fabric_with_pin(self.tmp, pin)
            self.assertEqual(drift.pinned_claude(root), upgrade.pinned_version(root), repr(pin))
        for broken in (..., "list"):
            root = fabric_with_pin(self.tmp, ...)
            if broken == "list":
                with open(os.path.join(root, "runtime", "claude-code", "harness.json"), "w") as fh:
                    fh.write("[1]")
            self.assertEqual(drift.pinned_claude(root), upgrade.pinned_version(root), repr(broken))
        own = os.path.join(self.tmp, "withbin")
        os.makedirs(os.path.join(own, ".local", "bin"))
        open(os.path.join(own, ".local", "bin", "claude"), "w").close()
        for home in ("/h", own):
            self.assertEqual(drift.claude_bin(home), upgrade.claude_bin(home), home)
        self.assertEqual(drift.claude_bin(own), os.path.join(own, ".local", "bin", "claude"))
        self.assertEqual(drift.claude_bin("/h"), "claude")
        self.assertEqual(drift.VERSION_RE.pattern, upgrade.VERSION_RE.pattern)


def stamps(ts) -> dict:
    """The time as /api/wait lists it (ts and ts_full, no timestamp: measured on the live relay, 2026-10-10)."""
    t = iso(ts) if isinstance(ts, float) else ts
    return {} if t is None else {"ts": t, "ts_full": t}


def message(seq: int, ts: float | str | None) -> dict:
    return {"seq": seq, "id": f"id-{seq}", "channel": "c", "sender": "x/y", "content": "z",
            **stamps(ts)}


class Inbox(unittest.TestCase):
    def relay(self, unread: list, newest_seq: int = 500):
        """A relay that answers a wait with `unread` and a listing with its newest message, recording every call."""
        calls: list[str] = []

        def api(path, **kw):
            calls.append(path)
            if kw:
                raise AssertionError(f"an option no read needs: {kw}")
            if path.startswith("/api/wait?"):
                return {"channel": "c", "messages": unread, "timed_out": not unread}
            if path.startswith("/api/messages?"):
                return {"channel": "c", "messages": [{"seq": newest_seq, "ts": iso(NOW)}]}
            raise AssertionError(f"unexpected call {path}")
        return api, calls

    def read(self, unread, **kw):
        api, calls = self.relay(unread, **kw)
        return drift.inbox(api, "gzapp:gzcoord", "h/a", NOW), calls

    def test_nothing_unread_is_no_lag(self):
        d, _ = self.read([])
        self.assertEqual(d, {"status": "ok", "channel": "gzapp:gzcoord", "unread": 0, "capped": False, "oldest_unread_seq": None,
                             "oldest_unread_at": None, "lag_s": 0, "lagging": False, "newest_seq": 500})

    def test_a_lagging_cursor_names_the_oldest_unread_and_the_relays_newest(self):
        d, _ = self.read([message(498, NOW - 3 * 86400.0), message(499, NOW - 60.0)])
        self.assertEqual((d["unread"], d["oldest_unread_seq"], d["lag_s"], d["lagging"], d["newest_seq"]), (2, 498, 3 * 86400, True, 500))
        self.assertEqual(d["oldest_unread_at"], iso(NOW - 3 * 86400.0))

    def test_the_oldest_is_the_lowest_seq_whatever_order_the_relay_lists_them_in(self):
        d, _ = self.read([message(499, NOW - 60.0), message(498, NOW - 3 * 86400.0)])
        self.assertEqual(d["oldest_unread_seq"], 498)

    def test_unread_but_recent_is_not_lag(self):
        d, _ = self.read([message(499, NOW - 3 * 3600.0)])
        self.assertEqual((d["unread"], d["lag_s"], d["lagging"]), (1, 3 * 3600, False))

    def test_a_day_exactly_is_not_lag_a_second_over_is(self):
        self.assertFalse(self.read([message(1, NOW - 86400.0)])[0]["lagging"])
        self.assertTrue(self.read([message(1, NOW - 86401.0)])[0]["lagging"])

    def test_a_full_page_says_it_was_capped(self):
        d, _ = self.read([message(i, NOW - 100.0) for i in range(1, 51)])
        self.assertEqual((d["unread"], d["capped"]), (50, True))
        d, _ = self.read([message(i, NOW - 100.0) for i in range(1, 50)])
        self.assertEqual((d["unread"], d["capped"]), (49, False))

    def test_an_age_that_cannot_be_read_is_unknown_not_zero_and_not_fine(self):
        for ts in (None, "yesterday", 7, "2026-10-09T12:00:00"):
            d, _ = self.read([message(1, ts)])
            self.assertEqual((d["status"], d["lag_s"], d["lagging"]), ("ok", None, None), repr(ts))

    def test_the_older_timestamp_field_of_the_messages_listing_is_read_too(self):
        m = {"seq": 3, "timestamp": iso(NOW - 2 * 86400.0)}
        d, _ = self.read([m])
        self.assertEqual((d["lagging"], d["oldest_unread_at"]), (True, m["timestamp"]))

    def test_each_time_field_alone_and_a_null_one_that_must_not_hide_the_next(self):
        old = iso(NOW - 2 * 86400.0)
        for fields in ({"ts": old}, {"ts_full": old}, {"timestamp": old}, {"ts_full": None, "timestamp": old}, {"ts_full": 7, "ts": old}):
            d, _ = self.read([{"seq": 3, **fields}])
            self.assertEqual((d["lagging"], d["oldest_unread_at"]), (True, old), repr(fields))

    def test_a_message_without_a_seq_or_an_answer_without_a_list_raises_not_guesses(self):
        for bad in ([{"id": "x", "timestamp": iso(NOW)}], [{"seq": True, "timestamp": iso(NOW)}], [{"seq": "7"}]):
            with self.assertRaises(ValueError):
                self.read(bad)
        with self.assertRaises(ValueError):
            drift.inbox(lambda path, **kw: {"messages": "none"}, "c", "h/a", NOW)

    def test_it_is_a_read_it_asks_as_the_account_never_acknowledges_and_waits_for_nothing(self):
        _, calls = self.read([message(1, NOW - 10.0)])
        self.assertEqual(len(calls), 2)
        wait = next(c for c in calls if c.startswith("/api/wait?"))
        self.assertIn("consumer_id=h%2Fa", wait)
        self.assertIn("timeout_seconds=0", wait)
        self.assertFalse([c for c in calls if "/api/ack" in c])

    def test_no_channel_is_none_and_asks_nothing(self):
        called: list = []
        d = drift.inbox(lambda *a, **k: called.append(a), None, "h/a", NOW)
        self.assertEqual((d["status"], called), ("none", []))

    def test_a_relay_that_cannot_be_asked_raises(self):
        def down(path, **kw):
            raise OSError("connection refused")
        with self.assertRaises(OSError):
            drift.inbox(down, "c", "h/a", NOW)


def ago(seconds: float) -> float:
    """A time `seconds` before the real clock, for code that reads it itself (the status op, fabric-status)."""
    import time
    return time.time() - seconds


class StatusOp(unittest.TestCase):
    def test_the_sections_ride_with_status_and_answer_for_a_daemon_that_hands_in_its_relay(self):
        api = Inbox().relay([message(3, ago(2 * 86400.0))])[0]
        ctx = {"home": "/home/x", "root": "/nonexistent-fabric", "run": lambda cmd, **k: done("2.1.286 (Claude Code)\n"),
               "inbox_opts": {"api": api, "channel": "gzapp:gzcoord", "me": "h/a"}}
        h, i = ops.SECTIONS["harness"](ctx), ops.SECTIONS["inbox"](ctx)
        self.assertEqual((h["installed"], h["pinned"], h["drift"]), ("2.1.286", None, None))
        self.assertEqual((i["status"], i["lagging"], i["unread"]), ("ok", True, 1))
        self.assertIn("harness", ops._wants("status"))
        self.assertIn("inbox", ops._wants("status"))
        self.assertEqual(ops._wants("jobs"), ["jobs"], "only status carries them")

    def test_a_context_with_no_relay_reader_says_so_and_reads_no_token(self):
        self.assertEqual(ops.SECTIONS["inbox"]({}), {"status": "none", "reason": "no relay reader in this context"})


def row_for(login: str, **sections) -> dict:
    data = {"identity": {"role": "web-dev"}, "fabric": {"status": "ok", "head": "abc1234", "behind": 0, "dirty": False},
            "usage": {"status": "ok"}, **sections}
    return ctl.rows([{"login": login, "host": "h", "address": f"h/{login}"}],
                    [{"kind": "reply", "from": f"h/{login}", "op": "status", "latency_ms": 5, "data": data}])[0]


class CtlStatus(unittest.TestCase):
    def line(self, **sections) -> str:
        return ctl._table_status([row_for("a", **sections)])[1]

    def test_a_control_agent_that_does_not_answer_them_gets_no_key_and_no_cell(self):
        r = row_for("a")
        self.assertNotIn("harness", r)
        self.assertNotIn("inbox", r)
        self.assertEqual(ctl._drift_cells(r), "")

    def test_the_rows_carry_what_was_answered(self):
        r = row_for("a", harness={"status": "ok", "installed": "2.1.286"}, inbox={"status": "none", "reason": "x"})
        self.assertEqual((r["harness"]["installed"], r["inbox"]["status"]), ("2.1.286", "none"))

    def test_sessions_still_on_the_old_account_are_named_and_zero_or_unknown_is_silent(self):
        self.assertTrue(self.line(session={"claude_processes": 2, "on_old_sign_in": 2}).endswith("  OLD ACCOUNT: 2 sessions (relaunch)"))
        self.assertTrue(self.line(session={"on_old_sign_in": 1}).endswith("  OLD ACCOUNT: 1 session (relaunch)"))
        for quiet in ({"on_old_sign_in": 0}, {"claude_processes": 1}, {"on_old_sign_in": True}):
            self.assertNotIn("OLD ACCOUNT", self.line(session=quiet))

    def test_drift_is_named_with_both_versions(self):
        line = self.line(harness={"status": "ok", "installed": "2.1.288", "pinned": "2.1.286", "drift": True})
        self.assertTrue(line.endswith("  claude 2.1.288 DRIFT (pin 2.1.286)"), line)

    def test_no_drift_says_the_version_and_an_unpinned_fleet_says_so(self):
        self.assertTrue(self.line(harness={"status": "ok", "installed": "2.1.286", "pinned": "2.1.286", "drift": False}).endswith("  claude 2.1.286"))
        self.assertTrue(self.line(harness={"status": "ok", "installed": "2.1.286", "pinned": None, "drift": None}).endswith("  claude 2.1.286 (no pin)"))

    def test_a_failed_harness_section_is_a_question_mark_never_fine(self):
        self.assertTrue(self.line(harness={"status": "failed", "error": "x"}).endswith("  claude ?"))

    def test_a_lagging_inbox_is_named_with_its_age_and_count_and_a_fine_one_adds_nothing(self):
        lag = {"status": "ok", "unread": 12, "capped": False, "lag_s": 3 * 86400, "lagging": True}
        self.assertTrue(self.line(inbox=lag).endswith("  inbox LAG 3 days (12 unread)"), self.line(inbox=lag))
        self.assertTrue(self.line(inbox={**lag, "capped": True}).endswith("(12+ unread)"))
        self.assertNotIn("inbox", self.line(inbox={"status": "ok", "unread": 0, "capped": False, "lag_s": 0, "lagging": False}))
        self.assertNotIn("inbox", self.line(inbox={"status": "ok", "unread": 2, "capped": False, "lag_s": 600, "lagging": False}))

    def test_an_inbox_that_could_not_be_read_or_aged_is_a_question_mark(self):
        self.assertTrue(self.line(inbox={"status": "failed", "error": "x"}).endswith("  inbox ?"))
        self.assertTrue(self.line(inbox={"status": "ok", "unread": 1, "lagging": None}).endswith("  inbox ?"))

    def test_an_account_with_no_channel_adds_nothing(self):
        self.assertNotIn("inbox", self.line(inbox={"status": "none", "reason": "x"}))

    def test_what_an_account_sent_reaches_the_terminal_escaped(self):
        line = self.line(harness={"status": "ok", "installed": "2.1.288\x1b]0;x\x07", "pinned": "2.1.286", "drift": True})
        self.assertNotIn("\x1b", line)


class FabricStatus(unittest.TestCase):
    def test_claude_lines(self):
        class D:
            def __init__(self, h):
                self.h = h

            def harness(self, root=None):
                if isinstance(self.h, Exception):
                    raise self.h
                return self.h
        ok = status.claude_state(D({"status": "ok", "installed": "2.1.286", "pinned": "2.1.286", "drift": False}), "/r")
        self.assertEqual((ok["status"], ok["detail"]), ("ok", "2.1.286, as pinned"))
        dr = status.claude_state(D({"status": "ok", "installed": "2.1.288", "pinned": "2.1.286", "drift": True}), "/r")
        self.assertEqual(dr["status"], "drift")
        self.assertIn("installed 2.1.288, the fleet pin is 2.1.286", dr["detail"])
        un = status.claude_state(D({"status": "ok", "installed": "2.1.288", "pinned": None, "drift": None}), "/r")
        self.assertEqual(un["status"], "unpinned")
        self.assertEqual(status.claude_state(D({"status": "failed", "error": "claude --version: exit 3", "pinned": None}), "/r")["status"], "unknown")
        self.assertEqual(status.claude_state(D(RuntimeError("boom")), "/r"), {"status": "unknown", "detail": "boom"})

    def inbox(self, unread, tok="tok", pairs=None, project="agent-fabric"):
        api, calls = Inbox().relay(unread)
        self.tokens_used: list = []

        class R:
            @staticmethod
            def channels(projects, env):      # as relay.channels: no project, no pair
                return (([("http://relay", "gzapp:gzcoord")] if pairs is None else pairs) if projects else []), []

            @staticmethod
            def own_token(home):
                return tok

            @staticmethod
            def call(url, token, path):
                self.tokens_used.append(token)
                return api(path)
        ctx = {"project": project, "host": "h", "agent": "a"}
        return status.inbox_state(drift, "/r", ctx, relay=R, home="/h"), calls

    def test_inbox_lines(self):
        s, _ = self.inbox([])
        self.assertEqual((s["status"], s["detail"]), ("ok", "nothing unread"))
        s, calls = self.inbox([message(498, ago(1.0))])
        self.assertEqual(self.tokens_used, ["tok", "tok"], "the account's own token, for both reads")
        self.assertEqual(s["status"], "ok")
        self.assertTrue(s["detail"].startswith("1 unread, the oldest "), s["detail"])
        self.assertFalse([c for c in calls if "ack" in c])
        s, _ = self.inbox([message(498, ago(3 * 86400.0))])
        self.assertEqual(s["status"], "lag")
        self.assertIn("3 days old (seq 498; relay newest 500)", s["detail"])

    def test_no_token_no_channel_and_an_unreadable_age_are_said(self):
        self.assertEqual(self.inbox([], tok=None)[0]["status"], "unknown")
        self.assertIn("no relay token", self.inbox([], tok=None)[0]["detail"])
        self.assertEqual(self.inbox([], pairs=[])[0]["status"], "none")
        s, calls = self.inbox([], pairs=[("http://relay", "")])
        self.assertEqual((s["status"], calls), ("none", []), "an empty channel is no channel, not a KeyError")
        self.assertEqual(self.inbox([message(1, "yesterday")])[0]["status"], "unknown")
        s, _ = self.inbox([], project=None)
        self.assertEqual(s["status"], "none", "no project: no channel to read")

    def test_the_session_environments_token_is_not_the_accounts_secrets_env(self):
        # The synced file is the account's current token (the env is a snapshot taken at the session's start, stale
        # after a rotation), and the only one read here: a token in the environment alone is "no token".
        import unittest.mock
        with unittest.mock.patch.dict(os.environ, {"CLAUDE_BRIDGE_AUTH_TOKEN": "stale-env-token"}):
            s, calls = self.inbox([], tok=None)
        self.assertEqual(s["status"], "unknown")
        self.assertEqual((calls, self.tokens_used), ([], []), "nothing was asked of the relay, with that token or any")

    def test_the_real_command_prints_both_lines_and_the_json_carries_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = os.path.join(tmp, "home")
            os.makedirs(os.path.join(home, ".local", "bin"))
            claude = os.path.join(home, ".local", "bin", "claude")
            with open(claude, "w") as fh:
                fh.write("#!/bin/sh\necho '9.9.9 (Claude Code)'\n")
            os.chmod(claude, 0o755)
            env = {k: v for k, v in os.environ.items() if not k.startswith(("AGENT_FABRIC_", "GITHUB_", "CLAUDE", "ANTHROPIC_")) and k != "GIT_DIR"}
            env.update(HOME=home, AGENT_FABRIC_STATE_DIR=os.path.join(tmp, "state"), AGENT_FABRIC_ROOT=HERE)
            r = subprocess.run([os.path.join(HERE, "bin", "fabric-status"), "--json"], env=env, cwd=tmp, capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr[-300:])
            tools = json.loads(r.stdout)["host_tools"]
            self.assertEqual((tools["claude"]["status"], tools["claude"]["installed"]), ("drift" if tools["claude"].get("pinned") else "unpinned", "9.9.9"))
            self.assertIn(tools["inbox"]["status"], ("unknown", "none"), "no token in the scratch home: nothing is read, nothing guessed")
            r2 = subprocess.run([os.path.join(HERE, "bin", "fabric-status")], env=env, cwd=tmp, capture_output=True, text=True, timeout=120)
            self.assertRegex(r2.stdout, r"(?m)^claude       (DRIFT: installed 9\.9\.9|9\.9\.9)")
            self.assertRegex(r2.stdout, r"(?m)^inbox        (UNKNOWN|no GZCoord channel)")


if __name__ == "__main__":
    unittest.main()
