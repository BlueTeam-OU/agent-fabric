#!/usr/bin/env python3
"""tools/fabric/work/: rule 14's table as data, the engine that is the only writer of a job's state, the pool's claims, the REQUEST title.

Pure cases, no process and no network. The command's behaviour per verb is pinned by tests/test_work_lifecycle*.py, which run the
real `fabric-jobs`; this suite holds the owner itself. **Each case names the mutation it kills**:

  the_table_is_the_adrs         <- a row edited in table.py and not in docs/adr/ADR-037 rule 14 (a from-state, a to-state, a verb, a row dropped)
  every_need_has_a_prover       <- a need named in a row that nobody proves, or a prover for a need no row names
  a_verb_is_taken_from_its_states_only <- row_for ignoring `frm`; a row's from-set widened
  an_unproved_need_is_refused   <- the engine's `unproved` check dropped
  a_proof_of_another_job_state_is_refused <- the seal comparison dropped
  one_active_job                <- the engine's own `no_other_active` dropped
  a_closed_job_is_never_reopened <- TERMINAL not refused for a verb whose row names the state
  block_replaces_the_wait_and_switch_adds <- the pop of waits_on/blockers for `block` dropped, or extended to `switch-blocked`
  the_log_and_the_session        <- the log entry, the session tag on entering or leaving active, `last`, the worktree as working copy
  create_makes_a_queued_job     <- create taking a state, a time or a log from the caller; an empty title
  fill_moves_a_list              <- fill into a list that has a job or a counter; two active jobs
  a_claim_has_three_states, claim_refuses_a_closed_claim_to_anyone, close_and_reopen_are_the_holders_rows
  judge_*                       <- each branch of claims.judge (fresh, claims, generation, the day, a claim of this id)
  the_request_title             <- the id dropped on a cut, the last (REQUEST id) not the one, a subject's mention taken
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from instance_fixtures import own_instance_tree  # noqa: E402
own_instance_tree()
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import by_path  # noqa: E402

work = by_path.load_package("fabric_work", os.path.join(ROOT, "tools", "fabric", "work"))
table, claims, Refusal, Proof = work.table, work.claims, work.Refusal, work.Proof
NOW = "2026-11-09T10:00:00Z"
RID = "01a11a18-4728-7d8b-afd9-0edb2d30a59c"
OTHER = "01a11a18-4728-7d8b-afd9-0edb2d30a59d"


def job(state="queued", jid="j1", **kw) -> dict:
    return {"id": jid, "title": "t", "state": state, "artifacts": [], "log": [{"at": NOW, "state": "queued"}], **kw}


def proved(j: dict, who: str, to: str) -> Proof:
    p = Proof(j["id"], work.seal(j))
    for need in table.row_for(who, j["state"], to).needs:
        p.note(need, "shown")
    return p


class Table(unittest.TestCase):
    def adr_rows(self) -> list[tuple[str, str, str, str]]:
        # Only a stripped copy lacks docs/adr/; skipping on the directory, not the file, keeps a renamed or deleted
        # ADR-037 in a full tree a failure instead of a silent skip.
        if not os.path.isdir(os.path.join(ROOT, "docs", "adr")):
            self.skipTest("docs/adr/ is absent (a stripped copy)")
        adr_path = os.path.join(ROOT, "docs", "adr", "ADR-037-each-agent-keeps-a-job-list.md")
        with open(adr_path, encoding="utf-8") as fh:
            text = fh.read()
        start = text.index("    | from | to | who | needs |")
        rows = []
        for line in text[start:].splitlines()[2:]:
            if not line.startswith("    |"):
                break
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            rows.append((cells[0], cells[1], cells[2], cells[3]))
        return rows

    def test_the_table_is_the_adrs(self):
        adr = self.adr_rows()
        self.assertEqual(len(adr), len(table.ROWS), "a row of rule 14 that the table lacks, or the reverse")
        for (frm, to, who, _needs), row in zip(adr, table.ROWS, strict=True):
            states = frozenset(re.findall(r"`(\w+)`", frm))
            self.assertEqual(frozenset(row.frm) if row.frm else frozenset(), frozenset() if frm.startswith("—") else states, row.label)
            to_state = None if "any state" in to else re.findall(r"`(\w+)`", to)[0]
            self.assertEqual(row.to, to_state, row.label)
            self.assertEqual(row.pool, "pool" in frm or ("pool" in to and "queued" not in to) or "pool holder" in who and row.pool, row.label)
            for token in row.who:
                word = {"pool-claim-landed": "pool-claim", "pool-close": "control agent", "pool-reopen": "control agent",
                        "switch-blocked": "switch", "intake": "intake"}.get(token, token)
                self.assertIn(word, who, (row.label, token))

    def test_a_verb_is_taken_from_its_states_only(self):
        for verb, states in {"start": {"queued", "paused", "blocked", "delivered"}, "pause": {"active"}, "deliver": {"active", "blocked"},
                             "done": {"active", "delivered"}, "block": {"queued", "active", "paused", "blocked"},
                             "drop": {"queued", "active", "paused", "blocked", "delivered"}, "sweep": {"delivered"}}.items():
            to = {"start": "active", "pause": "paused", "deliver": "delivered", "done": "done", "block": "blocked", "drop": "dropped",
                  "sweep": "done"}[verb]
            took = {s for s in table.JOB_STATES if table.row_for(verb, s, to)}
            self.assertEqual(took, states, verb)
        self.assertIsNone(table.row_for("start", "done", "active"), "nothing reopens a closed job")
        self.assertIsNone(table.row_for("done", "active", "dropped"), "a verb makes the transitions of its own rows")
        self.assertEqual(table.takes("switch", "active"), ("queued", "paused", "blocked", "delivered"), "start and switch take one set")

    def test_a_closed_job_is_never_reopened(self):
        for state in table.TERMINAL:
            for row in table.ROWS:
                if row.frm and not row.pool:
                    self.assertNotIn(state, row.frm, row.label)

    def test_every_need_has_a_prover(self):
        spec = importlib.util.spec_from_file_location("jobs_for_needs", os.path.join(ROOT, "tools", "fabric", "jobs.py"))
        jobs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(jobs)
        needs = sys.modules["fabric_jobs"].needs
        from fabric_work import lifecycle
        provers = set(needs.NEEDS) | lifecycle.ENGINE_NEEDS | lifecycle.CREATE_NEEDS | claims.NEEDS
        named = {n for row in table.ROWS for n in row.needs}
        self.assertEqual(named - provers, set(), "a need no one proves")
        self.assertEqual(provers - named, set(), "a prover for a need no row names")
        self.assertEqual(needs.WORLD | needs.LOCAL, set(needs.NEEDS), "a need that is neither asked outside the lock nor in it")
        del jobs


class Engine(unittest.TestCase):
    def go(self, doc, j, to, who, proof="auto", **fields):
        proof = proved(j, who, to) if proof == "auto" else proof
        work.transition(doc, j, to, who, proof, now=NOW, session="sess", **fields)

    def test_an_unproved_need_is_refused(self):
        j = job("active")
        with self.assertRaises(Refusal) as e:
            self.go({"jobs": [j]}, j, "delivered", "deliver", proof=None)
        self.assertIn("not proved: artifact_open", str(e.exception))
        short = Proof(j["id"], work.seal(j))
        with self.assertRaises(Refusal):
            self.go({"jobs": [j]}, j, "delivered", "deliver", proof=short)
        self.assertEqual(j["state"], "active")

    def test_a_row_with_only_the_engines_needs_needs_no_proof(self):
        j = job("queued")
        self.assertEqual(table.row_for("drop", "queued", "dropped").needs, ("reason", "request_answered"), "the control: drop asks for proof")
        doc = {"jobs": [j]}
        work.transition(doc, j, "active", "start", proved(j, "start", "active"), now=NOW)
        self.assertEqual(j["state"], "active")

    def test_a_proof_of_another_job_state_is_refused(self):
        j = job("active", artifacts=["o/r#1"])
        proof = proved(j, "deliver", "delivered")
        j["artifacts"].append("o/r#2")        # another session's deliver, between the proof and the change
        with self.assertRaises(Refusal) as e:
            self.go({"jobs": [j]}, j, "delivered", "deliver", proof=proof)
        self.assertIn("changed while deliver was checked", str(e.exception))
        other = proved(job("active", jid="j2"), "deliver", "delivered")
        with self.assertRaises(Refusal):
            self.go({"jobs": [j]}, j, "delivered", "deliver", proof=other)

    def test_one_active_job(self):
        a, b = job("active", jid="j1"), job("queued", jid="j2")
        with self.assertRaises(Refusal) as e:
            self.go({"jobs": [a, b]}, b, "active", "start")
        self.assertIn("one job is active at a time", str(e.exception))
        self.assertEqual(b["state"], "queued")
        doc = {"jobs": [a]}
        self.go(doc, a, "paused", "pause", reason="x")
        self.assertEqual(doc["last"], "j1")

    def test_a_verb_outside_its_rows_names_what_it_takes(self):
        j = job("queued")
        with self.assertRaises(Refusal) as e:
            self.go({"jobs": [j]}, j, "paused", "pause", proof=None)
        self.assertEqual(str(e.exception), "j1 is queued; pause takes a job that is active")
        done = job("done")
        with self.assertRaises(Refusal) as e:
            self.go({"jobs": [done]}, done, "active", "start", proof=None)
        self.assertIn("a closed job is not reopened", str(e.exception))

    def test_block_replaces_the_wait_and_switch_adds(self):
        j = job("blocked", blockers=["pr:o/r#1"], waits_on=RID, blocked_on="pr:o/r#1")
        self.go({"jobs": [j]}, j, "blocked", "block", blocked_on="free", blockers=None)
        self.assertNotIn("blockers", j)
        self.assertNotIn("waits_on", j)
        k = job("blocked", blockers=["request:" + RID], waits_on=RID, blocked_on="x")
        self.go({"jobs": [k]}, k, "blocked", "switch-blocked", blockers=["request:" + RID, "pr:o/r#2"], blocked_on="x; pr:o/r#2")
        self.assertEqual((k["waits_on"], k["blockers"]), (RID, ["request:" + RID, "pr:o/r#2"]))

    def test_the_log_and_the_session(self):
        j = job("queued")
        doc = {"jobs": [j]}
        self.go(doc, j, "active", "start", branch="b", worktree="/w", note="n", reason=None)
        self.assertEqual(j["log"][-1], {"at": NOW, "state": "active", "note": "n", "session": "sess"})
        self.assertEqual((j["branch"], j["worktree"], j["working_copy"], j["updated"]), ("b", "/w", "/w", NOW))
        self.go(doc, j, "delivered", "deliver")
        self.assertEqual(j["log"][-1]["session"], "sess", "leaving active is the session's too")
        k = job("queued", jid="j2")
        self.go({"jobs": [k]}, k, "dropped", "drop", reason="no")
        self.assertNotIn("session", k["log"][-1], "a drop of a job never active is no work done")
        self.assertEqual(k["reason"], "no")

    def test_leaving_blocked_drops_the_wait_and_entering_active_the_reason(self):
        j = job("blocked", blockers=["clock:x"], waits_on=RID, reason="old")
        self.go({"jobs": [j]}, j, "active", "start")
        self.assertEqual({k: v for k, v in j.items() if k in ("blockers", "waits_on", "reason")}, {})

    def test_create_makes_a_queued_job(self):
        doc = {"jobs": [], "seq": 4}
        made = work.create(doc, "add", {"title": "x", "state": "done", "created": "never", "log": ["no"], "source": {"kind": "self"}}, now=NOW)
        self.assertEqual((made["id"], made["state"], made["created"], made["log"], doc["seq"]), ("j5", "queued", NOW, [{"at": NOW, "state": "queued"}], 5))
        self.assertIs(doc["jobs"][-1], made)
        for who in ("start", "deliver", "pool-add"):
            with self.assertRaises(Refusal, msg=who):
                work.create(doc, who, {"title": "x"}, now=NOW)
        with self.assertRaises(Refusal):
            work.create(doc, "intake", {"title": "  "}, now=NOW)
        self.assertEqual(doc["seq"], 5, "a refused job takes no id")

    def test_a_request_is_one_job_whichever_path_makes_it(self):
        doc = {"jobs": [], "seq": 0}
        work.create(doc, "jobs-add", {"title": f"a subject (REQUEST {RID})", "source": {"kind": "owner"}}, now=NOW)
        for fields in ({"title": "again", "source": {"kind": "request", "message_id": RID}},
                       {"title": f"another (REQUEST {RID})", "source": {"kind": "self"}}):
            with self.assertRaises(Refusal):
                work.create(doc, "intake", fields, now=NOW)
        work.create(doc, "intake", {"title": f"see (REQUEST {OTHER}) and mine (REQUEST {RID[:-1]}0)", "source": {"kind": "request", "message_id": RID[:-1] + "0"}}, now=NOW)
        self.assertEqual(len(doc["jobs"]), 2, "another request is another job, and a mention in a subject names nothing")

    def test_a_pool_job_names_its_pool_job(self):
        doc = {"jobs": [], "seq": 0}
        for source in ({"kind": "self"}, {"kind": "pool"}, None):
            with self.assertRaises(Refusal):
                work.create(doc, "pool-claim-landed", {"title": "x", "source": source}, now=NOW)
        work.create(doc, "pool-claim-landed", {"title": "x", "source": {"kind": "pool", "pool_id": "p1", "from": "h/u"}}, now=NOW)
        self.assertEqual(len(doc["jobs"]), 1)

    def test_fill_moves_a_list(self):
        imported = {"seq": 3, "jobs": [job("active", jid="j2"), job("done", jid="j3")], "last": "j3"}
        current = {"jobs": []}
        work.fill(current, imported)
        self.assertEqual((current["seq"], len(current["jobs"]), current["last"]), (3, 2, "j3"))
        for bad in ({"jobs": [job()]}, {"jobs": [], "seq": 2}):
            with self.assertRaises(Refusal):
                work.fill(bad, imported)
        with self.assertRaises(Refusal):
            work.fill({"jobs": []}, {"seq": 2, "jobs": [job("active", jid="j1"), job("active", jid="j2")]})


class Claims(unittest.TestCase):
    GEN = "a" * 32

    def pool_job(self, **kw):
        return claims.add({"jobs": []}, {"id": "p1", "role": "python-dev", **kw})

    def test_a_claim_has_three_states(self):
        j = self.pool_job()
        self.assertEqual((j["claimed"], claims.state_of(j)), (None, "open"))
        self.assertIs(claims.claim(j, "h/a", lambda: NOW), False)
        self.assertEqual((j["claimed"], claims.state_of(j)), ({"by": "h/a", "at": NOW}, "claimed"))
        claims.close(j, "done", "2026-11-09T11:00:00Z")
        self.assertEqual(j["claimed"], {"by": "h/a", "at": NOW, "closed": {"at": "2026-11-09T11:00:00Z", "how": "done"}})
        self.assertEqual(claims.state_of(j), "closed")

    def test_a_repeat_by_its_claimant_is_a_repeat_and_by_another_is_refused(self):
        j = self.pool_job()
        claims.claim(j, "h/a", lambda: NOW)
        self.assertIs(claims.claim(j, "h/a", lambda: "later"), True)
        self.assertEqual(j["claimed"]["at"], NOW, "a repeat changes nothing")
        with self.assertRaises(Refusal) as e:
            claims.claim(j, "h/b", lambda: NOW)
        self.assertIn("claimed by h/a", str(e.exception))

    def test_claim_refuses_a_closed_claim_to_anyone(self):
        j = self.pool_job()
        claims.claim(j, "h/a", lambda: NOW)
        claims.close(j, "dropped", NOW)
        for sender in ("h/a", "h/b"):
            with self.assertRaises(Refusal, msg=sender) as e:
                claims.claim(j, sender, lambda: NOW)
            self.assertIn("closed (dropped at", str(e.exception))
        self.assertEqual(claims.state_of(j), "closed")

    def test_close_and_reopen_are_the_holders_rows_of_a_claimed_job_only(self):
        j = self.pool_job()
        for act in (lambda: claims.close(j, "done", NOW), lambda: claims.reopen(j)):
            with self.assertRaises(Refusal):
                act()                        # an open job has no claim to end
        claims.claim(j, "h/a", lambda: NOW)
        with self.assertRaises(Refusal):
            claims.close(j, "queued", NOW)
        claims.close(j, "done", NOW)
        with self.assertRaises(Refusal):
            claims.reopen(j)                 # a closed claim stays closed
        k = self.pool_job()
        claims.claim(k, "h/a", lambda: NOW)
        claims.reopen(k)
        self.assertEqual((k["claimed"], claims.state_of(k)), (None, "open"))

    def test_a_claim_is_what_javascript_calls_truthy(self):
        for held, state in (({}, "claimed"), ([], "claimed"), ("x", "claimed"), (0, "open"), ("", "open"), (None, "open"), (False, "open")):
            self.assertEqual(claims.state_of({"claimed": held}), state, held)

    def judge(self, claimed_at="2026-11-07T10:00:00Z", **kw):
        j = {"id": "p1", "claimed": {"by": "h/a", "at": claimed_at}}
        args = {"generation": self.GEN, "claims": [], "fresh": True, "now_s": claims._epoch(NOW)}
        args.update(kw)
        return claims.judge(j, args.pop("generation"), args.pop("claims"), **args)

    def test_judge_closes_on_a_claim_that_ended(self):
        for how in ("done", "dropped"):
            self.assertEqual(self.judge(claims=[{"generation": self.GEN, "id": "p1", "state": how}]), ("close", how))
        self.assertEqual(self.judge(claimed_at=NOW, claims=[{"generation": self.GEN, "id": "p1", "state": "done"}]), ("close", "done"),
                         "closing does not wait a day")
        for state in ("queued", "active", "paused", "blocked", "delivered"):
            self.assertIsNone(self.judge(claims=[{"generation": self.GEN, "id": "p1", "state": state}]), state)

    def test_judge_reads_the_claim_by_generation_and_id(self):
        other_gen = {"generation": "b" * 32, "id": "p1", "state": "done"}
        other_id = {"generation": self.GEN, "id": "p2", "state": "done"}
        self.assertEqual(self.judge(claims=[other_gen, other_id]), ("reopen", None), "a claim of another pool or job is not this one's")
        self.assertIsNone(self.judge(claims=[{"id": "p1", "state": "active"}]), "from before generations: might be this one")
        self.assertIsNone(self.judge(claims=[{"id": "p1", "state": "active"}, other_gen]))

    def test_judge_reopens_after_a_day_when_the_record_holds_none(self):
        self.assertEqual(self.judge(), ("reopen", None))
        self.assertIsNone(self.judge(claimed_at="2026-11-08T10:00:01Z"), "not yet a day")
        self.assertEqual(self.judge(claimed_at="2026-11-08T10:00:00Z"), ("reopen", None), "a day exactly")
        self.assertIsNone(self.judge(claimed_at="not a time"), "a claim whose time cannot be read is not old")
        self.assertIsNone(self.judge(claimed_at=None))

    def test_judge_unknown_changes_nothing(self):
        ended = [{"generation": self.GEN, "id": "p1", "state": "done"}]
        self.assertIsNone(self.judge(claims=None), "a record that reports no claims, or none at all")
        self.assertIsNone(self.judge(claims="p1"))
        self.assertIsNone(self.judge(fresh=False, claims=ended), "a stale record")
        self.assertIsNone(self.judge(fresh=False, claims=[]))
        self.assertIsNone(self.judge(generation=None, claims=ended), "a pool without a generation names no claim")
        job = {"id": "p1", "claimed": None}
        self.assertIsNone(claims.judge(job, self.GEN, ended, fresh=True, now_s=0), "an open job has no claim to end")
        closed = {"id": "p1", "claimed": {"by": "h/a", "at": NOW, "closed": {"at": NOW, "how": "done"}}}
        self.assertIsNone(claims.judge(closed, self.GEN, [], fresh=True, now_s=claims._epoch(NOW) + 10 ** 9), "nor a closed one")


class RequestTitle(unittest.TestCase):
    def test_the_request_title(self):
        title = work.request_title("  two\twords \n", RID)
        self.assertEqual(title, f"two words (REQUEST {RID})")
        self.assertEqual(work.request_id_of(title), RID)
        self.assertIsNone(work.request_id_of("two words"))
        self.assertEqual(work.request_id_of(work.request_title(f"see (REQUEST {OTHER}) follow-up", RID)), RID, "the last id is the job's")
        long = work.request_title("x" * 500, RID)
        self.assertEqual((len(long), work.request_id_of(long)), (work.TITLE_MAX, RID), "the subject gives way, never the id")
        self.assertEqual(work.request_id_of(f"a (REQUEST {RID}) and more"), None, "only a title that ends with it names it")


if __name__ == "__main__":
    unittest.main()
