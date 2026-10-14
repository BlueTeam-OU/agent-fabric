#!/usr/bin/env python3
"""tools/fabric/provisioning/ssh_add_login.py (j81; ADR-048): one more account
reaches the operator's ssh from the staging ssh-operator.sh made. Every trust
step has a refusal case and, beside it, the positive control — the same staging
accepted — so a refusal cannot be a staging that was wrong for another reason.
The owner the staging must have is this process's uid (a test is not root); the
CLI, which always demands root, is shown refusing the same staging."""
from __future__ import annotations

import io
import json
import os
import pwd
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from provisioning import ssh_add_login as sal, worker, worker_args as wa  # noqa: E402

ME = os.geteuid()
LIBEXEC = "/usr/local/libexec/agent-fabric"
KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGb1y2fxD0RkCq3dHn2iN8f3mR1vD0n1QvJx2v0r2X7a"
LINE = f'command="{LIBEXEC}/enter-ssh",restrict,pty {KEY}\n'
CONF = "ListenAddress 127.0.0.1\nAllowUsers alpha-01 beta-02\nMaxStartups 100\n"


def account(login: str = "gamma-03", uid: int = 1500, gecos: str = "agent-fabric python-dev") -> pwd.struct_passwd:
    return pwd.struct_passwd((login, "x", uid, uid, gecos, f"/home/{login}", "/bin/bash"))


class Staging(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ssh-add-login.")
        self.addCleanup(self.tmp.cleanup)
        self.stage = os.path.join(self.tmp.name, "stage")
        os.makedirs(os.path.join(self.stage, "authorized_keys"))
        os.chmod(self.stage, 0o700)
        os.chmod(os.path.join(self.stage, "authorized_keys"), 0o755)
        self.put("50-agent-fabric.conf", CONF, 0o600)
        self.put("restore.sh", "#!/bin/sh\n", 0o755)
        for n in ("alpha-01", "beta-02"):
            self.put(f"authorized_keys/{n}", LINE, 0o644)
        self.restored: list[str] = []

    def put(self, rel: str, text: str, mode: int) -> str:
        path = os.path.join(self.stage, rel)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(path, mode)
        return path

    def read(self, rel: str) -> str:
        with open(os.path.join(self.stage, rel), encoding="utf-8") as fh:
            return fh.read()

    def snapshot(self) -> dict[str, str]:
        out = {}
        for d, _, fs in os.walk(self.stage):
            for f in fs:
                if f == ".ssh-add-login.lock":
                    continue      # the empty file flock needs; it carries no state
                p = os.path.join(d, f)
                out[os.path.relpath(p, self.stage)] = open(p, encoding="utf-8").read()
        return out

    def add(self, login: str = "gamma-03", **kw):
        kw.setdefault("entry", account(login))
        return sal.add_login(login, self.stage, LIBEXEC, owner=ME, restore=self.restored.append, **kw)

    def refuses(self, why: str, login: str = "gamma-03", **kw) -> None:
        before, restarts = self.snapshot(), len(self.restored)
        with self.assertRaisesRegex(sal.Refused, why):
            self.add(login, **kw)
        self.assertEqual(self.snapshot(), before, "a refusal writes nothing")
        self.assertEqual(len(self.restored), restarts, "…and restarts nothing")


class Adds(Staging):
    def test_the_login_joins_allowusers_and_gets_the_staged_operator_key_then_the_staged_restore_runs(self):
        self.add()
        self.assertEqual(self.read("authorized_keys/gamma-03"), LINE)
        self.assertEqual(self.read("50-agent-fabric.conf"), CONF.replace("alpha-01 beta-02", "alpha-01 beta-02 gamma-03"))
        self.assertEqual(self.restored, [os.path.join(self.stage, "restore.sh")])
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.stage, "authorized_keys/gamma-03")).st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.stage, "50-agent-fabric.conf")).st_mode), 0o600)
        self.assertEqual(sorted(os.listdir(os.path.join(self.stage, "authorized_keys"))), ["alpha-01", "beta-02", "gamma-03"],
                         "no temporary file left")

    def test_again_changes_nothing_and_a_name_sorts_in_once(self):
        self.add()
        first = self.snapshot()
        self.add()
        self.assertEqual(self.snapshot(), first)
        self.add("aaa-00", entry=account("aaa-00"))
        self.assertIn("AllowUsers aaa-00 alpha-01 beta-02 gamma-03\n", self.read("50-agent-fabric.conf"))

    def test_a_restore_that_fails_is_a_refusal_naming_it_with_the_login_already_staged(self):
        def fail(path):
            raise sal.Refused(f"{path} exited 1; the login is staged, sshd may not have restarted")
        with self.assertRaisesRegex(sal.Refused, "exited 1; the login is staged"):
            sal.add_login("gamma-03", self.stage, LIBEXEC, entry=account(), owner=ME, restore=fail)
        self.assertEqual(self.read("authorized_keys/gamma-03"), LINE)

    def test_the_real_restore_runner_reports_a_non_zero_exit_a_missing_file_and_a_timeout(self):
        sh = self.put("bad.sh", "#!/bin/sh\nexit 3\n", 0o755)
        with self.assertRaisesRegex(sal.Refused, "exited 3"):
            sal.run_restore(sh)
        with self.assertRaisesRegex(sal.Refused, "No such file"):
            sal.run_restore(os.path.join(self.stage, "nowhere.sh"))
        slow = self.put("slow.sh", "#!/bin/sh\nsleep 5\n", 0o755)
        with mock.patch.object(sal, "RESTORE_TIMEOUT_S", 0.2), self.assertRaisesRegex(sal.Refused, "did not finish within"):
            sal.run_restore(slow)
        self.assertIsNone(sal.run_restore(self.put("ok.sh", "#!/bin/sh\nexit 0\n", 0o755)))


