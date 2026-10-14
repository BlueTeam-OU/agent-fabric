#!/usr/bin/env python3
"""tools/fabric/provisioning/launch_record.py (j125): a new account has its
first launch's provider on record before it launches. The record is read back
by the real consumer, install_agent_files.last_launch_provider; the worker
step is checked on the argument list it runs and on its order before
bootstrap (which installs the agent files for the recorded provider)."""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(HERE, "tools", "fabric")
sys.path.insert(0, TOOLS)
import install_agent_files  # noqa: E402
from provisioning import launch_record as lr, worker, worker_args as wa  # noqa: E402

LOGIN = "zz-unit-login"
SCRIPT = os.path.join(TOOLS, "provisioning", "launch_record.py")


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class Choose(unittest.TestCase):
    def test_a_profile_layer_wins_then_the_claude_account_asked_for_then_nothing(self):
        self.assertEqual(lr.choose("openrouter", "slug=aabbccddeeff", False), "openrouter")
        self.assertEqual(lr.choose("anthropic", "", True), "anthropic")
        self.assertEqual(lr.choose("gateway", "", False), "anthropic", "the gateway is the anthropic column")
        self.assertEqual(lr.choose(None, "slug=aabbccddeeff", False), "anthropic")
        self.assertEqual(lr.choose(None, "", True), "openrouter", "--no-claude-account is the broker path only")
        self.assertIsNone(lr.choose(None, "", False))
        self.assertEqual(lr.choose("bogus", "", True), "openrouter", "a value no column has is no layer")


class Profile(unittest.TestCase):
    def test_the_layers_in_the_order_resume_reads_them_and_the_same_answer_as_resume_on_the_real_file(self):
        with tempfile.TemporaryDirectory(prefix="launch-record.") as d:
            f = os.path.join(d, "profiles.json")
            doc = {"defaults": {"launch_provider": "openrouter"}, "roles": {"r": {"launch_provider": "anthropic"}},
                   "agents": {"a": {"launch_provider": "gateway"}, "b": {"launch_provider": 3}}}
            with open(f, "w") as fh:
                json.dump(doc, fh)
            self.assertEqual(lr.profile_provider(f, "a", "r"), "gateway")
            self.assertEqual(lr.profile_provider(f, "b", "r"), "anthropic", "a layer that names no provider is passed over")
            self.assertEqual(lr.profile_provider(f, "c", "zz"), "openrouter")
            for bad in ("[]", "not json"):
                with open(f, "w") as fh:
                    fh.write(bad)
                self.assertIsNone(lr.profile_provider(f, "a", "r"), bad)
            self.assertIsNone(lr.profile_provider(os.path.join(d, "absent.json"), "a", "r"))
        import resume
        real = os.path.join(HERE, "routing", "profiles.json")
        for login, role in (("python-dev-03", "python-dev"), ("x-01", "python-dev"), ("x-01", None)):
            with mock.patch.dict(os.environ, {"AGENT_FABRIC_RESUME_PROFILES": real}):
                self.assertEqual(lr.profile_provider(real, login, role), resume.profile_provider(login, role), (login, role))


