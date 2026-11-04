#!/usr/bin/env python3
"""`fabric-ctl <login|all> harness-restart` (tools/fabric/control/harness_restart.py).

The decision logic runs against a fake executor that models a systemd user manager and the
account's passwd entry per login, and fake `states` / `presence` probes; ctl.main is driven
once through its recursive probes with a fake relay `call`, and once with no probe faked, to
pin the argv that reaches sudo for the marker."""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import ctl, harness_restart as hr, units  # noqa: E402

ME = {"host": "h", "agent": "coordinator"}


class Fleet:
    """A user manager and a passwd file per login. `stop`/`start` move the unit; a start gives a new MainPID unless
    the login is in `same_pid`. `broken` maps a login to the step ("mark", "stop", "start") that exits 1 for it."""

    def __init__(self, logins, broken=None, same_pid=()):
        self.unit = {l: "active" for l in logins}
        self.pid = {l: 100 + i for i, l in enumerate(sorted(logins))}
        self.marked, self.calls = set(), []
        self.broken, self.same_pid = dict(broken or {}), set(same_pid)
        self.logins = sorted(logins)

    def __call__(self, host, argv, timeout):
        self.calls.append(argv)
        if argv[:2] == ["id", "-u"]:
            return 0, f"{1000 + self.logins.index(argv[2])}\n", ""
        if argv[:2] == ["getent", "passwd"]:
            l = argv[2]
            return 0, f"{l}:x:{1000 + self.logins.index(l)}:100::/home/{l}:/bin/bash\n", ""
        login = argv[3]
        if argv[4] != "env":
            assert argv == ["sudo", "-n", "-u", login, "/usr/local/bin/fabric-python",
                            f"/home/{login}/projects/agent-fabric/tools/fabric/control/harness_pane.py", "mark-resume"], argv
            if self.broken.get(login) == "mark":
                return 1, "", "harness_pane: cannot write x: Permission denied\n"
            self.marked.add(login)
            return 0, "wrote x\n", ""
        assert argv[-1] == units.HARNESS_UNIT, argv
        verb = argv[9]
        if verb == "is-active":
            return (0 if self.unit[login] == "active" else 3), self.unit[login] + "\n", ""
        if verb == "show":
            assert argv[10:12] == ["--property=MainPID", "--value"], argv
            return 0, f"{self.pid[login] if self.unit[login] == 'active' else 0}\n", ""
        if self.broken.get(login) == verb:
            return 1, "", f"Failed to {verb}\n"
        if verb == "stop":
            self.unit[login] = "inactive"
        elif verb == "start":
            self.unit[login] = "active"
            if login not in self.same_pid:
                self.pid[login] += 1000
        return 0, "", ""

    def verbs(self, login):
        return [a[9] for a in self.calls if len(a) > 9 and a[3] == login and a[4] == "env" and a[9] in ("stop", "start")]


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


