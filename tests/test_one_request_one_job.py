#!/usr/bin/env python3
"""One REQUEST, one job (agent-fabric ADR-037 rule 11), through the real job
list in a scratch state directory: the addressee's inbox intake
(gzcoord/intake.py queue_received), the sender's jobs-add (the control
plane's jobs_add, which runs `fabric-jobs add -- <title>`) and a person's
`fabric-jobs add --request` all add the same message, in either order and at
the same moment. The check that makes it one is the add's own, under the
list's lock; a test that leaves it out must see two jobs.
Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import time

from git_env import scrub_process_env  # noqa: E402 — tests/, the script's own directory
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
scrub_process_env()
own_instance_tree()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools", "fabric")
sys.path.insert(0, TOOLS)
from control import jobs as control_jobs  # noqa: E402
from gzcoord import intake  # noqa: E402

MID = "01a15af3-e63c-7e3e-9a35-96df28f028fb"
OTHER = "01a15af3-e63c-7e3e-9a35-96df28f028fc"
ME = "host-a/dev-01"
SUBJECT = "a request for the addressee"
TITLE = intake.title_for(SUBJECT, MID)
HANG_S = 120
fails = 0


def check(label: str, good: bool, detail: object = "") -> None:
    global fails
    if good:
        print(f"ok   {label}")
    else:
        fails += 1
        print(f"FAIL {label}: {detail}")


def delivery(mid: str = MID, project: str = "agent-fabric") -> dict:
    meta = {"FROM": "host-a/user", "TO": ME, "MESSAGE-ID": mid, "SUBJECT": SUBJECT, "PROJECT": project}
    return {"rec": {"seq": 7, "sender": "host-a/user"}, "msg": {"type": "REQUEST", "metadata": meta}, "isMine": True}


def listing(state: str) -> list[dict]:
    login = os.listdir(os.path.join(state, "agents"))[0]
    with open(os.path.join(state, "agents", login, "jobs.json"), encoding="utf-8") as fh:
        return json.load(fh)["jobs"]


def env_of(state: str) -> dict:
    return {**os.environ, "AGENT_FABRIC_STATE_DIR": state, "AGENT_FABRIC_ROOT": ROOT}


def jobs_add(state: str, title: str) -> dict:
    """The sender's half: the control plane's jobs-add, as the daemon runs it."""
    saved = os.environ.get("AGENT_FABRIC_STATE_DIR")
    os.environ["AGENT_FABRIC_STATE_DIR"] = state
    try:
        return control_jobs.jobs_add({"from": "host-a/op", "to": ["host-a/dev-01"], "args": {"title": title}},
                                     home=state, root=ROOT)
    finally:
        if saved is None:
            os.environ.pop("AGENT_FABRIC_STATE_DIR", None)
        else:
            os.environ["AGENT_FABRIC_STATE_DIR"] = saved


def inbox(state: str, mid: str = MID, project: str = "agent-fabric") -> tuple[list[str], str]:
    """The receiver's half, in this process, on the real jobs.py."""
    saved = os.environ.get("AGENT_FABRIC_STATE_DIR")
    os.environ["AGENT_FABRIC_STATE_DIR"] = state
    err = io.StringIO()
    try:
        return intake.queue_received([delivery(mid, project)], {"address": ME}, err=err), err.getvalue()
    finally:
        if saved is None:
            os.environ.pop("AGENT_FABRIC_STATE_DIR", None)
        else:
            os.environ["AGENT_FABRIC_STATE_DIR"] = saved


