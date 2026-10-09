"""tools/fabric/control/pool.py — a role's open pool of jobs (agent-fabric
ADR-037 rule 9), held by one control agent so that one process orders
every claim: runtime/control/pool.mjs in Python (ADR-040 Wave 8),
unwired until the cutover.

THE HOLDER is config.json's `pool_holder` when set; otherwise, with one
host in runtime/hosts/registry.json, that host's operator. With several
hosts and none configured no account holds it, and every pool op says
so: which agentd orders the claims is never guessed.

THE FILE is <state>/agents/<holder login>/pool.json, {seq, jobs: [...]},
written whole through a temporary file and a rename, as JSON.stringify
(doc, null, 2) lays it out: persisted state is frozen with the wire, and
a Node and a Python agentd read each other's. A file that cannot be read
is an error, never an empty pool: claims recorded in it would be handed
out again.

THE OPS. `pool-add` is an ACTION (sign.ACTION_OPS): the owner's job for a
role, a closed argument set — role, title, topic, project, priority — as
jobs-add checks it. `pool-list` and `pool-claim` are PUBLIC: any placed
account asks, for itself.

A CLAIM is checked against the claimant's binding as ITS control agent
reports it — the role in its newest state record on the state channel —
never a role the request names (the owner, 2026-10-08). No record from it
within STATES_STALE_MS (or within the newest STATES_REPLAY records, when
they reach back less) is a binding unknown, and the claim is refused. A
job has one claimant: a claim of a job another account holds is refused;
the same account claiming again gets it again.

SERIALIZED, by construction: every change to the file is one
read-modify-write that agentd runs in its loop, one request at a time,
and one agentd runs per account. What the relay verifies about a sender
is nothing: the fence is that a claim lands only on the claimant's own
list, written by its own fabric-jobs (rule 1).

CONTRACT, frozen from pool.mjs: POOL_FILE, POOL_ID, ROLE_SLUG,
pool_holder, read_pool (PoolError for a file that cannot be read),
by_priority, roles, check_pool_args, pool_add, pool_list,
role_from_stream, pool_claim — each answering {status, ...}, "refused"
with the reason the asker reads.

WHAT IS NOT NODE'S: the file's path is the caller's (Node's default was
upgrade.mjs's stateDir(), another port's), and so are STATES_REPLAY and
STATES_STALE_MS, ctl.mjs's, which this module states at their values
until ctl's port holds them. A write that fails is refused with
Python's text of the error (Node said "EACCES: permission denied, open
'…'"; Python "[Errno 13] Permission denied: '…'"). The file is read as
UTF-8 with bad bytes replaced, as Node's 'utf8' reads it. A pool or a
registry of a shape Node never writes is refused or names no holder
here: a job that is not an object (Node threw reading it), hosts that
is not an object or a host that is not one (Node named "0/user" for a
list, and threw for a null host).
"""
from __future__ import annotations

import errno
import functools
import os
import re
import sys
from datetime import datetime, timezone
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import roots  # noqa: E402
from control import gzcoord, js  # noqa: E402
from control.jobs import PRIORITIES, check_job_args  # noqa: E402
from control.sessions import date_parse  # noqa: E402

POOL_FILE = "pool.json"
POOL_ID = re.compile(r"p[1-9][0-9]{0,8}")              # matched whole
ROLE_SLUG = re.compile(r"[a-z][a-z0-9-]{0,62}")         # matched whole
# ctl.mjs's, until its port holds them (tests/test_control_pool.py holds
# them to ctl.mjs's values).
STATES_REPLAY = 500
STATES_STALE_MS = 2 * 10 * 60 * 1000


class PoolError(Exception):
    """The pool file cannot be read, is not JSON, or is not a pool."""


def _default_registry() -> str:
    return roots.hosts_registry(engine=gzcoord.FABRIC_ROOT, empty_is_set=True)


