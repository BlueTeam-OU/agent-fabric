"""tools/fabric/jobsparts/ranking.py — the queue's order: stored and effective priority, who waits on a job.
A part of tools/fabric/jobs.py, whose docstring is the contract."""
from __future__ import annotations

from fabric_jobs.base import DEFAULT_PRIORITY, Job, PRIORITIES, Refused, Stale


def stored_priority(job: dict) -> str | None:
    """The job's priority as stored, `normal` when the key is absent; None
    for a value that is none of the four — unknown, never a default."""
    value = job.get("priority", DEFAULT_PRIORITY)
    return value if value in PRIORITIES else None


def queue_order(doc: dict, waits: dict[str, list[str]] | None = None) -> list[Job]:
    """The queued jobs in the order `next` takes them: highest effective
    priority, then the oldest."""
    queued = [(i, j) for i, j in enumerate(doc["jobs"]) if j["state"] == "queued"]
    for _, j in queued:
        if stored_priority(j) is None:
            raise Refused(f"{j['id']} has priority {j.get('priority')!r}, none of {', '.join(PRIORITIES)}: the queue "
                          f"cannot be ordered; set it with fabric-jobs prio {j['id']} <priority>")
    return [j for _, j in sorted(queued, key=lambda q: (PRIORITIES.index(effective_priority(q[1], waits)), q[0]))]


def message_of(job: dict) -> str | None:
    return (job.get("source") or {}).get("message_id")


def named(who: list[str], stale: Stale | None) -> str:
    """The waiters, each stale one with its record's age."""
    def one(a: str) -> str:
        if a not in (stale or {}):
            return a
        age = (stale or {})[a]
        return f"{a} (state record {'of unknown age' if age is None else f'{age // 60} min old'}: stale)"
    return ", ".join(one(a) for a in who)


def waiters(job: dict, waits: dict[str, list[str]] | None) -> list[str]:
    """Who waits on this queued job's request; only a queued job ranks by it."""
    return list((waits or {}).get(message_of(job) or "", [])) if job["state"] == "queued" else []


def effective_priority(job: dict, waits: dict[str, list[str]] | None) -> str | None:
    return "blocking" if waiters(job, waits) else stored_priority(job)
