#!/usr/bin/env python3
"""The `restart` action (tools/fabric/control/restart.py): stop the account's
running session with the restart marker written first, so its launcher resumes
it. A fake session (a pid list, a kill that records, an alive that follows it)
and the real marker file in a temporary directory; the launcher's reading of
that marker is read through launcher/session.py's own read_restart."""
from __future__ import annotations

import io
import json
import os
import signal
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import agentd, ctl, restart as R, sign, upgrade as up  # noqa: E402
import launch  # noqa: E402,F401  (loads the fabric_launcher package)
from fabric_launcher import session  # noqa: E402

REQ = {"id": "req-1", "from": "h/user", "op": "restart"}


class Session:
    """A fake session: SIGTERM stops it unless it is `stuck`."""

    def __init__(self, pids, stuck=()):
        self.pids, self.stuck, self.stopped, self.signals = list(pids), set(stuck), set(), []

    def kill(self, pid, sig):
        self.signals.append((pid, sig))
        if pid not in self.stuck:
            self.stopped.add(pid)

    def alive(self, pid):
        return pid not in self.stopped


class Restart(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name
        self.marker = up.marker_path(self.dir)
        self.clock_t = [0.0]
        # An upgrade() probe that is not told busy (a regression these tests exist to catch) must fail the
        # test, never install, write the real marker or signal the developer's own session.
        self.upgrades_run = []
        for name in ("upgrade_once", "upgrade_fabric"):
            self.addCleanup(setattr, up, name, getattr(up, name))
            setattr(up, name, lambda request, _n=name, **kw: self.upgrades_run.append(_n) or {"status": "upgraded"})
        self.addCleanup(lambda: self.assertEqual(self.upgrades_run, [], "an upgrade ran beside a restart"))

    def run_restart(self, fake, request=REQ, **kw):
        def sleep(s):
            self.clock_t[0] += s
        return R.restart(request, me=kw.pop("me", "h/py"), directory=self.dir, sessions=kw.pop("sessions", fake.pids),
                         kill=fake.kill, alive=fake.alive, sleep=sleep, clock=lambda: self.clock_t[0], **kw)

    def marker_doc(self):
        with open(self.marker, encoding="utf-8") as fh:
            return json.load(fh)

    def test_a_running_session_gets_the_done_marker_then_sigterm_and_nothing_harder(self):
        fake = Session([41, 42])
        order = []
        write = up.write_marker
        up.write_marker = lambda d, m: (order.append("marker"), write(d, m))[1]
        self.addCleanup(setattr, up, "write_marker", write)
        kill = fake.kill
        fake.kill = lambda p, s: (order.append("kill"), kill(p, s))[1]
        r = self.run_restart(fake)
        self.assertEqual(r, {"status": "restarted", "pids": [41, 42]})
        self.assertEqual(order, ["marker", "kill", "kill"], "the marker is written before the first signal")
        self.assertEqual(fake.signals, [(41, signal.SIGTERM), (42, signal.SIGTERM)])
        m = self.marker_doc()
        self.assertEqual((m["status"], m["piece"], m["request_id"]), ("done", "the session", "req-1"))
        self.assertEqual(oct(os.stat(self.marker).st_mode & 0o777), "0o600")

    def test_no_session_writes_nothing_and_signals_nothing(self):
        fake = Session([])
        self.assertEqual(self.run_restart(fake), {"status": "no-session"})
        self.assertFalse(os.path.exists(self.marker))
        self.assertEqual(fake.signals, [])

    def test_the_requesters_own_session_is_never_stopped(self):
        fake = Session([7])
        r = self.run_restart(fake, request={**REQ, "from": "h/py"})
        self.assertEqual(r["status"], "yours")
        self.assertEqual(fake.signals, [])
        self.assertFalse(os.path.exists(self.marker))

    def test_a_session_that_does_not_stop_fails_and_takes_only_its_own_marker_away(self):
        fake = Session([9], stuck=[9])
        r = self.run_restart(fake, stop_wait_ms=3000)
        self.assertEqual(r["status"], "failed")
        self.assertIn("pid 9", r["reason"])
        self.assertIn("nothing forced", r["reason"])
        self.assertEqual(fake.signals, [(9, signal.SIGTERM)], "SIGTERM once, never SIGKILL")
        self.assertFalse(os.path.exists(self.marker), "a marker left behind would resume the session when it is ended on purpose")
        # An upgrade's marker, written since, is not ours to remove.
        other = Session([9], stuck=[9])
        real_sleep_target = self.dir

        def take_over(s):
            self.clock_t[0] += s
            up.write_marker(real_sleep_target, {"request_id": "someone-else", "status": "pending", "requested_at": "2026-01-01T00:00:00.000Z"})
        R.restart(REQ, me="h/py", directory=self.dir, sessions=[9], kill=other.kill, alive=other.alive, sleep=take_over,
                  clock=lambda: self.clock_t[0], stop_wait_ms=2000)
        self.assertEqual(self.marker_doc()["request_id"], "someone-else")

    def test_it_refuses_beside_an_upgrade_or_a_secrets_sync_and_stops_nothing(self):
        fake = Session([5])
        for kw, word in (({"syncing": lambda: True}, "a secrets-sync is running"), ({}, "an upgrade is running")):
            if not kw:
                up._running = True
                self.addCleanup(setattr, up, "_running", False)
            r = self.run_restart(fake, **kw)
            self.assertEqual(r["status"], "failed")
            self.assertIn(word, r["reason"])
        self.assertEqual(up._sync_restarting, 0, "a refused restart holds nothing")
        self.assertEqual(fake.signals, [])
        self.assertFalse(os.path.exists(self.marker))

    def test_the_real_interlocks_are_the_upgrade_modules_and_secretss(self):
        from control import secrets as sec
        fake = Session([5])
        with sec._syncing:
            self.assertEqual(self.run_restart(fake)["status"], "failed")
        self.assertEqual(self.run_restart(fake)["status"], "restarted")

    def test_while_restarting_an_upgrade_is_told_busy_from_the_first_slow_step_to_the_end_and_the_hold_is_released(self):
        # An upgrade that arrives while pgrep runs (up to 30 s), while the signal is sent and while the stop is awaited.
        seen = []
        busy = lambda: seen.append(up.upgrade({"args": {"piece": "claude"}}))   # noqa: E731
        fake = Session([5])
        kill = fake.kill
        fake.kill = lambda p, s: (busy(), kill(p, s))[1]

        def pgrep(_argv):
            busy()
            raise OSError("no pgrep")   # the answer does not matter; the upgrade arrived during the wait for it
        R.restart(REQ, me="h/py", directory=self.dir, pgrep=pgrep)
        self.run_restart(fake)
        self.assertEqual([r["status"] for r in seen], ["busy", "busy"])
        self.assertTrue(all("restarting" in r["note"] for r in seen))
        self.assertEqual(up._sync_restarting, 0)

    def test_a_secrets_sync_restart_beside_it_neither_stops_the_session_nor_clears_the_hold(self):
        inside, gate = threading.Event(), threading.Event()
        fake = Session([5])
        kill = fake.kill
        fake.kill = lambda p, s: (inside.set(), gate.wait(5), kill(p, s))[2]
        t = threading.Thread(target=lambda: self.run_restart(fake))
        t.start()
        try:
            self.assertTrue(inside.wait(5))
            # What secrets-sync does at its stop point: take its hold, then ask whether a restart is running.
            self.assertTrue(R.running(), "secrets-sync refuses beside a restart")
            up.restart_in_flight(True)
            up.restart_in_flight(False)
            self.assertEqual(up.upgrade({"args": {"piece": "claude"}})["status"], "busy", "its release does not clear ours")
        finally:
            gate.set()
            t.join(5)
        self.assertFalse(R.running())

    def test_a_pgrep_that_cannot_tell_is_a_failure_not_no_session(self):
        def pgrep(_argv):
            raise OSError("pgrep: not found")
        r = R.restart(REQ, me="h/py", directory=self.dir, pgrep=pgrep)
        self.assertEqual(r["status"], "failed")
        self.assertIn("could not tell whether a session is running", r["reason"])

    def test_the_arguments_are_a_closed_empty_set(self):
        fake = Session([5])
        for args in ({"x": 1}, {"restart": True}, [], "now", 3):
            r = self.run_restart(fake, request={**REQ, "args": args})
            self.assertEqual(r["status"], "refused", args)
        for args in (None, {}):
            self.assertEqual(self.run_restart(Session([5]), request={**REQ, "args": args})["status"], "restarted", args)
        self.assertEqual(fake.signals, [])

    def test_a_second_restart_at_once_is_busy(self):
        gate, inside = threading.Event(), threading.Event()
        fake = Session([5])
        kill = fake.kill

        def slow_kill(p, s):
            inside.set()
            gate.wait(5)
            kill(p, s)
        fake.kill = slow_kill
        first = []
        t = threading.Thread(target=lambda: first.append(self.run_restart(fake)))
        t.start()
        self.assertTrue(inside.wait(5))
        other = Session([6])
        self.assertEqual(R.restart(REQ, me="h/py", directory=self.dir, sessions=[6], kill=other.kill, alive=other.alive)["status"], "busy")
        self.assertEqual(other.signals, [])
        gate.set()
        t.join(5)
        self.assertEqual(first[0]["status"], "restarted")

    def test_the_launcher_reads_the_marker_and_says_so_in_its_own_words(self):
        fake = Session([5])
        started = int(time.time()) - 5
        self.run_restart(fake)
        binding = os.path.join(self.dir, "binding.json")
        with open(binding, "w", encoding="utf-8") as fh:
            json.dump({"session": "sess-3"}, fh)
        err = io.StringIO()
        with redirect_stderr(err):
            resumed = session.read_restart(self.marker, started, binding, "5")
        self.assertEqual(resumed, "sess-3")
        self.assertIn("the session was restarted by the control plane; resuming it on the current fabric.", err.getvalue())
        self.assertNotIn("upgraded", err.getvalue())


class Wiring(unittest.TestCase):
    def test_it_is_a_signed_action_and_a_known_op_with_no_arguments_on_the_wire(self):
        self.assertIn("restart", sign.ACTION_OPS)
        self.assertIn("restart", ctl.OPS)
        args = ctl.parse_args(["py", "restart"])
        self.assertEqual(args["op"], "restart")
        req = ctl.build_request(args, id="i", from_="h/user", to=["h/py"], cfg={"ttl_s": 60}, ts="2026-10-11T00:00:00.000Z")
        self.assertNotIn("args", req)
        self.assertLessEqual(req["ttl_s"], sign.ACTION_TTL_MAX_S)
        self.assertEqual(args["timeout"], R.RESTART_BUDGET_S)

    def test_the_agent_answers_it_and_ctl_counts_restarted_no_session_and_yours_as_success(self):
        self.assertEqual(ctl.ACTION_OK["restart"], ["restarted", "no-session", "yours"])
        reply = agentd.answer({"id": "q", "op": "restart", "args": {"x": 1}, "from": "h/user"},
                              {"me": {"address": "h/py"}, "started": "2026-10-11T00:00:00.000Z"})
        self.assertEqual(reply["data"]["restart"]["status"], "refused")

    def test_the_table_names_each_account_and_what_became_of_its_session(self):
        rows = [{"account": "a", "status": "ok", "restart": {"status": "restarted", "pids": [1]}},
                {"account": "b", "status": "ok", "restart": {"status": "failed", "reason": "an upgrade is running\x1b[31m"}},
                {"account": "c", "status": "silent"}]
        lines = ctl.table("restart", rows).split("\n")
        self.assertIn("restarted", lines[1])
        self.assertIn("failed", lines[2])
        self.assertNotIn("\x1b", lines[2], "what an account wrote is escaped")
        self.assertTrue(lines[3].startswith("c") and "silent" in lines[3])


class Fleet(unittest.TestCase):
    """`fabric-ctl all restart`: one account's session is stopped and its reply read before the next account is asked."""

    def run_all(self, answers, extra=()):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        reg = os.path.join(tmp.name, "registry.json")
        with open(reg, "w", encoding="utf-8") as fh:
            json.dump({"hosts": {"h1": {"operator": "op"}}, "placement": {"a": "h1", "b": "h1", "c": "h1"}}, fh)
        events, sent = [], []

        def call(path, method="GET", body=None, **_kw):
            if path.startswith("/api/send"):
                req = json.loads(json.loads(body)["content"])
                sent.append(req)
                events.append(("send", req["to"]))
                return {"id": f"m{len(sent)}"}
            events.append(("read",))
            req = sent[-1]
            who = req["to"][0] if isinstance(req["to"], list) else "*"
            reply = {"v": 1, "kind": "reply", "id": f"r{len(sent)}", "in_reply_to": req["id"], "from": who, "op": "restart",
                     "ok": True, "data": {"restart": answers[who]}}
            return {"messages": [{"id": f"x{len(sent)}", "content": json.dumps(reply)}]}
        keep = (ctl.signing_key, ctl.sign_request)
        ctl.signing_key, ctl.sign_request = (lambda *a, **k: {"key": "k"}), (lambda r, k: r)
        self.addCleanup(lambda: setattr(ctl, "signing_key", keep[0]) or setattr(ctl, "sign_request", keep[1]))
        out, err = [], []
        rc = ctl.main(["all", "restart", "--timeout", "5", *extra], registry=reg, call=call, out=out.append, err=err.append,
                      sleep=lambda s: None, who={"host": "h1", "agent": "op", "project": None}, token="tok")
        return rc, events, sent, "\n".join(out), "\n".join(err)

    def test_each_account_is_asked_alone_and_answered_before_the_next(self):
        ok = {"status": "restarted", "pids": [1]}
        rc, events, sent, out, err = self.run_all({"h1/a": ok, "h1/b": {"status": "no-session"}, "h1/c": {"status": "yours"}})
        self.assertEqual(rc, 0, err)
        self.assertEqual([e for e in events if e[0] == "send"], [("send", ["h1/a"]), ("send", ["h1/b"]), ("send", ["h1/c"])])
        sends = [i for i, e in enumerate(events) if e[0] == "send"]
        for first, second in zip(sends, sends[1:]):
            self.assertIn(("read",), events[first:second], "the previous account's reply is read before the next send")
        self.assertTrue(all("args" not in r and r["op"] == "restart" for r in sent))

    def test_one_failed_account_fails_the_run_and_the_rest_are_still_asked(self):
        rc, events, sent, out, _ = self.run_all({"h1/a": {"status": "failed", "reason": "an upgrade is running"},
                                                 "h1/b": {"status": "restarted", "pids": [2]}, "h1/c": {"status": "no-session"}})
        self.assertEqual(rc, 1)
        self.assertEqual(len(sent), 3)
        self.assertIn("an upgrade is running", out)


if __name__ == "__main__":
    unittest.main()
