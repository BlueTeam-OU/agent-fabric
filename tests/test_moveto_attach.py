#!/usr/bin/env python3
"""moveto's attach: `moveto --help` lists --attach, and `enter … --attach` / enter-ssh's `attach`
draw the terminal of the account's harness pane, held by its own FleetDeck server
(agent-fabric-harness.service). The binary is a fake script that logs its argv and answers like
the real CLI's JSON; it is reached by rewriting the module's one FLEETDECK line in a copy, as
test_enter_ssh.py rewrites the owner uid. The attach never starts a server: the log shows which
calls a refusal made."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOVETO_DIR = os.path.join(HERE, "runtime", "provisioning", "moveto")
sys.path.insert(0, MOVETO_DIR)
import moveto  # noqa: E402

FAKE = """#!{python}
import json, os, sys
a = sys.argv[1:]
with open(os.environ["FD_LOG"], "a") as fh:
    fh.write(json.dumps(a) + "\\n")
assert a[:2] == ["--session", "harness"], a
mode = os.environ.get("FD_MODE", "ok")
if mode == "down":
    sys.stderr.write("error: no server for session harness\\n")
    sys.exit(1)
cmd = a[2:]
if cmd == ["status", "server", "--json"]:
    print(json.dumps({{"result": {{"running": True}}}} if mode == "wrappedrunning" else {{}} if mode == "norunning" else {{"running": mode != "stopped"}}))
elif cmd == ["workspace", "list"]:
    if mode == "listfails":
        sys.stderr.write("error: socket closed\\n")
        sys.exit(1)
    if mode == "nullresult":
        print(json.dumps({{"result": None}}))
        sys.exit(0)
    ws = [] if mode == "nopane" else [{{"workspace_id": "w1", "label": "harness"}}] * (2 if mode == "twoworkspaces" else 1)
    if mode == "nolabel":
        ws = [{{"workspace_id": "w1", "name": "harness"}}]
    if mode == "junkentry":
        ws = [{{"workspace_id": "w1", "label": "harness"}}, "junk"]
    if mode == "badwsid":
        ws = [{{"workspace_id": "-w", "label": "harness"}}]
    print(json.dumps({{"result": {{"workspaces": ws}}}}))
elif cmd[:2] == ["pane", "list"]:
    panes = [{{"pane_id": "w1:p1", "terminal_id": "term_abc123"}}]
    if mode == "twopanes":
        panes.append({{"pane_id": "w1:p2", "terminal_id": "term_def"}})
    if mode == "noterminal":
        panes = [{{"pane_id": "w1:p1"}}]
    if mode == "hostileid":
        panes = [{{"pane_id": "w1:p1", "terminal_id": "x; id"}}]
    print(json.dumps({{"result": {{"panes": panes}}}}))
elif cmd[:2] == ["terminal", "attach"]:
    print("ATTACHED " + " ".join(cmd[2:]))
    sys.exit(int(os.environ.get("FD_ATTACH_RC", "0")))
else:
    sys.exit(9)
