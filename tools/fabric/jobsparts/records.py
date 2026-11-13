"""tools/fabric/jobsparts/records.py — the list's records: finding, transitions, new jobs and a job made from a GZCoord request.
A part of tools/fabric/jobs.py, whose docstring is the contract."""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
from fabric_jobs.base import DEFAULT_PRIORITY, FABRIC_ROOT, Job, Refused, _load, identity, request_id_of, work  # noqa: F401 — request_id_of lives in base (blockers reads it); records re-exports it


def find(doc: dict, job_id: str) -> Job:
    for job in doc["jobs"]:
        if job["id"] == job_id:
            return job
    raise Refused(f"no job {job_id} in this list (fabric-jobs list --all)")


def active(doc: dict) -> Job | None:
    return next((j for j in doc["jobs"] if j["state"] == "active"), None)


def session_id() -> str | None:
    """The harness session this command runs in (the variable the harness
    exports to its Bash tool; identity.resolve_context reads another name)."""
    return os.environ.get("CLAUDE_CODE_SESSION_ID") or None


def session_worked(doc: dict, session: str | None) -> str | None:
    """The first job with a log entry written in `session`, or None. A
    transition whose old or new state is `active` (entering it, leaving it,
    or a start of the job already active) records its session when the
    harness exports one, so a session launched with a job already active
    (fabric-fresh --job) is found when it finishes that job; a drop or block
    of a job that was never active is no work done and records none. Without
    a session id (an unlaunched shell) nothing can be told apart, so any job
    that has left `active` counts: such a session always says "fresh", even
    when just launched, which is the safe error."""
    for job in doc["jobs"]:
        if session is None and doc.get("last") == job["id"]:
            return job["id"]
        if session and any(e.get("session") == session for e in job.get("log", [])):
            return job["id"]
    return None


def push_fenced(doc: dict) -> str | None:
    """The job this session worked, when the job copy guard (runtime/claude-code/hooks/job-copy-guard.py, ADR-037 rule 3) denies its
    pushes: a session that has worked a job other than the active one. The guard's own reading, including its answer for a session
    with no id (it worked nothing: the fence never locks an unlaunched shell out)."""
    session = session_id()
    current = next((j for j in doc["jobs"] if j.get("state") == "active"), None)
    return session_worked({**doc, "jobs": [j for j in doc["jobs"] if j is not current]}, session) if session else None


def transition(doc: dict, job: dict, to: str, who: str, proof=None, **fields) -> None:
    """Move `job` to `to` as `who` (rule 14): the owner's transition, with this login's clock and session. The row's needs are
    asked first (needs.py) and handed over as `proof`."""
    work.transition(doc, job, to, who, proof, now=identity.now_iso(), session=session_id(), **fields)


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


def named_working_copy(project: str | None, working_copy: str | None) -> str | None:
    """The working copy a job is stored with: the one given, else this login's of `project`, else None."""
    if working_copy:
        # Stored as its checkout's toplevel, as a job added from inside it
        # is: a subdirectory or a symlinked path would compare as another
        # working copy in `next` and the session-start warning.
        given = os.path.realpath(os.path.expanduser(working_copy))
        return identity.resolve_context(cwd=given).get("working_copy") or given
    return working_copy_of(project) if project else None


def new_job(doc: dict, title: str, *, topic=None, project=None, working_copy=None, source=None,
            priority=DEFAULT_PRIORITY, deliver_to=None, project_from=None, who: str = "add") -> Job:
    """A queued job on the list, made as `who`: add, intake, jobs-add, or the claimant's pool-claim (rule 14, rows R2b and R3)."""
    # Control characters (C0, DEL, C1) would reach every terminal that
    # lists the job and the opening prompt of a fresh session. Tab, newline
    # and carriage return are whitespace, collapsed below as they always were
    # (a title from a file, a subject with a tab).
    if any((ord(c) < 32 and c not in "\t\n\r") or 127 <= ord(c) < 160 for c in title + (topic or "")):
        raise Refused("a title or topic carries a control character")
    title = " ".join(title.split())
    if not title:
        raise Refused("a job needs a title")
    working_copy = named_working_copy(project, working_copy)
    ctx = identity.resolve_context(cwd=working_copy or os.getcwd())
    fields = {
        "title": title,
        "topic": " ".join(topic.split()) if topic else None,
        "project": project or own_project(ctx),
        # Never the current directory's checkout for another project's job.
        "working_copy": working_copy or (ctx.get("working_copy") if not project or own_project(ctx) == project else None),
        "priority": priority,
        "source": source or {"kind": "self"},
        "artifacts": [],
        **({"deliver_to": deliver_to} if deliver_to else {}),
        **({"project_from": project_from} if project_from else {}),
    }
    return work.create(doc, who, fields, now=identity.now_iso())


