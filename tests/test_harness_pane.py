#!/usr/bin/env python3
"""tools/fabric/control/harness_pane.py, the harness unit's ExecStartPost step.

A fake FleetDeck server models what the step reads and writes (workspaces, panes,
what each pane runs); the step is driven against it for the three starts the
request names — no pane, a restored pane at a plain shell, a pane already
running — and the pane count is read after each. The real entry point runs once
against a fake `agent-fabric-fleetdeck` script to pin argv, stdout, stderr and
the exit status."""
from __future__ import annotations

import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric", "control"))
import harness_pane as hp  # noqa: E402

SHELL_PID = 4000


class FakeServer:
    """What `agent-fabric-fleetdeck --session harness …` answers. `answers_after` calls fail first (a server not yet
    listening); `panes` maps workspace id to a list of pane dicts {id, running}."""

    def __init__(self, workspaces=(), answers_after=0):
        self.workspaces = {w["workspace_id"]: dict(w) for w in workspaces}
        self.panes = {w["workspace_id"]: [{"pane_id": f"{w['workspace_id']}:p1", "running": w.get("running", False)}] for w in workspaces}
        self.calls, self.typed, self.refuse = [], [], answers_after

    def __call__(self, argv):
        assert argv[:3] == [hp.BINARY, "--session", "harness"], argv
        args = argv[3:]
        self.calls.append(args)
        if self.refuse:
            self.refuse -= 1
            return 1, "", "error: no server for session harness\n"
        if args == ["workspace", "list"]:
            return 0, json.dumps({"id": "x", "result": {"type": "workspace_list", "workspaces": list(self.workspaces.values())}}), ""
        if args[:2] == ["workspace", "create"]:
            n = f"w{len(self.workspaces) + 1}"
            label = args[args.index("--label") + 1]
            self.workspaces[n] = {"workspace_id": n, "label": label, "cwd": args[args.index("--cwd") + 1]}
            self.panes[n] = [{"pane_id": f"{n}:p1", "running": False}]
            return 0, json.dumps({"result": {"workspace": {"workspace_id": n}, "tab": {"tab_id": f"{n}:t1"}, "root_pane": {"pane_id": f"{n}:p1"}}}), ""
        if args[:2] == ["pane", "list"]:
            return 0, json.dumps({"result": {"panes": [{"pane_id": p["pane_id"], "workspace_id": args[3]} for p in self.panes[args[3]]]}}), ""
        if args[:2] == ["pane", "process-info"]:
            pane = next(p for ps in self.panes.values() for p in ps if p["pane_id"] == args[2])
            procs = [{"pid": SHELL_PID, "name": "bash", "argv": ["bash"]}]
            if pane["running"]:
                procs = [{"pid": SHELL_PID + 1, "name": "python", "argv": ["fabric-python", "-I", "/usr/local/share/moveto/moveto.py", "--enter"]}]
            return 0, json.dumps({"result": {"process_info": {"shell_pid": SHELL_PID, "foreground_pgid": 1, "foreground_processes": procs}}}), ""
        if args[:2] == ["pane", "run"]:
            self.typed.append((args[2], args[3]))
            next(p for ps in self.panes.values() for p in ps if p["pane_id"] == args[2])["running"] = True
            return 0, "{}", ""
        raise AssertionError(args)

    def pane_count(self):
        return sum(len(p) for p in self.panes.values())


def ensure(server, home="/home/a", login="a"):
    t = [0.0]
    def sleep(s):
        t[0] += s
    return hp.ensure(hp.Deck(server), login, home, clock=lambda: t[0], sleep=sleep)


