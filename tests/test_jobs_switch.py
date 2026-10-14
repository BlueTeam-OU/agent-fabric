#!/usr/bin/env python3
"""fabric-jobs switch and the paused state (agent-fabric ADR-037 rules 2 and 10, amended 2026-10-14): the old job is settled
with its evidence, the next starts fresh, its branch is chosen before any work. Run in process (jobs.main) so the pull-request
reading of the arming count, which a fake gh cannot answer, is replaced at its one seam; gh, git and the journal are real
(a fake gh on PATH, bare origins, a journal seeded through episodic.py). Every refusal has its positive control: the same
job, fixed, switches."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import jobs_world  # noqa: E402 — tests/, the script's own directory
from git_env import git_env, scrub_process_env  # noqa: E402 — tests/, the script's own directory
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
scrub_process_env()
own_instance_tree()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RID = "01a12bae-9f03-7d83-8795-bcac9d940240"
RID2 = "01a12bae-9f03-7d83-8795-bcac9d940241"
GH = """#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
doc = json.load(open(os.path.join(os.environ["FAKE_DIR"], "gh.json")))
if a[:2] == ["pr", "view"] and "--repo" in a:
    key = a[a.index("--repo") + 1] + "#" + a[2]
    if key in doc["states"]:
        print(json.dumps({"state": doc["states"][key]}))
        sys.exit(0)
    sys.stderr.write("GraphQL: Could not resolve to a PullRequest (HTTP 404)\\n")
    sys.exit(1)
if a[:2] == ["pr", "list"]:
    if "merged" in a:
        search = a[a.index("--search") + 1] if "--search" in a else ""
        print(json.dumps([{"number": 9}] if any(search == "head:" + h for h in doc["merged_heads"]) else []))
    else:
        print(json.dumps(doc["open_prs"]))
    sys.exit(0)
