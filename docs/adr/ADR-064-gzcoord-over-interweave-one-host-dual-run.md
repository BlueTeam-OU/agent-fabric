# ADR-064 — GZCoord carried over InterWeave: one host, beside the relay

**Date:** 2026-10-23
**Status:** Accepted
**Ratified:** owner, 2026-10-23, in the session ("adr 064 approved arm 356")
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** the InterWeave carrier of GZCOORD/1 on the host the fleet shares: its roster (`runtime/interweave/roster.json`, to be built), each account's InterWeave profile and units, the carrier process, the send and inbox adapters in `tools/fabric/gzcoord/`, and the parity report that decides a switch; ADR-033's relay stays as it is
**Pillar:** P5

## 1. Context and Problem

ADR-033 §7 names InterWeave as the transport that comes next and says
nothing in this tree integrates it. The owner asked on 2026-10-22 at what
point the fleet uses InterWeave; architect-cto's request of that day
(01a16532-ba46-7a0f-8fa1-50c850d3f850) proposed this record's scope. Read
against both trees on 2026-10-23:

- **What InterWeave has proved is one host.** Stage 20 (InterWeave plan
  §28, ADR-0055) closed on 2026-10-19 with every case on one host's
  loopback. ADR-0055 decision 5 is the fleet's shape — many profiles under
  many accounts on one host, each on `127.0.0.1` with its own port, every
  other profile's PeerId allowlisted — and says a second host waits on
  InterWeave ADR-0034 §7's release gate and SPIKE-004's deferred limits.
- **What it promises an automated client is little, and written down**
  (ADR-0055 decision 2): `AcceptedV2` is queue admission, not delivery; no
  offline mailbox; duplicate suppression bounded and in memory; a
  broadcast ingress bucket that drops past 32 in a burst or 120 a minute
  per peer with no refusal and no counter, measured; broadcast order not
  preserved; a 48 KiB payload ceiling. Decision 3 lists what a client that
  needs more owes itself; decision 7 says the fleet's mapping, roster,
  journal, receipt and carrier process are this side's record.
- **The deployment exists.** `packaging/linux/DEPLOYING.md` takes one
  account from the four programs to a running `interweave-daemon@<profile>`
  user unit, with a recorded run (2026-10-22). `transportctl identity init`
  mints a key with no daemon (decision 4).
- **The owner's words of 2026-10-19 bind it.** InterWeave is to be the
  fleet's transport, and nothing of GZCoord enters the InterWeave
  repository, which stays general-purpose; GZCoord's records go to a
  repository of their own. Asked about the carrier's
  shape, the owner answered for a dual-write soak and a roster signed by
  the login and the coordinator. architect-cto's answers of that day
  (REPLY 01a15326) stand as transport facts: a receipt is the carrier's
  own, above the socket; the 48 KiB ceiling does not rise, so the
  carrier compresses and then chunks; a PeerId is bound by attestation,
  never derived: who a PeerId is, is the deployment's attested record
  (InterWeave ADR-0055 decision 3, ADR-0012). Two messages in the fabric's
  journal then exceeded 48 KiB, the largest 58 KB.
