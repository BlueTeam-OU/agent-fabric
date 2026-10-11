"""tools/fabric/jobsparts/blockers.py — checkable blockers: a blocked job that says what it waits on in a form the
tool can check, so it learns by itself that the wait is over. A part of tools/fabric/jobs.py, whose docstring is the
contract.

THE FORMS (`block <id> --on <blocker>`, several allowed, all must clear)
  pr:<owner/repo>#<n>       cleared when the pull request is merged or closed (gh, through tools/fabric/gh.py)
  request:<message-id>      cleared when a REPLY whose IN-REPLY-TO is that id is in this login's journal
                            (episodic.open_readonly, the one reader's door)
  job:<login>/j<n>          cleared when that job is delivered, or has left the open list because it is done or
                            dropped; read through `fabric-ctl <login> jobs` (a host operator's op: any other
                            caller gets `unknown` with fabric-ctl's own refusal)

A CHECK says one of three things: `cleared`, `waiting`, or `unknown` (it could not be told: gh, the journal or
fabric-ctl failed, or the job is not on the open list and was never seen there). Unknown never clears a job.

THE CACHE (<state dir>/jobs-blockers.json, 0600): a check is made at most once per CACHE_TTL_S per blocker;
a cleared blocker stays cleared, since a merge, a reply and a delivered job do not undo. `--stored` and `--cached`
read it and check nothing. A job blocker also remembers that it was seen open: a job that is no longer on the open
list was closed only if it was seen open before; one never seen is unknown (a typo reads the same).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
from typing import Any, Callable, NamedTuple
from fabric_jobs.base import FABRIC_ROOT, MESSAGE_ID, Refused, _load, identity

CACHE_TTL_S = 600
CTL_TIMEOUT_S = 30
_REPO = r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9_.-]+"
PR = re.compile(rf"pr:({_REPO})#([1-9][0-9]{{0,8}})", re.ASCII)
REQUEST = re.compile(rf"request:({MESSAGE_ID.pattern})", re.ASCII)
JOB = re.compile(r"job:([a-z0-9][a-z0-9_-]{0,63})/(j[1-9][0-9]{0,8})", re.ASCII)
# What a free-text blocker names that has a checkable form: a PR number, or a GZCoord MESSAGE-ID.
NAMES_PR = re.compile(r"(?:\bPR\s*#?|#)\d+\b", re.IGNORECASE)
NAMES_MESSAGE = re.compile(MESSAGE_ID.pattern)
FORMS = "pr:<owner/repo>#<n>, request:<message-id> or job:<login>/j<n>"


class Check(NamedTuple):
    state: str          # "cleared", "waiting" or "unknown"
    detail: str


# The clock, replaceable: the cache bound is tested without waiting.
now: Callable[[], float] = time.time


def normalise(spec: str) -> str:
    """The blocker as it is stored, or Refused for a form that is none of the three."""
    text = spec.strip()
    if PR.fullmatch(text) or JOB.fullmatch(text):
        return text
    if REQUEST.fullmatch(text.lower()):
        return text.lower()
    raise Refused(f"{spec!r} is not a checkable blocker: {FORMS}; what is not checkable goes in the free text "
                  "(fabric-jobs block <id> \"<on what>\")")


def names_a_checkable(text: str) -> bool:
    return bool(NAMES_PR.search(text) or NAMES_MESSAGE.search(text))


# ── the three checks ────────────────────────────────────────────────────────────────────────────────────────────

def check_pr(repo: str, number: str) -> Check:
    gh = _load("fabric_gh", os.path.join(FABRIC_ROOT, "tools", "fabric", "gh.py"))
    try:
        state = str(gh.pr_view(int(number), ["state"], repo=repo).get("state") or "")
    except gh.GhError as e:
        return Check("unknown", f"gh: {e.reason}"[:160])
    except (ValueError, TypeError):
        return Check("unknown", "gh answered something that is not a pull request state")
    if state in ("MERGED", "CLOSED"):
        return Check("cleared", state.lower())
    return Check("waiting", state.lower() or "no state")


def check_request(message_id: str) -> Check:
    episodic = _load("fabric_episodic", os.path.join(FABRIC_ROOT, "tools", "fabric", "episodic.py"))
    path = episodic.db_path()
    if not os.path.exists(path):
        return Check("waiting", "no journal yet: nothing has been received")
    try:
        conn = episodic.open_readonly(path)
    except episodic.JournalError as e:
        return Check("unknown", str(e)[:160])
    try:
        row = conn.execute("SELECT 1 FROM episodes WHERE direction='inbound' AND type='REPLY' AND in_reply_to=? LIMIT 1",
                           (message_id,)).fetchone()
    except Exception as e:  # noqa: BLE001 — an unreadable journal is unknown, never a traceback in a listing
        return Check("unknown", f"journal: {e}"[:160])
    finally:
        conn.close()
    return Check("cleared", "answered") if row else Check("waiting", "no reply yet")


def ctl_program() -> list[str]:
    return [os.environ.get("AGENT_FABRIC_CTL") or os.path.join(FABRIC_ROOT, "bin", "fabric-ctl")]


def check_job(login: str, job_id: str, seen_open: bool) -> tuple[Check, bool]:
    """(the check, whether the job has now been seen on the open list). Absent from the open list is done or
    dropped only for a job seen open before."""
    try:
        p = subprocess.run([*ctl_program(), login, "jobs", "--json", "--timeout", "20"], capture_output=True, text=True,
                           timeout=CTL_TIMEOUT_S, stdin=subprocess.DEVNULL, check=False)
    except subprocess.TimeoutExpired:
        return Check("unknown", f"fabric-ctl did not answer within {CTL_TIMEOUT_S} s"), seen_open
    except OSError as e:
        return Check("unknown", f"fabric-ctl could not run ({e.strerror or e})"), seen_open
    row = None
    for text in p.stdout.splitlines():
        try:
            doc = json.loads(text)
        except ValueError:
            continue
        if isinstance(doc, dict) and doc.get("account") == login:
            row = doc
    if row is None or row.get("status") != "ok":
        why = (p.stderr.strip().splitlines() or [f"{login}: no answer" if row is None else f"{login}: {row.get('status')}"])[-1]
        return Check("unknown", f"fabric-ctl: {why}"[:160]), seen_open
    listed = (row.get("jobs") or {}).get("jobs") if isinstance(row.get("jobs"), dict) else None
    if not isinstance(listed, list):
        return Check("unknown", f"fabric-ctl: {login} gave no list of jobs"), seen_open
    job = next((j for j in listed if isinstance(j, dict) and j.get("id") == job_id), None)
    if job is None:
        if seen_open:
            return Check("cleared", "closed (done or dropped)"), True
        return Check("unknown", f"{job_id} is not on {login}'s open list: no such job, or closed before it was seen"), False
    if job.get("state") == "delivered":
        return Check("cleared", "delivered"), True
    return Check("waiting", str(job.get("state") or "open")), True


# ── the cache ───────────────────────────────────────────────────────────────────────────────────────────────────

def cache_path() -> str:
    return os.path.join(identity.agent_state_dir(), "jobs-blockers.json")


def load_cache() -> dict[str, dict]:
    try:
        with open(cache_path(), encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in doc.items() if isinstance(v, dict)} if isinstance(doc, dict) else {}


def save_cache(cache: dict[str, dict]) -> None:
    path = cache_path()
    try:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".jobs-blockers.", dir=os.path.dirname(path))
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, indent=1)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except OSError:
        pass   # a cache that cannot be written is checked again next time; it never fails a listing


def forget(specs: list[str]) -> None:
    """Drop the cache entries of `specs`: a job that blocks again on a spec starts from a fresh check, not from the
    answer a former wait left (a cleared blocker stays cleared only for as long as the wait it belonged to)."""
    cache = load_cache()
    if any(cache.pop(s, None) is not None for s in dict.fromkeys(specs)):
        save_cache(cache)


def run_check(spec: str, entry: dict | None) -> dict:
    """The cache entry for `spec`, freshly checked."""
    seen = bool((entry or {}).get("seen_open"))
    m = PR.fullmatch(spec)
    if m:
        result = check_pr(m.group(1), m.group(2))
    elif (m := REQUEST.fullmatch(spec)):
        result = check_request(m.group(1))
    elif (m := JOB.fullmatch(spec)):
        result, seen = check_job(m.group(1), m.group(2), seen)
    else:
        result = Check("unknown", "not a checkable form")
    return {"state": result.state, "detail": result.detail, "checked_at": now(), **({"seen_open": True} if seen else {})}


def refresh(specs: list[str], *, check: bool = True) -> dict[str, dict]:
    """The cache entry of each spec. With `check`, one that is not cleared and was last checked more than CACHE_TTL_S
    ago (or never) is checked now; a cleared one is never checked again. Without, nothing is checked."""
    cache = load_cache()
    changed = False
    for spec in dict.fromkeys(specs):
        entry = cache.get(spec)
        if not check or (entry and (entry.get("state") == "cleared"
                                    or (isinstance(entry.get("checked_at"), (int, float)) and now() - entry["checked_at"] < CACHE_TTL_S))):
            continue
        cache[spec] = run_check(spec, entry)
        changed = True
    if changed:
        save_cache(cache)
    return {s: cache[s] for s in specs if s in cache}


# ── what a job says of its blockers ─────────────────────────────────────────────────────────────────────────────

def specs_of(job: dict) -> list[str]:
    value = job.get("blockers")
    return [s for s in value if isinstance(s, str)] if isinstance(value, list) else []


def states_of(job: dict, cache: dict[str, dict]) -> list[dict[str, Any]]:
    """[{"spec", "state", "detail"?, "checked_at"}] for a job's checkable blockers, from `cache` alone. A spec never
    checked is `unknown` with a null time."""
    out = []
    for spec in specs_of(job):
        e = cache.get(spec) or {}
        at = e.get("checked_at")
        out.append({"spec": spec, "state": e.get("state") if e.get("state") in ("cleared", "waiting", "unknown") else "unknown",
                    "detail": e.get("detail"), "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(at))
                    if isinstance(at, (int, float)) else None})
    return out


def cleared_flag(job: dict, cache: dict[str, dict]) -> bool | None:
    """True when every checkable blocker is cleared, False when one was checked and still waits, None when the job
    has none, or none has been told yet (all unknown)."""
    states = [s["state"] for s in states_of(job, cache)]
    if not states:
        return None
    if all(s == "cleared" for s in states):
        return True
    if any(s == "waiting" for s in states):
        return False
    return None


def all_specs(doc: dict, *, only_blocked: bool = True) -> list[str]:
    return [s for j in doc["jobs"] if (j["state"] == "blocked" or not only_blocked) for s in specs_of(j)]
