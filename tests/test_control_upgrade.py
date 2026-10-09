#!/usr/bin/env python3
"""The `upgrade` action (tools/fabric/control/upgrade.py), a port of
runtime/control/tests/upgrade.test.mjs and upgrade-fabric.test.mjs case for
case: against a fake harness, at the pin nothing moves; a running session is
stopped gracefully (SIGTERM, never SIGKILL) with the launcher's restart
marker written first; the install is verified; the requester's own session
is never stopped; every failure is said; the host's install lease is held
from before the stop until the read-back. Then `upgrade fabric` against
real git (a bare origin and the account's checkout), and the cases the port
added: the names control/secrets.py and control/accounts.py reach, resolved
without fakes."""
from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
from control import upgrade as U  # noqa: E402


def done(out: str = "", err: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], 0, out.encode(), err.encode())


def failed(cmd, code: int = 1, err: str = "", out: str = "") -> subprocess.CalledProcessError:
    return subprocess.CalledProcessError(code, cmd, out.encode(), err.encode())


class Fx:
    """A fake harness, a pin file, and a lease that records when it is held."""

    def __init__(self, tc: unittest.TestCase, installed="2.1.280", pin: str | None = "2.1.281", install_fails=False,
                 installs_wrong=False, settings_fail=False, settings_warn=False) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="upgrade-")
        tc.addCleanup(tmp.cleanup)
        self.home, self.root = os.path.join(tmp.name, "home"), os.path.join(tmp.name, "root")
        os.makedirs(os.path.join(self.root, "runtime", "claude-code"))
        os.makedirs(self.home)
        if pin:
            with open(os.path.join(self.root, "runtime", "claude-code", "harness.json"), "w") as fh:
                json.dump({"claude": pin}, fh)
        self.dir = os.path.join(self.home, "state")
        self.calls: list[str] = []
        self.current = installed
        self.install_fails, self.installs_wrong, self.settings_fail, self.settings_warn = install_fails, installs_wrong, settings_fail, settings_warn

    def run(self, cmd, **kw):
        assert isinstance(cmd, list) and kw.get("timeout") and kw.get("check") is True, (cmd, kw)
        if cmd[0] == sys.executable:
            self.calls.append(f"user-settings {os.path.relpath(cmd[2], self.home)}")
            if self.settings_fail:
                raise failed(cmd, err="  !  unreadable\n")
            return done("  +  settings\n", "  !  s.json: Claude Code's auto-mode defaults could not be read — autoMode left as it is\n" if self.settings_warn else "")
        self.calls.append(" ".join(cmd[1:]))
        if cmd[1] == "--version":
            return done(f"{self.current} (Claude Code)\n")
        if cmd[1] == "install":
            if self.install_fails:
                raise failed(cmd, err="Downloading…\nInstall failed: network\n")
            self.current = "2.1.279" if self.installs_wrong else cmd[2]
            return done()
        raise AssertionError(f"unexpected {cmd}")

    def lease(self):
        self.calls.append("lease held")
        fx = self

        class Held:
            def release(self_) -> None:  # noqa: N805
                fx.calls.append("lease released")
        return Held()

    def opts(self, **more):
        return {"home": self.home, "root": self.root, "directory": self.dir, "run": self.run, "lease": self.lease, **more}


def req(**over):
    return {"id": "req-1", "from": "h/user", "op": "upgrade", "args": {"piece": "claude"}, **over}


def no_kill(*_a):
    raise AssertionError("a session was signalled")


def marker(f: Fx) -> dict:
    with open(U.marker_path(f.dir)) as fh:
        return json.load(fh)


