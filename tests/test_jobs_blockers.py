#!/usr/bin/env python3
"""Checkable blockers of bin/fabric-jobs (tools/fabric/jobsparts/blockers.py): `block <id> --on pr:… | request:… |
job:…` clears by itself. A fake gh on PATH, a scratch journal seeded through episodic.py and a fake fabric-ctl
(AGENT_FABRIC_CTL) stand in for the three; the real command and a scratch state directory run, never the login's own."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from instance_fixtures import write_operator_projects  # noqa: E402 — tests/, the script's own directory
from git_env import git_env, scrub_process_env  # noqa: E402 — tests/, the script's own directory
scrub_process_env()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS = os.path.join(ROOT, "bin", "fabric-jobs")
AGENT = "01a0f782-7e06-7dee-811f-0a860ed93bf3"
RID = "01a12bae-9f03-7d83-8795-bcac9d940240"      # a request this login sent
OTHER = "01a12baf-6ed2-73aa-9a5f-5cc759498af1"    # a message nobody replied to
GH = """#!/usr/bin/env python3
import json, os, sys
d = os.environ["FAKE_DIR"]
a = sys.argv[1:]
open(os.path.join(d, "gh.calls"), "a").write(" ".join(a) + "\\n")
states = json.load(open(os.path.join(d, "gh.states")))
if a[:2] == ["pr", "view"] and "--repo" in a:
    key = a[a.index("--repo") + 1] + "#" + a[2]
    if key in states:
        print("[]" if states[key] == "__ARRAY__" else json.dumps({"state": states[key]}))
        sys.exit(0)
    sys.stderr.write("GraphQL: Could not resolve to a PullRequest with the number (HTTP 404)\\n")
    sys.exit(1)
sys.stderr.write("fake gh: unsupported: " + " ".join(a) + "\\n")
sys.exit(2)
"""
CTL = """#!/usr/bin/env python3
import json, os, sys
d = os.environ["FAKE_DIR"]
a = sys.argv[1:]
open(os.path.join(d, "ctl.calls"), "a").write(" ".join(a) + "\\n")
doc = json.load(open(os.path.join(d, "ctl.json")))
login = a[0]
if doc.get("refuse"):
    sys.stderr.write("fabric-ctl: " + doc["refuse"] + "\\n")
    sys.exit(2)
if login not in doc.get("logins", {}):
    print(json.dumps({"account": login, "host": "h", "status": "no answer"}))
    sys.exit(1)
