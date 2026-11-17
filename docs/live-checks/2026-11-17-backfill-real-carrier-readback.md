# 2026-11-17 — the real-carrier read-back of the backfill (#573)

Gate 1 of `docs/proposals/gzcoord-interweave-only-cutover.md` (row W1,
remainder), asked of python-dev-03 by the owner (REQUEST `01a1e813`, job
j159). One message through the real carrier to a second account; shown once;
then found on the relay after its return; and a `gzcoord-backfill.jsonl` line.
It decides nothing: the gate is the owner's word.

## What was done, and what it is not

python-dev-03 sent `01a1e879-987f-7ff9-b3a2-9b092eedfc04` (a REQUEST) to
python-dev-02 with the relay **made unreachable for that one send** by
pointing the sender's `CLAUDE_BRIDGE_URL` at `http://127.0.0.1:9` (nothing
listens there). This is not a relay outage: the relay was up for everyone else,
and the nft cut (which needs root) was not run. What it does show is the same thing at the sender:
the mirror carries the message while the relay refuses it, and the backfill
posts the relay copy later. What it does not show: a relay outage seen by
the receiver's watch, nor the watch restart past its 15-minute budget. Those
remain the owner's drill.

The sender's `transport-mode.json` reads `relay-record` (the dual run); the receiver's mode was not read, but its ledger order below is the relay-record order.

## The three facts

**1. Shown once.** python-dev-02's own ledgers, quoted by it (REPLY
`01a1e9db`), for this MESSAGE-ID:

```
gzcoord-shown.jsonl
  {"h":"dc0b3b9e…","mid":"01a1e879-…","pending":true,"t":"2026-11-17T08:39:20Z","via":"relay"}
  {"h":"dc0b3b9e…","mid":"01a1e879-…","t":"2026-11-17T08:39:21Z","via":"relay"}
gzcoord-arrivals.jsonl
  {"addressee":"develop-qzapp/python-dev-02","carrier":"interweave","mid":"01a1e879-…","t":"2026-11-17T07:47:35Z","verdict":"ok"}
  {"addressee":"develop-qzapp/python-dev-02","carrier":"relay","mid":"01a1e879-…","t":"2026-11-17T08:39:20Z","verdict":"unauthenticated"}
gzcoord-acks.jsonl
  {"addressee":"develop-qzapp/python-dev-02","mid":"01a1e879-…","ok":true,"t":"2026-11-17T08:39:21Z"}
```

One pending line and its shown line (the ledger's two-step for one showing),
one acknowledgement, `ok`. The InterWeave copy arrived at 07:47:35Z with
verdict `ok`; the relay copy arrived at 08:39:20Z with verdict `unauthenticated`
(by design: `carrier/adapter.py` `relay_arrivals`, "the relay authenticates
nobody").

*What this does not show.* The session read the message at 08:39, after
**both** copies were there (the backfill posted the relay copy at 07:48:20Z).
In relay-record mode the ledger decides the relay copy first
(`transport/dedup.py` `admit`, `_admit_relay`, then `_admit_carrier`), so the
showing is `via: relay` and the InterWeave copy, already decided, was not
shown a second time. That is the once-only property, at the point where the
two copies meet. It is not the property in the order the plan describes — shown
from the carrier first, the relay copy returning afterwards and not shown
again. That order is what the relay-outage drill produces and is left to it.

**2. Found on the relay after its return.** The sender's relay read of the
channel for the MESSAGE-ID (`backfill.Relay.newest()`, filtered on the
MESSAGE-ID in the content) returns the backfill's record:

```
seq 1199518  id f8bc2681-19fe-44ff-9bb0-bdfa8def4eb6  ts 2026-11-17T07:48:20.861870Z  sender develop-qzapp/python-dev-03
```

(a second record with the MESSAGE-ID, seq 1210459, is python-dev-02's reply
quoting it, not a copy of the message.) The relay copy is 45 s after the
InterWeave arrival.

**3. The backfill line.** The sender's `gzcoord-backfill.jsonl`:

```
{"at": "2026-11-17T07:48:20Z", "channel": "gzapp:gzcoord", "delay_s": 45, "mid": "01a1e879-987f-7ff9-b3a2-9b092eedfc04", "outcome": "posted"}
```

The sender's `interweave/deliveries.jsonl` holds `queued`, `posted` and
`receipt` for the same MESSAGE-ID, all at 07:47:35Z: the carrier took it,
delivered it and the receipt came back in the same second.

## Commands

On python-dev-03 (state directory `~/.local/state/agent-fabric/agents/python-dev-03`):

```
grep 01a1e879-987f-7ff9-b3a2-9b092eedfc04 gzcoord-backfill.jsonl interweave/deliveries.jsonl
python3 relaycheck.py 01a1e879-987f-7ff9-b3a2-9b092eedfc04    # a 10-line script over backfill.Relay.newest(); not committed
```

On python-dev-02: `grep <mid>` of `gzcoord-shown.jsonl`, `gzcoord-arrivals.jsonl`,
`gzcoord-acks.jsonl`, sent by it in the REPLY above. I did not read its files;
I quote what it sent.

## Known limits

- The relay was refused at one sender, not cut. The receiver's side of a real
  outage is unproven here.
- Fact 1 is the once-only property with both copies present at read time, as
  said above.
- The two ledgers were read as python-dev-02 reported them; no collection was
  made for this entry.
