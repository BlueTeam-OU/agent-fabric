#!/usr/bin/env python3
"""tools/fabric/gzcoord/carrier/position.py and its readers (cutover plan row W13): an account in carrier-only reports its
GZCoord position from the carrier's spool and outbox, with the relay never asked, in `fabric-status` (status.inbox_state),
in the status op's `inbox` section and in `fabric-ctl status`'s row. Every other mode keeps the relay's reader."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
import unittest.mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402

own_instance_tree()
import status  # noqa: E402
import drift  # noqa: E402
from control import ops  # noqa: E402
from gzcoord.carrier import CARRIER_LABEL, position, server  # noqa: E402
from gzcoord.transport import mode  # noqa: E402

NOW = 1_800_000_000.0


def iso(t: float) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(t, datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def carrier(unseen=(), outstanding=(), unseen_ok=True, status_ok=True):
    """A carrier's answers to the two read ops, recording every request."""
    asked: list[str] = []

    def call(path, req, timeout=15.0):
        asked.append(req["op"])
        if req["op"] == "unseen":
            return {"ok": True, "records": list(unseen)} if unseen_ok else {"ok": False, "error": "busy"}
        if req["op"] == "status":
            return {"ok": True, "outstanding": list(outstanding), "recipients": {}, "counters": {}} if status_ok \
                else {"ok": False, "error": "busy"}
        raise AssertionError(f"an op no read needs: {req}")
    return call, asked


def arrival(ago: float) -> dict:
    return {"content": "x", "ts": iso(NOW - ago), "seq": None, "message_id": "m", "verdict": "ok", "sender": "h/a"}


def delivery(ago: float, blocked=None, posted=False) -> dict:
    return {"mid": "m", "to": "b", "posted": posted, "blocked": blocked, "attempts": 1, "queued_at": iso(NOW - ago)}


RD = "/run/user/1"


def section(**k):
    call, asked = carrier(**k)
    return position.section(call, RD, NOW), asked


class Section(unittest.TestCase):
    def test_the_lag_threshold_is_the_relay_readers(self):
        self.assertEqual(position.LAG_S, drift.LAG_S)

    def test_an_idle_carrier_has_nothing_unseen_and_no_delivery(self):
        s, asked = section()
        self.assertEqual((s["status"], s["unread"], s["lag_s"], s["lagging"], s["outstanding"], s["blocked"]),
                         ("ok", 0, 0, False, 0, {}))
        self.assertEqual(sorted(asked), ["status", "unseen"])

    def test_the_oldest_unseen_and_the_oldest_outstanding_are_the_oldest_not_the_first(self):
        s, _ = section(unseen=[arrival(60), arrival(3 * 86400), arrival(5)],
                       outstanding=[delivery(30), delivery(900, posted=True), delivery(10)])
        self.assertEqual((s["unread"], s["lag_s"], s["lagging"]), (3, 3 * 86400, True))
        self.assertEqual((s["outstanding"], s["oldest_outstanding_s"], s["awaiting_receipt"]), (3, 900, 1))
        self.assertEqual(s["oldest_outstanding_at"], iso(NOW - 900))

    def test_blocked_deliveries_are_counted_by_their_code(self):
        s, _ = section(outstanding=[delivery(1, "NotInRoster"), delivery(2, "NotInRoster"), delivery(3, "Refused"), delivery(4)])
        self.assertEqual(s["blocked"], {"NotInRoster": 2, "Refused": 1})

    def test_an_unseen_arrival_under_a_day_is_not_lagging(self):
        s, _ = section(unseen=[arrival(600)])
        self.assertEqual((s["lag_s"], s["lagging"]), (600, False))

    def test_a_stamp_that_cannot_be_read_leaves_the_age_unknown_not_zero(self):
        s, _ = section(unseen=[{"content": "x", "ts": "yesterday"}, arrival(10)], outstanding=[{"queued_at": None}])
        self.assertEqual((s["unread"], s["lag_s"], s["lagging"]), (2, None, None))
        self.assertEqual((s["outstanding"], s["oldest_outstanding_s"]), (1, None))

    def test_a_carrier_that_refuses_or_is_not_there_is_unknown_and_says_why(self):
        for kw, word in (({"unseen_ok": False}, "refused unseen"), ({"status_ok": False}, "refused status")):
            s, _ = section(**kw)
            self.assertEqual(s["status"], "unknown")
            self.assertIn(word, s["reason"])

        def gone(path, req, timeout=15.0):
            raise ConnectionRefusedError("no socket")
        s = position.section(gone, RD, NOW)
        self.assertEqual(s["status"], "unknown")
        self.assertIn("did not answer", s["reason"])

    def test_no_runtime_dir_is_unknown(self):
        call, asked = carrier()
        for rd in ("", "relative/dir"):
            self.assertEqual(position.section(call, rd, NOW)["status"], "unknown")
        self.assertEqual(asked, [])

    def test_a_malformed_answer_is_unknown(self):
        def odd(path, req, timeout=15.0):
            return {"ok": True, "records": "none", "outstanding": []}
        self.assertEqual(position.section(odd, RD, NOW)["status"], "unknown")

    def test_through_the_real_socket(self):
        with tempfile.TemporaryDirectory(prefix="pos") as rd:
            call, _ = carrier(unseen=[arrival(120)], outstanding=[delivery(7, "NotInRoster")])
            srv = server.Server(server.socket_path(rd), lambda req: call(None, req))
            try:
                s = position.section(runtime_dir=rd, now=NOW)
            finally:
                srv.close()
        self.assertEqual((s["status"], s["unread"], s["blocked"]), ("ok", 1, {"NotInRoster": 1}), s)


