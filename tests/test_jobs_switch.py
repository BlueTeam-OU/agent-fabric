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
import re
import sqlite3
import shutil
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

            def __init__(self, under: str | None = None) -> None:
                nonlocal n_worlds
                n_worlds += 1
                self.n = n_worlds
                self.state = os.path.join(tmp, f"state{self.n}")
                os.environ["AGENT_FABRIC_STATE_DIR"] = self.state
                self.repo = jobs_world.seeded(os.path.join(under or tmp, f"wc{self.n}"), origins)
                self.memory_of = self.repo      # the launch directory whose memory each switch refreshes
                self.memory()
                gh_says()

            def memory(self) -> None:
                jobs_world.touch_memory(home, self.memory_of)

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

            def started(self, job_id: str) -> str:
                return [e["at"] for e in self.job(job_id)["log"] if e.get("state") == "active"][-1]

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
                    if direction in ("out", "out-failed"):
                        mid = re.search(r"^MESSAGE-ID: (\S+)$", text, re.M).group(1)
                        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fabric", "episodic.py"), "gzcoord-out-final", mid,
                                            "--state", "failed" if direction == "out-failed" else "accepted"],
                                           env=os.environ, capture_output=True, text=True, timeout=60)
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

        print("settling the old job: a reflection job is done on the fabric-reflect cursor (ADR-058)")
        agent_id = "01a0f782-7e06-7dee-811f-0a860ed93bf3"

        def cursor(w: World, done_at: str | None, owner: str = agent_id) -> None:
            body = {"agent_id": owner, "row": 7, "episode": "e", **({"done_at": done_at} if done_at else {})}
            with open(os.path.join(w.state, "agents", login, "reflect-cursor.json"), "w", encoding="utf-8") as fh:
                json.dump(body, fh)

        later, earlier = "2999-01-01T00:00:00Z", "2000-01-01T00:00:00Z"
        for label, put, why in (("a cursor closed after the job started", lambda w: cursor(w, later), None),
                                ("no cursor", lambda w: None, "no fabric-reflect pass has been closed"),
                                ("a cursor older than the job", lambda w: cursor(w, earlier), "predates"),
                                ("a cursor of another agent", lambda w: cursor(w, later, "01a0f782-0000-7dee-811f-0a860ed93bf3"), "remove it to read this journal"),
                                ("a cursor closed in the second the job started", lambda w: cursor(w, w.started(j1)), "predates"),
                                ("a cursor with no done_at", lambda w: cursor(w, None), "no readable done_at")):
            w = World()
            j1 = w.working("weekly reflection pass", "--topic", "reflection")
            w.sw("done", j1)
            put(w)
            w.add("the next job")
            rc, out, err = w.switch()
            if why is None:
                check(f"reflection: {label} settles done and names the row",
                      rc == 0 and "fabric-reflect cursor at row 7, " + later in out, out + err)
            else:
                check(f"reflection: {label} is refused", rc == 1 and why in err and w.job(j1)["state"] != "active", err)
        w = World()
        j1 = w.working("weekly reflection pass", "--topic", "reflection")
        w.sw("done", j1)
        with open(os.path.join(w.state, "agents", login, "reflect-cursor.json"), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        w.add("the next job")
        rc, out, err = w.switch()
        check("reflection: an unreadable cursor is refused, not passed", rc == 1 and "cursor could not be read" in err and "is unreadable" in err, out + err)
        w = World()
        j1 = w.working("weekly reflection pass", "--topic", "other")
        w.sw("done", j1)
        cursor(w, later)
        settles(w, j1, "a job of another topic gets no evidence from a fresh cursor", "done needs evidence")
        w = World()
        j1 = w.working("weekly reflection pass, titled so", "--topic", "reflection")
        w.sw("deliver", j1, f"{jobs_world.GH_REPO}#2")
        w.sw("done", j1)
        gh_says({f"{jobs_world.GH_REPO}#2": "MERGED"})
        cursor(w, later)
        w.add("the next job")
        rc, out, err = w.switch()
        check("reflection: another evidence form counts beside the cursor", rc == 0 and "#2 merged" in out and "fabric-reflect cursor" in out, out + err)

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

        print("settling the old job: done with a reason and no artifact")
        w = World()
        j1 = w.working("disk cleanup")
        rc, out, err = w.sw("done", j1, "--no-artifact", "   ")
        check("an empty reason is refused and the job stays active", rc == 1 and "--no-artifact needs a reason" in err
              and w.job(j1)["state"] == "active", out + err)
        rc, out, err = w.sw("done", j1, "--no-artifact", "removed  old\nbuild caches")
        check("done --no-artifact closes the job, recording the reason squeezed", rc == 0 and w.job(j1)["state"] == "done"
              and w.job(j1).get("no_artifact") == "removed old build caches", out + err)
        check("list --all and show carry the reason", "no artifact: removed old build caches" in w.sw("list", "--all")[1]
              and "removed old build caches" in w.sw("show", j1)[1])
        settles(w, j1, "a done job with a reason and no evidence is settled")
        w = World()
        j1 = w.working("done after the fact")
        w.sw("done", j1)
        settles(w, j1, "without the reason the same job still refuses, naming --no-artifact", "--no-artifact")
        w = World()
        j1 = w.working("done, reason added later")
        w.sw("done", j1)
        rc, out, err = w.sw("done", j1, "--no-artifact", "tidied the scratch disk")
        check("a job already done gains the reason and stays done", rc == 0 and w.job(j1)["state"] == "done"
              and w.job(j1).get("no_artifact") == "tidied the scratch disk", out + err)
        rc, out, err = w.sw("done", j1)
        check("done again without a reason is still refused (closed job)", rc == 1 and "closed job is not reopened" in err, out + err)
        settles(w, j1, "the reason added after done settles it")
        w = World()
        j1 = w.working("a dropped job takes no reason")
        w.sw("drop", j1, "not needed")
        rc, out, err = w.sw("done", j1, "--no-artifact", "x")
        check("a dropped job is not given a done reason", rc == 1 and w.job(j1)["state"] == "dropped"
              and "no_artifact" not in w.job(j1), out + err)
        w = World()
        j1 = w.working("a reason does not stand in for an artifact that did not land")
        gh_says({f"{jobs_world.GH_REPO}#2": "CLOSED"})
        w.sw("deliver", j1, f"{jobs_world.GH_REPO}#2")
        w.sw("done", j1, "--no-artifact", "housekeeping")
        settles(w, j1, "a closed unmerged pull request plus a reason is refused", "did not land")
        w = World()
        j1 = w.working("an unlanded sha plus a reason")
        w.sw("deliver", j1, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
        w.sw("done", j1, "--no-artifact", "housekeeping")
        settles(w, j1, "a sha off the default branch plus a reason is refused", "did not land")
        w.sw("retract", j1, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
        settles(w, j1, "…and settled once the artifact is retracted (the positive control)")
        w = World()
        j1 = w.working("a reason does not outweigh an open pull request")
        gh_says({f"{jobs_world.GH_REPO}#2": "OPEN"})
        w.sw("deliver", j1, f"{jobs_world.GH_REPO}#2")
        w.sw("done", j1, "--no-artifact", "housekeeping")
        settles(w, j1, "an open pull request still means delivered, not done", "still open")

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

        def git(w: World, *a: str) -> None:
            subprocess.run(["git", "-C", w.repo, *a], check=True, env=git_env())
        contrib = "host/agent/for/user/the-thing"
        w = World()
        j1 = w.working("done as a contributor branch")
        git(w, "checkout", "-q", "-b", contrib)
        git(w, "commit", "-q", "--allow-empty", "-m", "supplied")
        git(w, "push", "-q", "origin", contrib)
        git(w, "checkout", "-q", "main")
        w.sw("deliver", j1, contrib)
        w.sw("done", j1)
        settles(w, j1, "a branch whose head is not on the default branch is no evidence, and the refusal names it",
                f"branch {contrib} is not on origin/main")
        git(w, "merge", "-q", "--no-ff", "-m", "folded", contrib)
        git(w, "push", "-q", "origin", "main")
        rc, out, err = w.switch()
        check("a branch whose head is on origin's default branch settles done (the positive control)",
              rc == 0 and f"branch {contrib} on origin/main" in out, out + err)

        w = World()
        j1 = w.working("a done job with the wrong artifact")
        git(w, "checkout", "-q", "-b", contrib)
        git(w, "commit", "-q", "--allow-empty", "-m", "supplied")
        git(w, "push", "-q", "origin", contrib)
        git(w, "checkout", "-q", "main")
        git(w, "merge", "-q", "--no-ff", "-m", "folded", contrib)
        git(w, "push", "-q", "origin", "main")
        w.sw("done", j1)
        settles(w, j1, "a done job with no artifact cannot be left", "done needs evidence")
        before = w.job(j1)["updated"]
        time.sleep(1.1)
        rc, out, err = w.sw("deliver", j1, f"origin/{contrib}")
        check("deliver on a done job appends evidence and does not reopen it",
              rc == 0 and w.job(j1)["state"] == "done" and w.job(j1)["artifacts"] == [f"origin/{contrib}"], out + err)
        check("…and stamps the job as updated", w.job(j1)["updated"] > before, w.job(j1))
        rc, out, err = w.switch()
        check("…and the appended evidence settles it (a branch named as origin/<ref>)", rc == 0 and f"branch {contrib} on origin/main" in out, out + err)

        w = World()
        j1 = w.working("dropped stays closed")
        w.sw("drop", j1, "no longer wanted")
        rc, out, err = w.sw("deliver", j1, contrib)
        check("a dropped job takes no evidence: a closed job is not reopened", rc == 1 and "not reopened" in err, out + err)

        w = World()
        j1 = w.working("delivered as a branch")
        git(w, "checkout", "-q", "-b", contrib)
        git(w, "commit", "-q", "--allow-empty", "-m", "supplied")
        git(w, "checkout", "-q", "main")
        w.sw("deliver", j1, contrib, "tools/fabric/x.py")
        settles(w, j1, "a branch that is not on origin is no delivery (a path beside it is no failure)", "delivered needs an artifact")
        git(w, "push", "-q", "origin", contrib)
        rc, out, err = w.switch()
        check("once on origin, the branch is the delivery (the positive control)", rc == 0 and f"branch {contrib} on origin" in out, out + err)

        def pushed_branch(w: World, fold: bool = False) -> None:
            git(w, "checkout", "-q", "-b", contrib)
            git(w, "commit", "-q", "--allow-empty", "-m", "supplied")
            git(w, "push", "-q", "origin", contrib)
            git(w, "checkout", "-q", "main")
            if fold:
                git(w, "merge", "-q", "--no-ff", "-m", "folded", contrib)
                git(w, "push", "-q", "origin", "main")
        w = World()
        j1 = w.working("a note that names the default branch")
        w.sw("deliver", j1, "merged into origin/main", "origin/HEAD")
        w.sw("done", j1)
        settles(w, j1, "the default branch named in an artifact is no contributor branch, so no evidence", "done needs evidence")
        w = World()
        j1 = w.working("delivered, naming the default branch")
        w.sw("deliver", j1, "origin/main")
        settles(w, j1, "…nor is it a delivery", "delivered needs an artifact")

        w = World()
        j1 = w.working("done as a contributor branch the default branch fast-forwarded to")
        git(w, "checkout", "-q", "-b", contrib)
        git(w, "commit", "-q", "--allow-empty", "-m", "supplied")
        git(w, "push", "-q", "origin", contrib)
        git(w, "checkout", "-q", "main")
        git(w, "merge", "-q", "--ff-only", contrib)
        git(w, "push", "-q", "origin", "main")
        w.sw("deliver", j1, contrib)
        w.sw("done", j1)
        w.add("the next job")
        rc, out, err = w.switch()
        check("a branch the default branch was fast-forwarded to shares its tip and still settles done", rc == 0 and f"branch {contrib} on origin/main" in out, out + err)

        w = World()
        j1 = w.working("squash-merged, its branch left un-folded")
        pushed_branch(w)
        gh_says({f"{jobs_world.GH_REPO}#2": "MERGED"})
        w.sw("deliver", j1, f"{jobs_world.GH_REPO}#2", contrib)
        w.sw("done", j1)
        w.add("the next job")
        rc, out, err = w.switch()
        check("a merged pull request settles a done job although its branch was squashed, not folded", rc == 0 and "#2 merged" in out, out + err)

        w = World()
        j1 = w.working("delivered, then the branch was deleted on origin")
        pushed_branch(w)
        w.sw("deliver", j1, contrib)
        origin = subprocess.run(["git", "-C", w.repo, "remote", "get-url", "origin"], capture_output=True, text=True, check=True).stdout.strip()
        subprocess.run(["git", "-C", origin, "branch", "-q", "-D", contrib], check=True, env=git_env())
        settles(w, j1, "a branch deleted on origin is no delivery although its tracking ref lingers", "delivered needs an artifact")

        w = World()
        j1 = w.working("delivered, and already folded")
        pushed_branch(w, fold=True)
        w.sw("deliver", j1, contrib)
        settles(w, j1, "a delivered job whose branch is already on the default branch is done, not delivered", "done, not delivered")

        w = World()
        j1 = w.working("a branch artifact with origin unreachable")
        pushed_branch(w)
        w.sw("deliver", j1, contrib)
        git(w, "remote", "set-url", "origin", os.path.join(w.repo, "no-such-origin"))
        settles(w, j1, "origin unreachable: a branch artifact is unknown, never evidence", "could not tell")

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
        settles(w, j1, "a reply that is not in the journal is not evidence", f"reply:{RID} names no answer this login sent")
        OWN = "01a12bae-0000-7000-8000-000000000001"
        w.journal(("out", answer(OWN, RID)))
        rc, out, err = w.switch()
        check("sent: a reply-only job is settled by the id it answers (the positive control)", rc == 0 and "delivered: reply 01a12bae sent" in out, out + err)
        w = World()
        j1 = w.working("delivered by a reply's own id")
        w.journal(("out", answer(OWN, RID)))
        w.sw("deliver", j1, f"reply:{OWN}")
        w.add("the next job")
        rc, out, err = w.switch()
        check("the reply's own id, the one gzcoord-send prints, settles", rc == 0 and f"reply {OWN[:8]} sent" in out, out + err)
        w = World()
        j1 = w.working("delivered by an inbound reply's id")
        w.journal(("in", answer(OWN, RID)))
        w.sw("deliver", j1, f"reply:{OWN}")
        settles(w, j1, "an inbound REPLY's id is no evidence", f"reply:{OWN} names no answer this login sent")
        w = World()
        j1 = w.working("delivered by an outbound request's id")
        w.journal(("out", request(OWN).replace("FROM: peer/sender", f"FROM: {me}")))
        w.sw("deliver", j1, f"reply:{OWN}")
        settles(w, j1, "an outbound message with no IN-REPLY-TO is no evidence", f"reply:{OWN} names no answer this login sent")

        print("retract: a mistaken artifact is removed, exactly as recorded, under the list lock")
        w = World()
        j1 = w.working("delivered by a wrong reply")
        w.sw("deliver", j1, f"reply:{RID}", f"{jobs_world.GH_REPO}#2")
        w.sw("done", j1)
        w.add("the next job")
        gh_says({f"{jobs_world.GH_REPO}#2": "OPEN"})
        rc, out, err = w.switch()
        check("a done job with a wrong reply: entry cannot be left", rc == 1 and f"reply:{RID} names no answer" in err, out + err)
        rc, out, err = w.sw("retract", j1, f"reply:{RID[:-1]}")
        check("retract of an absent string refuses and lists the artifacts", rc == 1 and f"reply:{RID}" in err and f"{jobs_world.GH_REPO}#2" in err
              and len(w.job(j1)["artifacts"]) == 2, err)
        before = {k: v for k, v in w.job(j1).items() if k not in ("artifacts", "log", "updated")}
        held = jobs.identity.agent_lock(login)      # re-entrant within a process, so the competing retract is a process of its own
        held.__enter__()
        proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "fabric", "jobs.py"), "retract", j1, f"reply:{RID}"],
                                env=os.environ, cwd=w.repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(1)
        waited = proc.poll() is None and len(w.job(j1)["artifacts"]) == 2
        held.__exit__(None, None, None)
        try:
            pout, perr = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            pout, perr = proc.communicate()
        check("with the list lock held elsewhere, retract waits for it", waited)
        check("…and goes on once it is let go", proc.returncode == 0, pout + perr)
        job = w.job(j1)
        check("retract removes that artifact only, notes it in the log with no state, and changes no other field",
              job["artifacts"] == [f"{jobs_world.GH_REPO}#2"] and job["log"][-1].get("kind") == "retract" and "state" not in job["log"][-1]
              and f"reply:{RID}" in job["log"][-1]["note"] and {k: v for k, v in job.items() if k not in ("artifacts", "log", "updated")} == before, repr(job))
        gh_says({f"{jobs_world.GH_REPO}#2": "MERGED"})
        rc, out, err = w.switch()
        check("then the job is left (the positive control)", rc == 0 and "#2 merged" in out, out + err)

        w = World()
        j1 = w.working("a delivered job with a mistaken artifact")
        w.sw("deliver", j1, f"{jobs_world.GH_REPO}#2", "not-a-reference")
        rc, out, err = w.sw("retract", j1, "not-a-reference")
        check("retract works in a state other than done and leaves the state alone", rc == 0 and w.job(j1)["state"] == "delivered"
              and w.job(j1)["artifacts"] == [f"{jobs_world.GH_REPO}#2"], out + err)
        w = World()
        j1 = w.working("a reflection job whose start cannot be read", "--topic", "reflection")
        w.sw("done", j1)
        cursor(w, later)
        jobs_path = os.path.join(w.state, "agents", login, "jobs.json")
        doc = json.load(open(jobs_path))
        for jb in doc["jobs"]:
            jb["created"] = "unreadable"
            for e in jb["log"]:
                e["at"] = "unreadable"
        json.dump(doc, open(jobs_path, "w"))
        w.add("the next job")
        rc, out, err = w.switch()
        check("reflection: a job with no readable start time says the cursor cannot be dated", rc == 1 and "so the fabric-reflect cursor cannot be dated" in err, out + err)

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
        j1 = w.working("an owed reply answered by a DECISION")
        w.sw("drop", j1, "done with it")
        w.journal(("in", request(RID)))
        settles(w, j1, "the request is owed before any answer", f"({RID})")
        w.journal(("out", answer("01a12bae-0000-7000-8000-000000000003", RID).replace("] REPLY", "] DECISION").replace("REPLY:\nok", "DECISION:\nok")))
        rc, out, err = w.switch()
        check("a DECISION with IN-REPLY-TO answers the request (the positive control)", rc == 0, err)
        w = World()
        j1 = w.working("an owed reply answered by an INFO with no IN-REPLY-TO")
        w.sw("drop", j1, "done with it")
        w.journal(("in", request(RID)))
        w.journal(("out", answer("01a12bae-0000-7000-8000-000000000004", RID).replace("] REPLY", "] INFO").replace("IN-REPLY-TO: " + RID + "\n", "")))
        settles(w, j1, "an outbound message with no IN-REPLY-TO answers nothing", f"({RID})")
        for label, kind, state in (("an empty IN-REPLY-TO", "empty", "out"), ("a failed send", "reply", "out-failed"), ("a send still pending", "reply", "out-pending")):
            w = World()
            j1 = w.working(f"an owed reply 'answered' by {label}")
            w.sw("drop", j1, "done with it")
            w.journal(("in", request(RID)))
            text = answer("01a12bae-0000-7000-8000-000000000007", RID)
            if kind == "empty":
                text = text.replace("] REPLY", "] INFO").replace("IN-REPLY-TO: " + RID, "IN-REPLY-TO: ")
            w.journal((state, text))
            settles(w, j1, f"{label} answers nothing", f"({RID})")
            D2 = "01a12bae-0000-7000-8000-000000000008"
            w = World()
            j1 = w.working(f"delivered by the id of {label}")
            w.journal((state, text.replace("000000000007", "000000000008")))
            w.sw("deliver", j1, f"reply:{D2}")
            settles(w, j1, f"reply:<id> of {label} is no evidence", f"reply:{D2} names no answer this login sent")
        w = World()
        j1 = w.working("an owed reply 'answered' by an inbound message")
        w.sw("drop", j1, "done with it")
        w.journal(("in", request(RID)), ("in", answer("01a12bae-0000-7000-8000-000000000005", RID).replace("] REPLY", "] DECISION")))
        settles(w, j1, "an inbound message with IN-REPLY-TO answers nothing", f"({RID})")
        w = World()
        j1 = w.working("delivered by a DECISION's own id")
        D = "01a12bae-0000-7000-8000-000000000006"
        w.journal(("out", answer(D, RID).replace("] REPLY", "] DECISION").replace("REPLY:\nok", "DECISION:\nok")))
        w.sw("deliver", j1, f"reply:{D}")
        w.add("the next job")
        rc, out, err = w.switch()
        check("reply:<id> accepts the id of a DECISION with IN-REPLY-TO", rc == 0 and f"reply {D[:8]} sent" in out, out + err)

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

        print("memory of a session launched above the working copy")
        workspace = os.path.join(home, "projects")
        os.makedirs(workspace)
        key = lambda d: os.path.join(home, ".claude", "projects", jobs_world.re.sub(r"[^A-Za-z0-9]", "-", d), "memory")
        w = World(under=workspace)
        j1 = w.working("launched in ~/projects")
        w.sw("drop", j1, "done with it")
        w.add("next")
        os.utime(key(w.repo), (1, 1)); os.utime(os.path.join(key(w.repo), "fact.md"), (1, 1))
        w.memory_of = workspace
        rc, out, err = w.switch()
        check("a session dir above the working copy settles once a file there changes", rc == 0, err)
        w = World(under=workspace)
        j1 = w.working("sibling and home keys")
        w.sw("drop", j1, "done with it")
        w.add("next")
        for d in (w.repo, workspace):      # the workspace's key still holds the previous case's fresh file
            os.utime(os.path.join(key(d), "fact.md"), (1, 1))
        sibling = os.path.join(workspace, "other-checkout")
        for d in (sibling, home):
            w.memory_of = d
            rc, out, err = w.switch()
            check(f"a memory written for {os.path.relpath(d, tmp)} is not read", rc == 1 and "has not changed during" in err, err)
        w.memory_of = workspace
        rc, out, err = w.switch()
        check("…the ancestor below the home is (the positive control)", rc == 0, err)
        w = World()
        j1 = w.working("no memory anywhere")
        w.sw("drop", j1, "done with it")
        w.add("next")
        shutil.rmtree(key(w.repo))
        rc, out, err = w.sw("switch")
        check("with none existing, the refusal lists the paths tried", rc == 1 and "no memory directory" in err and key(w.repo) in err, err)

        w = World(under=workspace)
        wt = w.repo + "-wt"
        subprocess.run(["git", "-C", w.repo, "worktree", "add", "-q", "-b", "wt-branch", wt], check=True, env=jobs_world.git_env())
        j1 = w.add("job in a linked worktree", "--working-copy", wt)
        w.sw("start", j1)
        w.sw("drop", j1, "done with it")
        w.add("next")
        for d in (w.repo, workspace):
            os.utime(os.path.join(key(d), "fact.md"), (1, 1))
        w.memory_of = os.path.join(workspace, "other-checkout")
        rc, out, err = w.switch(cwd=wt)
        check("a memory written for a sibling is not read for a worktree job", rc == 1 and "has not changed during" in err, err)
        w.memory_of = w.repo
        rc, out, err = w.switch(cwd=wt)
        check("a session launched in the main checkout settles a job in its linked worktree", rc == 0, err)
        settle_mod = sys.modules["fabric_jobs.settle"]
        real_text = settle_mod.vcs.text
        def failing(repo, *a, **k):
            if "--git-common-dir" in a:
                raise settle_mod.vcs.VcsError("git rev-parse: exit 128: boom")
            return real_text(repo, *a, **k)
        settle_mod.vcs.text = failing
        try:
            why = settle_mod.memory_changed({"id": "jX", "created": "2000-01-01T00:00:00Z", "log": []}, [wt])
        finally:
            settle_mod.vcs.text = real_text
        check("a git failure naming the main checkout is said in the refusal, not read as an unwritten memory",
              why is not None and "git could not name the main checkout" in why and "boom" in why and "has not changed" not in why, why)
        cfg = os.path.join(w.repo, ".git", "config")
        with open(cfg, "a", encoding="utf-8") as fh:
            fh.write("[broken\n")
        try:
            why = settle_mod.memory_changed({"id": "jX", "created": "2000-01-01T00:00:00Z", "log": []}, [wt])
        finally:
            with open(cfg, encoding="utf-8") as fh:
                text = fh.read()
            with open(cfg, "w", encoding="utf-8") as fh:
                fh.write(text.replace("[broken\n", ""))
        check("a repository git cannot read is a failure said as such, not 'no repository'",
              why is not None and "could not tell whether jX wrote a memory" in why and "has not changed" not in why, why)
        lone = World()
        shutil.rmtree(key(lone.repo))
        settle_mod.vcs.text = failing
        try:
            why = settle_mod.memory_changed({"id": "jX", "created": "2000-01-01T00:00:00Z", "log": []}, [lone.repo])
        finally:
            settle_mod.vcs.text = real_text
        check("…and with no memory directory at all, the refusal still carries the git failure",
              why is not None and "no memory directory" in why and "boom" in why, why)
        subprocess.run(["git", "-C", home, "init", "-q"], check=True, env=jobs_world.git_env())
        os.makedirs(os.path.join(home, "sub"))
        try:
            gone = [os.path.join(home, "swept-worktree")]
            check("a working copy that no longer exists is not blamed on git, even under a repository",
                  settle_mod.memory_changed({"id": "jX", "created": "2000-01-01T00:00:00Z", "log": []}, gone) is not None
                  and "git could not" not in settle_mod.memory_changed({"id": "jX", "created": "2000-01-01T00:00:00Z", "log": []}, gone), gone)
            got = settle_mod.memory_candidates([os.path.join(home, "sub")])
            check("the home is never a candidate, even when it is itself a repository", home not in got and os.path.join(home, "sub") in got, got)
        finally:
            shutil.rmtree(os.path.join(home, ".git"))
            os.rmdir(os.path.join(home, "sub"))

        w = World(under=workspace)
        w.memory_of = workspace
        j1 = w.add("reflect on it", "--topic", "reflection")
        w.sw("start", j1)
        w.sw("drop", j1, "done with it")
        w.add("next")
        os.utime(os.path.join(key(w.repo), "fact.md"), (1, 1))
        os.utime(os.path.join(key(workspace), "fact.md"), (1, 1))
        elsewhere = os.path.join(home, "herdr")
        w.memory_of = elsewhere
        rc, out, err = w.switch()
        check("a reflection job counts every memory directory of the login", rc == 0, err)
        w = World(under=workspace)
        j1 = w.working("not a reflection")
        w.sw("drop", j1, "done with it")
        w.add("next")
        os.utime(os.path.join(key(w.repo), "fact.md"), (1, 1))
        os.utime(os.path.join(key(workspace), "fact.md"), (1, 1))
        w.memory_of = elsewhere
        rc, out, err = w.switch()
        check("…and another job does not (the positive control)", rc == 1 and "has not changed during" in err, err)

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

        print("leaving a job sweeps what it left (j301): a pushed worktree goes, no branch is deleted, the next job's worktree stays")

        def git_in(path: str, *args: str) -> None:
            subprocess.run(["git", "-C", path, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
                           check=True, env=git_env(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        def left_behind(w: World, push: bool) -> tuple[str, str]:
            """A job with a worktree of its own and one commit (pushed or not), dropped; a queued branch at the default's tip."""
            j1 = w.add("first thing")
            assert w.switch()[0] == 0
            left = w.job(j1)["worktree"]
            git_in(left, "commit", "-q", "--allow-empty", "-m", "work")
            if push:
                git_in(left, "push", "-q", "origin", "HEAD:left-work")
                git_in(left, "fetch", "-q", "origin")
            assert w.sw("drop", j1, "x")[0] == 0
            git_in(w.repo, "branch", "queued-at-tip", "origin/main")
            return j1, left

        def branches_of(w: World) -> str:
            return subprocess.run(["git", "-C", w.repo, "branch", "--format=%(refname:short)"], capture_output=True, text=True).stdout

        # A registry the sweep can read, that lists no session: it removes a worktree only then, and reads every scratch directory
        # under $TMPDIR as an ended session's, so the suite gives it a $TMPDIR of its own.
        readable = {"CLAUDE_CONFIG_DIR": os.path.join(tmp, "claude-config"), "TMPDIR": os.path.join(tmp, "scratch-tmp"),
                    "CLAUDE_CODE_TMPDIR": os.path.join(tmp, "scratch-tmp")}
        os.makedirs(os.path.join(readable["CLAUDE_CONFIG_DIR"], "sessions"))
        os.makedirs(readable["TMPDIR"])

        def with_readable_registry(fn):
            saved = {k: os.environ.get(k) for k in readable}
            os.environ.update(readable)
            try:
                return fn()
            finally:
                for k, v in saved.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v

        w = World()
        j1, left = left_behind(w, push=True)
        j2 = w.add("second thing")
        rc, out, err = w.switch()
        check("a registry that cannot be read keeps the clean pushed worktree the left job leaves, with that reason, and the switch goes on",
              rc == 0 and os.path.isdir(left) and "session registry unreadable" in out and "removed worktree" not in out, out + err)
        check("…no branch is deleted: a queued job's branch may sit at the default branch's tip", "queued-at-tip" in branches_of(w), branches_of(w))
        check("…and what the command said of itself on stderr (no session registry here) reaches the person though it exited 0",
              "fabric-branches: the sessions of this login cannot be listed" in out, out + err)
        check("…and the next job's own worktree is made after the sweep, and stays", os.path.isdir(w.job(j2)["worktree"]) and w.job(j2)["worktree"] != left, out + err)

        w = World()
        j1, left = left_behind(w, push=True)
        j2 = w.add("second thing")
        rc, out, err = with_readable_registry(w.switch)
        check("the worktree the left job leaves, clean and on the remote, is removed, said, with its size, when the registry is readable",
              rc == 0 and not os.path.exists(left) and f"removed worktree {left}" in out and "freed" in out, out + err)
        check("…no branch is deleted there either", "queued-at-tip" in branches_of(w), branches_of(w))

        w = World()
        j1, left = left_behind(w, push=False)
        w.add("second thing")
        rc, out, err = w.switch()
        check("a worktree with a commit on no remote is kept, and the switch says why and goes on",
              rc == 0 and os.path.isdir(left) and "1 commit(s) on no remote" in out, out + err)

        said = sys.modules["fabric_jobs"].leave_sweep.after_leaving(os.path.join(tmp, "not-a-checkout"), None)
        check("a sweep that cannot start is said once, in the line that says it did not finish, and the switch goes on",
              said == ["sweep skipped: no working copy of the job is a directory"], said)
        os.makedirs(os.path.join(tmp, "not-a-checkout"), exist_ok=True)
        said = sys.modules["fabric_jobs"].leave_sweep.after_leaving(os.path.join(tmp, "not-a-checkout"), None)
        check("a sweep that fails is said once, in the line that says it did not finish, naming the line that ended it",
              sum("not in a git working copy" in l for l in said) == 1 and said[-1].startswith("sweep of ")
              and "did not finish (exit 2): fabric-branches: not in a git working copy" in said[-1], said)

        w = World()
        j1, left = left_behind(w, push=True)
        w.add("second thing")
        rc, out, err = with_readable_registry(lambda: w.switch("--json"))
        check("--json: stdout is the one object, the sweep's report is on stderr", rc == 0 and json.loads(out)["job"] and f"removed worktree {left}" in err
              and "removed worktree" not in out, out + err)

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

        print("leaving a job clears its worktree's cargo targets (j75): only that worktree, never a held, live, linked or configured-out one")
        import fcntl

        def cargo_job(w: World, *layout: str) -> tuple[str, str]:
            """A job started with a worktree of its own (under the home, which the step requires) holding `layout`: a path ending
            in / is a directory with a file in it, else a file."""
            j = w.add("with a build")
            assert w.switch()[0] == 0
            left = w.job(j)["worktree"]
            for rel in layout:
                path = os.path.join(left, rel)
                os.makedirs(os.path.dirname(path) if not rel.endswith("/") else path, exist_ok=True)
                if not rel.endswith("/"):
                    with open(path, "w") as fh:
                        fh.write("x" * 2048)
            commit_all(left)
            return j, left

        def commit_all(left: str) -> None:
            """What a real checkout has: the sources committed, the build output ignored (a settled job has no uncommitted change)."""
            with open(os.path.join(left, ".gitignore"), "w") as fh:
                fh.write("target\n")
            git_in(left, "add", "-A")
            git_in(left, "commit", "-q", "-m", "sources")

        def leave(w: World, j: str, how: str = "drop", *flags: str) -> tuple[int, str, str]:
            if how == "drop":
                assert w.sw("drop", j, "x")[0] == 0
            else:
                left = w.job(j)["worktree"]
                branch = w.job(j)["branch"]
                git_in(left, "push", "-q", "origin", f"HEAD:{branch}")
                git_in(left, "fetch", "-q", "origin")
                assert w.sw("pause", j, "later")[0] == 0
            nxt = w.add("next one")
            return w.switch(nxt, *flags)

        w = World(under=home)
        j, left = cargo_job(w, "Cargo.toml", "target/debug/big.o", "app/Cargo.toml", "app/target/release/x", "docs/target/y", "a/b/c/Cargo.toml", "a/b/c/target/z", "a/b/c/d/Cargo.toml", "a/b/c/d/target/z")
        rc, out, err = leave(w, j)
        check("a target beside a Cargo.toml is removed, at the top and below, and said with its size",
              rc == 0 and not os.path.exists(os.path.join(left, "target")) and not os.path.exists(os.path.join(left, "app", "target"))
              and re.search(rf"removed {re.escape(left)}/target \(\d+(\.\d)? (B|KB)\)", out) and f"removed {left}/app/target" in out, out + err)
        check("…a target at the 4th level is removed, one at the 5th is kept",
              not os.path.exists(os.path.join(left, "a/b/c/target")) and os.path.exists(os.path.join(left, "a/b/c/d/target/z")), out + err)
        check("…a target beside no Cargo.toml, and one deeper than 4 levels, stay; so does the source",
              os.path.exists(os.path.join(left, "docs", "target", "y")) and os.path.exists(os.path.join(left, "a/b/c/d/target/z"))
              and os.path.exists(os.path.join(left, "Cargo.toml")), out + err)

        w = World(under=home)
        j, left = cargo_job(w, "Cargo.toml", "target/debug/big.o")
        rc, out, err = leave(w, j, "pause")
        check("a job left paused pays too: its target is removed", rc == 0 and not os.path.exists(os.path.join(left, "target")), out + err)

        w = World(under=home)
        j, left = cargo_job(w, "Cargo.toml", "target/debug/big.o")
        rc, out, err = leave(w, j, "drop", "--keep-targets")
        check("--keep-targets skips the step: the target stays and nothing is said of it",
              rc == 0 and os.path.exists(os.path.join(left, "target", "debug", "big.o")) and "target" not in out.split("branch ")[0], out + err)

        w = World(under=home)
        j, left = cargo_job(w, "Cargo.toml", "target/debug/big.o")
        standing = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], cwd=os.path.join(left, "target", "debug"))
        try:
            time.sleep(0.2)      # exec'd: /proc/<pid>/cwd is the child's, not ours
            rc, out, err = leave(w, j)
        finally:
            standing.kill()
            standing.wait()
        check("a target with this uid's process standing in it is kept, and says so",
              rc == 0 and os.path.exists(os.path.join(left, "target", "debug", "big.o")) and f"kept {left}/target: a process of this uid stands in it" in out, out + err)

        w = World(under=home)
        j, left = cargo_job(w, "Cargo.toml", "target/debug/big.o", "target/debug/.cargo-lock")
        holder = os.open(os.path.join(left, "target", "debug", ".cargo-lock"), os.O_RDONLY)
        fcntl.flock(holder, fcntl.LOCK_EX)
        try:
            rc, out, err = leave(w, j)
            kept_held = os.path.exists(os.path.join(left, "target", "debug", "big.o"))
        finally:
            os.close(holder)
        check("a target whose .cargo-lock is held is kept, and says a build is running",
              rc == 0 and kept_held and f"kept {left}/target: its .cargo-lock is held" in out, out + err)
        rc, out, err = w.sw("show", j)
        w2 = w.add("again")      # the positive control: the same tree, the lock let go, is removed
        w.sw("start", w2)
        shutil_target = os.path.join(left, "target")
        from fabric_jobs.leave_targets import clean_targets as _clean
        said = _clean(left, w.repo)
        check("…and the same target, the lock released, is removed", not os.path.exists(shutil_target) and said and said[0].startswith("removed "), said)

        w = World(under=home)
        j, left = cargo_job(w, "Cargo.toml", "real/keep.o")
        os.symlink(os.path.join(left, "real"), os.path.join(left, "target"))
        rc, out, err = leave(w, j)
        check("a symlinked target is not followed, nor removed", rc == 0 and os.path.exists(os.path.join(left, "real", "keep.o"))
              and os.path.islink(os.path.join(left, "target")) and f"kept {left}/target: a link" in out, out + err)
        w = World(under=home)
        j, left = cargo_job(w, "Cargo.toml", "target/debug/big.o")
        outer = os.path.join(tmp, "outside-target")
        os.makedirs(outer)
        with open(os.path.join(outer, "precious"), "w") as fh:
            fh.write("x")
        os.symlink(outer, os.path.join(left, "target", "inner"))
        rc, out, err = leave(w, j)
        check("a link inside a target is removed as a link: what it points at is untouched",
              rc == 0 and not os.path.exists(os.path.join(left, "target")) and os.path.exists(os.path.join(outer, "precious")), out + err)

        w = World(under=home)
        j, left = cargo_job(w, "Cargo.toml", "target/debug/big.o", ".cargo/config.toml")
        with open(os.path.join(left, ".cargo", "config.toml"), "w") as fh:
            fh.write('[build]\ntarget-dir = "../../elsewhere"\n')
        commit_all(left)
        rc, out, err = leave(w, j)
        check("a cargo configuration sending the target directory outside the worktree keeps the target, and says where",
              rc == 0 and os.path.exists(os.path.join(left, "target", "debug", "big.o")) and "kept" in out and "sends the target directory to" in out, out + err)
        with open(os.path.join(left, ".cargo", "config.toml"), "w") as fh:
            fh.write('[env]\nCARGO_TARGET_DIR = "target-in"\n')
        said = _clean(left, w.repo)
        check("…the same tree with the directory named inside the worktree is removed", said and said[0].startswith("removed "), said)
        os.makedirs(os.path.join(left, "target"))
        with open(os.path.join(left, "Cargo.toml"), "w") as fh:
            fh.write("")
        with open(os.path.join(left, ".cargo", "config.toml"), "w") as fh:
            fh.write("[build\n")
        said = _clean(left, w.repo)
        check("…and a configuration that cannot be parsed keeps it (unknown is not free)", said and said[0].startswith("kept ") and "cannot be read" in said[0], said)

        w = World(under=home)
        j, left = cargo_job(w, "Cargo.toml", "target/debug/big.o", "sub/keep")
        w.add("holds the checkout", "--working-copy", os.path.join(left, "sub"))
        rc, out, err = leave(w, j)
        check("a switch passes the other jobs' working copies: one inside the left worktree keeps its targets, said",
              rc == 0 and "left alone" in out and os.path.isdir(os.path.join(left, "target")), out + err)
        lt0 = sys.modules["fabric_jobs"].leave_targets
        tdir = os.path.join(left, "target")
        check("a target on another filesystem than the worktree's is kept whole, said",
              lt0.one(tdir, left, -1, [], "").startswith(f"kept {tdir}: another filesystem"))

        w = World(under=home)
        j, left = cargo_job(w, "Cargo.toml", "target/debug/big.o", "q/Cargo.toml", "q/target/z")
        w.add("next one")
        racing_choose = sys.modules["fabric_jobs"].verbs.choose
        w.sw("drop", j, "x")

        def racing2(job, **kw):
            made = racing_choose(job, **kw)
            w.sw("add", "a high one that appeared meanwhile", "--working-copy", w.repo, "--priority", "high")
            return made
        sys.modules["fabric_jobs"].verbs.choose = racing2
        try:
            rc, out, err = w.switch()
        finally:
            sys.modules["fabric_jobs"].verbs.choose = racing_choose
        check("a switch that refuses afterwards (the list changed) leaves the targets as they were: the job was not left",
              rc == 1 and "list changed" in err and os.path.exists(os.path.join(left, "target", "debug", "big.o")), out + err)

        w = World(under=home)
        j, left = cargo_job(w, "Cargo.toml", "target/debug/a")
        os.link(os.path.join(left, "target", "debug", "a"), os.path.join(left, "target", "debug", "b"))
        with open(os.path.join(left, "target", "debug", "a"), "w") as fh:
            fh.write("y" * 1_000_000)
        said = _clean(left, w.repo)
        check("a file hard-linked inside a target is counted once in the size", said and re.search(r"\(9\d\d\.\d KB\)|\(1\.0 MB\)", said[0]) and "2.0 MB" not in said[0], said)

        w = World(under=home)
        j, left = cargo_job(w, "Cargo.toml", "target/debug/big.o")
        other = os.path.join(home, f"other-{w.n}")
        os.makedirs(os.path.join(other, "proj", "target"))
        for name in ("Cargo.toml",):
            open(os.path.join(other, "proj", name), "w").close()
        open(os.path.join(other, "proj", "target", "o"), "w").close()
        said = _clean(home, w.repo, (os.path.join(other, "proj"),))
        check("a worktree field above another job's working copy is refused, and nothing under it is touched",
              said and "left alone" in said[0] and os.path.exists(os.path.join(other, "proj", "target", "o")), said)
        os.makedirs(os.path.join(left, "inner", "target"))
        open(os.path.join(left, "inner", "Cargo.toml"), "w").close()
        said = _clean(os.path.join(left, "inner"), left, ())
        check("a worktree field inside a checkout (not a linked worktree) is refused", said and "left alone" in said[0] and os.path.isdir(os.path.join(left, "inner", "target")), said)
        said = _clean(left, w.repo, (left,))
        check("a worktree another job also names is refused", said and "left alone" in said[0] and os.path.isdir(os.path.join(left, "target")), said)
        os.makedirs(os.path.join(left, "sub"))
        said = _clean(left, w.repo, (os.path.join(left, "sub"),))
        check("a worktree that holds another job's working copy is refused (below)", said and "left alone" in said[0] and os.path.isdir(os.path.join(left, "target")), said)
        said = _clean(left, w.repo, (home,))
        check("a worktree that lies inside another job's working copy is refused (above)", said and "left alone" in said[0] and os.path.isdir(os.path.join(left, "target")), said)
        os.rmdir(os.path.join(left, "sub"))
        said = _clean(left, w.repo, (other,))
        check("…and the same worktree with unrelated other jobs is cleared (the positive control)", said and said[0].startswith("removed "), said)

        w = World(under=home)
        j, left = cargo_job(w, "Cargo.toml", "target/debug/big.o")
        os.makedirs(os.path.join(home, ".cargo"), exist_ok=True)
        elsewhere = os.path.join(tmp, "elsewhere-target")
        with open(os.path.join(home, ".cargo", "config.toml"), "w") as fh:
            fh.write(f'[build]\ntarget-dir = "{elsewhere}"\n')
        try:
            said = _clean(left, w.repo)
        finally:
            os.unlink(os.path.join(home, ".cargo", "config.toml"))
            os.rmdir(os.path.join(home, ".cargo"))
        check("a configuration above the worktree ($CARGO_HOME) that sends the target outside keeps it",
              said and said[0].startswith("kept ") and elsewhere in said[0] and os.path.isdir(os.path.join(left, "target")), said)
        # …found by the walk up the parents alone (CARGO_HOME names another place), and by CARGO_HOME alone (no parent has one)
        saved_ch = os.environ.get("CARGO_HOME")
        os.makedirs(os.path.join(home, ".cargo"), exist_ok=True)
        with open(os.path.join(home, ".cargo", "config.toml"), "w") as fh:
            fh.write(f'[build]\ntarget-dir = "{elsewhere}"\n')
        os.environ["CARGO_HOME"] = os.path.join(tmp, "no-cargo-home")
        try:
            said = _clean(left, w.repo)
        finally:
            os.unlink(os.path.join(home, ".cargo", "config.toml"))
            os.rmdir(os.path.join(home, ".cargo"))
        check("…also when only a parent directory's .cargo holds it", said and said[0].startswith("kept ") and elsewhere in said[0], said)
        ch = os.path.join(tmp, "cargo-home")
        os.makedirs(ch, exist_ok=True)
        with open(os.path.join(ch, "config.toml"), "w") as fh:
            fh.write(f'[build]\ntarget-dir = "{elsewhere}"\n')
        os.environ["CARGO_HOME"] = ch
        try:
            said = _clean(left, w.repo)
        finally:
            if saved_ch is None:
                os.environ.pop("CARGO_HOME", None)
            else:
                os.environ["CARGO_HOME"] = saved_ch
        check("…and when only $CARGO_HOME does", said and said[0].startswith("kept ") and elsewhere in said[0], said)
        plain = os.path.join(home, f"plain-{w.n}")
        os.makedirs(os.path.join(plain, "target"))
        open(os.path.join(plain, "Cargo.toml"), "w").close()
        said = _clean(plain, None)
        check("a directory that is no linked worktree (no .git file) is refused though nothing else overlaps it",
              said and "not a linked worktree" in said[0] and os.path.isdir(os.path.join(plain, "target")), said)

        w = World(under=home)
        j, left = cargo_job(w, "Cargo.toml", "target/debug/big.o", "bad/Cargo.toml", "bad/target/z", "bad/.cargo/config.toml", "ok/Cargo.toml", "ok/target/z")
        with open(os.path.join(left, "bad", ".cargo", "config.toml"), "wb") as fh:
            fh.write(b"[build]\ntarget-dir = '\xff\xfe'\n")
        said = _clean(left, w.repo)
        check("a configuration that is not UTF-8 keeps only its own target: the others are still judged and said",
              len(said) == 3 and sum(l.startswith("removed ") for l in said) == 2 and any(l.startswith("kept ") and "/bad/target" in l for l in said)
              and os.path.isdir(os.path.join(left, "bad", "target")), said)
        w = World(under=home)
        j, left = cargo_job(w, "Cargo.toml", "target/debug/big.o", ".cargo/config.toml")
        os.chmod(os.path.join(left, ".cargo"), 0)
        try:
            said = _clean(left, w.repo)
        finally:
            os.chmod(os.path.join(left, ".cargo"), 0o755)
        check("a .cargo directory that cannot be looked into keeps the target: unknown is not absent",
              said and said[0].startswith("kept ") and os.path.isdir(os.path.join(left, "target")), said)

        w = World(under=home)
        j, left = cargo_job(w, "Cargo.toml", "target/debug/big.o")
        lt = sys.modules["fabric_jobs"].leave_targets
        real_cwds = lt.live_cwds

        def blind():
            raise lt.Unknown("processes cannot be listed")
        lt.live_cwds = blind
        try:
            said = _clean(left, w.repo)
        finally:
            lt.live_cwds = real_cwds
        check("a process list that cannot be read keeps every target", said and said[0].startswith("kept ") and "cannot be listed" in said[0]
              and os.path.isdir(os.path.join(left, "target")), said)
        real_listdir = os.listdir

        def no_proc(path="."):
            if path == "/proc":
                raise PermissionError(13, "Permission denied")
            return real_listdir(path)
        os.listdir = no_proc
        try:
            try:
                lt.live_cwds()
                listed_ok = True
            except lt.Unknown:
                listed_ok = False
        finally:
            os.listdir = real_listdir
        check("a /proc that cannot be listed is Unknown, never nobody", not listed_ok)
        unreadable = os.path.join(left, "target", "debug", "locked")
        os.makedirs(unreadable)
        os.chmod(unreadable, 0)
        try:
            said = _clean(left, w.repo)
        finally:
            os.chmod(unreadable, 0o755)
        check("a directory in the target that cannot be read keeps it", said and said[0].startswith("kept ") and "cannot be read" in said[0], said)
        try:
            lt.scan(os.path.join(left, "target"), -1)
            crossed = False
        except lt.Unknown:
            crossed = True
        check("a target on another filesystem than the worktree's is Unknown (scan), never removed", crossed)

        w = World(under=home)
        j1 = w.working("shared checkout")
        os.makedirs(os.path.join(w.repo, "target", "debug"))
        for name in ("Cargo.toml", os.path.join("target", "debug", "o")):
            with open(os.path.join(w.repo, name), "w") as fh:
                fh.write("x")
        with open(os.path.join(w.repo, ".gitignore"), "w") as fh:
            fh.write("target\nCargo.toml\n")
        git_in(w.repo, "add", ".gitignore")
        git_in(w.repo, "commit", "-q", "-m", "ignore")
        w.sw("drop", j1, "x")
        said = _clean(w.repo, w.repo)
        check("the job's working copy is never touched, though the worktree field names it", said and "left alone" in said[0] and os.path.exists(os.path.join(w.repo, "target", "debug", "o")), said)
        w.add("n")
        rc, out, err = w.switch()
        check("…and a switch from a job whose worktree is unset or gone touches nothing and does not fail",
              rc == 0 and os.path.exists(os.path.join(w.repo, "target", "debug", "o")), out + err)
        outside = os.path.join(tmp, "not-in-home")
        os.makedirs(os.path.join(outside, "target"))
        with open(os.path.join(outside, "Cargo.toml"), "w") as fh:
            fh.write("")
        said = _clean(outside, None)
        check("a worktree outside the home is left alone", said and "left alone" in said[0] and os.path.isdir(os.path.join(outside, "target")), said)
        check("an unset field, and a directory that is gone, say nothing", _clean(None, None) == [] and _clean(os.path.join(home, "gone"), None) == [])

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
