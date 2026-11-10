"""tools/fabric/jobsparts/needs.py — what each row of agent-fabric ADR-037 rule 14 needs of a job, asked of the world.
A part of tools/fabric/jobs.py, whose docstring is the contract.

The owner (tools/fabric/work/lifecycle.py) is pure and refuses a transition whose row names a need nobody proved; this part is
where the needs are asked: git, gh, the journal, the blocker cache, the fleet hold. `prove` answers a row's needs for one job
with a `Proof` the owner then checks and spends. The needs are of two kinds. A WORLD need reads outside the list (a pull request,
a branch on origin, a reply in the journal): it is asked before the list's lock is taken, since every writer waits on that lock,
and the owner refuses the proof if the job changed since (its `seal`). A LOCAL need is cheap and must be true at the moment of
the change (the fleet hold is set under the list's lock): it is asked inside.

A need that cannot be told (gh, git or the journal did not answer) is a refusal, said as such: unknown is never proved.
"""
from __future__ import annotations

from collections.abc import Callable

from fabric_jobs import blockers as bl
from fabric_jobs import settle as st
from fabric_jobs.base import Refused, hold_view, identity, mutate, request_id_of, work
from fabric_jobs.records import find, transition

Proof = work.Proof

WORLD = frozenset({"blockers_cleared", "branch_pushed", "artifact_open", "done_test", "done_test_or_no_artifact_reason", "request_answered"})
LOCAL = frozenset({"no_hold", "working_copy", "reason", "blocker_checkable_or_owner_decision", "pull_request_added_to_blockers"})


def held_refusal(record: dict, what: str) -> str:
    """The answer to a start while the fleet hold is set (ADR-037 rule 13): the hold's own words, and what is not done."""
    return f"{what}: this login is held, {hold_view.words(record)}"


def _no_hold(job: dict, fields: dict, who: str) -> list[str]:
    held = hold_view.read(identity)
    if held:
        raise Refused(held_refusal(held, f"{job['id']} not started"))
    return ["no fleet hold"]


def _working_copy(job: dict, fields: dict, who: str) -> list[str]:
    # A job with no project at all (added in a directory that is no checkout) never had one to find: it starts as it always did.
    if job.get("project") and not job.get("working_copy"):
        raise Refused(f"{job['id']} has no working copy ({job['project']} has none here or beside this one): "
                      f"name one with fabric-jobs project {job['id']} {job['project']} --working-copy DIR")
    return ["a working copy"]


def _blockers_cleared(job: dict, fields: dict, who: str) -> list[str]:
    """Out of `blocked`, every checkable blocker the job waits on has cleared. A job that waits only on an owner's decision has none to
    check: starting it is the agent saying the decision came, and nothing else could."""
    specs = bl.specs_of(job)
    if job["state"] != "blocked" or not specs:
        return []
    cache = bl.refresh(specs, check=True, decide=True)
    if bl.cleared_flag(job, cache) is True:
        return [f"blocker cleared: {', '.join(specs)}"]
    left = "; ".join(f"{s['spec']} {s['state']}" + (f" ({s['detail']})" if s.get("detail") else "") for s in bl.states_of(job, cache) if s["state"] != "cleared")
    raise Refused(f"{job['id']} is still blocked: {left}; a wait that is not over is not started (a blocker that cannot be told is not cleared)")


def _reason(job: dict, fields: dict, who: str) -> list[str]:
    why = " ".join(str(fields.get("reason") or "").split())
    if not why:
        raise Refused(f"{who} needs a reason: fabric-jobs {who} {job['id']} \"<why>\"")
    return [why]


def _branch_pushed(job: dict, fields: dict, who: str) -> list[str]:
    problems: list[str] = []
    evidence = st._pushed(job, problems)
    if problems:
        raise Refused("; ".join(problems))
    return evidence


def _blocker_checkable_or_owner_decision(job: dict, fields: dict, who: str) -> list[str]:
    specs = list(fields.get("blockers") or [])
    on = str(fields.get("blocked_on") or "")
    if specs:
        return [f"blocked on {', '.join(specs)}"]
    if st.OWNER_DECISION.match(on):
        return [f"blocked on {on[:80]}"]
    raise Refused(f"{job['id']} is blocked on free text: name what it waits on with --on pr:<owner/repo>#<n>, request:<message-id>, "
                  "job:<login>/j<n> or clock:<YYYY-MM-DDTHH:MM[:SS]Z> (or --on-request), or state the owner's decision as \"owner: <what is awaited>\"")


def _pull_request_added(job: dict, fields: dict, who: str) -> list[str]:
    added = [s for s in fields.get("blockers") or [] if s.startswith("pr:")]
    if not added:
        raise Refused(f"{job['id']} is blocked on a pull request only by naming it: blockers carry no pr:<owner/repo>#<n>")
    return [f"blocked on {added[-1]}"]


