"""tools/fabric/gzcoord/intake.py — a REQUEST addressed to a login is work
that login has, so it is on that login's job list without anyone
remembering to put it there (agent-fabric ADR-037 §7, the owner,
2026-10-09).

Two halves, both best effort — a REQUEST that cannot be queued is a line
on stderr, never a failed delivery or a failed post:

  receiver  queue_received(): the inbox, for each REQUEST it delivers whose
            TO is this login's own address, adds a queued job to this
            login's list through jobs.py: source the REQUEST (MESSAGE-ID,
            sender, seq), project its PROJECT, title "<SUBJECT> (REQUEST
            <MESSAGE-ID>)". A project with no working copy here is still
            the job's project (what jobs-add does); the job then carries no
            working copy. A message already on the list — a job with that
            MESSAGE-ID as its source, or "(REQUEST <MESSAGE-ID>)" in its
            title — adds nothing, so a redelivery and a second watch are
            one job.
  sender    queue_for_addressee(): gzcoord-send, once a REQUEST TO a login
            is posted, when the sender is the operator of the addressee's
            host (runtime/hosts/registry.json), asks the control plane's
            jobs-add for the same job under the same title — unless the
            addressee's list already shows it (a live watch is usually
            first) or the relay answered "deduplicated" (a resend). This
            reaches a session whose watch has lapsed at its next start. The
            id is in the title because jobs-add takes nothing else (control
            plane frozen, ADR-040 §7), and it is the only thing the two
            halves share: the check and the add are not atomic, so two
            near-simultaneous halves can still make two jobs; a person
            drops one.

Not TO-ROLE, not BROADCAST, not any other type: only an assignment names
one login (SPEC §13), and only an assignment is work."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from typing import Any, Callable

from . import paths

TITLE_MAX = 300           # runtime/control/jobs.mjs TITLE_MAX: jobs-add refuses a longer title
CTL = os.path.join(paths.CHECKOUT, "bin", "fabric-ctl")
CTL_TIMEOUT_S = 30
_ADDED = re.compile(r"\badded\s+(j[1-9][0-9]*)\b", re.ASCII)
MESSAGE_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.ASCII)   # jobs.py's
PROJECT_SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,62}", re.ASCII)       # runtime/control/jobs.mjs's: a registry id


def _jobs():
    """tools/fabric/jobs.py, in this process, loaded when the first REQUEST needs it."""
    tools = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import jobs  # noqa: E402 — the sibling module
    return jobs


def is_request_to(meta: dict, address: str, mtype: Any) -> bool:
    return mtype == "REQUEST" and isinstance(meta, dict) and meta.get("TO") == address


def title_for(subject: str, message_id: str) -> str:
    """The sender's title, cut to jobs-add's limit with the id kept: the
    subject gives way, never the id the receiver dedupes on."""
    tail = f" (REQUEST {message_id})"
    subject = " ".join(str(subject or "").split())
    return subject[:max(TITLE_MAX - len(tail), 0)].rstrip() + tail


def named_in(title: str, message_id: str) -> bool:
    return f"(REQUEST {message_id})" in title


def listed(doc: dict, message_id: str) -> bool:
    return any((j.get("source") or {}).get("message_id") == message_id or named_in(str(j.get("title", "")), message_id)
               for j in doc.get("jobs", []))


def queue_received(classified: list[dict], me: dict, *, jobs: Any = None, err: Any = None) -> list[str]:
    """The lines to print with a delivery: `queued as jN` for each job this
    call added. `classified` is wait_loop's list ({rec, msg, isMine});
    `me` the inbox's identity (its address)."""
    err = err or sys.stderr
    out: list[str] = []
    for c in classified:
        msg, rec = c.get("msg"), c.get("rec") or {}
        meta = (msg or {}).get("metadata") or {}
        if not c.get("isMine") or not is_request_to(meta, me.get("address"), (msg or {}).get("type")):
            continue
        mid = meta.get("MESSAGE-ID")
        if not isinstance(mid, str) or not MESSAGE_ID.fullmatch(mid):
            err.write(f"gzcoord: a REQUEST to you was not queued on your job list: its MESSAGE-ID is not an id ({str(mid)[:60]!r})\n")
            continue
        try:
            jobs = jobs or _jobs()
            source = {"kind": "request", "message_id": mid, "from": meta.get("FROM") or rec.get("sender"), "seq": rec.get("seq")}
            project = meta.get("PROJECT") if PROJECT_SLUG.fullmatch(str(meta.get("PROJECT"))) else None
            title = title_for(meta.get("SUBJECT") or f"message {mid}", mid)

            def add(doc: dict, source: dict = source, project: Any = project, title: str = title, mid: str = mid) -> Any:
                return None if listed(doc, mid) else jobs.new_job(doc, title, project=project, source=source)

            job = jobs.mutate(add)
        except BaseException as e:  # noqa: BLE001 — any failure is a line; the delivery stands (SystemExit: identity's refusals)
            if isinstance(e, KeyboardInterrupt):
                raise
            err.write(f"gzcoord: REQUEST {mid} was not queued on your job list: {e}\n")
            continue
        if job:
            out.append(f"queued as {job['id']}: {job['title']}")
    return out


