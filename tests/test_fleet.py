#!/usr/bin/env python3
"""tools/fabric/fleet.py (bin/fabric-fleet): one record per placed agent,
sections by cost class, a shared cache. Every source is a fake program
behind Ctx.run, so the cases pin the library's own rules: a failing source
is a value (never a crash, never an absent agent), the cache is reused
across processes only while fresh and never holds a failure, the executor
is used for another host's /proc, and the command line refuses with one
line."""
from __future__ import annotations

import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import fleet  # noqa: E402

REGISTRY = {
    "hosts": {"h1": {"ssh": None, "platform": "linux", "operator": "op"}, "h2": {"ssh": "op@h2", "platform": "linux", "operator": "op"}},
    "placement": {"a": "h1", "b": "h1", "c": "h2", "hum": "h1"},
    "kinds": {"hum": "human"},
}


def done(out: str = "", err: str = "", rc: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], rc, out, err)


def ctl_rows(op: str, logins=("a", "b", "c"), **per) -> str:
    """What fabric-ctl --json prints for an op: the op's result under its key
    (`machine` for host, the flattened usage_status for usage), and no row for
    a human login (ctl.mjs drops it from `all`)."""
    rows = []
    for login in logins:
        row = {"account": login, "host": "x", "status": "ok", "op": op, "latency_ms": 5, "agentd": {"pid": 1}}
        if op == "usage":
            row["usage_status"] = "ok"
        else:
            row["machine" if op == "host" else op] = {"login": login}
        row.update(per.get(login, {}))
        rows.append(json.dumps(row))
    return "\n".join(rows) + "\n"


class Fleet:
    """A fixture root with a registry, a fake clock, a recording fake runner."""

    def __init__(self, test: unittest.TestCase, handlers=None, xdg: bool = True, registry=None):
        self.test = test
        self.dir = tempfile.mkdtemp(prefix="fleet-test-")
        test.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))
        os.makedirs(os.path.join(self.dir, "root", "runtime", "hosts"))
        with open(os.path.join(self.dir, "root", "runtime", "hosts", "registry.json"), "w") as fh:
            json.dump(registry or REGISTRY, fh)
        self.root = os.path.join(self.dir, "root")
        self.xdg = os.path.join(self.dir, "xdg")
        os.makedirs(self.xdg, mode=0o700)
        self.t = 1_800_000_000.0
        self.calls: list[list[str]] = []
        self.handlers = handlers or {}
        self.env = {"XDG_RUNTIME_DIR": self.xdg} if xdg else {}
        self.sampled: list[list[str]] = []
        old = os.environ.pop("AGENT_FABRIC_HOSTS_REGISTRY", None)
        test.addCleanup(lambda: os.environ.__setitem__("AGENT_FABRIC_HOSTS_REGISTRY", old) if old is not None else None)

    def run(self, argv, timeout, cwd, env):
        self.calls.append(list(argv))
        name = os.path.basename(argv[0])
        key = (name, argv[2] if name == "fabric-ctl" else argv[1] if name == "fabric-host" else "")
        h = self.handlers.get(key) or self.handlers.get(name)
        if h is None:
            raise AssertionError(f"unexpected program {argv}")
        return h(argv) if callable(h) else h

    def sample(self, logins, host):
        self.sampled.append(list(logins))
        return {"agents": {l: {"uid": 1, "cpu_pct": 1.0, "rss_kb": 10, "swap_kb": 0, "procs": 1} for l in logins if l != "nouser"}}

    def ctx(self) -> fleet.Ctx:
        return fleet.Ctx(root=self.root, ssh_hosts=frozenset({"h2"}), run=self.run, clock=lambda: self.t, here="h1", env=self.env, sample=self.sample)

    def fetch(self, sections, **kw):
        return fleet.fetch(sections, root=self.root, ctx=self.ctx(), **kw)

    def ctl_calls(self, op):
        return [c for c in self.calls if os.path.basename(c[0]) == "fabric-ctl" and c[2] == op]


def ctl_handlers(**ops):
    return {("fabric-ctl", op): (lambda argv, op=op, rows=rows: done(rows if isinstance(rows, str) else ctl_rows(op))) for op, rows in ops.items()}


def rec(doc, login, section):
    return next(a for a in doc["agents"] if a["login"] == login)["sections"][section]