sys.stderr.write("fake gh: unsupported: " + " ".join(a) + "\\n")
sys.exit(2)
"""


def load_jobs():
    spec = importlib.util.spec_from_file_location("jobs_under_test", os.path.join(ROOT, "tools", "fabric", "jobs.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {str(detail)[:700]}"))
        fails += not good

    with tempfile.TemporaryDirectory(prefix="jobs-switch-") as tmp:
        fake = os.path.join(tmp, "fake")
        os.makedirs(os.path.join(fake, "bin"))
        with open(os.path.join(fake, "bin", "gh"), "w", encoding="utf-8") as fh:
            fh.write(GH)
        os.chmod(os.path.join(fake, "bin", "gh"), 0o755)
        home = os.path.join(tmp, "home")
        os.makedirs(home)
        origins = os.path.join(tmp, "origins")
        login = subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip()
        os.environ.update(jobs_world.identity_env(), HOME=home, AGENT_FABRIC_ROOT=ROOT, FAKE_DIR=fake, GH_REPO=jobs_world.GH_REPO,
                          PATH=os.path.join(fake, "bin") + os.pathsep + os.environ.get("PATH", ""), CLAUDE_CODE_SESSION_ID="sess-A",
                          CLAUDE_BRIDGE_URL="http://127.0.0.1:9", CLAUDE_BRIDGE_AUTH_TOKEN="tok",
                          AGENT_FABRIC_HOSTS_REGISTRY=os.path.join(tmp, "none.json"))
        store = os.path.join(tmp, "store")
        os.makedirs(store)
        with open(os.path.join(store, ".agent-id"), "w") as fh:
            fh.write("01a0f782-7e06-7dee-811f-0a860ed93bf3\n")
        os.environ["AGENT_FABRIC_SECRET_STORE"] = store
        jobs = load_jobs()
        host = jobs.identity.current_host()
        me = f"{host}/{login}"
        mine = f"{host}/{login}/feat/earlier"      # a branch of this login with an open pull request, where a case has one
        n_worlds = 0

        def gh_says(states=None, open_prs=None, merged_heads=None) -> None:
            with open(os.path.join(fake, "gh.json"), "w", encoding="utf-8") as fh:
                json.dump({"states": states or {}, "open_prs": open_prs or [], "merged_heads": merged_heads or []}, fh)

        class World:
            """A fresh state directory and a fresh checkout with its origin."""

            def __init__(self) -> None:
                nonlocal n_worlds
                n_worlds += 1
                self.n = n_worlds
                self.state = os.path.join(tmp, f"state{self.n}")
                os.environ["AGENT_FABRIC_STATE_DIR"] = self.state
                self.repo = jobs_world.seeded(os.path.join(tmp, f"wc{self.n}"), origins)
                self.memory()
                gh_says()

            def memory(self) -> None:
                jobs_world.touch_memory(home, self.repo)

            def sw(self, *argv: str, cwd: str | None = None) -> tuple[int, str, str]:
                os.chdir(cwd or self.repo)
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    try:
                        rc = jobs.main(list(argv))
                    except SystemExit as e:
                        rc = e.code if isinstance(e.code, int) else 1
                return rc, out.getvalue(), err.getvalue()

            def add(self, title: str, *extra: str) -> str:
                rc, out, err = self.sw("add", title, "--working-copy", self.repo, *extra)
                assert rc == 0, err
                return out.split()[1]

            def working(self, title: str, *extra: str) -> str:
                job = self.add(title, *extra)
                assert self.sw("start", job)[0] == 0
                return job

            def job(self, job_id: str) -> dict:
                return next(j for j in json.load(open(os.path.join(self.state, "agents", login, "jobs.json")))["jobs"] if j["id"] == job_id)

            def switch(self, *argv: str, cwd: str | None = None) -> tuple[int, str, str]:
                self.memory()
                time.sleep(0.01)
                return self.sw("switch", *argv, cwd=cwd)

            def journal(self, *messages: tuple[str, str], ts: str | None = None) -> None:
                for direction, text in messages:
                    verb = ["gzcoord-in"] if direction == "in" else ["gzcoord-out-pending"]
                    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fabric", "episodic.py"), *verb],
                                       env=os.environ, input=json.dumps({"content": text, "seq": 1, **({"ts": ts} if ts else {})}) + "\n" if direction == "in" else text,
                                       capture_output=True, text=True, timeout=60)
                    assert r.returncode == 0, r.stderr

        def request(mid: str, expect: str = "yes") -> str:
            return (f"[GZCOORD/1] REQUEST\nFROM: peer/sender\nROLE: x\nPROJECT: p\nTO: {me}\nREPLY-EXPECTED: {expect}\n"
                    f"MESSAGE-ID: {mid}\nSUBJECT: please do\n\nREQUEST:\nx\n")

        def answer(mid: str, to: str) -> str:
            return (f"[GZCOORD/1] REPLY\nFROM: {me}\nROLE: x\nPROJECT: p\nTO: peer/sender\nIN-REPLY-TO: {to}\n"
                    f"MESSAGE-ID: {mid}\nSUBJECT: re\n\nREPLY:\nok\n")

        def settles(w: World, old: str, label: str, why: str | None = None) -> None:
            """`old` refuses to be left for `why`'s reason (or, with none, is left)."""
            w.add("the next job")
            rc, out, err = w.switch()
            if why is None:
                check(label, rc == 0 and "fabric-fresh --job" in out, out + err)
            else:
                check(label, rc == 1 and "cannot leave" in err and why in err and w.job(old)["state"] != "active"
                      and w.job("j2")["state"] == "queued", err)

        print("paused: pause, the evidence it needs, its place in the queue")
        w = World()
        j1 = w.working("the paused work")
        rc, out, err = w.sw("pause", j1, "  waiting for\nthe owner's ordering ")
        check("pause on a checkout on the default branch records no branch", rc == 0 and w.job(j1)["state"] == "paused"
              and "branch" not in w.job(j1) and w.job(j1)["reason"] == "waiting for the owner's ordering", err + repr(w.job(j1)))
        rc, out, err = w.sw("pause", j1, "again")
        check("only the active job is paused", rc == 1 and "only the active job" in err, err)
        j2 = w.add("next in line", "--priority", "high")
        rc, out, err = w.switch()
        check("a paused job with no branch is not settled: the refusal names how to pause it", rc == 1 and "names the branch holding its work" in err
              and "pause" in err, err)
        subprocess.run(["git", "-C", w.repo, "checkout", "-q", "-b", "side/work"], check=True, env=git_env())
        w.sw("start", j1)
        check("a paused job is started again by name", w.job(j1)["state"] == "active" and "reason" not in w.job(j1), repr(w.job(j1)))
        rc, out, err = w.sw("pause", j1, "set aside for the urgent one")
        check("pause on a feature branch records the branch and its checkout", rc == 0 and w.job(j1)["branch"] == "side/work"
              and w.job(j1)["worktree"] == w.repo, repr(w.job(j1)))
        rc, out, err = w.switch()
        check("a branch that is not on origin is refused", rc == 1 and "branch side/work is not on origin" in err, err)
        subprocess.run(["git", "-C", w.repo, "commit", "-q", "--allow-empty", "-m", "work"], check=True, env=git_env())
        subprocess.run(["git", "-C", w.repo, "push", "-q", "origin", "side/work"], check=True, env=git_env())
        subprocess.run(["git", "-C", w.repo, "commit", "-q", "--allow-empty", "-m", "more"], check=True, env=git_env())
        rc, out, err = w.switch()
        check("commits origin lacks are refused", rc == 1 and "has commits origin does not" in err, err)
        subprocess.run(["git", "-C", w.repo, "push", "-q", "origin", "side/work"], check=True, env=git_env())
        rc, out, err = w.switch()
        check("pushed: the paused job is left, and says so in both logs", rc == 0 and "paused: branch side/work pushed" in out
              and w.job(j1)["log"][-1]["note"].startswith(f"switch to {j2}: paused: branch side/work pushed")
              and w.job(j2)["log"][-1]["note"].startswith(f"switch from {j1} (paused: branch side/work pushed"), out + err)

        print("paused: offered before queued jobs of the same priority, never ahead of a higher one")
        w = World()
        subprocess.run(["git", "-C", w.repo, "checkout", "-q", "-b", "side/work"], check=True, env=git_env())
        subprocess.run(["git", "-C", w.repo, "commit", "-q", "--allow-empty", "-m", "work"], check=True, env=git_env())
        subprocess.run(["git", "-C", w.repo, "push", "-q", "origin", "side/work"], check=True, env=git_env())
        queued_first = w.add("queued, older than the paused job")
        old = w.working("work set aside")
        w.sw("pause", old, "urgent one first")
        high = w.add("a high one", "--priority", "high")
        os.chdir(tmp)
        rc, out, err = w.switch(cwd=w.repo)
        check("a high queued job still goes before a paused normal one", rc == 0 and out.startswith(high), out + err)
        w.sw("deliver", high, f"{jobs_world.GH_REPO}#2")
        gh_says({f"{jobs_world.GH_REPO}#2": "OPEN"})
        subprocess.run(["git", "-C", w.repo, "checkout", "-q", "main"], check=True, env=git_env())
        rc, out, err = w.switch()
        check("at equal priority the paused job goes before the older queued one, and the resume is said",
              rc == 0 and out.startswith(old) and "resumes paused work: urgent one first" in out and w.job(queued_first)["state"] == "queued",
              out + err)
        check("it keeps its own branch", w.job(old)["branch"] == "side/work" and "side/work (the job's own branch" in out, out)

        print("settling the old job: done")
        w = World()
        j1 = w.working("done without evidence")
        w.sw("done", j1)
        settles(w, j1, "done with no artifact is refused, naming the forms", "done needs evidence it landed")
        w = World()
        j1 = w.working("done on a reference that names nothing")
        w.sw("deliver", j1, "not-a-reference")
        w.sw("done", j1)
        settles(w, j1, "an artifact that names nothing checkable is not evidence", "done needs evidence")
        w = World()
        j1 = w.working("done on an open pull request")
        gh_says({f"{jobs_world.GH_REPO}#2": "OPEN"})
        w.sw("deliver", j1, f"{jobs_world.GH_REPO}#2")
        w.sw("done", j1)
        settles(w, j1, "a still-open pull request means delivered, not done", "still open")
        gh_says({f"{jobs_world.GH_REPO}#2": "MERGED"})
        rc, out, err = w.switch()
        check("merged: done is settled (the positive control)", rc == 0 and "done: " + jobs_world.GH_REPO + "#2 merged" in out, out + err)

        w = World()
        j1 = w.working("done by a commit")
        subprocess.run(["git", "-C", w.repo, "checkout", "-q", "-b", "side/x"], check=True, env=git_env())
        subprocess.run(["git", "-C", w.repo, "commit", "-q", "--allow-empty", "-m", "unlanded"], check=True, env=git_env())
        sha = subprocess.run(["git", "-C", w.repo, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        subprocess.run(["git", "-C", w.repo, "checkout", "-q", "main"], check=True, env=git_env())
        w.sw("deliver", j1, sha[:10])
        w.sw("done", j1)
        settles(w, j1, "a commit that is not on the default branch is no evidence", "done needs evidence")
        subprocess.run(["git", "-C", w.repo, "merge", "-q", "--ff-only", "side/x"], check=True, env=git_env())
        subprocess.run(["git", "-C", w.repo, "push", "-q", "origin", "main"], check=True, env=git_env())
        rc, out, err = w.switch()
        check("once on origin's default branch it is (positive control)", rc == 0 and f"{sha[:10]} on origin/main" in out, out + err)

        arts = sys.modules["fabric_jobs"].settle.artifacts_of({"artifacts": ["1234567", "abcdefa", "o/r#3", "reply:" + RID]}, "o/r")
        check("an abbreviated sha of seven digits, or of seven letters, is read as one; a pull request and a reply are read beside it",
              arts == {"prs": [("o/r", "3")], "shas": ["1234567", "abcdefa"], "replies": [RID]}, arts)

        print("settling the old job: delivered")
        w = World()
        j1 = w.working("delivered")
        gh_says({f"{jobs_world.GH_REPO}#3": "MERGED"})
        w.sw("deliver", j1, f"{jobs_world.GH_REPO}#3")
        settles(w, j1, "delivered with a merged pull request is refused: it is done", "is merged: the job is done, not delivered")
        gh_says({f"{jobs_world.GH_REPO}#3": "OPEN"})
        rc, out, err = w.switch()
        check("open: delivered is settled (the positive control)", rc == 0 and "delivered: " + jobs_world.GH_REPO + "#3 open" in out, out + err)
        w = World()
        j1 = w.working("delivered by a reply")
        w.sw("deliver", j1, f"reply:{RID}")
        settles(w, j1, "a reply that is not in the journal is not evidence", f"reply:{RID} is not in this login's journal")
        w.journal(("out", answer("01a12bae-0000-7000-8000-000000000001", RID)))
        rc, out, err = w.switch()
        check("sent: a reply-only job is settled (the positive control)", rc == 0 and "delivered: reply 01a12bae sent" in out, out + err)

        print("settling the old job: blocked, dropped")
        w = World()
        j1 = w.working("blocked on words")
        w.sw("block", j1, "waiting for somebody")
        settles(w, j1, "free-text blocked is refused, naming the checkable forms and the owner's decision", "blocked on free text")
        w.sw("start", j1)
        w.sw("block", j1, "owner: which of the two designs")
        rc, out, err = w.switch()
        check("an owner's decision named as text is a blocker", rc == 0 and "blocked: blocked on owner: which of the two designs" in out, out + err)
        w = World()
        j1 = w.working("blocked on a merged pull request")
        gh_says({"o/r#5": "MERGED"})
        w.sw("block", j1, "--on", "pr:o/r#5")
        w.add("the next job")
        rc, out, err = w.switch("j2")
        check("a blocker that already cleared means the job is not blocked: leaving it for another by name is refused", rc == 1 and "has cleared" in err
              and w.job("j2")["state"] == "queued", err)
        rc, out, err = w.switch()
        check("…and a plain switch takes the job whose wait is over, before anything queued", rc == 0 and out.startswith(j1), out + err)
        gh_says({"o/r#5": "OPEN"})
        w.sw("start", j1)
        gh_says({"o/r#6": "OPEN"})
        w.sw("block", j1, "--on", "pr:o/r#6")
        rc, out, err = w.switch()
        check("a blocker still waiting settles it (the positive control)", rc == 0 and "blocked on pr:o/r#6" in out, out + err)
        w = World()
        j1 = w.working("dropped")
        w.sw("drop", j1, "no longer needed")
        settles(w, j1, "a dropped job with its reason is settled", None)
        w = World()
        j1 = w.working("dropped with no reason")
        w.sw("drop", j1, "x")
        path = os.path.join(w.state, "agents", login, "jobs.json")
        doc = json.load(open(path))
        doc["jobs"][0]["reason"] = ""
        json.dump(doc, open(path, "w"))
        settles(w, j1, "a dropped job with no reason is refused", "needs a reason")

        print("settling the old job: the duties that hold whatever the outcome")
        w = World()
        j1 = w.working("duties")
        w.sw("drop", j1, "done with it")
        with open(os.path.join(w.repo, "scratch.txt"), "w") as fh:
            fh.write("x")
        settles(w, j1, "an uncommitted file is refused, with the file", "has uncommitted changes (?? scratch.txt)")
        os.unlink(os.path.join(w.repo, "scratch.txt"))
        rc, out, err = w.switch()
        check("clean again: switched (the positive control)", rc == 0, err)

        w = World()
        j1 = w.working("an owed reply")
        w.sw("drop", j1, "done with it")
        w.journal(("in", request(RID)))
        settles(w, j1, "a REPLY-EXPECTED: yes message addressed to this login with no reply is refused, named", f"({RID})")
        w.journal(("out", answer("01a12bae-0000-7000-8000-000000000002", RID)))
        rc, out, err = w.switch()
        check("answered: switched (the positive control)", rc == 0, err)
        w = World()
        j1 = w.working("a message that expects nothing")
        w.sw("drop", j1, "done with it")
        w.journal(("in", request(RID2, "no")), ("in", request(RID).replace(f"TO: {me}", "TO: peer/someone")))
        settles(w, j1, "REPLY-EXPECTED: no, and a message to someone else, owe nothing", None)

        w = World()
        j1 = w.working("memory")
        w.sw("drop", j1, "done with it")
        w.add("next")
        os.utime(os.path.join(home, ".claude", "projects", jobs_world.re.sub(r"[^A-Za-z0-9]", "-", w.repo), "memory", "fact.md"), (1, 1))
        rc, out, err = w.sw("switch")
        check("a memory directory that did not change during the job is refused", rc == 1 and "has not changed during" in err, err)
        rc, out, err = w.switch()
        check("…and written, it switches (the positive control)", rc == 0, err)

        w = World()
        j1 = w.working("several things wrong")
        w.sw("block", j1, "just words")
        with open(os.path.join(w.repo, "scratch.txt"), "w") as fh:
            fh.write("x")
        w.journal(("in", request(RID)))
        w.add("next")
        rc, out, err = w.sw("switch")
        check("every failed check is named at once", rc == 1 and err.count("\n  - ") >= 3, err)

        print("owed replies: received, not sent; and the session's start counts")
        w = World()
        j1 = w.add("backlog")
        w.switch()
        w.sw("drop", j1, "done")
        w.add("n")
        w.journal(("in", request(RID)), ts="2020-01-01T00:00:00Z")
        rc, out, err = w.switch()
        check("a message the sender wrote before the job began, received during it, is owed", rc == 1 and RID in err, err)
        w = World()
        first = w.working("the session's first job")
        w.sw("drop", first, "x")
        time.sleep(1.1)
        w.journal(("in", request(RID)))
        time.sleep(1.1)
        second = w.add("second")
        w.sw("start", second)
        w.sw("drop", second, "x")
        w.add("third")
        rc, out, err = w.switch()
        check("a message that arrived after the session started but before this job did is owed (the earlier of the two)", rc == 1 and RID in err, err)

        w = World()
        j1 = w.working("blocked and cleared at once")
        gh_says({"o/r#5": "MERGED"})
        w.sw("block", j1, "--on", "pr:o/r#5")
        rc, out, err = w.switch()
        check("the job just blocked, whose blocker has already cleared, is taken again: nothing to settle first",
              rc == 0 and out.startswith(j1) and w.job(j1)["state"] == "active" and w.job(j1)["log"][-1]["note"].startswith("switch; ")
              and " from " not in w.job(j1)["log"][-1]["note"].split(";")[0], out + err + w.job(j1)["log"][-1]["note"])

        print("an active job is never passed; nothing queued is the pool's offer, as before")
        w = World()
        j1 = w.working("still going")
        w.add("waiting")
        rc, out, err = w.switch()
        check("switch refuses while a job is active, and says how to leave it", rc == 1 and f"{j1} is still active" in err and "pause" in err, err)
        w = World()
        rc, out, err = w.switch()
        check("with nothing queued it refuses as next did", rc == 1 and "no queued job" in err, err)
        w = World()
        j1 = w.working("alias")
        w.sw("drop", j1, "x")
        w.add("n")
        w.memory()
        rc, out, err = w.sw("next")
        check("next is the alias: the same settling, the same fresh command", rc == 0 and f"fabric-fresh --job j2" in out and "fresh session" in out, out + err)

        print("the branch, chosen before any work (rule 10 step 3)")
        counted: dict = {}
        branching = sys.modules["fabric_jobs"].branching
        real_addable = branching._addable

        def addable_with(row: dict) -> str | None:
            """The real _addable, over the arming count's row for the pull request."""
            class Counts:
                @staticmethod
                def count_rows(refs):
                    return [row]
            saved = branching._load
            branching._load = lambda name, path: Counts
            try:
                return real_addable("o/r", 7)
            finally:
                branching._load = saved
        base = {"ok": True, "state": "open", "armed": "unarmed", "work": 15}
        check("a pull request with 15 work commits, unarmed, takes more", addable_with(base) is None)
        check("…16 work commits are landed, not added to", "16 work commits" in (addable_with({**base, "work": 16}) or ""))
        check("…armed or queued is not added to", "is armed" in (addable_with({**base, "armed": "armed"}) or "") and "is queued" in (addable_with({**base, "armed": "queued"}) or ""))
        check("…a row that could not be read, or a closed one, is unknown, never addable",
              "could not be read" in (addable_with({"ok": False, "line": "x cannot be read: y"}) or "") and "could not be read" in (addable_with({**base, "state": "merged"}) or "")
              and "could not be read" in (addable_with({**base, "work": None}) or ""))
        branching._addable = lambda repo, number: counted.get(number)

        def other_clone(w: World) -> str:
            other = os.path.join(tmp, f"other{w.n}")
            subprocess.run(["git", "clone", "-q", os.path.join(origins, os.path.basename(w.repo) + ".git"), other], check=True, env=git_env())
            return other

        def advance_default(w: World) -> str:
            other = other_clone(w)
            subprocess.run(["git", "-C", other, "commit", "-q", "--allow-empty", "-m", "default moved"], check=True, env=git_env())
            subprocess.run(["git", "-C", other, "push", "-q", "origin", "main"], check=True, env=git_env())
            return subprocess.run(["git", "-C", other, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()

        w = World()
        tip = advance_default(w)
        j1 = w.add("Fix the (REQUEST 01a1396c) thing in the parser, quickly please")
        rc, out, err = w.switch("--type", "fix")
        job = w.job(j1)
        want = f"{host}/{login}/fix/{j1}-fix-the-thing-in-the-parser"
        check("no open pull request: a new branch named from the job, off the freshly fetched default", rc == 0 and job["branch"] == want
              and job["worktree"] == f"{w.repo}-{j1}-fix-the-thing-in-the-parser"
              and subprocess.run(["git", "-C", job["worktree"], "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() == tip
              and f"branch {want}" in out, out + err + repr(job))
        check("the opening prompt names the branch", f"work on branch {want} in {job['worktree']}" in w.sw("show", j1, "--line")[1], w.sw("show", j1, "--line")[1])
        check("the log line carries the branch", f"branch {want}" in job["log"][-1]["note"], repr(job["log"]))
        check("the working copy itself is untouched", subprocess.run(["git", "-C", w.repo, "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True).stdout.strip() == "main")

        w = World()
        j1 = w.working("first")
        w.sw("drop", j1, "x")
        j2 = w.add("second")
        os.makedirs(f"{w.repo}-{j2}-second")
        rc, out, err = w.switch()
        check("a worktree path that is taken gets a new name beside it, never a refusal with no way out",
              rc == 0 and w.job(j2)["branch"].endswith(f"{j2}-second-2") and w.job(j2)["worktree"] == f"{w.repo}-{j2}-second-2", out + err)
        check("…and the taken directory is left alone", os.listdir(f"{w.repo}-{j2}-second") == [])

        w = World()
        j1 = w.working("a branch of the generated name already exists")
        w.sw("drop", j1, "x")
        j2 = w.add("second")
        subprocess.run(["git", "-C", w.repo, "branch", f"{host}/{login}/feat/{j2}-second"], check=True, env=git_env())
        rc, out, err = w.switch()
        check("a branch of the generated name that exists (a landed one, a leftover) is not reused or refused: a suffix",
              rc == 0 and w.job(j2)["branch"] == f"{host}/{login}/feat/{j2}-second-2", out + err)

        print("review findings: a switch that races, a swept worktree, odd artifacts, pause elsewhere, blockers kept")
        w = World()
        j1 = w.working("first")
        w.sw("drop", j1, "x")
        j2 = w.add("second")
        real_choose = sys.modules["fabric_jobs"].verbs.choose

        def racing(job, **kw):
            made = real_choose(job, **kw)
            w.sw("add", "a high one that appeared meanwhile", "--working-copy", w.repo, "--priority", "high")
            return made
        sys.modules["fabric_jobs"].verbs.choose = racing
        try:
            rc, out, err = w.switch()
        finally:
            sys.modules["fabric_jobs"].verbs.choose = real_choose
        check("a list that changed while the branch was prepared refuses, and the branch and worktree made for it are taken back",
              rc == 1 and "list changed" in err and w.job(j2)["state"] == "queued" and not os.path.exists(f"{w.repo}-{j2}-second")
              and subprocess.run(["git", "-C", w.repo, "branch", "--list", f"{host}/{login}/feat/{j2}-second"], capture_output=True, text=True).stdout.strip() == "", err)
        rc, out, err = w.switch()
        check("…and the next switch works (the positive control)", rc == 0 and out.startswith("j3"), out + err)

        w = World()
        j1 = w.working("first")
        w.sw("drop", j1, "x")
        j2 = w.add("second")
        rc, out, err = w.switch()
        wt = w.job(j2)["worktree"]
        w.sw("drop", j2, "done")
        subprocess.run(["git", "-C", w.repo, "worktree", "remove", "--force", wt], check=True, env=git_env())
        w.add("third")
        rc, out, err = w.switch()
        check("a worktree that was swept after its job is not 'could not tell': nothing uncommitted there", rc == 0, err)

        w = World()
        j1 = w.working("merged, with a word that looks like a sha")
        gh_says({f"{jobs_world.GH_REPO}#2": "MERGED"})
        w.sw("deliver", j1, f"{jobs_world.GH_REPO}#2", "answered request 01a1396c and deadbeef1")
        w.sw("done", j1)
        settles(w, j1, "a word that names no commit here is not evidence and not an unanswered check", None)

        w = World()
        j1 = w.add("on its own branch")
        rc, out, err = w.switch()
        branch, wt = w.job(j1)["branch"], w.job(j1)["worktree"]
        subprocess.run(["git", "-C", w.repo, "checkout", "-q", "-b", "elsewhere"], check=True, env=git_env())
        w.sw("pause", j1, "later")
        check("pause run in another checkout keeps the branch and worktree switch recorded", w.job(j1)["branch"] == branch and w.job(j1)["worktree"] == wt, repr(w.job(j1)))
        w.sw("start", j1)
        subprocess.run(["git", "-C", wt, "checkout", "-q", "-b", "moved-on"], check=True, env=git_env())
        w.sw("pause", j1, "again, from its own checkout", cwd=wt)
        check("…and run in its own checkout it records what is checked out there", w.job(j1)["branch"] == "moved-on" and w.job(j1)["worktree"] == wt, repr(w.job(j1)))

        w = World()
        subprocess.run(["git", "-C", w.repo, "checkout", "-q", "-b", mine], check=True, env=git_env())
        subprocess.run(["git", "-C", w.repo, "push", "-q", "origin", mine], check=True, env=git_env())
        subprocess.run(["git", "-C", w.repo, "checkout", "-q", "main"], check=True, env=git_env())
        gh_says(open_prs=[{"number": 40, "headRefName": mine, "isDraft": False}])
        counted[40] = f"{jobs_world.GH_REPO}#40 is armed"
        j1 = w.working("blocked twice over")
        gh_says({"o/r#5": "OPEN"}, open_prs=[{"number": 40, "headRefName": mine, "isDraft": False}])
        w.sw("block", j1, "--on-request", RID, "--on", "pr:o/r#5")
        j2 = w.add("another")
        rc, out, err = w.switch(j1, "--needs-merged")
        check("switch --needs-merged on a job already blocked adds the pull request and keeps what it waits on", rc == 0 and w.job(j1)["state"] == "blocked"
              and w.job(j1)["blockers"] == ["pr:o/r#5", f"request:{RID}", f"pr:{jobs_world.GH_REPO}#40"] and w.job(j1).get("waits_on") == RID, out + err + repr(w.job(j1)))
        counted.clear()

        w = World()
        j1 = w.working("left")
        w.sw("drop", j1, "x")
        w.add("n")
        w.switch()
        last = w.job(j1)["log"][-1]
        check("the left job's switch line has no state, so it is not a transition to the fleet's finish time",
              last.get("kind") == "switch" and "state" not in last and last["note"].startswith("switch to j2"), repr(last))

        print("a message owed is scoped to the job (the owner, 2026-10-14)")
        w = World()
        j1 = w.add("scoped")
        w.journal(("in", request(RID)))
        time.sleep(1.1)
        w.switch()
        w.sw("drop", j1, "done")
        w.add("n")
        w.journal(("in", request("01a12bae-9f03-7d83-8795-bcac9d940242").replace("REQUEST", "REPLY", 1)))
        w.journal(("in", request(RID2).replace("REQUEST", "QUESTION", 1)))
        rc, out, err = w.switch()
        check("a message that arrived before the job started does not hold the switch; one that arrived during it, a QUESTION, does",
              rc == 1 and RID2 in err and RID not in err and "0242" not in err, err)
        w.journal(("out", answer("01a12bae-0000-7000-8000-000000000009", RID2)))
        rc, out, err = w.switch()
        check("…answered, it switches (the positive control)", rc == 0, err)
        check("…and leaving a job adds no second 'done' to its log (the finish time stays the finish)",
              [e.get("state") for e in w.job(j1)["log"]].count("dropped") == 1, repr(w.job(j1)["log"]))

        w = World()
        j1 = w.working("first")
        w.sw("drop", j1, "x")
        j2 = w.add("second")
        rc, out, err = w.switch()
        w2 = w.job(j2)
        subprocess.run(["git", "-C", w2["worktree"], "commit", "-q", "--allow-empty", "-m", "begun"], check=True, env=git_env())
        os.chdir(w2["worktree"])
        w.sw("pause", j2, "later", cwd=w2["worktree"])
        subprocess.run(["git", "-C", w2["worktree"], "push", "-q", "origin", w2["branch"]], check=True, env=git_env())
        j3 = w.add("third")
        rc, out, err = w.switch(cwd=w2["worktree"])
        check("a job that has a branch of its own goes back to it, not to a new one", rc == 0 and out.startswith(j2)
              and w.job(j2)["branch"] == w2["branch"] and f"{w2['branch']} (the job's own branch" in out, out + err)

        print("…an open pull request of this login, when it is still addable")
        w = World()
        subprocess.run(["git", "-C", w.repo, "checkout", "-q", "-b", mine], check=True, env=git_env())
        subprocess.run(["git", "-C", w.repo, "commit", "-q", "--allow-empty", "-m", "on the pull request"], check=True, env=git_env())
        subprocess.run(["git", "-C", w.repo, "push", "-q", "origin", mine], check=True, env=git_env())
        subprocess.run(["git", "-C", w.repo, "checkout", "-q", "main"], check=True, env=git_env())
        tip = advance_default(w)
        gh_says(open_prs=[{"number": 40, "headRefName": mine, "isDraft": False}, {"number": 41, "headRefName": "someone/else/feat/x", "isDraft": False}])
        j1 = w.working("done before")
        w.sw("drop", j1, "x")
        j2 = w.add("the next piece")
        rc, out, err = w.switch()
        wt = w.job(j2).get("worktree")
        merged_in = subprocess.run(["git", "-C", wt or w.repo, "merge-base", "--is-ancestor", tip, "HEAD"]).returncode == 0 if wt else False
        check("the next job goes on that pull request's branch, with the default merged in first", rc == 0 and w.job(j2).get("branch") == mine
              and merged_in and f"{mine} (your open pull request #40" in out, out + err + repr(w.job(j2)))
        check("…in a worktree beside the working copy, the working copy untouched",
              wt == f"{w.repo}-earlier" and subprocess.run(["git", "-C", w.repo, "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True).stdout.strip() == "main", wt)

        w = World()
        subprocess.run(["git", "-C", w.repo, "checkout", "-q", "-b", mine], check=True, env=git_env())
        subprocess.run(["git", "-C", w.repo, "commit", "-q", "--allow-empty", "-m", "on the pull request"], check=True, env=git_env())
        subprocess.run(["git", "-C", w.repo, "push", "-q", "origin", mine], check=True, env=git_env())
        subprocess.run(["git", "-C", w.repo, "checkout", "-q", "main"], check=True, env=git_env())
        other = other_clone(w)
        with open(os.path.join(other, "f.txt"), "w") as fh:
            fh.write("default")
        subprocess.run(["git", "-C", other, "add", "f.txt"], check=True, env=git_env())
        subprocess.run(["git", "-C", other, "commit", "-q", "-m", "default adds f"], check=True, env=git_env())
        subprocess.run(["git", "-C", other, "push", "-q", "origin", "main"], check=True, env=git_env())
        subprocess.run(["git", "-C", w.repo, "checkout", "-q", mine], check=True, env=git_env())
        with open(os.path.join(w.repo, "f.txt"), "w") as fh:
            fh.write("branch")
        subprocess.run(["git", "-C", w.repo, "add", "f.txt"], check=True, env=git_env())
        subprocess.run(["git", "-C", w.repo, "commit", "-q", "-m", "branch adds f"], check=True, env=git_env())
        subprocess.run(["git", "-C", w.repo, "push", "-q", "origin", mine], check=True, env=git_env())
        subprocess.run(["git", "-C", w.repo, "checkout", "-q", "main"], check=True, env=git_env())
        gh_says(open_prs=[{"number": 40, "headRefName": mine, "isDraft": False}])
        j1 = w.working("done before")
        w.sw("drop", j1, "x")
        j2 = w.add("the next piece")
        rc, out, err = w.switch()
        wt = f"{w.repo}-earlier"
        check("a default branch that does not merge cleanly is refused, the merge undone, nothing started",
              rc == 1 and "does not merge into" in err and w.job(j2)["state"] == "queued"
              and subprocess.run(["git", "-C", wt, "status", "--porcelain"], capture_output=True, text=True).stdout == "", err)

        print("…not addable: blocked on it when the job needs it merged, else a new branch")
        w = World()
        subprocess.run(["git", "-C", w.repo, "checkout", "-q", "-b", mine], check=True, env=git_env())
        subprocess.run(["git", "-C", w.repo, "commit", "-q", "--allow-empty", "-m", "queued"], check=True, env=git_env())
        subprocess.run(["git", "-C", w.repo, "push", "-q", "origin", mine], check=True, env=git_env())
        subprocess.run(["git", "-C", w.repo, "checkout", "-q", "main"], check=True, env=git_env())
        gh_says(open_prs=[{"number": 40, "headRefName": mine, "isDraft": False}])
        counted[40] = f"{jobs_world.GH_REPO}#40 is armed"
        j1 = w.working("done before")
        w.sw("drop", j1, "x")
        j2 = w.add("depends on the pull request")
        j3 = w.add("independent")
        rc, out, err = w.switch(j2, "--needs-merged")
        check("it needs the pull request merged and the pull request cannot take more: blocked on it, nothing started",
              rc == 0 and w.job(j2)["state"] == "blocked" and w.job(j2)["blockers"] == [f"pr:{jobs_world.GH_REPO}#40"]
              and "fabric-fresh" not in out and "armed" in out, out + err + repr(w.job(j2)))
        w.memory()
        rc, out, err = w.switch(j3)
        check("otherwise a new branch off the default", rc == 0 and w.job(j3)["branch"].startswith(f"{host}/{login}/feat/{j3}-") , out + err)
        counted[40] = f"{jobs_world.GH_REPO}#40 holds 16 work commits"
        w2 = World()
        subprocess.run(["git", "-C", w2.repo, "checkout", "-q", "-b", mine], check=True, env=git_env())
        subprocess.run(["git", "-C", w2.repo, "push", "-q", "origin", mine], check=True, env=git_env())
        subprocess.run(["git", "-C", w2.repo, "checkout", "-q", "main"], check=True, env=git_env())
        gh_says(open_prs=[{"number": 40, "headRefName": mine, "isDraft": False}])
        a = w2.working("done before")
        w2.sw("drop", a, "x")
        b = w2.add("a piece that does not need it")
        rc, out, err = w2.switch()
        check("a full pull request is not added to: a new branch", rc == 0 and w2.job(b)["branch"] != mine and w2.job(b)["branch"].startswith(f"{host}/{login}/feat/"), out + err)

        w = World()
        gh_says(open_prs=[{"number": 40, "headRefName": f"{host}/{login}/feat/a", "isDraft": False}, {"number": 41, "headRefName": f"{host}/{login}/feat/b", "isDraft": False}])
        j1 = w.add("two open")
        rc, out, err = w.switch()
        check("two open pull requests of this login are refused, named: the choice is not guessed", rc == 1 and "#40, #41" in err and w.job(j1)["state"] == "queued", err)

        print("never behind the default branch, and the unknown stays unknown")
        w = World()
        subprocess.run(["git", "-C", w.repo, "remote", "remove", "origin"], check=True, env=git_env())
        j1 = w.add("no origin")
        rc, out, err = w.switch()
        check("a working copy with no reachable origin cannot choose a branch: refused, nothing started", rc == 1 and "could not be chosen" in err
              and w.job(j1)["state"] == "queued", err)
        w = World()
        j1 = w.add("job")
        doc_path = os.path.join(w.state, "agents", login, "jobs.json")
        doc = json.load(open(doc_path))
        doc["jobs"][0]["working_copy"] = None
        json.dump(doc, open(doc_path, "w"))
        rc, out, err = w.switch()
        check("a job with no working copy is refused, said", rc == 1 and "no working copy" in err, err)

        w = World()
        j1 = w.add("bad row")
        w.switch()
        w.sw("drop", j1, "done")
        w.add("n")
        w.journal(("in", request(RID, "no")))       # makes the journal exist
        path = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fabric", "episodic.py"), "where"], env=os.environ, capture_output=True, text=True).stdout.strip()
        conn = sqlite3.connect(path)
        conn.execute("UPDATE episodes SET metadata_json='not json', recorded_at='2099-01-01T00:00:00Z' WHERE message_id=?", (RID,))
        conn.commit()
        conn.close()
        rc, out, err = w.switch()
        check("a journal row whose metadata cannot be read is owed, never let through", rc == 1 and RID in err and "could not be read" in err, err)
        w.journal(("out", answer("01a12bae-0000-7000-8000-000000000011", RID)))
        rc, out, err = w.switch()
        check("…and answering it clears it, as it does any other (the positive control)", rc == 0, err)

        def broken_row(metadata: str | None, recorded: str) -> World:
            """A world whose journal holds one inbound request with `metadata` as its metadata_json, journaled at `recorded`."""
            w = World()
            j = w.add("bad row")
            w.switch()
            w.sw("drop", j, "done")
            w.add("n")
            w.journal(("in", request(RID, "yes")))
            conn = sqlite3.connect(subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fabric", "episodic.py"), "where"], env=os.environ,
                                                  capture_output=True, text=True).stdout.strip())
            if metadata is None:      # keep the metadata the journal wrote: only the receipt time is broken
                conn.execute("UPDATE episodes SET recorded_at=? WHERE message_id=?", (recorded, RID))
            else:
                conn.execute("UPDATE episodes SET metadata_json=?, recorded_at=? WHERE message_id=?", (metadata, recorded, RID))
            conn.commit()
            conn.close()
            return w
        rc, out, err = broken_row("not json", "2000-01-01T00:00:00Z").switch()
        check("a row whose metadata cannot be read, journaled before the job, is outside its window", rc == 0, err)
        rc, out, err = broken_row("[1]", "2099-01-01T00:00:00Z").switch()
        check("metadata that parses but is no object is as unreadable: owed", rc == 1 and RID in err and "could not be read" in err, err)

        rc, out, err = broken_row(None, "not a time").switch()
        check("a readable row with no usable receipt time is owed, and the refusal names its subject",
              rc == 1 and RID in err and "receipt time could not be read" in err and "please do" in err, err)
        rc, out, err = broken_row(None, "2000-01-01T00:00:00Z").switch()
        check("…and the same row with a usable time, before the job, is outside its window (the positive control)", rc == 0, err)

        print("blocked_on owner's decision, a dangling link in memory, a repeated pull request")
        w = World()
        subprocess.run(["git", "-C", w.repo, "checkout", "-q", "-b", mine], check=True, env=git_env())
        subprocess.run(["git", "-C", w.repo, "push", "-q", "origin", mine], check=True, env=git_env())
        subprocess.run(["git", "-C", w.repo, "checkout", "-q", "main"], check=True, env=git_env())
        gh_says(open_prs=[{"number": 40, "headRefName": mine, "isDraft": False}])
        counted[40] = f"{jobs_world.GH_REPO}#40 is armed"
        j1 = w.working("waits for the owner")
        w.sw("block", j1, "owner: which design")
        rc, out, err = w.switch(j1, "--needs-merged")
        check("a job blocked on an owner's decision is not also blocked on a pull request: refused, unchanged",
              rc == 1 and "nothing can check" in err and w.job(j1)["blocked_on"] == "owner: which design" and "blockers" not in w.job(j1), err)
        w2 = World()
        subprocess.run(["git", "-C", w2.repo, "checkout", "-q", "-b", mine], check=True, env=git_env())
        subprocess.run(["git", "-C", w2.repo, "push", "-q", "origin", mine], check=True, env=git_env())
        subprocess.run(["git", "-C", w2.repo, "checkout", "-q", "main"], check=True, env=git_env())
        gh_says({"o/r#5": "OPEN"}, open_prs=[{"number": 40, "headRefName": mine, "isDraft": False}])
        k = w2.working("twice")
        w2.sw("block", k, "--on", "pr:o/r#5")
        w2.switch(k, "--needs-merged")
        w2.memory()
        w2.switch(k, "--needs-merged")
        check("the same pull request added twice is said once", w2.job(k)["blocked_on"].count(f"pr:{jobs_world.GH_REPO}#40") == 1, w2.job(k)["blocked_on"])
        counted.clear()
        w = World()
        j1 = w.working("memory with a dangling link")
        w.sw("drop", j1, "x")
        w.add("n")
        mem = os.path.join(home, ".claude", "projects", jobs_world.re.sub(r"[^A-Za-z0-9]", "-", w.repo), "memory")
        os.symlink(os.path.join(tmp, "nowhere"), os.path.join(mem, "dangling.md"))
        rc, out, err = w.switch()
        check("a dangling link in the memory directory is not a change and not a failure", rc == 0, err)

        print("a session that has worked no job takes the first in place, with its branch")
        w = World()
        j1 = w.add("first")
        rc, out, err = w.switch("--json")
        v = json.loads(out)
        check("--json carries the verdict, the branch and what was settled", rc == 0 and v["fresh"] is False and v["settled"] is None
              and v["branch"].startswith(f"{host}/{login}/feat/{j1}-") and v["branch_kind"] == "new", out + err)

    print("PASS" if not fails else f"FAILED: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