class Races(Staging):
    def test_j81_logins_added_together_all_land_in_allowusers(self):
        import threading
        real = sal.read_text

        def slow(path):
            text = real(path)
            if path.endswith(".conf"):
                time.sleep(0.05)      # the window between reading the drop-in and writing it
            return text
        logins = [f"zz-{i:02d}" for i in range(6)]
        errors: list[BaseException] = []

        def one(n):
            try:
                self.add(n, entry=account(n))
            except BaseException as exc:      # noqa: BLE001 — surfaced below
                errors.append(exc)
        with mock.patch.object(sal, "read_text", slow):
            ts = [threading.Thread(target=one, args=(n,)) for n in logins]
            for t in ts:
                t.start()
            for t in ts:
                t.join(30)
        self.assertEqual(errors, [])
        names = self.read("50-agent-fabric.conf").split("AllowUsers ")[1].split("\n")[0].split()
        self.assertEqual(names, sorted(["alpha-01", "beta-02", *logins]))
        self.assertEqual(sorted(os.listdir(os.path.join(self.stage, "authorized_keys"))), sorted(["alpha-01", "beta-02", *logins]))

    def test_a_temporary_file_a_killed_run_left_does_not_block_later_runs(self):
        self.put("authorized_keys/.zz-99.123.new", "half", 0o600)
        self.add()
        self.assertEqual(self.read("authorized_keys/gamma-03"), LINE)


