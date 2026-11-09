"""tools/fabric/work/lifecycle.py — the only code that changes a job's `state` in an agent's job list (agent-fabric ADR-037
rule 14, ADR-067). A job is made queued by `create`, moved by `transition`, and an exported list is filled in by `fill`;
nothing else writes a `state` into a list, and tools/fabric/work_writes.py is the lint that says so.

`transition` takes the row of the table (table.py) that `who` makes from the job's state to `to`, or refuses: a verb that is
not in the table for that state makes no transition, however the caller got there. The row's needs are not asked here (they
read git, gh, the journal and the clock, and the list's lock is every writer's): the caller asks them first, with
`needs.prove` (tools/fabric/jobsparts/needs.py), and hands over the `Proof`. What this module checks, under the lock, is that
the proof covers every need the row names, and that it was made of the job as it is now (its `seal`), so a proof read of one
job state is never spent on another. The needs it can see in the document it proves itself: one active job at a time.

Pure: no I/O, a clock and a session id the caller gives, so that the control agent's half of the pool (claims.py) and the
tests load it without the job tool.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from fabric_work import table
from fabric_work.request_title import request_id_of


class Refusal(Exception):
    """A change the list does not allow; the message is the whole answer."""


def seal(job: dict) -> tuple:
    """What a proof of a job's needs was made of: the fields the needs read. A job edited between the proof and the change (another
    session's deliver, a retract) no longer matches it."""
    return (job["state"], tuple(job.get("artifacts") or ()), tuple(job.get("blockers") or ()), job.get("blocked_on"),
            job.get("branch"), job.get("worktree"), job.get("working_copy"))


@dataclass
class Proof:
    """What was found true of one job for one row: `held` maps each need the row names to what showed it (a line for the log)."""
    job: str
    seal: tuple
    held: dict[str, list[str]] = field(default_factory=dict)

    def note(self, need: str, *evidence: str) -> None:
        self.held[need] = list(evidence)


# Needs the document itself answers, under the lock, so that no caller can leave them out.
ENGINE_NEEDS = frozenset({"no_other_active"})
# The needs of the rows that make or fill a list rather than move a job: `create` and `fill` check them where the row is made.
CREATE_NEEDS = frozenset({"title_and_project", "request_once_per_id", "empty_list", "at_most_one_active", "pool_job_by_generation_and_id"})


def active(doc: dict) -> dict | None:
    return next((j for j in doc["jobs"] if j["state"] == "active"), None)


def listed(states: tuple[str, ...]) -> str:
    """"queued, paused or blocked": the states a verb takes, as a refusal says them."""
    return f"{', '.join(states[:-1])} or {states[-1]}" if len(states) > 1 else "".join(states)


def refusal_for_state(job: dict, who: str, to: str) -> Refusal:
    if job["state"] in table.TERMINAL:
        return Refusal(f"{job['id']} is {job['state']}; a closed job is not reopened — add a new one")
    takes = table.takes(who, to)
    if not takes:
        return Refusal(f"{who} makes no transition to {to}")
    return Refusal(f"{job['id']} is {job['state']}; {who} takes a job that is {listed(takes)}")