class Ensure(unittest.TestCase):
    def test_no_pane_creates_one_labelled_workspace_and_runs_enter_wait_in_it(self):
        s = FakeServer()
        said = ensure(s)
        self.assertEqual(s.pane_count(), 1)
        self.assertEqual(list(s.workspaces.values())[0]["label"], "harness")
        create = [c for c in s.calls if c[:2] == ["workspace", "create"]][0]
        self.assertEqual(create, ["workspace", "create", "--label", "harness", "--cwd", "/home/a/projects", "--no-focus"])
        self.assertEqual(s.typed, [("w1:p1", "/usr/local/share/moveto/enter /home/a/projects a --wait")])
        self.assertIn("opened", said)

    def test_a_restored_pane_at_a_plain_shell_gets_enter_again_and_no_second_pane(self):
        s = FakeServer([{"workspace_id": "w7", "label": "harness"}])
        said = ensure(s)
        self.assertEqual(s.pane_count(), 1)
        self.assertEqual([c for c in s.calls if c[:2] == ["workspace", "create"]], [])
        self.assertEqual(s.typed, [("w7:p1", "/usr/local/share/moveto/enter /home/a/projects a --wait")])
        self.assertIn("again", said)

    def test_a_pane_already_running_a_program_is_left_alone(self):
        s = FakeServer([{"workspace_id": "w7", "label": "harness", "running": True}])
        said = ensure(s)
        self.assertEqual((s.pane_count(), s.typed), (1, []))
        self.assertEqual([c for c in s.calls if c[:2] == ["workspace", "create"]], [])
        self.assertIn("already running", said)

    def test_running_the_step_twice_is_one_pane_and_enter_once(self):
        s = FakeServer()
        ensure(s)
        ensure(s)
        self.assertEqual((s.pane_count(), len(s.typed)), (1, 1))

    def test_other_workspaces_are_not_ours_and_two_labelled_ones_are_refused(self):
        s = FakeServer([{"workspace_id": "w1", "label": "other"}])
        ensure(s)
        self.assertEqual(s.pane_count(), 2)
        s = FakeServer([{"workspace_id": "w1", "label": "harness"}, {"workspace_id": "w2", "label": "harness"}])
        with self.assertRaisesRegex(hp.Failed, "2 workspaces are labelled harness"):
            ensure(s)
        self.assertEqual(s.typed, [])

    def test_a_workspace_with_other_than_one_pane_is_refused_not_chosen(self):
        s = FakeServer([{"workspace_id": "w1", "label": "harness"}])
        s.panes["w1"].append({"pane_id": "w1:p2", "running": False})
        with self.assertRaisesRegex(hp.Failed, "2 panes, not one"):
            ensure(s)
        s.panes["w1"] = []
        with self.assertRaisesRegex(hp.Failed, "0 panes, not one"):
            ensure(s)
        self.assertEqual(s.typed, [])

    def test_a_server_that_answers_late_is_waited_for_with_the_clock_not_a_sleep(self):
        s = FakeServer(answers_after=3)
        slept = []
        t = [0.0]
        hp.ensure(hp.Deck(s), "a", "/home/a", clock=lambda: t[0], sleep=lambda x: (slept.append(x), t.__setitem__(0, t[0] + x)))
        self.assertEqual(slept, [hp.POLL_S] * 3)
        self.assertEqual(len(s.typed), 1)

    def test_a_server_that_never_answers_is_an_error_naming_the_wait(self):
        s = FakeServer(answers_after=10 ** 6)
        with self.assertRaisesRegex(hp.Failed, rf"did not answer within {hp.WAIT_S} s"):
            ensure(s)
        self.assertEqual(s.typed, [])

    def test_a_shape_that_is_not_understood_is_a_failure_never_a_default(self):
        class Odd(FakeServer):
            def __init__(self, patch, *a):
                super().__init__(*a)
                self.patch = patch
            def __call__(self, argv):
                for key, answer in self.patch.items():
                    if argv[3:5] == list(key):
                        return answer
                return super().__call__(argv)
        ws = [{"workspace_id": "w1", "label": "harness"}]
        for key, answer, why in ((("workspace", "list"), (0, "not json", ""), "not JSON"),
                                 (("workspace", "list"), (0, json.dumps({"workspaces": []}), ""), "no result object"),
                                 (("workspace", "list"), (0, json.dumps({"result": {}}), ""), "no workspaces"),
                                 (("pane", "list"), (0, json.dumps({"result": {}}), ""), "no panes"),
                                 (("pane", "process-info"), (0, json.dumps({"result": {"process_info": {"shell_pid": 1, "foreground_processes": []}}}), ""), "no shell pid or no foreground"),
                                 (("pane", "process-info"), (0, json.dumps({"result": {"process_info": {"foreground_processes": [{"pid": 2}]}}}), ""), "no process_info.shell_pid"),
                                 (("pane", "process-info"), (1, "", "boom\n"), "boom")):
            s = Odd({key: answer}, ws)
            with self.assertRaisesRegex(hp.Failed, why):
                hp.ensure(hp.Deck(s), "a", "/home/a", clock=lambda: 0.0, sleep=lambda x: None) if key != ("workspace", "list") else ensure(s)
            self.assertEqual(s.typed, [], why)

    def test_the_typed_line_is_quoted_for_the_panes_shell(self):
        s = FakeServer()
        ensure(s, home="/home/we ird$(id)", login="a")
        self.assertEqual(s.typed[0][1], "/usr/local/share/moveto/enter '/home/we ird$(id)/projects' a --wait")


