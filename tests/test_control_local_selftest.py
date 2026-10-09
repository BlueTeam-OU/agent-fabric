#!/usr/bin/env python3
"""The `local` and `local-prune` ops (control/local.py) and the `secrets-selftest`
action (control/selftest.py): ports of runtime/control/tests/local.test.mjs
and selftest.test.mjs, case for case, less what belongs to the files that
own it: agentd's answer(), the signed-action tables (sign.mjs) and
fabric-ctl's rendering and argument parsing run in their own suites, and move
with their own ports. `local` goes through the real tools/fabric/local_settings.py
against a scratch home; the self-test through a fake fabric-secrets in a
scratch root."""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import local as L, ops, selftest as S  # noqa: E402

VALUE = "planted-value-never-reported"
STEPS = ["precondition", "set", "run", "rm", "absent"]
PASSING = {"status": "pass", "name": "AF_SELFTEST_CANARY", "steps": [{"step": s, "ok": True, "reason": ""} for s in STEPS]}


class Base(unittest.TestCase):
    def scratch(self, prefix: str) -> str:
        t = tempfile.TemporaryDirectory(prefix=prefix)
        self.addCleanup(t.cleanup)
        return t.name


class Local(Base):
    def home(self):
        h = self.scratch("local-home-")
        cfg = os.path.join(h, ".config", "agent-fabric")
        os.makedirs(cfg)
        with open(os.path.join(cfg, "secrets.env"), "w", encoding="utf-8") as fh:
            fh.write(f"# agent-fabric secrets\nexport OPENAI_API_KEY='{VALUE}'\nexport DEMO_PORT_OFFSET=640\n")
        with open(os.path.join(cfg, "env.sh"), "w", encoding="utf-8") as fh:
            fh.write("# agent-fabric secrets\nexport DEMO_PORT_OFFSET=640\n")

        def put(wc, doc, mode=0o600):
            f = os.path.join(h, "projects", wc, ".claude", "settings.local.json")
            os.makedirs(os.path.dirname(f))
            with open(f, "w", encoding="utf-8") as fh:
                fh.write(doc if isinstance(doc, str) else json.dumps(doc, indent=2))
            os.chmod(f, mode)
            return f
        return h, put

    def test_local_is_an_operator_read_local_prune_a_signed_action_neither_is_public(self):
        self.assertTrue("local" in ops.OPS and "local-prune" in ops.OPS)
        self.assertFalse("local" in ops.PUBLIC_OPS or "local-prune" in ops.PUBLIC_OPS)

    def test_local_reports_names_and_counts_per_working_copy_never_a_value(self):
        h, put = self.home()
        put("alpha", {"env": {"CLAUDE_BRIDGE_AUTH_TOKEN": VALUE, "DEMO_PORT_OFFSET": "640", "MY_FLAG": "1"},
                      "permissions": {"allow": ["Bash(ls)", "Read"], "deny": ["Bash(rm)"]}, "enableAllProjectMcpServers": True})
        put("beta", {})
        put("gamma", "{not json")
        os.makedirs(os.path.join(h, "projects", "delta"))   # no settings file: not listed
        r = L.local(home=h, root=HERE)
        self.assertEqual(r["status"], "ok")
        self.assertEqual([f["working_copy"] for f in r["files"]], ["alpha", "beta", "gamma"])
        a, b, g = r["files"]
        self.assertEqual(a["env"], ["CLAUDE_BRIDGE_AUTH_TOKEN", "DEMO_PORT_OFFSET", "MY_FLAG"])
        self.assertEqual(a["secrets"], ["CLAUDE_BRIDGE_AUTH_TOKEN"])
        self.assertEqual(a["permissions"], {"allow": 2, "deny": 1, "ask": 0})
        self.assertEqual(a["keys"], ["enableAllProjectMcpServers"])
        self.assertEqual([b["env"], b["secrets"]], [[], []])
        self.assertEqual(g["status"], "not json")
        self.assertNotIn(VALUE, json.dumps(r), "no value in the report")

    def test_local_prune_runs_the_tool_and_takes_no_arguments(self):
        h, put = self.home()
        f = put("alpha", {"env": {"GH_TOKEN": VALUE, "MY_FLAG": "1"}})
        r = L.local_prune({"from": "h/op", "to": ["h/a"]}, home=h, root=HERE)
        self.assertEqual(r["status"], "pruned", r)
        with open(f, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {"env": {"MY_FLAG": "1"}})
        self.assertNotIn(VALUE, json.dumps(r))
        ran = []
        refused = L.local_prune({"args": {"all": True}}, home=h, root=HERE, run=lambda *a, **k: ran.append(1))
        self.assertEqual(refused, {"status": "refused", "reason": "local-prune takes no arguments"})
        self.assertEqual(ran, [])
        for args in (None, [], "x", 0):
            self.assertEqual(L.local_prune({"args": args}, home=h, root=HERE, run=lambda *a, **k: ran.append(1))["status"], "refused", args)
        self.assertEqual(ran, [])
        self.assertTrue(L.takes_no_arguments({}) and L.takes_no_arguments({"args": {}}), "absent or empty: nothing")

    def test_a_tool_that_fails_is_a_failed_reply_with_its_last_line(self):
        def failing(cmd, **kw):
            self.assertTrue(kw["timeout"] and kw["check"], "bounded and checked")
            raise subprocess.CalledProcessError(2, cmd, "", "first\nlocal_settings: cannot read settings (EACCES)\n")
        r = L.local_prune({}, home="/h", root="/r", run=failing)
        self.assertEqual(r, {"status": "failed", "reason": "local_settings: cannot read settings (EACCES)"})

        def gone(cmd, **kw):
            raise FileNotFoundError(2, "No such file", cmd[0])
        self.assertEqual(L.local_prune({}, home="/h", root="/r", run=gone)["status"], "failed")

        def slow(cmd, **kw):   # TimeoutExpired.stderr is bytes even where the run asked for text
            raise subprocess.TimeoutExpired(cmd, 15, output=b"", stderr=b"working\nlocal_settings: still reading\n")
        self.assertEqual(L.local_prune({}, home="/h", root="/r", run=slow), {"status": "failed", "reason": "local_settings: still reading"})

        def not_json(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 0, "not json", "")
        self.assertEqual(L.local_prune({}, home="/h", root="/r", run=not_json)["status"], "failed", "output that is not JSON is a failure, not an invented ok")