class UpgradeClaude(unittest.TestCase):
    def test_the_state_directory_is_the_overrides_then_xdg_then_the_home(self):
        self.assertEqual(U.state_dir("/h", {}, "u"), "/h/.local/state/agent-fabric/agents/u")
        self.assertEqual(U.state_dir("/h", {"XDG_STATE_HOME": "/x/"}, "u"), "/x/agent-fabric/agents/u")
        self.assertEqual(U.state_dir("/h", {"XDG_STATE_HOME": ""}, "u"), "/h/.local/state/agent-fabric/agents/u")
        self.assertEqual(U.state_dir("/h", {"AGENT_FABRIC_STATE_DIR": "/s/a/../b", "XDG_STATE_HOME": "/x"}, "u"), "/s/b/agents/u")
        self.assertEqual(U.state_dir("/h", {"AGENT_FABRIC_STATE_DIR": "", "XDG_STATE_HOME": "/x"}, "u"), "/x/agent-fabric/agents/u")

    def test_sessions_are_read_again_under_the_lease_because_the_wait_can_outlast_one(self):
        f = Fx(self)
        sessions: list[int] = []
        up = [True]
        stopped: list[int] = []

        def lease():
            sessions.append(4242)   # a session started while this account queued for its turn
            return f.lease()
        r = U.upgrade_once(req(), **f.opts(sessions=sessions, lease=lease, kill=lambda p, _s: (stopped.append(p), up.__setitem__(0, False)),
                                           alive=lambda _p: up[0], sleep=lambda _s: None, me="h/db-admin"))
        self.assertEqual((r["status"], r["session"], stopped), ("upgraded", "restarting", [4242]))
        self.assertEqual(marker(f)["pids"], [4242])

    def test_a_failed_install_does_not_refresh_the_settings(self):
        f = Fx(self, install_fails=True)
        U.upgrade_once(req(), **f.opts(sessions=[], me="h/db-admin"))
        self.assertFalse(any(c.startswith("user-settings") for c in f.calls), f.calls)

    def test_at_the_pin_nothing_is_installed_and_no_session_is_touched(self):
        f = Fx(self, installed="2.1.281")
        r = U.upgrade_once(req(), **f.opts(sessions=[111], kill=no_kill, me="h/db-admin"))
        self.assertEqual(r, {"status": "current", "piece": "claude", "version": "2.1.281", "session": "running"})
        self.assertFalse(any(c.startswith("install") for c in f.calls))
        self.assertFalse(os.path.exists(U.marker_path(f.dir)))

    def test_a_running_session_marker_first_then_sigterm_wait_install_verify_marker_done(self):
        f = Fx(self)
        order, up = [], [True]

        def kill(pid, sig):
            order.append(f"kill {pid} {sig.name}")
            self.assertEqual(marker(f)["status"], "pending", "the marker is written before the session is signalled")
            up[0] = False
        r = U.upgrade_once(req(), **f.opts(sessions=[4242], kill=kill, alive=lambda _p: up[0], sleep=lambda _s: None, me="h/db-admin",
                                           now=lambda: datetime(2026, 9, 24, 21, 0, tzinfo=timezone.utc)))
        self.assertEqual(r, {"status": "upgraded", "piece": "claude", "from": "2.1.280", "to": "2.1.281", "settings": "refreshed", "session": "restarting"})
        self.assertEqual(list(r), ["status", "piece", "from", "to", "settings", "session"], "the reply's key order is the Node's")
        self.assertEqual(order, ["kill 4242 SIGTERM"])
        self.assertEqual(f.calls, ["--version", "lease held", "install 2.1.281", "--version", "user-settings .claude/settings.json", "lease released"],
                         "the lease is taken before the stop and held through the read-back; the settings follow the new build")
        m = marker(f)
        self.assertEqual([m["status"], m["from"], m["to"], m["installed"], m["request_id"], m["pids"]], ["done", "2.1.280", "2.1.281", "2.1.281", "req-1", [4242]])
        self.assertEqual(m["requested_at"], "2026-09-24T21:00:00.000Z")
        self.assertEqual(stat.S_IMODE(os.stat(U.marker_path(f.dir)).st_mode), 0o600)
        with open(U.marker_path(f.dir)) as fh:
            self.assertTrue(fh.read().endswith("}\n"))

    def test_no_session_installed_no_marker_nothing_signalled(self):
        f = Fx(self)
        r = U.upgrade_once(req(), **f.opts(sessions=[], kill=no_kill, me="h/db-admin"))
        self.assertEqual((r["status"], r["session"]), ("upgraded", "none"))
        self.assertFalse(os.path.exists(U.marker_path(f.dir)))

    def test_the_requesters_own_session_is_never_stopped_and_is_told_to_relaunch(self):
        f = Fx(self)
        r = U.upgrade_once(req(**{"from": "h/user"}), **f.opts(sessions=[777], kill=no_kill, me="h/user"))
        self.assertEqual((r["status"], r["session"]), ("upgraded", "yours: relaunch to use it"))
        self.assertFalse(os.path.exists(U.marker_path(f.dir)), "no restart marker for a session nobody stopped")

    def test_a_session_that_does_not_stop_not_installed_not_forced_the_marker_says_failed(self):
        f = Fx(self)
        sigs = []
        r = U.upgrade_once(req(), **f.opts(sessions=[5], kill=lambda _p, s: sigs.append(s), alive=lambda _p: True, sleep=lambda _s: None, stop_wait_ms=0, me="h/db-admin"))
        self.assertEqual(r["status"], "failed")
        self.assertRegex(r["reason"], r"did not stop .* nothing forced")
        self.assertEqual(sigs, [signal.SIGTERM], "never a second, harder signal")
        self.assertFalse(any(c.startswith("install") for c in f.calls))
        self.assertEqual(f.calls[-1], "lease released", "a failure under the lease still releases it")
        self.assertEqual(marker(f)["status"], "failed", "the launcher relaunches on what is installed and says why")

    def test_an_install_that_fails_or_lands_another_version_is_a_failure_with_its_reason_and_the_session_comes_back(self):
        for kw, pattern in (({"install_fails": True}, r"claude install 2\.1\.281: Install failed: network$"),
                            ({"installs_wrong": True}, r"after install, claude --version says 2\.1\.279")):
            f = Fx(self, **kw)
            up = [True]
            r = U.upgrade_once(req(), **f.opts(sessions=[9], kill=lambda *_a: up.__setitem__(0, False), alive=lambda _p: up[0], sleep=lambda _s: None, me="h/db-admin"))
            self.assertEqual(r["status"], "failed")
            self.assertRegex(r["reason"], pattern)
            self.assertEqual(marker(f)["status"], "failed")

    def test_arguments_are_a_closed_set_no_pin_is_a_refusal_version_overrides_the_pin(self):
        self.assertRegex(U.check_args({"piece": "kernel"}), r"not one of claude, fabric")
        self.assertRegex(U.check_args({"piece": "claude", "version": "2.1.281; rm -rf /"}), r"digits")
        self.assertRegex(U.check_args(None), r"no arguments")
        self.assertIsNone(U.check_args({"piece": "claude", "version": "2.1.282"}))
        f = Fx(self, pin=None)
        self.assertRegex(U.upgrade_once(req(), **f.opts(sessions=[]))["reason"], r"no pinned version")
        g = Fx(self)
        r = U.upgrade_once(req(args={"piece": "claude", "version": "2.1.279"}), **g.opts(sessions=[]))
        self.assertEqual(r["to"], "2.1.279")
        self.assertEqual(U.pinned_version(g.root), "2.1.281")
        for ok in ("1234.1234.123456", "0.0.0"):
            self.assertIsNone(U.check_args({"piece": "claude", "version": ok}), ok)
        for bad in ("12345.1.1", "1.12345.1", "1.1.1234567", "1.1", "a.b.c", "1.1.1.1"):
            self.assertRegex(U.check_args({"piece": "claude", "version": bad}), r"digits", bad)
        for body, want in (('{"claude": "x"}', None), ('{"claude": "2.1.281\\n"}', None), ('{"claude": 2}', None), ("[]", None), ("not json", None), ('{"claude": "9.9.9"}', "9.9.9")):
            h = Fx(self, pin=None)
            with open(os.path.join(h.root, "runtime", "claude-code", "harness.json"), "w") as fh:
                fh.write(body)
            self.assertEqual(U.pinned_version(h.root), want, body)

    def test_one_upgrade_at_a_time(self):
        slow = Fx(self)
        gate = threading.Event()
        entered = threading.Event()
        inner = slow.run

        def run(cmd, **kw):
            if len(cmd) > 1 and cmd[1] == "install":
                entered.set()
                gate.wait(10)
            return inner(cmd, **kw)
        out: list[dict] = []
        t = threading.Thread(target=lambda: out.append(U.upgrade(req(), **slow.opts(sessions=[], run=run))))
        t.start()
        self.assertTrue(entered.wait(10))
        self.assertTrue(U.upgrade_running())
        self.assertEqual(U.upgrade(req(id="req-2"))["status"], "busy")
        gate.set()
        t.join(10)
        self.assertEqual(out[0]["status"], "upgraded")
        self.assertFalse(U.upgrade_running())

    def test_session_pids_this_uids_claude_except_the_daemons_own_children(self):
        proc = tempfile.mkdtemp(prefix="upgrade-proc-")
        self.addCleanup(lambda: __import__("shutil").rmtree(proc, ignore_errors=True))
        for pid, ppid in ((100, 50), (200, 999), (300, 60)):
            os.mkdir(os.path.join(proc, str(pid)))
            with open(os.path.join(proc, str(pid), "stat"), "w") as fh:
                fh.write(f"{pid} (claude) S {ppid} 1 1 0 -1")
        self.assertEqual(U.session_pids(self_pid=999, proc=proc, run=lambda _a: "100\n200\n300\n400\n"), [100, 300],
                         "the daemon's child and a pid already gone are left out")

        def nothing(argv):
            raise subprocess.CalledProcessError(1, argv)
        self.assertEqual(U.session_pids(self_pid=999, proc=proc, run=nothing), [], "pgrep finding nothing is no session")

        def missing(argv):
            raise FileNotFoundError(2, "spawn pgrep ENOENT")
        with self.assertRaisesRegex(FileNotFoundError, "ENOENT"):
            U.session_pids(self_pid=999, proc=proc, run=missing)

        def broken(argv):
            raise subprocess.CalledProcessError(2, argv)
        with self.assertRaises(subprocess.CalledProcessError):
            U.session_pids(self_pid=999, proc=proc, run=broken)
        argv_seen: list[list[str]] = []
        U.session_pids(uid=1234, self_pid=999, proc=proc, run=lambda a: argv_seen.append(a) or "")
        self.assertEqual(argv_seen, [["pgrep", "-u", "1234", "-x", "claude"]])

    def test_a_pgrep_that_fails_nothing_installed_nothing_signalled_the_reason_said(self):
        f = Fx(self)

        def eacces(_argv):
            raise PermissionError(13, "spawn pgrep EACCES")
        r = U.upgrade_once(req(), **f.opts(me="h/db-admin", kill=no_kill, pgrep=eacces))
        self.assertEqual(r["status"], "failed")
        self.assertRegex(r["reason"], r"could not tell whether a session is running .*EACCES.*nothing installed")
        self.assertFalse(any(c.startswith("install") for c in f.calls))

    def test_no_turn_on_the_host_lease_nothing_stopped_nothing_installed_held_or_no_queue(self):
        for err, pattern in ((U.LeaseRefused(U.LEASE_HELD, "still held"), r"install lease \(claude-install\) stayed held for 900 s; not installed, no session stopped"),
                             (U.LeaseRefused(2, "fabric-lease: no lease directory at /run/lock/agent-fabric"),
                              r"install queue is unavailable \(fabric-lease: no lease directory .*\); not installed, no session stopped")):
            f = Fx(self)

            def refuse(err=err):
                raise err
            r = U.upgrade_once(req(), **f.opts(sessions=[31], me="h/db-admin", lease=refuse, kill=no_kill))
            self.assertEqual([r["status"], r["session"]], ["failed", "running"])
            self.assertRegex(r["reason"], pattern)
            self.assertFalse(any(c.startswith("install") for c in f.calls))
            self.assertFalse(os.path.exists(U.marker_path(f.dir)), "no marker: the launcher has nothing to wait for")

    def test_hold_lease_the_real_fabric_lease_holds_until_release(self):
        saved = os.environ.get("AGENT_FABRIC_LEASES")
        leases = tempfile.mkdtemp(prefix="upgrade-hold-")
        self.addCleanup(lambda: __import__("shutil").rmtree(leases, ignore_errors=True))
        self.addCleanup(lambda: os.environ.__setitem__("AGENT_FABRIC_LEASES", saved) if saved is not None else os.environ.pop("AGENT_FABRIC_LEASES", None))
        os.environ["AGENT_FABRIC_LEASES"] = leases
        h = U.hold_lease(HERE)
        began = time.monotonic()
        with self.assertRaises(U.LeaseRefused) as cm:
            U.hold_lease(HERE, wait_s=1)
        self.assertEqual((cm.exception.code, cm.exception.reason), (U.LEASE_HELD, "timeout"), "a second holder waits its time, then is refused — the reason as data")
        self.assertRegex(cm.exception.line, r"still held")
        self.assertGreaterEqual(time.monotonic() - began, 0.9)
        began = time.monotonic()
        h.release()
        self.assertLess(time.monotonic() - began, 5, "release closes the holder's stdin; it does not wait for the holder to give up")
        U.hold_lease(HERE).release()
        nolease = tempfile.mkdtemp(prefix="upgrade-nolease-")
        self.addCleanup(lambda: __import__("shutil").rmtree(nolease, ignore_errors=True))
        os.environ["AGENT_FABRIC_LEASES"] = os.path.join(nolease, "absent")
        with self.assertRaises(U.LeaseRefused) as nd:
            U.hold_lease(HERE)
        self.assertEqual((nd.exception.code, nd.exception.reason), (2, "nodir"))
        self.assertRegex(nd.exception.line, r"no lease directory")
        noscript = tempfile.mkdtemp(prefix="upgrade-noscript-")
        self.addCleanup(lambda: __import__("shutil").rmtree(noscript, ignore_errors=True))
        with self.assertRaises(U.LeaseRefused) as ns:
            U.hold_lease(noscript)
        self.assertEqual(ns.exception.code, -1)
        self.assertRegex(ns.exception.line, r"ENOENT")

    def test_a_refresh_that_wrote_every_key_but_automode_is_not_a_refresh(self):
        f = Fx(self, settings_warn=True)
        r = U.upgrade_once(req(), **f.opts(sessions=[], kill=no_kill, me="h/db-admin"))
        self.assertEqual(r["status"], "upgraded")
        self.assertRegex(r["settings"], r"^not refreshed: .*auto-mode defaults could not be read")

    def test_a_settings_refresh_that_fails_is_said_and_the_install_still_counts(self):
        f = Fx(self, settings_fail=True)
        r = U.upgrade_once(req(), **f.opts(sessions=[], kill=no_kill, me="h/db-admin"))
        self.assertEqual(r["status"], "upgraded")
        self.assertRegex(r["settings"], r"^not refreshed: .*unreadable")

    def test_a_failed_install_says_why_by_its_last_line_one_that_timed_out_says_so(self):
        e = failed(["claude", "install", "2.1.282"], err="Downloading…\n\nError: checksum mismatch for 2.1.282\n")
        self.assertEqual(U.last_line(e), "Error: checksum mismatch for 2.1.282", 'the line that says why, not "Command failed: <argv>"')

        class Said:
            message = "only this"
        self.assertEqual(U.last_line(Said()), "only this")
        f = Fx(self)
        inner = f.run

        def run(cmd, **kw):
            if len(cmd) > 1 and cmd[1] == "install":
                raise subprocess.TimeoutExpired(cmd, kw["timeout"])
            return inner(cmd, **kw)
        r = U.upgrade_once(req(), **f.opts(sessions=[], me="h/db-admin", run=run))
        self.assertRegex(r["reason"], r"claude install 2\.1\.281: timed out after 300 s$")

    def test_the_launcher_outwaits_what_the_daemon_does_after_the_stop(self):
        import re
        parts = [os.path.join(HERE, "tools", "fabric", "launch.py")]
        d = os.path.join(HERE, "tools", "fabric", "launcher")
        parts += [os.path.join(d, n) for n in sorted(os.listdir(d)) if n.endswith(".py")] if os.path.isdir(d) else []
        found = []
        for p in parts:
            with open(p, encoding="utf-8") as fh:
                found += re.findall(r"^RESTART_WAIT_S = (\d+)$", fh.read(), re.M)
        self.assertEqual(len(found), 1, "the launcher's restart wait default is defined once, where this test reads it")
        self.assertGreater(int(found[0]), U.POST_STOP_BUDGET_S)

    def test_two_accounts_upgrading_at_once_each_session_stops_on_its_turn_through_the_real_fabric_lease(self):
        leases = tempfile.mkdtemp(prefix="upgrade-leases-")
        base = tempfile.mkdtemp(prefix="upgrade-two-")
        self.addCleanup(lambda: __import__("shutil").rmtree(leases, ignore_errors=True))
        self.addCleanup(lambda: __import__("shutil").rmtree(base, ignore_errors=True))
        log = os.path.join(base, "installs.log")

        def account(name: str) -> str:
            home = os.path.join(base, name)
            os.makedirs(os.path.join(home, ".local", "bin"))
            state = os.path.join(home, "installed")
            with open(state, "w") as fh:
                fh.write("2.1.281")
            script = os.path.join(home, ".local", "bin", "claude")
            with open(script, "w") as fh:
                # A fake harness: --version reads its state; install records start and end around a 1 s "download".
                fh.write(f"""#!/bin/sh
case "$1" in
  --version) echo "$(cat '{state}') (Claude Code)" ;;
  install) echo "start {name} $(date +%s%N)" >> '{log}'; sleep 1; printf %s "$2" > '{state}'; echo "end {name} $(date +%s%N)" >> '{log}' ;;
esac
""")
            os.chmod(script, 0o755)
            return home
        saved = os.environ.get("AGENT_FABRIC_LEASES")
        os.environ["AGENT_FABRIC_LEASES"] = leases
        self.addCleanup(lambda: os.environ.__setitem__("AGENT_FABRIC_LEASES", saved) if saved is not None else os.environ.pop("AGENT_FABRIC_LEASES", None))
        homes = {n: account(n) for n in ("alpha", "beta")}
        results: dict[str, dict] = {}

        def go(name: str) -> None:
            up = [True]

            def kill(*_a):
                with open(log, "a") as fh:
                    fh.write(f"stop {name}\n")
                up[0] = False
            results[name] = U.upgrade_once(req(args={"piece": "claude", "version": "2.1.282"}), home=homes[name], root=HERE,
                                           directory=os.path.join(homes[name], "state"), sessions=[4000], me="h/x", kill=kill,
                                           alive=lambda _p: up[0], sleep=lambda _s: None, run=self._real_run)
        threads = [threading.Thread(target=go, args=(n,)) for n in homes]
        for t in threads:
            t.start()
        for t in threads:
            t.join(120)
        self.assertEqual([results["alpha"]["status"], results["beta"]["status"]], ["upgraded", "upgraded"], results)
        with open(log) as fh:
            ev = [line.split() for line in fh.read().strip().split("\n")]
        self.assertEqual([e[0] for e in ev], ["stop", "start", "end", "stop", "start", "end"],
                         "a session stopped out of its turn, or the installs overlapped:\n" + "\n".join(" ".join(e) for e in ev))
        self.assertTrue(ev[0][1] == ev[2][1] and ev[3][1] == ev[5][1], "each account stops, installs and finishes before the next one stops")

    @staticmethod
    def _real_run(cmd, **kw):
        # The settings refresh is a program of the checkout under test; this case is about the lease.
        if cmd[0] == sys.executable:
            return done("  +  settings\n")
        return U.default_run(cmd, **kw)


