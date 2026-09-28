#!/usr/bin/env python3
"""bin/fabric-jobs (tools/fabric/jobs.py): the job list, through the real
command and a scratch state directory — never the login's own list."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS = os.path.join(ROOT, "bin", "fabric-jobs")


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "AGENT_FABRIC_STATE_DIR": os.path.join(tmp, "state"), "AGENT_FABRIC_ROOT": ROOT}
        repo_a, repo_b = os.path.join(tmp, "alpha"), os.path.join(tmp, "beta")
        for r in (repo_a, repo_b):
            os.makedirs(r)
            subprocess.run(["git", "init", "-q", r], check=True)

        def run(*argv: str, cwd: str = repo_a) -> subprocess.CompletedProcess:
            return subprocess.run([JOBS, *argv], cwd=cwd, env=env, capture_output=True, text=True)

        def jobs() -> list[dict]:
            return json.loads(run("list", "--all", "--json").stdout)

        p = run("list")
        check("an empty list says so", p.returncode == 0 and "no open jobs" in p.stdout, p.stdout + p.stderr)

        p = run("add", "first  job", "--topic", "memory drain")
        check("add queues j1 in the directory's working copy",
              p.returncode == 0 and "j1" in p.stdout and jobs()[0]["working_copy"] == repo_a
              and jobs()[0]["state"] == "queued" and jobs()[0]["title"] == "first job", p.stdout + p.stderr)
        run("add", "second", "--working-copy", repo_b)
        check("--working-copy names another repository", jobs()[1]["working_copy"] == repo_b, repr(jobs()))
        check("a job the agent adds has source self", jobs()[0]["source"] == {"kind": "self"}, repr(jobs()[0]))

        check("start makes a job active", run("start", "j1").returncode == 0 and jobs()[0]["state"] == "active")
        p = run("start", "j2")
        check("a second active job is refused", p.returncode == 1 and "j1 is active" in p.stderr
              and jobs()[1]["state"] == "queued", p.stderr)

        p = run("block", "j1", "a review of the PR")
        check("block records what it waits on", p.returncode == 0 and jobs()[0]["blocked_on"] == "a review of the PR",
              p.stdout + p.stderr)
        run("start", "j2")
        p = run("deliver", "j2", "org/repo#12", "abc1234")
        check("deliver names its artifacts", jobs()[1]["state"] == "delivered"
              and jobs()[1]["artifacts"] == ["org/repo#12", "abc1234"], p.stdout + p.stderr)
        run("deliver", "j2", "abc1234", "org/repo#13")
        check("a second deliver adds, never duplicates",
              jobs()[1]["artifacts"] == ["org/repo#12", "abc1234", "org/repo#13"], repr(jobs()[1]))
        run("done", "j2")
        p = run("start", "j2")
        check("a closed job is not reopened", p.returncode == 1 and "not reopened" in p.stderr, p.stderr)
        run("drop", "j1", "superseded by another job")
        check("drop keeps its reason", jobs()[0]["state"] == "dropped"
              and jobs()[0]["reason"] == "superseded by another job")

        p = run("list")
        check("list hides closed jobs", p.stdout.strip() == "no open jobs", p.stdout)
        p = run("list", "--all")
        check("list --all shows them", "j1" in p.stdout and "j2" in p.stdout, p.stdout)
        p = run("show", "j2")
        check("show gives the job in full", "artifacts:" in p.stdout and "org/repo#13" in p.stdout, p.stdout)
        p = run("show", "j9")
        check("an unknown id is refused by name", p.returncode == 1 and "no job j9" in p.stderr, p.stderr)
        check("the log keeps every state change",
              [e["state"] for e in jobs()[1]["log"]] == ["queued", "active", "delivered", "delivered", "done"],
              repr(jobs()[1]["log"]))

        state = os.path.join(tmp, "state", "agents")
        login = os.listdir(state)[0]
        with open(os.path.join(state, login, "jobs.json"), encoding="utf-8") as fh:
            doc = json.load(fh)
        check("the file names its agent and host", doc["agent"] == login and doc.get("host"), repr(doc)[:200])
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