def transition(doc: dict, job: dict, to: str, who: str, proof: Proof | None, *, now: str, session: str | None = None, **fields) -> None:
    """Move `job` of the list `doc` to `to` as `who`, with `fields` set on it; `note` goes to the log entry instead."""
    row = table.row_for(who, job["state"], to)
    if row is None:
        raise refusal_for_state(job, who, to)
    unproved = [n for n in row.needs if n not in ENGINE_NEEDS and (proof is None or n not in proof.held)]
    if unproved:
        raise Refusal(f"{who} {job['id']}: not proved: {', '.join(unproved)}")
    if proof is not None and (proof.job != job["id"] or proof.seal != seal(job)):
        raise Refusal(f"{job['id']} changed while {who} was checked: run it again")
    if to == "active":
        current = active(doc)
        if current and current["id"] != job["id"]:
            raise Refusal(f"{current['id']} is active ({current['title']}); deliver, block, finish or drop "
                          "it first — one job is active at a time")
    if job["state"] == "active":
        # Only the no-session-id fallback of `next` reads this.
        doc["last"] = job["id"]
    # A wait ends with the state; a new `block` replaces the whole wait, so free text alone leaves no checkable blocker behind, while the
    # switch that adds a pull request to a blocked job keeps what it waited on (R6b: added, never substituted).
    if to != "blocked" or who == "block":
        job.pop("waits_on", None)
        job.pop("blockers", None)
    if to == "active":
        job.pop("reason", None)         # a paused job's why belongs to the pause; an active job has none
    # Entering or leaving `active`, not only entering: a session launched with its job already active never activates it, and is
    # known by finishing it. A drop or block of a job that was never active here is no work done.
    touches_active = to == "active" or job["state"] == "active"
    job["state"] = to
    job["updated"] = now
    entry = {"at": now, "state": to, **({"note": fields["note"]} if fields.get("note") else {})}
    if touches_active and session:
        entry["session"] = session
    job.setdefault("log", []).append(entry)
    for key, value in fields.items():
        if key != "note" and value is not None:
            job[key] = value
    # The record named two places for one job's work, and a relaunch followed the older (j474: 348 commits behind): where a job is
    # given a worktree, that is its working copy, in the same write.
    if fields.get("worktree"):
        job["working_copy"] = fields["worktree"]


def create(doc: dict, who: str, fields: dict, *, now: str) -> dict:
    """A job made `queued` by `who` (add, the inbox's intake, the control agent's jobs-add, or the claimant's pool-claim) and put at
    the end of `doc`; `fields` are everything but the id, the state and the times. The ids are the list's counter's."""
    row = table.row_for(who, None, "queued")
    if row is None:
        raise Refusal(f"{who} makes no job")
    if not str(fields.get("title") or "").strip():
        raise Refusal("a job needs a title")
    source = fields.get("source") if isinstance(fields.get("source"), dict) else {}
    if who == "pool-claim-landed" and (source.get("kind") != "pool" or not isinstance(source.get("pool_id"), str)):
        raise Refusal("a job claimed from a pool names the pool job (source.pool_id)")
    # Once per id (R3): by whichever path the REQUEST came, a job holding the message as its source or naming it in its title is the job.
    # The paths look first and answer with the job they found; this is the owner refusing the second one that slips by.
    mid = source.get("message_id") or request_id_of(str(fields["title"]))
    if mid and any((j.get("source") or {}).get("message_id") == mid or request_id_of(str(j.get("title", ""))) == mid for j in doc["jobs"]):
        raise Refusal(f"REQUEST {mid} is already a job on this list")
    doc["seq"] = int(doc.get("seq", 0)) + 1
    job = {"id": f"j{doc['seq']}", **{k: v for k, v in fields.items() if k not in ("state", "created", "updated", "log")},
           "state": "queued", "created": now, "updated": now, "log": [{"at": now, "state": "queued"}]}
    doc["jobs"].append(job)
    return job


def fill(current: dict, imported: dict) -> None:
    """A list moved from another host, every state and id as exported, into an empty one (R3b): not a job started."""
    if table.row_for("import", None, None) is None:
        raise Refusal("import makes no list")
    if current["jobs"] or current.get("seq"):
        raise Refusal(f"this list is not empty ({len(current['jobs'])} jobs, next id j{int(current.get('seq', 0)) + 1}); import fills an empty one only")
    if sum(j["state"] == "active" for j in imported["jobs"]) > 1:
        raise Refusal("the document has more than one active job")
    current["seq"], current["jobs"] = imported["seq"], imported["jobs"]
    if imported.get("last") is not None:
        current["last"] = imported["last"]
