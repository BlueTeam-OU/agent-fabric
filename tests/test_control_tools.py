#!/usr/bin/env python3
"""The tools report on the control plane (tools/fabric/control/tools.py): the
control agent runs `fabric-tools --all --json` at start and every hour and
keeps the last good result in <state>/tools.json; the `tools` op returns it
with its age. A port of runtime/control/tests/tools.test.mjs, case for case,
less what is the daemon's or fabric-ctl's: the hourly timer and the binding
watch (agentd's, which calls refresh() and refresh_again()) and the
`fabric-ctl tools` table and argument parsing (ctl's)."""
from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import ops, tools as T  # noqa: E402

DOC = {"projects": ["gzapp"], "ok": False, "tools": [
    {"project": "gzapp", "name": "pnpm", "status": "missing", "found": "pnpm not found", "version": "11.6.0", "where": "account", "optional": False, "why": "x"},
    {"project": "gzapp", "name": "doppler", "status": "missing", "found": "", "version": "", "where": "account", "optional": True, "why": "x"},
    {"project": "gzapp", "name": "git", "status": "ok", "found": "git 2", "version": "", "where": "host", "optional": False, "why": "x"}]}


class Base(unittest.TestCase):
    def scratch(self, prefix: str = "tools-") -> str:
        t = tempfile.TemporaryDirectory(prefix=prefix)
        self.addCleanup(t.cleanup)
        return t.name

    def fake_root(self, script: str) -> str:
        """A root with a bin/fabric-tools of its own: the keeper runs a real executable by argv, as in production."""
        root = self.scratch("tools-root-")
        os.makedirs(os.path.join(root, "bin"))
        f = os.path.join(root, "bin", "fabric-tools")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(f"#!/usr/bin/env bash\n{script}\n")
        os.chmod(f, 0o755)
        return root

    def quiet(self):
        said: list[str] = []
        return said, said.append


class Contract(Base):
    def test_tools_is_an_operator_read_neither_an_action_nor_public(self):
        self.assertIn("tools", ops.OPS)
        self.assertNotIn("tools", ops.PUBLIC_OPS)

    def test_parse_run_exit_1_with_a_document_that_says_not_ok_is_an_answer_every_other_disagreement_is_a_failure(self):
        self.assertEqual(T.parse_run(1, json.dumps(DOC))["doc"], DOC)
        self.assertEqual(T.parse_run(0, json.dumps({**DOC, "ok": True}))["doc"], {**DOC, "ok": True})
        self.assertRegex(T.parse_run(0, json.dumps(DOC))["error"], r"exited 0 but the document says ok: false")
        self.assertRegex(T.parse_run(1, json.dumps({**DOC, "ok": True}))["error"], r"exited 1 but")
        self.assertRegex(T.parse_run(2, json.dumps(DOC))["error"], r"exited 2")
        self.assertRegex(T.parse_run(127, "")["error"], r"exited 127")
        self.assertRegex(T.parse_run(0, "not json")["error"], r"no JSON document")
        self.assertRegex(T.parse_run(0, json.dumps({"ok": True}))["error"], r"without projects, tools and ok")
        self.assertRegex(T.parse_run(0, "[1]")["error"], r"without projects, tools and ok")
        self.assertRegex(T.parse_run(0, json.dumps({**DOC, "ok": "true"}))["error"], r"without projects, tools and ok", "ok is a boolean or it is not there")


