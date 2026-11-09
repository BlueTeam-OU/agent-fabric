"""tools/fabric/work/table.py — agent-fabric ADR-037 rule 14's table, as data.

The table is the one place that says which subsystem may move a job from which state to which, and what must be true when
it does. tests/test_work_table.py reads the ADR's own table and holds this one to it, row for row: a row edited in one place
and not the other fails there. `needs` are names, and what each asks of the world is in `needs` of the jobs side
(tools/fabric/jobsparts/needs.py) or, for the pool, in claims.py; the engine (lifecycle.py) refuses a transition whose row
names a need nobody proved, so a row cannot be made without its needs.

States are of two lists that are not mixed: a job in an agent's list (`JOB_STATES`) and a job in a role's pool (`POOL_STATES`).
`None` as a row's `frm` is "—": the job does not exist in that list yet.
"""
from __future__ import annotations

from dataclasses import dataclass

JOB_STATES = ("queued", "active", "paused", "blocked", "delivered", "done", "dropped")
TERMINAL = ("done", "dropped")
OPEN = tuple(s for s in JOB_STATES if s not in TERMINAL)
POOL_STATES = ("open", "claimed", "closed")


@dataclass(frozen=True)
class Row:
    label: str                       # the label the characterisation suites carry (tests/test_work_lifecycle.py): R1, R2, ...
    frm: frozenset[str] | None       # None: "—", the job is made by this row
    to: str | None                   # None: "any state, as exported" (import)
    who: tuple[str, ...]             # the subsystem(s) that may make it: a verb, an intake or a control-agent half
    needs: tuple[str, ...]
    pool: bool = False               # the row is of a role's pool.json, not of an agent's job list


def _row(label, frm, to, who, needs, pool=False) -> Row:
    return Row(label, None if frm is None else frozenset(frm), to, tuple(who.split()), tuple(needs.split()), pool)


ROWS: tuple[Row, ...] = (
    _row("R1", None, "open", "pool-add", "role title project priority", pool=True),
    _row("R2", ("open",), "claimed", "pool-claim", "binding_holds_role no_other_claimant", pool=True),
    _row("R2b", None, "queued", "pool-claim-landed", "pool_job_by_generation_and_id"),
    _row("R2c", ("claimed",), "closed", "pool-close", "fresh_record_reports_ended", pool=True),
    _row("R2d", ("claimed",), "open", "pool-reopen", "day_passed_fresh_record_holds_none", pool=True),
    _row("R3", None, "queued", "add intake jobs-add", "title_and_project request_once_per_id"),
    _row("R3b", None, None, "import", "empty_list at_most_one_active"),
    _row("R4", ("queued", "paused", "blocked", "delivered"), "active", "start switch",
         "no_other_active no_hold working_copy blockers_cleared"),
    _row("R5", ("active",), "paused", "pause", "reason branch_pushed"),
    _row("R6", ("queued", "active", "paused", "blocked"), "blocked", "block", "blocker_checkable_or_owner_decision"),
    _row("R6b", ("queued", "paused", "blocked"), "blocked", "switch-blocked", "pull_request_added_to_blockers"),
    _row("R7", ("active", "blocked"), "delivered", "deliver", "artifact_open"),
    _row("R8", ("delivered",), "done", "sweep", "done_test"),
    _row("R9", ("active", "delivered"), "done", "done", "done_test_or_no_artifact_reason"),
    _row("R10", ("queued", "active", "paused", "blocked", "delivered"), "dropped", "drop", "reason request_answered"),
)

# The verbs `fabric-jobs` has, by the name its `who` column gives them: `switch` makes two rows (R4 and R6b), told apart by
# the state it moves the job to, so R6b's `who` is a name of its own and not a verb.
VERBS = frozenset(w for r in ROWS if not r.pool for w in r.who)


def row_for(who: str, frm: str | None, to: str | None, *, pool: bool = False) -> Row | None:
    """The row `who` makes from `frm` to `to`, or None: no other transition exists (rule 14)."""
    for r in ROWS:
        if r.pool == pool and who in r.who and r.to == to and (r.frm is None) == (frm is None) and (frm is None or frm in r.frm):
            return r
    return None


def takes(who: str, to: str | None, *, pool: bool = False) -> tuple[str, ...]:
    """The from-states `who` takes toward `to`, in the table's order: what a refusal names."""
    for r in ROWS:
        if r.pool == pool and who in r.who and r.to == to and r.frm is not None:
            return tuple(s for s in (POOL_STATES if pool else JOB_STATES) if s in r.frm)
    return ()