class EntryPoint(unittest.TestCase):
    def fake_binary(self, script):
        d = tempfile.mkdtemp(prefix="hp-")
        self.addCleanup(__import__("shutil").rmtree, d, True)
        path = os.path.join(d, "fleetdeck")
        with open(path, "w") as fh:
            fh.write(script)
        os.chmod(path, 0o755)
        return d, path

    def test_main_prints_one_line_and_exits_0_through_the_real_subprocess_path(self):
        d, path = self.fake_binary("#!" + sys.executable + """
import json, os, sys
a = sys.argv[1:]
assert a[:2] == ["--session", "harness"], a
if a[2:4] == ["workspace", "list"]:
    print(json.dumps({"result": {"workspaces": []}}))
elif a[2:4] == ["workspace", "create"]:
    print(json.dumps({"result": {"root_pane": {"pane_id": "w1:p1"}}}))
elif a[2:4] == ["pane", "run"]:
    open(os.environ["HP_LOG"], "w").write(json.dumps(a))
    print("{}")
else:
    sys.exit(7)
""")
        log = os.path.join(os.path.dirname(path), "log")
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(hp, "BINARY", path), mock.patch.dict(os.environ, {"HP_LOG": log}), redirect_stdout(out), redirect_stderr(err):
            rc = hp.main(["ensure"])
        self.assertEqual((rc, err.getvalue()), (0, ""), out.getvalue())
        self.assertEqual(out.getvalue(), "opened the harness pane w1:p1\n")
        with open(log) as fh:
            typed = json.load(fh)
        self.assertEqual(typed[:5], ["--session", "harness", "pane", "run", "w1:p1"])
        self.assertTrue(typed[-1].startswith(hp.ENTER) and typed[-1].endswith(" --wait"))

    def test_a_missing_binary_is_one_line_exit_1_and_no_traceback(self):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(hp, "BINARY", "/nonexistent/agent-fabric-fleetdeck"), mock.patch.object(hp, "WAIT_S", 0), redirect_stdout(out), redirect_stderr(err):
            rc = hp.main(["ensure"])
        self.assertEqual((rc, out.getvalue()), (1, ""))
        self.assertTrue(err.getvalue().startswith("harness_pane: ") and err.getvalue().count("\n") == 1 and "Traceback" not in err.getvalue(), err.getvalue())

    def test_any_other_argv_is_a_usage_line_and_exit_2(self):
        for argv in ([], ["ensure", "x"], ["stop"]):
            err = io.StringIO()
            with redirect_stderr(err):
                self.assertEqual(hp.main(argv), 2)
            self.assertIn("usage", err.getvalue())


if __name__ == "__main__":
    unittest.main()
