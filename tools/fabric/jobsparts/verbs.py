"""tools/fabric/jobsparts/verbs.py — one function per verb of fabric-jobs, and the `next` verdict.
A part of tools/fabric/jobs.py, whose docstring is the contract."""
from __future__ import annotations

import calendar
import json
import os
import sys
import time
from fabric_jobs import vcs
from fabric_jobs.settle import settle
from fabric_jobs.leave_sweep import after_leaving
from fabric_jobs.leave_targets import clean_targets
from fabric_jobs.branching import choose
from fabric_jobs import blockers as bl
from fabric_jobs.base import MESSAGE_ID, Job, NothingQueued, OPEN, POOL_ID, PRIORITIES, Refused, TERMINAL, identity, mutate
from fabric_jobs.ranking import effective_priority, named, queue_order, stored_priority, waiters
from fabric_jobs.records import active, fetch_message, find, listed_request, new_job, request_id_of, request_job, session_id, session_worked, transition
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

        def add_titled(doc: dict) -> tuple[Job, bool]:
            # A title that names a REQUEST already on the list adds nothing: the
            # sender's jobs-add reaches here at the same moment the addressee's
            # inbox queues the same message, and only this check, under the lock,
            # can see both.
            if (mid := request_id_of(args.title)) and (listed := listed_request(doc, mid)):
                return listed, False
            return new_job(doc, args.title, topic=args.topic, project=args.project,
                           working_copy=args.working_copy, source=source, priority=args.priority), True

        job, added = mutate(add_titled)
        print(f"{'added' if added else 'already listed'} {line(job)}")
        if not added:
            return 0
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


def last_worked(doc: dict, session: str | None) -> dict | None:
    """The job this session worked most recently: the one whose latest log entry written in `session` is newest. With no
    session id (an unlaunched shell) the job that last left `active`, as session_worked reads it."""
    if session is None:
        return next((j for j in doc["jobs"] if doc.get("last") == j["id"]), None)
    # Stamps have one-second resolution: of jobs touched in the same second, the one that last left `active` (doc["last"]) is
    # the one just worked, else the later in the list.
    stamped = [(max(e.get("at", "") for e in j.get("log", []) if e.get("session") == session), j)
               for j in reversed(doc["jobs"]) if any(e.get("session") == session for e in j.get("log", []))]
    return max(stamped, key=lambda p: (p[0], p[1]["id"] == doc.get("last")))[1] if stamped else None


def discard(choice) -> None:
    """Take back a branch and worktree `choose` made for a switch that then refused: they are empty, and the job does not record them."""
    if choice.kind != "new" or not choice.worktree or not choice.branch:
        return
    try:
        top = vcs.text(choice.worktree, "rev-parse", "--git-common-dir")
        main = os.path.dirname(os.path.realpath(os.path.join(choice.worktree, top))) if top else None
        if main:
            vcs.run(main, "worktree", "remove", "--force", choice.worktree, check=False)
            vcs.run(main, "branch", "-D", choice.branch, check=False)
    except vcs.VcsError:
        pass


def session_start(doc: dict, session: str | None) -> float | None:
    """When this session first touched the list: its earliest log entry; None without a session id or an entry."""
    if not session:
        return None
    stamps = [e["at"] for j in doc["jobs"] for e in j.get("log", []) if e.get("session") == session and isinstance(e.get("at"), str)]
    try:
        return calendar.timegm(time.strptime(min(stamps), "%Y-%m-%dT%H:%M:%SZ")) if stamps else None
    except ValueError:
        return None


