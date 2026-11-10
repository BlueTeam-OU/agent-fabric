#!/usr/bin/env python3
"""`start --despite` (j127): a job re-pointed onto a peer's job that itself waits on this start can be started by its holder, who
names the peer's job and why; the waiver and the peer's state as read go to the log. Without --despite a job: blocker refuses as
before. The real bin/fabric-jobs against a scratch state directory and a fake fabric-ctl serving each login's board."""
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

import getpass
AGENT_LOGIN = getpass.getuser()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS = os.path.join(ROOT, "bin", "fabric-jobs")


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

        def log_of(i: str) -> list[dict]:
            return job(i, "--stored").get("log", [])

        def blocked_on(title: str, *specs: str) -> str:
            jid = re.search(r"added (j\d+)", run("add", title).stdout).group(1)
            run("start", jid)
            args = [a for s in specs for a in ("--on", s)]
            r = run("block", jid, *args)
            check(f"{title}: blocked", job(jid, "--stored")["state"] == "blocked", (r.stdout, r.stderr))
            return jid

        boards["peer"] = [row("j107", None, "active")]
        put_boards()

        print("(a) the deadlock: the peer's job is open and waits on this start; plain start refuses (the control)")
        jid = blocked_on("re-pointed", "job:peer/j107")
        r = run("start", jid)
        check("start refuses", r.returncode != 0 and "still blocked" in r.stderr and "job:peer/j107 waiting" in r.stderr, (r.stdout, r.stderr))
        check("…and names the way out", f"fabric-jobs start {jid} --despite job:peer/j107" in r.stderr, r.stderr)
        check("…the job stays blocked", job(jid, "--stored")["state"] == "blocked")

        print("(b) --despite with the reason starts it, and the log says what was waived")
        r = run("start", jid, "--despite", "job:peer/j107", "j107 waits on my push")
        check("started", r.returncode == 0 and job(jid, "--stored")["state"] == "active", (r.stdout, r.stderr))
        note = " ".join(str(e.get("note", "")) for e in log_of(jid))
        check("the log has the waiver, the peer's state as read and the reason",
              "job:peer/j107 waiting" in note and "j107 waits on my push" in note, log_of(jid))
        check("no despite field is stored on the job", "despite" not in job(jid, "--stored"))
        run("done", jid, "--no-artifact", "test")

        print("(c) what --despite does not waive")
        jid = blocked_on("no reason", "job:peer/j107")
        r = run("start", jid, "--despite", "job:peer/j107")
        check("no reason: refused", r.returncode != 0 and "needs the reason" in r.stderr and job(jid, "--stored")["state"] == "blocked", (r.stdout, r.stderr))
        r = run("start", jid, "--despite", "job:peer/j999", "x")
        check("a peer job not unmet is not the one waiting: refused",
              r.returncode != 0 and "must name each" in r.stderr and job(jid, "--stored")["state"] == "blocked", (r.stdout, r.stderr))
        r = run("start", jid, "why only")
        check("a reason without --despite is refused", r.returncode != 0 and job(jid, "--stored")["state"] == "blocked", (r.stdout, r.stderr))
        mixed = blocked_on("mixed", "job:peer/j107", "clock:2099-01-01T00:00:00Z")
        r = run("start", mixed, "--despite", "job:peer/j107", "x")
        check("another unmet kind of blocker is not waived", r.returncode != 0 and "another login only" in r.stderr and job(mixed, "--stored")["state"] == "blocked", (r.stdout, r.stderr))
        r = run("start", mixed)
        check("…and plain start gives no way out for it", r.returncode != 0 and "--despite" not in r.stderr, r.stderr)
        anchor = re.search(r"added (j\d+)", run("add", "an open job of this login").stdout).group(1)
        own = blocked_on("own job", f"job:{AGENT_LOGIN}/{anchor}")
        r = run("start", own, "--despite", f"job:{AGENT_LOGIN}/{anchor}", "x")
        check("a job of this login is not a peer's", r.returncode != 0 and job(own, "--stored")["state"] == "blocked", (r.stdout, r.stderr))

    print("pass" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
