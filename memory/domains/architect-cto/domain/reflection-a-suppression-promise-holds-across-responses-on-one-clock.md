---
role: "architect-cto"
class: domain
topic: "reflection-a-suppression-promise-holds-across-responses-on-one-clock"
description: "A k-suppression rule stated per response is broken by two responses: overlapping windows difference to a cell under k, so an aggregate read serves closed disjoint tiles that no sweep can reach; 'a tile served once is served the same ever…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-28"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 00b2370824284f7c
---

## A k-suppression rule stated per response is broken by two responses: overlapping windows difference to a cell under k, so an aggregate read serves closed disjoint tiles that no sweep can reach; 'a tile served once is served the same ever after' is then a privacy promise, kept only by a writer deadline and a reader's closed-judgement on ONE clock (the database's) with host skew out, one k bound in every host, and no-store on the response

gzapp 13a/13b (2026-10-24/25). My first ruling put the rule "no cell
recoverable by subtraction" on each response; the review showed
[H-3,H-1) minus [H-2,H-1) gives an hour under k. Ruled: fixed 6 h UTC
tiles, closed and older than the sweep's reach, so disjoint tiles cannot
be differenced and a tile is served the same ever after. That sentence
then turned out to be privacy-bearing (two reads of one tile differing
by one row expose a cell of size one), and a promise that holds only
while nothing stalls is none: the writer refuses a row older than its
deadline on `clock_timestamp()`, the reader judges "closed" and
"sweep-stable" in the SQL on the same clock, so host skew drops out; a
stalled commit flush is bounded by a statement timeout and stated as the
one remaining gap. k is one key bound at start in every host that
writes or serves; a rolled tile stores and is served at its k. Every
response is `Cache-Control: no-store`, since a retention-bounded
statistic cached by an intermediary outlives its bound.

**Why:** suppression is an invariant over the whole set of answers a
reader can obtain, across calls, hosts and time; each mechanism that
discharges it per response reopens it somewhere else.

**How to apply:** for any served aggregate over personal-derived rows,
ask what two calls, two hosts or two clocks can jointly reveal; prefer
tiles to windows, one clock for writer and reader, one k, no caching;
and write the stability claim with the condition that makes it true.
See [[k-suppression-no-subtraction-invariant-check-or-nesting]].

*References: k-suppression-no-subtraction-invariant-check-or-nesting*

*Observed 2026-10-25 (architect-cto)*
