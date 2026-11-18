# 2026-11-17 — the InterWeave misses and duplicate copies, traced

Gate 1 of `docs/proposals/gzcoord-interweave-only-cutover.md` (row W2, code
half), asked of python-dev-03 by the owner (REQUEST `01a1e813`, job j159).
It gives, for every miss and every duplicate class of
[`2026-11-09-interweave-parity.md`](2026-11-09-interweave-parity.md), a cause
a reviewer can find, and the report of a fresh window. It decides nothing:
the gate is the owner's word.

File and line citations are of the tree at `0a68bf5e` (main after #642),
paths under `tools/fabric/gzcoord/` (`engine.py`, `adapter.py` and `record.py` under its
`carrier/`); the lines have moved on main since.

## What was run

fabric-coordinator collected the evidence as operator
(`fabric-ctl all interweave-evidence --since 2026-10-24T00:00:00Z --until
2026-11-17T07:55Z --out /var/tmp/interweave-evidence-2026-11-17`; 30 of 30
accounts, every row `ok`; the collection itself says it holds arrivals to
07:47:44Z). python-dev-03 cannot run that op: `fabric-ctl` refuses a login that
is not a host operator. Then, from that directory:

```
gzcoord-carrier parity --window 2026-10-24T00:00:00Z 2026-11-17T07:47:44Z --collected <dir>
gzcoord-carrier parity --window 2026-11-16T00:00:00Z 2026-11-17T07:47:44Z --collected <dir>
```

The first is the 11-09 report's window extended to the end of the collection;
the second is the fresh window after 2026-11-16. Both were run twice: with
the installed tool (the numbers of the 11-09 file's method) and with the
branch's `parity.py` (below, "The one defect"). The classes were computed
from the same collection by a script that joins each missed pair to the
senders' `deliveries.jsonl` and `backfills.jsonl` and to the addressees'
`arrivals.jsonl` (not committed; the rule of each class is stated below so a
reviewer can redo it).

| window | tool | relay missed | InterWeave delivered | InterWeave missed | InterWeave duplicate copies |
|---|---|---|---|---|---|
| 10-24 to 11-17 (6 974 pairs) | installed | 26 | 6 033 | 941 | 516 |
| 10-24 to 11-17 | branch (#642) | 26 | 6 033 | 914, and 27 pairs listed apart | 516 |
| 11-16 to 11-17 (345 pairs) | installed | 1 | 344 | 1 | 0 |
| 11-16 to 11-17 | branch | 1 | 344 | 0, and 1 pair listed apart | 0 |

The fresh window's one relay miss is the W1 probe `01a1e879`, sent with the
relay unreachable for that one send: no relay copy existed until the backfill
posted it at 07:48:20Z, after the collection's end. It is the control that
the relay column can fail ([W1](2026-11-17-backfill-real-carrier-readback.md)).

## The 941 InterWeave misses

Each is a pair (MESSAGE-ID, addressee) with no InterWeave copy. The classes
are exclusive and applied in this order; they sum to 941.

| class | pairs | cause | where |
|---|---|---|---|
| A. the sender's own copy of its broadcast | 27 (12 of the 13 after 10-27; 1 of the fresh window) | The carrier sends a broadcast or TO-ROLE to every roster member but its sender; the relay returns the sender its own copy, which the relay column then expects an InterWeave twin of. **Not a miss**: the pair is the sender and the message it sent. The sender is known because it recorded deliveries to others for the same MESSAGE-ID (the account holding the 29 `done` rows is the addressee). | `carrier/engine.py` `Carrier.recipients` (lines 135-144: `others` drops `row["agent_id"] == me.agent_id`); ADR-064 rule 6 and CARRIER-CONTRACT.md §4 ("every other valid roster member"). Defect in the report, fixed (below) |
| B. the rollback drill | 6 | All six were sent between `interweave-stop` (2026-11-12T09:33:54Z) and `interweave-start` (10:09:36Z): no carrier ran on any account. The sender's backfill log says `relay-took-send` for each. Not a miss: the drill is what stops the carrier ([drills record](2026-11-12-interweave-drills.md)). | `adapter.py` `Adapter.post_result` returns `absent` when the socket is missing (line 99-100); the mirror then carries on with the relay (`send.py` 641-651) |
| C. the addressee was not receiving by InterWeave yet | 902 (906 on 10-24 to 10-26 in the 11-09 report, less the four that are class E or F: class B's pairs were all sent on 11-12) | The message is older than the addressee's first InterWeave arrival in the collection. The 30 accounts' first InterWeave arrivals run from 2026-10-25T19:23:29Z (python-dev-03) to 2026-10-27T07:05:40Z; the last carrier to start receiving is the staged rollout's end. Before it, a sender's roster had no row for the addressee, or the addressee's carrier was not running. Not a miss of the carrier: the dual run had not reached that account. Why a given sender recorded none (no row, carrier off) is the fact the 11-09 report called "not traced to rollout dates": the roster's admission date per account is not in the collection. | `engine.py` `Carrier.refresh_roster` (110-129) and `recipients` (135-144); `adapter.py` `Post("not-carried")` (125) |
| E. the sender's carrier had not delivered yet | 2 | user to python-dev-02, 10-25 19:33 and 19:56: the sender's first delivery record of any kind is 10-26T05:31:09Z. The same staged start, seen from the sender. | as C |
| F. unexplained by the collection | 4 | 10-25 19:29 and 19:46, python-dev-02 to python-dev-03 (both accounts were receiving since 19:23; the 0.1.0 exercise of [10-25](2026-10-25-interweave-two-accounts.md) ran its carriers as processes, not units, that evening); 10-28 11:38 architect-cto-01 to p2p-network-dev-02; 11-13 06:05 rust-ui-dev-02 to architect-cto-01. In each the sender's backfill log says `relay-took-send` and the addressee was receiving by InterWeave before and after. | below |

**What F cannot be told from the collection, and why.** A sender whose carrier
does not accept a send leaves the reason on stderr and nowhere durable:
`Adapter._ask` prints "the InterWeave carrier did not answer" or "refused"
(`adapter.py` 71-88), `post_result` returns `absent` / `not-carried` / `failed`
(96-126), and `send.py`'s `via_mirrors` (641-657) keeps only the accepted ones
(journal state `accepted`, carrier named), nothing for the others. So "no
roster row, carrier off or sender had none" (the report's cause text) is three
causes the evidence cannot separate, and the carrier's own journal for those
days is not kept (`journalctl --user -u interweave-client@gzcoord` on
python-dev-03 answers "No entries" for the unit at all). Two of the four
(`01a1748a`, `01a17499`) fall inside the 0.1.0 exercise's evening; the other
two have no record. They are the carrier failing open as it is designed to
(ADR-064: the relay carries on), four in 6 974 pairs, none since 11-13, none
in the fresh window. Whether to make that refusal durable (a line in the
sender's state beside `gzcoord-sent.jsonl`, collected by `interweave-evidence`)
so the next report names the cause is a change to a collected file set, the
coordinator's; I raise it, I do not make it here.

## The one defect: class A in the report

`parity.compute` expected an InterWeave copy for every pair that has a relay
copy, including the pair whose addressee is the message's own sender. It now
lists those apart ("Not counted as InterWeave misses: N pair(s) …") and keeps
the pair a miss when the sender recorded no delivery for it (the control: a
member the sender recorded nothing for is still a miss). It also adds, to a
miss with no sender record, the addressee's first InterWeave arrival in the
collection when it is later than the message, so class C reads from the
report without a script (`carrier/parity.py` `compute`, `_cause`;
`tests/test_gzcoord_carrier_parity.py`). Four mutations (the self test
inverted, removed, the lateness comparison flipped, the no-arrival branch
removed) each fail the suite.

Relay-side effect of class A for a reader: the relay shows a sender its own
broadcast, InterWeave does not. A sender no longer sees its own broadcast
once the relay is gone; the shown ledger of the sender showed those relay
copies (`gzcoord-shown.jsonl` of `user` for `01a18c45`). Nothing reads it as
news, and no code path depends on it, but it is a difference the cutover plan
does not list.

## The 516 duplicate copies

All 516 extra copies belong to 38 pairs and to messages sent on **2026-10-30**,
10:05 to 10:14Z; the fresh window has none and the window after 10-30 has no
other. 477 are the owner's broadcast `01a18c45` (fabric d941d5b0 on every
account; its text says "the journal moves to schema 3 the first time new code
opens it", and that a watch still running the old code ends with exit 6, "the
delivery was not acknowledged and comes again"): 28 of 29 addressees hold 18
copies from 10:05:34Z: the first retry after 333 s, the second after 384 s, then
every 300 s (`record.py` `BACKOFF_CAP`, line 44; `backoff`, 58-60), the last
of each account at 11:29:46Z to 11:31:54Z, account by account. Two more messages of
10:xx hold 16 copies each (32 extras), and eight pairs two copies (gap about
510 s).

**Cause**: one mechanism, by design, and not a duplicate seen by anyone.
`Carrier.finish` appends the arrival line **before** the journal write
(`engine.py` 363) and, when the journal refuses, returns without a receipt
(`except Exception … not_journaled`, 366-372). The sender's `send_due` posts
the same message again at each backoff step until the receipt comes
(`engine.py` 246-287, `retry_after` at 286). A receiving carrier whose journal
the new code had moved to schema 3 refused every copy until its carrier was
restarted; the staggered 11:29 to 11:31 ends are those restarts. The arrival
log therefore lists one line per refused copy, which the report counts as a
duplicate copy; none was journaled, spooled or shown (`spool.keep` comes after
the journal), so no session saw one twice, and the journal collapses repeats
by MESSAGE-ID in any case. The relay copy of each carried the message to
the session meanwhile.

*What is inferred*: that the refusal was the schema's. It is what the
message, the timing (all accounts, the same hour, ending when each restarted)
and `finish`'s failure path say together; the carriers' own logs for that day
are gone (see F). *What this means for carrier-only*: with no relay copy, a
carrier whose journal a newer fabric has migrated holds every arrival
unreceipted and unshown until it restarts — here 84 minutes — and nothing
tells the sender or the operator. That is not a defect of the carrier code
(it refuses rather than loses, and the sender keeps retrying), but it is a
hole in an upgrade that moves the journal's schema, and it belongs to
whoever owns the upgrade order (fabric-coordinator): the carrier unit should
restart in the same step that moves the schema, or `fabric-status` should name
`not_journaled` (`Counters`, `engine.py` 67-76), which is already counted.

## What the fresh report lacks

Only what the drill supplies: the relay-outage drill with the watch restart
inside it past the watch's 15-minute budget, and the shown-once and
acknowledgement read of the relay copy's return. No miss or duplicate of the
fresh window is unexplained.