class Run(Base):
    def test_runs_the_accounts_bin_fabric_tools_by_argv_exit_1_is_an_answer_exit_2_a_timeout_and_no_command_are_failures(self):
        argv_file = os.path.join(self.scratch("tools-argv-"), "argv")
        root = self.fake_root(f"printf '%s\\n' \"$@\" > '{argv_file}'\ncat <<'J'\n{json.dumps(DOC)}\nJ\nexit 1")
        got = T.run_tools(root=root, home=self.scratch("tools-home-"))
        self.assertEqual(got["doc"], DOC)
        with open(argv_file, encoding="utf-8") as fh:
            self.assertEqual([x for x in fh.read().split("\n") if x], ["--all", "--json"])
        self.assertRegex(T.run_tools(root=self.fake_root('echo "bad registry" >&2; exit 2'))["error"], r"exited 2")
        self.assertRegex(T.run_tools(root=self.fake_root("sleep 30"), timeout_ms=200)["error"], r"did not finish within 0\.2 s")
        self.assertRegex(T.run_tools(root=self.scratch("tools-empty-"))["error"], r"could not run \(ENOENT\)")
        killed = T.run_tools(root=self.fake_root("kill -9 $$"))["error"]   # a process the kernel killed is not the bound being too small
        self.assertRegex(killed, r"killed by SIGKILL")
        self.assertNotIn("did not finish", killed)

    def test_output_past_its_bound_is_a_failure_said(self):
        root = self.fake_root("head -c 5000000 /dev/zero")
        self.assertEqual(T.run_tools(root=root, timeout_ms=20000)["error"], "fabric-tools printed more than 4 MiB")


class Keeper(Base):
    def test_the_keeper_writes_the_report_atomically_and_leaves_no_temporary_file(self):
        d = self.scratch("tools-state-")
        file = os.path.join(d, "agents", "a", "tools.json")
        said, log = self.quiet()
        k = T.ToolsKeeper(run=lambda: {"doc": DOC}, file=file, log=log)
        self.assertEqual(k.refresh(), {"status": "written"})
        with open(file, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), DOC)
        self.assertEqual(os.listdir(os.path.dirname(file)), ["tools.json"])
        self.assertEqual(stat.S_IMODE(os.stat(file).st_mode), 0o600)
        # A reader that already has the old report open sees it whole: the new
        # one replaced the file, it was not written over it.
        with open(file, encoding="utf-8") as old:
            T.ToolsKeeper(run=lambda: {"doc": {**DOC, "ok": True}}, file=file, log=log).refresh()
            self.assertEqual(json.load(old), DOC)
        with open(file, encoding="utf-8") as fh:
            self.assertIs(json.load(fh)["ok"], True)

    def test_a_failed_run_keeps_the_previous_report_and_says_so_once_per_cause_a_success_rearms_the_line(self):
        file = os.path.join(self.scratch("tools-state-"), "tools.json")
        said, log = self.quiet()
        nxt: list[dict] = [{"doc": DOC}]
        k = T.ToolsKeeper(run=lambda: nxt[0], file=file, log=log)
        k.refresh()
        before = open(file, encoding="utf-8").read()
        nxt[0] = {"error": "fabric-tools exited 127"}
        self.assertEqual(k.refresh(), {"status": "kept", "error": "fabric-tools exited 127"})
        k.refresh()
        self.assertEqual(open(file, encoding="utf-8").read(), before, "the old report stays")
        self.assertEqual(len(said), 1, said)
        nxt[0] = {"error": "fabric-tools exited 2"}
        k.refresh()
        self.assertEqual(len(said), 2, "another cause is another line")
        nxt[0] = {"doc": {**DOC, "ok": True}}
        k.refresh()
        nxt[0] = {"error": "fabric-tools exited 2"}
        k.refresh()
        self.assertEqual(len(said), 3, "after a success the same failure is news again")

    def test_a_cause_alternating_with_another_is_still_said_once_until_a_run_succeeds(self):
        said, log = self.quiet()
        nxt: list[dict] = [{}]
        k = T.ToolsKeeper(run=lambda: nxt[0], file=os.path.join(self.scratch("tools-state-"), "tools.json"), log=log)
        for e in ("A", "B", "A", "B"):
            nxt[0] = {"error": e}
            k.refresh()
        self.assertEqual(len(said), 2, said)

    def test_a_run_that_raises_or_a_report_that_cannot_be_written_is_a_kept_report_too(self):
        d = self.scratch("tools-state-")
        file = os.path.join(d, "tools.json")
        said, log = self.quiet()

        def boom():
            raise RuntimeError("boom")
        self.assertEqual(T.ToolsKeeper(run=boom, file=file, log=log).refresh()["status"], "kept")
        os.mkdir(file)   # a directory where the report goes: the rename fails
        r = T.ToolsKeeper(run=lambda: {"doc": DOC}, file=file, log=log).refresh()
        self.assertEqual(r["status"], "kept")
        self.assertRegex(r["error"], r"could not be written")
        self.assertEqual(os.listdir(d), ["tools.json"], "no temporary file left behind")

    def test_two_refreshes_that_overlap_share_one_run(self):
        runs = [0]
        gate, started = threading.Event(), threading.Event()

        def run():
            runs[0] += 1
            started.set()
            gate.wait(10)
            return {"doc": DOC}
        k = T.ToolsKeeper(run=run, file=os.path.join(self.scratch("tools-state-"), "tools.json"), log=lambda m: None)
        results: list = []
        a = threading.Thread(target=lambda: results.append(k.refresh()))
        a.start()
        self.assertTrue(started.wait(10))
        b = threading.Thread(target=lambda: results.append(k.refresh()))
        b.start()
        gate.set()
        a.join(10)
        b.join(10)
        self.assertEqual((runs[0], results), (1, [{"status": "written"}] * 2))
        k.refresh()
        self.assertEqual(runs[0], 2, "and the next one runs again")

    def test_refresh_again_waits_for_the_run_in_flight_then_runs_once_more(self):
        runs = [0]
        gate, started = threading.Event(), threading.Event()

        def run():
            runs[0] += 1
            if runs[0] == 1:
                started.set()
                gate.wait(10)
            return {"doc": DOC}
        k = T.ToolsKeeper(run=run, file=os.path.join(self.scratch("tools-state-"), "tools.json"), log=lambda m: None)
        t = threading.Thread(target=k.refresh)
        t.start()
        self.assertTrue(started.wait(10))
        out: list = []
        u = threading.Thread(target=lambda: out.append(k.refresh_again()))
        u.start()
        gate.set()
        t.join(10)
        u.join(10)
        self.assertEqual((runs[0], out), (2, [{"status": "written"}]), "one more run after the one in flight")
        k.refresh_again()
        self.assertEqual(runs[0], 3, "with none in flight it is a plain refresh")