def git(cwd: str, *a: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    return subprocess.run(["git", "-C", cwd, *a], capture_output=True, text=True, check=True, env=env, timeout=60).stdout.strip()


class FabricFx:
    def __init__(self, tc: unittest.TestCase, bootstrap_fails=False, unit_changed=False) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="upgrade-fabric-")
        tc.addCleanup(tmp.cleanup)
        self.base = tmp.name
        origin, self.seed, self.root = (os.path.join(self.base, n) for n in ("origin.git", "seed", "agent-fabric"))
        self.record = os.path.join(self.base, "bootstrap.log")
        git(self.base, "init", "-q", "--bare", "-b", "main", origin)
        git(self.base, "init", "-q", "-b", "main", self.seed)
        os.makedirs(os.path.join(self.seed, "runtime", "claude-code"))
        unit = 'echo "  *  agent-fabric-agentd: unit changed; restart left to the caller"\n' if unit_changed else ""
        body = (unit + 'echo "  *  settings"\necho "bootstrap: the agent files could not be written" >&2\nexit 1\n' if bootstrap_fails else
                f"printf 'defer=%s provider=%s\\n' \"${{AGENT_FABRIC_DEFER_AGENTD_RESTART:-}}\" \"${{AGENT_FABRIC_LAUNCH_PROVIDER:-}}\" >> \"{self.record}\"\n" + unit)
        with open(os.path.join(self.seed, "runtime", "claude-code", "bootstrap.sh"), "w") as fh:
            fh.write(body)
        git(self.seed, "add", "-A")
        git(self.seed, "commit", "-q", "-m", "one")
        git(self.seed, "remote", "add", "origin", origin)
        git(self.seed, "push", "-q", "origin", "main")
        git(self.base, "clone", "-q", origin, self.root)
        self.env = {"PATH": os.environ["PATH"], "HOME": self.base, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}

    def advance(self, msg: str) -> str:
        with open(os.path.join(self.seed, f"{msg}.txt"), "w") as fh:
            fh.write(msg)
        git(self.seed, "add", "-A")
        git(self.seed, "commit", "-q", "-m", msg)
        git(self.seed, "push", "-q", "origin", "main")
        return git(self.seed, "rev-parse", "HEAD")

    def runs(self) -> list[str]:
        if not os.path.exists(self.record):
            return []
        with open(self.record) as fh:
            return fh.read().strip().split("\n")

    def head(self) -> str:
        return git(self.root, "rev-parse", "HEAD")

    def opts(self, **over):
        return {"root": self.root, "sessions": [], "env": self.env, **over}


