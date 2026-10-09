"""tools/fabric/jobsparts/verbs.py — one function per verb of fabric-jobs, and the `next` verdict.
A part of tools/fabric/jobs.py, whose docstring is the contract."""
from __future__ import annotations

import json
import sys
from fabric_jobs.base import MESSAGE_ID, NothingQueued, OPEN, POOL_ID, Refused, TERMINAL, identity, mutate
from fabric_jobs.ranking import effective_priority, named, queue_order, stored_priority, waiters
from fabric_jobs.records import active, fetch_message, find, new_job, own_project, request_job, transition
from fabric_jobs.queue import stream_waits
from fabric_jobs.pool import Unanswered, ask_pool, claimed_job, pool_job, pool_line, pool_offer, printable
from fabric_jobs.render import line, show, summary


def decide(doc: dict, nxt: dict, here: dict) -> dict:
    """Whether `nxt` continues in this session or needs a fresh one."""
    prev = next((j for j in doc["jobs"] if j["id"] == doc.get("last")), None)
    base = prev or {"project": own_project(here), "working_copy": here.get("working_copy"), "topic": None}
    against = f"{prev['id']}" if prev else "this directory"
    differs = []
    if (base.get("working_copy") or None) != (nxt.get("working_copy") or None):
        differs.append(f"working copy {nxt.get('working_copy') or '-'}, not {base.get('working_copy') or '-'}")
    elif (base.get("project") or None) != (nxt.get("project") or None):
        differs.append(f"project {nxt.get('project') or '-'}, not {base.get('project') or '-'}")
    caveat = None
    if base.get("topic") and nxt.get("topic"):
        if base["topic"].casefold() != nxt["topic"].casefold():
            differs.append(f"topic {nxt['topic']!r}, not {base['topic']!r}")
    else:
        missing = [j for j in (prev, nxt) if j and not j.get("topic")]
        caveat = (f"no topic on {' and '.join(j['id'] for j in missing)}: compared by repository only — "
                  "if the subject differs, it is a fresh session all the same") if missing else \
                 "compared with this directory by repository only"
    return {"job": nxt["id"], "against": against, "fresh": bool(differs), "differs": differs, "caveat": caveat}


def add(args) -> int:
    """add: a queued job, or one made from a GZCoord request (--request)."""
    if args.request:
        if args.title:
            raise Refused("--request takes its title from the message; give one or the other")
        msg = fetch_message(args.request)
        job = mutate(lambda doc: request_job(doc, msg, topic=args.topic, project=args.project,
                                             working_copy=args.working_copy, auto=args.auto,
                                             priority=args.priority))
        if job:
            print(f"added {line(job)}")
        elif args.auto:
            return 0
    else:
        if not args.title:
            raise Refused("add needs a title, or --request <MESSAGE-ID>")
        source = {"kind": "owner", "from": args.owner} if args.owner else None
        job = mutate(lambda doc: new_job(doc, args.title, topic=args.topic, project=args.project,
                                         working_copy=args.working_copy, source=source,
                                         priority=args.priority))
        print(f"added {line(job)}")
        if not job.get("working_copy"):
            print(f"  no working copy of {job.get('project') or 'its project'} found beside this one: "
                  f"fabric-jobs next compares it by project only; re-add it with --working-copy to fix",
                  file=sys.stderr)
    return 0


def pool_list(args) -> int:
    """pool-list: the open jobs of a role's pool."""
    said = ask_pool("pool-list", *([args.role] if args.role else []))
    answer = said["answer"]
    if answer.get("status") != "ok":
        raise Refused(f"{said['holder']} refused: {printable(answer.get('reason') or answer.get('status'))}")
    if args.json:
        print(json.dumps(answer, ensure_ascii=False, indent=2))
    elif not answer.get("jobs"):
        print(f"the {printable(answer.get('role'))} pool is empty")
    else:
        print("\n".join(pool_line(j) for j in answer["jobs"]))
    return 0


def pool_claim(args) -> int:
    """pool-claim: claim a pool job onto this list."""
    if not POOL_ID.fullmatch(args.id):
        raise Refused(f"a pool job id is p<n> (fabric-jobs pool-list), not {args.id!r}")
    try:
        said = ask_pool("pool-claim", args.id)
    except Unanswered as e:
        # Sent and unanswered is not unsent: the holder may have
        # recorded it, and the same claim again hands it back.
        raise Refused(f"{e}; if the claim reached the holder, {args.id} may be claimed for you — "
                      f"fabric-jobs pool-claim {args.id} again lands it or says whose it is")
    answer, holder = said["answer"], said["holder"]
    if answer.get("status") != "claimed":
        raise Refused(f"{holder} refused: {printable(answer.get('reason') or answer.get('status'))}")
    claimed = claimed_job(answer, args.id)
    try:
        job, added = mutate(lambda doc: pool_job(doc, claimed, holder, again=answer.get("again") is True,
                                                 topic=args.topic, working_copy=args.working_copy))
    except Refused as e:
        raise Refused(f"{args.id} is claimed at {holder}, but this list did not take it ({e}); "
                      f"fix that and run fabric-jobs pool-claim {args.id} again — it is yours")
    print(f"{'claimed' if added else 'already listed'} {line(job)}")
    return 0


