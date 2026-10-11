"""tools/fabric/jobsparts/verbs.py — one function per verb of fabric-jobs, and the `next` verdict.
A part of tools/fabric/jobs.py, whose docstring is the contract."""
from __future__ import annotations

import json
import sys
from fabric_jobs import blockers as bl
from fabric_jobs.base import MESSAGE_ID, NothingQueued, OPEN, POOL_ID, PRIORITIES, Refused, TERMINAL, identity, mutate
from fabric_jobs.ranking import effective_priority, named, queue_order, stored_priority, waiters
from fabric_jobs.records import active, fetch_message, find, new_job, request_job, session_id, session_worked, transition
from fabric_jobs.queue import stream_waits
from fabric_jobs.pool import Unanswered, ask_pool, claimed_job, pool_job, pool_line, pool_offer, printable
from fabric_jobs.render import blockers_note, line, show, summary


def decide(doc: dict, nxt: dict, session: str | None) -> dict:
    """Whether `nxt` continues in this session or needs a fresh one: a
    session that has already worked a job always needs a fresh one, so each
    job reads the fabric anew (the owner, 2026-10-11, ADR-037 rule 3)."""
    worked = session_worked(doc, session)
    return {"job": nxt["id"], "fresh": bool(worked), "worked": worked}


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
                  f"fabric-fresh would start it in the wrong directory; re-add it with --working-copy to fix",
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
    # Checkable blockers are re-checked here (cached: at most once per 10 minutes each); --stored and --cached read
    # the cache and check nothing, which is what the control agent's `jobs` op and a hook want.
    cache = bl.refresh(bl.all_specs(doc), check=not (args.stored or args.cached))
    if args.json:
        # The effective rank is the reader's, never stored: it is only
        # as true as the stream it was read from.
        print(json.dumps([{**j, "effective_priority": effective_priority(j, waits),
                           "waited_by": waiters(j, waits),
                           "stale_waiters": {a: stale[a] for a in waiters(j, waits) if a in stale},
                           **({"blockers": bl.states_of(j, cache), "cleared": bl.cleared_flag(j, cache)} if bl.specs_of(j) else {})}
                          for j in jobs], ensure_ascii=False, indent=2))
    elif not jobs:
        print("no open jobs" if not args.all else "no jobs")
    else:
        # A job whose blockers have all cleared is ranked first: the agent moves it on itself.
        first = sorted(jobs, key=lambda j: 0 if bl.cleared_flag(j, cache) is True else 1)
        print("\n".join(line(j, waits, stale, cache) for j in first))
    return 0


def show_job(args) -> int:
    """show: one job."""
    job = find(identity.read_jobs(), args.id)
    if args.field:
        print(job.get(args.field) or "")
    else:
        cache = bl.refresh(bl.specs_of(job), check=False)     # show reads the cache: it is also the launcher's call
        print(json.dumps({**job, **({"blockers": bl.states_of(job, cache), "cleared": bl.cleared_flag(job, cache)} if bl.specs_of(job) else {})},
                         ensure_ascii=False, indent=2) if args.json else summary(job) if args.line else show(job, cache))
    return 0


