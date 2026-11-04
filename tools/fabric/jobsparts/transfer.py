"""tools/fabric/jobsparts/transfer.py — `fabric-jobs export` and `import`: this login's job list moved to another host as one
versioned JSON document (the j422 design, gap F2). A part of tools/fabric/jobs.py, whose docstring is the contract.

The document is the list as jobs.json keeps it — format, version, agent, seq, last, jobs — and the blocker cache's entries for the
specs those jobs name (blocker_cache), and nothing else: no binding, no environment, so it holds no secret a job did not already hold.
The cache entries travel because `seen_open` is history the destination cannot re-derive: a job blocker whose peer closed after it was
seen open reads cleared, and without the memory it would read unknown for ever. It is read from
stdin and written to stdout in UTF-8 whatever the locale, so hostexec can pipe it and nothing needs a tty.

`import` only fills an EMPTY list of the same login: merging two lists would have to renumber ids, and every reference
(job:<login>/jN, a blocker, a REQUEST's intake) names an id. Each job is kept as exported, unknown fields too, because other
writers (the control agent) add fields this module does not know; the fields the rest of the tool reads or prints are checked for
type, and the text ones for the control characters `add` refuses (the document is from another host: an escape sequence in a title
would reach every terminal that lists the job). The source host is recorded in the document and not applied: update_jobs
writes this host's, and read_jobs refuses a list that names another."""
from __future__ import annotations

import json
import re
import sys
from fabric_jobs import blockers as bl
from fabric_jobs.base import DEFAULT_PRIORITY, PRIORITIES, STATES, Refused, identity, mutate

FORMAT = "fabric-jobs-export"
VERSION = 1
MAX_BYTES = 16 * 1024 * 1024   # a list is a few hundred KB after months; a bound keeps a wrong pipe from filling memory
MAX_DEPTH = 32   # a job is four levels deep (log entries); the bound is generous for fields another writer adds
JOB_ID = re.compile(r"j([1-9][0-9]*)", re.ASCII)
TOP_KEYS = {"format", "version", "agent", "host", "seq", "last", "jobs", "blocker_cache"}
TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", re.ASCII)
TEXT_KEYS = ("topic", "project", "working_copy", "branch", "worktree", "deliver_to", "blocked_on", "reason", "no_artifact", "waits_on", "project_from")


def has_control(text: str) -> bool:
    """The predicate records.new_job applies to a title: C0 (tab, newline and carriage return aside), DEL and C1."""
    return any((ord(c) < 32 and c not in "\t\n\r") or 127 <= ord(c) < 160 for c in text)


def strings(value: object):
    """Every string in a JSON value, at any depth, keys included: what a renderer may print is not a list of field names.
    An explicit stack, not recursion: the document is untrusted, and a value nested a thousand deep must not become a traceback."""
    stack = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        if depth > MAX_DEPTH:
            # json.dumps recurses too: a value this deep would pass the checks and then fail as a traceback when the list is written.
            raise Refused(f"a value is nested deeper than {MAX_DEPTH}")
        if isinstance(item, str):
            yield item
        elif isinstance(item, dict):
            for k, v in item.items():
                stack.append((k, depth + 1))
                stack.append((v, depth + 1))
        elif isinstance(item, list):
            stack.extend((v, depth + 1) for v in item)


def export_document(doc: dict, agent: str) -> dict:
    cache = bl.load_cache()
    return {"blocker_cache": {s: cache[s] for s in bl.all_specs(doc, only_blocked=False) if s in cache}, "format": FORMAT, "version": VERSION, "agent": agent, "host": doc.get("host") or identity.current_host(),
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
    except RecursionError:
        raise Refused("the document is nested too deeply")
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
    if not isinstance(job.get("title"), str) or not job["title"].strip():
        raise Refused(f"{where} has no title")
    for key in TEXT_KEYS:
        if job.get(key) is not None and not isinstance(job[key], str):
            raise Refused(f"{where} has a {key} that is not text")
    if not isinstance(job.get("blockers", []), list) or not all(isinstance(b, str) for b in job.get("blockers", [])):
        raise Refused(f"{where} has blockers that are not a list of strings")
    for spec in job.get("blockers", []):
        try:
            stored = bl.normalise(spec)
        except Refused:
            stored = None
        if stored != spec:
            raise Refused(f"{where} has a blocker {spec!r} that is not a checkable form in its stored shape")
    if job.get("state") not in STATES:
        raise Refused(f"{where} has state {job.get('state')!r}, not one of {', '.join(STATES)}")
    if job.get("priority", DEFAULT_PRIORITY) not in PRIORITIES:
        raise Refused(f"{where} has priority {job.get('priority')!r}, not one of {', '.join(PRIORITIES)}")
    for key in ("created", "updated"):
        if not isinstance(job.get(key), str) or not TIME.fullmatch(job[key]):
            raise Refused(f"{where} has no {key} time (YYYY-MM-DDTHH:MM:SSZ)")
    if not isinstance(job.get("source"), dict):
        raise Refused(f"{where} has no source")
    if not isinstance(job.get("artifacts"), list) or not all(isinstance(a, str) for a in job["artifacts"]):
        raise Refused(f"{where} has artifacts that are not a list of strings")
    if not isinstance(job.get("log"), list) or not all(isinstance(e, dict) for e in job["log"]):
        raise Refused(f"{where} has a log that is not a list of entries")
    # The whole job, not the fields known today: show prints source.from, a blocker, a log note, and a field the control agent adds.
    if any(has_control(t) for t in strings(job)):
        raise Refused(f"{where} carries a control character in its text")
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
    cache = doc.get("blocker_cache", {})
    if not isinstance(cache, dict) or not all(isinstance(k, str) and isinstance(v, dict) for k, v in cache.items()):
        raise Refused("the document's blocker_cache is not an object of entries")
    for spec, entry in cache.items():
        if any(has_control(t) for t in strings(entry)) or has_control(spec):
            raise Refused("the document's blocker_cache carries a control character")
        if not isinstance(entry.get("detail", ""), str) or type(entry.get("seen_open", True)) is not bool or entry.get("state", "unknown") not in ("cleared", "waiting", "unknown"):
            raise Refused(f"the document's blocker_cache entry for {spec!r} has a field of the wrong type")
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
    # After the list: a cache that cannot be written is checked again next time, as everywhere. Only the specs the jobs name, and an
    # entry this host already has is kept (it may be newer).
    wanted = set(bl.all_specs(doc, only_blocked=False))
    with bl._locked():
        cache = bl.load_cache()
        added = {s: bl._sane(e) for s, e in doc.get("blocker_cache", {}).items() if s in wanted and s not in cache}
        if added:
            bl.save_cache({**cache, **added})
    print(f"imported {len(doc['jobs'])} jobs (next id j{doc['seq'] + 1})")
    return 0
