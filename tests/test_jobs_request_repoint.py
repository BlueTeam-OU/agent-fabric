#!/usr/bin/env python3
"""A request blocker answered by a 'taken' REPLY (tools/fabric/jobsparts/blockers.py, request:): a REPLY answers the request,
it does not deliver the work, so the job the request became on the answerer's board replaces the blocker and the job stays
blocked. The real bin/fabric-jobs runs against a scratch state directory, a scratch journal seeded through episodic.py and a
fake fabric-ctl (AGENT_FABRIC_CTL) that serves each login's board; the login's own state and journal are never touched."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from instance_fixtures import write_operator_projects  # noqa: E402 — tests/, the script's own directory
import jobs_world  # noqa: E402 — tests/, the script's own directory
from git_env import scrub_process_env  # noqa: E402 — tests/, the script's own directory
from test_jobs_blockers import AGENT, CTL  # noqa: E402 — the fake fabric-ctl the other blocker suite uses
scrub_process_env()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS = os.path.join(ROOT, "bin", "fabric-jobs")


def mid(n: int) -> str:
    return f"01a1a000-0000-7000-8000-{n:012d}"


def answer(kind: str, n: int, sender: str, to: str, body: str) -> str:
    return (f"[GZCOORD/1] {kind}\nFROM: develop-qzapp/{sender}\nROLE: x\nTO: develop-qzapp/me\nIN-REPLY-TO: {to}\n"
            f"MESSAGE-ID: {mid(1000 + n)}\nSUBJECT: s\n\n{kind}:\n{body}\n")


def row(job_id: str, request: str | None, state: str = "active") -> dict:
    title = f"work on it (REQUEST {request.upper()})" if request else "unrelated work"      # as the sender's jobs-add writes it
    return {"id": job_id, "state": state, "title": title}


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {str(detail)[:600]}"))
        fails += not good

    with tempfile.TemporaryDirectory(prefix="jobs-repoint-") as tmp:
        fake = os.path.join(tmp, "fake")
        os.makedirs(os.path.join(fake, "bin"))
        with open(os.path.join(fake, "bin", "fabric-ctl"), "w") as fh:
            fh.write(CTL)
        os.chmod(os.path.join(fake, "bin", "fabric-ctl"), 0o755)
        store = os.path.join(tmp, "store")
        os.makedirs(store)
        with open(os.path.join(store, ".agent-id"), "w") as fh:
            fh.write(AGENT + "\n")
        home = os.path.join(tmp, "home")
        os.makedirs(home)
        state = os.path.join(tmp, "state")
        env = {**os.environ, "AGENT_FABRIC_STATE_DIR": state, "AGENT_FABRIC_ROOT": ROOT, "HOME": home, "FAKE_DIR": fake,
               "AGENT_FABRIC_CTL": os.path.join(fake, "bin", "fabric-ctl"), "AGENT_FABRIC_SECRET_STORE": store,
               "CLAUDE_CODE_SESSION_ID": "sess-A", "CLAUDE_BRIDGE_URL": "http://127.0.0.1:9", "CLAUDE_BRIDGE_AUTH_TOKEN": "tok",
               "AGENT_FABRIC_HOSTS_REGISTRY": os.path.join(tmp, "none.json")}
        env["AGENT_FABRIC_OPERATOR"] = write_operator_projects(os.path.join(tmp, "operator"), {"fixture-proj": ["git@example.org:o/fixture-proj.git"]})
        repo = jobs_world.seeded(os.path.join(tmp, "alpha"), os.path.join(tmp, "origins"))
        env.update(jobs_world.identity_env(), GH_REPO=jobs_world.GH_REPO)

        boards: dict[str, list[dict]] = {}

        def put_boards() -> None:
            with open(os.path.join(fake, "ctl.json"), "w") as fh:
                json.dump({"logins": boards}, fh)

        def run(*argv: str) -> subprocess.CompletedProcess:
            return subprocess.run([JOBS, *argv], cwd=repo, env=env, capture_output=True, text=True, timeout=120)

        def job(i: str, *extra: str) -> dict:
            return next(j for j in json.loads(run("list", "--all", "--json", *extra).stdout) if j["id"] == i)

        def cache() -> dict:
            for d, _, fs in os.walk(state):
                if "jobs-blockers.json" in fs:
                    return json.load(open(os.path.join(d, "jobs-blockers.json")))
            return {}

        def age(by: int = 700) -> None:
            for d, _, fs in os.walk(state):
                if "jobs-blockers.json" in fs:
                    path = os.path.join(d, "jobs-blockers.json")
                    doc = json.load(open(path))
                    for v in doc.values():
                        if "checked_at" in v:
                            v["checked_at"] -= by
                    json.dump(doc, open(path, "w"))

        def journal(content: str, seq: int) -> None:
            subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fabric", "episodic.py"), "gzcoord-in"], env=env,
                           input=json.dumps({"content": content, "seq": seq}) + "\n", capture_output=True, text=True, timeout=60, check=True)

        n = 0

        def blocked_on_request(title: str, request: str) -> tuple[str, subprocess.CompletedProcess]:
            """A job blocked on `request`; the block is the first look, so the journal is seeded before it."""
            added = run("add", title)
            jid = re.search(r"added (j\d+)", added.stdout).group(1)
            run("start", jid)
            return jid, run("block", jid, "--on", f"request:{request}")

        def case(sender: str, body: str, request: str, kind: str = "REPLY") -> str:
            nonlocal n
            n += 1
            journal(answer(kind, n, sender, request, body), n)
            return request

        print("(a) taken, and the sender's board has a row naming the request: re-pointed, still blocked, seen open")
        boards["boardy"] = [row("j12", mid(1)), row("j13", None)]
        put_boards()
        case("boardy", "taken as j13", mid(1))      # the body names another job: the board is the authority
        jid, r = blocked_on_request("held on boardy", mid(1))
        check("the first look says it once", f"request:{mid(1)} answered; now waiting on job:boardy/j12" in r.stdout, (r.stdout, r.stderr))
        j = job(jid, "--stored")
        check("blocked, on the job and not the request", j["state"] == "blocked" and [b["spec"] for b in j["blockers"]] == ["job:boardy/j12"], j)
        check("it is not handed back: the job is not cleared", j["cleared"] is not True, j)
        check("…and the new spec was seen open", cache().get("job:boardy/j12", {}).get("seen_open") is True, cache())
        check("the request is no longer waited on (waits_on) and blocked_on names the job",
              "waits_on" not in j and "job:boardy/j12" in j["blocked_on"], j)
        check("said once: the next listing does not repeat it", "answered; now waiting on" not in run("list").stdout)

        print("(b) the board row delivered later: cleared")
        boards["boardy"] = [row("j12", mid(1), "delivered"), row("j13", None)]
        put_boards()
        age()
        out = run("list").stdout
        check("blocker cleared: job:boardy/j12", "blocker cleared: job:boardy/j12" in out, out)
        run("start", jid)
        run("done", jid, "--no-artifact", "test")

        print("(c) a decline, no board row, no token: cleared as before")
        boards["decliner"] = []
        put_boards()
        case("decliner", "no, not taking this", mid(2))
        jid, r = blocked_on_request("held on decliner", mid(2))
        j = job(jid, "--stored")
        check("cleared, the blocker kept as the request", j["cleared"] is True and j["blockers"][0]["spec"] == f"request:{mid(2)}", j)
        run("start", jid)
        run("done", jid, "--no-artifact", "test")

        print("(d) the board unreachable, the body says 'taken as j7': re-pointed to the sender's job, not yet seen")
        case("nobody", "taken as j7", mid(3))
        jid, r = blocked_on_request("held on an unreachable board", mid(3))
        j = job(jid, "--stored")
        check("re-pointed to job:nobody/j7, still blocked", j["state"] == "blocked" and [b["spec"] for b in j["blockers"]] == ["job:nobody/j7"], j)
        check("…not marked seen open (nothing showed it)", "seen_open" not in cache().get("job:nobody/j7", {}), cache())
        check("…and not cleared: an unseen job is unknown", j["cleared"] is None, j)
        run("start", jid)
        run("done", jid, "--no-artifact", "test")

        print("(e) the board unreachable, no token: unknown, never cleared")
        case("nobody", "ok, on it", mid(4))
        jid, r = blocked_on_request("held, answered without a job", mid(4))
        j = job(jid, "--stored")
        check("unknown", j["cleared"] is None and j["blockers"][0]["state"] == "unknown" and j["blockers"][0]["spec"] == f"request:{mid(4)}", j)
        check("…and the job is not listed as ready", "blocker cleared" not in run("list").stdout)
        run("start", jid)
        run("done", jid, "--no-artifact", "test")

        print("(f) two j<n> tokens: no re-point")
        case("nobody", "taken as j7, after j8", mid(5))
        jid, r = blocked_on_request("two tokens, board unreachable", mid(5))
        j = job(jid, "--stored")
        check("unreachable board: unknown on the request", j["cleared"] is None and j["blockers"][0]["spec"] == f"request:{mid(5)}", j)
        run("start", jid)
        run("done", jid, "--no-artifact", "test")
        boards["twotok"] = [row("j7", None), row("j8", None)]
        put_boards()
        case("twotok", "j7 and j8", mid(6))
        jid, r = blocked_on_request("two tokens, board readable", mid(6))
        j = job(jid, "--stored")
        check("readable board without a row: cleared, not re-pointed", j["cleared"] is True and j["blockers"][0]["spec"] == f"request:{mid(6)}", j)
        run("start", jid)
        run("done", jid, "--no-artifact", "test")

        print("the body, with a readable board: only a job the board lists; job:<other>/j<n> is not the sender's")
        boards["lister"] = [row("j20", None)]
        put_boards()
        case("lister", "taken as j20", mid(7))
        jid, r = blocked_on_request("body token listed", mid(7))
        j = job(jid, "--stored")
        check("re-pointed, and seen open (the board showed it)", [b["spec"] for b in j["blockers"]] == ["job:lister/j20"]
              and cache().get("job:lister/j20", {}).get("seen_open") is True, (j, cache()))
        run("start", jid)
        run("done", jid, "--no-artifact", "test")
        case("lister", "taken as j99", mid(8))
        jid, r = blocked_on_request("body token closed", mid(8))
        j = job(jid, "--stored")
        check("a token the readable board does not list is a closed job: cleared", j["cleared"] is True and j["blockers"][0]["spec"] == f"request:{mid(8)}", j)
        run("start", jid)
        run("done", jid, "--no-artifact", "test")
        case("nobody", "see job:elsewhere/j5; taken as job:nobody/j6", mid(9))
        jid, r = blocked_on_request("another login's job named", mid(9))
        j = job(jid, "--stored")
        check("only the sender's job counts", [b["spec"] for b in j["blockers"]] == ["job:nobody/j6"], j)
        run("start", jid)
        run("done", jid, "--no-artifact", "test")

        print("a DECISION clears by its type: the board unreadable, or a job token in the body, change nothing")
        case("nobody", "decided: no", mid(11), "DECISION")
        jid, r = blocked_on_request("decision, unreadable board", mid(11))
        check("cleared", job(jid, "--stored")["cleared"] is True, job(jid, "--stored"))
        run("start", jid)
        run("done", jid, "--no-artifact", "test")
        case("nobody", "decided; see j4 for context", mid(12), "DECISION")
        jid, r = blocked_on_request("decision naming a job", mid(12))
        j = job(jid, "--stored")
        check("cleared, not re-pointed", j["cleared"] is True and j["blockers"][0]["spec"] == f"request:{mid(12)}", j)
        run("start", jid)
        run("done", jid, "--no-artifact", "test")

        case("nobody", "ack, looking", mid(14))
        case("nobody", "decided: no", mid(14), "DECISION")
        jid, r = blocked_on_request("ack then decision", mid(14))
        check("an unreadable ack does not hold back a later DECISION", job(jid, "--stored")["cleared"] is True, job(jid, "--stored"))
        run("start", jid)
        run("done", jid, "--no-artifact", "test")

        print("a board row whose id is not a job id is no job")
        boards["liar"] = [{"id": "j3\nINJECTED", "state": "active", "title": f"x (REQUEST {mid(13)})"}]
        put_boards()
        case("liar", "taken", mid(13))
        jid, r = blocked_on_request("hostile board row", mid(13))
        j = job(jid, "--stored")
        check("nothing hostile is stored; the request clears as with no row", "INJECTED" not in json.dumps(j) and j["blockers"][0]["spec"] == f"request:{mid(13)}", j)
        run("start", jid)
        run("done", jid, "--no-artifact", "test")

        print("j751: a message this login sent as an OBSERVATION or QUESTION is answered by any reply naming it")

        def sent(kind: str, n: int) -> str:
            """A message of this login, journaled as sent, as the send command leaves it."""
            text = (f"[GZCOORD/1] {kind}\nFROM: develop-qzapp/me\nROLE: x\nTO: develop-qzapp/nobody\nMESSAGE-ID: {mid(n)}\n"
                    f"SUBJECT: s\n\n{kind}:\nbody\n")
            subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fabric", "episodic.py"), "gzcoord-out-pending"], env=env,
                           input=text, capture_output=True, text=True, timeout=60, check=True)
            subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fabric", "episodic.py"), "gzcoord-out-final", mid(n),
                            "--state", "accepted"], env=env, capture_output=True, text=True, timeout=60, check=True)
            return mid(n)

        for kind, k in (("OBSERVATION", 20), ("QUESTION", 21)):
            sent(kind, k)
            case("nobody", "ok, noted", mid(k))      # the board of nobody is unreadable and the body names no job
            jid, r = blocked_on_request(f"held on an answered {kind}", mid(k))
            j = job(jid, "--stored")
            check(f"an answered {kind} clears", j["cleared"] is True and j["blockers"][0]["spec"] == f"request:{mid(k)}", j)
            run("start", jid)
            run("done", jid, "--no-artifact", "test")
        sent("REQUEST", 22)
        case("nobody", "ok, noted", mid(22))
        jid, r = blocked_on_request("held on an answered REQUEST (the control)", mid(22))
        check("positive control: an answered REQUEST on an unreadable board stays unknown", job(jid, "--stored")["cleared"] is None, job(jid, "--stored"))
        run("start", jid)
        run("done", jid, "--no-artifact", "test")

        print("a second job on the same request is re-pointed with the first")
        boards["boardy"] = [row("j30", mid(10))]
        put_boards()
        case("boardy", "taken", mid(10))
        j1, _ = blocked_on_request("first on mid 10", mid(10))
        j2 = re.search(r"added (j\d+)", run("add", "second on mid 10").stdout).group(1)
        # Both are blocked before either is looked at: the cache still has the first's answer, the second's block forgets nothing.
        run("start", j2)
        run("block", j2, "--on", f"request:{mid(10)}")
        check("both name job:boardy/j30", all([b["spec"] for b in job(j, "--stored")["blockers"]] == ["job:boardy/j30"] for j in (j1, j2)),
              (job(j1, "--stored"), job(j2, "--stored")))

    print("pass" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