def list_jobs(args) -> int:
    """list: the open jobs (--all: closed ones too)."""
    doc = identity.read_jobs()
    jobs = [j for j in doc["jobs"] if args.all or j["state"] in OPEN]
    waits, stale = stream_waits(doc, stored=args.stored)
    if args.json:
        # The effective rank is the reader's, never stored: it is only
        # as true as the stream it was read from.
        print(json.dumps([{**j, "effective_priority": effective_priority(j, waits),
                           "waited_by": waiters(j, waits),
                           "stale_waiters": {a: stale[a] for a in waiters(j, waits) if a in stale}}
                          for j in jobs], ensure_ascii=False, indent=2))
    elif not jobs:
        print("no open jobs" if not args.all else "no jobs")
    else:
        print("\n".join(line(j, waits, stale) for j in jobs))
    return 0


def show_job(args) -> int:
    """show: one job."""
    job = find(identity.read_jobs(), args.id)
    if args.field:
        print(job.get(args.field) or "")
    else:
        print(json.dumps(job, ensure_ascii=False, indent=2) if args.json else summary(job) if args.line else show(job))
    return 0


def next_job(args) -> int:
    """next: start the next job and say whether it needs a fresh session."""
    here = identity.resolve_context()
    # Read before the lock: the stream is a relay call, and the list's
    # lock is every writer's.
    waits, stale = ({}, {}) if args.id else stream_waits(identity.read_jobs())

    def pick(doc):
        current = active(doc)
        if current:
            raise Refused(f"{current['id']} is still active ({current['title']}); deliver, block, "
                          "finish or drop it first, then ask for the next")
        if args.id:
            nxt = find(doc, args.id)
            if nxt["state"] not in ("queued", "blocked"):
                raise Refused(f"{nxt['id']} is {nxt['state']}; next takes a queued or blocked job")
        else:
            nxt = next(iter(queue_order(doc, waits)), None)
            if nxt is None:
                raise NothingQueued("no queued job")
        verdict = decide(doc, nxt, here)
        who = waiters(nxt, waits)
        transition(doc, nxt, "active")
        return verdict, dict(nxt), who
    try:
        verdict, job, who = mutate(pick)
    except NothingQueued:
        raise Refused(f"no queued job; {pool_offer()}")
    if args.json:
        print(json.dumps(verdict, ensure_ascii=False, indent=2))
    else:
        print(line(job))
        if who and stored_priority(job) != "blocking":
            print(f"  ranked blocking: {named(who, stale)} {'waits' if len(who) == 1 else 'wait'} on its request "
                  f"(stored {stored_priority(job)})")
        if verdict["fresh"]:
            print(f"fresh session: against {verdict['against']}, {'; '.join(verdict['differs'])}.")
            print(f"  run: fabric-fresh --job {job['id']}")
        else:
            print(f"continue here: the same repository{'' if verdict['caveat'] else ' and topic'} "
                  f"as {verdict['against']}.")
        if verdict["caveat"]:
            print(f"  ({verdict['caveat']})")
    return 0


def change(args) -> int:
    """prio, start, block, deliver, done, drop: one job changed under the lock."""
    def change(doc):
        job = find(doc, args.id)
        if args.cmd == "prio":
            if job["state"] in TERMINAL:
                raise Refused(f"{job['id']} is {job['state']}; a closed job has no place in the queue")
            job["priority"] = args.priority
            job["updated"] = identity.now_iso()
        elif args.cmd == "start":
            transition(doc, job, "active")
        elif args.cmd == "block":
            mid = args.on_request.strip().lower() if args.on_request is not None else None
            if mid is not None and not MESSAGE_ID.fullmatch(mid):
                raise Refused(f"--on-request takes a MESSAGE-ID (a UUID), not {args.on_request!r}")
            if not (args.on or "").strip() and mid is None:
                raise Refused("block needs what the job waits on, or --on-request <MESSAGE-ID>")
            on = " ".join(args.on.split()) if (args.on or "").strip() else f"request {mid}"
            transition(doc, job, "blocked", blocked_on=on, note=on)
            if mid is None:
                job.pop("waits_on", None)
            else:
                job["waits_on"] = mid
        elif args.cmd == "deliver":
            arts = list(dict.fromkeys((job.get("artifacts") or []) + args.artifacts))
            transition(doc, job, "delivered", artifacts=arts)
        elif args.cmd == "done":
            transition(doc, job, "done")
        elif args.cmd == "drop":
            transition(doc, job, "dropped", reason=" ".join(args.why.split()), note=args.why)
        return job
    print(line(mutate(change)))
    return 0
