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
import pwd
import re
import select
import shlex
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

    def __init__(self, workspaces=(), answers_after=0, startup=(), typed_lost=False):
        """`startup`: the non-shell foreground pids of the first process-info reads, one set per read (a shell still
        sourcing its profile), before the pane's own state answers; `typed_lost`: a `pane run` that never arrives."""
        self.workspaces = {w["workspace_id"]: dict(w) for w in workspaces}
        self.panes = {w["workspace_id"]: [{"pane_id": f"{w['workspace_id']}:p1", "running": w.get("running", False)}] for w in workspaces}
        self.calls, self.typed, self.refuse = [], [], answers_after
        self.startup, self.typed_lost = list(startup), typed_lost

    def __call__(self, argv, timeout):
        assert 0 < timeout <= hp.CALL_TIMEOUT_S, timeout
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
            # The fork refuses a positional pane id (live, 0.10.0): `--pane <ID>` only.
            if args[2] != "--pane" or len(args) != 4:
                return 2, "", f"error: unknown option: {args[2]}\n"
            pane = next(p for ps in self.panes.values() for p in ps if p["pane_id"] == args[3])
            procs = [{"pid": SHELL_PID, "name": "bash", "argv": ["bash"]}]
            if self.startup:
                procs += [{"pid": pid, "name": "grepconf.sh", "argv": ["/usr/bin/sh", "/usr/libexec/grepconf.sh", "-c"]} for pid in self.startup.pop(0)]
            elif pane["running"]:
                procs = [{"pid": SHELL_PID + 1, "name": "python", "argv": ["fabric-python", "-I", "/usr/local/share/moveto/moveto.py", "--enter"]}]
            return 0, json.dumps({"result": {"process_info": {"shell_pid": SHELL_PID, "foreground_pgid": 1, "foreground_processes": procs}}}), ""
        if args[:2] == ["pane", "run"]:
            self.typed.append((args[2], args[3]))
            if not self.typed_lost:
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
        first = [i for i, c in enumerate(s.calls) if c == ["workspace", "list"]]
        self.assertEqual(first, [0, 1, 2, 3])    # three refused, then the answer: one poll's sleep between each
        self.assertEqual(set(slept), {hp.POLL_S})
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
            def __call__(self, argv, timeout):
                for key, answer in self.patch.items():
                    if argv[3:5] == list(key):
                        return answer
                return super().__call__(argv, timeout)
        ws = [{"workspace_id": "w1", "label": "harness"}]
        for key, answer, why in ((("workspace", "list"), (0, "not json", ""), "not JSON"),
                                 (("workspace", "list"), (0, json.dumps({"workspaces": []}), ""), "no result object"),
                                 (("workspace", "list"), (0, json.dumps({"result": {}}), ""), "no workspaces"),
                                 (("pane", "list"), (0, json.dumps({"result": {}}), ""), "no panes"),
                                 (("pane", "process-info"), (0, json.dumps({"result": {"process_info": {"shell_pid": 1, "foreground_processes": []}}}), ""), "no shell pid or no foreground"),
                                 (("pane", "process-info"), (0, json.dumps({"result": {"process_info": {"foreground_processes": [{"pid": 2}]}}}), ""), "no process_info.shell_pid"),
                                 (("pane", "process-info"), (1, "", "boom\n"), "boom"),
                                 # A listing that does not name the label is not a listing with no harness workspace.
                                 (("workspace", "list"), (0, json.dumps({"result": {"workspaces": [{"workspace_id": "w1", "name": "harness"}]}}), ""), "not an object with a label"),
                                 (("workspace", "list"), (0, json.dumps({"result": {"workspaces": [{"workspace_id": "w1", "label": "harness"}, "junk"]}}), ""), "not an object with a label"),
                                 (("workspace", "list"), (0, json.dumps({"result": {"workspaces": [{"workspace_id": "-w", "label": "harness"}]}}), ""), "not a plain id"),
                                 (("pane", "list"), (0, json.dumps({"result": {"panes": [{"pane_id": "-x", "terminal_id": "t"}]}}), ""), "not a plain id")):
            s = Odd({key: answer}, ws)
            with self.assertRaisesRegex(hp.Failed, why):
                hp.ensure(hp.Deck(s), "a", "/home/a", clock=lambda: 0.0, sleep=lambda x: None) if key != ("workspace", "list") else ensure(s)
            self.assertEqual(s.typed, [], why)
            self.assertEqual(len(s.workspaces), 1, why)    # none created

    def test_a_restored_shell_still_sourcing_its_profile_is_waited_out_then_given_enter(self):
        # Measured 2026-10-31: a restored pane's foreground held flatpak, grepconf.sh or readlink for a moment, each a
        # new pid; read as "running a program", 5 of 12 panes were left at a bare shell and the deck pressed nothing.
        s = FakeServer([{"workspace_id": "w7", "label": "harness"}], startup=[{5001}, {5002, 5003}, {5004}])
        said = ensure(s)
        self.assertEqual(s.typed, [("w7:p1", "/usr/local/share/moveto/enter /home/a/projects a --wait")])
        self.assertIn("again", said)

    def test_a_foreground_that_only_churns_is_an_error_and_nothing_is_typed(self):
        churn = [{6000 + i} for i in range(int(hp.STARTUP_S / hp.POLL_S) + 5)]
        s = FakeServer([{"workspace_id": "w7", "label": "harness"}], startup=churn)
        with self.assertRaisesRegex(hp.Failed, rf"no program that stays in its foreground after {hp.STARTUP_S:g} s"):
            ensure(s)
        self.assertEqual(s.typed, [])

    def test_a_pane_just_made_is_typed_into_once_its_profile_child_leaves_however_long_it_stayed(self):
        # Round 1 F1: a profile child that outlasts SETTLE_S in a pane this step made is not a running program.
        stays = int(hp.SETTLE_S / hp.POLL_S) + 3
        s = FakeServer(startup=[{9001}] * stays)
        self.assertIn("opened", ensure(s))
        self.assertEqual(s.typed, [("w1:p1", "/usr/local/share/moveto/enter /home/a/projects a --wait")])

    def test_a_pane_just_made_that_never_comes_to_its_shell_is_an_error_and_nothing_is_typed(self):
        s = FakeServer(startup=[{9001}] * (int(hp.STARTUP_S / hp.POLL_S) + 5))
        with self.assertRaisesRegex(hp.Failed, rf"has not come to its shell after {hp.STARTUP_S:g} s"):
            ensure(s)
        self.assertEqual((s.typed, s.pane_count()), ([], 1))

    def test_a_program_that_stays_for_the_settle_window_is_a_running_one(self):
        # Positive control for the waiting-out above: the same pid read across SETTLE_S is never typed over.
        s = FakeServer([{"workspace_id": "w7", "label": "harness"}], startup=[{7000}] * (int(hp.SETTLE_S / hp.POLL_S) + 1))
        self.assertIn("already running", ensure(s))
        self.assertEqual(s.typed, [])

    def test_a_line_that_never_starts_enter_fails_the_step_and_is_not_typed_twice(self):
        # The unit's Restart=on-failure is the retry: a second line could land at enter's prompt as the activating Enter.
        for ws in ((), ({"workspace_id": "w7", "label": "harness"},)):
            s = FakeServer(ws, typed_lost=True)
            with self.assertRaisesRegex(hp.Failed, rf"is still at its shell after {hp.READBACK_S:g} s"):
                ensure(s)
            self.assertEqual(len(s.typed), 1)

    def test_the_step_ends_within_its_budget_however_slow_the_calls(self):
        # Round 1 F2: systemd's default TimeoutStartSec (90 s) bounds the step as a whole, slow calls included. A call
        # given less time than it takes times out at that time, as real_run's subprocess timeout does.
        self.assertLess(hp.STEP_S + hp.POLL_S, 90)
        for latency in (0.2, 5, 14, 20):
            for ws, kw in (((), {"typed_lost": True}), (({"workspace_id": "w7", "label": "harness"},), {"typed_lost": True, "answers_after": 2}),
                           (({"workspace_id": "w7", "label": "harness"},), {"startup": [{6000 + i} for i in range(200)]})):
                t = [0.0]
                class Slow(FakeServer):
                    def __call__(self, argv, timeout):
                        if latency > timeout:
                            t[0] += timeout
                            raise hp.Failed("no answer")
                        t[0] += latency
                        return super().__call__(argv, timeout)
                s = Slow(ws, **kw)
                with self.assertRaises(hp.Failed):
                    hp.ensure(hp.Deck(s), "a", "/home/a", clock=lambda: t[0], sleep=lambda x: t.__setitem__(0, t[0] + x))
                self.assertLessEqual(t[0], hp.STEP_S + hp.POLL_S, (latency, kw))
                self.assertLessEqual(len(s.typed), 1)

    def test_a_line_is_never_typed_with_less_than_its_read_back_left_of_the_step(self):
        # Round 2 F3: slow first calls, then a restored profile that churns until the step is nearly spent. A line
        # typed then would get a read-back cut short and fail a pane whose enter did start; it is not typed. Control:
        # with fewer churning reads the same start types the line and succeeds.
        def run(churn):
            t, n = [0.0], [0]
            class Slow(FakeServer):
                def __call__(self, argv, timeout):
                    n[0] += 1
                    t[0] += 14 if n[0] <= 4 else 0.2
                    return super().__call__(argv, timeout)
            s = Slow([{"workspace_id": "w7", "label": "harness"}], answers_after=2,
                     startup=[{6000 + i} for i in range(churn)])
            return s, (lambda: hp.ensure(hp.Deck(s), "a", "/home/a", clock=lambda: t[0],
                                         sleep=lambda x: t.__setitem__(0, t[0] + x)))
        s, go = run(28)
        with self.assertRaisesRegex(hp.Failed, rf"not typed into: less than the {hp.READBACK_S:g} s"):
            go()
        self.assertEqual(s.typed, [])
        s, go = run(0)
        self.assertIn("ran enter again", go())
        self.assertEqual(len(s.typed), 1)

    def test_a_typed_line_always_has_its_whole_read_back_however_slow_pane_run(self):
        # Round 3 F3: `pane run` itself may be slow; the read-back still gets READBACK_S after it returns. Swept over
        # how long the restored profile churns, with calls that time out at the timeout they are given (as real_run's
        # do): whenever a line was typed, the read-back window after `pane run` is whole. Control: some sweep typed.
        typed_any = False
        for churn in range(0, 60):
            t, n, ran_at = [0.0], [0], []
            class Slow(FakeServer):
                def __call__(self, argv, timeout):
                    n[0] += 1
                    latency = 14 if n[0] <= 3 or "run" in argv else 0.2
                    if latency > timeout:
                        t[0] += timeout
                        raise hp.Failed("no answer")
                    t[0] += latency
                    out = super().__call__(argv, timeout)
                    if "run" in argv:
                        ran_at.append(t[0])
                    return out
            s = Slow([{"workspace_id": "w7", "label": "harness"}], answers_after=2,
                     startup=[{6000 + i} for i in range(churn)])
            try:
                hp.ensure(hp.Deck(s), "a", "/home/a", clock=lambda: t[0], sleep=lambda x: t.__setitem__(0, t[0] + x))
            except hp.Failed:
                pass
            for at in ran_at:
                typed_any = True
                self.assertLessEqual(at, hp.STEP_S - hp.READBACK_S, churn)
        self.assertTrue(typed_any)

    def test_a_wait_the_step_cut_short_says_so_not_its_own_window(self):
        # Round 2 F3: a call that ends past the step's deadline ends the wait; the message names the deadline and the
        # time waited, not the window's nominal STARTUP_S. Control: the same wait with the step's time left names its
        # own window's length and no deadline.
        def wait(left, latency):
            t = [0.0]
            class Slow(FakeServer):
                def __call__(self, argv, timeout):
                    t[0] += latency
                    return super().__call__(argv, timeout)
            deck = hp.Deck(Slow([{"workspace_id": "w7", "label": "harness"}], startup=[{9001}] * 1000))
            deck.start(lambda: t[0])
            t[0] = hp.STEP_S - left
            hp.shell_alone(deck, "w7:p1", lambda: t[0], lambda x: t.__setitem__(0, t[0] + x), hp.STARTUP_S)
        with self.assertRaisesRegex(hp.Failed, rf"after 6 s, when the step's {hp.STEP_S:g} s ran out"):
            wait(5, 6)
        with self.assertRaisesRegex(hp.Failed, r"has not come to its shell after 2\d s$"):
            wait(hp.STEP_S, 0.1)

    def test_the_typed_line_is_quoted_for_the_panes_shell(self):
        s = FakeServer()
        ensure(s, home="/home/we ird$(id)", login="a")
        self.assertEqual(s.typed[0][1], "/usr/local/share/moveto/enter '/home/we ird$(id)/projects' a --wait")


