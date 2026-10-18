"""tools/fabric/jobsparts/render.py — a job as a line, as a summary and as the show text.
A part of tools/fabric/jobs.py, whose docstring is the contract."""
from __future__ import annotations

import os
from fabric_jobs import blockers as bl
from fabric_jobs.base import PRIORITIES, Stale
from fabric_jobs.ranking import named, stored_priority, waiters


def blockers_note(job: dict, cache: dict | None) -> str:
    """What the checkable blockers of a blocked job say, from the cache: "blocker cleared: <what>" when all have
    cleared, else each with its state. Nothing for a job with none, or when no cache was read."""
    if cache is None or not bl.specs_of(job):
        return ""
    states = bl.states_of(job, cache)
    if all(s["state"] == "cleared" for s in states):
        return f" — blocker cleared: {', '.join(s['spec'] for s in states)}"
    return " — " + ", ".join(f"{s['spec']} {s['state']}" + (f" ({s['detail']})" if s["state"] != "unknown" and s.get("detail") else "")
                             for s in states)


def line(job: dict, waits: dict[str, list[str]] | None = None, stale: Stale | None = None, cache: dict | None = None) -> str:
    where = job.get("project") or os.path.basename(job.get("working_copy") or "") or "(no project)"
    topic = f" [{job['topic']}]" if job.get("topic") else ""
    extra = ""
    if job["state"] == "blocked" and job.get("blocked_on"):
        extra = f" — on {job['blocked_on']}" + blockers_note(job, cache)
    elif job.get("artifacts"):
        extra = f" — {', '.join(job['artifacts'])}"
    elif job.get("no_artifact"):
        extra = f" — no artifact: {job['no_artifact']}"
    who = waiters(job, waits)
    if who and stored_priority(job) != "blocking":
        extra += f" — ranks blocking: {named(who, stale)} {'waits' if len(who) == 1 else 'wait'} on it"
    return f"{job['id']:<5} {job['state']:<9} {stored_priority(job) or '?':<8} {where}{topic}: {job['title']}{extra}"


def show(job: dict, cache: dict | None = None) -> str:
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
        ("blocked on", job.get("blocked_on")),
        ("blockers", "; ".join(f"{b['spec']} {b['state']}" + (f" ({b['detail']})" if b["state"] != "unknown" and b.get("detail") else "")
                               + (f", checked {b['checked_at']}" if b.get("checked_at") else ", not checked")
                               for b in bl.states_of(job, cache)) if cache is not None and bl.specs_of(job) else None),
        ("branch", job.get("branch")), ("worktree", job.get("worktree")),
        ("artifacts", ", ".join(job.get("artifacts") or []) or None),
        ("no artifact", job.get("no_artifact")), ("reason", job.get("reason")), ("created", job.get("created")), ("updated", job.get("updated")),
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
            f"artifacts {', '.join(job['artifacts'])}" if job.get("artifacts") else "",
            f"work on branch {job['branch']}" + (f" in {job['worktree']}" if job.get("worktree") else "") if job.get("branch") else ""]
    return f"{job['id']}, {job['title'][:200]} ({'; '.join(b for b in bits if b) or 'no project'})"
