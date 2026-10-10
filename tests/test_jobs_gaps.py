#!/usr/bin/env python3
"""What tests/test_jobs.py (the oracle for fabric-jobs) did not pin, found by planting one change per
behaviour on tools/fabric/jobs.py and again on the split (ADR-040 Wave 9): five survived both. A closed
job's reason is its text with the white space collapsed, and its log keeps the text as given; the claimed
job a pool holder answers with is held to a title and a registry project id before the list is touched;
a queue.mjs that does not answer in time is said with its bound. Plain script: prints ok/FAIL, exit 1 on
any failure."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from instance_fixtures import own_instance_tree  # noqa: E402

own_instance_tree()
ROOT = os.path.dirname(HERE)
JOBS = os.path.join(ROOT, "bin", "fabric-jobs")


def load_jobs():
    spec = importlib.util.spec_from_file_location("jobs_gaps", os.path.join(ROOT, "tools", "fabric", "jobs.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    print("a closed job's reason and its log")
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        repo = os.path.join(tmp, "repo")
        os.makedirs(home)
        os.makedirs(repo)
        env = {**os.environ, "AGENT_FABRIC_STATE_DIR": os.path.join(tmp, "state"), "AGENT_FABRIC_ROOT": ROOT, "HOME": home}

        def run(*argv: str) -> subprocess.CompletedProcess:
            return subprocess.run([JOBS, *argv], cwd=repo, env=env, capture_output=True, text=True, timeout=120)

        def listed() -> list[dict]:
            return json.loads(run("list", "--all", "--stored", "--json").stdout)

        run("add", "first")
        run("add", "second")
        p = run("drop", "j1", "  gone   for\tgood ")
        j1 = next(j for j in listed() if j["id"] == "j1")
        check("drop: the reason is the text with its white space collapsed", p.returncode == 0 and j1.get("reason") == "gone for good", (p.stderr, j1))
        check("...and the log keeps the note as given, on the entry for the state it moved to",
              j1["log"][-1]["state"] == "dropped" and j1["log"][-1].get("note") == "  gone   for\tgood ", j1["log"])
        run("start", "j2")
        p = run("block", "j2", "a  review   of the PR")
        j2 = next(j for j in listed() if j["id"] == "j2")
        check("block: blocked_on and the log note are the collapsed text", p.returncode == 0 and j2["blocked_on"] == "a review of the PR"
              and j2["log"][-1].get("note") == "a review of the PR", j2)
        check("a transition with no note writes no note key", "note" not in j2["log"][0], j2["log"])

    print("the claimed job a pool holder answers with")
    jobs = load_jobs()

    def refused(answer: dict) -> str:
        try:
            jobs.claimed_job(answer, "p1")
        except jobs.Refused as e:
            return str(e)
        return ""
    good = {"job": {"id": "p1", "title": "a title", "priority": "normal", "topic": "t", "project": "agent-fabric"}}
    check("positive control: a well-formed answer is accepted and returned", refused(good) == "" and jobs.claimed_job(good, "p1") == good["job"])
    check("a title that is blank is refused, naming it", "carries no title" in refused({"job": {**good["job"], "title": "  "}}))
    check("a title that is missing is refused", "carries no title" in refused({"job": {k: v for k, v in good["job"].items() if k != "title"}}))
    check("a title that is not text is refused", "carries no title" in refused({"job": {**good["job"], "title": 7}}))
    check("a project that is not a registry id is refused, naming it",
          "project is not a registry id" in refused({"job": {**good["job"], "project": "Not A Slug"}}))
    check("a project that is not text is refused", "project is not a registry id" in refused({"job": {**good["job"], "project": 3}}))
    check("a null project is allowed (the job names none)", refused({"job": {**good["job"], "project": None}}) == "")

    print("queue.mjs that does not answer in time")
    real_run = subprocess.run

    def times_out(*a, **kw):
        raise subprocess.TimeoutExpired(a[0], kw.get("timeout", 0))
    subprocess.run = times_out
    try:
        try:
            jobs.ask_queue("waits")
            message, sent = "", "no exception"
        except jobs.Unreachable as e:
            message, sent = str(e), e.sent
    finally:
        subprocess.run = real_run
    check("a timeout is said with the bound, and nobody knows whether anything was sent",
          message == f"no answer within {jobs.QUEUE_TIMEOUT_S} s" and sent is None, (message, sent))

    print(f"\ntest_jobs_gaps: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
