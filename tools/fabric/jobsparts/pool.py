"""tools/fabric/jobsparts/pool.py — a role's pool: asking the holder, the claimed job and its lines.
A part of tools/fabric/jobs.py, whose docstring is the contract."""
from __future__ import annotations

import re
from fabric_jobs.base import Job, PRIORITIES, Refused
from fabric_jobs.records import new_job
from fabric_jobs.queue import Unreachable, ask_queue


class Unanswered(Refused):
    """A request reached the relay and its answer did not come back."""


def ask_pool(*argv: str) -> dict:
    """{holder, answer} from the pool's holder, or Refused saying why there
    is none: a pool not reached is never an empty one."""
    try:
        said = ask_queue(*argv)
    except Unreachable as e:
        # Unknown is not unsent: only a request known never to have left
        # is said without how to land a claim the holder may have taken.
        raise (Refused if e.sent is False else Unanswered)(f"the pool could not be asked: {e}")
    if not isinstance(said.get("answer"), dict) or not isinstance(said.get("holder"), str):
        raise Refused("the pool's answer is not one")
    return said


def pool_offer() -> str:
    """What `next` says when nothing is queued: the pool's first job for
    the bound role, that the pool is empty, or that it could not be read."""
    try:
        said = ask_pool("pool-list")
    except Refused as e:
        return f"{e} (fabric-jobs add, or fabric-jobs pool-list --role <role>)"
    answer = said["answer"]
    if answer.get("status") != "ok":
        return f"the pool: {said['holder']} refused ({printable(answer.get('reason') or answer.get('status'))})"
    jobs = answer.get("jobs") or []
    if not jobs:
        return f"the {printable(answer.get('role'))} pool is empty too"
    first = jobs[0]
    return (f"the {printable(answer.get('role'))} pool offers {pool_line(first)}\n"
            f"  claim it with fabric-jobs pool-claim {printable(first.get('id'))}, then fabric-jobs next")


PROJECT_SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,62}", re.ASCII)   # tools/fabric/control/jobs.py PROJECT_SLUG


def claimed_job(answer: dict, asked: str) -> dict:
    """The job a holder's claim answer carries, held to the shape pool.mjs
    sends; anything else is refused before the list is touched — a reply
    on the relay is any token holder's post, and a missing field never
    becomes a default."""
    job = answer.get("job")
    bad = None
    if not isinstance(job, dict) or job.get("id") != asked:
        bad = f"it names job {job.get('id') if isinstance(job, dict) else None!r}, not {asked}"
    elif not isinstance(job.get("title"), str) or not job["title"].strip():
        bad = "it carries no title"
    elif job.get("priority") not in PRIORITIES:
        bad = f"its priority {job.get('priority')!r} is none of {', '.join(PRIORITIES)}"
    elif job.get("topic") is not None and not isinstance(job.get("topic"), str):
        bad = "its topic is not text"
    elif job.get("project") is not None and not (isinstance(job["project"], str) and PROJECT_SLUG.fullmatch(job["project"])):
        bad = "its project is not a registry id"
    if bad:
        raise Refused(f"the holder's answer to the claim of {asked} is not a pool job: {bad}")
    return job


def pool_job(doc: dict, job: dict, holder: str, *, again: bool, topic=None, working_copy=None) -> tuple[Job, bool]:
    """The claimed job on this list: (job, added). Only a claim the holder
    says this claimant held already (`again`) can be a job listed before —
    the same holder's, by pool id, in any state; a first claim is always a
    new job, since pool ids restart with a new holder or a new pool file
    and an id alone names nothing."""
    listed = next((j for j in doc["jobs"]
                   if (j.get("source") or {}).get("kind") == "pool" and j["source"].get("from") == holder
                   and j["source"].get("pool_id") == job["id"]), None) if again else None
    if listed:
        return listed, False
    return new_job(doc, job["title"], topic=topic or job.get("topic"), project=job.get("project"),
                   working_copy=working_copy, source={"kind": "pool", "pool_id": job["id"], "from": holder},
                   priority=job["priority"]), True


def printable(value) -> str:
    """A holder's text as one line a terminal shows and never obeys:
    C0, DEL and C1 (U+009B is a CSI) as '?', whitespace collapsed."""
    return " ".join("".join("?" if ord(c) < 32 or 127 <= ord(c) < 160 else c for c in str(value)).split())


def pool_line(job: dict) -> str:
    topic = f" [{printable(job['topic'])}]" if job.get("topic") else ""
    where = f" {printable(job['project'])}" if job.get("project") else ""
    return (f"{printable(job.get('id', '?')):<5} {printable(job.get('priority', '?')):<8} "
            f"{printable(job.get('role', '?'))}{where}{topic}: {printable(job.get('title', ''))}")