def freq(commit: str) -> dict:
    return {"id": "req-1", "from": "h/user", "op": "upgrade", "args": {"piece": "fabric", "commit": commit}}


class UpgradeFabric(unittest.TestCase):
    def test_behind_fast_forwarded_bootstrapped_with_the_daemon_restart_deferred_the_daemon_told_to_restart(self):
        f = FabricFx(self)
        from_ = f.head()[:7]
        target = f.advance("two")
        r = U.upgrade_fabric(freq(target), **f.opts())
        self.assertEqual((r["status"], r["from"], r["to"]), ("upgraded", from_, target[:7]))
        self.assertEqual(f.head(), target)
        self.assertEqual(f.runs(), ["defer=1 provider="])
        self.assertTrue(r["restart_daemon"])
        self.assertEqual(r["session"], "none")
        self.assertEqual(list(r), ["status", "piece", "from", "to", "session", "restart_daemon", "note"])
        self.assertEqual(r["note"], "the control agent restarts on the new code after this reply")

    def test_at_the_commit_current_bootstrap_still_runs_no_daemon_restart(self):
        f = FabricFx(self)
        r = U.upgrade_fabric(freq(f.head()), **f.opts())
        self.assertEqual((r["status"], r["restart_daemon"]), ("current", False))
        self.assertNotIn("note", r)
        self.assertEqual(len(f.runs()), 1)

    def test_an_older_commit_than_the_checkout_current_never_moved_back(self):
        f = FabricFx(self)
        old = f.head()
        target = f.advance("two")
        git(f.root, "pull", "-q", "--ff-only")
        r = U.upgrade_fabric(freq(old), **f.opts())
        self.assertEqual(r["status"], "current")
        self.assertEqual(f.head(), target)

    def test_a_checkout_on_a_branch_is_someones_work_refused_not_moved_not_bootstrapped(self):
        f = FabricFx(self)
        git(f.root, "switch", "-q", "-c", "h/someone/work")
        target = f.advance("two")
        before = f.head()
        r = U.upgrade_fabric(freq(target), **f.opts())
        self.assertEqual(r["status"], "refused")
        self.assertRegex(r["reason"], r"on h/someone/work, not main")
        self.assertEqual(f.head(), before)
        self.assertEqual(f.runs(), [])

    def test_a_branch_with_nothing_uncommitted_and_nothing_unpushed_still_refused_but_says_a_switch_loses_nothing(self):
        f = FabricFx(self)
        git(f.root, "switch", "-q", "-c", "h/someone/locale")
        git(f.root, "push", "-q", "-u", "origin", "h/someone/locale")
        target = f.advance("two")
        with open(os.path.join(f.root, "scratch.txt"), "w") as fh:
            fh.write("uncommitted")
        self.assertRegex(U.upgrade_fabric(freq(target), **f.opts())["reason"], r"find whose work it is", "uncommitted work: not known safe")
        os.unlink(os.path.join(f.root, "scratch.txt"))
        before = f.head()
        r = U.upgrade_fabric(freq(target), **f.opts())
        self.assertEqual(r["status"], "refused")
        self.assertRegex(r["reason"], r"clean and pushed, so nothing is lost by `git switch main`")
        self.assertEqual(f.head(), before, "not moved: a session on the branch would lose its hooks")
        self.assertEqual(f.runs(), [])
        with open(os.path.join(f.root, "unpushed.txt"), "w") as fh:
            fh.write("x")
        git(f.root, "add", "-A")
        git(f.root, "commit", "-q", "-m", "local")
        self.assertRegex(U.upgrade_fabric(freq(target), **f.opts())["reason"], r"find whose work it is", "an unpushed commit: not known safe")

    def test_a_main_that_cannot_fast_forward_failed_never_forced_not_bootstrapped(self):
        f = FabricFx(self)
        with open(os.path.join(f.root, "local.txt"), "w") as fh:
            fh.write("x")
        git(f.root, "add", "-A")
        git(f.root, "commit", "-q", "-m", "local")
        before = f.head()
        target = f.advance("two")
        r = U.upgrade_fabric(freq(target), **f.opts())
        self.assertEqual(r["status"], "failed")
        self.assertRegex(r["reason"], r"cannot fast-forward .*not forced")
        self.assertEqual(f.head(), before)
        self.assertEqual(f.runs(), [])

    def test_a_commit_that_is_not_on_the_accounts_origin_main_refused_not_moved(self):
        f = FabricFx(self)
        before = f.head()
        r = U.upgrade_fabric(freq("0" * 40), **f.opts())
        self.assertEqual(r["status"], "refused")
        self.assertRegex(r["reason"], r"not on this account's origin/main")
        self.assertEqual(f.head(), before)

    def test_a_bootstrap_that_fails_failed_with_its_last_line_the_checkout_has_moved_and_says_so(self):
        f = FabricFx(self, bootstrap_fails=True)
        target = f.advance("two")
        r = U.upgrade_fabric(freq(target), **f.opts())
        self.assertEqual((r["status"], r["to"]), ("failed", target[:7]))
        self.assertEqual(r["reason"], "bootstrap: bootstrap: the agent files could not be written")

    def test_a_running_session_bootstrap_installs_for_the_provider_it_was_launched_with_the_session_is_not_stopped(self):
        f = FabricFx(self)
        proc = os.path.join(f.base, "proc")
        os.makedirs(os.path.join(proc, "4242"))
        with open(os.path.join(proc, "4242", "environ"), "wb") as fh:
            fh.write(b"HOME=/h\0AGENT_FABRIC_LAUNCH_PROVIDER=openrouter\0")
        target = f.advance("two")
        r = U.upgrade_fabric(freq(target), **f.opts(sessions=[4242], proc=proc))
        self.assertEqual((r["provider"], r["session"]), ("openrouter", "running: next launch uses it"))
        self.assertEqual(f.runs(), ["defer=1 provider=openrouter"])

    def test_session_provider_an_unreadable_or_malformed_value_is_no_provider(self):
        proc = tempfile.mkdtemp(prefix="upgrade-fabric-proc-")
        self.addCleanup(lambda: __import__("shutil").rmtree(proc, ignore_errors=True))
        os.mkdir(os.path.join(proc, "7"))
        with open(os.path.join(proc, "7", "environ"), "wb") as fh:
            fh.write(b"AGENT_FABRIC_LAUNCH_PROVIDER=$(x)\0")
        self.assertIsNone(U.session_provider([7, 8], proc))

    def test_arguments_fabric_takes_a_full_sha_and_no_version_claude_takes_no_commit(self):
        self.assertIsNone(U.check_args({"piece": "fabric", "commit": "a" * 40}))
        self.assertRegex(U.check_args({"piece": "fabric", "commit": "abc1234"}), r"full 40-hex sha")
        self.assertRegex(U.check_args({"piece": "fabric", "commit": "a" * 40, "version": "2.1.1"}), r"not a version")
        self.assertRegex(U.check_args({"piece": "claude", "commit": "a" * 40}), r"not a commit")

    def test_upgrade_routes_the_fabric_piece_one_action_at_a_time(self):
        f = FabricFx(self)
        target = f.advance("two")
        gate, entered = threading.Event(), threading.Event()

        def run(cmd, **kw):
            if cmd[0] == "bash":
                entered.set()
                gate.wait(10)
            return U.default_run(cmd, **kw)
        out: list[dict] = []
        t = threading.Thread(target=lambda: out.append(U.upgrade(freq(target), **f.opts(run=run))))
        t.start()
        self.assertTrue(entered.wait(30))
        self.assertEqual(U.upgrade(freq(target), **f.opts())["status"], "busy")
        gate.set()
        t.join(30)
        self.assertEqual(out[0]["status"], "upgraded")

    def test_a_current_checkout_whose_bootstrap_changed_the_unit_the_daemon_still_restarts_and_the_row_says_so(self):
        f = FabricFx(self, unit_changed=True)
        r = U.upgrade_fabric(freq(f.head()), **f.opts())
        self.assertEqual((r["status"], r["restart_daemon"]), ("current", True))
        self.assertRegex(r["note"], r"restarts on the new unit")

    def test_a_merge_base_that_cannot_tell_is_failed_with_gits_line_not_not_on_origin_main(self):
        f = FabricFx(self)

        def run(cmd, **kw):
            if "merge-base" in cmd:
                raise failed(cmd, code=128, err="fatal: bad object")
            return U.default_run(cmd, **kw)
        r = U.upgrade_fabric(freq(f.advance("two")), **f.opts(run=run))
        self.assertEqual(r["status"], "failed")
        self.assertRegex(r["reason"], r"git merge-base: fatal: bad object; not moved")

    def test_a_commit_the_account_has_but_not_on_its_origin_main_refused_not_moved(self):
        f = FabricFx(self)
        git(f.seed, "switch", "-q", "-c", "side")
        with open(os.path.join(f.seed, "side.txt"), "w") as fh:
            fh.write("x")
        git(f.seed, "add", "-A")
        git(f.seed, "commit", "-q", "-m", "side")
        git(f.seed, "push", "-q", "origin", "side")
        side = git(f.seed, "rev-parse", "HEAD")
        git(f.root, "fetch", "-q", "origin", "side")
        before = f.head()
        r = U.upgrade_fabric(freq(side), **f.opts())
        self.assertEqual(r["status"], "refused")
        self.assertRegex(r["reason"], r"not on this account's origin/main")
        self.assertEqual(f.head(), before)

    def test_a_bootstrap_that_installed_the_unit_and_then_failed_failed_and_the_daemon_still_restarts(self):
        f = FabricFx(self, bootstrap_fails=True, unit_changed=True)
        r = U.upgrade_fabric(freq(f.head()), **f.opts())
        self.assertEqual((r["status"], r["restart_daemon"]), ("failed", True))
        self.assertNotIn("note", r)


