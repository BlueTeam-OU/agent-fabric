#!/usr/bin/env python3
"""A request job closed with no work of this session's must not lock the session's own commit (j178; agent-fabric ADR-037 rule 3).
The job copy guard denies every commit of a session that has worked a job other than the active one, reading the session ids in the
jobs' logs (records.session_worked). A session that started and then closed a REQUEST with `done --no-artifact` (no commit) was
thereby locked out of committing its own job. The real bin/fabric-jobs and the real guard hook, scratch state; the controls are
the cases that must still be refused: a job of its own closed the same way, and a request closed with an artifact."""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
import tempfile
import hook_harness  # noqa: E402 — tests/, the script's own directory
import jobs_world  # noqa: E402 — tests/, the script's own directory
from instance_fixtures import write_operator_projects  # noqa: E402 — tests/, the script's own directory
from git_env import scrub_process_env  # noqa: E402 — tests/, the script's own directory
scrub_process_env()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS = os.path.join(ROOT, "bin", "fabric-jobs")
SESSION = "sess-A"


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {str(detail)[:600]}"))
        fails += not good

    with tempfile.TemporaryDirectory(prefix="jobs-unworked-") as tmp:
        home = os.path.join(tmp, "home")
        os.makedirs(home)
        registry = os.path.join(tmp, "registry.json")
        with open(registry, "w", encoding="utf-8") as fh:
            fh.write("{}")
        env = {**os.environ, "AGENT_FABRIC_ROOT": ROOT, "HOME": home, "AGENT_FABRIC_STATE_DIR": os.path.join(tmp, "state"),
               "CLAUDE_CODE_SESSION_ID": SESSION, "CLAUDE_BRIDGE_URL": "http://127.0.0.1:9", "CLAUDE_BRIDGE_AUTH_TOKEN": "tok",
               "AGENT_FABRIC_HOSTS_REGISTRY": registry}
        env["AGENT_FABRIC_OPERATOR"] = write_operator_projects(os.path.join(tmp, "operator"), {"fixture-proj": ["git@example.org:o/fixture-proj.git"]})
        repo = jobs_world.seeded(os.path.join(tmp, "alpha"), os.path.join(tmp, "origins"))
        env.update(jobs_world.identity_env(), GH_REPO=jobs_world.GH_REPO)
        guard = hook_harness.entry("JOB_COPY_GUARD_HOOK", "job-copy-guard.sh")

        def run(*argv: str, cwd: str = repo) -> subprocess.CompletedProcess:
            return subprocess.run([JOBS, *argv], cwd=cwd, env=env, capture_output=True, text=True, timeout=120)

        def job(i: str) -> dict:
            return next(j for j in json.loads(run("list", "--all", "--json", "--stored").stdout) if j["id"] == i)

        def add(title: str, *, request: bool = False) -> str:
            r = run("add", title)
            jid = r.stdout.split("added ")[1].split()[0]
            if request:
                # The shape the inbox's intake gives it; the verbs read `source.kind`, not how the job got it.
                (path,) = glob.glob(os.path.join(tmp, "state", "**", "jobs.json"), recursive=True)
                doc = json.load(open(path))
                next(j for j in doc["jobs"] if j["id"] == jid)["source"] = {"kind": "request", "message_id": "01a2029f-1bab-7404-80b5-0359d41a6240"}
                json.dump(doc, open(path, "w"))
            return jid

        def commit_decision(cwd: str) -> str:
            payload = {"tool_name": "Bash", "cwd": cwd, "tool_input": {"command": "git commit -m x"}, "hook_event_name": "PreToolUse"}
            r = hook_harness.run(guard, json.dumps(payload), hook_harness.env(
                home, AGENT_FABRIC_ROOT=ROOT, AGENT_FABRIC_STATE_DIR=env["AGENT_FABRIC_STATE_DIR"], CLAUDE_CODE_SESSION_ID=SESSION,
                AGENT_FABRIC_HOSTS_REGISTRY=registry), cwd=cwd)
            return json.loads(r.out)["hookSpecificOutput"]["permissionDecision"] if r.out else "allow"

        own = add("my own job")
        r = run("start", own)
        check("the session's own job starts", r.returncode == 0, (r.stdout, r.stderr))
        wt = job(own)["working_copy"]

        print("(a) the deadlock: a request started and closed with no artifact, then the own job's commit")
        run("block", own, "owner: setting it aside", cwd=wt)
        req = add("a request", request=True)
        r = run("start", req)
        check("the request starts", r.returncode == 0, (r.stdout, r.stderr))
        r = run("done", req, "--no-artifact", "answered by REPLY")
        check("and closes with a reason", r.returncode == 0 and job(req)["state"] == "done", (r.stdout, r.stderr))
        check("no log entry of the request names this session", not any(e.get("session") for e in job(req)["log"]), job(req)["log"])
        r = run("start", own, cwd=wt)
        check("the own job starts again", r.returncode == 0, (r.stdout, r.stderr))
        check("the guard allows its commit", commit_decision(wt) == "allow", commit_decision(wt))

        print("(b) controls: what really was worked is still refused")
        self_job = add("self job")
        run("block", own, "owner: setting aside", cwd=wt)
        run("start", self_job)
        run("done", self_job, "--no-artifact", "did it")
        run("start", own, cwd=wt)
        check("a job of its own closed with --no-artifact keeps the session's mark", any(e.get("session") for e in job(self_job)["log"]), job(self_job)["log"])
        check("  and the guard denies the commit", commit_decision(wt) == "deny", commit_decision(wt))
    print(f"\ntest_jobs_request_unworked: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