def iso(t):
    import datetime
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class Restart(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()

    def probes(self, states=None, presence=None):
        """states: login -> state word; presence: login -> a function of the clock giving the presence dict (default:
        online since the clock's now, once a start has happened)."""
        self.states = states or {}
        self.presence_calls = []

        def states_of(login):
            return {"state": self.states.get(login, "idle")} if not isinstance(self.states.get(login), dict) else self.states[login]

        def presence_of(login):
            self.presence_calls.append(login)
            if presence and login in presence:
                return presence[login](self.clock)
            return {"status": "ok", "online": True, "sessions": 1, "since": iso(self.clock.now())}
        return states_of, presence_of

    def run_all(self, fleet, logins, states=None, presence=None, me="coordinator", include_self=False):
        states_of, presence_of = self.probes(states, presence)
        return hr.run_all([{"login": l, "host": "h"} for l in logins], run=fleet, me=me, include_self=include_self, timeout=5,
                          states_of=states_of, presence_of=presence_of, sleep=self.clock.sleep, now=self.clock.now)

    def test_an_idle_account_is_marked_by_itself_stopped_started_and_read_back(self):
        fleet = Fleet(["a"])
        rows = self.run_all(fleet, ["a"])
        self.assertEqual([(r["login"], r["state"]) for r in rows], [("a", "restarted")])
        self.assertIn("MainPID 1100", rows[0]["detail"])
        self.assertEqual(fleet.marked, {"a"})
        self.assertEqual(fleet.verbs("a"), ["stop", "start"])
        order = [a[9] if a[4] == "env" else "mark" for a in fleet.calls if len(a) > 4 and a[0] == "sudo"]
        self.assertLess(order.index("mark"), order.index("stop"))

    def test_an_account_that_is_not_idle_is_refused_with_nothing_stopped_or_marked(self):
        for state in ("working", "blocked", "unknown", "none"):
            fleet = Fleet(["a"])
            rows = self.run_all(fleet, ["a"], states={"a": {"state": state, "why": "no record for two heartbeats"}})
            self.assertEqual(rows[0]["state"], "refused", state)
            self.assertIn(f"sessions are {state}, not idle", rows[0]["detail"])
            self.assertEqual((fleet.verbs("a"), fleet.marked, fleet.unit["a"]), ([], set(), "active"), state)

    def test_a_row_without_a_state_word_is_not_idle(self):
        fleet = Fleet(["a"])
        rows = self.run_all(fleet, ["a"], states={"a": {"address": "h/a"}})
        self.assertEqual((rows[0]["state"], fleet.verbs("a")), ("refused", []))

    def test_a_unit_that_is_not_running_is_refused_and_pointed_at_harness_start(self):
        fleet = Fleet(["a"])
        fleet.unit["a"] = "inactive"
        rows = self.run_all(fleet, ["a"])
        self.assertEqual(rows[0]["state"], "refused")
        self.assertIn("harness-start", rows[0]["detail"])
        self.assertEqual((fleet.verbs("a"), fleet.marked), ([], set()))

    def test_all_goes_one_account_at_a_time_each_read_back_before_the_next_is_stopped(self):
        fleet = Fleet(["a", "b", "c"])
        seen = []
        states_of, presence_of = self.probes()

        def presence(login):
            # while this account is read back, the ones after it have not been touched
            seen.append((login, {l: (fleet.unit[l], fleet.pid[l], fleet.verbs(l)) for l in "abc"}))
            return presence_of(login)
        rows = hr.run_all([{"login": l, "host": "h"} for l in "abc"], run=fleet, me=None, timeout=5, states_of=states_of,
                          presence_of=presence, sleep=self.clock.sleep, now=self.clock.now)
        self.assertEqual([r["state"] for r in rows], ["restarted"] * 3)
        self.assertEqual([x[0] for x in seen], ["a", "b", "c"])
        self.assertEqual(seen[0][1]["b"], ("active", 101, []))
        self.assertEqual(seen[0][1]["c"], ("active", 102, []))
        self.assertEqual(seen[1][1]["a"][2], ["stop", "start"])
        self.assertEqual(seen[1][1]["c"], ("active", 102, []))

    def test_a_failure_stops_all_and_the_rest_are_not_run_and_untouched(self):
        fleet = Fleet(["a", "b", "c"], broken={"b": "start"})
        rows = self.run_all(fleet, ["a", "b", "c"])
        self.assertEqual([r["state"] for r in rows], ["restarted", "failed", "not-run"])
        self.assertIn("b failed before it", rows[2]["detail"])
        self.assertEqual((fleet.verbs("c"), fleet.marked), ([], {"a", "b"}))
        self.assertIn("the unit is stopped, not started", rows[1]["detail"])

    def test_a_refusal_does_not_stop_all_it_left_its_account_as_it_was(self):
        fleet = Fleet(["a", "b"])
        rows = self.run_all(fleet, ["a", "b"], states={"a": "working"})
        self.assertEqual([r["state"] for r in rows], ["refused", "restarted"])
        self.assertFalse(hr.ok(rows))

    def test_a_marker_that_cannot_be_written_leaves_the_unit_running(self):
        fleet = Fleet(["a"], broken={"a": "mark"})
        rows = self.run_all(fleet, ["a"])
        self.assertEqual(rows[0]["state"], "failed")
        self.assertIn("mark-resume exit 1", rows[0]["detail"])
        self.assertEqual((fleet.verbs("a"), fleet.unit["a"]), ([], "active"))

    def test_a_stop_the_manager_refuses_is_failed_with_the_marker_said(self):
        fleet = Fleet(["a"], broken={"a": "stop"})
        rows = self.run_all(fleet, ["a"])
        self.assertEqual(rows[0]["state"], "failed")
        self.assertIn("resume marker is written, the unit was not stopped", rows[0]["detail"])

    def test_a_server_with_the_old_pid_is_not_a_new_server(self):
        fleet = Fleet(["a"], same_pid=["a"])
        rows = self.run_all(fleet, ["a"])
        self.assertEqual(rows[0]["state"], "failed")
        self.assertIn("not new", rows[0]["detail"])

    def test_a_session_that_never_comes_back_is_a_failed_row_after_the_bound_not_a_pass(self):
        fleet = Fleet(["a"])
        gone = {"a": lambda clock: {"status": "ok", "online": False, "sessions": 0, "since": None}}
        rows = self.run_all(fleet, ["a"], presence=gone)
        self.assertEqual(rows[0]["state"], "failed")
        self.assertIn(f"no new session within {hr.RESUME_WAIT_S} s (no session)", rows[0]["detail"])
        self.assertGreaterEqual(self.clock.now(), 1_000_000.0 + hr.RESUME_WAIT_S)
        self.assertLess(len(self.presence_calls), hr.RESUME_WAIT_S // hr.POLL_S + 3)

    def test_a_session_older_than_the_restart_is_not_the_resumed_one(self):
        fleet = Fleet(["a"])
        old = {"a": lambda clock: {"status": "ok", "online": True, "sessions": 1, "since": iso(1_000_000.0 - 3600)}}
        rows = self.run_all(fleet, ["a"], presence=old)
        self.assertEqual(rows[0]["state"], "failed")
        self.assertIn("before the restart", rows[0]["detail"])

    def test_a_presence_that_is_not_an_answer_is_said(self):
        fleet = Fleet(["a"])
        bad = {"a": lambda clock: {"status": "failed", "error": "pgrep: ETIMEDOUT"}}
        rows = self.run_all(fleet, ["a"], presence=bad)
        self.assertIn("presence failed: pgrep: ETIMEDOUT", rows[0]["detail"])

    def test_a_session_that_comes_back_after_some_polls_passes(self):
        fleet = Fleet(["a"])
        late = {"a": lambda clock: ({"status": "ok", "online": False, "sessions": 0, "since": None} if clock.now() < 1_000_040
                                    else {"status": "ok", "online": True, "sessions": 1, "since": iso(1_000_041)})}
        rows = self.run_all(fleet, ["a"], presence=late)
        self.assertEqual(rows[0]["state"], "restarted")
        self.assertGreater(len(self.presence_calls), 3)

    def test_a_probe_that_cannot_read_is_a_failed_row_before_anything_is_stopped(self):
        fleet = Fleet(["a"])

        def states_of(login):
            raise units.StepFailed("states could not be read: no CLAUDE_BRIDGE_AUTH_TOKEN")
        rows = hr.run_all([{"login": "a", "host": "h"}], run=fleet, me=None, timeout=5, states_of=states_of,
                          presence_of=lambda l: {}, sleep=self.clock.sleep, now=self.clock.now)
        self.assertEqual((rows[0]["state"], fleet.verbs("a"), fleet.marked), ("failed", [], set()))

    def test_this_sessions_own_account_is_skipped_unless_include_self(self):
        fleet = Fleet(["coordinator", "b"])
        rows = self.run_all(fleet, ["coordinator", "b"])
        self.assertEqual([r["state"] for r in rows], ["skipped", "restarted"])
        self.assertEqual(fleet.verbs("coordinator"), [])
        rows = self.run_all(fleet, ["coordinator"], include_self=True)
        self.assertEqual(rows[0]["state"], "restarted")

    def test_a_name_that_is_not_a_login_runs_nothing(self):
        fleet = Fleet(["a"])
        rows = self.run_all(fleet, ["-n"])
        self.assertEqual((rows[0]["state"], fleet.calls), ("failed", []))


def registry(tc, logins):
    d = tempfile.mkdtemp()
    tc.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
    f = os.path.join(d, "registry.json")
    with open(f, "w") as fh:
        json.dump({"hosts": {"h": {"operator": "user", "ssh": None, "fabric": "~"}}, "placement": {l: "h" for l in logins}}, fh)
    return f


class Verb(unittest.TestCase):
    def ctl(self, argv, fleet, logins, who=ME, call=None):
        reg = registry(self, logins)
        out, err = [], io.StringIO()
        clock = Clock()
        with redirect_stderr(err):
            rc = ctl.main(argv, registry=reg, out=out.append, who=who, units_run=fleet, sleep=clock.sleep, now=clock.now, call=call, token="t")
        return rc, out, err.getvalue()

    def test_naming_this_sessions_account_without_include_self_is_a_refusal_that_runs_nothing(self):
        fleet = Fleet(["coordinator"])
        rc, out, err = self.ctl(["coordinator", "harness-restart"], fleet, ["coordinator"])
        self.assertEqual((rc, out, fleet.calls), (2, [], []))
        self.assertIn("--include-self", err)

    def test_include_self_goes_with_the_restart_and_not_with_the_starts(self):
        self.assertEqual(ctl.parse_args(["a", "harness-restart", "--include-self"])["include_self"], True)
        with self.assertRaises(ctl.CtlError):
            ctl.parse_args(["a", "harness-start", "--include-self"])

    def test_the_probes_are_this_commands_own_states_and_presence_and_their_failure_is_a_row(self):
        fleet = Fleet(["a"])

        def call(path, **init):
            raise OSError("relay down")
        rc, out, err = self.ctl(["--json", "a", "harness-restart"], fleet, ["a"], call=call)
        row = json.loads(out[0])
        self.assertEqual((rc, row["state"], fleet.verbs("a")), (1, "failed", []))
        self.assertIn("states could not be read", row["detail"])

    def test_through_the_command_the_probes_read_a_real_states_record_and_a_real_presence_reply(self):
        fleet = Fleet(["a"])
        clock = Clock()
        cfg = ctl._agentd().control_config()
        sent = []

        def call(path, **init):
            if path.startswith("/api/send"):
                sent.append(json.loads(json.loads(init["body"])["content"]))
                return {"id": "m1"}
            if f"channel={cfg['state_channel']}" in path.replace("%3A", ":"):
                rec = {"v": 1, "kind": "state", "from": "h/a", "ts": iso(clock.now()), "sessions": [{"session": "s", "state": "idle", "since": "t"}]}
                return {"messages": [{"id": "s1", "content": json.dumps(rec)}]}
            presence = {"status": "ok", "online": True, "sessions": 1, "since": iso(clock.now())}
            reply = {"kind": "reply", "from": "h/a", "in_reply_to": sent[-1]["id"], "op": "presence", "data": {"presence": presence}}
            return {"messages": [{"id": "r1", "content": json.dumps(reply)}]}
        reg = registry(self, ["a"])
        out = []
        rc = ctl.main(["--json", "a", "harness-restart"], registry=reg, out=out.append, who={"host": "h", "agent": "user"},
                      units_run=fleet, sleep=clock.sleep, now=clock.now, call=call, token="t")
        self.assertEqual((rc, [json.loads(x)["state"] for x in out]), (0, ["restarted"]), out)
        self.assertEqual([r["op"] for r in sent], ["presence"])
        self.assertEqual(fleet.verbs("a"), ["stop", "start"])

    def test_the_default_timeout_is_the_units_and_json_rows_have_three_keys(self):
        self.assertEqual(ctl.parse_args(["a", "harness-restart"])["timeout"], units.STEP_TIMEOUT_S)


if __name__ == "__main__":
    unittest.main()