def relay_stopped():
    """A relay reader that fails the test when asked for anything."""
    class R:
        calls = 0

        @classmethod
        def channels(cls, projects, env):
            cls.calls += 1
            raise AssertionError("the relay was asked")

        own_token = call = channels
    return R


class Readers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pos")
        self.addCleanup(self.tmp.cleanup)
        self.ctx = {"project": "agent-fabric", "host": "h", "agent": "a", "state_dir": self.tmp.name}

    def put(self, m):
        mode.write(m, "op", self.tmp.name)

    def opts(self, **k):
        call, asked = carrier(**k)
        self.asked = asked
        return {"call": call, "runtime_dir": RD, "now": NOW}

    def test_fabric_status_prints_the_position_in_carrier_only_with_the_relay_stopped(self):
        self.put(mode.CARRIER_ONLY)
        R = relay_stopped()
        s = status.inbox_state(drift, "/r", self.ctx, relay=R, home="/h",
                               carrier=self.opts(unseen=[arrival(300)], outstanding=[delivery(60, "NotInRoster")]))
        self.assertEqual(R.calls, 0)
        self.assertEqual(s["status"], "ok")
        self.assertEqual(s["detail"], "1 unseen, the oldest 5 min old; outbox: 1 outstanding, the oldest 60 s old; "
                                      f"blocked NotInRoster x1 ({CARRIER_LABEL} carrier, no relay cursor)")

    def test_a_lagging_arrival_is_lag_and_an_idle_carrier_is_ok(self):
        self.put(mode.CARRIER_ONLY)
        s = status.inbox_state(drift, "/r", self.ctx, relay=relay_stopped(), carrier=self.opts(unseen=[arrival(3 * 86400)]))
        self.assertEqual(s["status"], "lag")
        s = status.inbox_state(drift, "/r", self.ctx, relay=relay_stopped(), carrier=self.opts())
        self.assertEqual((s["status"], s["detail"].split(";")[0]), ("ok", "nothing unseen"))

    def test_an_unreachable_carrier_is_unknown_and_never_the_relay(self):
        self.put(mode.CARRIER_ONLY)
        R = relay_stopped()

        def gone(path, req, timeout=15.0):
            raise ConnectionRefusedError("no socket")
        s = status.inbox_state(drift, "/r", self.ctx, relay=R, carrier={"call": gone, "runtime_dir": RD})
        self.assertEqual(s["status"], "unknown")
        self.assertEqual(R.calls, 0)

    def test_a_damaged_mode_file_is_unknown_and_never_the_relay(self):
        with open(mode.path(self.tmp.name), "w") as f:
            f.write("{not json")
        R = relay_stopped()
        s = status.inbox_state(drift, "/r", self.ctx, relay=R)
        self.assertEqual(s["status"], "unknown")
        self.assertEqual(R.calls, 0)

    def test_the_other_modes_keep_the_relay_reader_and_never_ask_the_carrier(self):
        for m in (mode.RELAY_RECORD, mode.CARRIER_RECORD):
            self.put(m)
            asked: list = []

            def call(path, req, timeout=15.0):
                asked.append(req)
                raise AssertionError("the carrier was asked")

            class R:
                @staticmethod
                def channels(projects, env):
                    return [], []
            s = status.inbox_state(drift, "/r", self.ctx, relay=R, carrier={"call": call, "runtime_dir": RD})
            self.assertEqual(s["status"], "none", m)
            self.assertEqual(asked, [])

    def test_an_account_with_no_mode_file_is_carrier_only_and_reads_the_carrier(self):
        # W15: the default is carrier-only, so the account that never wrote a mode is read from the carrier, not the relay.
        R = relay_stopped()
        s = status.inbox_state(drift, "/r", self.ctx, relay=R, home="/h", carrier=self.opts(unseen=[arrival(300)]))
        self.assertEqual((R.calls, s["status"]), (0, "ok"))
        self.assertIn("1 unseen", s["detail"])
        self.assertIn("unseen", self.asked)

    def test_the_status_op_section_reads_the_carrier_in_carrier_only_and_ignores_the_daemons_relay(self):
        self.put(mode.CARRIER_ONLY)

        def api(*a, **k):
            raise AssertionError("the relay was asked")
        ctx = {"mode_state_dir": self.tmp.name, "inbox_opts": {"api": api, "channel": "c", "me": "h/a"},
               "inbox_carrier_opts": self.opts(outstanding=[delivery(5, "Refused")])}
        s = ops.SECTIONS["inbox"](ctx)
        self.assertEqual((s["status"], s["source"], s["blocked"]), ("ok", "interweave", {"Refused": 1}))

    def test_a_daemon_on_the_second_carrier_alone_still_answers_carrier_only_from_the_carrier(self):
        self.put(mode.CARRIER_ONLY)
        ctx = {"mode_state_dir": self.tmp.name, "inbox_relay_unread": "the relay is not read here",
               "inbox_carrier_opts": self.opts(outstanding=[])}
        self.assertEqual(ops.SECTIONS["inbox"](ctx)["source"], "interweave")
        self.put(mode.RELAY_RECORD)
        s = ops.SECTIONS["inbox"](ctx)
        self.assertEqual((s["status"], s["reason"]), ("unknown", "the relay is not read here"))

    def test_the_status_op_says_unknown_for_a_damaged_mode_and_keeps_no_reader_for_the_others(self):
        with open(mode.path(self.tmp.name), "w") as f:
            f.write("[]")
        self.assertEqual(ops.SECTIONS["inbox"]({"mode_state_dir": self.tmp.name})["status"], "unknown")
        self.put(mode.RELAY_RECORD)
        self.assertEqual(ops.SECTIONS["inbox"]({"mode_state_dir": self.tmp.name}),
                         {"status": "none", "reason": "no relay reader in this context"})


