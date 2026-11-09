"""tools/fabric/control/jobs.py — the job list on the control plane
(agent-fabric ADR-037 rule 6, ADR-029): ported from runtime/control/jobs.mjs
(ADR-040 Wave 8; deleted in step s8).

`jobs` is a read op: this account's open jobs, as bin/fabric-jobs holds
them, for an operator. Not public: peers see each other's presence, not
each other's lists. `job-state` is the one narrow public read beside it
(see JOB-STATE below). `jobs-add` is an ACTION (sign.ACTION_OPS): the
owner's job, added to this login's list with source `owner` and the
operator's address. Both run tools/fabric/jobs.py as this login, by argv
— no field of a request reaches a shell — with the root it was given, so
the tool and the identity it loads are one tree's; the arguments of
jobs-add are a closed set, checked before anything runs.

CONTRACT, frozen from jobs.mjs:
  TITLE_MAX, TOPIC_MAX, PRIORITIES                    as Node's
  jobs(home, root, run)      {"status": "ok", "jobs": [...], "hold": null or the
                             fleet hold's record (ADR-037 rule 13)}, each job's
                             id, state, title, project, topic, priority,
                             source, blocked_on, artifacts, updated, and
                             where it has checkable blockers (after the
                             Node was deleted) blockers and cleared; a
                             failed list is JobsError
  check_job_args(args)       None, or why the arguments are refused
  jobs_add(request, home, root, run)
                             {"status": "added" or "listed", "job", ["warning"]} or
                             {"status": "refused", "reason"}
  job_state(request, home, root, run)
                             {"status": "ok", "id", "state"} (state: a job state, or "absent")
                             or {"status": "refused", "reason"}

JOB-STATE (PUBLIC, control/ops PUBLIC_OPS): a placed account asks this
account about exactly one job, by `args` {job: "j<n>"} or {request: "<message
id>"} (the job whose title ends "(REQUEST <id>)", work/request_title.py),
and gets that job's id and state: queued, active, paused, blocked,
delivered, done, dropped, or "absent" when the list holds no such job. It
never carries a title, a list or another job.
WHO MAY ASK: the sender of the REQUEST the job was taken from, the job's
`source.from`, and only of a job whose source kind is `request` (a job from a
pool, an owner or self is asked of by nobody, though it may carry a `from`);
any other asker is refused, the same words for every job that
exists, so a refusal names nothing. "absent" is said to anyone: an id with no
job carries nothing to protect, and a job that left the list reads as closed
only to a waiter that saw it open (jobsparts/blockers.py).
WHAT IS NOT CHECKED, and why: the second reader the owner's request allowed,
a login that names the job in its own blocker. A blocker is held in that
login's own job list and in no record this account can read (the state stream
carries `waits_on` message ids, not blockers, and one account never reads
another's list), so the answering side cannot tell a real blocker from a
claim of one: it would be the sender condition with a password anyone could
say. Only the sender is answered.

The arguments are judged as JavaScript judged them, since a request may
come from a Node fabric-ctl during the rolling upgrade and must be
refused or run alike: a length is UTF-16 code units, trim() is
JavaScript's whitespace, String() of a value is JavaScript's (null is
"null", which a project slug matches, and then no --project is passed,
as Node passed none), `$` never before a trailing newline, and an
object's keys in JavaScript's order.

WHAT IS NOT NODE'S: PROJECT_SLUG is registry_id.py's grammar, shared with the
job list and the intake. It admits a dot inside an id (the registry has ids
that Node refused), refuses a trailing hyphen Node admitted, and a number
as `project` now reads as its text ("1.5") and passes; tests/test_registry_id.py
holds the registry to it. The project refusal's words are registry_id.py's
(Node's said "lowercase, digits, dashes", which a dot made untrue); every other
refusal text is Node's.

WHAT IS NOT NODE'S, where Node's refusal said nothing: its reason was
its error's stderr, the empty string, when jobs.py gave no answer within
the bound, exited non-zero saying nothing (or only "fabric-jobs:"), or
could not be started. Here the reason is "no answer within 15 s",
"exit <n>", or why it could not be started.

What crosses to jobs.py is what Node's execFile sent: each argument
String()-ed, a lone surrogate as U+FFFD (a title the operator signed
with one is added, as Node added it, not a crash); its output read as
UTF-8 with bad bytes replaced, never by the locale.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from typing import Callable

# Run as a script, this directory would lead sys.path and its queue.py
# shadow the standard library's for any module importing it: replaced.
if sys.path and os.path.realpath(sys.path[0] or ".") == os.path.dirname(os.path.realpath(__file__)):
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
else:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from control import js  # noqa: E402
import hold_view  # noqa: E402
from registry_id import REGISTRY_ID as PROJECT_SLUG, REGISTRY_ID_DESCRIPTION  # noqa: E402 — one grammar for jobs-add, the job list and the intake

JOBS_TIMEOUT_S = 15
TITLE_MAX = 300
TOPIC_MAX = 60
# ADR-037 rule 7; tools/fabric/jobs.py PRIORITIES is the same list.
PRIORITIES = ["blocking", "high", "normal", "low"]

# A control character in a title would reach the list, the prompt of a
# fresh session and every operator's terminal: C0, DEL and C1 (U+009B is
# a terminal's CSI as surely as ESC [ is).
_CONTROL = re.compile("[\u0000-\u001f\u007f-\u009f]")


class JobsError(Exception):
    """jobs.py could not answer the list: not run, failed, or not a list."""


def _plain(s) -> bool:
    return isinstance(s, str) and not _CONTROL.search(s)


def _jobs_py(root: str) -> str:
    return os.path.join(root, "tools", "fabric", "jobs.py")


def _default_root(home: str) -> str:
    # `??`: set but empty is set.
    root = os.environ.get("AGENT_FABRIC_ROOT")
    return root if root is not None else os.path.join(home, "projects", "agent-fabric")


def run_python(argv: list[str], *, cwd: str | None, env: dict, timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(["python3", *argv], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          cwd=cwd, env=env, timeout=timeout, stdin=subprocess.DEVNULL)


Runner = Callable[..., subprocess.CompletedProcess]


def _hold() -> dict | None:
    from control.hold import identity_module
    return hold_view.read(identity_module())


def _listed(root: str, run: Runner, *extra: str) -> list[dict]:
    """The stored list as jobs.py gives it (`list --json --stored`), or JobsError."""
    # --stored: the operator reads what the list holds, and the daemon
    # answers in seconds, never behind a read of the state stream.
    try:
        r = run([_jobs_py(root), "list", "--json", "--stored", *extra], cwd=None, env={**os.environ, "AGENT_FABRIC_ROOT": root},
                timeout=JOBS_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise JobsError(f"fabric-jobs list: no answer within {JOBS_TIMEOUT_S} s") from None
    except OSError as e:
        raise JobsError(f"fabric-jobs list: {e.strerror or e}") from None
    if r.returncode != 0:
        lines = (r.stderr or "").strip().splitlines()
        raise JobsError(f"fabric-jobs list: exit {r.returncode}: {lines[-1] if lines else ''}")
    try:
        listed = json.loads(r.stdout)
    except ValueError:
        raise JobsError("fabric-jobs list: the answer is not JSON") from None
    if not isinstance(listed, list) or not all(isinstance(j, dict) for j in listed):
        raise JobsError("fabric-jobs list: the answer is not a list of jobs")
    return listed


def jobs(home: str | None = None, root: str | None = None, run: Runner = run_python, hold: Callable[[], dict | None] = _hold) -> dict:
    home = os.path.expanduser("~") if home is None else home
    root = _default_root(home) if root is None else root
    listed = _listed(root, run)

    def nn(v, default=None):          # `v ?? default`
        return default if v is None else v

    out = []
    for j in listed:
        source = j.get("source")
        kind = source.get("kind") if isinstance(source, dict) else None
        # The log stays on the account: the owner reads where each job is, not its history.
        # j.id of a job without one is undefined, which JSON.stringify drops.
        out.append({**{k: j[k] for k in ("id", "state", "title") if k in j}, "project": nn(j.get("project")),
                    "topic": nn(j.get("topic")), "priority": j["priority"] if "priority" in j else "normal",
                    "source": nn(kind, "self"), "blocked_on": nn(j.get("blocked_on")), "artifacts": nn(j.get("artifacts"), []),
                    "updated": nn(j.get("updated")),
                    # Only where the job has checkable blockers (fabric-jobs list --json --stored, from its cache): the
                    # board reads a missing key as "not said". Each is {spec, state, detail, checked_at}.
                    **({"blockers": j["blockers"], "cleared": j.get("cleared")} if isinstance(j.get("blockers"), list) and j["blockers"] else {})})
    # ADR-037 rule 13: null when not held; {"unreadable": why} for a hold.json that cannot be read, which holds.
    return {"status": "ok", "jobs": out, "hold": hold()}


def check_job_args(args) -> str | None:
    if not isinstance(args, dict):
        return "jobs-add takes { title, topic, project, priority }"
    extra = [k for k in js.keys(args) if k not in ("title", "topic", "project", "priority")]
    if extra:
        return f"jobs-add takes only title, topic, project and priority, not {', '.join(extra)}"
    title = args.get("title")
    if not _plain(title) or not js.trim(title) or js.length(title) > TITLE_MAX:
        return f"title is one line of 1 to {TITLE_MAX} characters"
    if "topic" in args:
        topic = args["topic"]
        if not _plain(topic) or not js.trim(topic) or js.length(topic) > TOPIC_MAX:
            return f"topic is one line of 1 to {TOPIC_MAX} characters"
    if "project" in args and not PROJECT_SLUG.fullmatch(js.string(args["project"])):
        return f"project is a registry id ({REGISTRY_ID_DESCRIPTION})"
    if "priority" in args and not (isinstance(args["priority"], str) and args["priority"] in PRIORITIES):
        return f"priority is one of {', '.join(PRIORITIES)}"
    return None


def jobs_add(request: dict, home: str | None = None, root: str | None = None, run: Runner = run_python) -> dict:
    home = os.path.expanduser("~") if home is None else home
    root = _default_root(home) if root is None else root
    # One login's, never the fleet's: fabric-ctl refuses `all`, and a signed
    # request that names more than this account is refused here too.
    to = request.get("to")
    to = to if isinstance(to, list) else [to]
    if len(to) != 1 or to[0] == "*":
        return {"status": "refused", "reason": "jobs-add names one login, never all"}
    args = request.get("args")
    bad = check_job_args(args)
    if bad:
        return {"status": "refused", "reason": bad}
    title, topic, project, priority = (args.get(k) for k in ("title", "topic", "project", "priority"))
    # `--` before the title: a title that begins with a dash is a title.
    argv = [_jobs_py(root), "add", "--owner", js.string(request.get("from")),
            *(["--topic", js.string(topic)] if js.truthy(topic) else []),
            *(["--project", js.string(project)] if js.truthy(project) else []),
            *(["--priority", js.string(priority)] if js.truthy(priority) else []), "--", title]
    argv = [js.well_formed(a) for a in argv]
    try:
        r = run(argv, cwd=home, env={**os.environ, "AGENT_FABRIC_ROOT": root}, timeout=JOBS_TIMEOUT_S)
    except subprocess.TimeoutExpired as e:
        said = e.stderr.decode("utf-8", "replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        return _refused(said, f"no answer within {JOBS_TIMEOUT_S} s")
    except OSError as e:
        return _refused("", str(e.strerror or e))
    if r.returncode != 0:
        return _refused(r.stderr or "", f"exit {r.returncode}")
    out = js.trim(r.stdout or "")
    # What fabric-jobs says on stderr of a job it added (no working copy
    # of the project found) is the owner's to read, not dropped.
    warning = js.SPACES.sub(" ", js.trim(r.stderr or ""))
    # "already listed": the title names a REQUEST the list holds (fabric-jobs add),
    # so nothing was added; the job it names is the answer.
    listed = out.startswith("already listed")
    return {"status": "listed" if listed else "added", "job": re.sub(f"^(added|already listed)[{js.SPACE}]+", "", out),
            **({"warning": js.slice(warning, 300)} if warning else {})}


def _refused(stderr: str, otherwise: str) -> dict:
    last = js.trim(stderr).split("\n")[-1]
    why = re.sub(f"^fabric-jobs:[{js.SPACE}]*", "", last)
    return {"status": "refused", "reason": js.slice(why or otherwise, 200)}


JOB_ID = re.compile(r"j[1-9][0-9]{0,8}", re.ASCII)
MESSAGE_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.ASCII)
_REQUEST_TAIL = re.compile(r"\(REQUEST ([0-9A-Fa-f-]{36})\)\Z")


def _request_of(title: object) -> str | None:
    """The message id a title ends in "(REQUEST <id>)" with, lower case; None for any other title."""
    m = _REQUEST_TAIL.search(" ".join(title.split())) if isinstance(title, str) else None
    return m.group(1).lower() if m and MESSAGE_ID.fullmatch(m.group(1).lower()) else None


def check_job_state_args(args) -> str | None:
    if not isinstance(args, dict) or len(args) != 1:
        return "job-state takes { job } or { request }"
    if "job" in args:
        return None if isinstance(args["job"], str) and JOB_ID.fullmatch(args["job"]) else "job is j<n>"
    if "request" in args:
        return None if isinstance(args["request"], str) and MESSAGE_ID.fullmatch(args["request"].lower()) else "request is a message id"
    return "job-state takes { job } or { request }"


def job_state(request: dict, home: str | None = None, root: str | None = None, run: Runner = run_python) -> dict:
    """See JOB-STATE in the header. `request["from"]` is a claim the relay does not verify (agentd's fence); what it
    buys is the same as pool-claim's: a read of one job's state, by someone who already holds the REQUEST's id and
    the relay's token."""
    home = os.path.expanduser("~") if home is None else home
    root = _default_root(home) if root is None else root
    args = request.get("args")
    bad = check_job_state_args(args)
    if bad:
        return {"status": "refused", "reason": bad}
    asker = request.get("from")
    try:
        # --all: a job that is done or dropped is no longer open, and is still on the list the asker's blocker waits on.
        listed = _listed(root, run, "--all")
    except JobsError as e:
        return {"status": "refused", "reason": js.slice(str(e), 200)}
    if "job" in args:
        found = next((j for j in listed if j.get("id") == args["job"]), None)
    else:
        wanted = args["request"].lower()
        found = next((j for j in listed if _request_of(j.get("title")) == wanted), None)
    if found is None:
        return {"status": "ok", "id": args.get("job"), "state": "absent"}
    source = found.get("source")
    sender = source.get("from") if isinstance(source, dict) and source.get("kind") == "request" else None
    if not (isinstance(asker, str) and isinstance(sender, str) and sender == asker):
        return {"status": "refused", "reason": "job-state answers the sender of the request the job was taken from"}
    return {"status": "ok", "id": found.get("id"), "state": found.get("state")}