def next_job(args) -> int:
    """next: start the next job and say whether it needs a fresh session."""
    # Read before the lock: the stream is a relay call, and the list's
    # lock is every writer's.
    listed = identity.read_jobs()
    waits, stale = ({}, {}) if args.id else stream_waits(listed)
    cache = {} if args.id else bl.refresh(bl.all_specs(listed), check=True)

    def cleared(doc):
        """The blocked jobs whose blockers have all cleared, the highest stored priority first, then the oldest."""
        ready = [(i, j) for i, j in enumerate(doc["jobs"]) if j["state"] == "blocked" and bl.cleared_flag(j, cache) is True]
        return [j for _, j in sorted(ready, key=lambda q: (PRIORITIES.index(stored_priority(q[1]) or "normal"), q[0]))]

    def pick(doc):
        current = active(doc)
        ready = cleared(doc)
        if current:
            note = (f"; blocker cleared on {', '.join(j['id'] for j in ready)} ({'; '.join(j['blocked_on'] for j in ready if j.get('blocked_on'))})"
                    if ready else "")
            raise Refused(f"{current['id']} is still active ({current['title']}); deliver, block, "
                          f"finish or drop it first, then ask for the next{note}")
        if args.id:
            nxt = find(doc, args.id)
            if nxt["state"] not in ("queued", "blocked"):
                raise Refused(f"{nxt['id']} is {nxt['state']}; next takes a queued or blocked job")
        elif ready:
            nxt = ready[0]       # its wait is over: it goes first, ahead of anything queued
        else:
            nxt = next(iter(queue_order(doc, waits)), None)
            if nxt is None:
                raise NothingQueued("no queued job")
        verdict = decide(doc, nxt, session_id())
        who = waiters(nxt, waits)
        was_cleared = blockers_note(nxt, cache) if nxt["state"] == "blocked" and bl.cleared_flag(nxt, cache) is True else ""
        transition(doc, nxt, "active")
        return verdict, dict(nxt), who, was_cleared
    try:
        verdict, job, who, was_cleared = mutate(pick)
    except NothingQueued:
        raise Refused(f"no queued job; {pool_offer()}")
    if args.json:
        print(json.dumps(verdict, ensure_ascii=False, indent=2))
    else:
        print(line(job) + was_cleared)
        if who and stored_priority(job) != "blocking":
            print(f"  ranked blocking: {named(who, stale)} {'waits' if len(who) == 1 else 'wait'} on its request "
                  f"(stored {stored_priority(job)})")
        if verdict["fresh"]:
            print(f"fresh session: this one has already worked {verdict['worked']}; every job starts in a fresh one.")
            print(f"  run: fabric-fresh --job {job['id']}")
        else:
            print("continue here: this session has worked no job yet, so it is already fresh.")
    return 0


def change(args) -> int:
    """prio, start, block, deliver, done, drop: one job changed under the lock."""
    said: dict = {}

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
            specs = list(dict.fromkeys([bl.normalise(s) for s in (args.on_spec or [])] + ([f"request:{mid}"] if mid else [])))
            text = " ".join(args.on.split()) if (args.on or "").strip() else None
            if text is None and not specs:
                raise Refused("block needs what the job waits on: free text, --on <blocker> or --on-request <MESSAGE-ID>")
            # The words the agent gave, else the blockers; a lone --on-request keeps its old wording.
            on = text or (f"request {mid}" if mid and len(specs) == 1 else ", ".join(specs))
            transition(doc, job, "blocked", blocked_on=on, note=on)
            # A request waited on is also kept as waits_on, which the state stream reads (rule 8).
            requests = [s.split(":", 1)[1] for s in specs if s.startswith("request:")]
            job.pop("waits_on", None)
            job.pop("blockers", None)       # a new block replaces the whole wait: free text alone leaves no checkable blocker behind
            if requests:
                job["waits_on"] = requests[0]
            if specs:
                job["blockers"] = specs
            said["specs"], said["hint"] = specs, text is not None and not specs and bl.names_a_checkable(text)
        elif args.cmd == "deliver":
            arts = list(dict.fromkeys((job.get("artifacts") or []) + args.artifacts))
            transition(doc, job, "delivered", artifacts=arts)
        elif args.cmd == "done":
            transition(doc, job, "done")
        elif args.cmd == "drop":
            transition(doc, job, "dropped", reason=" ".join(args.why.split()), note=args.why)
        return job
    job = mutate(change)
    if said.get("specs"):
        # The first look, outside the lock, from a clean cache entry: a blocker that is already over is said at once.
        bl.forget(said["specs"])
        cache = bl.refresh(said["specs"], check=True)
        print(line(job, cache=cache))
    else:
        print(line(job))
    if said.get("hint"):
        print(f"fabric-jobs: a blocker that names a pull request or a message can clear by itself: --on {bl.FORMS}", file=sys.stderr)
    return 0