def pool_holder(cfg: dict | None = None, registry: str | None = None) -> str | None:
    """The address that holds the pool, or None when none can be named."""
    cfg = cfg or {}
    if isinstance(cfg.get("pool_holder"), str) and cfg["pool_holder"]:
        return cfg["pool_holder"]
    try:
        with open(_default_registry() if registry is None else registry, encoding="utf-8", errors="replace") as fh:
            doc = js.json_parse(fh.read())
        hosts = doc.get("hosts") if isinstance(doc, dict) else None
        # A registry Node never writes (hosts not an object, a host that is
        # not one) names no holder here: never guessed.
        if not isinstance(hosts, dict):
            return None
        names = js.keys(hosts)
        if len(names) != 1 or not isinstance(hosts[names[0]], dict):
            return None
        op = hosts[names[0]].get("operator")
        return f"{names[0]}/{js.string('user' if op is None else op)}"
    except (OSError, ValueError, AttributeError):
        return None


def read_pool(file: str) -> dict:
    try:
        with open(file, encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
    except FileNotFoundError:
        return {"seq": 0, "jobs": []}
    except OSError as e:
        code = errno.errorcode.get(e.errno) if e.errno else None
        raise PoolError(f"the pool cannot be read ({code or e})") from None
    try:
        doc = js.json_parse(raw)
    except ValueError:
        raise PoolError("the pool file is not JSON") from None
    if (not isinstance(doc, dict) or not isinstance(doc.get("jobs"), list) or not js.is_integer(doc.get("seq"))
            or not all(isinstance(j, dict) for j in doc["jobs"])):
        # A job that is not an object: Node's ops threw reading it ("Cannot
        # read properties of null"), a refusal too; here it is said once.
        raise PoolError("the pool file is not a pool")
    return doc


def _write_pool(file: str, doc: dict) -> None:
    # dirname of a bare name is "", which Node's path.dirname gives as ".".
    os.makedirs(os.path.dirname(file) or ".", exist_ok=True)
    tmp = f"{file}.{os.getpid()}.tmp"
    data = (js.stringify(doc, indent=2) + "\n").encode("utf-8")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    done = False
    try:
        try:
            # Every byte, or an error: one os.write() may write part of it (a
            # full disk, a file-size limit) and return, and a short pool
            # renamed over the good one loses every claim (review of d441507c, F1).
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view):]
        finally:
            os.close(fd)
        os.replace(tmp, file)
        done = True
    finally:
        # However the write ends — an error, an interrupt — no temporary
        # file is left beside the pool.
        if not done and os.path.exists(tmp):
            os.unlink(tmp)


def _index(priority) -> int:
    return PRIORITIES.index(priority) if isinstance(priority, str) and priority in PRIORITIES else -1


def _by_priority(a: dict, b: dict) -> float:
    d = _index(a.get("priority")) - _index(b.get("priority"))
    if d:
        return d
    sa, sb = a.get("seq"), b.get("seq")
    if isinstance(sa, (int, float)) and isinstance(sb, (int, float)) and not isinstance(sa, bool) and not isinstance(sb, bool):
        return sa - sb
    # Equal: as Node takes a seq that a.seq - b.seq reads as NaN (absent, an
    # object, a word). Node also coerces null, a boolean or a numeric
    # string, which pool.mjs never writes; here any seq that is not a
    # number is equal.
    return 0


# The pool's order is the queue's (tools/fabric/jobs.py queue_order):
# highest priority, then the oldest — Node's comparator, never a
# TypeError on a seq that is not a number; sorted() is stable as
# Array.prototype.sort is.
by_priority = functools.cmp_to_key(_by_priority)


def _shown(j: dict) -> dict:
    # A key the stored job lacks is undefined in Node, and JSON.stringify drops it.
    return {k: (j[k] if k in j else js.UNDEFINED) for k in ("id", "role", "title", "topic", "project", "priority", "created")}