print(json.dumps({"account": login, "host": "h", "status": "ok", "jobs": {"status": "ok", "jobs": doc["logins"][login]}}))
"""


def reply(mid: str, to: str) -> str:
    return (f"[GZCOORD/1] REPLY\nFROM: develop-qzapp/peer\nROLE: x\nTO: develop-qzapp/me\nIN-REPLY-TO: {to}\n"
            f"MESSAGE-ID: {mid}\nSUBJECT: s\n\nREPLY:\ndone\n")


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {str(detail)[:500]}"))
        fails += not good

    with tempfile.TemporaryDirectory(prefix="jobs-blockers-") as tmp:
        fake = os.path.join(tmp, "fake")
        os.makedirs(os.path.join(fake, "bin"))
        for name, body in (("gh", GH), ("fabric-ctl", CTL)):
            with open(os.path.join(fake, "bin", name), "w") as fh:
                fh.write(body)
            os.chmod(os.path.join(fake, "bin", name), 0o755)
        store = os.path.join(tmp, "store")
        os.makedirs(store)
        with open(os.path.join(store, ".agent-id"), "w") as fh:
            fh.write(AGENT + "\n")
        home = os.path.join(tmp, "home")
        os.makedirs(home)
        state = os.path.join(tmp, "state")
        env = {**os.environ, "AGENT_FABRIC_STATE_DIR": state, "AGENT_FABRIC_ROOT": ROOT, "HOME": home, "FAKE_DIR": fake,
               "PATH": os.path.join(fake, "bin") + os.pathsep + os.environ.get("PATH", ""), "AGENT_FABRIC_CTL": os.path.join(fake, "bin", "fabric-ctl"),
               "AGENT_FABRIC_SECRET_STORE": store, "CLAUDE_CODE_SESSION_ID": "sess-A", "CLAUDE_BRIDGE_URL": "http://127.0.0.1:9",
               "CLAUDE_BRIDGE_AUTH_TOKEN": "tok", "AGENT_FABRIC_HOSTS_REGISTRY": os.path.join(tmp, "none.json")}
        env["AGENT_FABRIC_OPERATOR"] = write_operator_projects(os.path.join(tmp, "operator"), {"fixture-proj": ["git@example.org:o/fixture-proj.git"]})
        repo = os.path.join(tmp, "alpha")
        os.makedirs(repo)
        subprocess.run(["git", "init", "-q", repo], check=True, env=git_env())

        def put(name: str, doc) -> None:
            with open(os.path.join(fake, name), "w") as fh:
                json.dump(doc, fh)

        def calls(name: str) -> list[str]:
            p = os.path.join(fake, name)
            return open(p).read().splitlines() if os.path.exists(p) else []

        def run(*argv: str) -> subprocess.CompletedProcess:
            return subprocess.run([JOBS, *argv], cwd=repo, env=env, capture_output=True, text=True, timeout=120)

        def jobs(*extra: str) -> list[dict]:
            return json.loads(run("list", "--all", "--json", *extra).stdout)

        def job(i: str, *extra: str) -> dict:
            return next(j for j in jobs(*extra) if j["id"] == i)

        def cache_file() -> str:
            for d, _, fs in os.walk(state):
                if "jobs-blockers.json" in fs:
                    return os.path.join(d, "jobs-blockers.json")
            return ""

        def age(spec: str | None = None, by: int = 700) -> None:
            """Make a cached check older than the bound (the clock is the process's own)."""
            path = cache_file()
            doc = json.load(open(path))
            for k, v in doc.items():
                if (spec is None or k == spec) and "checked_at" in v:
                    v["checked_at"] -= by
            json.dump(doc, open(path, "w"))

        def episodic(line: dict) -> None:
            subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fabric", "episodic.py"), "gzcoord-in"], env=env,
                           input=json.dumps(line) + "\n", capture_output=True, text=True, timeout=60, check=True)

        put("gh.states", {"o/r#5": "OPEN", "o/r#6": "OPEN", "o/r#7": "MERGED", "o/r#8": "CLOSED"})
        put("ctl.json", {"logins": {"peer-1": [{"id": "j3", "state": "active"}, {"id": "j4", "state": "delivered"}]}})
        for t in ("held on a pull request", "held on a reply", "held on a peer's job", "held on two", "held on nothing checkable", "ready, queued"):
            run("add", t)

        print("--on forms: refused when none of the three, stored when one")
        r = run("block", "j1", "--on", "pr:not-a-pr")
        check("a form that is none of the three is refused, naming the forms, and nothing is written",
              r.returncode == 1 and "pr:<owner/repo>#<n>" in r.stderr and job("j1")["state"] == "queued", (r.stderr, job("j1")["state"]))
        r = run("start", "j1")
        r = run("block", "j1", "--on", "pr:o/r#5")
        check("a PR blocker is stored, with the job's own words made of it", r.returncode == 0 and job("j1")["state"] == "blocked"
              and job("j1")["blockers"][0]["spec"] == "pr:o/r#5" and job("j1")["blocked_on"] == "pr:o/r#5", (r.stdout, r.stderr))
        check("…and checked once, at block time, and said", "pr:o/r#5 waiting (open)" in r.stdout and len(calls("gh.calls")) == 1, (r.stdout, calls("gh.calls")))
        check("the cache is private (0600)", os.stat(cache_file()).st_mode & 0o777 == 0o600, oct(os.stat(cache_file()).st_mode))

        print("the cache bound: a blocker is checked at most once per ten minutes")
        n = len(calls("gh.calls"))
        for _ in range(3):
            run("list")
        check("three listings inside the bound make no new call", len(calls("gh.calls")) == n, calls("gh.calls"))
        age("pr:o/r#5", 100)
        run("list")
        check("100 s later still inside it", len(calls("gh.calls")) == n)
        age("pr:o/r#5", 600)
        run("list")
        check("past it, one new call", len(calls("gh.calls")) == n + 1, calls("gh.calls"))
        check("…still waiting: not cleared, not ranked, no word of it", "blocker cleared" not in run("list").stdout and job("j1")["cleared"] is False)

        print("pr: merged or closed clears; a cleared blocker is never checked again")
        put("gh.states", {"o/r#5": "MERGED", "o/r#6": "OPEN", "o/r#7": "MERGED", "o/r#8": "CLOSED"})
        age("pr:o/r#5")
        out = run("list").stdout
        check("merged: the line says so", "blocker cleared: pr:o/r#5" in out, out)
        check("…and the JSON says cleared true with the state", job("j1")["cleared"] is True and job("j1")["blockers"][0]["state"] == "cleared"
              and job("j1")["blockers"][0]["detail"] == "merged", job("j1"))
        n = len(calls("gh.calls"))
        age("pr:o/r#5", 100000)
        run("list")
        check("a cleared blocker stays cleared: not checked again however old", len(calls("gh.calls")) == n, calls("gh.calls"))
        run("start", "j1")
        run("block", "j1", "--on", "pr:o/r#8")
        check("closed (not merged) clears too", job("j1")["cleared"] is True and job("j1")["blockers"][0]["detail"] == "closed", job("j1"))
        r = run("block", "j1", "--on", "pr:o/r#99")
        check("a PR gh cannot find is unknown with gh's reason, and never clears",
              job("j1")["cleared"] is None and job("j1")["blockers"][0]["state"] == "unknown", job("j1"))
        run("start", "j1")
        check("leaving blocked drops the blockers", "blockers" not in job("j1") and "cleared" not in job("j1"), job("j1"))
        run("done", "j1")

        print("request: a REPLY with that IN-REPLY-TO in the journal clears it")
        run("start", "j2")
        r = run("block", "j2", "--on", f"request:{RID}")
        check("stored, and waiting: no journal yet", job("j2")["blockers"][0]["state"] == "waiting" and "no journal" in job("j2")["blockers"][0]["detail"], job("j2"))
        check("a request waited on is also kept as waits_on, for the state stream", job("j2", "--stored")["waits_on"] == RID)
        episodic({"content": reply("01a12b00-0000-7000-8000-000000000001", OTHER), "seq": 1})
        age()
        run("list")
        check("a reply to another message does not clear it", job("j2")["cleared"] is False and job("j2")["blockers"][0]["detail"] == "no reply yet", job("j2"))
        episodic({"content": reply("01a12b00-0000-7000-8000-000000000002", RID), "seq": 2})
        age()
        out = run("list").stdout
        check("a reply to it clears it", "blocker cleared: request:" + RID in out and job("j2")["cleared"] is True, out)
        run("start", "j2")
        run("block", "j2", "--on-request", RID)
        check("--on-request is the same blocker, with the wording it always had", job("j2")["blocked_on"] == f"request {RID}"
              and job("j2")["blockers"][0]["spec"] == f"request:{RID}" and job("j2")["cleared"] is True, job("j2"))
        run("start", "j2")
        run("done", "j2")

        print("job: delivered clears; closed clears only after it was seen open; fabric-ctl's refusal is unknown")
        run("start", "j3")
        run("block", "j3", "--on", "job:peer-1/j3")
        check("an active peer job: waiting, on the state fabric-ctl reports", job("j3")["blockers"][0]["state"] == "waiting"
              and job("j3")["blockers"][0]["detail"] == "active", job("j3"))
        check("fabric-ctl is asked for that login's jobs, in JSON", any(c.startswith("peer-1 jobs --json") for c in calls("ctl.calls")), calls("ctl.calls"))
        put("ctl.json", {"logins": {"peer-1": [{"id": "j3", "state": "delivered"}]}})
        age()
        check("delivered: cleared", job("j3")["cleared"] is True and job("j3")["blockers"][0]["detail"] == "delivered", job("j3"))
        run("start", "j3")
        put("ctl.json", {"logins": {"peer-1": [{"id": "j3", "state": "active"}]}})
        run("block", "j3", "--on", "job:peer-1/j3")
        put("ctl.json", {"logins": {"peer-1": []}})
        age()
        check("gone from the open list after being seen open: closed, cleared", job("j3")["cleared"] is True
              and "closed" in job("j3")["blockers"][0]["detail"], job("j3"))
        run("start", "j3")
        run("block", "j3", "--on", "job:peer-1/j9")
        check("never seen open and absent: unknown, never cleared (a typo reads the same)", job("j3")["cleared"] is None
              and job("j3")["blockers"][0]["state"] == "unknown", job("j3"))
        run("start", "j3")
        put("ctl.json", {"refuse": "me is not a host operator in runtime/hosts/registry.json — no agent would answer; not sent"})
        run("block", "j3", "--on", "job:peer-1/j3")
        check("fabric-ctl refusing this caller: unknown with its words, never cleared",
              job("j3")["blockers"][0]["state"] == "unknown" and "not a host operator" in job("j3")["blockers"][0]["detail"]
              and job("j3")["cleared"] is None, job("j3"))
        run("start", "j3")
        run("done", "j3")
        put("ctl.json", {"logins": {"peer-1": [{"id": "j3", "state": "active"}]}})

        print("several blockers: all must clear")
        put("gh.states", {"o/r#5": "MERGED", "o/r#6": "OPEN", "o/r#7": "MERGED", "o/r#8": "CLOSED"})
        run("start", "j4")
        run("block", "j4", "--on", "pr:o/r#7", "--on", "pr:o/r#6", "waiting on both")
        j = job("j4")
        check("one cleared and one waiting is not cleared; the words given are kept",
              j["cleared"] is False and j["blocked_on"] == "waiting on both" and [b["state"] for b in j["blockers"]] == ["cleared", "waiting"], j)
        check("…and the line shows each one's state, not a cleared word", "blocker cleared" not in run("list").stdout
              and "pr:o/r#6 waiting" in run("list").stdout)
        put("gh.states", {"o/r#5": "MERGED", "o/r#6": "MERGED", "o/r#7": "MERGED", "o/r#8": "CLOSED"})
        age()
        check("both cleared: cleared", job("j4")["cleared"] is True)
        run("start", "j4")
        run("done", "j4")

        print("a free-text blocker behaves as before, and a hint says once that a checkable form exists")
        run("start", "j5")
        calls_before = (len(calls("gh.calls")), len(calls("ctl.calls")))
        r = run("block", "j5", "the owner's decision")
        check("free text: stored as it was, no blockers, no cleared, no hint", job("j5")["blocked_on"] == "the owner's decision"
              and "blockers" not in job("j5") and "cleared" not in job("j5") and "checkable" not in r.stderr, (job("j5"), r.stderr))
        check("…and no call of any kind was made for it", (len(calls("gh.calls")), len(calls("ctl.calls"))) == calls_before, calls("gh.calls"))
        for text in ("waiting for PR 123 to merge", "waiting for #45", f"waiting on message {RID}"):
            run("start", "j5")
            r = run("block", "j5", text)
            check(f"{text!r}: one hint line, the job blocked as written", r.stderr.count("can clear by itself") == 1 and job("j5")["blocked_on"] == text
                  and "blockers" not in job("j5"), (r.stderr, job("j5")))
        run("start", "j5")
        r = run("block", "j5", "waiting for PR 123", "--on", "pr:o/r#6")
        check("with a checkable blocker given, no hint", "checkable" not in r.stderr and "can clear" not in r.stderr, r.stderr)
        check("a block with nothing to wait on is refused", run("block", "j5").returncode == 1)
        run("start", "j5")
        run("done", "j5")

        print("a job whose blockers cleared is ranked first, in `list` and in `next`")
        run("start", "j6")
        run("block", "j6", "--on", "pr:o/r#7")
        listing = run("list").stdout.splitlines()
        check("`list` puts it first", listing[0].startswith("j6") and "blocker cleared: pr:o/r#7" in listing[0], listing)
        run("add", "a queued high job", "--priority", "high")
        r = run("next")
        check("`next` takes it ahead of a queued high job, and says why",
              r.returncode == 0 and r.stdout.splitlines()[0].startswith("j6") and "blocker cleared: pr:o/r#7" in r.stdout.splitlines()[0], r.stdout)
        check("…and it is active, its blockers dropped", job("j6")["state"] == "active" and "blockers" not in job("j6"))
        run("block", "j6", "--on", "pr:o/r#7")
        r = run("start", "j7")
        r = run("next")
        check("`next` with a job active refuses and names the job whose blocker cleared", r.returncode == 1 and "blocker cleared on j6" in r.stderr, r.stderr)
        run("done", "j7")

        print("--stored and --cached read the cache and check nothing")
        run("start", "j6")
        put("gh.states", {"o/r#5": "OPEN", "o/r#6": "OPEN", "o/r#7": "OPEN", "o/r#8": "OPEN", "o/r#10": "OPEN"})
        run("block", "j6", "--on", "pr:o/r#10")
        n = len(calls("gh.calls"))
        age()
        for flag in ("--stored", "--cached"):
            j = job("j6", flag)
            check(f"{flag}: the cache's answer, no call", len(calls("gh.calls")) == n and j["blockers"][0]["state"] == "waiting", (calls("gh.calls"), j))
        r = run("show", "j6")
        check("show reads the cache too and names the blockers", len(calls("gh.calls")) == n and "pr:o/r#10 waiting" in r.stdout, r.stdout)
        run("start", "j6")
        run("block", "j6", "--on", "pr:o/r#10")
        # A blocker never checked (the cache removed) reads unknown with no time, from --stored.
        os.unlink(cache_file())
        j = job("j6", "--stored")
        check("a blocker never checked: unknown, no time, cleared null (the board reads it as not said)",
              j["blockers"][0]["state"] == "unknown" and j["blockers"][0]["checked_at"] is None and j["cleared"] is None, j)

        print("request: only a REPLY clears it, not any message that carries the IN-REPLY-TO")
        RID2 = "01a12bb0-2791-7a73-abbc-a186091ebbb4"
        jid = re.search(r"added (j\d+)", run("add", "held on a request answered by an INFO first").stdout).group(1)
        run("start", jid)
        run("block", jid, "--on", f"request:{RID2}")
        info = (f"[GZCOORD/1] INFO\nFROM: develop-qzapp/peer\nROLE: x\nTO: develop-qzapp/me\nIN-REPLY-TO: {RID2}\n"
                f"MESSAGE-ID: 01a12b00-0000-7000-8000-000000000003\nSUBJECT: s\n\nINFO:\nstill working\n")
        episodic({"content": info, "seq": 3})
        age()
        check("an INFO that answers it is not a REPLY: still waiting", job(jid)["cleared"] is False, job(jid))
        episodic({"content": reply("01a12b00-0000-7000-8000-000000000004", RID2), "seq": 4})
        age()
        check("the REPLY clears it", job(jid)["cleared"] is True, job(jid))
        run("start", jid)
        run("done", jid)

        print("blocking again with free text replaces the whole wait, the checkable blockers included")
        jid = re.search(r"added (j\d+)", run("add", "re-blocked on free text").stdout).group(1)
        put("gh.states", {"o/r#5": "OPEN", "o/r#6": "OPEN", "o/r#7": "MERGED", "o/r#8": "CLOSED", "o/r#20": "OPEN"})
        run("start", jid)
        run("block", jid, "--on", "pr:o/r#20", "--on", f"request:{RID}")
        check("blocked on a PR and a request", sorted(b["spec"] for b in job(jid)["blockers"]) == sorted(["pr:o/r#20", f"request:{RID}"])
              and job(jid, "--stored")["waits_on"] == RID, job(jid))
        run("block", jid, "now waiting on the owner")
        j = job(jid, "--stored")
        check("the free-text block leaves no checkable blocker and no waits_on behind",
              "blockers" not in j and "cleared" not in j and "waits_on" not in j and j["blocked_on"] == "now waiting on the owner", j)
        put("gh.states", {"o/r#5": "OPEN", "o/r#6": "OPEN", "o/r#7": "MERGED", "o/r#8": "CLOSED", "o/r#20": "MERGED"})
        age()
        out = run("list").stdout
        check("…so the PR merging later does not clear a job that waits on the owner", "blocker cleared" not in out.split(jid, 1)[1].splitlines()[0], out)
        run("start", jid)
        run("done", jid)

        print("a journal SQLite cannot open is unknown, never a dead listing")
        jid = re.search(r"added (j\d+)", run("add", "held on a request, journal broken").stdout).group(1)
        RID3 = "01a12bb1-0000-7000-8000-0000000000a3"
        run("start", jid)
        run("block", jid, "--on", f"request:{RID3}")
        db = next(os.path.join(d, "episodic.db") for d, _, fs in os.walk(state) if "episodic.db" in fs)
        os.replace(db, db + ".good")
        with open(db, "wb") as fh:
            fh.write(b"this is not a database" * 40)
        age()
        r = run("list")
        check("`list` still lists, and the broken journal is unknown with its reason", r.returncode == 0 and "Traceback" not in r.stderr
              and job(jid)["blockers"][0]["state"] == "unknown" and "journal" in job(jid)["blockers"][0]["detail"], (r.returncode, r.stderr[-300:], job(jid)))
        r = run("next")
        check("`next` still runs", "Traceback" not in r.stderr, r.stderr[-300:])
        run("start", jid) if job(jid)["state"] != "active" else None
        os.replace(db + ".good", db)
        run("block", jid, "--on", f"request:{RID3}")
        run("start", jid)
        run("done", jid)

        print("a check that fails in a way nobody listed is unknown, never a dead command")
        put("gh.states", {"o/r#40": "__ARRAY__"})
        jid = re.search(r"added (j\d+)", run("add", "held on a PR gh answers oddly").stdout).group(1)
        run("start", jid)
        r = run("block", jid, "--on", "pr:o/r#40")
        check("gh answering an array: the block is made, the blocker unknown, nothing crashes",
              r.returncode == 0 and "Traceback" not in r.stderr and job(jid)["blockers"][0]["state"] == "unknown"
              and "the check failed" in job(jid)["blockers"][0]["detail"], (r.returncode, r.stderr[-300:], job(jid)))
        r = run("list")
        check("…and `list` lists it", r.returncode == 0 and jid in r.stdout)
        run("start", jid)
        run("done", jid)

        print("a cache value out of range is no value, and never fails a listing")
        jid = re.search(r"added (j\d+)", run("add", "held on a PR, cache damaged").stdout).group(1)
        put("gh.states", {"o/r#5": "OPEN", "o/r#6": "OPEN", "o/r#7": "MERGED", "o/r#8": "CLOSED", "o/r#21": "OPEN"})
        run("start", jid)
        run("block", jid, "--on", "pr:o/r#21")
        path = cache_file()
        for label, bad in (("1e300", 1e300), ("Infinity", float("inf")), ("NaN", float("nan")), ("far in the future", 1e12), ("negative", -5)):
            doc = json.load(open(path))
            doc["pr:o/r#21"]["checked_at"] = bad
            json.dump(doc, open(path, "w"))
            r = run("list", "--stored", "--json")
            got = json.loads(r.stdout) if r.returncode == 0 else []
            entry = next((j for j in got if j["id"] == jid), None)
            check(f"checked_at {label}: `list --stored` still answers, with no time", r.returncode == 0 and entry is not None
                  and entry["blockers"][0]["checked_at"] is None, (r.returncode, r.stderr[-200:]))
        n = len(calls("gh.calls"))
        run("list")
        check("…and is rechecked at the next look, since it is no value", "pr view 21 --json state --repo o/r" in calls("gh.calls")[n:], calls("gh.calls")[n:])
        run("start", jid)
        run("done", jid)

        print("two jobs on one peer job: blocking again keeps what was seen")
        put("ctl.json", {"logins": {"peer-1": [{"id": "j30", "state": "active"}]}})
        ja = re.search(r"added (j\d+)", run("add", "waits on peer j30 (A)").stdout).group(1)
        jb = re.search(r"added (j\d+)", run("add", "waits on peer j30 (B)").stdout).group(1)
        for x in (ja, jb):
            run("start", x)
            run("block", x, "--on", "job:peer-1/j30")
        put("ctl.json", {"logins": {"peer-1": []}})        # the peer finished it
        age()
        run("start", jb)
        run("block", jb, "--on", "job:peer-1/j30")          # B blocks again: a fresh check, the sighting kept
        check("B, blocked again after the peer closed j30, reads cleared, not unknown", job(jb)["cleared"] is True, job(jb))
        check("…and A, which was never rechecked, reads cleared too", job(ja)["cleared"] is True, job(ja))
        for x in (ja, jb):
            run("start", x)
            run("done", x)

        print("a reply id written in upper case clears the blocker, which is stored in lower case")
        RID4 = "01a12bb2-0000-7000-8000-0000000000a4"
        jid = re.search(r"added (j\d+)", run("add", "held on a request answered in upper case").stdout).group(1)
        run("start", jid)
        run("block", jid, "--on", f"request:{RID4.upper()}")
        check("stored lower-cased", job(jid)["blockers"][0]["spec"] == f"request:{RID4}")
        episodic({"content": reply("01a12b00-0000-7000-8000-000000000005", RID4.upper()), "seq": 5})
        age()
        check("the reply clears it", job(jid)["cleared"] is True, job(jid))
        run("start", jid)
        run("done", jid)

        print("the control agent's jobs op carries blockers and cleared only where the job has them")
        sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
        from control import jobs as control_jobs  # noqa: E402
        listed = [{"id": "j1", "state": "blocked", "title": "t", "blocked_on": "pr:o/r#7", "blockers": [{"spec": "pr:o/r#7", "state": "cleared"}], "cleared": True},
                  {"id": "j2", "state": "queued", "title": "u"}]

        class Ran:
            returncode, stderr, stdout = 0, "", json.dumps(listed)
        got = control_jobs.jobs(home=home, root=ROOT, run=lambda *a, **k: Ran())["jobs"]
        check("blockers and cleared pass through where present", got[0]["cleared"] is True and got[0]["blockers"][0]["spec"] == "pr:o/r#7", got[0])
        check("…and are absent where the job has none (an older record)", "blockers" not in got[1] and "cleared" not in got[1], got[1])

        print("the forms")
        sys.path.insert(0, ROOT)
        import importlib.util
        spec = importlib.util.spec_from_file_location("fabric_jobs_main", os.path.join(ROOT, "tools", "fabric", "jobs.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        bl = mod.blockers
        for good in ("pr:o/r#1", "pr:Blue-Team.OU/agent.fabric#123456789", f"request:{RID}", "job:python-dev-04/j12", "job:u/j1"):
            check(f"{good!r} is a checkable blocker", bl.normalise(good) == good)
        for bad in ("pr:o/r", "pr:o/r#0", "pr:o#1", "pr:o/r#1234567890", "request:123", "request:" + RID[:-1], "job:u/12", "job:/j1", "job:U/j1", "http://x", "",
                    "pr:o/r#1 extra"):
            try:
                bl.normalise(bad)
                refused = False
            except mod.Refused:
                refused = True
            check(f"{bad!r} is refused", refused)
        check("a request id is stored lower-cased", bl.normalise("request:" + RID.upper()) == "request:" + RID)

        print("the cache merge: a result never undoes what another process wrote")
        os.environ["AGENT_FABRIC_STATE_DIR"] = os.path.join(tmp, "merge-state")
        spec = "pr:o/r#31"
        real = bl.run_check

        def raced(s, entry):
            """While this process checks, another one clears the same blocker and has seen the job open."""
            bl.save_cache({**bl.load_cache(), s: {"state": "cleared", "detail": "merged", "checked_at": bl.now(), "seen_open": True}})
            return {"state": "waiting", "detail": "open", "checked_at": bl.now()}
        bl.run_check = raced
        try:
            got = bl.refresh([spec], check=True)
        finally:
            bl.run_check = real
        check("a cleared answer written meanwhile is kept over a waiting one", got[spec]["state"] == "cleared" and bl.load_cache()[spec]["state"] == "cleared", got)
        bl.forget([spec])
        check("forget keeps only what was seen", bl.load_cache().get(spec) == {"seen_open": True}, bl.load_cache())
        check("the cache and its lock are private", all(os.stat(os.path.join(os.path.dirname(bl.cache_path()), n)).st_mode & 0o777 == 0o600
                                                        for n in os.listdir(os.path.dirname(bl.cache_path())) if n.startswith("jobs-blockers")))

    print("pass" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