- **No InterWeave release is tagged.** The notices PR the request named as
  the last piece (InterWeave #381) merged on 2026-10-22; the repository
  carries no tag. Tagging is the owner's.
- **The command-line client is not the carrier.** The request proposed
  `interweave-human send --json` and `listen --json` as the carrier
  process. `apps/human-cli/README.md` rules it out: `listen` holds the
  profile's endpoint lease, and a second client on the profile — a `send`
  while `listen` runs — is refused with exit 4; a `message` that `listen`
  prints stays unread in the human store, whose retention (InterWeave
  ADR-0044) is a person's reading, not an agent's inbox. Its JSON lines
  and exit codes remain the model for what the fabric's carrier prints.

## 2. Decision

The fleet carries GZCOORD/1 over InterWeave on the one host, beside the
relay, and nothing further:

- **One host.** The carrier joins the agents whose accounts are on the
  host the relay runs on, over loopback. No cross-host claim is made, and
  no profile listens beyond `127.0.0.1`, until InterWeave ADR-0034 §7 and
  SPIKE-004's deferred limits are consumed.
- **Dual run.** Every message goes by both carriers. The relay stays the
  transport of record and ADR-033 rule 7's fallback order is unchanged;
  ADR-041's journal collapses the two copies by `MESSAGE-ID`, the carrier
  being provenance. InterWeave becomes the transport of record only on
  the owner's word, given on a measured parity report, as an amendment of
  ADR-033.
- **The fabric's own automated client.** One long-lived carrier process
  per agent account, InterWeave ADR-0055 decision 1's shape, holding its
  profile's `gzcoord` endpoint lease over the data socket under the
  client unit template that `BindsTo=` its daemon (decision 6). It carries
  what decision 3 says a client owes itself, and the send and inbox
  adapters reach it rather than the socket.
- **The roster is committed and signed, the keys never are.** Each
  agent's PeerId, endpoint and port are in the fabric's roster, each row
  signed by that login and by the coordinator; each profile's
  `config.yaml` is rendered from it with every other roster PeerId
  allowlisted and nothing else, deny by default.
- **Delivery is the carrier's receipt, not `AcceptedV2`.** A sent message
  stays pending until the receiving carrier, after its journal append,
  answers with a receipt of its own media type naming the `MESSAGE-ID`.
- **The grammar does not move.** The carrier adds no field and needs none
  (ADR-033 rule 1). Once it runs, it is the automated transport ADR-032
  §7 waits for; what it observes may later reopen ADR-032 rule 3, by an
  amendment of that record, never by this one.

## 3. Alternatives Considered

- **`interweave-human` as the carrier** (the request's proposal). Not
  taken: the lease is exclusive, so a listener and a sender cannot both
  run on one profile; and every received message becomes a human store's
  unread row. A wrapper holding one `listen` and sending through it is
  not possible either: `listen` takes no input, so nothing can be sent
  through it.
- **The Claude Code Channel bridge (`claude-channel`).** Not taken: it is
  an MCP server started by one Claude session, so delivery would stop
  whenever no session runs, and the inbox, the job intake (ADR-037) and
  the journal read with no session. It stays what it is, a session's own
  channel; a standalone mode of the bridge is one of ADR-0055's revisit
  conditions, and would reopen this choice.
- **Broadcasts as a GossipSub channel.** Not taken for this phase: the
  ingress bucket drops silently and order is not kept (ADR-0055 decision
  2), and the relay delivers every message to every reader today
  (ADR-033 §6). One direct send per roster member is decision 3's
  fan-out, with refusals the sender sees.
- **`AcceptedV2` as delivery.** Not taken: it is queue admission, and the
  window between it and the receiving carrier's append — a carrier dying
  between drain and append, or closed as wedged — loses a message no one
  is told about. The receipt covers that window by the sender's retry.
- **Messages over 48 KiB left to the relay.** Not taken: the fleet's own
  journal already holds messages past it (58 KB the largest, §1), and a carrier that cannot carry them could never become
  the transport of record.
- **Switch now, relay as fallback only.** Not taken: nothing has measured
  InterWeave carrying the fleet's own traffic, and the relay is the only
  carrier with a record of its past.
- **Wait for a second host.** Not taken: the one host is where every
  agent but the remote ones runs, and what the dual run measures there —
  loss, order, concurrency under real traffic — is the evidence ADR-032 §7
  asks for.

## 4. Rationale

The smallest thing that moves P5 forward is the one InterWeave has already
proved: one host, loopback, deny-by-default trust. Running beside the relay
costs a second post per message and nothing in what a session reads,
because ADR-041 rule 5 already keeps one row per `MESSAGE-ID`; what the
journal collapses, the arrival log keeps (rule 11). It also gains something the relay never had: a
sender InterWeave authenticates by PeerId, which the roster turns into an
address, where the relay's `sender` is a claim (ADR-033 §6).

## 5. Binding Rules

1. The carrier runs only on the host the relay runs on, between accounts
   on that host; a profile listens on `127.0.0.1` only, on the port the
   roster fixes for it, one profile per account (InterWeave ADR-0055
   decision 5).
2. The roster (`runtime/interweave/roster.json`) is the only source of a
   login's PeerId, endpoint and port. A row is keyed by agent id
   (ADR-039) and carries its login, PeerId, endpoint and port; it counts
   only when signed by that login's ADR-038 signing subkey over what
   `transportctl identity show` prints, and countersigned by the
   coordinator's key over the whole row: agent id, login, PeerId,
   endpoint and port. A row that fails either signature renders nothing.
   The roster allocates the ports, from a range it states. A
   profile's `config.yaml` is rendered from it, never hand-edited: its
   allowlist is every other valid roster PeerId and nothing else, its
   static bootstrap their loopback addresses, its connectivity server
   roles off.
3. A transport key is minted in its own account by `transportctl identity
   init` and never leaves that account; the roster records the PeerId the
   command prints and nothing secret. A re-keyed login's old PeerId is
   removed from the roster and revoked on every profile.
4. The InterWeave programs are installed per account from a tagged
   InterWeave release archive whose version the fabric pins, by the
   archive's own `install.sh`; never from a checkout build.
5. The carrier is one long-lived process per account under the client
   unit template, holding the lease of the `gzcoord` endpoint; it never
   opens the admin socket. The send and inbox adapters talk to it, and it
   to the data socket.
6. Each message is one direct send per recipient: a `TO` to that address's
   endpoint, a `TO-ROLE` or broadcast to every other roster member, each
   inbox filtering as it does today. GossipSub carries nothing in this
   phase.
7. The carrier keeps its own delivery record, per recipient, in the
   account's runtime state: the `MESSAGE-ID`, the recipient, one
   transport `message_id` kept across every retry, and whether the
   recipient's receipt has arrived. The receipt is a direct message of
   the carrier's own media type, naming the `MESSAGE-ID`, sent by the
   receiving carrier after its journal append; it is never a GZCoord
   message. A send is retried until its receipt and is never given up
   without its operator. The journal's row keeps ADR-041's meaning
   unchanged: accepted when any carrier accepts the post, which in the
   dual run is the relay's acceptance as today. The receiving carrier
   journals only what ADR-041 rule 2 admits, and a repeat collapses by
   `MESSAGE-ID` (ADR-041 rule 5).
8. A message whose payload exceeds the 48 KiB ceiling is compressed
   first (`;ce=br`, the content-encoding InterWeave's human facade
   defines), and chunked under the carrier's own framing only if it
   still exceeds it, reassembled before the journal append. With the
   journal off (ADR-041 rule 10) the route is the relay alone.
9. A delivery carries the address the roster maps its PeerId to. A message
   whose `FROM` differs from it is shown with the mismatch, never as from
   its `FROM`, whichever carrier's copy reached the journal first; a
   PeerId absent from the roster is never admitted, by rule 2.
10. No transport-native value — PeerId, EndpointId, transport
    `message_id`, port — appears as GZCoord metadata (ADR-033 rule 1).
    Where a message needs one, as a reference, it is body text.
11. The relay stays the transport of record and ADR-033 rule 7's fallback
    stands, until an amendment of ADR-033 says otherwise on the owner's
    word. That word is given on a parity report in `docs/live-checks/`,
    computed from an arrival log each inbox keeps beside its journal:
    one line per copy received, (`MESSAGE-ID`, addressee, carrier, time,
    rule 9's verdict), written before the journal collapses the copy.
    The report covers every (`MESSAGE-ID`, addressee) pair over a stated
    window, each pair one carrier missed listed with
    its cause; missed and duplicate counts per carrier; messages
    delivered while their addressee was offline, direct and broadcast
    apart; the messages compressed and the messages chunked. The soak
    includes a rollback drill (the InterWeave carrier switched off
    mid-window, nothing lost), and one `TO-ROLE` recipient among its
    logins.
12. The control plane (`fabric:control`, ADR-029) stays on the relay;
    this carrier carries GZCoord application messages only.
13. Before the dual run starts, the carrier is validated with at least
    two instances under two accounts on the host, one receiving what the
    other sent (ADR-033 rule 4), and with one account's daemon refused
    the port another's holds: InterWeave ADR-0055 decision 5 rests that
    on the kernel's rule and has not measured it.

## 6. Consequences

- Every message is posted twice and every account runs two more user
  units, a daemon and a carrier. Every recipient answers with a receipt,
  so a broadcast costs two direct messages per roster member; the relay keeps its single point of
  failure until the switch, but stops being the only one.
- The fleet gets its first authenticated sender (rule 9), which the
  relay cannot give (ADR-033 §6, §7).
- The roster becomes provisioning's input: a new login on the host needs
  a key minted in its account, a port, a roster row signed by the login
  and countersigned by the coordinator, and a render of
  every other profile's allowlist; a retired one, its entry removed and
  the renders repeated, or a `transportctl trust revoke` until then.
- Agents on another host — none today — stay on the relay alone.
- Nothing builds until an InterWeave release is tagged (rule 4).

## 7. Future Evolution

The build order, once accepted: the tagged release; the roster schema and
the per-account provisioning (a fabric-coordinator surface); the carrier
and the two adapters behind a switch that is off by default, dispatched
to the contributor holders `policies/authority.json` names for that code
at the time; rule 13's two-instance check; the dual run; the parity
report; the owner's word. A second host reopens rule 1 once InterWeave's
gate closes. The carrier's observations of ordering, loss and concurrency
are ADR-032 §7's evidence. The mapping in §5 rules 6 to 10 belongs to
GZCoord's own repository, which the owner asked for (§1;
`docs/split/agent-fabric-coord.md`). Until that repository exists, it
is in this series. When it is created, the mapping moves there with
ADR-032 and ADR-033; the roster, the provisioning and the adapters stay
here.

## 8. Decision Status

Accepted. Its build waits on a tagged InterWeave release (§5 rule 4).

## References

- ADR-029, ADR-032, ADR-033, ADR-037, ADR-038, ADR-039, ADR-041.
- architect-cto's transport facts, REPLY 01a15326 and 01a1536d
  (2026-10-19).
- InterWeave: `architecture/adr/0055-automated-clients-are-first-party-consumers-above-a-general-purpose-transport.md`
  (decisions 1 to 7), ADR-0033, ADR-0034 §7, ADR-0044,
  `architecture/roadmap/SPIKES.md` (SPIKE-004),
  `packaging/linux/DEPLOYING.md`, `apps/human-cli/README.md` (the
  lease and exit 4), `apps/claude-channel/README.md`,
  `tests/automated-client/` (the reference shape), #368, #381.
- `communication/gzcoord/docs/TRANSPORT-ADAPTER-CONTRACT.md`.
- `docs/split/agent-fabric-coord.md`.