class Op(Base):
    def test_the_tools_op_none_yet_the_report_with_its_age_and_an_unreadable_one_named(self):
        d = self.scratch("tools-state-")
        self.assertEqual(T.tools(d), {"status": "none"})
        T.write_report(T.report_file(d), DOC)
        mtime = os.stat(T.report_file(d)).st_mtime * 1000
        self.assertEqual(T.tools(d, lambda: mtime + 3 * 3600 * 1000), {"status": "ok", "age_s": 10800, "ok": False, "tools": DOC["tools"]})
        with open(T.report_file(d), "w", encoding="utf-8") as fh:
            fh.write("not json")
        self.assertEqual(T.tools(d), {"status": "failed", "error": "tools.json is not JSON"})
        with open(T.report_file(d), "w", encoding="utf-8") as fh:
            fh.write("{}")
        self.assertRegex(T.tools(d)["error"], r"holds no tools list")

    def test_the_persisted_report_is_the_documents_own_bytes_in_meaning(self):
        d = self.scratch("tools-state-")
        T.write_report(T.report_file(d), {**DOC, "tools": [{**DOC["tools"][0], "why": "ünïcode ✓"}]})
        with open(T.report_file(d), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("ünïcode ✓", text, "non-ASCII as itself, as JSON.stringify wrote it")
        self.assertTrue(text.endswith("}\n"))
        self.assertIn('\n  "projects": [\n    "gzapp"\n  ]', text, "two-space indent")

    def test_collect_answers_the_tools_op_from_the_accounts_own_state_directory(self):
        d = self.scratch("tools-state-")
        T.write_report(T.report_file(d), DOC)
        r = ops.collect("tools", {"tools_opts": {"directory": d}})
        self.assertEqual(r["tools"]["status"], "ok")
        self.assertEqual(list(r), ["tools"])


if __name__ == "__main__":
    unittest.main()
