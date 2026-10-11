#!/usr/bin/env python3
"""tools/fabric/memory_flagrun.py (ADR-050 rules 3 and 6): the drain's flag phase. Real subprocesses stand in for the
three things outside it — `fabric-ctl` (presence and jobs), `gzcoord-send` and the harness CLI — each a small script
that records its calls. A dry run asks and sends nothing; --send sends one REQUEST per owning agent and writes the
ledger; a second run sends nothing new; a hint is present, absent or failed; the tree is byte-identical throughout."""
from __future__ import annotations

import json
import os
import pwd
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import memory_flagrun as fr  # noqa: E402
from test_memory_check import Tree, anchored, git  # noqa: E402 — tests/, the script's own directory
from test_memory_hint import FAKE, tree_digest  # noqa: E402

CTL = """import json, os, sys
d = os.environ["FAKE_CTL_DIR"]
op = sys.argv[2]
with open(os.path.join(d, "calls.log"), "a", encoding="utf-8") as fh:
    fh.write(" ".join(sys.argv[1:]) + "\\n")
sys.stdout.write(open(os.path.join(d, op + ".jsonl"), encoding="utf-8").read())
"""
SEND = """import os, sys
d = os.environ["FAKE_SEND_DIR"]
text = open(sys.argv[1], encoding="utf-8").read()
to = [ln for ln in text.splitlines() if ln.startswith("TO: ")][0][4:]
n = len(os.listdir(os.path.join(d, "sent")))
with open(os.path.join(d, "sent", f"{n}.txt"), "w", encoding="utf-8") as fh:
    fh.write(text)
rc = 0
try:
    rc = int(open(os.path.join(d, "rc-" + to.rsplit("/", 1)[-1]), encoding="utf-8").read())
except FileNotFoundError:
    pass
if rc:
    print("send: a warning that comes first", file=sys.stderr)
    print(f"send: pretend refusal {rc}", file=sys.stderr)
sys.exit(rc)
"""
HOST = "develop-qzapp"
NOW = 1_791_700_000.0       # 2026-10-11
DAY = 86400


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def jl(rows) -> str:
    return "".join(json.dumps(r) + "\n" for r in rows)


def presence(account, role, online):
    return {"account": account, "host": HOST, "status": "ok", "op": "presence",
            "presence": {"status": "ok", "online": online, "role": role}}


def jobs(account, titles, answered=True):
    return {"account": account, "host": HOST, "status": "ok" if answered else "failed", "op": "jobs",
            "jobs": {"status": "ok", "jobs": [{"state": "queued", "title": t} for t in titles]} if answered else None}