def operator_of(address: str, hosts: Any) -> str | None:
    """The login that operates the host an address names, from the hosts registry."""
    host = address.split("/", 1)[0] if "/" in address else None
    table = hosts.get("hosts") if isinstance(hosts, dict) else None
    entry = table.get(host) if isinstance(table, dict) and host else None
    op = entry.get("operator") if isinstance(entry, dict) else None
    return op if isinstance(op, str) and op else None


def addressee_lists(login: str, message_id: str, run: Callable[..., Any]) -> bool:
    """Does the addressee's list already show this REQUEST (its open jobs,
    as `fabric-ctl jobs --json` prints them, one JSON row per account)? A
    list that cannot be read says False: the add is the sender's purpose and
    the check only spares a duplicate."""
    try:
        r = run([CTL, login, "jobs", "--json"], capture_output=True, text=True, timeout=CTL_TIMEOUT_S)
        if r.returncode != 0:
            return False
        for line in (r.stdout or "").splitlines():
            row = json.loads(line)
            if any(named_in(str(j.get("title", "")), message_id) for j in (((row.get("jobs") or {}).get("jobs")) or [])):
                return True
    except Exception:  # noqa: BLE001 — see above: cannot tell is not a reason to skip the add
        return False
    return False


def queue_for_addressee(msg: dict, *, sender: str, hosts: Any, run: Callable[..., Any] = subprocess.run,
                        err: Any = None) -> str | None:
    """Ask the addressee's control agent for the job; its id, or None. Only
    the host's operator signs a control action, so any other sender asks
    nothing."""
    err = err or sys.stderr
    meta = msg.get("metadata") or {}
    to, mid = meta.get("TO"), meta.get("MESSAGE-ID")
    if msg.get("type") != "REQUEST" or not isinstance(to, str) or not isinstance(mid, str) or "/" not in to:
        return None
    try:
        if operator_of(to, hosts) != sender:
            return None
        login = to.split("/", 1)[1]
        if addressee_lists(login, mid, run):
            return None
        argv = [CTL, login, "jobs-add", *(["--project", meta["PROJECT"]] if PROJECT_SLUG.fullmatch(str(meta.get("PROJECT"))) else []),
                "--", title_for(meta.get("SUBJECT", ""), mid)]
        r = run(argv, capture_output=True, text=True, timeout=CTL_TIMEOUT_S)
        found = _ADDED.search(r.stdout or "")
        if r.returncode != 0 or not found:
            said = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
            raise RuntimeError(said[-1] if said else f"fabric-ctl exit {r.returncode}")
        return found.group(1)
    except subprocess.TimeoutExpired:
        why = f"fabric-ctl did not answer in {CTL_TIMEOUT_S} s"
    except OSError as e:
        why = str(e.strerror or e)
    except Exception as e:  # noqa: BLE001 — the post has succeeded: whatever this was, it is a line
        why = str(e)
    err.write(f"gzcoord: REQUEST {mid} was not queued on {to}'s list: {why}\n")
    return None
