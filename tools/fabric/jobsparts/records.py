"""tools/fabric/jobsparts/records.py — the list's records: finding, transitions, new jobs and a job made from a GZCoord request.
A part of tools/fabric/jobs.py, whose docstring is the contract."""
from __future__ import annotations

import json
import os
import subprocess
from fabric_jobs.base import DEFAULT_PRIORITY, FABRIC_ROOT, Job, Refused, TERMINAL, identity


def find(doc: dict, job_id: str) -> Job:
    for job in doc["jobs"]:
        if job["id"] == job_id:
            return job
    raise Refused(f"no job {job_id} in this list (fabric-jobs list --all)")


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
    if state != "blocked":
        job.pop("waits_on", None)
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
