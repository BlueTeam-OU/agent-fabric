#!/usr/bin/env python3
"""The `secrets-sync` action (tools/fabric/control/secrets.py) against a fake
fabric-secrets: it applies what the login's own store says, reports the
sign-in by fingerprint, proves it against the fingerprint it was sent, and —
asked to — resumes a running session on it through the launcher's restart
marker. A port of runtime/control/tests/secrets.test.mjs case for case, less
the `fabric-ctl` table case (ctl's) and the interlock with `upgrade` (the
upgrade port's: control/upgrade.py is python-dev-03's, faked here by the
five names secrets.py calls)."""
from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import secrets as S  # noqa: E402

TPL = "sk-ant-oat01-TEMPLATE-FIXTURE"
OLD = "sk-ant-oat01-OLD-ACCOUNT"


def fp(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()[:12]


def env_with(tok: str | None, provider: str | None = "anthropic"):
    def of(_pid: int) -> bytes:
        return (f"PATH=/usr/bin\0{f'AGENT_FABRIC_LAUNCH_PROVIDER={provider}' + chr(0) if provider else ''}"
                f"{f'CLAUDE_CODE_OAUTH_TOKEN={tok}' + chr(0) if tok else ''}HOME=/x\0").encode()
    return of


class FakeUpgrade:
    """The names secrets.py reaches in control/upgrade.py, with upgrade.mjs's marker file."""
    STOP_WAIT_MS = 90000

    def __init__(self) -> None:
        self.in_flight: list[bool] = []
        self.running = False

    def marker_path(self, d: str) -> str:
        return os.path.join(d, "restart.json")

    def write_marker(self, d: str, m: dict) -> None:
        os.makedirs(d, exist_ok=True)
        with open(self.marker_path(d), "w", encoding="utf-8") as fh:
            json.dump(m, fh)

    def upgrade_running(self) -> bool:
        return self.running

    def restart_in_flight(self, on: bool) -> None:
        self.in_flight.append(on)

    def session_pids(self, **_kw):
        raise AssertionError("sessions were handed in")


class Fixture:
    def __init__(self, tc: unittest.TestCase, writes: str | None = TPL, code: int = 0, report: dict | None = None,
                 before: str | None = None) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="secrets-")
        tc.addCleanup(tmp.cleanup)
        self.home, self.root, self.dir = (os.path.join(tmp.name, n) for n in ("home", "root", "state"))
        self.cfg = os.path.join(self.home, ".config", "agent-fabric", "secrets.env")
        os.makedirs(os.path.dirname(self.cfg))
        if before:
            self._env(before)
        self.calls: list[list[str]] = []
        self.writes, self.code, self.report = writes, code, report or {}
        self.up = FakeUpgrade()
        self.opts = dict(home=self.home, root=self.root, run=self.run, directory=self.dir)

    def _env(self, tok: str | None) -> None:
        with open(self.cfg, "w", encoding="utf-8") as fh:
            fh.write(f"export CLAUDE_CODE_OAUTH_TOKEN='{tok}'\n" if tok else "export GH_TOKEN=x\n")

    def run(self, cmd, **kw):
        # A timeout and a closed stdin are part of the contract of a call to a program.
        assert isinstance(cmd, list) and kw.get("timeout") and kw.get("check") is False, kw
        self.calls.append([os.path.relpath(cmd[0], self.root), *cmd[1:]])
        self._env(self.writes)
        return subprocess.CompletedProcess(cmd, self.code, json.dumps(self.report).encode(), b"")

    def sync(self, request: dict, **more):
        saved = S.upgrade
        S.upgrade = lambda: self.up
        try:
            return S.secrets_sync(request, **{**self.opts, **more})
        finally:
            S.upgrade = saved


def no_kill(*_a):
    raise AssertionError("a session was signalled")


