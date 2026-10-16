#!/usr/bin/env python3
"""fabric-jobs sweep (agent-fabric ADR-037 rule 10): a delivered job whose evidence has landed becomes done. Run in process
(jobs.main) against a fake gh on PATH and bare origins, with a registry fixture for the project names; the artifact strings are the
shapes old jobs hold (fabric-jobs list --all). Every refusal to close has its positive control in the same world: the job that
differs only by the evidence closes."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import jobs_world  # noqa: E402 — tests/, the script's own directory
from git_env import git_env, scrub_process_env  # noqa: E402 — tests/, the script's own directory
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
scrub_process_env()
own_instance_tree()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = jobs_world.GH_REPO
PROJECT = "fixture-proj"
GH = """#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
fake = os.environ["FAKE_DIR"]
doc = json.load(open(os.path.join(fake, "gh.json")))
if a[:2] == ["pr", "view"] and "--repo" in a:
    key = a[a.index("--repo") + 1] + "#" + a[2]
    with open(os.path.join(fake, "calls.log"), "a") as fh:
        fh.write(key + "\\n")
    if key in doc["states"]:
        print(json.dumps({"state": doc["states"][key]}))
        sys.exit(0)
    sys.stderr.write("GraphQL: Could not resolve to a PullRequest (HTTP 404)\\n")
    sys.exit(1)
