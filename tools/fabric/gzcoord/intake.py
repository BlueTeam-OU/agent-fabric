"""tools/fabric/gzcoord/intake.py — a REQUEST addressed to a login is work
that login has, so it is on that login's job list without anyone
remembering to put it there (agent-fabric ADR-037 §7, the owner,
2026-10-09).

Two halves, both best effort — a REQUEST that cannot be queued is a line
on stderr, never a failed delivery or a failed post:

  receiver  queue_received(): the inbox, for each REQUEST it delivers whose
            TO is this login's own address, adds a queued job to this
            login's list through jobs.py (source: the REQUEST, its
            MESSAGE-ID, sender and project). A message already on the list
            — as a job with that MESSAGE-ID as its source, or named in a
            title the sender's half wrote — adds nothing, so a redelivery,
            a second watch and the sender's own add are one job.
  sender    queue_for_addressee(): gzcoord-send, once a REQUEST TO a login
            is posted, when the sender is the operator of the addressee's
            host (runtime/hosts/registry.json), asks the control plane's
            jobs-add for the same job, titled "<SUBJECT> (REQUEST <id>)".
            This reaches a session whose watch has lapsed at its next
            start. The id is in the title because jobs-add takes nothing
            else (control plane frozen, ADR-040 §7).

Not TO-ROLE, not BROADCAST, not any other type: only an assignment names
one login (SPEC §13), and only an assignment is work."""
from __future__ import annotations

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


def listed(doc: dict, message_id: str) -> bool:
    return any((j.get("source") or {}).get("message_id") == message_id or message_id in str(j.get("title", ""))
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
        if not mid:
            continue
        try:
            jobs = jobs or _jobs()
            as_job = {"type": "REQUEST", "metadata": meta, "seq": rec.get("seq"), "sender": rec.get("sender")}

            def add(doc: dict, as_job: dict = as_job, mid: str = mid) -> Any:
                return None if listed(doc, mid) else jobs.request_job(doc, as_job, auto=True)

            job = jobs.mutate(add)
        except BaseException as e:  # noqa: BLE001 — any failure is a line; the delivery stands (SystemExit: identity's refusals)
            if isinstance(e, KeyboardInterrupt):
                raise
            err.write(f"gzcoord: REQUEST {mid} was not queued on your job list: {e}\n")
            continue
        if job:
            out.append(f"queued as {job['id']}: {job['title']}")
    return out


def operator_of(address: str, hosts: dict) -> str | None:
    """The login that operates the host an address names, from the hosts registry."""
    host = address.split("/", 1)[0] if "/" in address else None
    entry = (hosts.get("hosts") or {}).get(host) if host else None
    op = entry.get("operator") if isinstance(entry, dict) else None
    return op if isinstance(op, str) and op else None


def queue_for_addressee(msg: dict, *, sender: str, hosts: dict, run: Callable[..., Any] = subprocess.run,
                        err: Any = None) -> str | None:
    """Ask the addressee's control agent for the job; its id, or None. Only
    the host's operator signs a control action, so any other sender asks
    nothing."""
    err = err or sys.stderr
    meta = msg.get("metadata") or {}
    to, mid = meta.get("TO"), meta.get("MESSAGE-ID")
    if msg.get("type") != "REQUEST" or not to or not mid or "/" not in to:
        return None
    if operator_of(to, hosts) != sender:
        return None
    login = to.split("/", 1)[1]
    argv = [CTL, login, "jobs-add", *(["--project", meta["PROJECT"]] if meta.get("PROJECT") else []), "--",
            title_for(meta.get("SUBJECT", ""), mid)]
    try:
        r = run(argv, capture_output=True, text=True, timeout=CTL_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        err.write(f"gzcoord: REQUEST {mid} was not queued on {to}'s list: fabric-ctl did not answer in {CTL_TIMEOUT_S} s\n")
        return None
    except OSError as e:
        err.write(f"gzcoord: REQUEST {mid} was not queued on {to}'s list: {e.strerror or e}\n")
        return None
    found = _ADDED.search(r.stdout or "")
    if r.returncode != 0 or not found:
        said = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
        err.write(f"gzcoord: REQUEST {mid} was not queued on {to}'s list: "
                  f"{said[-1] if said else f'fabric-ctl exit {r.returncode}'}\n")
        return None
    return found.group(1)