def switch_job(args) -> int:
    """switch (and its alias next): settle the job being left with its evidence, start the next, choose its branch."""
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
                          f"finish, pause or drop it first, then switch{note}")
        if args.id:
            nxt = find(doc, args.id)
            if nxt["state"] not in ("queued", "blocked", "paused"):
                raise Refused(f"{nxt['id']} is {nxt['state']}; switch takes a queued, paused or blocked job")
        elif ready:
            nxt = ready[0]       # its wait is over: it goes first, ahead of anything queued
        else:
            nxt = next(iter(queue_order(doc, waits)), None)
            if nxt is None:
                raise NothingQueued("no queued job")
        return nxt

    try:
        nxt = pick(listed)
    except NothingQueued:
        raise Refused(f"no queued job; {pool_offer()}")
    session = session_id()
    old = last_worked(listed, session)
    settled = None
    swept: list[str] = []
    # The job just left is the one taken again (a blocker that cleared at once, a job paused and resumed): nothing was left.
    if old and old["id"] != nxt["id"]:
        try:
            here = vcs.toplevel(os.getcwd())
        except vcs.VcsError as e:
            raise Refused(f"could not tell which checkout this is ({e})") from None
        places = list(dict.fromkeys(p for p in (old.get("working_copy"), old.get("worktree"), here) if p))
        evidence, problems = settle(old, places, session_start(listed, session))
        if problems:
            raise Refused(f"cannot leave {old['id']} ({old['state']}) yet; fix:\n" + "\n".join(f"  - {p}" for p in problems))
        settled = f"{old['state']}: " + "; ".join(evidence)
        # Before the next job's worktree is made: the sweep would take a fresh one for finished (clean, on the remote). Said, never
        # a reason to stay: what it cannot do it reports.
        swept = after_leaving(old.get("working_copy"), here)
    choice = choose(nxt, kind=args.type, needs_merged=args.needs_merged)
    verdict_for = {}

    def commit(doc):
        again = pick(doc)
        if again["id"] != nxt["id"]:
            raise Refused(f"the list changed while the branch was prepared ({again['id']} is now first, not {nxt['id']}): run switch again")
        job = find(doc, nxt["id"])
        verdict = decide(doc, job, session)
        who = waiters(job, waits)
        was_cleared = blockers_note(job, cache) if job["state"] == "blocked" and bl.cleared_flag(job, cache) is True else ""
        resumed = job.get("reason") if job["state"] == "paused" else None
        where = f"branch {choice.branch}" if choice.branch else f"no branch ({choice.note})"
        mark = f"switch from {old['id']} ({settled}); {where}" if settled else f"switch; {where}"
        if choice.kind == "blocked":
            on = f"pr:{choice.repo}#{choice.pr}"
            was_blocked = job["state"] == "blocked"
            before = (job.get("blocked_on"), list(job.get("blockers") or []))
            if was_blocked and not before[1]:
                # Its only gate is words (an owner's decision): a checkable blocker added beside it would clear on its own and
                # let the job be taken while the decision is still awaited.
                raise Refused(f"{job['id']} is blocked on {before[0]!r}, which nothing can check: resolve that before it is blocked on a pull request")
            # A job already blocked keeps its blockers and waits_on: the pull request is added, never substituted.
            transition(doc, job, "blocked", blocked_on=(before[0] if on in before[1] else f"{before[0]}; {on}") if was_blocked and before[0] else on, note=mark)
            job["blockers"] = list(dict.fromkeys(before[1] + [on])) if was_blocked else [on]
        else:
            transition(doc, job, "active", note=mark, branch=choice.branch, worktree=choice.worktree)
        if settled:
            find(doc, old["id"]).setdefault("log", []).append(
                {"at": identity.now_iso(), "kind": "switch", "note": f"switch to {job['id']}: {settled}; {where}"})   # no `state`: fleet.log_times reads the state of an entry as a transition
        verdict_for.update(verdict=verdict, who=who, was_cleared=was_cleared, resumed=resumed, job=dict(job))
    try:
        mutate(commit)
    except Refused:
        discard(choice)
        raise
    verdict, job = verdict_for["verdict"], verdict_for["job"]
    # Only now: the job has really been left (a refusal above leaves it, and its targets, as they were). The sweep above has had its
    # turn first; a worktree it removed is gone and has nothing to clear.
    if old and old["id"] != nxt["id"] and not args.keep_targets:
        others = tuple(p for j in listed["jobs"] if j["id"] != old["id"] for p in (j.get("working_copy"), j.get("worktree")))
        # The next job may be on the very branch the old one was (an open pull request, its own branch): `choose` then hands it the
        # old worktree, which the snapshot of the list above does not yet show as its own.
        others += (choice.worktree,)
        swept = clean_targets(old.get("worktree"), old.get("working_copy"), others) + swept
    if args.json:
        for said in swept:
            print(said, file=sys.stderr)      # stdout is the one JSON object
        print(json.dumps({**verdict, "branch": choice.branch, "worktree": choice.worktree, "branch_kind": choice.kind, "settled": settled},
                         ensure_ascii=False, indent=2))
        return 0
    print(line(job) + verdict_for["was_cleared"])
    if choice.kind == "blocked":
        print(f"  blocked, not started: {choice.note}. It waits on pr:{choice.repo}#{choice.pr}; run fabric-jobs switch again for another job.")
        for said in swept:
            print(f"    {said}")
        return 0
    if verdict_for["resumed"]:
        print(f"  resumes paused work: {verdict_for['resumed']}")
    if settled:
        print(f"  left {old['id']}: {settled}")
        for said in swept:
            print(f"    {said}")
    print(f"  branch {choice.branch} ({choice.note}) in {choice.worktree}")
    if verdict_for["who"] and stored_priority(job) != "blocking":
        print(f"  ranked blocking: {named(verdict_for['who'], stale)} {'waits' if len(verdict_for['who']) == 1 else 'wait'} on its request "
              f"(stored {stored_priority(job)})")
    if verdict["fresh"]:
        print(f"fresh session: this one has already worked {verdict['worked']}; every job starts in a fresh one.")
        # The agent runs it, never the person: an agent once handed this line to the owner as a
        # "! command" instead of running it (the owner, 2026-10-11: "should not ask, should do").
        print(f"  run it yourself, now, once your work is committed (never hand it to the owner): fabric-fresh --job {job['id']}")
    else:
        print("continue here: this session has worked no job yet, so it is already fresh.")
    return 0


