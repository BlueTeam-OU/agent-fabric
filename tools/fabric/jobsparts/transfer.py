"""tools/fabric/jobsparts/transfer.py — `fabric-jobs export` and `import`: this login's job list moved to another host as one
versioned JSON document (the j422 design, gap F2). A part of tools/fabric/jobs.py, whose docstring is the contract.

The document is the list as jobs.json keeps it — format, version, agent, seq, last, jobs — and nothing else: no state-directory
file beside it (the blocker cache, the binding), no environment, so it holds no secret a job did not already hold. It is read from
stdin and written to stdout in UTF-8 whatever the locale, so hostexec can pipe it and nothing needs a tty.

`import` only fills an EMPTY list of the same login: merging two lists would have to renumber ids, and every reference
(job:<login>/jN, a blocker, a REQUEST's intake) names an id. Each job is kept as exported, unknown fields too, because other
writers (the control agent) add fields this module does not know; only the fields the rest of the tool reads are checked.
The host stamp is not carried: update_jobs writes this host's, and read_jobs refuses a list that names another."""
from __future__ import annotations

import json
import re
import sys
from fabric_jobs.base import DEFAULT_PRIORITY, PRIORITIES, STATES, Refused, identity, mutate

FORMAT = "fabric-jobs-export"
VERSION = 1
MAX_BYTES = 16 * 1024 * 1024   # a list is a few hundred KB after months; a bound keeps a wrong pipe from filling memory
JOB_ID = re.compile(r"j([1-9][0-9]*)", re.ASCII)
TOP_KEYS = {"format", "version", "agent", "host", "seq", "last", "jobs"}


def export_document(doc: dict, agent: str) -> dict:
    return {"format": FORMAT, "version": VERSION, "agent": agent, "host": doc.get("host") or identity.current_host(),
            "seq": doc["seq"], "last": doc.get("last"), "jobs": doc["jobs"]}


def export_jobs(args) -> int:
    """export: the whole list, every state, on stdout."""
    agent = identity.current_agent()
    text = json.dumps(export_document(identity.read_jobs(agent), agent), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    sys.stdout.flush()
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.flush()
    return 0


def read_stdin() -> str:
    if sys.stdin.isatty():
        raise Refused("import reads the exported document on stdin: fabric-jobs export | fabric-jobs import")
    raw = sys.stdin.buffer.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise Refused(f"the document is larger than {MAX_BYTES} bytes")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise Refused("the document is not UTF-8")


def parse(text: str) -> dict:
    try:
        # Python reads NaN and Infinity; JSON does not have them, and a stored one would not survive the next json.dumps strictly.
        doc = json.loads(text, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
    except ValueError as exc:
        raise Refused(f"the document is not valid JSON ({exc})")
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise Refused(f"the document is not a fabric-jobs export (format {FORMAT!r} missing)")
    version = doc.get("version")
    if type(version) is not int or version != VERSION:
        raise Refused(f"the document is version {version!r}; this fabric-jobs imports version {VERSION}")
    unknown = sorted(set(doc) - TOP_KEYS)
    if unknown:
        raise Refused(f"the document has unknown field {unknown[0]!r}")
    return doc


def check_job(job: object, position: int) -> str:
    where = f"job {position + 1}"
    if not isinstance(job, dict):
        raise Refused(f"{where} is not an object")
    job_id = job.get("id")
    if not isinstance(job_id, str) or not JOB_ID.fullmatch(job_id):
        raise Refused(f"{where} has no id of the form jN")
    where = job_id
    if not isinstance(job.get("title"), str) or not job["title"]:
        raise Refused(f"{where} has no title")
    if job.get("state") not in STATES:
        raise Refused(f"{where} has state {job.get('state')!r}, not one of {', '.join(STATES)}")
    if job.get("priority", DEFAULT_PRIORITY) not in PRIORITIES:
        raise Refused(f"{where} has priority {job.get('priority')!r}, not one of {', '.join(PRIORITIES)}")
    for key in ("created", "updated"):
        if not isinstance(job.get(key), str):
            raise Refused(f"{where} has no {key} time")
    if not isinstance(job.get("source"), dict):
        raise Refused(f"{where} has no source")
    if not isinstance(job.get("artifacts"), list) or not all(isinstance(a, str) for a in job["artifacts"]):
        raise Refused(f"{where} has artifacts that are not a list of strings")
    if not isinstance(job.get("log"), list) or not all(isinstance(e, dict) for e in job["log"]):
        raise Refused(f"{where} has a log that is not a list of entries")
    return job_id


def check_document(doc: dict, agent: str) -> None:
    if doc.get("agent") != agent:
        raise Refused(f"the document is {doc.get('agent')!r}'s job list; this login is {agent!r}")
    jobs, seq = doc.get("jobs"), doc.get("seq")
    if not isinstance(jobs, list):
        raise Refused("the document has no list of jobs")
    ids = [check_job(job, i) for i, job in enumerate(jobs)]
    if len(set(ids)) != len(ids):
        raise Refused(f"the document lists {next(i for i in ids if ids.count(i) > 1)} twice")
    # seq is the counter the next id comes from: below an existing id, the next add would repeat it.
    if type(seq) is not int or seq < max((int(JOB_ID.fullmatch(i).group(1)) for i in ids), default=0):
        raise Refused(f"the document's seq {seq!r} is not a number at or above its highest job id")
    if sum(job["state"] == "active" for job in jobs) > 1:
        raise Refused("the document has more than one active job")
    if doc.get("last") is not None and doc["last"] not in ids:
        raise Refused(f"the document's last job {doc['last']!r} is not in its list")


def import_jobs(args) -> int:
    """import: the document on stdin into this login's empty list, ids kept."""
    agent = identity.current_agent()
    doc = parse(read_stdin())
    check_document(doc, agent)

    def fill(current: dict) -> None:
        # Checked inside the lock: two imports, or an add racing one, must not both find the list empty.
        if current["jobs"] or current.get("seq"):
            raise Refused(f"this list is not empty ({len(current['jobs'])} jobs, next id j{int(current.get('seq', 0)) + 1}); import fills an empty one only")
        current["seq"], current["jobs"] = doc["seq"], doc["jobs"]
        if doc.get("last") is not None:
            current["last"] = doc["last"]

    mutate(fill)
    print(f"imported {len(doc['jobs'])} jobs (next id j{doc['seq'] + 1})")
    return 0