sys.stderr.write("fake gh: unsupported: " + " ".join(a) + "\\n")
sys.exit(2)
"""


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {str(detail)[:900]}"))
        fails += not good

    spec = importlib.util.spec_from_file_location("jobs_under_test", os.path.join(ROOT, "tools", "fabric", "jobs.py"))
    jobs = importlib.util.module_from_spec(spec)
    with tempfile.TemporaryDirectory(prefix="jobs-sweep-") as tmp:
        fake = os.path.join(tmp, "fake")
        os.makedirs(os.path.join(fake, "bin"))
        with open(os.path.join(fake, "bin", "gh"), "w", encoding="utf-8") as fh:
            fh.write(GH)
        os.chmod(os.path.join(fake, "bin", "gh"), 0o755)
        home = os.path.join(tmp, "home")
        os.makedirs(home)
        operator = os.path.join(tmp, "operator")
        os.makedirs(os.path.join(operator, "projects"))
        with open(os.path.join(operator, "projects", "registry.json"), "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "projects": {
                PROJECT: {"remotes": [f"git@github.com:{REPO}.git", f"https://github.com/{REPO}"]},
                "other-proj": {"remotes": ["https://github.com/fixture-org/other-proj"]}}}, fh)
        os.environ.update(jobs_world.identity_env(), HOME=home, AGENT_FABRIC_ROOT=ROOT, FAKE_DIR=fake,
                          PATH=os.path.join(fake, "bin") + os.pathsep + os.environ.get("PATH", ""), CLAUDE_CODE_SESSION_ID="sess-A",
                          AGENT_FABRIC_HOSTS_REGISTRY=os.path.join(tmp, "none.json"), AGENT_FABRIC_STATE_DIR=os.path.join(tmp, "state"))
        store = os.path.join(tmp, "store")
        os.makedirs(store)
        with open(os.path.join(store, ".agent-id"), "w", encoding="utf-8") as fh:
            fh.write("01a0f782-7e06-7dee-811f-0a860ed93bf3\n")
        os.environ["AGENT_FABRIC_SECRET_STORE"] = store
        spec.loader.exec_module(jobs)
        login = subprocess.run(["id", "-un"], capture_output=True, text=True, check=True).stdout.strip()
        path = os.path.join(tmp, "state", "agents", login, "jobs.json")
        repo = jobs_world.seeded(os.path.join(tmp, "wc"), os.path.join(tmp, "origins"))

        def git(*args: str) -> str:
            return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True, env=git_env()).stdout.strip()

        main_tip = git("rev-parse", "HEAD")
        git("push", "-q", "origin", "HEAD:refs/heads/dev/host/feat/folded")
        git("checkout", "-q", "-b", "dev/host/feat/ahead")
        git("commit", "-q", "--allow-empty", "-m", "ahead")
        ahead_tip = git("rev-parse", "HEAD")
        git("push", "-q", "origin", "dev/host/feat/ahead")
        git("checkout", "-q", "main")

        def gh_says(states: dict[str, str]) -> None:
            with open(os.path.join(fake, "gh.json"), "w", encoding="utf-8") as fh:
                json.dump({"states": states}, fh)
            open(os.path.join(fake, "calls.log"), "w").close()

        def run(*argv: str) -> tuple[int, str, str]:
            os.chdir(repo)
            out, err = io.StringIO(), io.StringIO()
            outer = os.environ.get("AGENT_FABRIC_OPERATOR")       # a run nested in another's gh lookup puts the outer one's value back
            os.environ["AGENT_FABRIC_OPERATOR"] = operator
            try:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    rc = jobs.main(list(argv))
            finally:
                if outer is None:
                    del os.environ["AGENT_FABRIC_OPERATOR"]
                else:
                    os.environ["AGENT_FABRIC_OPERATOR"] = outer
            return rc, out.getvalue(), err.getvalue()

        def seed(entries: list[tuple[str, list[str]]], project: str | None = PROJECT) -> list[str]:
            """One job per (state, artifacts), j1.. in order, written as the list keeps them."""
            ids = []
            for n, (state, arts) in enumerate(entries, 1):
                rc, out, err = run("add", f"job {n}", "--working-copy", repo, *(["--project", project] if project else []))
                assert rc == 0, err
                ids.append(out.split()[1])
            doc = json.load(open(path, encoding="utf-8"))
            for job, (state, arts) in zip(doc["jobs"][-len(entries):], entries):
                job.update(state=state, artifacts=arts, project=project)
            json.dump(doc, open(path, "w", encoding="utf-8"))
            return ids

        def job(jid: str) -> dict:
            return next(j for j in json.load(open(path, encoding="utf-8"))["jobs"] if j["id"] == jid)

        def line(out: str, jid: str) -> str:
            return next((l for l in out.splitlines() if l.startswith(jid + " ")), "")

        print("the shapes old jobs hold: a merged pull request closes, whatever form names it")
        gh_says({f"{REPO}#5": "MERGED", f"{REPO}#6": "MERGED", f"{REPO}#7": "MERGED", f"{REPO}#8": "MERGED", f"{REPO}#9": "MERGED",
                 f"{REPO}#10": "OPEN", f"{REPO}#11": "MERGED", "fixture-org/other-proj#3": "MERGED"})
        shapes = [f"pr:{REPO}#5", f"{PROJECT} #6", f"{PROJECT} PR #7", f"{PROJECT}#8 merged (3 work, 1 fix)", f"https://github.com/{REPO}/pull/9",
                  "other-proj #3 merged", "other-proj PR 3 (no hash sign)"]
        ids = seed([("delivered", [a]) for a in shapes])
        before = open(path, "rb").read()
        rc, out, err = run("sweep", "--dry-run")
        check("--dry-run changes nothing", rc == 0 and open(path, "rb").read() == before, out + err)
        check("each form is read: pr:o/r#N, <project> #N, <project> PR #N, <project>#N, the URL, another project's #N, its PR N",
              all("would close" in line(out, j) for j in ids), out + err)
        check("the line names the evidence", f"{REPO}#5 merged" in line(out, ids[0]) and "fixture-org/other-proj#3 merged" in line(out, ids[5]), out)
        rc, out, err = run("sweep")
        done = [job(j) for j in ids]
        check("without --dry-run they are done, each with a note naming the evidence", rc == 0 and all(j["state"] == "done" for j in done)
              and all(j["log"][-1].get("note", "").startswith("swept: ") and "merged" in j["log"][-1]["note"] for j in done), out + err)
        check("no artifact is removed", [j["artifacts"] for j in done] == [[a] for a in shapes])
        after = open(path, "rb").read()
        rc, out, err = run("sweep")
        check("a second run changes nothing", rc == 0 and open(path, "rb").read() == after and "no delivered jobs" in out, out + err)

        print("what stays delivered, and why")
        gh_says({f"{REPO}#10": "OPEN", f"{REPO}#11": "MERGED", f"{REPO}#12": "MERGED", "fixture-org/other-proj#3": "MERGED"})
        ids = seed([("delivered", [f"{REPO}#10"]),                                                      # open
                    ("delivered", ["scan reported to the coordinator (seq above)"]),                    # unresolvable free text
                    ("delivered", [f"{REPO}#404"]),                                                     # gh cannot answer
                    ("delivered", [f"{REPO}#11", f"{REPO}#10"]),                                        # one merged, one still open
                    ("delivered", [f"{REPO}#11", "gzcoord #13 (a project the registry does not hold)"]),   # merged beside a #N of no known repository
                    ("delivered", []),
                    ("delivered", ["branch:dev/host/feat/gone"]),
                    ("queued", [f"{REPO}#12"]), ("active", [f"{REPO}#12"]), ("paused", [f"{REPO}#12"]), ("blocked", [f"{REPO}#12"]),
                    ("done", [f"{REPO}#12"]), ("dropped", [f"{REPO}#12"]),
                    ("delivered", [f"{REPO}#12"]),                                                     # the positive control
                    ("delivered", ["gzcoord #11", "gzcoord PR 11"]),                                    # REPO#11 is merged: the job's own, were it read so
                    ("delivered", [f"{REPO}#12", "reply:01a14482-0000-7000-8000-000000000001"]),        # a reply this login never sent
                    ("delivered", ["other-proj #3, #11"]),                                              # both merged: the second is another list item of other-proj
                    ("delivered", ["other-proj pull request #3 and unregistered merged #11"]),
                    ("delivered", [f"{PROJECT} #11 and {PROJECT} #12 merged"]),                          # the positive control: each number with its project
                    ("delivered", ["fixture-org/other-proj#3, #11"]),
                    ("delivered", ["PR #11 merged"]),                                                   # a bare number: whose?
                    ("delivered", [f"{PROJECT} #11 merged, and fixes #12 in unreg"]),                   # a number after, naming another repository
                    ("delivered", [f"{REPO}#11", "gzcoord#4"]),                                         # a shape no pattern reads, beside a merged one
                    ("delivered", ["gzcoord pull request", "#11"]),
                    ("delivered", [f"{REPO}#11", "see PR 12"])])                                        # a name in one artifact, the number in the next
        reflection = seed([("delivered", [f"{REPO}#12"])])[0]
        doc = json.load(open(path, encoding="utf-8"))
        next(j for j in doc["jobs"] if j["id"] == reflection)["topic"] = "reflection"
        json.dump(doc, open(path, "w", encoding="utf-8"))
        ids_unreg = seed([("delivered", [f"{REPO}#11", "PR #13"])], project="unregistered")
        before = open(path, "rb").read()
        rc, out, err = run("sweep")
        check("an open pull request stays and is named", "stays" in line(out, ids[0]) and f"{REPO}#10" in line(out, ids[0]) and "open" in line(out, ids[0]), out)
        check("an unresolvable free-text artifact stays", "stays" in line(out, ids[1]) and "no artifact" in line(out, ids[1]), out)
        check("a gh failure stays and says it could not tell", "stays" in line(out, ids[2]) and "could not tell" in line(out, ids[2]), out)
        check("a merged and an open pull request together stay", "stays" in line(out, ids[3]) and "open" in line(out, ids[3]), out)
        check("a #N with no registered project beside a merged one stays", "stays" in line(out, ids_unreg[0]) and "unresolved" in line(out, ids_unreg[0]), out)
        check("a #N that follows another project's name is not the job's own pull request", "stays" in line(out, ids[4]) and "names no repository" in line(out, ids[4]), out)
        check("no artifacts stays", "stays" in line(out, ids[5]) and "no artifacts" in line(out, ids[5]), out)
        check("a branch that is not on origin stays, and says so", "stays" in line(out, ids[6]) and "is not on origin" in line(out, ids[6]), out)
        check("the positive control, the same world, closes", "closed" in line(out, ids[13]) and job(ids[13])["state"] == "done", out)
        check("a number after an unregistered project's name, with or without #, is no pull request of the job's own",
              "stays" in line(out, ids[14]) and "names no repository" in line(out, ids[14]) and job(ids[14])["state"] == "delivered", out)
        check("a reply artifact the journal does not hold stays beside a merged pull request, as `done` would refuse it",
              "stays" in line(out, ids[15]) and "names no answer this login sent" in line(out, ids[15]) and job(ids[15])["state"] == "delivered", out)
        check("a bare number after a registered project's name or any other word is not the job's own",
              all("stays" in line(out, j) and "names no repository" in line(out, j) for j in (ids[16], ids[17], ids[19])) and all(job(j)["state"] == "delivered" for j in (ids[16], ids[17], ids[19])), out)
        check("the positive control, each number written with its project, closes", "closed" in line(out, ids[18]), out)
        check("a bare number, one that follows its project's name, and a shape no pattern reads all stay",
              all("stays" in line(out, j) and "names no repository" in line(out, j) for j in ids[20:23] + ids[23:25]) and all(job(j)["state"] == "delivered" for j in ids[20:25]), out)
        check("a reflection job is asked for its cursor too, and stays without one", "stays" in line(out, reflection) and "fabric-reflect" in line(out, reflection), out)
        check("every other delivered job is still delivered, every other state untouched",
              all(job(j)["state"] == "delivered" for j in ids[:7]) and job(ids_unreg[0])["state"] == "delivered"
              and [job(j)["state"] for j in ids[7:13]] == ["queued", "active", "paused", "blocked", "done", "dropped"]
              and not any(line(out, j) for j in ids[7:13])      # not even a line: they are not this verb's business
              and all(job(j)["log"] == json.loads(before)["jobs"][int(j[1:]) - 1]["log"] for j in ids[7:13]), out)

        print("a reflection job is done on the closed cursor, with no artifact at all")
        with open(os.path.join(tmp, "state", "agents", login, "reflect-cursor.json"), "w", encoding="utf-8") as fh:
            json.dump({"agent_id": "01a0f782-7e06-7dee-811f-0a860ed93bf3", "row": 7, "episode": "e", "done_at": "2999-01-01T00:00:00Z"}, fh)
        bare_pass = seed([("delivered", [])])[0]
        doc = json.load(open(path, encoding="utf-8"))
        next(j for j in doc["jobs"] if j["id"] == bare_pass)["topic"] = "reflection"
        json.dump(doc, open(path, "w", encoding="utf-8"))
        rc, out, err = run("sweep")
        check("it closes, naming the cursor", "closed" in line(out, bare_pass) and "fabric-reflect cursor at row 7" in line(out, bare_pass), out + err)
        check("the same cursor lets the reflection job that also has a merged pull request close", "closed" in line(out, reflection), out)
        os.remove(os.path.join(tmp, "state", "agents", login, "reflect-cursor.json"))

        print("one gh lookup per distinct pull request")
        gh_says({f"{REPO}#21": "MERGED"})
        ids = seed([("delivered", [f"{REPO}#21"]), ("delivered", [f"{PROJECT} #21"]), ("delivered", [f"{PROJECT} PR #21"])])
        rc, out, err = run("sweep")
        calls = [c for c in open(os.path.join(fake, "calls.log"), encoding="utf-8").read().split() if c.endswith("#21")]    # earlier sections' stayers are asked again
        check("three jobs naming one pull request ask gh once, and all close", calls == [f"{REPO}#21"] and all(job(j)["state"] == "done" for j in ids), calls)
        gh_says({})
        ids = seed([("delivered", [f"{REPO}#22"]), ("delivered", [f"{REPO}#22"])])
        rc, out, err = run("sweep")
        calls = [c for c in open(os.path.join(fake, "calls.log"), encoding="utf-8").read().split() if c.endswith("#22")]
        check("a lookup that failed is not repeated for the next job, and both stay", calls == [f"{REPO}#22"]
              and all(job(j)["state"] == "delivered" for j in ids), calls)

        print("a job that changed while gh was asked is not closed on the evidence read from the old one")
        gh_says({f"{REPO}#31": "MERGED"})
        ids = seed([("delivered", [f"{REPO}#31"])])
        sweep_part = sys.modules["fabric_jobs.sweep"]
        asked = sweep_part.PrStates.__call__

        def edited_meanwhile(self, repo_name, number):
            if number == "31":
                assert run("deliver", ids[0], "an artifact added meanwhile")[0] == 0
            return asked(self, repo_name, number)
        sweep_part.PrStates.__call__ = edited_meanwhile
        try:
            rc, out, err = run("sweep")
        finally:
            sweep_part.PrStates.__call__ = asked
        check("it stays and says so", "stays (changed while the sweep ran)" in line(out, ids[0]) and job(ids[0])["state"] == "delivered", out + err)
        rc, out, err = run("sweep")
        check("the next sweep, reading the new artifacts, closes it", "closed" in line(out, ids[0]), out + err)

        print("a fetch that fails is not repeated for every job, and none of them closes on it")
        gh_says({})
        ids = seed([("delivered", ["branch:dev/host/feat/folded"]), ("delivered", [f"{PROJECT} commit {main_tip[:8]}"])])
        vcs_part, fetched = sys.modules["fabric_jobs.vcs"], []
        real_fetch = vcs_part.fetch

        def broken(where):
            fetched.append(where)
            raise vcs_part.VcsError("git fetch: exit 128: the remote is gone")
        vcs_part.fetch = broken
        try:
            rc, out, err = run("sweep")
        finally:
            vcs_part.fetch = real_fetch
        check("one attempt, both stay, and the line says git could not tell", len(fetched) == 1 and all("stays" in line(out, j) and "the remote is gone" in line(out, j) for j in ids), (fetched, out))

        print("commits and branches on origin's default branch")
        gh_says({})
        ids = seed([("delivered", ["branch:dev/host/feat/folded"]),
                    ("delivered", ["develop/dev/host/feat/ahead pushed, no PR"]),
                    ("delivered", [f"{PROJECT} commit {main_tip[:8]}"]),
                    ("delivered", [f"{PROJECT} commit {ahead_tip[:8]}"]),
                    ("delivered", [f"merged as {main_tip[:8]}"]),
                    ("delivered", ["branch:dev/host/feat/ahead"])])
        vcs_part, fetched = sys.modules["fabric_jobs.vcs"], []
        real_fetch = vcs_part.fetch
        vcs_part.fetch = lambda where: (fetched.append(where), real_fetch(where))[1]
        try:
            rc, out, err = run("sweep")
        finally:
            vcs_part.fetch = real_fetch
        check("the checkout is fetched once for the whole run, however many jobs ask git", len(fetched) == 1, fetched)
        check("a branch artifact whose tip is on origin/main closes", "closed" in line(out, ids[0]) and "branch dev/host/feat/folded" in line(out, ids[0]), out + err)
        check("a branch ahead of origin/main stays", "stays" in line(out, ids[5]) and "not on origin/main" in line(out, ids[5]), out)
        check("a commit beside the project's name, on origin/main, closes", "closed" in line(out, ids[2]) and main_tip[:8] in line(out, ids[2]), out)
        check("a commit not on origin/main stays", "stays" in line(out, ids[3]), out)
        check("a commit with no project beside it is no evidence", "stays" in line(out, ids[4]), out)

    print("PASS" if not fails else f"FAILED: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