class FlagRun(Tree):
    def setUp(self):
        super().setUp()
        git(self.tree, "init", "-q")
        self.write("tools/fabric/runner.py", "def run_it():\n    return 1\n")
        git(self.tree, "add", "-A")
        git(self.tree, "commit", "-q", "-m", "the first state", date="2026-03-01")
        self.write("tools/fabric/runner.py", "def run_it():\n    return 2\n")
        git(self.tree, "add", "-A")
        git(self.tree, "commit", "-q", "-m", "the run changes its answer", date="2026-03-20")
        self.slice("a", ("moved", anchored("run_it returns 1 and the run takes no arguments.", ["tools/fabric/runner.py::run_it"], observed="2026-03-10")),
                   ("gone", anchored("A claim about a deleted file.", ["tools/fabric/deleted.py"], observed="2026-03-10", role="rust-dev")),
                   ("fresh", anchored("Settled.", ["tools/fabric/runner.py::run_it"], observed="2026-03-25")))
        self.work = tempfile.mkdtemp(prefix="flagrun-")
        self.addCleanup(__import__("shutil").rmtree, self.work, True)
        self.ledger = os.path.join(self.work, "memory-flags.jsonl")
        for name, text in (("ctl.py", CTL), ("send.py", SEND), ("claude.py", FAKE)):
            with open(os.path.join(self.work, name), "w", encoding="utf-8") as fh:
                fh.write(text)
        os.makedirs(os.path.join(self.work, "sent"))
        for var in ("FAKE_CTL_DIR", "FAKE_SEND_DIR", "FAKE_CLAUDE_DIR"):
            os.environ[var] = self.work
            self.addCleanup(os.environ.pop, var, None)
        self.fleet_files(presence=[presence("python-dev-01", "python-dev", True), presence("python-dev-02", "python-dev", False),
                                   presence("rust-dev-01", "rust-dev", False)],
                         jobs=[jobs("python-dev-01", []), jobs("python-dev-02", []), jobs("rust-dev-01", [])])
        self.mode("ok")
        self.report = {"section_writers": {}, "memory_marks": {}, "review_horizons": {}}
        self.said: list[str] = []

    def fleet_files(self, **ops):
        for op, rows in ops.items():
            with open(os.path.join(self.work, op + ".jsonl"), "w", encoding="utf-8") as fh:
                fh.write(jl(rows))

    def mode(self, name):
        with open(os.path.join(self.work, "mode"), "w", encoding="utf-8") as fh:
            fh.write(name)

    def exit_of(self, login, rc):
        with open(os.path.join(self.work, "rc-" + login), "w", encoding="utf-8") as fh:
            fh.write(str(rc))

    def sent(self):
        d = os.path.join(self.work, "sent")
        return [read(os.path.join(d, n)) for n in sorted(os.listdir(d), key=lambda n: int(n.split(".")[0]))]

    def ledger_rows(self):
        return [json.loads(ln) for ln in read(self.ledger).splitlines()]

    def claude_calls(self):
        p = os.path.join(self.work, "calls.jsonl")
        return [json.loads(ln) for ln in read(p).splitlines()] if os.path.exists(p) else []

    def go(self, send: bool, now=NOW):
        corpora = [fr.Corpus("f", "agent-fabric", self.corpus, self.tree, "agent-fabric")]
        flags, sources = fr.gather(corpora, self.report)
        fleet = fr.read_fleet([sys.executable, os.path.join(self.work, "ctl.py")])
        return fr.execute(flags, sources, self.report["section_writers"], fleet, ledger=self.ledger, sender=f"{HOST}/user",
                          sender_role="fabric-coordinator", project="agent-fabric", now=now, say=self.said.append,
                          send=[sys.executable, os.path.join(self.work, "send.py")] if send else None,
                          hint_argv=[sys.executable, os.path.join(self.work, "claude.py"), "-p"])


