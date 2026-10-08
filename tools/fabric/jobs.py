#!/usr/bin/env python3
"""tools/fabric/jobs.py — the agent's own job list (agent-fabric ADR-037),
behind bin/fabric-jobs.

    fabric-jobs add "<title>" [--topic T] [--project P] [--working-copy W] [--priority P]
    fabric-jobs add --request <MESSAGE-ID|seq> [--topic T] [--working-copy W] [--priority P]
    fabric-jobs list [--all] [--json]
    fabric-jobs prio <id> <blocking|high|normal|low>
    fabric-jobs start <id>
    fabric-jobs block <id> "<on what>"
    fabric-jobs deliver <id> <artifact>...
    fabric-jobs done <id>
    fabric-jobs drop <id> "<why>"
    fabric-jobs show <id> [--json]
    fabric-jobs next [<id>] [--json]

The list is agents/<login>/jobs.json, read and written only through
runtime/identity.py, under the agent lock. A job's project and working
copy are the ones the directory it was added in resolves to, unless given;
its topic is a label the agent sets, compared by `next` and never guessed.
At most one job is active: `start` refuses a second, because "what am I
doing" has one answer.

`add --request` is how a receiver puts a GZCoord request it takes on its
list: the title, sender and project are read from the message through the
inbox's own replay (addressed to this login, or refused, SPEC §17), and
a message already on the list is refused by name. Only the receiver runs
it (ADR-037 rule 4). The automatic intake in the GZCoord send
(tools/fabric/gzcoord/send.py) calls it with
--auto, which skips quietly what is not a REQUEST or is already listed;
that path runs only under AGENT_FABRIC_JOBS_AUTO_INTAKE=1, which nothing
sets (rule 5).

A job has a priority (ADR-037 rule 7): blocking, high, normal or low;
normal when none was set, and in a list written before priorities
existed. A stored value outside the four is not read as normal: `next`
refuses to order a queue it cannot rank, and names the job.

`next` is the restart rule (ADR-022 rule 12). It never passes an active
job, which is never preempted, and takes the job named, or the queued job
of highest priority, the oldest first (the list's order is the order jobs
were added); a blocked job keeps its place and is taken only by name. It
compares that job with the job that last left
`active`, or, when none has, with the directory it runs in:
the same project, working copy and topic continue in this session; any
difference is a fresh session, and `next` prints the one command that
starts it (`fabric-fresh --job <id>`). The agent confirms by running it.
A topic missing on either side leaves only the repository to compare,
and `next` says so rather than guessing whether the subjects differ.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from typing import Any, TypedDict

HERE = os.path.dirname(os.path.abspath(__file__))
FABRIC_ROOT = os.environ.get("AGENT_FABRIC_ROOT") or os.path.dirname(os.path.dirname(HERE))


# A job as jobs.json keeps it (runtime/control/jobs.mjs reads it too). The
# keys a state change adds live in a total=False subclass: under `from
# __future__ import annotations` TypedDict counts NotRequired[...] as
# required. tests/test_types.py holds every job the CLI writes to it.
class _JobKeys(TypedDict):
    id: str
    title: str
    topic: str | None
    project: str | None
    working_copy: str | None
    state: str
    source: dict[str, Any]
    artifacts: list[str]
    created: str
    updated: str
    log: list[dict[str, str]]


class Job(_JobKeys, total=False):
    blocked_on: str
    reason: str
    priority: str


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


identity = _load("fabric_identity", os.path.join(FABRIC_ROOT, "runtime", "identity.py"))

STATES = ("queued", "active", "blocked", "delivered", "done", "dropped")
OPEN = ("queued", "active", "blocked", "delivered")
TERMINAL = ("done", "dropped")
PRIORITIES = ("blocking", "high", "normal", "low")
DEFAULT_PRIORITY = "normal"


class Refused(Exception):
    """A change the list does not allow; the message is the whole answer."""


def find(doc: dict, job_id: str) -> Job:
    for job in doc["jobs"]:
        if job["id"] == job_id:
            return job
    raise Refused(f"no job {job_id} in this list (fabric-jobs list --all)")


def stored_priority(job: dict) -> str | None:
    """The job's priority as stored, `normal` when the key is absent; None
    for a value that is none of the four — unknown, never a default."""
    value = job.get("priority", DEFAULT_PRIORITY)
    return value if value in PRIORITIES else None


def queue_order(doc: dict) -> list[Job]:
    """The queued jobs in the order `next` takes them: highest priority,
    then the oldest."""
    queued = [(i, j) for i, j in enumerate(doc["jobs"]) if j["state"] == "queued"]
    for _, j in queued:
        if stored_priority(j) is None:
            raise Refused(f"{j['id']} has priority {j.get('priority')!r}, none of {', '.join(PRIORITIES)}: the queue "
                          f"cannot be ordered; set it with fabric-jobs prio {j['id']} <priority>")
    return [j for _, j in sorted(queued, key=lambda q: (PRIORITIES.index(stored_priority(q[1])), q[0]))]


def active(doc: dict) -> Job | None:
    return next((j for j in doc["jobs"] if j["state"] == "active"), None)


def transition(doc: dict, job: dict, state: str, **fields) -> None:
    if job["state"] in TERMINAL:
        raise Refused(f"{job['id']} is {job['state']}; a closed job is not reopened — add a new one")
    if state == "active":
        current = active(doc)
        if current and current["id"] != job["id"]:
            raise Refused(f"{current['id']} is active ({current['title']}); deliver, block, finish or drop "
                          "it first — one job is active at a time")
    if job["state"] == "active" and state != "active":
        # The job that just left `active` is what `next` compares against.
        doc["last"] = job["id"]
    now = identity.now_iso()
    job["state"] = state
    job["updated"] = now
    job.setdefault("log", []).append({"at": now, "state": state, **({"note": fields["note"]} if fields.get("note") else {})})
    for key, value in fields.items():
        if key != "note" and value is not None:
            job[key] = value


def own_project(ctx: dict) -> str | None:
    """The project a checkout IS, from its remote or marker — never the
    binding's, which resolve_context falls back to for an unregistered
    directory: that fallback made every unregistered checkout "be" the
    bound project, and a job for it land in the wrong tree."""
    return ctx.get("project") if ctx.get("project_source") == "working-copy" else None


def working_copy_of(project: str) -> str | None:
    """This login's working copy of `project`: the directory it runs in
    when that is one, else the first checkout that resolves to it beside
    the current working copy, then beside the fabric — the workspace
    either way in a normal layout, and the first still right when the
    fabric in use is a worktree elsewhere. A job added from another
    project, or by the owner through the control agent, lands where the
    work is done; None when no checkout is found."""
    here = identity.resolve_context()
    if own_project(here) == project and here.get("working_copy"):
        return here["working_copy"]
    workspaces = [os.path.dirname(here["working_copy"])] if here.get("working_copy") else []
    workspaces.append(os.path.dirname(os.path.realpath(FABRIC_ROOT)))
    for workspace in dict.fromkeys(workspaces):
        try:
            names = sorted(os.listdir(workspace))
        except OSError:
            continue
        for name in names:
            path = os.path.join(workspace, name)
            if os.path.isdir(os.path.join(path, ".git")) and own_project(identity.resolve_context(cwd=path)) == project:
                return path
    return None


def new_job(doc: dict, title: str, *, topic=None, project=None, working_copy=None, source=None,
            priority=DEFAULT_PRIORITY) -> Job:
    # Control characters (C0, DEL, C1) would reach every terminal that
    # lists the job and the opening prompt of a fresh session. Tab, newline
    # and carriage return are whitespace, collapsed below as they always were
    # (a title from a file, a subject with a tab).
    if any((ord(c) < 32 and c not in "\t\n\r") or 127 <= ord(c) < 160 for c in title + (topic or "")):
        raise Refused("a title or topic carries a control character")
    title = " ".join(title.split())
    if not title:
        raise Refused("a job needs a title")
    if working_copy:
        # Stored as its checkout's toplevel, as a job added from inside it
        # is: a subdirectory or a symlinked path would compare as another
        # working copy in `next` and the session-start warning.
        given = os.path.realpath(os.path.expanduser(working_copy))
        working_copy = identity.resolve_context(cwd=given).get("working_copy") or given
    elif project:
        working_copy = working_copy_of(project)
    ctx = identity.resolve_context(cwd=working_copy or os.getcwd())
    doc["seq"] = int(doc.get("seq", 0)) + 1
    now = identity.now_iso()
    job = {
        "id": f"j{doc['seq']}",
        "title": title,
        "topic": " ".join(topic.split()) if topic else None,
        "project": project or own_project(ctx),
        # Never the current directory's checkout for another project's job.
        "working_copy": working_copy or (ctx.get("working_copy") if not project or own_project(ctx) == project else None),
        "state": "queued",
        "priority": priority,
        "source": source or {"kind": "self"},
        "artifacts": [],
        "created": now,
        "updated": now,
        "log": [{"at": now, "state": "queued"}],
    }
    doc["jobs"].append(job)
    return job


INBOX = os.path.join(FABRIC_ROOT, "bin", "gzcoord-inbox")


def fetch_message(which: str) -> dict:
    """The message, read the way `gzcoord-inbox --replay` reads it: the
    relay's recent history, the body only when addressed to this login."""
    try:
        p = subprocess.run([INBOX, "--replay", which, "--json"], capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        raise Refused(f"cannot read message {which}: the relay did not answer within 15 s")
    # Exit 2 is also inbox's refusal of a control channel: only its own
    # {"addressed": false} answer means "not for this login".
    if p.returncode == 2:
        try:
            said = json.loads(p.stdout)
        except ValueError:
            said = None
        if isinstance(said, dict) and said.get("addressed") is False:
            raise Refused(f"message {which} is not addressed to this login; only its receiver adds it")
    if p.returncode != 0 or not p.stdout.strip():
        why = (p.stderr.strip().splitlines() or ["no answer from the inbox"])[-1]
        raise Refused(f"cannot read message {which}: {why}")
    return json.loads(p.stdout)


def request_job(doc: dict, msg: dict, *, topic=None, project=None, working_copy=None, auto=False,
                priority=DEFAULT_PRIORITY) -> Job | None:
    meta = msg.get("metadata") or {}
    mid = meta.get("MESSAGE-ID") or str(msg.get("seq"))
    if auto and msg.get("type") != "REQUEST":
        return None
    listed = next((j for j in doc["jobs"] if (j.get("source") or {}).get("message_id") == mid), None)
    if listed:
        if auto:
            return None
        raise Refused(f"message {mid} is already {listed['id']} ({listed['state']})")
    wanted = project or meta.get("PROJECT")
    here = identity.resolve_context(cwd=os.path.abspath(os.path.expanduser(working_copy)) if working_copy else None)
    if wanted and not working_copy and own_project(here) != wanted:
        working_copy = working_copy_of(wanted)
        if not working_copy:
            raise Refused(f"the message is for project {wanted}, and no working copy of it is here or beside "
                          "this one; run from its working copy or pass --working-copy")
    source = {"kind": "request" if msg.get("type") == "REQUEST" else (msg.get("type") or "message").lower(),
              "message_id": mid, "from": meta.get("FROM") or msg.get("sender"), "seq": msg.get("seq")}
    return new_job(doc, meta.get("SUBJECT") or f"message {mid}", topic=topic, project=wanted,
                   working_copy=working_copy, source=source, priority=priority)


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


def line(job: dict) -> str:
    where = job.get("project") or os.path.basename(job.get("working_copy") or "") or "(no project)"
    topic = f" [{job['topic']}]" if job.get("topic") else ""
    extra = ""
    if job["state"] == "blocked" and job.get("blocked_on"):
        extra = f" — on {job['blocked_on']}"
    elif job.get("artifacts"):
        extra = f" — {', '.join(job['artifacts'])}"
    return f"{job['id']:<5} {job['state']:<9} {stored_priority(job) or '?':<8} {where}{topic}: {job['title']}{extra}"


def show(job: dict) -> str:
    src = job.get("source") or {}
    origin = src.get("kind", "self")
    if src.get("from"):
        origin += f" from {src['from']}"
    if src.get("message_id"):
        origin += f" (message {src['message_id']})"
    rows = [
        ("job", job["id"]), ("title", job["title"]), ("state", job["state"]),
        ("priority", stored_priority(job) or f"{job.get('priority')!r} (none of {', '.join(PRIORITIES)})"),
        ("project", job.get("project") or "-"), ("working copy", job.get("working_copy") or "-"),
        ("topic", job.get("topic") or "-"), ("source", origin),
        ("blocked on", job.get("blocked_on")), ("artifacts", ", ".join(job.get("artifacts") or []) or None),
        ("reason", job.get("reason")), ("created", job.get("created")), ("updated", job.get("updated")),
    ]
    return "\n".join(f"{k + ':':<14}{v}" for k, v in rows if v)


def summary(job: dict) -> str:
    """One line for a fresh session's opening prompt: what the job is, where
    it came from, what it has delivered — the rest is `show`."""
    src = job.get("source") or {}
    bits = [f"project {job['project']}" if job.get("project") else "",
            f"topic {job['topic']}" if job.get("topic") else "",
            " ".join(x for x in (f"from a {src.get('kind')}", src.get("message_id"), f"by {src['from']}") if x)
            if src.get("from") else "",
            f"artifacts {', '.join(job['artifacts'])}" if job.get("artifacts") else ""]
    return f"{job['id']}, {job['title'][:200]} ({'; '.join(b for b in bits if b) or 'no project'})"


def mutate(fn):
    """Run fn(doc) under the lock and return what it returns; a Refused
    leaves the file as it was."""
    out = {}

    def edit(doc):
        out["value"] = fn(doc)
        return doc
    identity.update_jobs(edit)
    return out.get("value")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fabric-jobs", description="this agent's job list (agent-fabric ADR-037)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="add a queued job")
    a.add_argument("title", nargs="?")
    a.add_argument("--request", metavar="MESSAGE-ID", help="a GZCoord message addressed to this login")
    a.add_argument("--auto", action="store_true", help=argparse.SUPPRESS)
    a.add_argument("--owner", metavar="ADDRESS", help=argparse.SUPPRESS)   # the control agent's jobs-add
    a.add_argument("--topic")
    a.add_argument("--project")
    a.add_argument("--working-copy")
    a.add_argument("--priority", choices=PRIORITIES, default=DEFAULT_PRIORITY)
    ls = sub.add_parser("list", help="open jobs (--all: closed ones too)")
    ls.add_argument("--all", action="store_true")
    ls.add_argument("--json", action="store_true")
    pr = sub.add_parser("prio", help="set a job's priority")
    pr.add_argument("id")
    pr.add_argument("priority", choices=PRIORITIES)
    for name in ("start", "done"):
        sub.add_parser(name).add_argument("id")
    b = sub.add_parser("block")
    b.add_argument("id")
    b.add_argument("on")
    d = sub.add_parser("deliver")
    d.add_argument("id")
    d.add_argument("artifacts", nargs="+")
    dr = sub.add_parser("drop")
    dr.add_argument("id")
    dr.add_argument("why")
    s = sub.add_parser("show")
    s.add_argument("id")
    s.add_argument("--json", action="store_true")
    s.add_argument("--line", action="store_true", help="one line, for an opening prompt")
    s.add_argument("--field", help="one field's value, for the launcher")
    n = sub.add_parser("next", help="start the next job and say whether it needs a fresh session")
    n.add_argument("id", nargs="?")
    n.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "add" and args.request:
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
        elif args.cmd == "add":
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
        elif args.cmd == "list":
            doc = identity.read_jobs()
            jobs = [j for j in doc["jobs"] if args.all or j["state"] in OPEN]
            if args.json:
                print(json.dumps(jobs, ensure_ascii=False, indent=2))
            elif not jobs:
                print("no open jobs" if not args.all else "no jobs")
            else:
                print("\n".join(line(j) for j in jobs))
        elif args.cmd == "show":
            job = find(identity.read_jobs(), args.id)
            if args.field:
                print(job.get(args.field) or "")
            else:
                print(json.dumps(job, ensure_ascii=False, indent=2) if args.json else summary(job) if args.line else show(job))
        elif args.cmd == "next":
            here = identity.resolve_context()

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
                    nxt = next(iter(queue_order(doc)), None)
                    if nxt is None:
                        raise Refused("no queued job; add one with fabric-jobs add")
                verdict = decide(doc, nxt, here)
                transition(doc, nxt, "active")
                return verdict, dict(nxt)
            verdict, job = mutate(pick)
            if args.json:
                print(json.dumps(verdict, ensure_ascii=False, indent=2))
            else:
                print(line(job))
                if verdict["fresh"]:
                    print(f"fresh session: against {verdict['against']}, {'; '.join(verdict['differs'])}.")
                    print(f"  run: fabric-fresh --job {job['id']}")
                else:
                    print(f"continue here: the same repository{'' if verdict['caveat'] else ' and topic'} "
                          f"as {verdict['against']}.")
                if verdict["caveat"]:
                    print(f"  ({verdict['caveat']})")
        else:
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
                    transition(doc, job, "blocked", blocked_on=" ".join(args.on.split()), note=args.on)
                elif args.cmd == "deliver":
                    arts = list(dict.fromkeys((job.get("artifacts") or []) + args.artifacts))
                    transition(doc, job, "delivered", artifacts=arts)
                elif args.cmd == "done":
                    transition(doc, job, "done")
                elif args.cmd == "drop":
                    transition(doc, job, "dropped", reason=" ".join(args.why.split()), note=args.why)
                return job
            print(line(mutate(change)))
    except Refused as exc:
        print(f"fabric-jobs: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