class Records(unittest.TestCase):
    def test_one_record_per_placed_agent_and_section_with_src_and_at(self):
        f = Fleet(self, ctl_handlers(jobs=True, presence=True))
        f.handlers[("fabric-host", "h2")] = done(json.dumps({"agents": {"c": {"uid": 3, "cpu_pct": 0.0, "rss_kb": 5, "swap_kb": 0, "procs": 1}}}))
        doc = f.fetch(["jobs", "presence", "proc"])
        self.assertEqual([a["login"] for a in doc["agents"]], ["a", "b", "c", "hum"])
        self.assertEqual([a["kind"] for a in doc["agents"]], ["agent", "agent", "agent", "human"])
        self.assertEqual(doc["agents"][2]["address"], "h2/c")
        for a in doc["agents"]:
            for name in ("jobs", "presence", "proc"):
                r = a["sections"][name]
                if a["login"] == "hum" and name != "proc":
                    self.assertEqual((r["status"], r["why"]), ("failed", "op:" + name + ": " + fleet.HUMAN))
                    continue
                self.assertEqual(r["status"], "ok", (a["login"], name, r))
                self.assertRegex(r["at"], r"^20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(rec(doc, "a", "jobs")["src"], "op:jobs")
        self.assertEqual(rec(doc, "a", "jobs")["data"], {"jobs": {"login": "a"}})   # meta keys (account, status, agentd…) are not data

    def test_proc_is_in_process_here_and_through_the_executor_for_another_host(self):
        f = Fleet(self)
        f.handlers[("fabric-host", "h2")] = done(json.dumps({"agents": {"c": {"uid": 3, "cpu_pct": 0.0, "rss_kb": 5, "swap_kb": 0, "procs": 1}}}))
        doc = f.fetch(["proc"])
        self.assertEqual((rec(doc, "a", "proc")["src"], rec(doc, "c", "proc")["src"]), ("proc-local", "hostexec"))
        self.assertEqual(f.sampled, [["a", "b", "hum"]])
        argv = next(c for c in f.calls if os.path.basename(c[0]) == "fabric-host")
        self.assertEqual(argv[1:4], ["h2", "run", "--"])
        self.assertEqual(argv[-2:], ["--login", "c"])
        self.assertIn("@fabric/tools/fabric/fleet_proc.py", argv)

    def test_a_host_is_read_in_process_only_when_it_is_this_one_and_has_no_ssh(self):
        answer = done(json.dumps({"agents": {l: {"uid": 1, "cpu_pct": 0.0, "rss_kb": 1, "swap_kb": 0, "procs": 1} for l in ("a", "b", "c", "hum")}}))
        for here, ssh, srcs in (("h9", {"h2"}, {"hostexec"}), ("h1", {"h1", "h2"}, {"hostexec"})):
            f = Fleet(self, {"fabric-host": answer})
            ctx = f.ctx()
            ctx.here, ctx.ssh_hosts = here, frozenset(ssh)
            doc = fleet.fetch(["proc"], root=f.root, ctx=ctx)
            self.assertEqual({rec(doc, l, "proc")["src"] for l in ("a", "b", "c", "hum")}, srcs, (here, ssh))
            self.assertEqual(f.sampled, [])

    def test_default_sections_leave_out_the_expensive_class(self):
        self.assertNotIn("tokens", fleet.DEFAULT_SECTIONS)
        self.assertNotIn("disk", fleet.DEFAULT_SECTIONS)
        self.assertEqual(set(fleet.expand("C3")), {"tokens", "disk"})

    def test_tokens_carries_the_window(self):
        f = Fleet(self, ctl_handlers(tokens=True))
        f.fetch(["tokens"], days=3)
        argv = f.ctl_calls("tokens")[0]
        self.assertEqual(argv[argv.index("--days"):argv.index("--days") + 2], ["--days", "3"])

    def test_states_rows_are_keyed_by_address(self):
        rows = "\n".join(json.dumps({"address": f"h1/{l}", "state": "idle", "sessions": []}) for l in ("a", "b")) + "\n"
        f = Fleet(self, {("fabric-ctl", "states"): done(rows)})
        doc = f.fetch(["states"])
        self.assertEqual(rec(doc, "a", "states")["data"], {"state": "idle", "sessions": []})
        self.assertEqual(rec(doc, "c", "states")["status"], "failed")
        self.assertIn("no row for this agent", rec(doc, "c", "states")["why"])
        self.assertIn(fleet.HUMAN, rec(doc, "hum", "states")["why"])


class Failures(unittest.TestCase):
    def failed_everywhere(self, doc, section, why):
        for a in doc["agents"]:
            if a["kind"] == "human":
                continue   # said as a human, not as the failure (HumanLogins)
            r = a["sections"][section]
            self.assertEqual(r["status"], "failed", (a["login"], r))
            self.assertIn(why, r["why"])
            self.assertIn("at", r)
            self.assertNotIn("data", r)

    def test_a_timeout_a_missing_program_and_an_empty_answer_are_told_apart(self):
        def hang(_argv):
            raise subprocess.TimeoutExpired("fabric-ctl", 90)

        def missing(_argv):
            raise FileNotFoundError("fabric-ctl")
        f = Fleet(self, {("fabric-ctl", "jobs"): hang, ("fabric-ctl", "usage"): missing,
                         ("fabric-ctl", "host"): done("", "fabric-ctl: not a host operator\n", 2)})
        doc = f.fetch(["jobs", "usage", "host"])
        self.failed_everywhere(doc, "jobs", "did not answer within 90 s")
        self.failed_everywhere(doc, "usage", "fabric-ctl not found")
        self.failed_everywhere(doc, "host", "fabric-ctl: not a host operator")
        self.assertEqual(len(doc["agents"]), 4, "no agent goes absent")

    def test_one_agent_that_did_not_answer_is_that_agents_failure_only(self):
        f = Fleet(self, {("fabric-ctl", "jobs"): done(ctl_rows("jobs", b={"status": "no answer"}))})
        doc = f.fetch(["jobs"])
        self.assertEqual([rec(doc, l, "jobs")["status"] for l in ("a", "b", "c")], ["ok", "failed", "ok"])
        self.assertIn("no answer", rec(doc, "b", "jobs")["why"])

    def test_a_failing_section_leaves_the_others_whole(self):
        f = Fleet(self, {("fabric-ctl", "jobs"): done("", "boom\n", 2), ("fabric-ctl", "presence"): done(ctl_rows("presence"))})
        doc = f.fetch(["jobs", "presence"])
        self.assertTrue(all(rec(doc, l, "presence")["status"] == "ok" for l in ("a", "b", "c")))
        self.assertTrue(all(a["sections"]["jobs"]["status"] == "failed" for a in doc["agents"]))

    def test_a_source_that_raises_unexpectedly_is_a_failed_record_naming_it(self):
        def bug(_argv):
            raise RuntimeError("surprise")
        f = Fleet(self, {("fabric-ctl", "jobs"): bug})
        self.failed_everywhere(f.fetch(["jobs"]), "jobs", "internal error (RuntimeError: surprise)")

    def test_sources_are_tried_in_order_and_the_whys_are_all_kept(self):
        calls = []

        def bad(ctx, agents):
            calls.append("bad")
            raise fleet.SourceError("first is down")

        def good(ctx, agents):
            calls.append("good")
            return {a.login: {"v": 1} for a in agents if a.login != "b"}
        f = Fleet(self)
        sec = fleet.Section("x", "C1", 30, (fleet.Source("s1", bad), fleet.Source("s2", good)))
        recs = fleet.read_section(f.ctx(), sec, list(fleet.load_placements(f.root).values()))
        self.assertEqual(calls, ["bad", "good"])
        self.assertEqual((recs["a"]["status"], recs["a"]["src"]), ("ok", "s2"))
        self.assertEqual(recs["b"]["status"], "failed")
        self.assertEqual(recs["b"]["why"], "s1: first is down; s2: no row for this agent")

    def test_a_proc_host_without_the_account_is_failed_for_that_login_only(self):
        f = Fleet(self)
        f.handlers[("fabric-host", "h2")] = done(json.dumps({"agents": {}}))
        doc = f.fetch(["proc"])
        self.assertEqual(rec(doc, "c", "proc")["status"], "failed")
        self.assertEqual(rec(doc, "a", "proc")["status"], "ok")

    def test_an_unreadable_executor_answer_is_failed_with_its_cause(self):
        f = Fleet(self)
        f.handlers[("fabric-host", "h2")] = done("not json", "ssh: connect refused\n", 255)
        self.assertIn("ssh: connect refused", rec(f.fetch(["proc"]), "c", "proc")["why"])


class OpResults(unittest.TestCase):
    def row(self, **kw):
        return json.dumps({"account": "a", "host": "x", "status": "ok", "op": "jobs", "agentd": {}, **kw}) + "\n"

    def why(self, op, text, agent="a"):
        f = Fleet(self, {("fabric-ctl", op): done(text)})
        r = rec(f.fetch([op], agent=agent), agent, op)
        return r["status"], r.get("why")

    def test_an_op_that_threw_inside_the_control_agent_is_that_agents_failure(self):
        st, why = self.why("jobs", self.row(jobs={"status": "failed", "error": "EACCES jobs.json"}))
        self.assertEqual((st, why), ("failed", "op:jobs: jobs failed: EACCES jobs.json"))

    def test_a_missing_result_is_a_failure_not_empty_data(self):
        st, why = self.why("jobs", self.row(jobs=None))
        self.assertEqual(st, "failed")
        self.assertIn("answered without a jobs result", why)

    def test_usage_and_host_are_judged_by_the_keys_ctl_flattens_them_to(self):
        self.assertEqual(self.why("usage", self.row(op="usage", usage_status="read-failed"))[0], "failed")
        self.assertEqual(self.why("usage", self.row(op="usage", usage_status=None))[0], "failed")
        self.assertEqual(self.why("host", self.row(op="host", machine={"status": "failed", "error": "x"}))[0], "failed")
        self.assertEqual(self.why("host", self.row(op="host", machine=None))[0], "failed")

    def test_other_statuses_are_answers_left_for_the_reader(self):
        for op, kw in (("host", {"machine": {"status": "partial"}}), ("accounts", {"accounts": {"status": "none"}}),
                       ("tokens", {"tokens": {"status": "no-records"}}), ("usage", {"usage_status": "not-signed-in"})):
            f = Fleet(self, {("fabric-ctl", op): done(self.row(op=op, **kw))})
            r = rec(f.fetch([op], agent="a"), "a", op)
            self.assertEqual(r["status"], "ok", (op, r))

    def test_a_failed_result_is_not_cached_as_a_success(self):
        f = Fleet(self, {("fabric-ctl", "jobs"): done(self.row(jobs={"status": "failed"}))})
        f.fetch(["jobs"], agent="a")
        f.fetch(["jobs"], agent="a")
        self.assertEqual(len(f.ctl_calls("jobs")), 2)


class HumanLogins(unittest.TestCase):
    def test_a_human_is_said_so_and_never_asked_of_a_control_agent(self):
        f = Fleet(self, ctl_handlers(jobs=True, presence=True))
        f.handlers["fabric-host"] = done("[]")   # a jobs file that would answer, if asked
        doc = f.fetch(["jobs", "presence", "states", "closed_jobs"], agent="hum")
        for n in ("jobs", "presence", "states", "closed_jobs"):
            self.assertIn(fleet.HUMAN, rec(doc, "hum", n)["why"])
        self.assertEqual(f.calls, [], "fabric-ctl refuses a human by name; it is not called")

    def test_a_single_agent_ask_among_humans_still_targets_that_login(self):
        f = Fleet(self, ctl_handlers(jobs=True))
        f.fetch(["jobs"], agent="a")
        self.assertEqual(f.ctl_calls("jobs")[0][1], "a")


class TwoRemoteHosts(unittest.TestCase):
    REG = {"hosts": {"h1": {"ssh": None}, "h2": {"ssh": "op@h2"}, "h3": {"ssh": "op@h3"}},
           "placement": {"a": "h1", "c": "h2", "d": "h3"}}

    def test_one_host_down_fails_its_own_agents_only_and_without_noise(self):
        def host(argv):
            if argv[1] == "h3":
                raise subprocess.TimeoutExpired("fabric-host", 60)
            return done(json.dumps({"agents": {"c": {"uid": 3, "cpu_pct": 0.0, "rss_kb": 5, "swap_kb": 0, "procs": 1}}}))
        f = Fleet(self, {"fabric-host": host}, registry=self.REG)
        ctx = f.ctx()
        ctx.ssh_hosts = frozenset({"h2", "h3"})
        doc = fleet.fetch(["proc"], root=f.root, ctx=ctx)
        self.assertEqual([rec(doc, l, "proc")["status"] for l in ("a", "c", "d")], ["ok", "ok", "failed"])
        self.assertEqual(rec(doc, "d", "proc")["why"], "hostexec: h3: fabric-host did not answer within 60 s")
        self.assertEqual(rec(doc, "c", "proc")["src"], "hostexec")


class Prs(unittest.TestCase):
    def test_rows_belong_to_the_owner_the_ref_names_and_others_are_ignored(self):
        doc = {"base": "origin/main", "fetch_ok": True, "prs_ok": True, "rows": [
            {"owner": "h1/a", "branch": "h1/a/feat/x", "pr": 7, "ahead": 3, "last_commit": "t", "paths_total": 2, "paths": ["p"]},
            {"owner": "h1/a", "branch": "h1/a/feat/y", "pr": "none", "ahead": 1, "last_commit": "t", "paths_total": 1},
            {"owner": "unattributed", "branch": "stray", "pr": 9}]}
        f = Fleet(self, {"pr-gate.sh": done(json.dumps(doc))})
        out = f.fetch(["prs"])
        self.assertEqual([p["pr"] for p in rec(out, "a", "prs")["data"]["prs"]], [7, "none"])
        self.assertNotIn("paths", rec(out, "a", "prs")["data"]["prs"][0])
        self.assertEqual(rec(out, "b", "prs")["data"]["prs"], [])
        self.assertEqual(f.calls[0][1:], ["--in-flight", "--json"])

    def test_partial_gate_exit_with_rows_is_an_answer_that_says_what_it_lacked(self):
        doc = {"base": "origin/main", "fetch_ok": False, "prs_ok": True, "rows": []}
        f = Fleet(self, {"pr-gate.sh": done(json.dumps(doc), "pr-gate: git fetch origin failed\n", 2)})
        data = rec(f.fetch(["prs"]), "a", "prs")["data"]
        self.assertEqual((data["fetch_ok"], data["prs"]), (False, []))

    def test_no_output_is_failed_with_the_gate_stderr(self):
        f = Fleet(self, {"pr-gate.sh": done("", "pr-gate: the base origin/main is not in this clone\n", 2)})
        self.assertIn("the base origin/main is not in this clone", rec(f.fetch(["prs"]), "a", "prs")["why"])


class ClosedJobs(unittest.TestCase):
    def test_only_done_and_dropped_newest_first_capped_and_per_agent_failure(self):
        jobs = [{"id": f"j{i}", "title": "t", "state": "done", "updated": f"2026-10-{i:02d}T00:00:00Z"} for i in range(1, 26)]
        jobs += [{"id": "o", "state": "active", "updated": "2027"}, {"id": "d", "state": "dropped", "updated": "2026-10-30T00:00:00Z"}]

        def host(argv):
            who = argv[argv.index("--as") + 1]
            return done(json.dumps(jobs)) if who == "a" else done("", "sudo: a password is required\n", 1)
        f = Fleet(self, {"fabric-host": host})
        out = f.fetch(["closed_jobs"])
        d = rec(out, "a", "closed_jobs")["data"]
        self.assertEqual((d["closed_total"], len(d["closed"]), d["closed"][0]["id"]), (26, 20, "d"))
        self.assertNotIn("o", [j["id"] for j in d["closed"]])
        self.assertEqual(rec(out, "b", "closed_jobs")["status"], "failed")
        self.assertIn("sudo: a password is required", rec(out, "b", "closed_jobs")["why"])
        call = next(c for c in f.calls if "--as" in c)
        self.assertEqual(call[-5:], ["--", "fabric-jobs", "list", "--all", "--json"][-5:])

    def test_unreadable_output_is_failed(self):
        f = Fleet(self, {"fabric-host": done("{}")})
        self.assertIn("unreadable output", rec(f.fetch(["closed_jobs"]), "a", "closed_jobs")["why"])


class Cache(unittest.TestCase):
    def setUp(self):
        self.f = Fleet(self, ctl_handlers(jobs=True))

    def test_a_fresh_entry_is_reused_by_another_process_and_a_stale_one_is_not(self):
        self.f.fetch(["jobs"])
        n = len(self.f.ctl_calls("jobs"))
        self.f.t += 29
        self.f.fetch(["jobs"])
        self.assertEqual(len(self.f.ctl_calls("jobs")), n, "within the 30 s TTL: no new call")
        self.f.t += 2
        self.f.fetch(["jobs"])
        self.assertEqual(len(self.f.ctl_calls("jobs")), n + 1, "past it: read again")

    def test_max_age_overrides_the_ttl_and_zero_forces(self):
        self.f.fetch(["jobs"])
        self.f.t += 100
        self.f.fetch(["jobs"], max_age=200)
        self.assertEqual(len(self.f.ctl_calls("jobs")), 1)
        self.f.fetch(["jobs"], max_age=0)
        self.assertEqual(len(self.f.ctl_calls("jobs")), 2)
        self.f.fetch(["jobs"], max_age=0)
        self.assertEqual(len(self.f.ctl_calls("jobs")), 3, "zero forces a read even in the same instant")

    def test_the_cached_record_keeps_its_original_at(self):
        first = self.f.fetch(["jobs"])
        self.f.t += 10
        again = self.f.fetch(["jobs"])
        self.assertEqual(rec(again, "a", "jobs")["at"], rec(first, "a", "jobs")["at"])
        self.assertNotEqual(again["at"], first["at"])

    def test_one_agent_asked_does_not_make_the_rest_look_fresh(self):
        self.f.fetch(["jobs"], agent="a")
        self.assertEqual(self.f.ctl_calls("jobs")[0][1], "a")
        doc = self.f.fetch(["jobs"])
        self.assertEqual([c[1] for c in self.f.ctl_calls("jobs")], ["a", "all"], "the three others in one call")
        self.assertEqual(len(doc["agents"]), 4)
        self.assertTrue(all(rec(doc, l, "jobs")["status"] == "ok" for l in ("a", "b", "c")))

    def test_a_failure_is_never_cached(self):
        f = Fleet(self, {("fabric-ctl", "jobs"): done("", "down\n", 2)})
        f.fetch(["jobs"])
        f.fetch(["jobs"])
        self.assertEqual(len(f.ctl_calls("jobs")), 2)

    def test_the_files_are_private_and_nothing_else_is_left_in_the_directory(self):
        self.f.fetch(["jobs"])
        d = os.path.join(self.f.xdg, "fabric-fleet")
        self.assertEqual(stat.S_IMODE(os.stat(d).st_mode), 0o700)
        self.assertEqual(os.listdir(d), ["jobs.json"])
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(d, "jobs.json")).st_mode), 0o600)

    def test_a_torn_or_foreign_cache_file_is_a_miss(self):
        self.f.fetch(["jobs"])
        path = os.path.join(self.f.xdg, "fabric-fleet", "jobs.json")
        for junk in ("{not json", "[]", json.dumps({"agents": {"a": {"t": "x", "record": 3}}})):
            with open(path, "w") as fh:
                fh.write(junk)
            n = len(self.f.ctl_calls("jobs"))
            self.assertEqual(rec(self.f.fetch(["jobs"]), "a", "jobs")["status"], "ok")
            self.assertEqual(len(self.f.ctl_calls("jobs")), n + 1, junk)

    def test_without_a_runtime_dir_there_is_no_cache_and_the_answer_says_so(self):
        f = Fleet(self, ctl_handlers(jobs=True), xdg=False)
        a = f.fetch(["jobs"])
        f.fetch(["jobs"])
        self.assertEqual(len(f.ctl_calls("jobs")), 2)
        self.assertEqual(a["cache"], {"usable": False, "why": "XDG_RUNTIME_DIR is not set"})
        self.assertNotIn("cache", self.f.fetch(["jobs"]))

    def test_a_cache_directory_of_another_user_is_refused(self):
        self.f.fetch(["jobs"])
        real = os.geteuid
        os.geteuid = lambda: real() + 1
        try:
            doc = self.f.fetch(["jobs"], max_age=0)
        finally:
            os.geteuid = real
        self.assertFalse(doc["cache"]["usable"])

    def test_a_linked_or_open_cache_directory_is_refused(self):
        target = os.path.join(self.f.dir, "elsewhere")
        os.makedirs(target, mode=0o700)
        os.symlink(target, os.path.join(self.f.xdg, "fabric-fleet"))
        self.assertFalse(self.f.fetch(["jobs"])["cache"]["usable"])
        self.assertEqual(os.listdir(target), [], "nothing written through the link")
        os.unlink(os.path.join(self.f.xdg, "fabric-fleet"))
        os.mkdir(os.path.join(self.f.xdg, "fabric-fleet"), 0o755)
        os.chmod(os.path.join(self.f.xdg, "fabric-fleet"), 0o755)
        self.assertFalse(self.f.fetch(["jobs"])["cache"]["usable"])