class Phase(FlagRun):
    def test_a_dry_run_prints_the_plan_and_asks_sends_and_writes_nothing(self):
        digest = tree_digest(self.base)
        o = self.go(send=False)
        self.assertEqual({a: [f.heading for f in fl] for a, fl in o.plan.requests.items()},
                         {f"{HOST}/python-dev-01": ["moved"], f"{HOST}/rust-dev-01": ["gone"]})
        self.assertEqual(fr.lines(o, True), [
            "flags: 2 routed to 2 agents (hints: 0, none: 0)",
            f"  {HOST}/python-dev-01: 1 flag(s) [running-holder]", f"  {HOST}/rust-dev-01: 1 flag(s) [lowest-numbered-holder]",
            "dry run: nothing sent, no model asked (--send sends)"])
        self.assertEqual((self.sent(), self.claude_calls(), os.path.exists(self.ledger), tree_digest(self.base)), ([], [], False, digest))

    def test_send_makes_one_request_per_agent_to_a_login_and_writes_the_ledger(self):
        digest = tree_digest(self.base)
        o = self.go(send=True)
        sent = self.sent()
        self.assertEqual(sorted(o.sent), [f"{HOST}/python-dev-01", f"{HOST}/rust-dev-01"])
        self.assertEqual(len(sent), 2)
        for text in sent:
            self.assertEqual((text.count("[GZCOORD/1] REQUEST"), text.count("\nTO: ")), (1, 1), "one request, TO one login, never TO-ROLE")
            self.assertNotIn("TO-ROLE", text)
        self.assertIn("run_it returns 1", sent[0] + sent[1])
        ledger = self.ledger_rows()
        self.assertEqual(sorted((r["key"], r["to"]) for r in ledger),
                         [("agent-fabric:domains/d/domain/a.md#gone", f"{HOST}/rust-dev-01"),
                          ("agent-fabric:domains/d/domain/a.md#moved", f"{HOST}/python-dev-01")])
        self.assertEqual(oct(os.stat(self.ledger).st_mode & 0o777), "0o600")
        self.assertEqual(tree_digest(self.base), digest, "nothing in the corpus or the checkout changed")
        self.assertEqual(sorted(os.listdir(self.work)), sorted(["ctl.py", "send.py", "claude.py", "sent", "mode", "calls.log", "calls.jsonl",
                                                                 "memory-flags.jsonl", "presence.jsonl", "jobs.jsonl"]), "no temporary file is left")

    def test_a_second_run_sends_nothing_new_until_the_grace_has_passed_and_its_job_is_gone(self):
        self.go(send=True)
        calls = len(self.claude_calls())
        again = self.go(send=True, now=NOW + 60)
        self.assertEqual(len(self.claude_calls()), calls, "no model is asked about a flag that is not sent")
        self.assertEqual((again.sent, len(again.plan.open), len(self.sent())), ({}, 2, 2), "inside the grace the REQUEST stands")
        late = self.go(send=True, now=NOW + 8 * DAY)
        self.assertEqual(sorted(late.sent), [f"{HOST}/python-dev-01", f"{HOST}/rust-dev-01"], "a week on, with no job for it: sent again")
        # the ledger now holds the late run's ids; an open job under the latest id keeps its flag from going again
        last = {r["to"]: r["message_id"] for r in self.ledger_rows()}
        self.fleet_files(jobs=[jobs("python-dev-01", [f"m (REQUEST {last[f'{HOST}/python-dev-01']})"]), jobs("python-dev-02", []),
                               jobs("rust-dev-01", [f"m (REQUEST {last[f'{HOST}/rust-dev-01']})"])])
        held = self.go(send=True, now=NOW + 20 * DAY)
        self.assertEqual((held.sent, len(held.plan.open)), ({}, 2), "its job is still open: never sent again")

    def test_the_grace_runs_from_the_second_the_request_went_not_from_a_midnight(self):
        self.go(send=True, now=NOW)
        self.assertEqual(self.go(send=True, now=NOW + 7 * DAY - 2).sent, {})
        self.assertEqual(len(self.go(send=True, now=NOW + 7 * DAY + 2).sent), 2)

    def test_a_flag_whose_last_writer_did_not_answer_is_held_not_given_to_another_holder(self):
        self.fleet_files(presence=[presence("python-dev-01", "python-dev", True), {"account": "python-dev-02", "host": HOST, "status": "failed"},
                                   presence("rust-dev-01", "rust-dev", False)])
        self.report["section_writers"] = {"memory/domains/d/domain/a.md#moved": {"agent": "python-dev-02"}}
        o = self.go(send=True)
        self.assertEqual([f.heading for f, _ in o.held], ["moved"])
        self.assertEqual(sorted(o.sent), [f"{HOST}/rust-dev-01"])
        self.assertIn("  held: agent-fabric:domains/d/domain/a.md#moved", "\n".join(fr.lines(o, False)))

    def test_a_flag_whose_open_request_sits_with_a_silent_account_is_not_sent_to_its_neighbour(self):
        self.go(send=True)                      # no writer recorded: the running holder, python-dev-01, was asked
        self.fleet_files(presence=[{"account": "python-dev-01", "host": HOST, "status": "failed"}, presence("python-dev-02", "python-dev", True),
                                   presence("rust-dev-01", "rust-dev", False)])
        o = self.go(send=True, now=NOW + 30 * DAY)
        self.assertEqual([f.heading for f, _ in o.held], ["moved"])
        self.assertEqual(o.sent.keys() & {f"{HOST}/python-dev-02"}, set(), "the neighbour is not asked in its place")

    def test_a_flag_whose_last_addressee_did_not_answer_the_jobs_query_is_held_too(self):
        self.go(send=True)
        self.fleet_files(jobs=[jobs("python-dev-01", [], answered=False), jobs("python-dev-02", []), jobs("rust-dev-01", [])],
                         presence=[presence("python-dev-01", "python-dev", False), presence("python-dev-02", "python-dev", True),
                                   presence("rust-dev-01", "rust-dev", False)])
        o = self.go(send=True, now=NOW + 30 * DAY)
        self.assertEqual(([f.heading for f, _ in o.held], list(o.sent)), (["moved"], [f"{HOST}/rust-dev-01"]))

    def test_a_request_that_went_out_but_could_not_be_recorded_says_so_with_its_id(self):
        real = fr.memory_flags.append_ledger
        def full(*a, **k):
            raise OSError(28, "No space left on device")
        fr.memory_flags.append_ledger = full
        self.addCleanup(setattr, fr.memory_flags, "append_ledger", real)
        o = self.go(send=True)
        self.assertTrue(o.failed and not o.sent)
        self.assertRegex(o.unsent[f"{HOST}/python-dev-01"], r"^sent as [0-9a-f-]{36} but not recorded in the ledger \(No space left on device\); the next run sends it again$")
        self.assertEqual(len(self.sent()), 2, "they did go out")

    def test_a_role_with_no_answering_holder_is_unknown_when_an_account_was_silent(self):
        self.fleet_files(presence=[presence("python-dev-01", "python-dev", True), {"account": "rust-dev-01", "host": HOST, "status": "failed"}])
        o = self.go(send=False)
        why = dict((f.heading, w) for f, w in o.plan.unrouted)["gone"]
        self.assertIn("has no holder (any of the 1 account(s) that did not answer may hold it)", why)
        self.fleet_files(presence=[presence("python-dev-01", "python-dev", True)])
        self.assertTrue(dict((f.heading, w) for f, w in self.go(send=False).plan.unrouted)["gone"].endswith("has no holder"))

    def test_a_request_that_cannot_be_made_does_not_stop_the_others_and_fails_the_run(self):
        real = fr.memory_flags.render_request
        def boom(address, *a, **k):
            if address.endswith("python-dev-01"):
                raise ValueError("does not validate")
            return real(address, *a, **k)
        fr.memory_flags.render_request = boom
        self.addCleanup(setattr, fr.memory_flags, "render_request", real)
        o = self.go(send=True)
        self.assertEqual((sorted(o.sent), o.failed, o.unsent[f"{HOST}/python-dev-01"]), ([f"{HOST}/rust-dev-01"], True, "ValueError: does not validate"))

    def test_a_refusal_shows_the_last_line_and_an_unknown_outcome_says_it_may_have_been_delivered(self):
        self.exit_of("python-dev-01", 3)
        o = self.go(send=True)
        self.assertEqual(o.unsent[f"{HOST}/python-dev-01"], "gzcoord-send exited 3: send: pretend refusal 3 (it may have been delivered)")

    def test_an_account_that_did_not_answer_for_its_jobs_is_never_sent_to_again(self):
        self.go(send=True)
        self.fleet_files(jobs=[jobs("python-dev-01", [], answered=False), jobs("python-dev-02", []), jobs("rust-dev-01", [])])
        o = self.go(send=True, now=NOW + 30 * DAY)
        self.assertEqual(sorted(o.sent), [f"{HOST}/rust-dev-01"], "unknown is not 'gone': only the account that answered is asked again")

    def test_a_hint_reaches_the_request_marked_as_a_guess(self):
        o = self.go(send=True)
        text = [t for t in self.sent() if f"TO: {HOST}/python-dev-01" in t][0]
        self.assertIn("- a model's guess, advisory, not a finding: The sentence 'run_it returns 1' looks wrong", text)
        self.assertEqual((o.hints["eligible"], o.hints["hinted"], len(self.claude_calls()), self.said), (1, 1, 1, []))
        self.assertEqual(fr.lines(o, False)[0], "flags: 2 routed to 2 agents (hints: 1, none: 0)")
        other = [t for t in self.sent() if f"TO: {HOST}/rust-dev-01" in t][0]
        self.assertNotIn("a model's guess", other, "a stale-hard section is not asked about")

    def test_no_hint_when_the_model_says_none(self):
        self.mode("none")
        o = self.go(send=True)
        self.assertNotIn("a model's guess", "".join(self.sent()))
        self.assertEqual((len(self.sent()), o.hints["hinted"], self.said), (2, 0, []))
        self.assertEqual(fr.lines(o, False)[0], "flags: 2 routed to 2 agents (hints: 0, none: 1)")

    def test_a_failed_model_call_gives_no_hint_one_line_and_the_requests_still_go(self):
        self.mode("exit")
        o = self.go(send=True)
        self.assertEqual(len(self.sent()), 2)
        self.assertNotIn("a model's guess", "".join(self.sent()))
        self.assertEqual(len(self.said), 1)
        self.assertIn("none attached to this drain's flags", self.said[0])
        self.assertEqual((o.hints["failed"] is not None, o.failed), (True, False), "a missing hint is not a failed run")

    def test_no_cli_at_all_is_the_same_failure(self):
        corpora = [fr.Corpus("f", "agent-fabric", self.corpus, self.tree, "agent-fabric")]
        flags, sources = fr.gather(corpora, self.report)
        fleet = fr.read_fleet([sys.executable, os.path.join(self.work, "ctl.py")])
        o = fr.execute(flags, sources, {}, fleet, ledger=self.ledger, sender=f"{HOST}/user", sender_role="fabric-coordinator",
                       project="agent-fabric", now=NOW, say=self.said.append, hint_argv=[os.path.join(self.work, "no-such-claude")],
                       send=[sys.executable, os.path.join(self.work, "send.py")])
        self.assertEqual((len(self.sent()), len(self.said)), (2, 1))
        self.assertIn("is not installed", self.said[0])
        self.assertIsNotNone(o.hints["failed"])

    def test_an_agent_with_no_session_is_not_recorded_and_a_refusal_fails_the_run_without_stopping_the_others(self):
        self.exit_of("python-dev-01", 4)
        o = self.go(send=True)
        self.assertEqual((sorted(o.sent), list(o.unsent), o.failed), ([f"{HOST}/rust-dev-01"], [f"{HOST}/python-dev-01"], False))
        self.assertEqual([r["to"] for r in self.ledger_rows()], [f"{HOST}/rust-dev-01"])
        self.assertIn("not sent — no session running", "\n".join(fr.lines(o, False)))
        self.exit_of("python-dev-01", 1)
        os.unlink(self.ledger)
        o = self.go(send=True)
        self.assertEqual((sorted(o.sent), o.failed), ([f"{HOST}/rust-dev-01"], True))
        self.assertIn("gzcoord-send exited 1: send: pretend refusal 1", o.unsent[f"{HOST}/python-dev-01"])

    def test_a_reader_mark_joins_the_flag_and_a_section_the_check_passed_is_flagged_on_it(self):
        self.report["memory_marks"] = {"f:domains/d/domain/a#3": [{"t": "2026-10-10", "verdict": "stale", "note": "no longer so"}]}
        o = self.go(send=False)
        flags = {f.heading: sorted(r["kind"] for r in f.reasons) for fl in o.plan.requests.values() for f in fl}
        self.assertEqual(flags["fresh"], ["mark-stale"])

    def test_the_holders_are_every_account_of_the_role_and_a_silent_account_is_unknown_not_absent(self):
        self.fleet_files(presence=[presence("python-dev-01", "python-dev", True), {"account": "python-dev-02", "host": HOST, "status": "failed",
                                                                  "presence": {"status": "ok", "online": True, "role": "python-dev"}},
                                   {**presence("python-dev-03", "python-dev", True), "presence": {"status": "failed", "online": True, "role": "python-dev"}},
                                   presence("rust-dev-01", None, False)])
        fleet = fr.read_fleet([sys.executable, os.path.join(self.work, "ctl.py")])
        self.assertEqual((fleet.holders, fleet.running), ({"python-dev": [f"{HOST}/python-dev-01"]}, {f"{HOST}/python-dev-01"}))
        self.assertEqual(fleet.silent, {f"{HOST}/python-dev-02", f"{HOST}/python-dev-03"}, "unknown, kept apart from 'holds none'")

    def test_a_fleet_that_gave_no_account_is_a_refusal_not_a_guess(self):
        self.fleet_files(presence=[])
        with self.assertRaisesRegex(fr.FlagRunError, "gave no account"):
            fr.read_fleet([sys.executable, os.path.join(self.work, "ctl.py")])


