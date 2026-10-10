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
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

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
        self.timeouts: list[float] = []     # the bound each program was given, in call order
        self.handlers = handlers or {}
        self.env = {"XDG_RUNTIME_DIR": self.xdg} if xdg else {}
        self.sampled: list[list[str]] = []
        old = os.environ.pop("AGENT_FABRIC_HOSTS_REGISTRY", None)
        test.addCleanup(lambda: os.environ.__setitem__("AGENT_FABRIC_HOSTS_REGISTRY", old) if old is not None else None)

    def run(self, argv, timeout, cwd, env):
        self.calls.append(list(argv))
        self.timeouts.append(timeout)
        name = program(argv)
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
            raise subprocess.TimeoutExpired("fabric-ctl", 60)

        def missing(_argv):
            raise FileNotFoundError("fabric-ctl")
        f = Fleet(self, {("fabric-ctl", "jobs"): hang, ("fabric-ctl", "usage"): missing,
                         ("fabric-ctl", "host"): done("", "fabric-ctl: not a host operator\n", 2)})
        doc = f.fetch(["jobs", "usage", "host"])
        self.failed_everywhere(doc, "jobs", "did not answer within 60 s")   # jobs is C1: its class's bound
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
        doc = f.fetch(["jobs", "presence", "states"], agent="hum")
        for n in ("jobs", "presence", "states"):
            self.assertIn(fleet.HUMAN, rec(doc, "hum", n)["why"])
        self.assertEqual(f.calls, [], "fabric-ctl refuses a human by name; it is not called")

    def test_a_humans_closed_jobs_are_never_entered_through_sudo(self):
        f = Fleet(self, {"fabric-host": done("[]")})
        doc = f.fetch(["closed_jobs"])
        self.assertIn("human login", rec(doc, "hum", "closed_jobs")["why"])
        self.assertEqual(rec(doc, "a", "closed_jobs")["status"], "ok", "positive control: the others are asked")
        self.assertNotIn("hum", [c[c.index("--as") + 1] for c in f.calls if "--as" in c])

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
                raise subprocess.TimeoutExpired("fabric-host", 40)
            return done(json.dumps({"agents": {"c": {"uid": 3, "cpu_pct": 0.0, "rss_kb": 5, "swap_kb": 0, "procs": 1}}}))
        f = Fleet(self, {"fabric-host": host}, registry=self.REG)
        ctx = f.ctx()
        ctx.ssh_hosts = frozenset({"h2", "h3"})
        doc = fleet.fetch(["proc"], root=f.root, ctx=ctx)
        self.assertEqual([rec(doc, l, "proc")["status"] for l in ("a", "c", "d")], ["ok", "ok", "failed"])
        self.assertEqual(rec(doc, "d", "proc")["why"], "hostexec: h3: fabric-host did not answer within 40 s")   # proc is C0
        self.assertEqual(rec(doc, "c", "proc")["src"], "hostexec")


    def test_a_malformed_answer_from_one_host_fails_that_host_only(self):
        def host(argv):
            if argv[1] == "h3":
                return done(json.dumps({"agents": None}))
            return done(json.dumps({"agents": {"c": {"uid": 3, "cpu_pct": 0.0, "rss_kb": 5, "swap_kb": 0, "procs": 1}}}))
        f = Fleet(self, {"fabric-host": host}, registry=self.REG)
        ctx = f.ctx()
        ctx.ssh_hosts = frozenset({"h2", "h3"})
        doc = fleet.fetch(["proc"], root=f.root, ctx=ctx)
        self.assertEqual([rec(doc, l, "proc")["status"] for l in ("a", "c", "d")], ["ok", "ok", "failed"])


GATE_ROW = {"title": "t", "head": "abc12345", "work_commits": 3, "fix_commits": 1, "checks": "green", "review": "head reviewed",
            "unresolved_threads": "0", "armed": "no", "queue_position": "", "draft": False, "verdict": "MERGEABLE — ask the owner"}


def gate_row(number, owner, branch, **kw):
    return {"number": number, "owner": owner, "branch": branch, **GATE_ROW, **kw}


def inflight(*rows, **kw):
    return done(json.dumps({"base": "origin/main", "fetch_ok": True, "prs_ok": True, "rows": list(rows), **kw}))


def program(argv):
    """The program a call names; the gate's in-flight read is told from its
    per-PR read, as the two were two programs (pr-gate.sh and fabric-pr)."""
    name = os.path.basename(argv[0])
    return "fabric-pr --in-flight" if name == "fabric-pr" and "--in-flight" in argv else name


def pr_handlers(inflight_out, gate_out=(), origin="git@github.com:BlueTeam-OU/agent-fabric.git\n"):
    return {"fabric-pr --in-flight": inflight_out, "fabric-pr": done(json.dumps(list(gate_out))) if isinstance(gate_out, (list, tuple)) else gate_out,
            "git": done(origin)}