def _artifact_open(job: dict, fields: dict, who: str) -> list[str]:
    problems: list[str] = []
    evidence = st.delivered_evidence(job, problems)
    if problems:
        raise Refused("; ".join(problems))
    return evidence


def _done_test(job: dict, fields: dict, who: str) -> list[str]:
    """R8's need as the sweep asks it, with no one at the job's checkout: a bare #N names no repository. Sweep itself hands in its verdict
    for the whole run (`done_proof`); the `done` verb asks R9's `done_test_or_no_artifact_reason`, which reads a bare #N in the job's own."""
    problems: list[str] = []
    repos, _ = st.artifacts.registry_repos()
    evidence = st.done_test(job, problems, bare_repo=None, repos=repos, named=st.artifacts.project_pattern(list(repos)))
    if not evidence and not problems:
        problems.append(f"{job['id']} has no artifact that landed: deliver one that is merged or on the default branch")
    if problems:
        raise Refused("; ".join(problems))
    return evidence


def _done_test_or_reason(job: dict, fields: dict, who: str) -> list[str]:
    problems: list[str] = []
    evidence = st.done_evidence(job, problems)
    if problems:
        raise Refused("; ".join(problems))
    return evidence


def request_of(job: dict) -> str | None:
    """The REQUEST a job came from: its source's message, or the one its title names (the sender's jobs-add made it by title)."""
    source = job.get("source") or {}
    mid = source.get("message_id") if source.get("kind") == "request" else None
    return str(mid).lower() if mid else request_id_of(str(job.get("title") or ""))


def _request_answered(job: dict, fields: dict, who: str) -> list[str]:
    mid = request_of(job)
    if mid is None:
        return []
    said = st.replied(mid)
    if said is True:
        return [f"REQUEST {mid[:8]} answered"]
    if said is False:
        raise Refused(f"{job['id']} came from REQUEST {mid}, which this login has not answered: answer it first with gzcoord-send "
                      "(a REPLY, or a DECISION, naming it in IN-REPLY-TO), then drop the job with the reason")
    raise Refused(f"could not tell whether REQUEST {mid} was answered ({said})")


NEEDS: dict[str, Callable[[dict, dict, str], list[str]]] = {
    "no_hold": _no_hold,
    "working_copy": _working_copy,
    "blockers_cleared": _blockers_cleared,
    "reason": _reason,
    "branch_pushed": _branch_pushed,
    "blocker_checkable_or_owner_decision": _blocker_checkable_or_owner_decision,
    "pull_request_added_to_blockers": _pull_request_added,
    "artifact_open": _artifact_open,
    "done_test": _done_test,
    "done_test_or_no_artifact_reason": _done_test_or_reason,
    "request_answered": _request_answered,
}


def prove(job: dict, who: str, to: str, fields: dict | None = None, *, asking: frozenset[str] = WORLD | LOCAL) -> Proof:
    """The needs of the row `who` makes from `job`'s state to `to`, those in `asking`, asked of the job as it would be with `fields`
    set on it. Refuses with every need that failed, or when no row takes the job."""
    fields = fields or {}
    row = work.table.row_for(who, job["state"], to)
    if row is None:
        raise work.lifecycle.refusal_for_state(job, who, to)
    candidate = {**job, **{k: v for k, v in fields.items() if v is not None and k != "note"}}
    proof = Proof(job["id"], work.seal(job))
    refused: list[str] = []
    for need in row.needs:
        if need not in asking or need not in NEEDS:
            continue
        try:
            proof.note(need, *NEEDS[need](candidate, fields, who))
        except Refused as e:
            refused.append(str(e))
    if refused:
        raise Refused("\n".join(refused))
    return proof


def combine(world: Proof, local: Proof) -> Proof:
    """The proof the owner is handed: what was asked outside the lock, sealed of the job as it was then, with what was asked inside."""
    return Proof(world.job, world.seal, {**world.held, **local.held})


def done_proof(job: dict, evidence: list[str]) -> Proof:
    """The proof of R8 from a verdict `sweep` already reached for the whole list (one lookup per pull request in the run), sealed of
    the job it was read from."""
    proof = Proof(job["id"], work.seal(job))
    proof.note("done_test", *evidence)
    return proof


def advance(job_id: str, to: str, who: str, fields_of: Callable[[dict], dict]) -> dict:
    """Move one job to `to` as `who`: the row is checked against the job as it is, the world's needs are asked without the list's lock,
    and the change is made under it with the local needs and the owner's own checks. `fields_of(job)` gives the fields the change
    sets, of the job it is given (the one read first, then the one under the lock)."""
    first = find(identity.read_jobs(), job_id)
    world = prove(first, who, to, fields_of(first), asking=WORLD)

    def apply(doc: dict) -> dict:
        job = find(doc, job_id)
        fields = fields_of(job)
        transition(doc, job, to, who, combine(world, prove(job, who, to, fields, asking=LOCAL)), **fields)
        return job
    return mutate(apply)