class RefusesTheLogin(Staging):
    def test_a_name_that_is_not_a_plain_login_would_write_more_than_one_rule_into_allowusers(self):
        self.add()      # positive control: the staging is accepted
        for bad in ("a b", "a\nPermitRootLogin yes", "A-upper", "ro*t", "x!", "-lead", "", "x" * 33, "a,b", "a:b", "../x", "a/b"):
            self.refuses("not a plain login name", bad, entry=account("gamma-03"))

    def test_root_a_missing_account_a_system_uid_and_an_account_new_agent_did_not_make(self):
        self.refuses("never reachable", "root", entry=account("root", uid=0))
        self.refuses("no account on this host", entry=None)
        self.refuses("system account", entry=account(uid=999))
        self.refuses("system account", entry=account(uid=0))
        for gecos in ("", "Some Service", "agent-fabric", "xagent-fabric role"):
            self.refuses("was not made by new-agent", entry=account(gecos=gecos))
        self.add(entry=account(gecos="agent-fabric human"))      # the other comment new-agent leaves

    def test_the_account_is_looked_up_by_the_cli_and_an_absent_one_is_refused(self):
        err = io.StringIO()
        env = {"AGENT_FABRIC_SSH_STAGE": self.stage, "AGENT_FABRIC_SSH_LIBEXEC": LIBEXEC}
        with redirect_stderr(err):
            rc = sal.main(["no-such-login-zz"], env)
        self.assertEqual(rc, 1)
        self.assertEqual(err.getvalue(), "ssh-add-login: no-such-login-zz has no account on this host\n")


class RefusesTheStaging(Staging):
    def test_a_staging_directory_or_file_an_account_could_write_is_refused_and_the_same_staging_closed_is_not(self):
        self.add()
        for rel, mode in (("", 0o770), ("", 0o702), ("50-agent-fabric.conf", 0o660), ("restore.sh", 0o775),
                          ("authorized_keys", 0o775), ("authorized_keys/alpha-01", 0o664), ("authorized_keys/beta-02", 0o646)):
            path = os.path.join(self.stage, rel) if rel else self.stage
            was = stat.S_IMODE(os.stat(path).st_mode)
            os.chmod(path, mode)
            self.refuses("closed to group and others")
            os.chmod(path, was)

    def test_an_owner_other_than_root_is_refused_by_the_cli_which_always_demands_it(self):
        err = io.StringIO()
        env = {"AGENT_FABRIC_SSH_STAGE": self.stage, "AGENT_FABRIC_SSH_LIBEXEC": LIBEXEC}
        me = pwd.getpwuid(ME).pw_name
        with mock.patch.object(sal.pwd, "getpwnam", return_value=account(me)), redirect_stderr(err):
            rc = sal.main([me], env)
        # Not root: the staging this process owns is not root's. (As root the same call would go on.)
        self.assertEqual(rc, 1 if ME != 0 else rc)
        if ME != 0:
            self.assertIn("is not owned by uid 0", err.getvalue())
        self.assertEqual(sorted(os.listdir(os.path.join(self.stage, "authorized_keys"))), ["alpha-01", "beta-02"])
        with self.assertRaisesRegex(sal.Refused, "is not owned by uid"):
            sal.add_login("gamma-03", self.stage, LIBEXEC, entry=account(), owner=ME + 1, restore=self.restored.append)
        self.assertEqual(self.restored, [])

    def test_a_symlink_is_never_followed_into_the_staging(self):
        outside = os.path.join(self.tmp.name, "outside.conf")
        with open(outside, "w") as fh:
            fh.write(CONF)
        os.chmod(outside, 0o600)
        conf = os.path.join(self.stage, "50-agent-fabric.conf")
        os.unlink(conf)
        os.symlink(outside, conf)
        self.refuses("not a regular file")
        os.unlink(conf)
        self.put("50-agent-fabric.conf", CONF, 0o600)
        self.add()      # control

    def test_a_missing_or_odd_dropin_is_refused(self):
        conf = os.path.join(self.stage, "50-agent-fabric.conf")
        for text, why in (("", "exactly one AllowUsers"), ("AllowUsers a\nAllowUsers b\n", "exactly one AllowUsers"),
                          ("AllowUsers alpha-01 x*\n", "not a plain login"), ("AllowUsers alpha-01 ro\\\n", "not a plain login")):
            self.put("50-agent-fabric.conf", text, 0o600)
            self.refuses(why)
        os.unlink(conf)
        self.refuses("No such file")
        self.put("50-agent-fabric.conf", CONF, 0o600)
        self.add()

    def test_the_operator_key_must_be_staged_alike_in_the_shape_ssh_operator_writes(self):
        keys = "authorized_keys"
        other = LINE.replace("Gb1y2fx", "Hb1y2fx")
        shapes = (
            ("alpha-01", other, "different operator keys"),
            ("alpha-01", LINE + LINE, "not the one forced-command line"),
            ("alpha-01", LINE.rstrip("\n"), "not the one forced-command line"),
            ("alpha-01", 'command="/home/x/enter-ssh",restrict,pty ' + KEY + "\n", "not the one forced-command line"),
            ("alpha-01", LINE.replace(",restrict,pty", ""), "not the one forced-command line"),
            ("alpha-01", LINE.replace(KEY, "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ=="), "not the one forced-command line"),
            ("alpha-01", LINE.replace(KEY, KEY + " owner@deck"), "not the one forced-command line"),
            ("alpha-01", "", "not the one forced-command line"),
        )
        for name, text, why in shapes:
            self.put(f"{keys}/{name}", text, 0o644)
            self.refuses(why)
            self.put(f"{keys}/{name}", LINE, 0o644)
        self.add()      # control
        for n in os.listdir(os.path.join(self.stage, keys)):
            os.unlink(os.path.join(self.stage, keys, n))
        self.refuses("no keys file is staged")

    def test_a_restore_script_that_is_not_the_staged_trusted_file_is_not_run(self):
        os.unlink(os.path.join(self.stage, "restore.sh"))
        self.refuses("No such file")
        self.put("restore.sh", "#!/bin/sh\n", 0o755)
        self.add()