# A for/ branch as DELIVER-TO writes it. A word with an angle bracket is the protocol's placeholder
# ("<host>/<login>/for/<caller>/<what>"), which the charset excludes.
FOR_BRANCH = re.compile(r"(?<![\w./-])([A-Za-z0-9][\w.-]*/[A-Za-z0-9][\w.-]*/for/[A-Za-z0-9][\w.-]*/[A-Za-z0-9][\w./-]*)", re.ASCII)


SECTION_MARKER = re.compile(r"[A-Z][A-Z0-9-]*:\Z", re.ASCII)       # gzmsg's _MARKER: the name alone on its line


def section_of(text: str, name: str) -> str | None:
    """A message section's body from the message text (the inbox's replay carries the text, not its parse): the lines after
    `NAME:` up to the next marker; a section named twice resumes, as gzmsg.parse reads it. Metadata lines carry a space after the
    colon and are never markers."""
    body: list[str] | None = None
    current = None
    for line in text.splitlines():
        if SECTION_MARKER.match(line):
            current = line[:-1]
            if current == name and body is None:
                body = []
        elif current == name and body is not None:
            body.append(line)
    return "\n".join(body) if body is not None else None


def deliver_branch(msg: dict) -> str | None:
    """The for/ branch a REQUEST's DELIVER-TO section names for this login, or None: no section, no branch in it, or one of another
    login's, which this job would not own. The first one named wins; the section is the sender's free text, so the name is
    matched by shape and never trusted further (it is checked out only after git accepts it as a branch name)."""
    text = (msg.get("sections") or {}).get("DELIVER-TO") if isinstance(msg.get("sections"), dict) else None
    if text is None and isinstance(msg.get("text"), str):
        text = section_of(msg["text"], "DELIVER-TO")
    if not isinstance(text, str):
        return None
    mine = f"{identity.current_host()}/{identity.current_agent()}/for/"
    for name in FOR_BRANCH.findall(text):
        name = name.rstrip(".,;:/")
        if name.startswith(mine) and ".." not in name and not name.endswith(".lock"):
            return name
    return None


INBOX = os.path.join(FABRIC_ROOT, "bin", "gzcoord-inbox")

# How long the inbox's replay may take. It is a wall bound on a whole process (interpreter start, imports, one relay
# call): about half a second on a quiet host and, on one starved of CPU, as long as the host's load makes it, so the
# bound is a setting and not a constant: FABRIC_INBOX_REPLAY_WAIT_S, seconds, positive. A suite that runs this on a
# loaded host sets it high; it is never to be read as "the relay is slow".
REPLAY_WAIT_S = 15


def replay_wait() -> float:
    raw = os.environ.get("FABRIC_INBOX_REPLAY_WAIT_S")
    if raw is None:
        return REPLAY_WAIT_S
    try:
        wait = float(raw)
    except ValueError:
        wait = math.nan
    if not (wait > 0 and math.isfinite(wait)):
        raise Refused(f"FABRIC_INBOX_REPLAY_WAIT_S must be a positive number of seconds, got {raw!r}")
    return wait


def fetch_message(which: str) -> dict:
    """The message, read the way `gzcoord-inbox --replay` reads it: a MESSAGE-ID from this account's own journal first (the
    relay down, or none configured, makes no difference to a message the account already holds), else the relay's recent
    history; the body only when addressed to this login. The inbox's process is the one reader, so this and --replay cannot
    answer differently."""
    wait = replay_wait()
    try:
        p = subprocess.run([INBOX, "--replay", which, "--json"], capture_output=True, text=True, timeout=wait)
    except subprocess.TimeoutExpired:
        raise Refused(f"cannot read message {which}: the relay did not answer within {wait:g} s")
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


def listed_request(doc: dict, message_id: str) -> Job | None:
    """The job already made for this REQUEST, by whichever path added it: one
    that holds the message as its source, or one whose title names it. Every
    add of a request checks here, under the list's lock, so the inbox's intake,
    the sender's jobs-add and a person's `add --request` give one job."""
    return next((j for j in doc["jobs"] if (j.get("source") or {}).get("message_id") == message_id
                 or request_id_of(str(j.get("title", ""))) == message_id), None)