class Record(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="launch-record.")
        self.addCleanup(self.tmp.cleanup)
        self.state = os.path.join(self.tmp.name, "state", "agents", "x")

    def test_the_one_writer_keeps_an_existing_record_and_replaces_it_otherwise(self):
        import launch_provider_record as rec

        class launch:   # the name the cases below were written against
            record_launch_provider = staticmethod(rec.write)
        self.assertTrue(launch.record_launch_provider(self.state, "openrouter", keep_existing=True))
        path = os.path.join(self.state, "launch-provider.json")
        self.assertEqual(sorted(load(path)), ["at", "provider"])
        with mock.patch.dict(os.environ, {"AGENT_FABRIC_STATE_DIR": os.path.join(self.tmp.name, "state")}), \
                mock.patch.object(install_agent_files.fabric_writes.pwd, "getpwuid", return_value=mock.Mock(pw_name="x")):
            self.assertEqual(install_agent_files.last_launch_provider(), "openrouter")
        self.assertFalse(launch.record_launch_provider(self.state, "anthropic", keep_existing=True), "the account's own launch is a fact")
        self.assertEqual(load(path)["provider"], "openrouter")
        self.assertEqual(os.listdir(self.state), ["launch-provider.json"], "no temporary file left")
        self.assertTrue(launch.record_launch_provider(self.state, "anthropic"), "a launch's own record still replaces")
        self.assertEqual(load(path)["provider"], "anthropic")

    def test_the_launchers_record_is_that_writer_and_keeps_its_old_behaviour(self):
        import launch
        launch.record_launch_provider(self.state, "anthropic", "gateway")
        doc = load(os.path.join(self.state, "launch-provider.json"))
        self.assertEqual((doc["provider"], doc["transport"]), ("anthropic", "gateway"))
        launch.record_launch_provider(self.state, "openrouter")
        self.assertEqual(load(os.path.join(self.state, "launch-provider.json"))["provider"], "openrouter")
        self.assertNotIn("transport", load(os.path.join(self.state, "launch-provider.json")))

    def test_the_entry_takes_one_known_provider_and_writes_in_the_state_dir_the_account_has(self):
        env = {"PATH": os.environ["PATH"], "AGENT_FABRIC_STATE_DIR": os.path.join(self.tmp.name, "s"), "HOME": self.tmp.name}
        bad = subprocess.run([sys.executable, "-I", SCRIPT, "gateway"], env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual((bad.returncode, bad.stdout), (2, ""))
        self.assertIn("usage", bad.stderr)
        ok = subprocess.run([sys.executable, "-I", SCRIPT, "anthropic"], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        found = [os.path.join(d, f) for d, _, fs in os.walk(env["AGENT_FABRIC_STATE_DIR"]) for f in fs]
        self.assertEqual([os.path.basename(f) for f in found], ["launch-provider.json"])
        again = subprocess.run([sys.executable, "-I", SCRIPT, "openrouter"], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(again.returncode, 0)
        self.assertIn("kept", again.stderr)
        self.assertEqual(load(found[0])["provider"], "anthropic")

    def test_a_state_dir_that_cannot_be_written_is_a_failure_not_a_kept_record(self):
        blocker = os.path.join(self.tmp.name, "file")
        open(blocker, "w").close()
        env = {"PATH": os.environ["PATH"], "AGENT_FABRIC_STATE_DIR": blocker, "HOME": self.tmp.name}
        got = subprocess.run([sys.executable, "-I", SCRIPT, "anthropic"], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(got.returncode, 1, got.stderr)
        self.assertNotIn("kept", got.stderr)


class Step(unittest.TestCase):
    def worker(self, *argv: str, human: bool = False) -> worker.Worker:
        who = ["--human"] if human else ["backend-dev"]
        w = worker.Worker(wa.parse_args(["finish", LOGIN, *who, *argv]), root=HERE, env={})
        w.home = f"/home/{LOGIN}"
        return w

    def run_step(self, w, profile=None):
        calls, err = [], io.StringIO()

        def fake(argv, **kw):
            calls.append(list(argv))
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        with mock.patch.object(subprocess, "run", fake), mock.patch.object(lr, "profile_provider", return_value=profile), \
                redirect_stderr(err):
            worker.record_launch_provider(w)
        return calls, err.getvalue()

    def test_the_step_runs_the_recorder_as_the_account_on_the_pinned_python(self):
        calls, err = self.run_step(self.worker("--claude-account", "slug=aabbccddeeff"))
        self.assertEqual(len(calls), 1, calls)
        account_copy = os.path.join(f"/home/{LOGIN}", "projects", "agent-fabric", "tools", "fabric", "provisioning", "launch_record.py")
        self.assertIn(["-I", account_copy, "anthropic"], [calls[0][i:i + 3] for i in range(len(calls[0]) - 2)],
                      "run from the account's own clone: it cannot read the worker's checkout (homes are 700)")
        self.assertIn("-u", calls[0])
        self.assertIn(LOGIN, calls[0])
        self.assertIn("6b. first launch on anthropic recorded", err)

    def test_a_profile_layer_outranks_the_account_and_a_dry_run_runs_nothing(self):
        calls, _ = self.run_step(self.worker("--claude-account", "slug=aabbccddeeff"), profile="openrouter")
        self.assertEqual(calls[0][-1], "openrouter")
        calls, err = self.run_step(self.worker("--no-claude-account", "--dry-run"))
        self.assertEqual(calls, [])
        self.assertIn("would: as zz-unit-login: launch_record.py openrouter", err)

    def test_nothing_to_go_on_is_said_and_records_nothing(self):
        calls, err = self.run_step(self.worker())
        self.assertEqual(calls, [])
        self.assertIn("no launch provider recorded", err)

    def test_a_recorder_that_fails_stops_the_run(self):
        w = self.worker("--no-claude-account")
        with mock.patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 1, stdout="boom\n", stderr="")), \
                mock.patch.object(lr, "profile_provider", return_value=None), redirect_stderr(io.StringIO()):
            with self.assertRaises(worker.Stop):
                worker.record_launch_provider(w)

    def test_finish_records_before_bootstrap_for_an_agent_and_never_for_a_human(self):
        order = []
        for human in (False, True):
            order.clear()
            w = self.worker(human=human)
            with mock.patch.object(worker, "record_launch_provider", lambda w: order.append("record")), \
                    mock.patch.object(worker, "bootstrap_and_bind", lambda w: order.append("bootstrap")), \
                    mock.patch.object(worker, "toolchains", lambda w: order.append("toolchains")), \
                    mock.patch.object(worker, "verify", lambda w: 0), redirect_stderr(io.StringIO()):
                w.a = wa.parse_args(["finish", LOGIN, *(["--human"] if human else ["backend-dev", "--no-claude-account"]), "--dry-run"])
                worker.finish(w)
            self.assertEqual(order, [] if human else ["record", "bootstrap", "toolchains"], human)


if __name__ == "__main__":
    unittest.main()
