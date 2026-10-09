"""tools/fabric/jobsparts/render.py — a job as a line, as a summary and as the show text.
A part of tools/fabric/jobs.py, whose docstring is the contract."""
from __future__ import annotations

import os
from fabric_jobs.base import PRIORITIES, Stale
from fabric_jobs.ranking import named, stored_priority, waiters


def line(job: dict, waits: dict[str, list[str]] | None = None, stale: Stale | None = None) -> str:
    where = job.get("project") or os.path.basename(job.get("working_copy") or "") or "(no project)"
    topic = f" [{job['topic']}]" if job.get("topic") else ""
    extra = ""
    if job["state"] == "blocked" and job.get("blocked_on"):
        extra = f" — on {job['blocked_on']}"
    elif job.get("artifacts"):
        extra = f" — {', '.join(job['artifacts'])}"
    who = waiters(job, waits)
    if who and stored_priority(job) != "blocking":
        extra += f" — ranks blocking: {named(who, stale)} {'waits' if len(who) == 1 else 'wait'} on it"
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