class Prs(unittest.TestCase):
    def test_rows_belong_to_the_owner_the_ref_names_and_others_are_ignored(self):
        f = Fleet(self, pr_handlers(inflight(
            {"owner": "h1/a", "branch": "h1/a/feat/x", "pr": 7, "ahead": 3, "last_commit": "t", "paths_total": 2, "paths": ["p"]},
            {"owner": "h1/a", "branch": "h1/a/feat/y", "pr": "none", "ahead": 1, "last_commit": "t", "paths_total": 1},
            {"owner": "unattributed", "branch": "stray", "pr": 9})))
        out = f.fetch(["prs"])
        self.assertEqual([p["pr"] for p in rec(out, "a", "prs")["data"]["prs"]], [7, "none"])
        self.assertNotIn("paths", rec(out, "a", "prs")["data"]["prs"][0])
        self.assertEqual(rec(out, "b", "prs")["data"]["prs"], [])
        self.assertEqual(f.calls[0][1:], ["gate", "--in-flight", "--json"])

    def test_a_row_carries_the_gates_own_fields_the_number_and_the_repo(self):
        f = Fleet(self, pr_handlers(
            inflight({"owner": "h1/a", "branch": "h1/a/feat/x", "pr": 7, "ahead": 3, "last_commit": "t", "paths_total": 2}),
            [gate_row(7, "h1/a", "h1/a/feat/x", title="the title", work_commits=8)]))
        row = rec(f.fetch(["prs"]), "a", "prs")["data"]["prs"][0]
        self.assertEqual({k: row[k] for k in ("pr", "number", "repo", "branch", "ahead", "title", "head", "work_commits", "fix_commits",
                                              "checks", "review", "unresolved_threads", "armed", "queue_position", "draft", "verdict")},
                         {"pr": 7, "number": 7, "repo": "BlueTeam-OU/agent-fabric", "branch": "h1/a/feat/x", "ahead": 3, "title": "the title",
                          "head": "abc12345", "work_commits": 8, "fix_commits": 1, "checks": "green", "review": "head reviewed",
                          "unresolved_threads": "0", "armed": "no", "queue_position": "", "draft": False,
                          "verdict": "MERGEABLE — ask the owner"})
        self.assertNotIn("owner", row)
        self.assertEqual(f.calls[1][1:], ["gate", "--all", "--json"])

    def test_the_repo_is_read_from_the_origin_in_either_url_form_or_is_unknown(self):
        for origin, want in (("https://github.com/BlueTeam-OU/agent-fabric.git\n", "BlueTeam-OU/agent-fabric"),
                             ("git@github.com:o/r\n", "o/r"), ("nonsense\n", None), ("", None)):
            f = Fleet(self, pr_handlers(inflight({"owner": "h1/a", "branch": "b", "pr": 7}), origin=origin))
            self.assertEqual(rec(f.fetch(["prs"]), "a", "prs")["data"]["prs"][0]["repo"], want, origin)
        f = Fleet(self, {**pr_handlers(inflight({"owner": "h1/a", "branch": "b", "pr": 7})), "git": done("", "fatal\n", 128)})
        self.assertIsNone(rec(f.fetch(["prs"]), "a", "prs")["data"]["prs"][0]["repo"])

    def test_a_row_with_no_pr_number_joins_the_gate_by_branch_and_is_listed_once(self):
        for pr in ("unavailable", "none"):
            f = Fleet(self, pr_handlers(inflight({"owner": "h1/a", "branch": "h1/a/feat/x", "pr": pr, "ahead": 3}),
                                        [gate_row(7, "h1/a", "h1/a/feat/x", verdict="BLOCKED: x")]))
            rows = rec(f.fetch(["prs"]), "a", "prs")["data"]["prs"]
            self.assertEqual([(r["pr"], r["number"], r["ahead"], r["verdict"]) for r in rows], [(pr, 7, 3, "BLOCKED: x")], pr)

    def test_a_number_the_gate_lacks_does_not_join_by_branch(self):
        f = Fleet(self, pr_handlers(inflight({"owner": "h1/a", "branch": "h1/a/feat/x", "pr": 5}), [gate_row(9, "h1/a", "h1/a/feat/x")]))
        rows = rec(f.fetch(["prs"]), "a", "prs")["data"]["prs"]
        self.assertEqual(sorted((r["pr"], r["number"], r["gate_found"]) for r in rows), [(5, 5, False), (9, 9, True)])

    def test_gate_found_says_whether_the_pr_was_at_the_gate_and_is_unknown_when_the_gate_was_not_read(self):
        f = Fleet(self, pr_handlers(inflight({"owner": "h1/a", "branch": "h1/a/feat/x", "pr": 7}, {"owner": "h1/a", "branch": "h1/a/feat/y", "pr": 8}),
                                    [gate_row(7, "h1/a", "h1/a/feat/x")]))
        rows = rec(f.fetch(["prs"]), "a", "prs")["data"]["prs"]
        self.assertEqual([(r["number"], r["gate_found"]) for r in rows], [(7, True), (8, False)])
        h = pr_handlers(inflight({"owner": "h1/a", "branch": "b", "pr": 7}))
        h["fabric-pr"] = done("", "gh: no\n", 1)
        self.assertIsNone(rec(Fleet(self, h).fetch(["prs"]), "a", "prs")["data"]["prs"][0]["gate_found"])

    def test_what_two_sections_share_lasts_one_fetch_not_the_ctx(self):
        f = Fleet(self, pr_handlers(inflight({"owner": "h1/a", "branch": "b", "pr": 7})))
        ctx = f.ctx()
        fleet.fetch(["prs"], root=f.root, ctx=ctx, max_age=0)
        fleet.fetch(["prs"], root=f.root, ctx=ctx, max_age=0)
        self.assertEqual(len([c for c in f.calls if program(c) == "fabric-pr --in-flight"]), 2)

    def test_a_pr_the_in_flight_listing_lacks_is_still_there_at_its_gate(self):
        f = Fleet(self, pr_handlers(inflight(), [gate_row(8, "h1/b", "h1/b/feat/z", verdict="BLOCKED: x")]))
        row = rec(f.fetch(["prs"]), "b", "prs")["data"]["prs"][0]
        self.assertEqual((row["number"], row["branch"], row["verdict"], row["ahead"], row["paths_total"]), (8, "h1/b/feat/z", "BLOCKED: x", None, None))

    def test_a_gate_that_could_not_be_read_leaves_the_gate_fields_null_and_says_so(self):
        for gate in (done("", "gh: no\n", 1), done("not json"), "missing"):
            h = pr_handlers(inflight({"owner": "h1/a", "branch": "b", "pr": 7, "ahead": 2}))
            if gate == "missing":
                del h["fabric-pr"]
                h["fabric-pr"] = lambda argv: (_ for _ in ()).throw(FileNotFoundError("fabric-pr"))
            else:
                h["fabric-pr"] = gate
            data = rec(Fleet(self, h).fetch(["prs"]), "a", "prs")["data"]
            self.assertIs(data["gate_ok"], False)
            self.assertTrue(data["gate_why"])
            row = data["prs"][0]
            self.assertEqual((row["pr"], row["ahead"], row["verdict"], row["checks"], row["title"]), (7, 2, None, None, None), gate)

    def test_a_pr_of_no_placed_account_is_kept_at_the_top_never_dropped(self):
        f = Fleet(self, pr_handlers(
            inflight({"owner": "h1/a", "branch": "h1/a/feat/x", "pr": 7}, {"owner": "", "branch": "dependabot/pip/x", "pr": 9, "ahead": 1},
                     {"owner": "h9/ghost", "branch": "h9/ghost/feat/q", "pr": 10}),
            [gate_row(7, "h1/a", "h1/a/feat/x"), gate_row(9, "", "dependabot/pip/x"), gate_row(10, "h9/ghost", "h9/ghost/feat/q")]))
        doc = f.fetch(["prs"])
        un = doc["prs_unplaced"]
        self.assertEqual((un["status"], un["src"]), ("ok", "pr-gate"))
        self.assertEqual(sorted(r["number"] for r in un["data"]["prs"]), [9, 10])
        self.assertEqual([p["number"] for p in rec(doc, "a", "prs")["data"]["prs"]], [7])
        self.assertTrue(all("prs_unplaced" not in a["sections"] for a in doc["agents"]), "a fleet section is not an agent's")
        self.assertIn("prs_unplaced", doc["sections"])
        self.assertEqual(len(f.ctl_calls("x")), 0)
        self.assertEqual(len([c for c in f.calls if program(c) == "fabric-pr --in-flight"]), 1, "one read serves both sections")

    def test_asking_for_unplaced_alone_works_and_asking_for_prs_adds_it(self):
        f = Fleet(self, pr_handlers(inflight({"owner": "", "branch": "stray", "pr": 3}), [gate_row(3, "", "stray")]))
        doc = f.fetch(["prs_unplaced"])
        self.assertEqual(doc["sections"], ["prs_unplaced"])
        self.assertEqual([r["number"] for r in doc["prs_unplaced"]["data"]["prs"]], [3])
        self.assertTrue(all(a["sections"] == {} for a in doc["agents"]))

    def test_the_in_flight_failure_is_that_sections_failure_for_every_agent_and_the_unplaced_list(self):
        f = Fleet(self, pr_handlers(done("", "pr-gate: the base origin/main is not in this clone\n", 2)))
        doc = f.fetch(["prs"])
        self.assertIn("the base origin/main is not in this clone", rec(doc, "a", "prs")["why"])
        self.assertEqual(doc["prs_unplaced"]["status"], "failed")

    def test_partial_gate_exit_with_rows_is_an_answer_that_says_what_it_lacked(self):
        doc = {"base": "origin/main", "fetch_ok": False, "prs_ok": True, "rows": []}
        f = Fleet(self, pr_handlers(done(json.dumps(doc), "pr-gate: git fetch origin failed\n", 2)))
        data = rec(f.fetch(["prs"]), "a", "prs")["data"]
        self.assertEqual((data["fetch_ok"], data["prs"]), (False, []))

    def test_no_output_is_failed_with_the_gate_stderr(self):
        f = Fleet(self, pr_handlers(done("", "pr-gate: the base origin/main is not in this clone\n", 2)))
        self.assertIn("the base origin/main is not in this clone", rec(f.fetch(["prs"]), "a", "prs")["why"])


