"""tools/fabric/work/claims.py — the only code that changes a claim in a role's pool.json (agent-fabric ADR-037 rule 14, rows R2,
R2c and R2d; ADR-067).

A pool job is in one of three states, read from its `claimed` field and never stored apart from it:
  open     `claimed` is null: any placed agent of the role may claim it;
  claimed  `claimed` is {"by": <address>, "at": <time>}: one claimant, whose own list holds the job;
  closed   `claimed` also holds {"closed": {"at", "how"}}: the claimant's job ended (`how` is done or dropped). The claim is kept,
           never removed, and refused to every claim, its claimant's included: a job done is done, and a pool is not a queue
           that hands the same work to the same agent again.

The holder's control agent makes all three moves (control/pool.py calls this module), the last two from what the claimant's own
control agent says of its list in its state record (`claims`, control/sessions.py): each claim it holds by the pool's generation
and id, with the state of the job it became. `judge` is the whole of that reading and is pure: the caller hands it the record, or
None where there is none. A record that is missing, stale, unreadable or does not report claims is unknown, and unknown moves
nothing — never a default that closes or reopens a claim.
"""
from __future__ import annotations

import calendar
import re
import time

from fabric_work import table
from fabric_work.lifecycle import Refusal

# How long a claim is left to be taken up before a record that reports none for it reopens it (rule 14, R2d).
REOPEN_AFTER_S = 24 * 60 * 60
ENDED = ("done", "dropped")
GENERATION = re.compile(r"[0-9a-f]{32}")
POOL_ID = re.compile(r"p[1-9][0-9]{0,8}")
# Every need a pool row names, and who proves it: the engine here, or the caller, which holds the stream and the registry.
NEEDS = frozenset({"role", "title", "project", "priority", "binding_holds_role", "no_other_claimant", "fresh_record_reports_ended",
                   "day_passed_fresh_record_holds_none"})


def _truthy(value) -> bool:
    """JavaScript's truthiness, as the pool file has always been read (a pool.json a Node agentd wrote is read by a Python one): a claim
    that is `{}` or `[]` is held, one that is 0 or "" is not."""
    if value is None or value is False:
        return False
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return value == value and value != 0
    if isinstance(value, str):
        return value != ""
    return True


def state_of(job: dict) -> str:
    claimed = job.get("claimed")
    if not _truthy(claimed):
        return "open"
    return "closed" if isinstance(claimed, dict) and claimed.get("closed") else "claimed"


def _row(who: str, job: dict, to: str) -> None:
    if table.row_for(who, state_of(job), to, pool=True) is None:
        raise Refusal(f"{job.get('id')} is {state_of(job)}; {who} takes a pool job that is {', '.join(table.takes(who, to, pool=True))}")


def add(doc: dict, job: dict) -> dict:
    """R1: `job` (everything but the claim) joins the pool, open."""
    if table.row_for("pool-add", None, "open", pool=True) is None:
        raise Refusal("pool-add makes no pool job")
    made = {**job, "claimed": None}
    doc["jobs"].append(made)
    return made


def claim(job: dict, sender: str, now) -> bool:
    """R2: `sender` claims the pool job; `now()` is read only when a claim is made. True when it is a repeat (the same claimant claiming again gets the job again), False
    when this call made the claim. Refuses another claimant's, and a closed one to anyone."""
    claimed = job.get("claimed")
    if state_of(job) == "closed":
        how = claimed["closed"].get("how")
        raise Refusal(f"{job['id']} is closed ({how if isinstance(how, str) else 'ended'} at {claimed['closed'].get('at')}): "
                      "a claimed job that ended is never handed out again")
    if _truthy(claimed):
        by, at = (claimed.get("by"), claimed.get("at")) if isinstance(claimed, dict) else (None, None)
        if by != sender:
            raise Refusal(f"{job['id']} is claimed by {by} ({at})")
        return True
    _row("pool-claim", job, "claimed")
    job["claimed"] = {"by": sender, "at": now()}
    return False


def close(job: dict, how: str, now: str) -> None:
    """R2c: the claimant's job ended as `how`; the claim stays, with when and how it closed."""
    if how not in ENDED:
        raise Refusal(f"a claim closes as done or dropped, not {how!r}")
    _row("pool-close", job, "closed")
    job["claimed"] = {**job["claimed"], "closed": {"at": now, "how": how}}


def reopen(job: dict) -> None:
    """R2d: nobody holds the claim any more; the job is open again."""
    _row("pool-reopen", job, "open")
    job["claimed"] = None


def _epoch(stamp) -> float | None:
    try:
        return calendar.timegm(time.strptime(str(stamp)[:19], "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, OverflowError):
        return None


def judge(job: dict, generation: str | None, claims, *, fresh: bool, now_s: float) -> tuple[str, str | None] | None:
    """What a claimant's state record says to do with a claimed pool job: ("close", how), ("reopen", None) or None.

    `claims` is the record's `claims` field (None: the record has none, or there is no record), `fresh` that the record is within the
    state stream's bound. Both rows need a fresh record that reports claims; closing needs this claim among them, ended; reopening
    needs a day since the claim and none of the reported claims to be this one. A reported claim of this id with no generation (a list
    from before generations) might be this one, and so is not "none"."""
    if state_of(job) != "claimed" or not fresh or not isinstance(claims, list) or not generation:
        return None
    mine = [c for c in claims if isinstance(c, dict) and c.get("id") == job.get("id")]
    for c in mine:
        if c.get("generation") == generation and c.get("state") in ENDED:
            return ("close", c["state"])
    if any(c.get("generation") in (generation, None) for c in mine):
        return None
    taken = _epoch(job["claimed"].get("at")) if isinstance(job["claimed"], dict) else None
    if taken is not None and now_s - taken >= REOPEN_AFTER_S:
        return ("reopen", None)
    return None