def roles(catalog: str | None = None) -> set | None:
    try:
        return set(gzcoord.load_taxonomy(catalog or roots.role_catalog(engine=gzcoord.FABRIC_ROOT)).roles)
    except (OSError, ValueError, AttributeError, TypeError):
        return None


_UNSET = object()


def check_pool_args(args, known=_UNSET) -> str | None:
    known = roles() if known is _UNSET else known
    if not isinstance(args, dict):
        return "pool-add takes { role, title, topic, project, priority }"
    extra = [k for k in js.keys(args) if k not in ("role", "title", "topic", "project", "priority")]
    if extra:
        return f"pool-add takes only role, title, topic, project and priority, not {', '.join(extra)}"
    if not isinstance(args.get("role"), str) or not ROLE_SLUG.fullmatch(args["role"]):
        return "role is a catalogue id (lowercase, digits, dashes)"
    if not known:
        return "the role catalogue cannot be read"
    if args["role"] not in known:
        return f"no role {args['role']} in the catalogue"
    return check_job_args({k: v for k, v in args.items() if k != "role"})


def _refused(reason: str) -> dict:
    return {"status": "refused", "reason": reason}


def _not_holder(me: str, holder: str | None) -> dict | None:
    if not holder:
        return _refused("no account holds the pool: several hosts and no pool_holder in runtime/control/config.json")
    return None if me == holder else _refused(f"this account does not hold the pool; {holder} does")


def _iso_now() -> str:
    return js.iso_now()


def _squash(s: str) -> str:
    return js.SPACES.sub(" ", js.trim(s))


def pool_add(request: dict, *, me: str, holder: str | None, file: str, known=_UNSET, now: Callable[[], str] = _iso_now) -> dict:
    to = request.get("to")
    to = to if isinstance(to, list) else [to]
    if len(to) != 1 or to[0] != me:
        return _refused("pool-add names the account that holds the pool, and only it")
    no = _not_holder(me, holder)
    if no:
        return no
    bad = check_pool_args(request.get("args"), known)
    if bad:
        return _refused(bad)
    a = request["args"]
    topic = a.get("topic")
    try:
        doc = read_pool(file)
        doc["seq"] += 1
        job = {"id": f"p{js.string(doc['seq'])}", "seq": doc["seq"], "role": a["role"], "title": _squash(a["title"]),
               "topic": _squash(topic) if isinstance(topic, str) else None, "project": a.get("project"),
               "priority": "normal" if a.get("priority") is None else a["priority"], "created": now(),
               "from": js.string(request.get("from", js.UNDEFINED)), "claimed": None}
        doc["jobs"].append(job)
        _write_pool(file, doc)
        return {"status": "added", "job": _shown(job)}
    except (PoolError, OSError) as e:
        return _refused(str(e))


def pool_list(request: dict, *, me: str, holder: str | None, file: str) -> dict:
    no = _not_holder(me, holder)
    if no:
        return no
    args = request.get("args")
    role = args.get("role") if isinstance(args, dict) else None
    if not isinstance(role, str) or not ROLE_SLUG.fullmatch(role):
        return _refused("pool-list takes { role }")
    try:
        open_jobs = sorted((j for j in read_pool(file)["jobs"] if isinstance(j, dict) and j.get("role") == role and not js.truthy(j.get("claimed"))),
                           key=by_priority)
        return {"status": "ok", "role": role, "jobs": [_shown(j) for j in open_jobs]}
    except PoolError as e:
        return _refused(str(e))


