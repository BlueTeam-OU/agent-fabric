#!/usr/bin/env python3
"""tools/fabric/jobs.py — the agent's own job list (agent-fabric ADR-037),
behind bin/fabric-jobs.

    fabric-jobs add "<title>" [--topic T] [--project P] [--working-copy W]
    fabric-jobs list [--all] [--json]
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

`next` is the restart rule (ADR-022 rule 12). It compares the next job —
the one named, or the oldest queued — with the job that last left
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
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FABRIC_ROOT = os.environ.get("AGENT_FABRIC_ROOT") or os.path.dirname(os.path.dirname(HERE))


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


identity = _load("fabric_identity", os.path.join(FABRIC_ROOT, "runtime", "identity.py"))

STATES = ("queued", "active", "blocked", "delivered", "done", "dropped")
OPEN = ("queued", "active", "blocked", "delivered")
TERMINAL = ("done", "dropped")


class Refused(Exception):
    """A change the list does not allow; the message is the whole answer."""


def find(doc: dict, job_id: str) -> dict:
    for job in doc["jobs"]:
        if job["id"] == job_id:
            return job
    raise Refused(f"no job {job_id} in this list (fabric-jobs list --all)")


def active(doc: dict) -> dict | None:
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


def new_job(doc: dict, title: str, *, topic=None, project=None, working_copy=None, source=None) -> dict:
    title = " ".join(title.split())
    if not title:
        raise Refused("a job needs a title")
    if working_copy:
        working_copy = os.path.abspath(os.path.expanduser(working_copy))
    ctx = identity.resolve_context(cwd=working_copy or os.getcwd())
    doc["seq"] = int(doc.get("seq", 0)) + 1
    now = identity.now_iso()
    job = {
        "id": f"j{doc['seq']}",
        "title": title,
        "topic": " ".join(topic.split()) if topic else None,
        "project": project or ctx.get("project"),
        "working_copy": working_copy or ctx.get("working_copy"),
        "state": "queued",
        "source": source or {"kind": "self"},
        "artifacts": [],
        "created": now,
        "updated": now,
        "log": [{"at": now, "state": "queued"}],
    }
    doc["jobs"].append(job)
    return job


def decide(doc: dict, nxt: dict, here: dict) -> dict:
    """Whether `nxt` continues in this session or needs a fresh one."""
    prev = next((j for j in doc["jobs"] if j["id"] == doc.get("last")), None)
    base = prev or {"project": here.get("project"), "working_copy": here.get("working_copy"), "topic": None}
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
    return f"{job['id']:<5} {job['state']:<9} {where}{topic}: {job['title']}{extra}"


def show(job: dict) -> str:
    src = job.get("source") or {}
    origin = src.get("kind", "self")
    if src.get("from"):
        origin += f" from {src['from']}"
    if src.get("message_id"):
        origin += f" (message {src['message_id']})"
    rows = [
        ("job", job["id"]), ("title", job["title"]), ("state", job["state"]),
        ("project", job.get("project") or "-"), ("working copy", job.get("working_copy") or "-"),
        ("topic", job.get("topic") or "-"), ("source", origin),
        ("blocked on", job.get("blocked_on")), ("artifacts", ", ".join(job.get("artifacts") or []) or None),
        ("reason", job.get("reason")), ("created", job.get("created")), ("updated", job.get("updated")),
    ]
    return "\n".join(f"{k + ':':<14}{v}" for k, v in rows if v)


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
    a.add_argument("title")
    a.add_argument("--topic")
    a.add_argument("--project")
    a.add_argument("--working-copy")
    ls = sub.add_parser("list", help="open jobs (--all: closed ones too)")
    ls.add_argument("--all", action="store_true")
    ls.add_argument("--json", action="store_true")
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
    n = sub.add_parser("next", help="start the next job and say whether it needs a fresh session")
    n.add_argument("id", nargs="?")
    n.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "add":
            job = mutate(lambda doc: new_job(doc, args.title, topic=args.topic, project=args.project,
                                             working_copy=args.working_copy))
            print(f"added {line(job)}")
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
            print(json.dumps(job, ensure_ascii=False, indent=2) if args.json else show(job))
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
                    nxt = next((j for j in doc["jobs"] if j["state"] == "queued"), None)
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
                if args.cmd == "start":
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