class Tokens(unittest.TestCase):
    def test_a_window_is_part_of_what_was_cached(self):
        f = Fleet(self, ctl_handlers(tokens=True))
        f.fetch(["tokens"], days=7)
        f.fetch(["tokens"], days=7)
        self.assertEqual(len(f.ctl_calls("tokens")), 1)
        f.fetch(["tokens"], days=30)
        self.assertEqual(len(f.ctl_calls("tokens")), 2)
        argv = f.ctl_calls("tokens")[1]
        self.assertEqual(argv[argv.index("--days"):argv.index("--days") + 2], ["--days", "30"])
        self.assertEqual(sorted(os.listdir(os.path.join(f.xdg, "fabric-fleet"))), ["tokens-30.json", "tokens-7.json"])


class RunProgram(unittest.TestCase):
    def test_a_timeout_kills_the_children_the_program_started_too(self):
        d = tempfile.mkdtemp(prefix="fleet-run-")
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        pidfile = os.path.join(d, "pid")
        began = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            fleet.run_program(["sh", "-c", f"sleep 60 & echo $! > {pidfile}; wait"], timeout=1)
        # A survivor holding the pipe open would keep communicate() waiting for it.
        self.assertLess(time.monotonic() - began, 20)
        with open(pidfile) as fh:
            pid = int(fh.read())
        for _ in range(50):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        else:
            os.kill(pid, 9)
            self.fail("the grandchild outlived the timeout")

    def test_a_finished_program_returns_its_streams_and_status(self):
        p = fleet.run_program(["sh", "-c", "echo out; echo err >&2; exit 3"], timeout=10)
        self.assertEqual((p.returncode, p.stdout, p.stderr), (3, "out\n", "err\n"))