def fake_root(test: Base, report, code: int = 0, stderr: str = "") -> str:
    """A root whose bin/fabric-secrets prints REPORT and exits CODE, recording its argv."""
    root = test.scratch("selftest-root-")
    os.makedirs(os.path.join(root, "bin"))
    binary = os.path.join(root, "bin", "fabric-secrets")
    body = report if isinstance(report, str) else json.dumps(report)
    err = f"echo '{stderr}' >&2\n" if stderr else ""
    with open(binary, "w", encoding="utf-8") as fh:
        fh.write(f"#!/bin/sh\nprintf '%s\\n' \"$*\" > \"{root}/argv\"\ncat <<'EOF'\n{body}\nEOF\n{err}exit {code}\n")
    os.chmod(binary, 0o755 | stat.S_IMODE(os.stat(binary).st_mode))
    return root


class Selftest(Base):
    def once(self, root, request=None):
        return S.secrets_selftest_once(request if request is not None else {}, home="/nonexistent-home", root=root)

    def test_runs_fabric_secrets_selftest_json_and_relays_the_verdict_and_the_steps(self):
        root = fake_root(self, PASSING)
        self.assertEqual(self.once(root), {"status": "pass", "name": "AF_SELFTEST_CANARY", "steps": PASSING["steps"]})
        with open(os.path.join(root, "argv"), encoding="utf-8") as fh:
            self.assertEqual(fh.read().strip(), "selftest --json")

    def test_a_failing_step_is_fail_a_report_that_says_pass_with_a_failed_step_is_not_a_pass(self):
        failing = {**PASSING, "status": "fail", "steps": [{**s, "ok": False, "reason": "the command's environment held another value"} if s["step"] == "run" else s for s in PASSING["steps"]]}
        self.assertEqual(self.once(fake_root(self, failing, 1))["status"], "fail")
        self.assertEqual(self.once(fake_root(self, {**failing, "status": "pass"}, 0))["status"], "fail")
        self.assertEqual(self.once(fake_root(self, {**PASSING, "steps": []}, 0))["status"], "fail", "no steps is no pass")
        self.assertEqual(self.once(fake_root(self, PASSING, 1))["status"], "fail", "exit 1 is never a pass, whatever the report says")

    def test_no_report_or_an_exit_that_is_neither_pass_nor_fail_is_failed_with_the_reason_nothing_invented(self):
        r = self.once(fake_root(self, "not json", 1, "fabric-secrets: the store could not be read"))
        self.assertEqual(r, {"status": "failed", "reason": "fabric-secrets: the store could not be read"})
        self.assertEqual(self.once(fake_root(self, PASSING, 127))["status"], "failed")
        r3 = self.once(self.scratch("selftest-empty-"))
        self.assertEqual(r3["status"], "failed", "no fabric-secrets at all")
        self.assertIn("ENOENT", r3["reason"])

    def test_only_step_ok_and_reason_are_relayed_each_bounded(self):
        noisy = {**PASSING, "extra": "x", "steps": [{**s, "value": "should-not-pass", "reason": "r" * 500} for s in PASSING["steps"]]}
        r = self.once(fake_root(self, noisy))
        self.assertTrue("should-not-pass" not in json.dumps(r) and "extra" not in r)
        self.assertTrue(all(list(s) == ["step", "ok", "reason"] and len(s["reason"]) == 200 for s in r["steps"]))

    def test_a_hostile_report_still_gets_a_reply(self):
        evil = {"status": "pass", "name": {"toString": 1}, "steps": [{"step": {"toString": 1}, "ok": True, "reason": {"toString": 1}}]}
        self.assertEqual(self.once(fake_root(self, evil)), {"status": "pass", "name": "", "steps": [{"step": "?", "ok": True, "reason": ""}]})
        self.assertEqual(len(self.once(fake_root(self, {**PASSING, "name": "N" * 100000}))["name"]), 64)
        many = self.once(fake_root(self, {**PASSING, "steps": [PASSING["steps"][0]] * 17}))
        self.assertEqual(many["status"], "failed")
        self.assertRegex(many["reason"], r"17 steps, more than 16")
        for odd in ([], "x", 3, None, [1, "a", None]):
            self.assertIn(self.once(fake_root(self, {**PASSING, "steps": odd}))["status"], ("fail", "failed"), odd)
        self.assertEqual(self.once(fake_root(self, [1, 2]))["status"], "failed", "a report that is not an object")
        self.assertEqual(self.once(fake_root(self, "null"))["status"], "failed")
        self.assertEqual(self.once(fake_root(self, {"status": "pass", "steps": [{"step": "s", "ok": "true"}]}))["steps"][0]["ok"], False, "ok is true or it is not")

    def test_it_takes_no_arguments_and_runs_nothing_when_given_some(self):
        root = fake_root(self, PASSING)
        self.assertEqual(self.once(root, {"args": {"name": "X"}}), {"status": "refused", "reason": "secrets-selftest takes no arguments"})
        self.assertFalse(os.path.exists(os.path.join(root, "argv")))
        self.assertEqual(self.once(root, {"args": {}})["status"], "pass")

    def test_a_timeout_and_a_signal_are_failed_not_fail(self):
        def slow(cmd, **kw):
            self.assertEqual(kw["timeout"], S.SELFTEST_TIMEOUT_MS / 1000)
            raise subprocess.TimeoutExpired(cmd, kw["timeout"])
        r = S.secrets_selftest_once({}, home="/h", root="/r", run=slow)
        self.assertEqual(r, {"status": "failed", "reason": "fabric-secrets selftest: timed out after 450 s"})

        def killed(cmd, **kw):
            raise subprocess.CalledProcessError(-9, cmd, b"", b"")
        self.assertEqual(S.secrets_selftest_once({}, home="/h", root="/r", run=killed)["status"], "failed")
        self.assertTrue(S.SELFTEST_BUDGET_S > S.SELFTEST_TIMEOUT_MS / 1000, "fabric-ctl waits past the daemon's own bound")

    def test_one_at_a_time_per_daemon_a_second_while_one_runs_is_busy(self):
        started, gate = threading.Event(), threading.Event()

        def run_slow(cmd, **kw):
            started.set()
            gate.wait(10)
            return subprocess.CompletedProcess(cmd, 0, json.dumps(PASSING).encode(), b"")
        ran_again = []

        def run_again(cmd, **kw):
            ran_again.append(1)
            return subprocess.CompletedProcess(cmd, 0, json.dumps(PASSING).encode(), b"")
        out: list = []
        t = threading.Thread(target=lambda: out.append(S.secrets_selftest({}, home="/h", root="/nowhere", run=run_slow)))
        t.start()
        self.assertTrue(started.wait(10))
        self.assertEqual(S.secrets_selftest({}, home="/h", root="/nowhere", run=run_again), {"status": "busy", "note": "a secrets-selftest is already running on this account"})
        self.assertEqual(ran_again, [], "the second ran nothing")
        gate.set()
        t.join(10)
        self.assertEqual(out[0]["status"], "pass")
        self.assertEqual(S.secrets_selftest({}, home="/h", root="/nowhere", run=run_again)["status"], "pass", "free again once it ended")


if __name__ == "__main__":
    unittest.main()
