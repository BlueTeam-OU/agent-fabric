#!/usr/bin/env python3
"""The intake's half of the work lifecycle, pinned against agent-fabric ADR-037 rule 14 (A 2026-11-08), row R3:

  -> queued    `fabric-jobs add`; the inbox intake (rule 11); the control agent's `jobs-add` (rule 4); `import` into an empty list
               needs a title and project; from a REQUEST, its id, once per id

Each path runs the real code against the scratch list of tests/work_lifecycle_world.py, the intake in process (tools/fabric/gzcoord/
intake.py over the real jobs.py, not the fake the intake suite uses: the point here is what the paths do to one list) and the others as
the command. `add --request` takes its message from the relay's replay and is covered in tests/test_jobs.py; here its job-making
function, records.request_job, is called with the same message the intake gets. The list's lock is what makes the paths one job
in whatever order they arrive (jobs.py listed_request), and the cases hold that for every state a job can be in."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
from git_env import scrub_process_env  # noqa: E402 — tests/, this script's own directory
from instance_fixtures import own_instance_tree  # noqa: E402
scrub_process_env()
own_instance_tree()
from gzcoord import intake  # noqa: E402
from work_lifecycle_world import World  # noqa: E402

ME_HOST = "dev-host"
MID = "01a11f64-ba5d-75f8-aa8d-4e755dc0f76e"
OTHER = "01a11f64-ba5d-75f8-aa8d-4e755dc0f76f"


class Intake(unittest.TestCase):
    def setUp(self) -> None:
        self.w = World()
        self.addCleanup(self.w.close)
        patch = mock.patch.dict(os.environ, self.w.env, clear=True)
        patch.start()
        self.addCleanup(patch.stop)
        spec = importlib.util.spec_from_file_location("jobs_in_process", os.path.join(ROOT, "tools", "fabric", "jobs.py"))
        self.jobs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.jobs)
        self.me = f"{ME_HOST}/{self.w.login}"
        cwd = os.getcwd()
        os.chdir(self.w.alpha)
        self.addCleanup(os.chdir, cwd)

    def delivery(self, mtype: str = "REQUEST", mid: str = MID, **meta) -> dict:
        metadata = {"FROM": "dev-host/user", "TO": self.me, "MESSAGE-ID": mid, "SUBJECT": "a subject", "PROJECT": "fixture-proj", **meta}
        return {"rec": {"seq": 7, "sender": "dev-host/user"}, "msg": {"type": mtype, "metadata": {k: v for k, v in metadata.items() if v is not None}},
                "isMine": True}

    def receive(self, *items: dict, jobs=None) -> tuple[list[str], str]:
        err = io.StringIO()
        return intake.queue_received(list(items), {"address": self.me}, jobs=jobs or self.jobs, err=err), err.getvalue()

    # ── R3, the inbox's half ────────────────────────────────────────────────────────────────────────────────────────

    def test_r3_a_request_to_this_login_is_queued_with_the_request_as_its_source(self):
        lines, err = self.receive(self.delivery())
        self.assertEqual((lines, err), ([f"queued as j1: a subject (REQUEST {MID})"], ""))
        job = self.w.job("j1")
        self.assertEqual((job["state"], job["project"], job["title"]), ("queued", "fixture-proj", f"a subject (REQUEST {MID})"))
        self.assertEqual(job["source"], {"kind": "request", "message_id": MID, "from": "dev-host/user", "seq": 7})
        self.assertEqual([e["state"] for e in job["log"]], ["queued"])

    def test_r3_once_per_id_a_redelivery_a_second_watch_and_one_page_twice_are_one_job(self):
        self.receive(self.delivery())
        self.receive(self.delivery())
        self.receive(self.delivery(), self.delivery())
        self.assertEqual([j["id"] for j in self.w.jobs()], ["j1"])

    def test_r3_a_job_in_any_state_holds_its_request_so_nothing_reopens_it(self):
        for state in ("active", "paused", "blocked", "delivered", "done", "dropped"):
            with self.subTest(state):
                self.receive(self.delivery())
                self.w.put(lambda doc, s=state: doc["jobs"][0].update(state=s))
                lines, _ = self.receive(self.delivery())
                self.assertEqual((lines, [(j["id"], j["state"]) for j in self.w.jobs()]), ([], [("j1", state)]))
                os.unlink(self.w.path)

    def test_r3_only_a_request_to_this_login_is_work(self):
        not_mine = self.delivery(TO="dev-host/someone-else")
        by_role = self.delivery()
        del by_role["msg"]["metadata"]["TO"]
        by_role["msg"]["metadata"]["TO-ROLE"] = "python-dev"
        broadcast = self.delivery()
        del broadcast["msg"]["metadata"]["TO"]
        broadcast["msg"]["metadata"]["BROADCAST"] = "true"
        unclassified = {**self.delivery(), "isMine": False}
        lines, err = self.receive(not_mine, by_role, broadcast, self.delivery("REPLY"), self.delivery("INFO"), unclassified)
        self.assertEqual((lines, err), ([], ""))
        self.assertFalse(os.path.exists(self.w.path), "nothing was written")

    def test_r3_a_message_id_that_is_not_one_is_said_on_stderr_and_queues_nothing(self):
        lines, err = self.receive(self.delivery(mid="17"))
        self.assertEqual(lines, [])
        self.assertIn("its MESSAGE-ID is not an id", err)

    def test_r3_a_request_that_cannot_be_queued_is_a_line_never_a_failed_delivery(self):
        class Broken:
            def __getattr__(self, name):
                raise RuntimeError("the list is locked")
        lines, err = self.receive(self.delivery(), jobs=Broken())
        self.assertEqual(lines, [])
        self.assertIn(f"REQUEST {MID} was not queued on your job list: the list is locked", err)

    def test_r3_the_for_branch_a_request_names_is_filled_in_only_while_the_job_is_queued_and_has_none(self):
        branch = f"{sys.modules['fabric_jobs'].records.identity.current_host()}/{self.w.login}/for/user/a-thing"
        item = self.delivery()
        item["msg"]["text"] = f"[GZCOORD/1] REQUEST\n\nREQUEST:\nplease\n\nDELIVER-TO:\n{branch}\n"
        self.assertEqual(self.w.run("add", "--owner", "dev-host/user", "--", f"a subject (REQUEST {MID})").returncode, 0)
        self.receive(item)
        self.assertEqual(self.w.job("j1")["deliver_to"], branch)
        self.w.put(lambda doc: doc["jobs"][0].pop("deliver_to"))
        self.w.put(lambda doc: doc["jobs"][0].update(state="active"))
        self.receive(item)
        self.assertNotIn("deliver_to", self.w.job("j1"), "a job already taken is not given a branch afterwards")

    # ── R3, the sender's half and the control agent's jobs-add ──────────────────────────────────────────────────────

    def sent(self, run, **kw) -> str | None:
        msg = {"type": "REQUEST", "metadata": {"TO": self.me, "MESSAGE-ID": MID, "SUBJECT": "a subject", "PROJECT": "fixture-proj"}}
        hosts = {"hosts": {ME_HOST: {"operator": "boss"}}}
        return intake.queue_for_addressee(msg, sender=kw.pop("sender", "boss"), hosts=hosts, run=run, err=kw.pop("err", io.StringIO()))

    def test_r3_the_operators_send_asks_the_addressees_control_agent_for_the_same_title(self):
        asked: list[list[str]] = []

        def run(argv, **kw):
            asked.append(argv)
            if argv[2:3] == ["jobs"]:
                return subprocess.CompletedProcess(argv, 0, "", "")        # the addressee's list does not show it
            return subprocess.CompletedProcess(argv, 0, "added j3    queued\n", "")
        self.assertEqual(self.sent(run), "j3")
        self.assertEqual(asked[1][2:], ["jobs-add", "--project", "fixture-proj", "--", f"a subject (REQUEST {MID})"])

    def test_r3_a_sender_that_is_not_the_hosts_operator_asks_nothing_and_a_listed_request_is_not_asked_twice(self):
        calls: list[list[str]] = []
        self.assertIsNone(self.sent(lambda argv, **kw: calls.append(argv), sender="someone"))
        row = json.dumps({"jobs": {"jobs": [{"title": f"a subject (REQUEST {MID})"}]}})
        self.assertIsNone(self.sent(lambda argv, **kw: calls.append(argv) or subprocess.CompletedProcess(argv, 0, row, "")))
        self.assertEqual([c[2] for c in calls], ["jobs"], "the second send looked, found it listed, and added nothing")

    def test_r3_a_failed_jobs_add_is_a_line_on_stderr_and_no_job(self):
        err = io.StringIO()
        calls = iter([subprocess.CompletedProcess([], 0, "", ""), subprocess.CompletedProcess([], 1, "", "fabric-jobs: no\n")])
        self.assertIsNone(self.sent(lambda argv, **kw: next(calls), err=err))
        self.assertIn(f"REQUEST {MID} was not queued on {self.me}'s list: fabric-jobs: no", err.getvalue())

    def test_r3_the_title_the_sender_adds_and_the_one_the_inbox_adds_are_one_job_in_either_order(self):
        title = f"a subject (REQUEST {MID})"
        add = ("add", "--owner", "dev-host/boss", "--project", "fixture-proj", "--", title)
        self.assertEqual(self.w.run(*add).returncode, 0)
        self.receive(self.delivery())
        again = self.w.run(*add)
        self.assertTrue(again.stdout.startswith("already listed j1"), again.stdout)
        self.assertEqual([(j["id"], j["source"]["kind"]) for j in self.w.jobs()], [("j1", "owner")])
        os.unlink(self.w.path)
        self.receive(self.delivery())
        self.assertTrue(self.w.run(*add).stdout.startswith("already listed j1"))
        self.assertEqual([(j["id"], j["source"]["kind"]) for j in self.w.jobs()], [("j1", "request")])

    def test_r3_add_by_the_control_agent_is_a_queued_job_with_the_operator_as_its_owner(self):
        from control import jobs as control_jobs

        def run(argv, cwd=None, env=None, timeout=None):
            return subprocess.run([sys.executable, *argv] if not os.access(argv[0], os.X_OK) else argv, cwd=self.w.alpha, env=self.w.env,
                                  capture_output=True, text=True, timeout=timeout)
        said = control_jobs.jobs_add({"from": "dev-host/boss", "to": [self.me], "args": {"title": "an owner's job", "priority": "high"}},
                                     home=self.w.env["HOME"], root=ROOT, run=run)
        self.assertEqual(said["status"], "added", said)
        job = self.w.job("j1")
        self.assertEqual((job["state"], job["priority"], job["source"]), ("queued", "high", {"kind": "owner", "from": "dev-host/boss"}))

    # ── the paths that make the same REQUEST into a job ─────────────────────────────────────────────────────────────

    def request_job_title(self) -> str:
        msg = {"type": "REQUEST", "seq": 7, "metadata": {"FROM": "dev-host/user", "TO": self.me, "MESSAGE-ID": MID, "SUBJECT": "a subject",
                                                           "PROJECT": "fixture-proj"}}
        doc = {"jobs": [], "seq": 0}
        return self.jobs.request_job(doc, msg)["title"]

    def test_f11_a_request_is_titled_the_same_by_every_path_that_makes_it_a_job(self):
        # The requester's `request:<id>` blocker finds the job its REQUEST became by this title's suffix (blockers._became): a job added
        # by `add --request` had none, so the board showed no such job and the wait read as cleared.
        self.receive(self.delivery())
        self.assertEqual(self.w.job("j1")["title"], f"a subject (REQUEST {MID})")
        self.assertEqual(self.request_job_title(), f"a subject (REQUEST {MID})")
        self.assertEqual(self.jobs.request_id_of(self.request_job_title()), MID)


if __name__ == "__main__":
    unittest.main()