def sequential() -> None:
    with tempfile.TemporaryDirectory() as state:
        # A project with no working copy here: the job has none, so an add that did add would warn of it.
        queued, err = inbox(state, project="no-copy-anywhere")
        check("the inbox adds the request", len(queued) == 1 and len(listing(state)) == 1, (queued, err))
        r = jobs_add(state, TITLE)
        check("the sender's jobs-add after the inbox names the job and adds nothing",
              r.get("status") == "listed" and r["job"].split()[0] == "j1" and len(listing(state)) == 1, (r, listing(state)))
        check("...and says nothing of a working copy: it advises on a job it added, not one it found",
              "warning" not in r and listing(state)[0].get("working_copy") is None, (r, listing(state)))
        queued, err = inbox(state)
        check("the inbox again adds nothing", queued == [] and len(listing(state)) == 1, (queued, err))
    with tempfile.TemporaryDirectory() as state:
        r = jobs_add(state, TITLE)
        check("the sender's jobs-add first adds the job", r.get("status") == "added" and r["job"].split()[0] == "j1", r)
        queued, err = inbox(state)
        check("the inbox after it adds nothing", queued == [] and len(listing(state)) == 1, (queued, err, listing(state)))
        r = jobs_add(state, TITLE)
        check("a resend of the sender's jobs-add names the job and adds nothing",
              r.get("status") == "listed" and r["job"].split()[0] == "j1" and len(listing(state)) == 1, (r, listing(state)))
        r = jobs_add(state, intake.title_for(SUBJECT, OTHER))
        check("another request's title is another job: the check is by id, not by subject",
              r.get("status") == "added" and len(listing(state)) == 2, (r, listing(state)))
        r = jobs_add(state, "a title that names no request, twice")
        r = jobs_add(state, "a title that names no request, twice")
        check("a title naming no request is added each time, as before", len(listing(state)) == 4, listing(state))


def person_adds_the_message() -> None:
    """`fabric-jobs add --request` takes the message from the relay, which this
    suite has none of; the rule it shares is request_job's refusal, called here on
    a list the sender's job is already on."""
    sys.path.insert(0, TOOLS)
    import jobs  # noqa: E402 — tools/fabric/jobs.py
    doc = {"jobs": [{"id": "j1", "state": "queued", "title": TITLE, "source": {"kind": "owner", "from": "host-a/op"}}]}
    msg = {"type": "REQUEST", "seq": 7, "metadata": {"MESSAGE-ID": MID, "FROM": "host-a/user", "TO": ME, "SUBJECT": SUBJECT}}
    try:
        jobs.request_job(doc, msg)
        check("`add --request` for a message the sender's job holds is refused by name", False, "it added a job")
    except jobs.Refused as e:
        check("`add --request` for a message the sender's job holds is refused by name",
              "already j1" in str(e) and len(doc["jobs"]) == 1, str(e))
    check("...and quietly under --auto, as the intake wants", jobs.request_job(doc, msg, auto=True) is None and len(doc["jobs"]) == 1)


RACER = """
import io, os, sys, time
sys.path.insert(0, {tools!r})
kind, go = sys.argv[1], sys.argv[2]
import jobs
from gzcoord import intake
delivery = {delivery!r}
while not os.path.exists(go):
    time.sleep(0.0005)
if kind == "sender":
    sys.exit(jobs.main(["add", "--owner", "host-a/op", "--", {title!r}]))
queued = intake.queue_received([delivery], {{"address": {me!r}}}, err=sys.stderr)
sys.exit(0)
"""


def concurrent() -> None:
    """Both halves released together, several of each: they meet at the list's lock."""
    for round_no in range(3):
        with tempfile.TemporaryDirectory() as state, tempfile.TemporaryDirectory() as gate:
            go = os.path.join(gate, "go")
            code = RACER.format(tools=TOOLS, delivery=delivery(), title=TITLE, me=ME)
            kinds = ["sender", "receiver"] * 6
            procs = [subprocess.Popen([sys.executable, "-c", code, kind, go], env=env_of(state), stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True) for kind in kinds]
            time.sleep(1.5)   # every child has imported and is polling for the gate
            open(go, "w").close()
            outs = []
            for p in procs:
                try:
                    out, err = p.communicate(timeout=HANG_S)
                except subprocess.TimeoutExpired:
                    p.kill()
                    out, err = p.communicate()
                    err += "\n(killed: no answer within the hang guard)"
                outs.append((p.returncode, out, err))
            got = listing(state)
            check(f"round {round_no + 1}: twelve adds of one request, sender and inbox at once, make exactly one job",
                  len(got) == 1 and all(rc == 0 for rc, _, _ in outs), (len(got), outs[:3]))


def main() -> int:
    sequential()
    person_adds_the_message()
    concurrent()
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
