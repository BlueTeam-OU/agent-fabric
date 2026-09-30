# ADR-036 — Sustainable operation: shared resources, and cost per verified result beside supervision per verified result

**Date:** 2026-09-27
**Status:** Accepted
**Ratified:** owner, 2026-09-29, "Accept", answering fabric-coordinator's question closing the Proposed records; carried by the pull request that marks them Accepted
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** how the fabric treats its finite means — host resources, model spend and usage windows, prompt and context budgets — as one account, and how it measures cost per verified result (`tools/fabric/results.py`, `fabric-results`)
**Pillar:** P7

## 1. Context and Problem

ADR-000's P7: the organization runs on finite means — model budgets and
usage windows, prompt and context budgets, a host's disk and memory, the
owner's attention. Its direction: a cost per verified result is measured
beside the supervision per verified result; growth is judged by
capability per unit of spend, not by the number of agents; consuming a
shared resource is a cooperative act, like any other commitment.

The pieces that exist were each built after an incident, and each is
recorded where it lives:

- **Host resources.** The host died under load on 2026-09-19 and
  2026-09-25 (`docs/live-checks/2026-09-19-develop-qzapp-crash.md`,
  `docs/live-checks/2026-09-25-develop-qzapp-crash.md`). A memory-heavy
  job takes the host lease `heavy`, and fleet installs queue on
  `claude-install` (ADR-010, ADR-009); the account quota and a fleet lease
  are not built (ADR-010 §2). A test run leaves nothing it did not find
  (ADR-021). The control agent's `host` op reads memory, disks, leases
  and the largest processes (ADR-029).
- **Prompt and context.** The launch prompt has a character ceiling and
  the shared prompt templates a token budget, both checked before a
  launch fails on them (ADR-002, ADR-017); memory slices carry a
  per-slice token budget in lint.
- **Model spend and windows.** Each Claude account's five-hour and weekly
  windows are read by the coordinator's observer (`fabric-ctl <login>
  accounts`, ADR-031; `bin/fabric-usage` as the fallback); a login's own
  spend per model is read from its session records by `fabric-ctl
  <login|all> tokens`, direct-path and broker models summed apart, with
  an input-token-equivalent proxy (ADR-029). Broker spend is reported by
  the provider per key, so per agent; the fabric reads none of it.
- **Supervision.** ADR-026 proposes supervision per verified result and
  defines a verified result.

Nothing puts these together. No number says what a verified result
cost, and the only fleet-wide reading of spend is a window's percentage
per Claude account, which says how close the fleet is to a limit, not
what the limit bought.

## 2. Decision

**The fabric measures cost per verified result, beside
supervision per verified result, and treats each shared resource as a
commitment.**

- **Cost per verified result** is the model spend attributable to a
  period's verified results, divided by their number — the denominator
  and its definition are ADR-026's, shared. Spend is counted in the
  units the fabric can read without estimating: input-token equivalents
  from each login's own records on the direct path, and the provider's
  per-key spend on the broker path, reported apart, never summed into one
  currency.
- It is read as a trend beside supervision per verified result and the
  verified-result rate, never as a target, never per agent.
- **Growth is judged by capability per unit of spend**: a change that
  adds agents, tiers or context is argued by what it does to cost per
  verified result, not by how much more work it starts.
- **A shared resource is a commitment.** A host lease, a usage window, a
  prompt budget and the owner's attention are each spent as a
  cooperative act: taken for a stated job, released when it ends, and
  visible to those who share it — as the host lease already is.

## 3. Alternatives Considered

- **Spend per agent, or per period.** Rejected: it rewards doing less, and
  per-agent numbers invite optimising one's own row (the same reasoning
  as ADR-026 §3).
- **One currency for all spend.** Rejected: a subscription window and a
  metered key are different kinds of cost; converting one into the other
  would be an estimate presented as a measurement. They are reported
  side by side.
- **Budgets per agent enforced by the fabric.** Not now: nothing measures
  the cost of a result yet, so a budget would be a guess. It is what the
  measure would make possible.

## 4. Rationale

A cost read beside the supervision measure and the verification rate
makes the three hard to game together: fewer results with less spend is
not progress, and neither is more spend with less supervision if the
verified-result rate falls. Counting only what the fabric already reads
keeps the number auditable and keeps it from inventing precision the
sources do not have.

## 5. Binding Rules

1. Cost per verified result is published per period, per repository and
   in total, with its numerator, its denominator and the verified-result
   rate beside it, and the supervision measure of ADR-026 on the same
   periods.
2. The denominator is ADR-026's verified result; a change to that
   definition changes both measures and recomputes both series.
3. Direct-path spend is counted from the logins' own session records
   (`tokens`, input-token equivalents); broker spend from the provider's
   per-key report; the two are never converted into each other.
4. The number is never a target, never compared between agents, and
   never a reason to skip verification or a review.
5. A proposal that adds agents, a heavier tier, or context to every
   session states its expected effect on cost per verified result.
6. A job that takes a shared host resource takes its lease for the job
   and names itself (`fabric-lease --label`), as ADR-010 §5 rules 9–11
   already require of memory-heavy jobs.

## 6. Consequences

- `fabric-results` reads the spend (`fabric-ctl all tokens`) over the
  period its results were merged in, and divides it by verified results
  only across every registered project (`--all`), because nothing yet
  attributes a login's spend to the pull request it produced. The session records carry the spend; the
  link from a session to a result would come from the branch and the
  commits, and is not built.
- Broker spend needs a reader of the provider's per-key report, which the
  fabric does not have.
- What a Claude account spends off the fleet's hosts is not visible, so
  direct-path cost is the fleet's visible part only.

## 7. Future Evolution

**The first concrete step:** a read-only report that joins, for each PR
merged in a period, the `tokens` records of the sessions whose branch
produced it — found by branch name and commit time in each login's own
records, over the control plane — and prints input-token equivalents per
merged PR, with the merged-PR count and ADR-026's verified-result count
beside it. **What would show it worked:** the report accounts for most
of the period's direct-path spend (the unattributed share printed, and
small), and two consecutive periods can be compared.

Then: the broker reader; the account quota of ADR-010 when an incident
gives it a shape; and, once the series exist, the owner's decision on
whether the definitions hold.

## 8. Decision Status

Accepted and in force.

## References

- ADR-000 §5, P7 (Today, Direction).
- ADR-002 and ADR-017 (the prompt ceiling), ADR-009 (`claude-install`),
  ADR-010 (hosts, leases, quota), ADR-021 (a test run leaves nothing),
  ADR-026 (supervision per verified result), ADR-029 (`host`, `tokens`),
  ADR-031 (usage windows).
- `bin/fabric-lease`, `bin/fabric-usage`, `runtime/control/ops.mjs`
  (`tokens`, `equivalent`), `tools/fabric/launch_prompt.py`
  (`MAX_CHARS`), `tools/fabric/lint.py` (the template and slice budgets).