def ctl_jobs(rows_by_login):
    """What `fabric-ctl <login> jobs --json` prints for one account."""
    def handler(argv):
        login = argv[1]
        if login not in rows_by_login:
            return done(json.dumps({"account": login, "status": "no answer"}) + "\n", "", 1)
        return done(json.dumps({"account": login, "status": "ok", "jobs": {"status": "ok", "jobs": rows_by_login[login]}}) + "\n")
    return handler


def job(job_id, state, *log):
    return {"id": job_id, "state": state, "title": job_id, "log": [{"at": at, "state": s} for at, s in log]}


def without_log(rows):
    """What the control agent's jobs op lists: no log ("the log stays on the account")."""
    return {login: [{k: v for k, v in j.items() if k != "log"} for j in jobs] for login, jobs in rows.items()}


def fullhost(rows_by_login):
    """What `fabric-host H run --as L -- fabric-jobs list --all --json` prints: every job with its log."""
    def handler(argv):
        login = argv[argv.index("--as") + 1]
        return done(json.dumps(rows_by_login[login])) if login in rows_by_login else done("", "sudo: no\n", 1)
    return handler


class Plans(unittest.TestCase):
    """A fleet-scope section: the plans of the login that runs the deck, each
    step with its job's state and the times its job's log gives."""

    def setUp(self):
        import plan as plan_mod
        self.plan = plan_mod
        self.f = Fleet(self, {})
        self.state = os.path.join(self.f.dir, "state")
        os.makedirs(self.state)
        saved = {k: os.environ.get(k) for k in ("AGENT_FABRIC_STATE_DIR", "AGENT_FABRIC_HOSTS_REGISTRY")}
        os.environ["AGENT_FABRIC_STATE_DIR"] = self.state
        os.environ["AGENT_FABRIC_HOSTS_REGISTRY"] = os.path.join(self.f.root, "runtime", "hosts", "registry.json")
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v) for k, v in saved.items()])
        self.me = plan_mod.identity.current_agent()

    def write_plan(self, plan_id, steps, **kw):
        d = os.path.join(self.state, "agents", self.me, "plans")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{plan_id}.json"), "w") as fh:
            json.dump({"id": plan_id, "title": f"title of {plan_id}", "created_at": "2026-10-09T10:00:00Z", "status": "open", "steps": steps, **kw}, fh)

    @staticmethod
    def break_plan(directory):
        with open(os.path.join(directory, "p1.json"), "w") as fh:
            fh.write("{broken")

    def fetch(self, handlers, **kw):
        self.f.handlers = handlers
        return self.f.fetch(["plans"], **kw)

    def test_steps_carry_their_jobs_state_and_the_times_its_log_gives(self):
        self.write_plan("p1", [
            {"id": "s1", "title": "first", "owner": "a", "depends_on": [], "job": "a:j1", "est_days": 2},
            {"id": "s2", "title": "second", "owner": "b", "depends_on": ["s1"], "job": "b:j2"},
            {"id": "s3", "title": "third", "owner": "a", "depends_on": ["s2"], "job": None},
            {"id": "s4", "title": "fourth", "owner": "c", "depends_on": [], "job": None}])
        rows = {"a": [job("j1", "done", ("2026-10-08T10:00:00Z", "queued"), ("2026-10-08T11:00:00Z", "active"), ("2026-10-08T12:00:00Z", "delivered"),
                          ("2026-10-08T13:00:00Z", "done"))],
                "b": [job("j2", "active", ("2026-10-09T09:00:00Z", "queued"), ("2026-10-09T09:30:00Z", "active"))]}
        # j1 is closed (the executor's list), j2 open: the control agent lists it without its log, the executor's list has it.
        doc = self.fetch({("fabric-ctl", "jobs"): ctl_jobs(without_log({"a": [], "b": rows["b"]})), "fabric-host": fullhost(rows)})
        r = doc["plans"]
        self.assertEqual((r["status"], r["src"]), ("ok", "fabric-plan+hostexec"))
        self.assertEqual(r["data"]["login"], self.me)
        (pl,) = r["data"]["plans"]
        self.assertEqual({k: pl[k] for k in ("id", "title", "status", "created_at")},
                         {"id": "p1", "title": "title of p1", "status": "open", "created_at": "2026-10-09T10:00:00Z"})
        steps = {s["id"]: s for s in pl["steps"]}
        self.assertEqual([s["id"] for s in pl["steps"]], ["s1", "s2", "s3", "s4"], "in the plan's order")
        self.assertEqual((steps["s1"]["state"], steps["s1"]["started"], steps["s1"]["finished"], steps["s1"]["est_days"]),
                         ("done", "2026-10-08T11:00:00Z", "2026-10-08T13:00:00Z", 2))
        self.assertEqual((steps["s2"]["state"], steps["s2"]["started"], steps["s2"]["finished"], steps["s2"]["est_days"]),
                         ("active", "2026-10-09T09:30:00Z", None, None))
        self.assertEqual((steps["s3"]["state"], steps["s3"]["reason"], steps["s3"]["started"]), ("waiting", "waits for s2", None))
        self.assertEqual((steps["s4"]["state"], steps["s4"]["job"]), ("planned", None))
        self.assertEqual(sorted(steps["s1"]), ["depends_on", "est_days", "finished", "id", "job", "owner", "reason", "started", "state", "times_why", "title"])
        self.assertEqual(steps["s2"]["depends_on"], ["s1"])

    def test_a_job_that_cannot_be_read_is_unknown_with_its_reason_and_no_times(self):
        self.write_plan("p1", [{"id": "s1", "title": "t", "owner": "a", "depends_on": [], "job": "a:j1"}])
        doc = self.fetch({("fabric-ctl", "jobs"): ctl_jobs({}), "fabric-host": done("", "no\n", 1)})
        (s,) = doc["plans"]["data"]["plans"][0]["steps"]
        self.assertEqual((s["state"], s["started"], s["finished"], s["times_why"]), ("unknown", None, None, None))
        self.assertIn("a:j1", s["reason"] + "a:j1")
        self.assertTrue(s["reason"])

    def test_an_open_jobs_times_come_from_the_full_list_not_the_control_agents_logless_row(self):
        self.write_plan("p1", [{"id": "s1", "title": "t", "owner": "a", "depends_on": [], "job": "a:j1"}])
        rows = {"a": [job("j1", "delivered", ("t1", "queued"), ("t2", "active"), ("t3", "delivered"))]}
        (s,) = self.fetch({("fabric-ctl", "jobs"): ctl_jobs(without_log(rows)), "fabric-host": fullhost(rows)})["plans"]["data"]["plans"][0]["steps"]
        self.assertEqual((s["state"], s["started"], s["finished"], s["times_why"]), ("delivered", "t2", "t3", None))

    def test_times_that_cannot_be_read_are_null_with_the_why_never_a_silent_never(self):
        self.write_plan("p1", [{"id": "s1", "title": "t", "owner": "a", "depends_on": [], "job": "a:j1"},
                               {"id": "s2", "title": "t", "owner": "b", "depends_on": [], "job": "b:j2"}])
        open_rows = without_log({"a": [job("j1", "active")], "b": [job("j2", "active")]})
        (s1, s2) = self.fetch({("fabric-ctl", "jobs"): ctl_jobs(open_rows),
                               "fabric-host": fullhost({"b": [job("jother", "active", ("t1", "active"))]})})["plans"]["data"]["plans"][0]["steps"]
        self.assertEqual((s1["state"], s1["started"], s1["finished"]), ("active", None, None))
        self.assertIn("a's full job list", s1["times_why"])
        self.assertEqual((s2["started"], s2["times_why"]), (None, "b:j2 is not on b's full job list"))

    def test_a_fleet_section_is_at_the_top_of_the_document_and_in_no_agents_record(self):
        self.write_plan("p1", [])
        doc = self.fetch({})
        self.assertEqual(doc["sections"], ["plans"])
        self.assertTrue(all(a["sections"] == {} for a in doc["agents"]))
        self.assertEqual(doc["plans"]["data"]["plans"][0]["steps"], [])

    def test_plans_are_named_not_default(self):
        self.assertNotIn("plans", fleet.DEFAULT_SECTIONS)
        self.assertIn("prs_unplaced", fleet.DEFAULT_SECTIONS)
        self.assertEqual(fleet.expand("C2"), ["prs", "prs_unplaced", "plans", "closed_jobs", "accounts"])

    def test_a_login_with_no_plans_answers_an_empty_list_and_says_whose(self):
        doc = self.fetch({})
        self.assertEqual((doc["plans"]["status"], doc["plans"]["data"]), ("ok", {"login": self.me, "plans": []}))

    def test_an_unreadable_plan_file_is_the_sections_failure_naming_it(self):
        d = os.path.join(self.state, "agents", self.me, "plans")
        os.makedirs(d)
        self.break_plan(d)
        r = self.fetch({})["plans"]
        self.assertEqual(r["status"], "failed")
        self.assertIn("p1.json", r["why"])

    def test_a_failed_refresh_shows_the_last_plans_as_stale(self):
        self.write_plan("p1", [])
        self.fetch({})
        d = os.path.join(self.state, "agents", self.me, "plans")
        self.break_plan(d)
        self.f.t += 300
        r = self.f.fetch(["plans"])["plans"]
        self.assertEqual((r["status"], r["age_s"], r["data"]["plans"][0]["id"]), ("stale", 300, "p1"))
        self.assertIn("p1.json", r["why"])

    def test_log_times_first_active_and_last_done_dropped_or_delivered(self):
        lt = fleet.log_times
        self.assertEqual(lt(job("j", "done", ("t1", "queued"), ("t2", "active"), ("t3", "blocked"), ("t4", "active"), ("t5", "delivered"), ("t6", "done"))), ("t2", "t6"))
        self.assertEqual(lt(job("j", "dropped", ("t1", "queued"), ("t2", "dropped"))), (None, "t2"))
        self.assertEqual(lt(job("j", "delivered", ("t1", "active"), ("t2", "delivered"))), ("t1", "t2"))
        self.assertEqual(lt(job("j", "queued", ("t1", "queued"))), (None, None))
        for odd in (None, {}, {"log": "x"}, {"log": [None, {"state": "active"}, {"at": 5, "state": "done"}]}):
            self.assertEqual(lt(odd), (None, None), odd)


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
        self.assertEqual(d["done_total"], 25, "done alone: the dropped one is in closed_total, not here")
        self.assertEqual(rec(out, "b", "closed_jobs")["status"], "failed")
        self.assertIn("sudo: a password is required", rec(out, "b", "closed_jobs")["why"])
        call = next(c for c in f.calls if "--as" in c)
        self.assertEqual(call[-5:], ["--", "fabric-jobs", "list", "--all", "--json"][-5:])

    def test_unreadable_output_is_failed(self):
        f = Fleet(self, {"fabric-host": done("{}")})
        self.assertIn("unreadable output", rec(f.fetch(["closed_jobs"]), "a", "closed_jobs")["why"])