class Entry(FlagRun):
    """The installed entry: fabric-memory-check --flags, as a program, in an environment it owns."""

    def run_cli(self, *args, bound=True):
        import subprocess
        wc = self.tree
        # The code reads a few files of the fabric root it is given (the identity module, the role catalogue): copied in.
        for rel in ("runtime/identity.py", "identities/roles/catalog.json"):
            dest = os.path.join(wc, rel)
            if not os.path.exists(dest):
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy(os.path.join(HERE, rel), dest)
        project_dir = os.path.join(wc, ".agent-fabric", "memory")
        os.makedirs(project_dir, exist_ok=True)
        with open(os.path.join(project_dir, "last-drain-report.json"), "w", encoding="utf-8") as fh:
            json.dump(self.report, fh)
        state = os.path.join(self.work, "state")
        os.makedirs(os.path.join(state, "agent-fabric", "agents", pwd.getpwuid(os.geteuid()).pw_name), exist_ok=True)
        with open(os.path.join(state, "agent-fabric", "agents", pwd.getpwuid(os.geteuid()).pw_name, "binding.json"), "w", encoding="utf-8") as fh:
            json.dump({"role": "fabric-coordinator"} if bound else {}, fh)
        env = {"PATH": "/usr/bin:/bin", "HOME": self.work, "XDG_STATE_HOME": state, "AGENT_FABRIC_ROOT": self.tree,
               "AGENT_FABRIC_CTL": os.path.join(self.work, "ctl.sh"), "AGENT_FABRIC_GZCOORD_SEND": os.path.join(self.work, "send.sh"),
               "FAKE_CTL_DIR": self.work, "FAKE_SEND_DIR": self.work}
        for name, script in (("ctl.sh", "ctl.py"), ("send.sh", "send.py")):
            with open(os.path.join(self.work, name), "w", encoding="utf-8") as fh:
                fh.write(f"#!/bin/sh\nexec {sys.executable} {os.path.join(self.work, script)} \"$@\"\n")
            os.chmod(os.path.join(self.work, name), 0o755)
        return subprocess.run([sys.executable, os.path.join(HERE, "tools", "fabric", "memory_check.py"), "--flags", *args],
                              capture_output=True, text=True, env=env, timeout=120, stdin=subprocess.DEVNULL, check=False)

    def test_the_command_defaults_to_a_dry_run_and_send_sends_through_the_real_entry(self):
        dry = self.run_cli()
        self.assertEqual((dry.returncode, dry.stderr), (0, ""), dry)
        self.assertIn("flags: 2 routed to 2 agents (hints: 0, none: 0)", dry.stdout)
        self.assertEqual(self.sent(), [])
        live = self.run_cli("--send")
        self.assertEqual(live.returncode, 0, live)
        self.assertEqual(len(self.sent()), 2)
        self.assertIn("(hints: 0, none: 1)", live.stdout)
        self.assertIn("the harness CLI (claude) is not installed", live.stderr, "the real CLI is absent from this PATH: no hint and one line")
        self.assertEqual(len(live.stderr.strip().splitlines()), 1)

    def test_send_from_a_session_bound_to_no_role_is_refused_before_anything_goes(self):
        r = self.run_cli("--send", bound=False)
        self.assertEqual((r.returncode, self.sent()), (1, []))
        self.assertEqual(r.stderr.strip(), "memory flags: this session is bound to no role: the REQUESTs would carry none")
        self.assertEqual(self.run_cli(bound=False).returncode, 0, "a dry run needs no role")

    def test_a_project_with_no_drain_report_is_one_line_and_exit_1(self):
        r = self.run_cli("--project", "no-such-project")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1)
        self.assertTrue(r.stderr.startswith("memory flags: "))

    def test_an_unknown_option_is_usage_exit_2(self):
        r = self.run_cli("--bogus")
        self.assertEqual((r.returncode, r.stdout), (2, ""))