def branch_here() -> dict:
    """The branch checked out where `pause` runs, with its checkout; nothing when that is the default branch, detached, or not
    a checkout: a paused job names the branch holding its work or switch refuses it."""
    here = vcs.toplevel(os.getcwd())
    if not here:
        return {}
    try:
        name = vcs.run(here, "symbolic-ref", "-q", "--short", "HEAD", check=False).stdout.strip()
        return {} if not name or name == vcs.default_branch(here) else {"branch": name, "worktree": here}
    except vcs.VcsError:
        return {}


def change(args) -> int:
    """prio, start, pause, block, deliver, retract, done, drop: one job changed under the lock."""
    said: dict = {}
    paused_branch = branch_here() if args.cmd == "pause" else {}

    def change(doc):
        job = find(doc, args.id)
        if args.cmd == "prio":
            if job["state"] in TERMINAL:
                raise Refused(f"{job['id']} is {job['state']}; a closed job has no place in the queue")
            job["priority"] = args.priority
            job["updated"] = identity.now_iso()
        elif args.cmd == "start":
            transition(doc, job, "active")
        elif args.cmd == "pause":
            if job["state"] != "active":
                raise Refused(f"{job['id']} is {job['state']}; only the active job is paused (it is the agent's own choice to set work aside)")
            why = " ".join(args.why.split())
            if not why:
                raise Refused("pause needs a reason: fabric-jobs pause <id> \"<why>\"")
            # The branch the paused work is on, read from where this command runs: switch asks that it is pushed.
            # The branch `switch` recorded stays unless this runs in its checkout: another directory's branch is not the job's.
            keep = bool(job.get("branch")) and paused_branch.get("worktree") != job.get("worktree")
            transition(doc, job, "paused", reason=why, note=why, **({} if keep else paused_branch))
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
        elif args.cmd == "deliver" and job["state"] == "done":
            # Evidence only: the job stays closed (nothing reopens it), so a missing artifact can be added. `deliver` never removes one; a
            # wrong artifact does not hide behind a landed one (settle makes a reply: naming no sent REPLY a problem whatever else
            # landed), it is taken out with `retract`.
            job["artifacts"] = list(dict.fromkeys((job.get("artifacts") or []) + args.artifacts))
            job["updated"] = identity.now_iso()
        elif args.cmd == "deliver":
            arts = list(dict.fromkeys((job.get("artifacts") or []) + args.artifacts))
            transition(doc, job, "delivered", artifacts=arts)
        elif args.cmd == "retract":
            arts = list(job.get("artifacts") or [])
            if args.artifact not in arts:
                raise Refused(f"{job['id']} has no artifact {args.artifact!r}; its artifacts: " + (", ".join(repr(a) for a in arts) or "none"))
            job["artifacts"] = [a for a in arts if a != args.artifact]
            now = identity.now_iso()
            job["updated"] = now
            # No `state`: fleet.log_times reads the state of an entry as a transition, and settle dates the job's start by its last `active` one.
            job.setdefault("log", []).append({"at": now, "kind": "retract", "note": f"retracted artifact {args.artifact}"})
        elif args.cmd == "done":
            why = " ".join(args.no_artifact.split()) if args.no_artifact is not None else None
            if args.no_artifact is not None and not why:
                raise Refused("--no-artifact needs a reason: fabric-jobs done <id> --no-artifact \"<what was done>\"")
            if job["state"] == "done" and why:
                # Evidence only, as `deliver` on a done job: the job stays closed, the reason is added (or replaced).
                job["no_artifact"] = why
                job["updated"] = identity.now_iso()
            elif why:
                transition(doc, job, "done", no_artifact=why)
            else:
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