class Stranded(unittest.TestCase):
    """Gate 2's soak asks for "no stranded delivery" per account, in carrier-record too (j151, cutover plan D8): the outbox's
    age and count, metadata only, from the carrier's status op alone."""

    def read(self, outstanding=(), **k):
        call, asked = carrier(outstanding=outstanding, **k)
        return position.stranded(call, RD, NOW), asked

    def test_an_idle_outbox_has_none_older(self):
        s, asked = self.read()
        self.assertEqual((s["status"], s["outstanding"], s["older"], s["oldest_s"], s["blocked"]), ("ok", 0, 0, 0, {}))
        self.assertEqual(asked, ["status"], "the outbox alone: the spool is not read")

    def test_only_the_deliveries_older_than_the_bound_count_and_the_oldest_is_named(self):
        bound = position.STRANDED_AFTER_S
        s, _ = self.read([delivery(5), delivery(bound), delivery(bound + 1), delivery(bound * 3, blocked="E_ROSTER")])
        self.assertEqual((s["outstanding"], s["older"], s["oldest_s"], s["older_than_s"], s["blocked"]),
                         (4, 2, bound * 3, bound, {"E_ROSTER": 1}), "the bound itself is not older")

    def test_a_stamp_that_cannot_be_read_is_stranded_and_leaves_the_age_unknown(self):
        bad = {**delivery(1), "queued_at": "yesterday"}
        s, _ = self.read([delivery(5), bad])
        self.assertEqual((s["older"], s["oldest_s"]), (1, None))

    def test_no_identifier_or_text_leaves_the_account(self):
        s, _ = self.read([{**delivery(900), "mid": "SECRET-MID", "to": "h/secret-recipient"}])
        self.assertNotIn("SECRET-MID", repr(s))
        self.assertNotIn("secret-recipient", repr(s))

    def test_a_carrier_that_cannot_be_asked_is_unknown_never_zero(self):
        s, _ = self.read(status_ok=False)
        self.assertEqual(s["status"], "unknown")
        self.assertNotIn("older", s)

        def gone(path, req, timeout=15.0):
            raise ConnectionRefusedError("no socket")
        self.assertEqual(position.stranded(gone, RD, NOW)["status"], "unknown")
        self.assertEqual(position.stranded(gone, "", NOW)["status"], "unknown")

    def test_the_interweave_op_carries_it_in_any_mode(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            call, _ = carrier(outstanding=[delivery(5000)])
            for m in (mode.RELAY_RECORD, mode.CARRIER_RECORD):
                mode.write(m, "test", d)      # an explicit state directory: never the login's own transport-mode.json
                out = ops.SECTIONS[position_op_name()]({"mode_state_dir": d, "home": d, "root": d,
                                                         "inbox_carrier_opts": {"call": call, "runtime_dir": RD, "now": NOW}})
                self.assertEqual((out["outbox"]["status"], out["outbox"]["older"]), ("ok", 1), out)


def position_op_name() -> str:
    from control.carrier_install import CARRIER_NAME
    return CARRIER_NAME


class JournalRefusals(unittest.TestCase):
    """The carrier's not_journaled count, which fabric-status names when nonzero (job j166, ADR-064 rule 11): an arrival the
    journal refused is never receipted, so a unit left running over a schema move holds every arrival until restarted."""

    RD = "/run/user/1"

    def read(self, counters, last=..., ok=True, exists=True):
        def call(path, req, timeout=15.0):
            assert req == {"op": "status"}
            out = {"ok": ok, "outstanding": [], "recipients": {}, "counters": counters}
            if last is not ...:
                out["not_journaled_last"] = last
            return out
        with unittest.mock.patch("os.path.exists", return_value=exists):
            return position.journal_refusals(call, self.RD)

    LAST = {"mid": "M-6", "at": "2026-11-18T10:05:34Z", "error": "OSError: journal is held"}

    def test_a_count_with_its_last_error(self):
        d = self.read({"not_journaled": 3}, self.LAST)
        self.assertEqual(d, {"status": "ok", "not_journaled": 3, "last": self.LAST})

    def test_a_carrier_older_than_the_field_has_a_count_and_no_last_error(self):
        self.assertEqual(self.read({"not_journaled": 2}), {"status": "ok", "not_journaled": 2, "last": None})

    def test_no_socket_is_nothing_to_say_and_a_socket_that_cannot_be_read_is_unknown(self):
        self.assertEqual(self.read({"not_journaled": 1}, exists=False), {"status": "none"})
        self.assertEqual(position.journal_refusals(lambda *a, **k: 1 / 0, "relative"), {"status": "none"})

        def gone(path, req, timeout=15.0):
            raise ConnectionRefusedError("no listener")
        with unittest.mock.patch("os.path.exists", return_value=True):
            d = position.journal_refusals(gone, self.RD)
        self.assertEqual(d["status"], "unknown")
        self.assertIn("did not answer", d["reason"])

    def test_an_answer_without_a_count_is_unknown_never_zero(self):
        for counters in ({}, {"not_journaled": "3"}, {"not_journaled": True}, {"not_journaled": -1}, None):
            self.assertEqual(self.read(counters)["status"], "unknown", counters)
        self.assertEqual(self.read({"not_journaled": 0}, ok=False)["status"], "unknown")

    def test_fabric_status_line_for_a_refusal_names_count_error_and_the_fix(self):
        with unittest.mock.patch("os.path.exists", return_value=True):
            line = status.carrier_journal(call=lambda path, req, timeout=15.0: {
                "ok": True, "counters": {"not_journaled": 18}, "not_journaled_last": self.LAST}, runtime_dir=self.RD)
        self.assertEqual((line["status"], line["not_journaled"], line["last"]), ("journal-refused", 18, self.LAST))
        for word in ("18 arrival(s) not journaled since the", "M-6", "OSError: journal is held", "Restart the carrier unit"):
            self.assertIn(word, line["detail"])

    REPORT = {
        "agent": "a", "host": "h", "placement": None, "role": None, "project": None, "working_copy": None, "session": None,
        "binding_updated": None, "launched_role": None, "launch_prompt_digest": None, "drift": None, "session_effort": None,
        "undrained_memories": None, "jobs": {"active": None, "queued": 0, "paused": 0, "blocked": 0, "delivered": 0},
        "api": {"provider": "anthropic", "path": "vanilla claude", "base_url_host": None, "session_model": "m", "launch_profile": None,
                "pins": "none (harness defaults)", "credentials": "none", "claude_sign_in": "own /login"},
        "capabilities": {"code-low": "haiku"}, "routing_check": "clean", "control_plane": "/r"}

    def rendered(self, entry):
        return "\n".join(status.render({**self.REPORT, "host_tools": {"moveto": {"installed": False}, "carrier_journal": entry}}, ""))

    def test_a_count_of_zero_prints_nothing_and_a_refusal_prints_one_line(self):
        zero = {"status": "ok", "detail": "no arrival refused by the journal", "not_journaled": 0, "last": None}
        for quiet in (zero, {"status": "none", "detail": "no carrier running"}):
            self.assertNotIn("carrier", self.rendered(quiet).replace("claude sign-in", ""))
        with unittest.mock.patch("os.path.exists", return_value=True):
            refused = status.carrier_journal(call=lambda path, req, timeout=15.0: {
                "ok": True, "counters": {"not_journaled": 2}, "not_journaled_last": self.LAST}, runtime_dir=self.RD)
        text = self.rendered(refused)
        self.assertEqual(len([x for x in text.split("\n") if x.startswith("carrier ")]), 1)
        self.assertIn("carrier      JOURNAL REFUSED: 2 arrival(s) not journaled", text)
        self.assertIn("carrier      UNKNOWN: boom", self.rendered({"status": "unknown", "detail": "boom"}))

    def test_a_carrier_that_cannot_be_read_never_breaks_the_report(self):
        with unittest.mock.patch.object(position, "journal_refusals", side_effect=RuntimeError("boom")):
            self.assertEqual(status.carrier_journal(), {"status": "unknown", "detail": "boom"})


if __name__ == "__main__":
    unittest.main()
