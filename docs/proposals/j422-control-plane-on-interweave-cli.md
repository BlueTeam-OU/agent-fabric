# The control plane on InterWeave, driven by its CLI: a second host first (draft, j422)

A design for the owner's review, drafted for fabric-coordinator; it decides nothing until the
records in §8 are accepted. The owner's direction (2026-10-27): "control plane on interweave
should be implemented on interweave cli". Its purpose, from the same day: to **move an agent to a
remote host**. The first one is likely `edge-hosting`. Today the control plane (agent-fabric
ADR-029) and GZCoord both ride one relay at `http://127.0.0.1:8765` (`runtime/control/config.json`),
and that relay cannot be reached from a second host (ADR-029 §7, lines 301-305; ADR-033 §7, lines
144-147). Read against origin/main 478bcc3f and InterWeave origin/main cf7089b5 (re-pinned, R12).

**Revision 2026-10-27.** Twelve requirements, R1-R12, came from architect-cto's verification of this
draft against InterWeave's records (origin/main 5080940c). Each is folded into the section it
belongs to and tagged `(R<n>)`. R8 and R9 are InterWeave's own changes, noted at §9.

## 1. Summary of decisions

1. **Cross-host is the main case.** The target is `edge-hosting` on a second host, `H2`, which is
   not yet named or registered. `fabric-ctl` on develop-qzapp reaches it, and its GZCoord traffic
   reaches it too, over InterWeave between the two hosts. The design does not use NAT traversal or
   discovery: both hosts get static addresses that the operator writes into the configuration, on a
   routed private overlay (§3). Listeners are wildcard and the firewall is the boundary (R7).
2. **Carrier.** Each account's `agentd` runs `interweave-human … listen --json` as a supervised,
   long-lived child process, and sends through that same process. **The CLI cannot carry this
   today.** ADR-064 §1's finding stands: `listen` holds the endpoint lease alone, a `send` while it
   runs exits 4, and what it prints lands unread in the human store. §4.0 states the four changes
   InterWeave must make first. They are the main REQUEST to architect-cto.
3. **Topology.** Control traffic uses the account's existing InterWeave profile and PeerId, on a
   second endpoint `fabric-control`, the profile's first and only human endpoint, an identity (R3).
   The `gzcoord` carrier keeps its own automated endpoint. The control profile is never a person's
   profile: the human store's lock is profile-wide (R2). On the operator's account, `fabric-ctl` does its fan-out through the operator's own
   agentd over a local socket, never through its own lease (§5).
4. **Safety.** On develop-qzapp the relay stays the transport of record for control until a parity
   report and the owner's word, as ADR-064 rule 11 did for GZCoord. The `interweave*` ops stay
   relay-only on that host. On H2, which has no relay, the path when InterWeave is down is hostexec
   over ssh to a local op runner, which checks the same signature (§6). Every control record is stored durably before it is sent and
   carries no secret value (R6).
5. **Grammar.** ADR-029's request and reply envelopes (`protocol.py:34-39`) and `sign.py` do not
   change. Only the reply part sizes change, per carrier (§4.3).

## 2. What blocks a second host today, and what has to close first

**In the fabric**

- ADR-064 rule 1. On main (lines 142-147) it reads "The carrier runs only on the host the relay
  runs on". PR #397 (head d1f0473c, 2026-10-27, the owner's change) rewrites it: one host is the
  *first milestone*, and a second host is the next. That milestone opens through an amendment that:
  - names the host;
  - gives its accounts' roster rows routable addresses;
  - says how InterWeave ADR-0034 §7 and SPIKE-004's limits are consumed, or accepted on the owner's
    word.

  Until that amendment lands, nothing listens off loopback. §8 drafts the amendment, for H2 and
  edge-hosting.
- The roster has no host or address field. Its rows are `agent_id, login, peer_id, endpoint, port`
  and two signatures (`runtime/interweave/roster.schema.json`), and the render hard-codes
  `LOOPBACK = "127.0.0.1"` (`tools/fabric/gzcoord/carrier/roster.py:32,53`).
- ADR-048 rule 1 (lines 97-107): sshd listens on loopback, with "more than one host" left to §7
  (lines 187-188).
- ADR-010 §7 (line 144): the ssh backend of hostexec has never been read back on a real second host.
- The registry has one host (`runtime/hosts/registry.json`, develop-qzapp, `ssh: null`).
- ADR-034 (lines 72-74, 125-128) put the second host *after* the relay-loss rows and a scheduled
  drain. Whether the owner's direction overrides that order is open question Q1.

**In InterWeave**