class PortAdditions(unittest.TestCase):
    """What the Node suite could not say: the port's own seams."""

    def test_a_number_or_a_list_that_prints_as_a_sha_is_the_nodes_answer_a_refusal_never_a_raise(self):
        big = 1111111111111111111111111111111111111111.0   # what a 40-digit JSON literal parses to
        self.assertEqual(U.js_string(big), "1.1111111111111112e+39")
        self.assertEqual(U.js_string(1e-7), "1e-7")
        self.assertEqual(U.js_string(1e-5), "0.00001", "JavaScript writes an exponent only below 1e-6")
        self.assertEqual(U.js_string(10 ** 39), "1e+39", "a 40-digit integer a plain json.loads left an int is the double Node read")
        self.assertRegex(U.check_args({"piece": "fabric", "commit": 10 ** 39}), r"full 40-hex sha")
        self.assertEqual(U.js_string(2.0), "2")
        self.assertEqual(U.js_string(2.5), "2.5")
        self.assertIsNone(U.check_args({"piece": "fabric", "commit": ["a" * 40]}), "a one-element list prints as its element")
        self.assertRegex(U.check_args({"piece": "fabric", "commit": big}), r"full 40-hex sha")
        f = FabricFx(self)
        r = U.upgrade_fabric({"id": "r", "from": "h/u", "args": {"piece": "fabric", "commit": [f.head()]}}, **f.opts())
        self.assertEqual(r["status"], "current", "a one-element list that prints as the sha is the sha, as `${commit}` was")

    def test_a_program_that_fails_without_output_says_command_failed_with_its_argv(self):
        e = subprocess.CalledProcessError(1, ["false", "-x"])
        self.assertEqual(U.last_line(e), "Command failed: false -x")
        self.assertEqual(U.last_line(subprocess.TimeoutExpired(["slow", "a"], 5)), "Command failed: slow a")
        f = Fx(self)
        inner = f.run

        def run(cmd, **kw):
            if len(cmd) > 1 and cmd[1] == "install":
                raise subprocess.CalledProcessError(2, cmd)
            return inner(cmd, **kw)
        r = U.upgrade_once(req(), **f.opts(sessions=[], me="h/db-admin", run=run))
        self.assertRegex(r["reason"], r"^claude install 2\.1\.281: Command failed: .*claude install 2\.1\.281$")

        def pgrep(argv):
            raise subprocess.CalledProcessError(2, argv)
        r = U.upgrade_once(req(), **f.opts(me="h/db-admin", pgrep=pgrep))
        self.assertRegex(r["reason"], r"\(pgrep: Command failed: pgrep -u \d+ -x claude\)")

        def missing(argv):
            raise FileNotFoundError(2, "No such file", "pgrep")
        r = U.upgrade_once(req(), **f.opts(me="h/db-admin", pgrep=missing))
        self.assertRegex(r["reason"], r"\(pgrep: spawnSync pgrep ENOENT\)")

    def test_a_settings_refresh_that_times_out_names_python3_and_its_arguments_as_the_node_did(self):
        f = Fx(self)
        inner = f.run

        def run(cmd, **kw):
            if cmd[0] == sys.executable:
                raise subprocess.TimeoutExpired(cmd, kw["timeout"])
            return inner(cmd, **kw)
        r = U.upgrade_once(req(), **f.opts(sessions=[], me="h/db-admin", run=run))
        self.assertEqual(r["status"], "upgraded")
        said = f"Command failed: python3 {os.path.join(f.root, 'runtime', 'claude-code', 'user-settings.py')} {os.path.join(f.home, '.claude', 'settings.json')}"
        self.assertEqual(r["settings"], f"not refreshed: {said[:160]}", "the line is cut at 160, as the Node cut it")

    def test_a_head_that_cannot_be_read_back_keeps_the_nodes_key_order(self):
        f = FabricFx(self)
        target = f.advance("two")

        def run(cmd, **kw):
            if "rev-parse" in cmd and "--short" in cmd and f.head() == target:
                raise failed(cmd, code=128, err="fatal: cannot read")
            return U.default_run(cmd, **kw)
        r = U.upgrade_fabric(freq(target), **f.opts(run=run))
        self.assertEqual(list(r), ["status", "piece", "from", "reason", "restart_daemon"])
        self.assertRegex(r["reason"], r"moved, but HEAD could not be read back: fatal: cannot read; not bootstrapped")

    def test_a_request_without_an_id_writes_a_marker_without_request_id_as_json_stringify_does(self):
        f = Fx(self)
        up = [True]
        U.upgrade_once({"from": "h/user", "args": {"piece": "claude"}}, **f.opts(sessions=[9], kill=lambda *_a: up.__setitem__(0, False), alive=lambda _p: up[0],
                                                                               sleep=lambda _s: None, me="h/x"))
        self.assertNotIn("request_id", marker(f))

    def test_the_names_other_control_modules_reach_resolve_without_fakes(self):
        from control import secrets
        self.assertIs(secrets.upgrade(), U)
        for name in ("STOP_WAIT_MS", "upgrade_running", "restart_in_flight", "marker_path", "write_marker", "session_pids"):
            self.assertTrue(hasattr(U, name), name)
        self.assertEqual(U.STOP_WAIT_MS, 90000)
        self.assertEqual(U.upgrade_running(), False)

    def test_a_secrets_sync_restart_interlocks_with_the_real_upgrade_module(self):
        U.restart_in_flight(True)
        try:
            u = U.upgrade(req(), home="/nonexistent")
            self.assertEqual((u["status"], u["note"]), ("busy", "a secrets-sync is restarting the session on this account"))
        finally:
            U.restart_in_flight(False)
        self.assertEqual(U.upgrade(req(args={"piece": "claude", "version": "x"}))["status"], "refused", "the interlock is released afterwards")

    def test_a_version_or_commit_with_a_trailing_newline_is_refused(self):
        self.assertRegex(U.check_args({"piece": "claude", "version": "2.1.281\n"}), r"digits")
        self.assertRegex(U.check_args({"piece": "fabric", "commit": "a" * 40 + "\n"}), r"full 40-hex sha")

    def test_the_marker_is_replaced_whole_and_private_even_over_a_stale_loose_temp_file(self):
        d = tempfile.mkdtemp(prefix="upgrade-marker-")
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        tmp = U.marker_path(d) + ".tmp"
        with open(tmp, "w") as fh:
            fh.write("stale")
        os.chmod(tmp, 0o644)
        U.write_marker(d, {"status": "pending", "n": 1})
        self.assertEqual(sorted(os.listdir(d)), ["restart.json"])
        self.assertEqual(stat.S_IMODE(os.stat(U.marker_path(d)).st_mode), 0o600)
        with open(U.marker_path(d)) as fh:
            self.assertEqual(fh.read(), '{\n  "status": "pending",\n  "n": 1\n}\n')

    def test_a_version_that_cannot_be_read_is_a_failure_with_the_reason_and_nothing_else_ran(self):
        f = Fx(self)

        def missing(cmd, **kw):
            raise FileNotFoundError(2, "No such file", cmd[0])
        r = U.upgrade_once(req(), **f.opts(run=missing, sessions=[]))
        self.assertEqual(r["status"], "failed")
        self.assertRegex(r["reason"], r"^claude --version: spawn .* ENOENT$")
        self.assertNotIn("from", r)

    def test_a_lease_that_never_answers_is_a_refusal_not_a_hang(self):
        fake = tempfile.mkdtemp(prefix="upgrade-silent-")
        self.addCleanup(lambda: __import__("shutil").rmtree(fake, ignore_errors=True))
        os.makedirs(os.path.join(fake, "bin"))
        script = os.path.join(fake, "bin", "fabric-lease")
        with open(script, "w") as fh:
            fh.write("#!/bin/sh\nexec sleep 30\n")
        os.chmod(script, 0o755)
        saved = U.LEASE_GRACE_S
        U.LEASE_GRACE_S = 1
        self.addCleanup(lambda: setattr(U, "LEASE_GRACE_S", saved))
        began = time.monotonic()
        with self.assertRaises(U.LeaseRefused) as cm:
            U.hold_lease(fake, wait_s=0)
        self.assertLess(time.monotonic() - began, 10)
        self.assertEqual(cm.exception.code, -1)
        self.assertRegex(cm.exception.line, r"did not answer within 1 s")

    def test_a_process_that_cannot_be_signalled_is_not_taken_for_gone(self):
        real = os.kill

        def eperm(pid, sig):
            raise PermissionError(1, "Operation not permitted")
        os.kill = eperm
        try:
            self.assertTrue(U._alive(1))
        finally:
            os.kill = real
        self.assertFalse(U._alive(2 ** 22 + 12345))


if __name__ == "__main__":
    unittest.main()