class Timeouts(unittest.TestCase):
    """Each section's program is bound by its cost class: fabric-ctl waits
    `ctl` seconds for the replies, and the whole program gets `call`."""

    def bounds(self, section, handlers, **kw):
        f = Fleet(self, handlers, registry=kw.pop("registry", None))
        f.fetch([section], **kw)
        ctl = [int(c[c.index("--timeout") + 1]) for c in f.calls if os.path.basename(c[0]) == "fabric-ctl"]
        return ctl, f.timeouts

    def test_each_cost_class_has_its_own_ctl_wait_and_program_bound(self):
        for section, cls in (("presence", "C0"), ("jobs", "C1"), ("accounts", "C2"), ("tokens", "C3")):
            ctl, bound = self.bounds(section, ctl_handlers(**{section: True}))
            want_ctl, want_call, _ = fleet.COST_CLASSES[cls]
            self.assertEqual((ctl, bound), ([want_ctl], [want_call]), (section, cls))
        self.assertEqual([fleet.COST_CLASSES[c][0] for c in ("C0", "C1", "C2", "C3")], sorted(fleet.COST_CLASSES[c][0] for c in fleet.COST_CLASSES),
                         "a dearer class waits longer")

    def test_states_prs_closed_jobs_and_the_remote_proc_use_their_class_too(self):
        states = {("fabric-ctl", "states"): done(json.dumps({"address": "h1/a", "sessions": []}) + "\n")}
        ctl, bound = self.bounds("states", states)
        self.assertEqual((ctl, bound), ([fleet.COST_CLASSES["C0"][0]], [fleet.COST_CLASSES["C0"][1]]))
        gate = {"fabric-pr --in-flight": done(json.dumps({"rows": [], "fetch_ok": True, "prs_ok": True, "base": "main"})),
                "fabric-pr": done("[]"), "git": done("git@github.com:o/r.git\n")}
        f = Fleet(self, gate)
        f.fetch(["prs"])
        by_program = {program(c): b for c, b in zip(f.calls, f.timeouts)}
        self.assertEqual((by_program["fabric-pr --in-flight"], by_program["fabric-pr"]), (fleet.COST_CLASSES["C2"][1],) * 2)
        jobs = {"fabric-host": done("[]")}
        _, bound = self.bounds("closed_jobs", jobs)
        self.assertEqual(set(bound), {fleet.COST_CLASSES["C2"][1]})
        remote = {"fabric-host": done(json.dumps({"agents": {"c": {"uid": 3, "cpu_pct": 0.0, "rss_kb": 5, "swap_kb": 0, "procs": 1}}}))}
        _, bound = self.bounds("proc", remote)
        self.assertEqual(bound, [fleet.COST_CLASSES["C0"][1]], "h2's agents through the executor")

    def test_a_hand_made_ctx_outside_any_section_keeps_the_old_defaults(self):
        self.assertEqual((fleet.CTL_TIMEOUT_S, fleet.CALL_TIMEOUT_S), (20, 90))
        ctx = Fleet(self, {}).ctx()
        self.assertEqual((ctx.ctl_s, ctx.call_s), (20, 90))

    def test_plans_use_their_classes_bounds_for_every_program_and_ask_each_login_once(self):
        f = Fleet(self, {("fabric-ctl", "jobs"): ctl_jobs(without_log({"a": [job("j1", "active")]})),
                         "fabric-host": fullhost({"a": [job("j1", "active", ("t1", "active")), job("j2", "done", ("t1", "active"), ("t2", "done"))]})})
        self.write_two_plans(f)
        f.fetch(["plans"])
        hosts = [c for c in f.calls if os.path.basename(c[0]) == "fabric-host"]
        self.assertEqual(len(hosts), 1, "the executor's full list of a is read once for both plans, whoever needs it")
        want_ctl, want_call, _ = fleet.COST_CLASSES["C2"]
        ctl = [c for c in f.calls if os.path.basename(c[0]) == "fabric-ctl"]
        self.assertEqual([int(c[c.index("--timeout") + 1]) for c in ctl], [want_ctl], "one ask of a for two plans, with C2's wait")
        self.assertEqual(set(f.timeouts), {want_call})

    @staticmethod
    def write_two_plans(f):
        import plan as plan_mod
        d = os.path.join(f.dir, "state", "agents", plan_mod.identity.current_agent(), "plans")
        os.makedirs(d, exist_ok=True)
        for n in ("p1", "p2"):
            with open(os.path.join(d, f"{n}.json"), "w") as fh:
                json.dump({"id": n, "title": n, "created_at": "t", "status": "open",
                           "steps": [{"id": "s1", "title": "t", "owner": "a", "depends_on": [], "job": "a:j1"},
                                     {"id": "s2", "title": "t", "owner": "a", "depends_on": [], "job": "a:j2"}]}, fh)
        saved = {k: os.environ.get(k) for k in ("AGENT_FABRIC_STATE_DIR", "AGENT_FABRIC_HOSTS_REGISTRY")}
        os.environ["AGENT_FABRIC_STATE_DIR"] = os.path.join(f.dir, "state")
        os.environ["AGENT_FABRIC_HOSTS_REGISTRY"] = os.path.join(f.root, "runtime", "hosts", "registry.json")
        f.test.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v) for k, v in saved.items()])