class Command(unittest.TestCase):
    def main(self, *argv, fetcher=None):
        out, err = io.StringIO(), io.StringIO()
        old = fleet.fetch
        if fetcher:
            fleet.fetch = fetcher
        try:
            with redirect_stdout(out), redirect_stderr(err):
                rc = fleet.main(list(argv))
        finally:
            fleet.fetch = old
        return rc, out.getvalue(), err.getvalue()

    def test_refusals_are_one_line_exit_2_and_nothing_on_stdout(self):
        for args, word in (([], "--json is required"), (["--json", "--max-age", "x"], "needs a number"),
                           (["--json", "--max-age", "-1"], "out of range"), (["--json", "--days", "0"], "out of range"),
                           (["--json", "--agent"], "needs a value"), (["--json", "--section", ","], "names no section"),
                           (["--json", "--wat"], "unknown argument"),
                           (["--json", "--days", "3"], "--days applies to the tokens section"),
                           (["--json", "--days", "3", "--section", "jobs"], "--days applies to the tokens section")):
            rc, out, err = self.main(*args)
            self.assertEqual((rc, out), (2, ""), args)
            self.assertEqual(len(err.strip().splitlines()), 1, args)
            self.assertIn(word, err)

    def test_options_reach_fetch_and_the_answer_is_one_json_object(self):
        seen = {}

        def fake(sections, agent, max_age, days=None):
            seen.update(sections=sections, agent=agent, max_age=max_age, days=days)
            return {"schema": 1, "agents": []}
        rc, out, _ = self.main("--json", "--agent", "a", "--section", "C0,jobs,tokens", "--max-age", "7", "--days", "2", fetcher=fake)
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out), {"schema": 1, "agents": []})
        self.assertEqual(seen, {"sections": ["proc", "states", "presence", "jobs", "tokens"], "agent": "a", "max_age": 7.0, "days": 2})

    def test_an_unknown_agent_or_section_is_a_usage_refusal(self):
        f = Fleet(self)
        with self.assertRaisesRegex(fleet.FleetError, "ghost is not a placed account"):
            f.fetch(["jobs"], agent="ghost")
        with self.assertRaisesRegex(fleet.FleetError, "no section nope"):
            f.fetch(["nope"])

    def test_an_unreadable_registry_is_refused_not_guessed(self):
        f = Fleet(self)
        with open(os.path.join(f.root, "runtime", "hosts", "registry.json"), "w") as fh:
            fh.write("{}")
        with self.assertRaisesRegex(fleet.FleetError, "no placement object"):
            f.fetch(["jobs"])


if __name__ == "__main__":
    unittest.main()