# What `add --owner ... --project` records, and what the inbox's receiver half then replaces with the resolver's reason.
SENDER_ADD_LABEL = "--project, as the sending side's jobs-add gave it"


def registered_projects_of(repository: str) -> list[str]:
    """The registered projects with a remote at `repository` (<org>/<repo>, case folded as GitHub reads it); any host, since the
    header carries the path only. Raises OSError/ValueError/AttributeError when the registry cannot be read:
    `request_project` turns that into its fallback, never into a refusal."""
    wc = _load("fabric_workingcopy", os.path.join(FABRIC_ROOT, "tools", "fabric", "workingcopy.py"))
    roots = _load("fabric_roots", os.path.join(FABRIC_ROOT, "tools", "fabric", "roots.py"))
    path = roots.projects_registry(engine=FABRIC_ROOT)
    # load_registry reads an absent file as an empty registry, which would make every REPOSITORY "unregistered".
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    projects = wc.load_registry(path).get("projects") or {}
    wanted = repository.strip().strip("/").casefold()
    return [name for name, entry in projects.items()
            if any((parsed := wc.parse_remote(remote)) and parsed["path"].strip("/").casefold() == wanted
                   for remote in entry.get("remotes") or [])]


def request_project(meta: dict, project: str | None) -> tuple[str | None, str | None]:
    """(the project a REQUEST's job belongs to, where that came from). --project wins; then the message's REPOSITORY, only when
    the registry is readable and maps it to exactly one project (it names the repository the work is in). Otherwise PROJECT,
    with the reason REPOSITORY did not decide (unregistered, ambiguous, registry unreadable): gzcoord-compose stamps PROJECT
    from the sender's directory, which says nothing of the work, but nothing a REQUEST carries may be the reason it is not
    queued: a lost assignment is worse than a job in the wrong project, which `project` re-points."""
    if project:
        return project, "--project"
    repository, header = meta.get("REPOSITORY"), meta.get("PROJECT")
    why = None
    if repository:
        try:
            found = registered_projects_of(repository)
        except (OSError, ValueError, AttributeError) as e:
            found, why = [], f"{repository}: registry unreadable ({type(e).__name__}: {e})"
        else:
            why = f"{repository} ambiguous: {', '.join(found)}" if len(found) > 1 else f"{repository} unregistered"
        if len(found) == 1:
            return found[0], f"REPOSITORY {repository}" + (f" (the header PROJECT: {header} was not used)" if header and header != found[0] else "")
    if not header:
        # The reason is still said. new_job then gives the job the project of the checkout it is added from, if any (not where the
        # message named), and the label says so rather than claiming "no project".
        return None, (f"none: REPOSITORY {why}, and no PROJECT header; the project is the adding checkout's, if any" if why else None)
    return header, "PROJECT" + (f": REPOSITORY {why}" if why else "")


def request_job(doc: dict, msg: dict, *, topic=None, project=None, working_copy=None, auto=False,
                priority=DEFAULT_PRIORITY) -> Job | None:
    meta = msg.get("metadata") or {}
    mid = meta.get("MESSAGE-ID") or str(msg.get("seq"))
    if auto and msg.get("type") != "REQUEST":
        return None
    listed = listed_request(doc, mid)
    if listed:
        if auto:
            return None
        raise Refused(f"message {mid} is already {listed['id']} ({listed['state']})")
    wanted, project_from = request_project(meta, project)
    here = identity.resolve_context(cwd=os.path.abspath(os.path.expanduser(working_copy)) if working_copy else None)
    if wanted and not working_copy and own_project(here) != wanted:
        # No refusal when there is none: a request lost from the list is worse than a job that cannot start (`start` says why).
        working_copy = working_copy_of(wanted)
    source = {"kind": "request" if msg.get("type") == "REQUEST" else (msg.get("type") or "message").lower(),
              "message_id": mid, "from": meta.get("FROM") or msg.get("sender"), "seq": msg.get("seq")}
    subject = meta.get("SUBJECT") or f"message {mid}"
    # The title the inbox and the sender's jobs-add give the same REQUEST (F11): the requester's `request:` blocker finds the job by it.
    # A message with no MESSAGE-ID (a relay seq stands in) has no id to carry.
    return new_job(doc, work.request_title(subject, mid) if work.MESSAGE_ID.fullmatch(mid) else subject, topic=topic, project=wanted,
                   working_copy=working_copy, source=source, priority=priority,
                   deliver_to=deliver_branch(msg), project_from=project_from)
