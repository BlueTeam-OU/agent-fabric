# ADR-046 — Fleet views: the fleet's state read on demand, read-only

**Date:** 2026-10-09
**Status:** Proposed
**Decision Makers:** the owner (the views, the two stages, the layout); drafted by fabric-coordinator
**Scope:** `tools/fabric/fleet.py`, `tools/fabric/fleet_proc.py`, `bin/fabric-fleet`; the views in the herdr fork (`fleet-deck/fabric_view.py`, its plugin manifest); what a view may read and do
**Pillar:** P1

## 1. Context and Problem

Fleet Deck, the operator's console (the herdr fork), shows each account's
session state and, in a status pane, its own status, jobs and pull
requests. The owner wants the fleet in view as a fleet and per agent:
resources, jobs open and done, what each agent is doing, a side-by-side
comparison, and reports such as a Gantt of plan steps (ADR-047), with the
data fetched when a view is opened or looked at, never polled in the
background.

The control plane answers most of it already (ADR-029: `host`, `disk`,
`tokens`, `usage`, `accounts`, `jobs`, `presence`, the state stream), but
not per-login CPU or memory, not a closed job or a job's times, and no new
operation can be added before Wave 8's cutover deletes the Node code
(ADR-040 §7).

## 2. Decision

The fleet's state is read by one module, `tools/fabric/fleet.py`, and
drawn by views that run in herdr panes. A view fetches when it opens and
while it has focus, and stops when focus leaves. The views only read. Until
the cutover the module reads what exists, through two named bridges; after
it, new control-plane operations replace the bridges without changing what
a view receives.

## 3. Alternatives Considered

- **A collector that samples the fleet all the time** and keeps a history
  for the views. Rejected: a standing load on every account for a screen
  that is mostly closed, and the owner asked for reads on demand.
- **The views calling `fabric-ctl` themselves.** Rejected: several views
  would each fan out to every account; one module with a shared cache
  answers them all and keeps the sources in one place.
- **Waiting for the cutover** to build the views once with new operations.
  Rejected by the owner: the views come now, on the data that exists.

## 4. Rationale

The cost of a read is paid when someone looks: a pane's process lives as
long as the pane, and terminal focus reporting tells it when it is looked
at. Every account is on one host today, so `/proc` gives per-login CPU and
memory without a new operation; a second host needs Stage 2's operation,
which the source list absorbs. Tagging every value with its source keeps a
bridge visible rather than silent.

## 5. Binding Rules

1. `tools/fabric/fleet.py` is the one reader of the fleet's state for a
   view: a record per placed account, every value carrying its source
   (`src`) and the time it was read (`at`). A section that cannot be read
   is a value with its failure, never a missing account.
2. Sections have a cost class and a time to live: per-login resources,
   states and presence (cheapest); open jobs, usage, host and fabric;
   pull requests, closed jobs and accounts (read only when a view shows
   them); tokens and disk (read only when asked for). A shared cache under
   `$XDG_RUNTIME_DIR/fabric-fleet/`, mode 0600, serves a fresh entry to
   every view.
3. A view fetches when it opens, and refreshes only while it has focus
   (terminal focus reporting); it stops when focus leaves, and `r`
   refetches. Fleet Deck itself adds no polling for the views.
4. A view only reads. It calls no herdr socket (`server.socket_access`
   refuses a pane's process), sends no signed action (ADR-029 rule 5), and
   reads no process environment and no session transcript.
5. Two bridges stand until the operations that replace them exist, and
   are named in every value they produce: per-login CPU, memory and swap
   from `/proc` on the host the views run on (`proc-local`); closed jobs
   and their times through `fabric-host <host> run --as <login> --
   fabric-jobs list --all --json` (`hostexec`), the fallback ADR-029 keeps
   for a host whose control agents are down, used here read-only.
6. After the cutover (ADR-040 §7), `jobs --all` and `resources` operations
   replace the bridges as the first source of their sections; the bridges
   stay as the fallback for an account whose control agent does not
   answer. A view's record keeps its shape; only `src` changes.
7. A comparison across agents shows resources and job counts, as
   operational facts, never `fabric-results`' verified work (ADR-026 §5
   rule 4).

## 6. Consequences

- Per-login resources are visible today on the host the deck runs on, and
  nowhere else until Stage 2.
- A closed job is read with the operator's sudo through the host executor
  until Stage 2; every such value says so.
- The views are the herdr fork's (rust-ui-dev); the module is agent-fabric's.

## 7. Future Evolution

- The `jobs --all` and `resources` operations, after the cutover.
- Views of other hosts, once `resources` answers from each daemon.

## 8. Decision Status

Proposed: the owner approved the plan in the coordinator's session; this
record awaits the owner's acceptance in its pull request.

## References

- ADR-026 (the results number), ADR-029 (the control plane), ADR-040 §7
  (Wave 8, the frozen wire), ADR-047 (plans).
- `docs/fleet-deck/tab-states.md` (the deck's tabs).