"""


class Attach(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix="mva-")
        self.addCleanup(shutil.rmtree, self.t, True)
        self.fd = os.path.join(self.t, "fleetdeck")
        with open(self.fd, "w") as fh:
            fh.write(FAKE.format(python=sys.executable))
        os.chmod(self.fd, 0o755)
        self.log = os.path.join(self.t, "calls.log")
        self.share = os.path.join(self.t, "share")
        os.makedirs(self.share)
        # An installed copy of moveto.py and enter, with the binary's path pointed at the fake.
        with open(os.path.join(MOVETO_DIR, "moveto.py"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertEqual(text.count('\nFLEETDECK = "/usr/local/bin/agent-fabric-fleetdeck"\n'), 1)
        with open(os.path.join(self.share, "moveto.py"), "w", encoding="utf-8") as fh:
            fh.write(text.replace('\nFLEETDECK = "/usr/local/bin/agent-fabric-fleetdeck"\n', f'\nFLEETDECK = "{self.fd}"\n'))
        shutil.copy2(os.path.join(MOVETO_DIR, "enter"), self.share)
        self.home = os.path.join(self.t, "home")
        os.makedirs(os.path.join(self.home, "projects"))

    def env(self, **extra):
        return {"PATH": "/usr/bin:/bin", "HOME": self.home, "LANG": "C.UTF-8", "AGENT_FABRIC_PYTHON": sys.executable, "FD_LOG": self.log, **extra}

    def calls(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log, encoding="utf-8") as fh:
            return [json.loads(ln)[2:] for ln in fh.read().splitlines()]

    def enter(self, mode="ok", **extra):
        return subprocess.run([os.path.join(self.share, "enter"), os.path.join(self.home, "projects"), "acct", "--attach"], env=self.env(FD_MODE=mode, **extra),
                              capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)

    def test_help_lists_attach_as_a_whole_token_through_the_installed_shim(self):
        r = subprocess.run(["bash", os.path.join(MOVETO_DIR, "moveto"), "--help"], env={"PATH": "/usr/bin:/bin", "AGENT_FABRIC_PYTHON": sys.executable},
                           capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertIn("--attach", r.stdout.split())    # the token the fork gates on (its modes_in), not a substring of another word
        for word in ("--wait", "--resume", "--watch"):
            self.assertIn(word, r.stdout.split())

    def test_enter_attach_becomes_terminal_attach_of_the_harness_panes_terminal(self):
        r = self.enter()
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "ATTACHED term_abc123\n", ""))
        self.assertEqual(self.calls(), [["status", "server", "--json"], ["workspace", "list"], ["pane", "list", "--workspace", "w1"],
                                        ["terminal", "attach", "term_abc123"]])

    def test_the_attachs_exit_status_is_the_commands_not_a_refusals(self):
        self.assertEqual(self.enter(FD_ATTACH_RC="3").returncode, 3)

    def test_no_title_and_no_refresh_are_written_before_the_attach(self):
        r = self.enter()
        self.assertNotIn("\033", r.stdout)
        self.assertNotIn("Enter to activate", r.stdout)

    def test_every_missing_piece_is_one_line_and_exit_1_and_no_server_is_started(self):
        cases = {"down": "no harness server is running", "stopped": "no harness server is running", "nopane": "has no harness pane",
                 "twoworkspaces": "more than one harness workspace", "twopanes": "does not hold exactly one pane",
                 "noterminal": "not an id", "hostileid": "not an id",
                 # An answer not understood is said as that: never "not running" or "no pane".
                 "norunning": "no running field", "wrappedrunning": "no running field", "nullresult": "no result object",
                 "nolabel": "not a list of labelled workspaces", "junkentry": "not a list of labelled workspaces",
                 "badwsid": "not an id", "listfails": "failed `workspace list`: error: socket closed"}
        for mode, why in cases.items():
            os.path.exists(self.log) and os.remove(self.log)
            r = self.enter(mode)
            self.assertEqual((r.returncode, r.stdout), (1, ""), mode)
            self.assertEqual(r.stderr.count("\n"), 1, (mode, r.stderr))
            self.assertRegex(r.stderr, rf"^moveto: .*{why}", mode)
            self.assertNotIn("Traceback", r.stderr)
            if mode not in ("down", "stopped"):
                self.assertNotIn("is running", r.stderr, mode)
            self.assertNotIn(["terminal", "attach"], [c[:2] for c in self.calls()], mode)
            # Only read-only questions were asked: nothing that could start, create or type.
            self.assertTrue(all(c[0] in ("status", "workspace", "pane") and c[1] in ("server", "list") for c in self.calls()), (mode, self.calls()))

    def test_no_binary_names_the_installer_in_one_line(self):
        os.remove(self.fd)
        r = self.enter()
        self.assertEqual((r.returncode, r.stdout), (1, ""))
        self.assertRegex(r.stderr, r"^moveto: no harness unit here: .* is not installed \(tools/fabric/provisioning/install_fleetdeck.py\)\n$")

    def test_attach_in_process_execs_the_binary_with_the_argument_list_and_nothing_via_a_shell(self):
        with mock.patch.object(moveto, "FLEETDECK", self.fd), mock.patch.object(moveto, "harness_terminal", return_value="term_9"), \
                mock.patch.object(moveto.os, "execv", side_effect=SystemExit(0)) as ex, self.assertRaises(SystemExit):
            moveto.attach()
        ex.assert_called_once_with(self.fd, [self.fd, "--session", "harness", "terminal", "attach", "term_9"])

    def test_terminal_ids_are_checked_before_they_reach_an_argv(self):
        for bad in ("x; id", "$(id)", "a b", "", "a\nb", "-x", "--takeover", "ünï"):
            doc = {"result": {"panes": [{"pane_id": "p", "terminal_id": bad}]}}
            calls = iter([{"running": True}, {"result": {"workspaces": [{"workspace_id": "w", "label": "harness"}]}}, doc])
            with mock.patch.object(moveto, "harness_call", side_effect=lambda *a, _c=calls: next(_c)), self.assertRaises(moveto.Refused):
                moveto.harness_terminal()

    def test_enter_ssh_attach_runs_the_same_through_the_forced_command_and_records_the_client(self):
        bindir = os.path.join(self.t, "bin")
        os.makedirs(bindir)
        dst = os.path.join(bindir, "enter-ssh")
        shutil.copy2(os.path.join(MOVETO_DIR, "enter-ssh"), dst)
        subprocess.run(["sed", "-i", f"s/^EXPECTED_OWNER_UID=0$/EXPECTED_OWNER_UID={os.getuid()}/", dst], check=True)
        with open(os.path.join(bindir, "enter-ssh.conf"), "w") as fh:
            fh.write(os.path.join(self.share, "enter") + "\n")
        os.chmod(os.path.join(bindir, "enter-ssh.conf"), 0o644)
        for ok_mode, want_rc in (("ok", 0), ("down", 1)):
            os.path.exists(self.log) and os.remove(self.log)
            with subprocess.Popen([dst], env=self.env(FD_MODE=ok_mode, SSH_ORIGINAL_COMMAND="attach", SSH_CLIENT="192.0.2.9 50000 22"),
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, stdin=subprocess.DEVNULL) as p:
                out, err = p.communicate(timeout=60)
            self.assertEqual(p.returncode, want_rc, (ok_mode, out, err))
            if want_rc == 0:
                self.assertEqual(out, "ATTACHED term_abc123\n")
                state = os.path.join(self.home, ".local", "state", "agent-fabric", "agents")
                recs = [os.path.join(d, f) for d, _, fs in os.walk(state) for f in fs if d.endswith("ssh-clients")]
                # exec keeps the pid through bash -l, enter and the module: the record is keyed by the attach's own.
                self.assertEqual([os.path.basename(r) for r in recs], [str(p.pid)])
            else:
                self.assertEqual(out, "")
                self.assertRegex(err, r"^moveto: no harness server is running")
                self.assertEqual(err.count("\n"), 1)


if __name__ == "__main__":
    unittest.main()