class Drain(FlagRun):
    """assemble.py --flags: the phase after the drain, which reads its report and adds its own line to it."""

    def drain(self, *extra, body="A passive beacon emits."):
        import test_assemble as ta
        tmp = tempfile.mkdtemp(prefix="flagrun-drain-", dir=self.work)
        drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [
            {"class": "domain", "topic": "ble", "title": "Advertisements are one-way", "body": body, "evidence": ["h1"]}])})
        env = {"AGENT_FABRIC_CTL": os.path.join(self.work, "ctl.sh"), "AGENT_FABRIC_GZCOORD_SEND": os.path.join(self.work, "send.sh"),
               "XDG_STATE_HOME": os.path.join(self.work, "state")}
        for name, script in (("ctl.sh", "ctl.py"), ("send.sh", "send.py")):
            with open(os.path.join(self.work, name), "w", encoding="utf-8") as fh:
                fh.write(f"#!/bin/sh\nexec {sys.executable} {os.path.join(self.work, script)} \"$@\"\n")
            os.chmod(os.path.join(self.work, name), 0o755)
        saved = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        try:
            return ta.run_assemble(drain, claims_dir, out, *extra), ta.report_path(out)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_without_the_option_the_drain_is_what_it_was(self):
        r, report = self.drain()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("flags:", r.stdout)
        self.assertNotIn("memory_flags", read(report))

    def test_the_phase_runs_after_the_report_and_leaves_its_line_in_it(self):
        r, report = self.drain("--flags")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("flags: 0 routed to 0 agents (hints: 0, none: 0)", r.stdout)
        self.assertIn("dry run: nothing sent", r.stdout)
        doc = json.loads(read(report))
        self.assertEqual(doc["memory_flags"]["routed"], 0)
        self.assertTrue(doc["memory_flags"]["dry_run"])
        self.assertIn("section_writers", doc, "the drain's own report is kept whole")
        self.assertEqual(os.listdir(os.path.join(self.work, "sent")), [])

    def test_a_drain_that_failed_routes_nothing(self):
        ok, _ = self.drain("--flags")
        self.assertIn("flags:", ok.stdout, "the same setup, a clean drain, runs the phase")
        r, _ = self.drain("--flags", body="Bisogna fare questo, quindi anche il resto.")   # reads as non-English: the drain rejects it, exit 1
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertNotIn("flags:", r.stdout)

    def test_send_without_flags_is_a_usage_error_before_anything_is_written(self):
        r, report = self.drain("--send")
        self.assertEqual(r.returncode, 2)
        self.assertFalse(os.path.exists(report))
        self.assertIn("--send goes with --flags", r.stderr)


if __name__ == "__main__":
    unittest.main()
