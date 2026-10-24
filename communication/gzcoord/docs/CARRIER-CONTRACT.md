# The InterWeave carrier: wire framing, receipt and adapter channel

Decisions: agent-fabric ADR-064 (rules 5-10), ADR-033, ADR-041.
This is the contract the carrier (`tools/fabric/gzcoord/carrier/`) and the
two adapters (`send.py`, `inbox.py`) are built against. It adds nothing to
the GZCOORD/1 grammar (ADR-033 rule 1); everything below is carrier to
carrier, or adapter to carrier, on one host.

## 1. Names

| what | value |
|---|---|
| profile name (every account) | `gzcoord` |
| endpoint id leased by the carrier | `gzcoord` |
| client kind presented in the IPC `hello` | `automated-client` |
| roster port range | 47100-47199, loopback only |
| message media type | `application/vnd.agentfabric.gzcoord.v1` |
| compressed message | same, plus `;ce=deflate` (zlib; the only codec) |
| chunk media type | `application/vnd.agentfabric.gzcoord-chunk.v1` |
| receipt media type | `application/vnd.agentfabric.gzcoord-receipt.v1` |

## 2. Payload framing (one direct send = one InterWeave payload)

The payload ceiling is 49152 bytes (InterWeave ADR-0026) and does not rise.

- **plain**: UTF-8 text of the whole GZCoord message, when it fits.
- **compressed**: past the ceiling, zlib (level 9) of the UTF-8 text under
  `;ce=deflate`, when that fits. Decompression is bounded (4 MiB).
- **chunked**: when the compressed form still exceeds the ceiling, N chunks
  (2 <= N <= 16), each its own direct send with its own transport
  `message_id`. A chunk payload is one ASCII JSON header line, `\n`, then a
  slice of the compressed bytes. Header keys, exactly:
  `{"id": <MESSAGE-ID>, "i": <0-based index>, "of": N, "ce": "deflate",
  "sha256": <hex sha256 of the whole compressed body>}`. The header line is
  at most 512 bytes. The receiver holds partial messages in memory (at most
  16 in flight, at most 4 per source PeerId so one roster member cannot hold
  the whole budget, keyed by source PeerId and MESSAGE-ID), reassembles in any
  order, refuses a digest mismatch, and appends to the journal only the
  reassembled message. A restart loses partials; the sender's retry resends
  every chunk.
- A message needing more than 16 chunks (or past 4 MiB) is refused by the
  sender, never truncated.

## 3. Receipt

After the receiving carrier has finished with a message, it sends the sender
one direct message: media type `...gzcoord-receipt.v1`, payload the
MESSAGE-ID as UTF-8 text, to the sender's `gzcoord` endpoint. "Finished"
means: appended to the journal when ADR-041 rule 2 admits it; filtered out
(not addressed to this agent: a `TO-ROLE` it does not hold, a broadcast
filtered as today) otherwise, because the sender sends to every roster
member for `TO-ROLE` and broadcast and would retry for ever to a member
that filters. A message already finished (a retry) is answered with the
receipt again, without a second journal append. A receipt is never a
GZCoord message and never enters a journal or an inbox.

The sender's delivery is done on the receipt of the member it was sent to,
identified by the receipt's authenticated source PeerId mapped through the
roster; a receipt naming a MESSAGE-ID the carrier did not send to that
member is ignored.

## 4. Sender behaviour (ADR-064 rules 6, 7)