class Entry(unittest.TestCase):
    def test_usage_is_exit_2_and_names_the_form(self):
        for argv in ([], ["a", "b"]):
            err = io.StringIO()
            with redirect_stderr(err):
                self.assertEqual(sal.main(argv, {}), 2)
            self.assertIn("usage: ssh_add_login.py <login>", err.getvalue())

    def test_the_real_entry_refuses_as_a_subprocess_with_one_line_and_no_traceback(self):
        with tempfile.TemporaryDirectory(prefix="ssh-add-login.") as d:
            env = {"PATH": os.environ["PATH"], "AGENT_FABRIC_SSH_STAGE": os.path.join(d, "none")}
            got = subprocess.run([sys.executable, "-I", os.path.join(HERE, "tools", "fabric", "provisioning", "ssh_add_login.py"),
                                  "root"], env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual((got.returncode, got.stdout), (1, ""))
        self.assertEqual(got.stderr, "ssh-add-login: root is never reachable over the operator's ssh\n")


LOGIN = "zz-unit-login"


class WorkerStep(unittest.TestCase):
    def worker(self, *argv: str, human: bool = False) -> worker.Worker:
        who = ["--human"] if human else ["backend-dev", "--no-claude-account"]
        w = worker.Worker(wa.parse_args(["finish", LOGIN, *who, *argv]), root=HERE, env={})
        w.home = f"/home/{LOGIN}"
        return w

    def step(self, w, registry, here="here-host"):
        calls, err = [], io.StringIO()
        with tempfile.TemporaryDirectory(prefix="ssh-add-login.") as d:
            reg = os.path.join(d, "registry.json")
            if registry is not None:
                with open(reg, "w") as fh:
                    fh.write(registry if isinstance(registry, str) else json.dumps(registry))

            def fake(argv, **kw):
                calls.append(list(argv))
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
            with mock.patch.dict(os.environ, {"AGENT_FABRIC_HOSTS_REGISTRY": reg}), mock.patch.object(subprocess, "run", fake), \
                    mock.patch.object(worker.hs, "host_check", return_value=f"{here}\naccount: present\n"), redirect_stderr(err):
                try:
                    worker.operator_ssh(w)
                    stopped = None
                except worker.Stop as exc:
                    stopped = exc.code
        return calls, err.getvalue(), stopped

    def test_a_host_with_an_sshd_pin_runs_the_script_as_root_on_the_pinned_python_for_this_login_only(self):
        pinned = {"hosts": {"here-host": {"sshd": {"address": "127.0.0.1", "port": 22, "host_keys": []}}}}
        calls, err, stopped = self.step(self.worker(), pinned)
        script = os.path.join(HERE, "tools", "fabric", "provisioning", "ssh_add_login.py")
        self.assertEqual(calls, [["sudo", "-n", worker.PY, "-I", script, LOGIN]])
        self.assertIsNone(stopped)
        self.assertIn(f"9b. ssh: {LOGIN} is in AllowUsers", err)

    def test_no_pin_for_this_host_runs_nothing_and_says_so_whatever_another_host_pins(self):
        for reg in ({"hosts": {"here-host": {"sshd": None}}}, {"hosts": {"here-host": {}}},
                    {"hosts": {"other": {"sshd": {"address": "127.0.0.1"}}}}, {"hosts": {}}, {}):
            calls, err, stopped = self.step(self.worker(), reg)
            self.assertEqual((calls, stopped), ([], None), reg)
            self.assertIn("pins no sshd", err)
            self.assertIn(f"ssh_add_login.py {LOGIN}", err, "the message names the command to run once it does")

    def test_an_unreadable_registry_stops_the_run_it_is_not_taken_for_no_pin(self):
        for reg in (None, "not json", "[]"):
            calls, err, stopped = self.step(self.worker(), reg)
            self.assertEqual((calls, stopped), ([], 1), reg)
            self.assertIn("could not be read for the sshd pin", err)

    def test_a_script_that_refuses_stops_the_run_and_a_dry_run_runs_nothing(self):
        pinned = {"hosts": {"here-host": {"sshd": {"address": "127.0.0.1", "port": 22, "host_keys": []}}}}
        w = self.worker()
        err = io.StringIO()
        with tempfile.TemporaryDirectory(prefix="ssh-add-login.") as d:
            reg = os.path.join(d, "r.json")
            with open(reg, "w") as fh:
                json.dump(pinned, fh)
            with mock.patch.dict(os.environ, {"AGENT_FABRIC_HOSTS_REGISTRY": reg}), \
                    mock.patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 1, stdout="", stderr="")), \
                    mock.patch.object(worker.hs, "host_check", return_value="here-host\n"), redirect_stderr(err):
                with self.assertRaises(worker.Stop):
                    worker.operator_ssh(w)
        self.assertIn("step failed:", err.getvalue())
        calls, err2, stopped = self.step(self.worker("--dry-run"), pinned)
        self.assertEqual(calls, [])
        self.assertIn("would:", err2)
        self.assertNotIn("is in AllowUsers", err2)

    def test_finish_runs_the_step_for_an_agent_after_the_toolchains_and_never_for_a_human(self):
        for human in (False, True):
            order: list[str] = []
            w = self.worker(human=human)
            with mock.patch.object(worker, "record_launch_provider", lambda w: order.append("record")), \
                    mock.patch.object(worker, "bootstrap_and_bind", lambda w: order.append("bootstrap")), \
                    mock.patch.object(worker, "toolchains", lambda w: order.append("toolchains")), \
                    mock.patch.object(worker, "operator_ssh", lambda w: order.append("ssh")), \
                    mock.patch.object(worker, "verify", lambda w: order.append("verify") or 0), redirect_stderr(io.StringIO()):
                w.a = wa.parse_args(["finish", LOGIN, *(["--human"] if human else ["backend-dev", "--no-claude-account"])])
                worker.finish(w)
            self.assertEqual(order, ["verify"] if human else ["record", "bootstrap", "toolchains", "ssh", "verify"], human)


if __name__ == "__main__":
    unittest.main()