- ADR-0055 decision 5 and its revisit conditions (line 17, "a second host is the day [ADR-0034 §7]
  and SPIKE-004's deferred limits are consumed"; the Security section: "Not claimed: … any property
  of a second host").
- ADR-0034 decision 7 makes SPIKE-003 (Kademlia, default-on) a v1 release gate. The server-mode
  reachability evidence for it is still missing (`architecture/roadmap/SPIKES.md:258`).
- SPIKE-004's phase B closed on 2026-09-26 with four limits the owner deferred: a public VM, a
  carrier's CGNAT, hole-punch success rates in the wild, and relay and probe services that are
  operationally independent (`SPIKES.md`, SPIKE-004 closing record).

**Reading.** Those two gates are about discovery (a DHT) and about reaching nodes behind NAT
(AutoNAT, relay, DCUtR). The deployment proposed here uses none of that:

- Kademlia is left out of the profile, which ADR-0034 decision 4 allows.
- The connectivity server roles stay off, as the render already does (ADR-064 rule 2).
- Every dial goes to an address the operator wrote in the configuration. ADR-0052 rule 9 puts that
  door outside the floor for peer-supplied addresses, so private ranges are allowed.
- The two hosts can route to each other directly over WireGuard.

So the request to InterWeave is narrow (gap **X1**): an amendment to ADR-0055 that adds a
decision 5b, "two hosts, static operator-supplied addresses, directly routable, discovery and
connectivity roles off". It would be backed by a two-host case in `tests/automated-client`, run in
two network namespaces or containers like the SPIKE-004 phase-B setup. It would claim nothing about
NAT, the internet or Kademlia. ADR-0034 §7 and SPIKE-004 stay where they are, and they block only a
deployment that needs NAT traversal or discovery. **Only architect-cto can rule on this.** If X1 is
refused, the PR #397 route remains: the owner accepts the gates as known limits for H2, and §8
records that.

## 3. The first remote agent: edge-hosting on H2

**Why this agent.** Its brief says its egress "is shared by every agent on the host"
(`identities/roles/edge-hosting/brief.md:53-54`). Its charter says a status surface must share
nothing with what it reports on (`charter.md:24-28`). A second host gives it an outside vantage
point and its own failure domain. That claim holds only if H2 does not share develop-qzapp's uplink
or provider, which is open question Q2.

### 3.1 Network (decided, with the alternatives rejected)

- **Decided:** a WireGuard overlay between develop-qzapp and H2, run by each host's operator.
  - On each host, each profile listens on a wildcard address on its roster port (R7). A literal
    overlay-address listener loses network-change detection (InterWeave ADR-0055 5b, measured), and
    the same-host fleet would fail to start whenever the overlay is down (a listen failure exits 1;
    the unit retries four times).
  - Each host's firewall is the boundary: it admits the roster port range (`47100-47199`) only
    from the other host's overlay address.
  - ADR-064 rule 1's port reservation applies on every host.
- **Rejected: a public listener with Noise as the only defence.** It exposes every daemon to
  internet scans. Its pre-auth buckets are the residual risk ADR-0052 accepts, not a boundary.
- **Rejected: relay circuits or hole punching.** These are exactly SPIKE-004's deferred limits.
- **Rejected: Tailscale or another coordinated mesh.** It adds a third-party control server to the
  failure domain. The owner may choose it anyway (Q3).

### 3.2 Registering H2 (ADR-010 rule 5: an entry, a check, one live read-back)

A `hosts.H2` entry in `runtime/hosts/registry.json`:

| field | value |
|---|---|
| `platform` | the host's platform |
| `ssh` | `op@<H2 overlay address>`, the hostexec ssh backend |
| `operator` | the operator login on H2 |
| `fabric` | the path of H2's fabric checkout |
| `operator_key` | null, so no one signs from H2 and `fabric-ctl` runs only on develop-qzapp (Q4: does the schema allow null?) |
| `sshd` | sshd bound to the overlay address (an ADR-048 rule 1 amendment for a non-single-host deployment) |
| `interweave_address` (new) | H2's literal overlay IP |

develop-qzapp gets `interweave_address` too. Then `fabric-host H2 check`, then the first real
ssh-backend read-back as a live check (ADR-010 §7).

### 3.3 The roster across hosts (fabric-coordinator's surface)

- Rows gain `host`, a registry id. The address comes from the host's `interweave_address`, so one
  move rewrites one field.
- The countersignature covers `host`. Every row is re-countersigned once. The logins do not
  re-sign, because their signature covers `identity_show` only (ADR-064 rule 2).
- The render, per account: listen on the wildcard at `<port>` (R7), and static bootstrap to every
  other valid row's address and port: `127.0.0.1` for a row on the same host, the row's host
  `interweave_address` for a row on another host. The allowlist stays every other roster PeerId and
  nothing else.
- An account that is running picks the change up through `interweave-start`'s `rerendered` path
  (ADR-029 table, line 85).

### 3.4 What H2 must have installed and keyed for edge-hosting

- **The account.**
  - The login `edge-hosting`; its agent id does not change (ADR-039).
  - It lingers, and it is persisted if H2 is a Qubes AppVM (ADR-029 rule 11).
  - It runs `agent-fabric-agentd.service` (rule 1).
  - Claude Code, the gateway (`gateway-install`), and GitHub's pinned host keys (ADR-010 rule 7).
- **InterWeave.**
  - The pinned release, installed by its own `install.sh` (ADR-064 rule 4).
  - `interweave-human` added to `release.json` `reports` and `program_sha256`. Today the pin's
    description says the human clients are "installed … and not checked"; that is gap F1.
- **Keys** (Q5 below asks whether to rotate or carry; the decision is to rotate):
  - The ADR-038 signing subkey is **rotated**: minted in the H2 account and attested by the
    parent's certification. "Rotation keeps the identity" (ADR-038 line 43); the key is never
    copied between hosts.
  - The transport key is **re-minted** with `transportctl identity init`. This is ADR-064 rule 3's
    re-key: the old PeerId row is removed and revoked on every profile.
  - The `fabric-control` identity key, `<state>/identity-keys/fabric-control.key`, is provisioned
    state (R3): minted on H2 by the first run, owner-only, never copied between hosts, and its
    card is never shared.
- **Secrets.** The store `BlueTeam-OU/fabric-agent-<id>` is cloned on H2. The old account first
  re-encrypts it to both key ids, and drops the old key id at cut-over. Then
  `fabric-secrets sync` runs on H2. A provider credential reaches H2 only inside the store.
- **Clocks (R10).** ADR-029's freshness window and "strictly newer" rule compare timestamps made
  on different hosts. Both hosts run chrony (or another NTP client) against a common source, and
  agentd reports its offset in `interweave`. Proposal, to be set on a measurement: a skew under
  2 s is tolerated; at or above it the channel reports `control: off (clock)` and refuses signed
  actions rather than guessing. The 2 s figure is a proposal, not a decision.
- **Bounds (R11).** Static bootstrap entries are capped at 64 (InterWeave ADR-0062 d2; fatal at
  start above it), so a one-profile-per-account mesh holds at most 65 accounts per profile. The
  render fails above it. It also renders `channels.desired` empty for these profiles, or `listen`
  would receive every GZCoord broadcast into the human store.

### 3.5 Moving edge-hosting, in order

| step | what happens | who |
|---|---|---|
| 0 | §7 phases P0-P2 are done: the CLI gaps are released and pinned, control parity is accepted on develop-qzapp, X1 is ruled, and the two-host check is done with a throwaway login on H2 | coordinator, owner, InterWeave |
| 1 | The old account drains its memory (`fabric-ctl edge-hosting memory`), pushes every branch (`fabric-branches`), takes `fabric-jobs` to no active job, and its working copies are clean | edge-hosting |
| 2 | Jobs move: `fabric-jobs export` on the old account and `import` on H2, piped through hostexec stdin (gap F2). Job state is runtime state, never in git | coordinator |
| 3 | H2 is provisioned (§3.4) while dormant: agentd is installed but not started, and the working copies are cloned fresh from GitHub. No file is copied between homes | H2 operator, coordinator |
| 4 | The new PeerId's row (host H2) is signed by the login and countersigned. Every develop-qzapp account re-renders. H2's daemon and carrier start | coordinator |
| 5 | Cut-over: on the old account `interweave-stop`, then agentd stopped and its user units disabled. `placement.edge-hosting` changes to H2. The address becomes `H2/edge-hosting` (ADR-039: the name changes, the id stays). H2's agentd starts. `fabric-ctl edge-hosting ping` answers over InterWeave | coordinator |
| 6 | The old account is locked, not deleted: a `userdel` on Qubes is undone at boot (ADR-029 §7, lines 306-307). It is retired once a week of H2 rows is clean | owner |

**GZCoord for the remote agent.** The account has no relay, so InterWeave is its only GZCoord
carrier. That needs an amendment to ADR-033 and ADR-064 rule 11 making InterWeave the transport of
record *for off-host accounts*, given on the owner's word over the GZCoord parity report. The
develop-qzapp senders already post twice, and their InterWeave copy reaches H2 by rule 6's direct
sends. H2's sends go by InterWeave only, and the journal accepts a message when either carrier
accepts it (rule 7). The fallbacks when InterWeave is down: the human relay, git, and a harvest
bundle over hostexec.

## 4. The carrier: agentd drives interweave-human

### 4.0 ADR-064 §1's finding, faced: why the CLI cannot carry today, and what must change

ADR-064 §1 (lines 51-58) and §3 (lines 98-103) found three things wrong with `interweave-human` as
a carrier. Each is still true at InterWeave cf7089b5:

- **(a) The lease is exclusive.** `listen` holds it. Any second client on the profile, so a `send`
  while `listen` runs, is refused with exit 4 (`apps/human-cli/README.md:57-58`).
- **(b) `listen` takes no input.** It loops on the session and stdout only
  (`apps/human-cli/src/verbs.rs:817ff`), so nothing can be sent through the process that holds
  the lease.
- **(c) What `listen` prints lands in the human store.** A `message` it prints "stays unread in the
  store" (`README.md:64`). The store's retention is a person's reading (ADR-0044); it is encrypted
  at rest (ADR-0060) and grows with every control record.

The control plane can ride the CLI only once InterWeave makes these four changes. They are the
main REQUEST to architect-cto. Each one is stated as behaviour, so a test can hold it:

1. **(G1, answers a and b) A listen that takes input.**
   - `listen --json --input` reads JSON lines on stdin, `{"send": {"conversation": <c>, "text":
     <t>, "ref": <r>}}`, and sends each one over the lease it already holds.
   - Each send is answered on stdout by one `{"event": "outbound", "ref": <r>, "id": <p-id>,
     "status": <token>}` line, using the fixed tokens `send` already has (`output.rs:69-97`).
   - A malformed input line is answered with `{"event": "input-refused", "ref", "reason"}` and the
     process carries on running.
   - Closing stdin does not end `listen`; SIGTERM does, with exit 0, as today.
2. **(G2) The endpoint is named.**
   - `--endpoint <id>` on `listen` (which human endpoint's lease the process holds) and on each
     input send (which endpoint it sends from). `identities enable` already exists.
   - Creating a named human endpoint from the command line, which README line 16 puts in Stage 22.
   - The `message` event names the local endpoint that received the message (G6). Today it names
     only the author and the peer's endpoint (`verbs.rs:735-752`).
3. **(G3, answers c) A listen that consumes.** `listen --consume` marks each `message` read and
   not kept once its line is written and flushed. No unread row is left behind, and RETENTION.md's
   "read and not kept lives only for the run" applies. A line that cannot be written (the reader
   is gone) is not marked read.
4. **(G4) An ephemeral send.** An input send with `"pending": false`, or `send --no-pending`, is
   cancelled when its `--wait` runs out, never left for a later run to send again (`README.md:62`).
   A signed request sent again after its TTL would only be refused, but it must not reach the wire.

Ruling **X2** goes with these: a human-kind lease on `fabric-control` and the fabric carrier's
lease on `gzcoord` can be held at once in one profile and one daemon. That is a statement about the
daemon's leases only. **The exclusion that remains is the human store's instance lock, not a
lease** (R2): exit 4 is `HumanClientLock`, profile-wide (`startup.rs:91-98`, `main.rs:218`). While
agentd's child holds it, no other `interweave-human` run on that profile works, a one-shot `status`
or `store health` included, and no desktop client. So:

- the control profile is never a person's profile;
- operator diagnostics of it go through the `interweave` read op or the daemon, never the CLI;
- a per-endpoint lock is an InterWeave change that architect-cto will not make for this.

With G1-G4 and X2, objections (a), (b) and (c) are answered for the control plane. For GZCoord,
ADR-064 §3 stays as it is: the volume, the receipts and the chunked media types still need the
fabric's own carrier.

### 4.1 The long-lived child

- **What runs.** A new `tools/fabric/control/carrier_cli.py` starts
  `interweave-human --profile gzcoord listen --json --endpoint fabric-control --input` (gaps G1 and
  G2). The first `session` event with `ready` means the child is up. The supervisor reads stdout
  line by line.
- **Destination (R1).** Every control send names `<peer>/fabric-control`. A peer-only send goes to
  the remote's default endpoint (`ENDPOINTS.md:76`, `README.md:52`), which the roster row says is
  `gzcoord`, and that breaks ADR-029 rule 2 by one omitted field. So the render pins each
  profile's default endpoint (`gzcoord` or none), `identities default` is never run on these
  profiles, and the carriers enforce both ends: the GZCoord carrier refuses a `fabric-control/1`
  body arriving on `gzcoord`, and a carrier media type arriving on `fabric-control` is dropped.
- **What `fabric-control` is (R3).** In InterWeave ADR-0061's terms it is the `gzcoord` profile's
  first and only human endpoint, hence its identity in front (d1). The CLI mints its identity key
  silently on the first run (`profile.rs::leasable_endpoints`, `main.rs:141-153`), at
  `<state>/identity-keys/fabric-control.key`: provisioned state, owner-only (§3.4). A second
  human-kind endpoint is never configured on the profile (it would be a route, d2, and the CLI
  would default to no identity, d9). `gzcoord` stays automated (d8) with `allowed_client_kinds`
  automated only; `fabric-control` is human-client only, the misbinding guard of `ENDPOINTS.md`.
- **Admin connection (R5).** `interweave-human` holds an admin Status connection, polled every 5 s
  (`transport-client client.rs:3-5,62`), while `AUTOMATED-CLIENT.md` says an automated consumer
  never opens the admin socket. This is acceptable, as named: the carrier runs `listen` alone
  (Status read only), agentd never drives an admin-mutating verb (`identities`, `peers`), and the
  `interweave*` ops stay on the relay or hostexec.
- **Custody (R4).** Today the store key and identity key are owner-only files. InterWeave ADR-0060
  d3 seals the store key under ADR-0038's passphrase envelope when SPIKE-007 lands, and ADR-0063
  d2 re-seals the identity keys in the same step; a lingering agentd cannot answer a passphrase.
  **Constraint SPIKE-007's adoption must meet:** a headless custody mode stays available for an
  account's control profile (architect-cto carries it into ADR-0060/0038's revisit once this
  design is accepted). The two destructive CLI ops are never agentd's: `store discard --confirm`
  (exit 5) is an operator's op, and `identity new-key --confirm key-change` runs only on the
  owner's word, since a key change re-issues the card.
- **Restart on exit.** Restart uses backoff of 1, 2, 4 … 60 s, by exit code:

  | exit | meaning | agentd does |
  |---|---|---|
  | 3 | no daemon | channel `off`, retry |
  | 4 | the lease is held | a journal line, retry, never kill the holder |
  | 5 | the store cannot be used | channel `off`, reported in `interweave` |
  | EOF or a crash | the child died | restart |

  The state goes into the `interweave` read as `control: ok|off|restarting`.
- **Backpressure.** The reader thread only parses and enqueues, into a queue bounded at 256 to
  match the daemon's per-client queue (ADR-0055 decision 2). A child that does not drain is closed
  as wedged and loses its lease. A full queue drops its oldest request with a journal line;
  requests expire after `ttl_s` of 30 s anyway.
- **Sends.** Sends go to the same child's stdin, one JSON line each, with a `ref`. The child
  answers with an `outbound` event naming the `ref` and a fixed status token (`accepted`, or
  `too-large`, `peer-untrusted`, `route-unavailable`, `no-network-path`, `busy`; see
  `apps/human-cli/src/output.rs:66-75`). A send never outlives its request's budget.
- **Durable first, and no secrets (R6).** Every control record is written durably to the human
  store before it is sent or presented (RETENTION.md: `PENDING_OUTBOUND`, `UNREAD_INBOUND`); G3
  and G4 delete after, not instead. No control record carries a secret value, in any op's request
  or reply: a rule, checked at the sender (ADR-029's ops already print prefixes and counts).

### 4.2 fabric-ctl's side

`fabric-ctl` keeps its own logic: the targets (`ctl.py:884`), the budgets (`ctl.py:607-618`,
ADR-029 rule 12, unchanged), the rows, and silence as a row. It hands each send to the operator's
agentd over `$XDG_RUNTIME_DIR/agent-fabric/control.sock` (mode 0600, same uid). It reads back the
replies agentd routes to it by `in_reply_to`, and their carrier. `all` expands at the sender to one
direct send per placed agent's roster row. `*` is never sent on InterWeave.

State records (rule 16) go as direct sends to each host operator's address, on change and on the
10-minute heartbeat.

### 4.3 Framing, size and correlation

- **One record is one text message.** The message body is `fabric-control/1 ` followed by the JSON
  object. The prefix means a person's text to the endpoint is never parsed as a record.
  - The canonical form and the signature do not change. Freshness and "strictly newer" now run
    across hosts, so they need synchronised clocks (R10, §3.4). An action is accepted only when it is
    signed, fresh and strictly newer (rule 5), so a copy arriving by both carriers runs once
    (`ActionLedger`, `agentd.py:342-386`).
- **Size.** The CLI cannot set a media type or chunk. The human facade brotli-compresses an
  envelope of up to 192 KiB raw and refuses anything that is still over 48 KiB afterwards
  (`crates/human/chat-protocol/src/decode.rs:21`, `encode.rs:166`).
  - The part bound becomes a per-carrier constant: on InterWeave, 32 KiB of base64 per memory part
    (rule 9 says 90 KiB) and 32 KiB per evidence page (`carrier_evidence.py:52-54` derives 64 KiB
    from the relay's 128 KiB).
  - A 32 KiB evidence page is JSON-escaped twice (the record, then the message line) before the
    192 KiB raw ceiling applies, so the part size is measured once on the real path, not derived
    (R11).
  - A `too-large` status re-splits at half the size, once.
- **Correlation.** `id` and `in_reply_to` are unchanged. agentd's seen-set (rule 4, the last 256
  ids) is shared across both carriers, so a request is answered once.
  - During the dual run the reply goes back on *both* carriers. fabric-ctl keeps the first copy per
    (`in_reply_to`, `from`) and logs every arrival with its carrier for the parity report.
- **No transport receipt.** The reply is the receipt. A pending send whose `--wait` ran out is
  cancelled, never left to be sent again later (G4).
- **Authenticated sender.** The listen event's `author` is the sender's PeerId, which the roster
  maps to a login. agentd refuses a request whose `from` is not that login's address. fabric-ctl
  likewise accepts a reply only from the PeerId of its `from`. That closes ADR-029 §6's first
  bullet for the InterWeave copy.

### 4.4 Alternatives rejected

- **A library binding to the data socket.** The owner's direction rules it out, and it would be a
  second carrier codebase.
- **The `gzcoord` carrier as the control broker.** It is a second bridge. It also couples control's
  liveness to the process that control installs and checks (ADR-064 rule 14).
- **A one-shot `send` per reply while `listen` runs.** The second client exits with code 4
  (`README.md:57`).
- **Two profiles per account, one listening and one sending.** It doubles the daemons, ports, keys
  and roster rows, and amends rule 1's "one profile per account". It also means the PeerId that
  replies is not the one that was asked.
- **fabric-ctl holding its own lease each time it runs.** The deck's `states --follow`, the
  switch-controller timer, concurrent runs and a desktop client on the operator's profile would all
  exit with code 4.

## 5. Topology and who may send to whom

- **Decided: one profile, one PeerId, two endpoints.** `gzcoord` belongs to the fabric's carrier
  and `fabric-control` to `interweave-human`. This keeps rule 1's one daemon per account and adds
  no keys or ports.
  - It assumes InterWeave allows a human-kind lease and a carrier-kind lease on different endpoints
    of one profile at the same time. That is question X2 for architect-cto; the store lock (§4.0, R2) is the limit that stays.
  - If X2 says no, the fallback is a second profile per account, `fabric-control`, with its own
    port range (`47200-47299`) and its own roster rows (a `profile` column).
- **Rejected: sharing the `gzcoord` endpoint.** Control records would reach GZCoord inboxes, against
  ADR-029 rule 2 (`assert_not_control_channel`, `inbox_parts/config.py:66`).
- **Transport trust** is per PeerId: every other valid roster row and nothing else, deny by
  default (ADR-064 rule 2).
- **Control authority** stays ADR-029 rules 4 and 5, enforced in agentd:
  - operators send to accounts; any placed account may send a public op;
  - an account replies only to the sender of the request;
  - a request between two agents is refused and gets a journal line.
- **Not needed:** an endpoint-scoped allowlist in the transport. It would be optional hardening
  (G9).

## 6. Safety: the dual run, and the path when InterWeave is down

- **develop-qzapp accounts run both carriers** while the relay stays the transport of record for
  control. The switch to InterWeave as transport of record needs a control parity report in
  `docs/live-checks/` and the owner's word, as an amendment of ADR-029. The report covers:
  - every (request id, addressee) pair, with which carrier carried the request and which the reply;
  - latency p50 and p95 per carrier;
  - each miss, with its cause;
  - a drill with `interweave-stop` run in the middle of the window, in which every request is still
    answered by the relay.
- **Ops that stay relay-only on develop-qzapp:** `interweave`, `interweave-install`,
  `interweave-start`, `interweave-stop`. These are the check of the channel and the actions that
  take the channel down (ADR-064 rule 14), and asking over that same channel is circular.
- **When the carrier is off,** fabric-ctl drops back to the relay per account and names the carrier
  in each row.
- **H2 has no relay.** Its fallback is `fabric-host H2 run --as edge-hosting -- @fabric/bin/fabric-op
  <op> [args]`: a local op runner (gap F3) that takes the *same signed request* on stdin and checks
  the operator's signature as agentd does. This is how `interweave-install`, `-start` and `-stop`
  reach H2.
  - It is break-glass by ADR-010. Every use is a journal line on both hosts.
- **Rejected: exposing the relay on the overlay.** Its `sender` is a claim (ADR-033 §6) and it
  binds loopback by design. It would need TLS and a per-instance credential (ADR-033 §7, third
  bullet). The owner may still want it as the uniform fallback (Q6).

## 7. Rollout, measurement and lanes

| phase | what | done when | lane |
|---|---|---|---|
| P0 | CLI gaps G1-G4 and G6 merged, plus X1 and X2 ruled; a tagged release; `release.json` bumped (F1) | the pin points at a tag | InterWeave holders via architect-cto; tagging is the owner's; the pin is the coordinator's |
| P1 | `carrier_cli.py`, the control socket, the per-carrier part sizes and the control parity computation, behind `control_carrier: relay\|dual` (off by default); a two-account check like rule 13; then a dual run on every develop-qzapp account | the parity report is in `docs/live-checks/` and the owner has given the word | python-dev contributors (`tools/`, `runtime/control/`, `runtime/interweave/` are theirs in `policies/authority.json`); the ADR amendments are the coordinator's |
| P2 | H2 registered (§3.2); the overlay up; the roster's `host` field and the render; a throwaway login on H2 doing ping and identity both ways plus one GZCoord message each way; F3 | the live check, and the GZCoord parity covers the off-host pair | coordinator (registry, roster, provisioning, ADR-048 amendment); H2's operator; python-dev for the render and F3 |
| P3 | edge-hosting moves (§3.5) | `ping`, `identity`, `tools` and `status` answered from H2 over a week; no lost message in the arrival logs | coordinator; edge-hosting for step 1; the owner for retiring the old account |

**What is measured throughout:**

- the child's restart count;
- the store's row count, which G3 must keep flat (R9);
- the clock offset between the two hosts (R10);
- per-op latency on and off the host. `ping`'s 5 s budget may need 10 s across hosts, and it is
  changed only on a measurement;
- missed and duplicate counts per carrier.

## 8. The records: draft amendment text

**ADR-029 (carrier).**

- §2, first bullet. Replace "The records ride the relay on a channel of their own" with: "The
  records ride a carrier: the relay's `fabric:control` channel, and InterWeave, where each
  account's agentd holds its profile's `fabric-control` endpoint through `interweave-human`'s
  duplex listen and the operator's agentd carries fabric-ctl's fan-out. A record is one JSON object
  per message on either carrier, unchanged."
- New rule 18:
  - On InterWeave a request counts only when its `from` is the address the roster maps its author
    PeerId to.
  - The seen-set is shared across carriers.
  - The `interweave*` ops go on the relay only, and on a host with no relay through `fabric-op`
    over hostexec, signed alike.
  - Part bounds are per carrier: 32 KiB on InterWeave.
  - Every send names `<peer>/fabric-control`; the carriers refuse a `fabric-control/1` body on
    `gzcoord` and drop a carrier media type on `fabric-control` (R1).
  - Every control record is stored durably before it is sent, and none carries a secret value,
    checked at the sender (R6).
  - The hosts' clocks are synchronised within the tolerance proposed in §3.4 (R10).
- §6, first bullet. Narrow it to the relay copy.
- §7, second-host bullet. Replace it with: "A second host is reached over InterWeave (ADR-064 as
  amended); the relay stays on develop-qzapp."

**ADR-064: the second-host milestone amendment, for edge-hosting.** This is the amendment PR #397's
rule 1 asks for. It opens the next milestone; it does not lift a rule. Draft text, appended to rule
1 as "(A 2026-1x-xx)":

> The second milestone is the host `<H2>`, registered in `runtime/hosts/registry.json` with its
> `interweave_address`. Its first account is `edge-hosting`.
>
> - **Addresses.** On `<H2>` and on the relay's host, a profile listens on a wildcard
>   address at its roster port, and the host's firewall is the boundary: it admits the roster's
>   port range only from the other host's address on the operator-managed WireGuard overlay. Each
>   roster row names its `host`, and the render gives static bootstrap `127.0.0.1:<port>` for a
>   same-host row and `<interweave_address>:<port>` for an other-host row.
> - **The InterWeave gates.** For this deployment, ADR-0034 §7's release gate and SPIKE-004's
>   deferred limits are *consumed*, by InterWeave ADR-0055 decision 5b (X1) and its two-host case:
>   Kademlia is omitted, the connectivity roles are off, and every dial goes to an address the
>   operator supplied. *Or*, if X1 is not given, they are *accepted on the owner's word as known
>   limits for `<H2>`*, quoted here with its date. Either way, no NAT traversal, relay circuit or
>   discovery is relied on, and a third host is a further amendment.

- **Rule 2** gains `host`, covered by the countersignature.
- **Rule 11** gains an exception: an off-host account has no relay, so its GZCoord carrier of record
  is InterWeave from its cut-over. The cut-over follows the owner's word on the on-host parity
  report.
- **Rule 12** is replaced: "The control plane rides each account's InterWeave profile on its own
  `fabric-control` endpoint, carried by `interweave-human` (ADR-029 rule 18), never by this
  carrier. On the relay's host the relay stays control's transport of record until the owner's
  word on a control parity report; on `<H2>` InterWeave is control's only carrier, and hostexec is
  its break-glass. The profile is the control plane's alone: `fabric-control` is its only human
  endpoint, a person's client never uses it, and `gzcoord` is automated-only (R2, R3)."
- §3. The `interweave-human` bullet gains a sentence: "Not taken for GZCoord's volume and receipts;
  taken for the control plane (A 2026-10-2x): its records are few, small and TTL'd, the reply is
  their receipt, and the CLI's duplex listen (gap G1) and consuming read (G3) remove the lease and
  store objections."
- Rule 11 gains an exception: an off-host account's GZCoord carrier of record is InterWeave from
  its cut-over.

**ADR-033 §7, second bullet** (the stale sentence at lines 145-147). Replace it with:
"InterWeave carries GZCOORD/1 beside this relay on one host (ADR-064), and is what a second host
is reached by (ADR-064 rule 1 as amended)."

**Also needed:** an ADR-048 rule 1 amendment for sshd on the overlay address of a multi-host
deployment; an ADR-010 live check for H2; and InterWeave's ADR-0055 decision 5b (X1).

## 9. Gaps

**InterWeave CLI and transport** (for architect-cto as a REQUEST). Blocking marks what P1 cannot
start without; cross-host marks what P2 cannot start without.

- **G1-G4 (blocking), the main request**, specified in §4.0:
  - G1: a listen that takes input;
  - G2: a named endpoint, and creating one from the command line;
  - G3: a listen that consumes what it prints;
  - G4: an ephemeral send.
- **G5 — fixed send outcomes in JSON.** `route-unavailable` and `no-network-path` already exist as
  tokens (`output.rs:69-97`). Input sends need them as JSON fields as well as exit codes. The
  `outbound` event prints message status tokens (`sending`, `accepted`, `cancelled`,
  `needs-attention`), not these send-problem tokens (`too-large`, `route-unavailable`, ...), so the
  re-split on `too-large`, and telling a restarting child from an unreachable host, need G5 in
  G1's event (R8, InterWeave's, asked on #477).
- **G6 (blocking) — the receiving endpoint in the event.** The `message` event names the author
  (PeerId) and `conversation` (the peer's endpoint, `verbs.rs:735-752`). It must also name the local
  endpoint that received the message.
- **G3 also (R9, InterWeave's, asked on #477)** drains the store's unread rows at session open and
  on `UnreadInStore` (a crash between commit and print, the held cap), and drops a card proposal a
  roster peer sends to `fabric-control`; else the "row count flat" measure drifts.
- **G7 — filters on listen.** `--events message,session,connectivity` and `--conversation <c>`.
- **G8 (cross-host) — per-peer connection state.** `peers --json` gives only
  `{address, source, dialled}`. It needs `connected` and the `last_seen_ms` per trusted peer, so
  that "H2 unreachable" can be told apart from "agentd silent". The `connectivity` and
  `disconnected` events should name the peer.
- **G9 (optional) — endpoint-scoped trust.** A peer may reach an endpoint only if allowed for it.
- **X1 (cross-host, InterWeave records) — ADR-0055 decision 5b** and a two-host case in
  `tests/automated-client` (§2).
- **X2 (blocking) — leases.** A ruling that a human-kind lease on `fabric-control` and the
  carrier's lease on `gzcoord` can live together in one profile and one daemon.

**The fabric's own:**

- **F1** — `interweave-human` in `release.json` `reports` and `program_sha256`.
- **F2** — `fabric-jobs export|import`.
- **F3** — `bin/fabric-op`, the local signed-op runner.
- **F4** — the roster schema's `host` field, and `interweave_address` in the registry schema.

## 10. Open questions for the owner

- **Q1.** Does the move to H2 override ADR-034's order (relay-loss rows and a scheduled drain
  before a second host)?
- **Q2.** Where is H2? Does it share develop-qzapp's uplink or provider? That decides whether
  edge-hosting gains an independent vantage point.
- **Q3.** WireGuard run by the operators, or a coordinated mesh?
- **Q4.** Does H2 get its own operator key, so `fabric-ctl` could run there, or no signer at all?
- **Q5.** Rotate edge-hosting's ADR-038 subkey on H2 (proposed), or carry the keyring over ssh?
- **Q6.** Is break-glass hostexec acceptable as H2's only control fallback, or should the relay be
  exposed on the overlay with TLS and a per-instance credential?
- **Q7.** InterWeave's ADR-0064, which is only Proposed, gives automated clients sealed messages
  (decision 8, which names the control plane) and an offline holder (decision 5). Should control
  wait for it, or move without it as proposed here?