class WaitLine(unittest.TestCase):
    """The deck's boot presses Enter only at `<login> - Enter to activate` (fork PR #50, interface point c): the unit's
    pane runs exactly the line this module types, so the line is read from moveto's own enter run with those arguments."""

    def run_enter(self, home, stdin_open=True):
        typed = shlex.split(hp.enter_command(pwd.getpwuid(os.getuid()).pw_name, home))
        self.assertEqual((typed[0], typed[-1]), (hp.ENTER, "--wait"))
        stub = os.path.join(HERE, "runtime", "provisioning", "moveto", "enter")
        env = {"PATH": "/usr/bin:/bin", "HOME": home, "LANG": "C.UTF-8", "AGENT_FABRIC_PYTHON": sys.executable}
        return subprocess.Popen(["bash", stub, *typed[1:]], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_the_panes_last_line_while_it_waits_is_the_login_and_enter_to_activate(self):
        home = tempfile.mkdtemp(prefix="hp-home-")
        self.addCleanup(__import__("shutil").rmtree, home, True)
        os.makedirs(os.path.join(home, "projects"))
        p = self.run_enter(home)
        self.addCleanup(lambda: (p.kill(), p.wait(), [f.close() for f in (p.stdin, p.stdout, p.stderr) if f]))
        got = b""
        while not got.endswith(b"Enter to activate\n"):
            ready, _, _ = select.select([p.stdout], [], [], 30)
            self.assertTrue(ready, f"no Enter line within 30 s: {got!r}")
            chunk = os.read(p.stdout.fileno(), 4096)
            if not chunk:    # the message is built only here: reading stderr of a live process would block
                self.fail(f"enter ended before the line: {got!r} {p.stderr.read()!r}")
            got += chunk
        login = pwd.getpwuid(os.getuid()).pw_name
        # The title is two OSC sequences a terminal does not draw (enter writes them first, on the same line).
        drawn = re.sub(r"\x1b\][12];[^\x07]*\x07", "", got.decode())
        self.assertEqual(drawn.splitlines()[-1], f"{login} - Enter to activate")
        self.assertEqual(drawn, f"{login} - Enter to activate\n")
        # It waits there: nothing more is drawn, and it has not exited, until the Enter.
        self.assertEqual(select.select([p.stdout], [], [], 1.0)[0], [])
        self.assertIsNone(p.poll())
        # Positive control: the Enter is what moves it on (a pane that ignored stdin would pass the two checks above).
        p.stdin.write(b"\n")
        p.stdin.flush()
        p.stdin.close()
        p.wait(timeout=60)
        rest = p.stdout.read() + p.stderr.read()
        self.assertTrue(rest, "nothing followed the Enter")


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
elif a[2:4] == ["pane", "process-info"]:
    procs = [{"pid": 10}] + ([{"pid": 11}] if os.path.exists(os.environ["HP_LOG"]) else [])
    print(json.dumps({"result": {"process_info": {"shell_pid": 10, "foreground_processes": procs}}}))
else:
    sys.exit(7)
""")
        log = os.path.join(os.path.dirname(path), "log")
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(hp, "BINARY", path), mock.patch.object(hp, "SETTLE_S", 0.2), mock.patch.object(hp, "POLL_S", 0.1), \
                mock.patch.dict(os.environ, {"HP_LOG": log}), redirect_stdout(out), redirect_stderr(err):
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
