"""tools/fabric/control/jobs.py — the job list on the control plane
(agent-fabric ADR-037 rule 6, ADR-029): runtime/control/jobs.mjs in
Python (ADR-040 Wave 8), unwired until the cutover.

`jobs` is a read op: this account's open jobs, as bin/fabric-jobs holds
them, for an operator. Not public: peers see each other's presence, not
each other's lists. `jobs-add` is an ACTION (sign.ACTION_OPS): the
owner's job, added to this login's list with source `owner` and the
operator's address. Both run tools/fabric/jobs.py as this login, by argv
— no field of a request reaches a shell — with the root it was given, so
the tool and the identity it loads are one tree's; the arguments of
jobs-add are a closed set, checked before anything runs.

CONTRACT, frozen from jobs.mjs:
  PROJECT_SLUG, TITLE_MAX, TOPIC_MAX, PRIORITIES      as Node's
  jobs(home, root, run)      {"status": "ok", "jobs": [...]}, each job's
                             id, state, title, project, topic, priority,
                             source, blocked_on, artifacts, updated; a
                             failed list is JobsError
  check_job_args(args)       None, or why the arguments are refused
  jobs_add(request, home, root, run)
                             {"status": "added", "job", ["warning"]} or
                             {"status": "refused", "reason"}

The arguments are judged as JavaScript judged them, since a request may
come from a Node fabric-ctl during the rolling upgrade and must be
refused or run alike: a length is UTF-16 code units, trim() is
JavaScript's whitespace, String() of a value is JavaScript's (null is
"null", which a project slug matches, and then no --project is passed,
as Node passed none), `$` never before a trailing newline, and an
object's keys in JavaScript's order.

WHAT IS NOT NODE'S: a jobs.py that gives no answer within the bound and
says nothing on stderr is refused with "no answer within 15 s"; Node's
reason was the empty string, its error's stderr.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from control import js  # noqa: E402

JOBS_TIMEOUT_S = 15
PROJECT_SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")   # matched whole: JavaScript's /^…$/
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
    return subprocess.run(["python3", *argv], capture_output=True, text=True, cwd=cwd, env=env, timeout=timeout,
                          stdin=subprocess.DEVNULL)


Runner = Callable[..., subprocess.CompletedProcess]


def jobs(home: str | None = None, root: str | None = None, run: Runner = run_python) -> dict:
    home = os.path.expanduser("~") if home is None else home
    root = _default_root(home) if root is None else root
    # --stored: the operator reads what the list holds, and the daemon
    # answers in seconds, never behind a read of the state stream.
    try:
        r = run([_jobs_py(root), "list", "--json", "--stored"], cwd=None, env={**os.environ, "AGENT_FABRIC_ROOT": root},
                timeout=JOBS_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise JobsError(f"fabric-jobs list: no answer within {JOBS_TIMEOUT_S} s") from None
    except OSError as e:
        raise JobsError(f"fabric-jobs list: {e.strerror or e}") from None
    if r.returncode != 0:
        raise JobsError(f"fabric-jobs list: exit {r.returncode}: {(r.stderr or '').strip().splitlines()[-1:] or ''}")
    try:
        listed = json.loads(r.stdout)
    except ValueError:
        raise JobsError("fabric-jobs list: the answer is not JSON") from None
    if not isinstance(listed, list) or not all(isinstance(j, dict) for j in listed):
        raise JobsError("fabric-jobs list: the answer is not a list of jobs")

    def nn(v, default=None):          # `v ?? default`
        return default if v is None else v

    out = []
    for j in listed:
        source = j.get("source")
        kind = source.get("kind") if isinstance(source, dict) else None
        # The log stays on the account: the owner reads where each job is, not its history.
        out.append({"id": j.get("id"), "state": j.get("state"), "title": j.get("title"), "project": nn(j.get("project")),
                    "topic": nn(j.get("topic")), "priority": j["priority"] if "priority" in j else "normal",
                    "source": nn(kind, "self"), "blocked_on": nn(j.get("blocked_on")), "artifacts": nn(j.get("artifacts"), []),
                    "updated": nn(j.get("updated"))})
    return {"status": "ok", "jobs": out}


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
        return "project is a registry id (lowercase, digits, dashes)"
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
    return {"status": "added", "job": re.sub(f"^added[{js.SPACE}]+", "", out),
            **({"warning": js.slice(warning, 300)} if warning else {})}


def _refused(stderr: str, otherwise: str) -> dict:
    last = js.trim(stderr).split("\n")[-1]
    why = re.sub(f"^fabric-jobs:[{js.SPACE}]*", "", last)
    return {"status": "refused", "reason": js.slice(why or otherwise, 200)}