class Stale(unittest.TestCase):
    """A slow account reads as old, not unknown: the last good value, with
    its age and the fresh read's failure, until the class's window ends."""

    def setUp(self):
        self.answer = [ctl_rows("jobs")]
        self.f = Fleet(self, {("fabric-ctl", "jobs"): lambda argv: done(self.answer[0])})

    def slow(self, **per):
        self.answer[0] = ctl_rows("jobs", **{k: {"status": "no answer"} for k in per})

    def test_a_failed_refresh_inside_the_window_is_the_last_good_value_with_its_age_and_why(self):
        first = self.f.fetch(["jobs"])
        good = rec(first, "b", "jobs")
        self.slow(b=1)
        self.f.t += 100                                   # past the 30 s TTL, inside C1's 600 s window
        doc = self.f.fetch(["jobs"])
        r = rec(doc, "b", "jobs")
        self.assertEqual({k: r[k] for k in ("status", "src", "at", "age_s", "data")},
                         {"status": "stale", "src": good["src"], "at": good["at"], "age_s": 100, "data": good["data"]})
        self.assertIn("no answer", r["why"])
        self.assertEqual([rec(doc, l, "jobs")["status"] for l in ("a", "c")], ["ok", "ok"], "only the slow account is old")

    def test_the_age_grows_while_the_account_stays_slow_and_the_value_does_not_move(self):
        self.f.fetch(["jobs"])
        self.slow(b=1)
        ages = []
        for _ in range(3):
            self.f.t += 60
            ages.append(rec(self.f.fetch(["jobs"]), "b", "jobs")["age_s"])
        self.assertEqual(ages, [60, 120, 180], "a failed refresh does not evict the last good entry, nor renew it")

    def test_past_the_window_it_is_failed_again_and_unknown_stays_unknown(self):
        self.f.fetch(["jobs"])
        self.slow(b=1)
        self.f.t += fleet.COST_CLASSES["C1"][2] + 1
        r = rec(self.f.fetch(["jobs"]), "b", "jobs")
        self.assertEqual(r["status"], "failed")
        self.assertNotIn("data", r)
        self.f.t -= 5000
        self.assertEqual(rec(self.f.fetch(["jobs"]), "b", "jobs")["status"], "failed", "and the expired entry is gone, not revived")

    def test_the_window_is_the_classes_own(self):
        self.assertEqual([fleet.COST_CLASSES[c][2] for c in ("C0", "C1", "C2", "C3")], [60, 600, 1800, 7200])
        for name, section in fleet.SECTIONS.items():
            self.assertEqual(section.stale_s, fleet.COST_CLASSES[section.cost][2], name)

    def test_an_account_that_answers_again_is_ok_and_fresh(self):
        self.f.fetch(["jobs"])
        self.slow(b=1)
        self.f.t += 100
        self.f.fetch(["jobs"])
        self.answer[0] = ctl_rows("jobs")
        self.f.t += 100
        r = rec(self.f.fetch(["jobs"]), "b", "jobs")
        self.assertEqual((r["status"], r["at"]), ("ok", fleet.stamp(self.f.t)))

    def test_forcing_a_read_with_max_age_zero_still_falls_back_to_the_last_good_value(self):
        self.f.fetch(["jobs"])
        self.slow(b=1)
        self.f.t += 5
        self.assertEqual(rec(self.f.fetch(["jobs"], max_age=0), "b", "jobs")["status"], "stale")

    def test_a_stale_record_is_never_written_back_as_if_it_were_a_reading(self):
        self.f.fetch(["jobs"])
        self.slow(b=1)
        self.f.t += 100
        self.f.fetch(["jobs"])
        with open(os.path.join(self.f.xdg, "fabric-fleet", "jobs.json")) as fh:
            kept = json.load(fh)["agents"]
        self.assertTrue(all(e["record"]["status"] == "ok" for e in kept.values()), kept)
        self.assertEqual(kept["b"]["t"], 1_800_000_000.0, "b's entry is still the original reading")

    def test_without_a_cache_there_is_nothing_old_to_show(self):
        f = Fleet(self, {("fabric-ctl", "jobs"): done(ctl_rows("jobs", b={"status": "no answer"}))}, xdg=False)
        self.assertEqual(rec(f.fetch(["jobs"]), "b", "jobs")["status"], "failed")

    def test_entries_past_the_window_are_dropped_when_the_file_is_written(self):
        self.f.fetch(["jobs"], agent="a")
        self.f.t += fleet.COST_CLASSES["C1"][2] + 1
        self.f.fetch(["jobs"], agent="b")
        with open(os.path.join(self.f.xdg, "fabric-fleet", "jobs.json")) as fh:
            self.assertEqual(sorted(json.load(fh)["agents"]), ["b"])

    def test_the_slow_account_in_a_real_command_line_answer_has_a_value_in_data(self):
        self.f.fetch(["jobs"])
        self.slow(b=1)
        self.f.t += 100
        out = io.StringIO()
        with redirect_stdout(out):
            doc = json.loads(json.dumps(self.f.fetch(["jobs"])))
        r = rec(doc, "b", "jobs")
        self.assertTrue(r["status"] == "stale" and r["data"], r)


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

    def test_a_cache_file_of_another_version_is_a_miss(self):
        self.f.fetch(["jobs"])
        path = os.path.join(self.f.xdg, "fabric-fleet", "jobs.json")
        with open(path) as fh:
            doc = json.load(fh)
        doc["version"] = 1
        with open(path, "w") as fh:
            json.dump(doc, fh)
        n = len(self.f.ctl_calls("jobs"))
        self.f.fetch(["jobs"])
        self.assertEqual(len(self.f.ctl_calls("jobs")), n + 1, "an entry another version wrote is read again, not served")

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
        def alive() -> bool:
            # A killed process nobody reaps (a container's init does not) stays a zombie, and kill(pid, 0) still finds it.
            try:
                with open(f"/proc/{pid}/stat") as fh:
                    return fh.read().rsplit(")", 1)[1].split()[0] != "Z"
            except (FileNotFoundError, ProcessLookupError):   # the second: a /proc entry caught mid-exit
                return False
        for _ in range(50):
            if not alive():
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