def role_from_stream(*, call, cfg: dict, now: Callable[[], float] = lambda: datetime.now(timezone.utc).timestamp() * 1000):
    """The claimant's role as its control agent last reported it, read from
    the state channel: {"role"} or {"error"}."""
    def role_of(address: str) -> dict:
        try:
            page = call("/api/messages?" + js.search_params({"channel": cfg.get("state_channel", js.UNDEFINED),
                                                             "limit": js.string(STATES_REPLAY), "full": "1"}))
        except Exception as e:  # noqa: BLE001 — pool.mjs's catch: any failure of the call is an answer
            return {"error": f"the state stream could not be read ({gzcoord.relay_failure(e, cfg.get('relay_url'))})"}
        rows = page.get("messages") if isinstance(page, dict) and isinstance(page.get("messages"), list) else []
        newest, oldest = None, float("nan")
        for rec in rows:
            try:
                content = rec.get("content") if isinstance(rec, dict) else None
                r = js.json_parse(content) if isinstance(content, str) else None
            except ValueError:
                continue
            if not isinstance(r, dict) or r.get("kind") != "state" or not (js.is_integer(r.get("v")) and r.get("v") == 1) \
                    or not isinstance(r.get("ts"), str):
                continue
            t = date_parse(r["ts"])
            if t == t and not (t >= oldest):   # a ts that does not parse says nothing of the span
                oldest = t
            if r.get("from") == address:
                newest = r
        # The relay gives its newest STATES_REPLAY records and pages only
        # forward: a full page that reaches back less than STATES_STALE_MS
        # has not looked at the whole bound, and says so rather than that
        # nothing came in it.
        n = now()
        if newest is None and len(rows) >= STATES_REPLAY and not (n - oldest >= STATES_STALE_MS):
            span = f"only {js.string((n - oldest) // 60000)} min" if oldest == oldest else "an unknown span"
            return {"error": f"the state stream's last {len(rows)} records reach back {span} and none is from {address}: its binding is unknown"}
        if newest is None or not (n - date_parse(newest["ts"]) <= STATES_STALE_MS):
            return {"error": f"no state record from {address} in the last {js.string(STATES_STALE_MS / 60000)} min: its binding is unknown"}
        role = newest.get("role")
        return {"role": role} if isinstance(role, str) and role else {"error": f"{address} reports no bound role"}
    return role_of


def pool_claim(request: dict, *, me: str, holder: str | None, file: str, role_of=None, now: Callable[[], str] = _iso_now) -> dict:
    no = _not_holder(me, holder)
    if no:
        return no
    args = request.get("args")
    pid = args.get("id") if isinstance(args, dict) else None
    if not isinstance(pid, str) or not POOL_ID.fullmatch(pid):
        return _refused("pool-claim takes { id }, a pool job id (p<n>)")
    sender = js.string(request.get("from", js.UNDEFINED))
    if not callable(role_of):
        return _refused("this control agent reads no state stream: the claimant's role is unknown")
    bound = role_of(sender)
    try:
        doc = read_pool(file)
        job = next((j for j in doc["jobs"] if isinstance(j, dict) and j.get("id") == pid), None)
        if job is None:
            return _refused(f"no pool job {pid}")
        if bound.get("error"):
            return _refused(bound["error"])
        if bound.get("role") != job.get("role"):
            return _refused(f"{sender} holds {js.string(bound.get('role', js.UNDEFINED))}, as its control agent reports it; {pid} is for {js.string(job.get('role', js.UNDEFINED))}")
        claimed = job.get("claimed")
        if js.truthy(claimed) and (claimed.get("by") if isinstance(claimed, dict) else js.UNDEFINED) != sender:
            by = claimed.get("by", js.UNDEFINED) if isinstance(claimed, dict) else js.UNDEFINED
            at = claimed.get("at", js.UNDEFINED) if isinstance(claimed, dict) else js.UNDEFINED
            return _refused(f"{pid} is claimed by {js.string(by)} ({js.string(at)})")
        again = js.truthy(claimed)
        if not again:
            job["claimed"] = {"by": sender, "at": now()}
            _write_pool(file, doc)
        return {"status": "claimed", "job": _shown(job), **({"again": True} if again else {})}
    except (PoolError, OSError) as e:
        return _refused(str(e))