- Recipients: `TO <host>/<login>` is the roster member for that login (one
  host, so only this host's members); `TO-ROLE` and `BROADCAST` are every
  other valid roster member. An address with no valid row is not carried
  (relay alone).
- One delivery per (MESSAGE-ID, recipient), its transport `message_id`s
  minted once and kept across retries and restarts in
  `<state>/agents/<login>/interweave/deliveries.jsonl`.
- Retry: 1 s doubling to 5 min, no count limit, until the receipt. A daemon
  refusal that a retry cannot mend (`UnauthorizedPeer`, `InvalidArgument`,
  `PayloadTooLarge`) is recorded on the delivery as blocked and the
  delivery stays outstanding, visible in `status` (section 6).
- Pacing: fan-out is sent one recipient at a time, in roster order. An
  `Overloaded` refusal is retried; the receiving ingress bucket (32 burst,
  then 2 a second per peer) is InterWeave's.

## 5. Receiver behaviour (ADR-064 rules 9, 10, 11)

A delivery event carries the source PeerId. The carrier maps it through the
valid roster to `<this host>/<login>`; a PeerId absent from the roster is
dropped and counted, never admitted. For an admitted-by-roster message:

1. parse the header; verdict = `ok` if `FROM` equals the mapped address,
   else `mismatch`;
2. append one line to the arrival log, `<state>/agents/<login>/
   gzcoord-arrivals.jsonl`: `{"mid", "addressee", "carrier":
   "interweave", "t", "verdict"}` (the relay path writes the same line with
   `"carrier": "relay"` and `"verdict": "unauthenticated"`, before its journal
   append);
3. if addressed to this agent (the inbox's `for_me`), append to the journal
   with carrier `interweave` (`episodic.inbound`); on failure send no
   receipt: the sender retries;
4. send the receipt (section 3).

A `mismatch` message is journaled and shown with the mismatch, never as from
its `FROM` (rule 9). No PeerId, EndpointId, transport `message_id` or port
is ever written into a message, a journal row's metadata or the arrival
log (rule 10).

## 6. Adapter channel

A Unix stream socket at `$XDG_RUNTIME_DIR/agent-fabric/gzcoord-carrier.sock`
(directory 0700, socket 0600, the account's own; the carrier unlinks a stale
one at start). One JSON object per line in, one per line out, then the
connection closes. Request lines are at most 4 MiB.

- `{"op":"send","message_id":<id>,"text":<message>}` ->
  `{"ok":true,"carried":<n recipients>,"queued":<n durably recorded>,
  "posted":<n the daemon accepted so far>}` or `{"ok":false,"error":<why>}`.
  The call returns once the delivery records are fsync'd (within 10 s), not
  on receipt. The send adapter reports `accepted` to the journal when
  `queued == carried > 0`, `failed` when the carrier is unreachable or
  answers `ok:false`, and nothing when `carried == 0`. Provenance is set by
  `episodic.out_final` for the first carrier to accept and left by a later
  accept (rule 7).
- `{"op":"claim","message_id":<id>,"via":"relay"|"interweave"}` ->
  `{"ok":true,"first":true|false,"shown_via":...}`. Each inbox path claims a
  MESSAGE-ID before showing it; only the first claimant shows it. This is
  the only state that decides what a session sees twice (rule 9's re-show
  is a flagged claim below).
- `{"op":"unseen"}` -> `{"ok":true,"records":[{"content","ts","seq":null,
  "message_id","verdict","mismatch_of"}]}`: InterWeave arrivals already
  journaled, not yet claimed, in arrival order. `mismatch_of` names the
  MESSAGE-ID of the relay copy shown earlier when this copy reveals a
  mismatch (the inbox shows it again, flagged, naming that message).
- `{"op":"status"}` -> counts per recipient: outstanding, blocked (with
  code), posted-awaiting-receipt, oldest age.
- `{"op":"abandon","message_id":<id>,"recipient":<login>,"by":<operator>}`
  -> `{"ok":true,"abandoned":true|false}`: the operator's way to end a
  delivery (a re-keyed or removed roster member, rule 3). It is the only
  way a delivery ends without its receipt; the event (who, when, MESSAGE-ID,
  recipient) is appended to the delivery record, and the delivery is moved
  to `delivered.jsonl` marked `abandoned`. The CLI is
  `gzcoord-carrier abandon <message-id> <recipient>`.

Every connection is checked with `SO_PEERCRED` before a byte is read: the
peer's uid must equal the carrier's, else the connection is closed unread
(the directory and socket modes are the default, not the check).

**The relay path fails open.** When the carrier is unreachable (not started,
crashed, journal off) the relay inbox shows a message without a claim: the
relay stays the transport of record (ADR-064 rule 11) and no inbox waits on
the carrier. An InterWeave copy of a message shown that way collapses at the
journal by MESSAGE-ID (ADR-041 rule 5) and is not shown again unless rule 9
flags it.

The inbox adapters feed `unseen` records into the same page flow as relay
records (classification, journal, acknowledgement, rendering), so a
delivery from either carrier takes the same path and the same exit codes.
With `GZCOORD_JOURNAL=off` the adapters do not call the carrier and the
carrier refuses to start (ADR-064 rule 8).

## 7. The carrier process

One per account, under `interweave-client@gzcoord` (InterWeave's client unit
template, `BindsTo=` its daemon): opens the data socket
`$XDG_RUNTIME_DIR/interweave/gzcoord.sock`, claims endpoint `gzcoord` as
kind `automated-client`, negotiates keepalive, never opens the admin
socket, reconnects with 1 s doubling to 30 s (a fresh lease and hello each
time), and drains its event queue as part of holding the lease. It reads the
roster from the account's checkout at the fabric's origin/main and
re-reads it when its file changes. A roster that fails to verify leaves
the carrier running with no recipient, never with the last good one.

The carrier never carries `fabric:control` (ADR-029): the control plane
stays on the relay (ADR-064 rule 12).