class SecretsSync(unittest.TestCase):
    def test_template_synced_named_by_fingerprint_value_nowhere(self):
        f = Fixture(self)
        r = f.sync({"id": "x"}, sessions=[])
        self.assertEqual(f.calls, [["bin/fabric-secrets", "sync", "--json"]])
        self.assertEqual(r, {"status": "synced", "claude_sign_in": {"via": "setup-token", "token_sha256_12": fp(TPL)}, "session": "none"})
        self.assertNotIn(TPL, json.dumps(r))

    def test_no_template_missing_names_said_running_session_told_to_relaunch(self):
        f = Fixture(self, writes=None, code=2, report={"missing": ["SSH_PRIVATE_KEY"]})
        r = f.sync({"id": "x"}, sessions=[4242], env_of=env_with(None))
        self.assertEqual(r, {"status": "synced", "claude_sign_in": {"via": "none: its next session is refused"},
                             "missing": ["SSH_PRIVATE_KEY"], "session": "running: relaunch to use it"})

    def test_sync_that_applied_nothing_fails_with_reason_and_bad_arguments_refused_first(self):
        f = Fixture(self, code=3, report={"error": "config agents_x names AGENT_LOGIN=y, this login is x; nothing applied"})
        r = f.sync({"id": "x"}, sessions=[])
        self.assertEqual((r["status"], r["reason"]), ("failed", "config agents_x names AGENT_LOGIN=y, this login is x; nothing applied"))
        g = Fixture(self)
        self.assertEqual(g.sync({"id": "x", "args": {"config": "agents_other"}}, sessions=[])["status"], "refused")
        self.assertEqual(g.calls, [])

    def test_exit_that_is_not_a_number_or_a_command_that_did_not_run_is_a_failure_with_its_cause(self):
        f = Fixture(self)

        def missing(cmd, **kw):
            raise FileNotFoundError(2, "No such file", cmd[0])

        def slow(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, kw["timeout"])
        self.assertEqual(f.sync({"id": "x"}, run=missing, sessions=[]),
                         {"status": "failed", "reason": f"fabric-secrets: spawn {os.path.join(f.root, 'bin', 'fabric-secrets')} ENOENT"})
        self.assertTrue(f.sync({"id": "x"}, run=slow, sessions=[])["reason"].startswith("fabric-secrets: Command failed"))
        killed = lambda cmd, **kw: subprocess.CompletedProcess(cmd, -signal.SIGKILL, b"", b"")  # noqa: E731
        self.assertEqual(f.sync({"id": "x"}, run=killed, sessions=[])["reason"], "fabric-secrets sync exited -1")

    def test_output_that_is_not_json_still_reads_by_its_exit_code(self):
        f = Fixture(self)
        r = f.sync({"id": "x"}, run=lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, b"not json", b""), sessions=[])
        self.assertEqual((r["status"], r["reason"]), ("failed", "fabric-secrets sync exited 1"))

    def test_expect_must_be_the_templates_and_nothing_is_stopped_on_a_mismatch(self):
        f = Fixture(self)
        self.assertEqual(f.sync({"id": "x", "args": {"expect": fp(TPL)}}, sessions=[])["status"], "synced")
        other = "sk-ant-oat01-SOMEONE-ELSE"
        g = Fixture(self, writes=other)
        r = g.sync({"id": "x", "args": {"expect": fp(TPL), "restart": True}}, sessions=[7], kill=no_kill)
        self.assertEqual(r["status"], "failed")
        self.assertIn(f"holds setup-token {fp(other)}, not the expected {fp(TPL)}; nothing restarted", r["reason"])
        self.assertFalse(os.path.exists(g.up.marker_path(g.dir)))
        for args in ({"expect": "XYZ"}, {"restart": "yes"}, {"config": "agents_other"}, [], {"expect": None}, None, {"expect": 123456789012}):
            h = Fixture(self)
            self.assertEqual(h.sync({"id": "x", "args": args}, sessions=[])["status"], "refused", args)
            self.assertEqual(h.calls, [])

    def test_args_absent_is_nothing_args_null_is_refused(self):
        f = Fixture(self)
        self.assertEqual(f.sync({"id": "x"}, sessions=[])["status"], "synced")
        self.assertEqual(f.sync({"id": "x", "args": None}, sessions=[]), {"status": "refused", "reason": "secrets-sync takes { expect, restart }"})
        self.assertEqual(len(f.calls), 1, "the refused request ran nothing")

    def test_a_template_with_no_token_fails_an_expect(self):
        f = Fixture(self, writes=None)
        r = f.sync({"id": "x", "args": {"expect": fp(TPL)}}, sessions=[])
        self.assertEqual(r["status"], "failed")
        self.assertIn("holds no token, not the expected", r["reason"])

    def test_restart_marker_first_already_done_then_sigterm(self):
        f = Fixture(self, before=OLD)
        up, order = [True], []

        def kill(pid, sig):
            with open(f.up.marker_path(f.dir), encoding="utf-8") as fh:
                order.append(f"{signal.Signals(sig).name} {pid} marker={json.load(fh)['status']}")
            up[0] = False
        r = f.sync({"id": "req-9", "from": "h/user", "args": {"expect": fp(TPL), "restart": True}}, sessions=[55],
                   me="h/web-dev-01", env_of=env_with(OLD), kill=kill, alive=lambda p: up[0], sleep=lambda s: None)
        self.assertEqual((r["status"], r["session"]), ("synced", "restarting"))
        self.assertEqual(order, ["SIGTERM 55 marker=done"])
        with open(f.up.marker_path(f.dir), encoding="utf-8") as fh:
            m = json.load(fh)
        self.assertEqual([m["piece"], m["from"], m["installed"], m["request_id"]],
                         ["the Claude account", f"setup-token {fp(OLD)}", f"setup-token {fp(TPL)}", "req-9"])
        self.assertNotIn("sk-ant-oat01", json.dumps(m))
        self.assertEqual(f.up.in_flight, [True, False], "the restart interlock is taken and released")
        self.assertRegex(m["requested_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")

    def test_restart_spares_own_session_one_already_on_the_token_and_forces_none(self):
        own = Fixture(self, before=OLD)
        r1 = own.sync({"id": "x", "from": "h/user", "args": {"restart": True}}, sessions=[1], me="h/user", env_of=env_with(OLD), kill=no_kill)
        self.assertEqual(r1["session"], "yours: relaunch to use it")
        same = Fixture(self, before=TPL)
        r2 = same.sync({"id": "x", "from": "h/user", "args": {"restart": True}}, sessions=[2], me="h/db-admin", env_of=env_with(TPL), kill=no_kill)
        self.assertEqual(r2["session"], "running, already on it")
        stuck = Fixture(self, before=OLD)
        sigs: list[int] = []
        r3 = stuck.sync({"id": "x", "from": "h/user", "args": {"restart": True}}, sessions=[3], me="h/db-admin", env_of=env_with(OLD),
                        kill=lambda p, s: sigs.append(s), alive=lambda p: True, sleep=lambda s: None, stop_wait_ms=0)
        self.assertEqual(r3["status"], "failed")
        self.assertRegex(r3["reason"], r"synced, but the session \(pid 3\) did not stop within 0 s; nothing forced — run it again")
        self.assertEqual(sigs, [signal.SIGTERM])
        self.assertFalse(os.path.exists(stuck.up.marker_path(stuck.dir)), "no marker left to resume the session whenever it is ended later")
        self.assertEqual(stuck.up.in_flight, [True, False], "released on the failure path too")

    def test_the_session_not_the_record_says_whether_it_is_on_the_token(self):
        f = Fixture(self, before=TPL)
        up, sigs = [True], []
        r = f.sync({"id": "r2", "from": "h/user", "args": {"expect": fp(TPL), "restart": True}}, sessions=[66], me="h/db-admin",
                   env_of=env_with(OLD), kill=lambda p, sg: (sigs.append(sg), up.__setitem__(0, False)), alive=lambda p: up[0], sleep=lambda s: None)
        self.assertEqual((r["status"], r["session"], sigs), ("synced", "restarting", [signal.SIGTERM]))

        def unreadable(_pid):
            raise PermissionError(13, "EACCES")
        g = Fixture(self)
        r2 = g.sync({"id": "r3", "from": "h/user", "args": {"restart": True}}, sessions=[67], me="h/db-admin", env_of=unreadable,
                    kill=lambda p, s: None, alive=lambda p: False, sleep=lambda s: None)
        self.assertEqual(r2["session"], "restarting", 'an environment that cannot be read is not "already on it"')
        self.assertEqual(S.session_env(1, env_with(TPL)), {"token": TPL, "provider": "anthropic"})
        self.assertEqual(S.session_env(1, env_with(None, "openrouter")), {"token": None, "provider": "openrouter"})
        self.assertEqual(S.session_env(1, env_with(TPL, None)), {"token": TPL, "provider": None}, "no stamp: plain claude")
        self.assertEqual(S.session_env(1, lambda p: "CLAUDE_CODE_OAUTH_TOKEN=\0"), {"token": None, "provider": None}, "empty is absent")

    def test_restart_refuses_without_token_with_a_failed_pgrep_during_an_upgrade_and_never_removes_anothers_marker(self):
        none = Fixture(self, writes=None)
        r1 = none.sync({"id": "x", "from": "h/user", "args": {"restart": True}}, sessions=[5], me="h/db-admin", env_of=env_with(OLD), kill=no_kill)
        self.assertEqual((r1["status"], r1["reason"]), ("failed", "the synced record holds no token; nothing stopped"))
        self.assertFalse(os.path.exists(none.up.marker_path(none.dir)))

        def eacces(**_kw):
            raise PermissionError(13, "spawn pgrep EACCES")
        pg = Fixture(self)
        pg.up.session_pids = eacces
        r2 = pg.sync({"id": "x", "from": "h/user", "args": {"restart": True}}, me="h/db-admin", kill=no_kill)
        self.assertEqual(r2["status"], "failed")
        self.assertRegex(r2["reason"], r"could not tell whether a session is running \(pgrep: .*EACCES.*\); nothing restarted")
        quiet = Fixture(self)
        quiet.up.session_pids = eacces
        r2b = quiet.sync({"id": "x", "from": "h/user"}, me="h/db-admin")
        self.assertEqual((r2b["status"], r2b["session"]), ("synced", "unknown"), "without a restart asked, the sync stands and the unknown is said")
        self.assertIn("EACCES", r2b["reason"])
        up = Fixture(self)
        up.up.running = True
        r3 = up.sync({"id": "x", "from": "h/user", "args": {"restart": True}}, sessions=[8], me="h/db-admin", env_of=env_with(OLD), kill=no_kill)
        self.assertEqual(r3["status"], "failed")
        self.assertIn("an upgrade is running", r3["reason"])
        self.assertEqual(up.up.in_flight, [], "the interlock is not taken under an upgrade")
        other = Fixture(self)
        os.makedirs(other.dir)

        def kill(_p, _s):
            with open(other.up.marker_path(other.dir), "w", encoding="utf-8") as fh:
                json.dump({"request_id": "an-upgrade", "status": "pending"}, fh)
        r4 = other.sync({"id": "mine", "from": "h/user", "args": {"restart": True}}, sessions=[9], me="h/db-admin", env_of=env_with(OLD),
                        kill=kill, alive=lambda p: True, sleep=lambda s: None, stop_wait_ms=0)
        self.assertEqual(r4["status"], "failed")
        with open(other.up.marker_path(other.dir), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["request_id"], "an-upgrade", "the upgrade's marker survives")

    def test_a_broker_session_has_no_claude_account_to_move(self):
        f = Fixture(self)
        for run in range(2):
            r = f.sync({"id": f"b{run}", "from": "h/user", "args": {"expect": fp(TPL), "restart": True}}, sessions=[70], me="h/db-admin",
                       env_of=env_with(None, "openrouter"), kill=no_kill)
            self.assertEqual((r["status"], r["session"]), ("synced", "running (broker): no Claude account to move"))
        self.assertFalse(os.path.exists(f.up.marker_path(f.dir)))
        g = Fixture(self)
        up, sigs = [True], []
        r = g.sync({"id": "mix", "from": "h/user", "args": {"restart": True}}, sessions=[71, 72], me="h/db-admin",
                   env_of=lambda pid: (env_with(None, "openrouter") if pid == 71 else env_with(OLD))(pid),
                   kill=lambda pid, s: (sigs.append(pid), up.__setitem__(0, False)), alive=lambda p: up[0], sleep=lambda s: None)
        self.assertEqual((r["session"], sigs), ("restarting", [72]))
        with open(g.up.marker_path(g.dir), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["pids"], [72])

    def test_one_sync_at_a_time(self):
        f = Fixture(self)
        gate, entered = threading.Event(), threading.Event()
        calls = f.run

        def slow(cmd, **kw):
            entered.set()
            gate.wait(10)
            return calls(cmd, **kw)
        out: list[dict] = []
        t = threading.Thread(target=lambda: out.append(f.sync({"id": "a"}, run=slow, sessions=[])))
        t.start()
        self.assertTrue(entered.wait(10))
        self.assertEqual(f.sync({"id": "b"}, sessions=[]), {"status": "busy", "note": "a secrets-sync is already running on this account"})
        gate.set()
        t.join(10)
        self.assertEqual(out[0]["status"], "synced")
        self.assertEqual(f.sync({"id": "c"}, sessions=[])["status"], "synced", "released afterwards")


if __name__ == "__main__":
    unittest.main()
