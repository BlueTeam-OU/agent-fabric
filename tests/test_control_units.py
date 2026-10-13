#!/usr/bin/env python3
"""`fabric-ctl <login|all> control-start | control-stop` (tools/fabric/control/units.py).

The decision logic runs against a fake executor that models a systemd user
manager per login; the executor itself (hostexec_run) runs once for real
through runtime/hostexec/hostexec with a fixture registry and a fake `id` and
`sudo` first on PATH, to pin the argument list that reaches sudo."""
from __future__ import annotations

import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import ctl, units  # noqa: E402

ME = {"host": "h", "agent": "coordinator"}


class FakeSystemd:
    """One unit state per login. `start` makes it active unless the login is
    in `wont_start`; `stop` makes it inactive unless in `wont_stop`."""

    def __init__(self, states, wont_start=(), wont_stop=(), broken=(), hang=(), refuse=()):
        self.states, self.wont_start, self.wont_stop = dict(states), set(wont_start), set(wont_stop)
        self.broken, self.hang, self.refuse = set(broken), set(hang), set(refuse)
        self.calls = []

    def __call__(self, host, argv, timeout):
        self.calls.append((host, argv, timeout))
        if argv[:2] == ["id", "-u"]:
            login = argv[2]
            return (0, f"{1000 + sorted(self.states).index(login)}\n", "") if login in self.states else (1, "", f"id: ‘{login}’: no such user\n")
        assert argv[:5] == ["sudo", "-n", "-u", argv[3], "env"], argv
        login, verb = argv[3], argv[-2]
        uid = 1000 + sorted(self.states).index(login)
        assert argv[5:7] == [f"XDG_RUNTIME_DIR=/run/user/{uid}", f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus"], argv
        assert argv[7:9] == ["systemctl", "--user"] and argv[-1] == units.UNIT, argv
        if login in self.hang:
            raise subprocess.TimeoutExpired(argv, timeout)
        if login in self.broken:
            return 1, "", "Failed to connect to bus: No such file or directory\n"
        if verb == "is-active":
            s = self.states[login]
            return (0 if s == "active" else 3), s + "\n", ""
        if verb == "start" and login in self.refuse:
            return 1, "", "Failed to start: Unit is masked.\n"
        if verb == "start":
            if login not in self.wont_start:
                self.states[login] = "active"
            return 0, "", ""
        if verb == "stop":
            if login not in self.wont_stop:
                self.states[login] = "inactive"
            return 0, "", ""
        raise AssertionError(verb)


def registry(tc, placement, kinds=None):
    d = tempfile.mkdtemp()
    tc.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
    f = os.path.join(d, "registry.json")
    with open(f, "w") as fh:
        json.dump({"hosts": {"h": {"operator": "user", "ssh": None, "fabric": "~"}}, "placement": placement, **({"kinds": kinds} if kinds else {})}, fh)
    return f


class Units(unittest.TestCase):
    def ctl(self, argv, fake, placement=None, kinds=None, who=ME):
        reg = registry(self, placement or {a: "h" for a in fake.states}, kinds)
        out, err = [], io.StringIO()
        with redirect_stderr(err):
            rc = ctl.main(argv, registry=reg, out=out.append, who=who, units_run=fake)
        return rc, out, err.getvalue()

    def test_start_reports_active_started_and_failed_and_exits_1_on_a_failed_row(self):
        fake = FakeSystemd({"a": "active", "b": "inactive", "c": "failed", "d": "inactive"}, wont_start=["d"])
        rc, out, _ = self.ctl(["--json", "all", "control-start"], fake)
        rows = [json.loads(x) for x in out]
        self.assertEqual([(r["login"], r["state"]) for r in rows], [("a", "active"), ("b", "started"), ("c", "started"), ("d", "failed")])
        self.assertEqual([list(r) for r in rows][0], ["login", "state", "detail"])
        self.assertIn("inactive", rows[3]["detail"])   # the read-back word, not start's status
        self.assertEqual(rc, 1)
        self.assertNotIn("start", [c[1][-2] for c in fake.calls if c[1][-1] == units.UNIT and c[1][3] == "a"])   # active is left alone

    def test_a_start_the_manager_refuses_says_why_and_is_a_failed_row_even_if_the_unit_reads_active(self):
        fake = FakeSystemd({"a": "inactive"}, refuse=["a"])
        rc, out, _ = self.ctl(["--json", "a", "control-start"], fake)
        row = json.loads(out[0])
        self.assertEqual((rc, row["state"]), (1, "failed"))
        self.assertIn("exit 1: Failed to start: Unit is masked.", row["detail"])

    def test_start_exits_0_when_all_are_active_afterwards(self):
        fake = FakeSystemd({"a": "active", "b": "inactive"})
        rc, out, _ = self.ctl(["all", "control-start"], fake)
        self.assertEqual(rc, 0)
        self.assertEqual(set(fake.states.values()), {"active"})
        self.assertIn("started", "\n".join(out))

    def test_start_is_read_back_not_trusted_from_the_exit_status(self):
        fake = FakeSystemd({"a": "inactive"}, wont_start=["a"])   # start exits 0, the unit stays down
        rc, out, _ = self.ctl(["--json", "a", "control-start"], fake)
        self.assertEqual((rc, json.loads(out[0])["state"]), (1, "failed"))

    def test_stop_stops_and_keeps_units_enabled(self):
        fake = FakeSystemd({"a": "active", "b": "inactive", "c": "active"}, wont_stop=["c"])
        rc, out, _ = self.ctl(["--json", "all", "control-stop"], fake, who={"host": "h", "agent": "nobody"})
        self.assertEqual([(json.loads(x)["login"], json.loads(x)["state"]) for x in out], [("a", "stopped"), ("b", "stopped"), ("c", "failed")])
        self.assertEqual(rc, 1)
        self.assertNotIn("disable", {c[1][-2] for c in fake.calls})

    def test_stop_leaves_this_sessions_account_alone_without_include_self(self):
        fake = FakeSystemd({"coordinator": "active", "b": "active"})
        rc, out, _ = self.ctl(["--json", "all", "control-stop"], fake)
        rows = {json.loads(x)["login"]: json.loads(x)["state"] for x in out}
        self.assertEqual((rc, rows), (0, {"coordinator": "skipped", "b": "stopped"}))
        self.assertEqual(fake.states["coordinator"], "active")
        self.assertFalse([c for c in fake.calls if "coordinator" in c[1]])
        rc, out, _ = self.ctl(["--json", "all", "control-stop", "--include-self"], fake)
        self.assertEqual((rc, fake.states["coordinator"]), (0, "inactive"))

    def test_start_never_skips_self(self):
        fake = FakeSystemd({"coordinator": "inactive"})
        rc, out, _ = self.ctl(["--json", "coordinator", "control-start"], fake)
        self.assertEqual((rc, json.loads(out[0])["state"]), (0, "started"))

    def test_a_dead_bus_a_missing_account_and_a_hang_are_each_a_failed_row_with_their_own_words(self):
        fake = FakeSystemd({"a": "active", "b": "active", "c": "active"}, broken=["a"], hang=["b"])
        reg = registry(self, {"a": "h", "b": "h", "c": "h", "ghost": "h"})
        out = []
        rc = ctl.main(["--json", "all", "control-stop"], registry=reg, out=out.append, who={"host": "h", "agent": "x"}, units_run=fake)
        rows = {json.loads(x)["login"]: json.loads(x) for x in out}
        self.assertIn("no state", rows["a"]["detail"])
        self.assertIn("Failed to connect to bus", rows["a"]["detail"])
        self.assertIn("no answer within", rows["b"]["detail"])
        self.assertEqual(rows["c"]["state"], "stopped")   # a failure on one account stops no other
        self.assertIn("no uid for ghost", rows["ghost"]["detail"])
        self.assertEqual(rc, 1)

    def test_all_is_every_agent_and_never_a_human_and_a_human_name_is_refused(self):
        fake = FakeSystemd({"a": "inactive", "h1": "inactive"})
        reg = registry(self, {"a": "h", "h1": "h"}, {"h1": "human"})
        out, err = [], io.StringIO()
        with redirect_stderr(err):
            rc = ctl.main(["--json", "all", "control-start"], registry=reg, out=out.append, who=ME, units_run=fake)
            self.assertEqual((rc, [json.loads(x)["login"] for x in out]), (0, ["a"]))
            self.assertEqual(ctl.main(["h1", "control-start"], registry=reg, out=out.append, who=ME, units_run=fake), 2)
        self.assertIn("human login", err.getvalue())

    def test_refusals_run_nothing(self):
        fake = FakeSystemd({"a": "inactive"})
        for argv, want in ((["a", "control-start", "--include-self"], "control-stop only"), (["nobody", "control-stop"], "not a placed account")):
            fake.calls.clear()
            rc, out, err = self.ctl(argv, fake)
            self.assertEqual((rc, out, fake.calls), (2, [], []), argv)
            self.assertIn(want, err)

    def test_table_output_and_the_step_timeout(self):
        fake = FakeSystemd({"a": "inactive", "bb": "active"})
        rc, out, _ = self.ctl(["all", "control-start", "--timeout", "7"], fake)
        self.assertEqual(out, ["a   started  was inactive\nbb  active   already active"])
        self.assertEqual({c[2] for c in fake.calls}, {7})
        fake.calls.clear()
        self.ctl(["all", "control-start"], fake)
        self.assertEqual({c[2] for c in fake.calls}, {units.STEP_TIMEOUT_S})

    def test_the_login_is_checked_before_it_reaches_a_command_line(self):
        fake = FakeSystemd({})
        row = units.one(units.START, {"login": "a;rm -rf", "host": "h"}, fake, 1)
        self.assertEqual(row["state"], "failed")
        self.assertEqual(fake.calls, [])

    def test_help_lists_both_ops_for_fleet_deck(self):
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(ctl.main(["--help"]), 0)
        self.assertRegex(err.getvalue(), r"fabric-ctl <login\|all> control-start")
        self.assertRegex(err.getvalue(), r"fabric-ctl <login\|all> control-stop")


class RealExecutor(unittest.TestCase):
    """hostexec_run through the real runtime/hostexec/hostexec and the worker."""

    def test_the_argument_list_that_reaches_sudo(self):
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        bin_ = os.path.join(d, "bin")
        os.mkdir(bin_)
        log = os.path.join(d, "log")
        for name, body in (("id", 'print("4242")'), ("sudo", 'import json,os,sys\nopen(os.environ["LOG"],"a").write(json.dumps(sys.argv[1:])+"\\n")\nprint("active")')):
            p = os.path.join(bin_, name)
            with open(p, "w") as fh:
                fh.write(f"#!{sys.executable}\n{body}\n")
            os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR)
        reg = registry(self, {})
        env = {"PATH": f"{bin_}:/usr/bin:/bin", "LOG": log, "HOME": d}
        with mock.patch.dict(os.environ, env, clear=True):
            run = units.hostexec_run(reg)
            uid = units.user_uid(run, "h", "web-dev-01", 20)
            state = units.is_active(run, "h", "web-dev-01", uid, 20)
        self.assertEqual((uid, state), (4242, "active"))
        with open(log) as fh:
            argv = json.loads(fh.read().splitlines()[0])
        self.assertEqual(argv, ["-n", "-u", "web-dev-01", "env", "XDG_RUNTIME_DIR=/run/user/4242",
                                "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/4242/bus", "systemctl", "--user", "is-active", units.UNIT])

    def test_an_unknown_host_is_a_failed_row(self):
        reg = registry(self, {})
        row = units.one(units.START, {"login": "a", "host": "nowhere"}, units.hostexec_run(reg), 20)
        self.assertEqual(row["state"], "failed")
        self.assertIn("unknown host", row["detail"])


if __name__ == "__main__":
    unittest.main()
