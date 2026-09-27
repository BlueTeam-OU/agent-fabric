# ADR-033 — GZCoord's transports: the human relay, the adapter contract, Telegram retired; the relay is central today

**Date:** 2026-08-13
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #53 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** communication/gzcoord/docs/TRANSPORT-ADAPTER-CONTRACT.md and HUMAN-RELAY-TRANSPORT.md (the manuals); communication/gzcoord/history/ (telegram-transport, claude-bridge-selection); the relay's deployment — communication/gzcoord/runtime/gzcoord-relay.service, its installation in runtime/claude-code/bootstrap.sh, the session-start activation in communication/gzcoord/scripts/inbox.mjs, the projects' integration configs (projects/gzapp/integration/gzcoord/config.json and its siblings), and projects/gzapp/integration/gzcoord/BRIDGE-RELAY-SETUP.md
**Pillar:** P5

## 1. Context and Problem

GZCOORD/1 is transport-independent (SPEC §14): something has to carry
the text between sessions, and what carries it decides what the fleet
can rely on.

The first automated transport was Telegram, one bot per instance in a
shared group. It was retired on 2026-08-13
(`communication/gzcoord/history/telegram-transport/README.md`): Telegram
bots never receive messages from other bots, so instance-to-instance
routing could not work at all, and both bootstrap validations had passed
because neither put two instances in the group. The way around it — a
full user account per instance — was refused: an agent under a
human-style identity can deal with third parties while appearing to be
one.

A person then carried messages between session terminals — the human
relay — and the traffic it carried became the corpus the next transport
was designed against. The Claude-Bridge relay was evaluated against the
adapter contract, selected on 2026-09-16
(`communication/gzcoord/history/claude-bridge-selection/`), and on
2026-09-19 became a systemd user unit instead of a process that died with
the terminal that started it.

## 2. Decision

- **A transport is a carrier, never a successor.** It carries GZCOORD/1
  unchanged; transport-native fields never become protocol fields. An
  automated transport satisfies the adapter contract
  (`communication/gzcoord/docs/TRANSPORT-ADAPTER-CONTRACT.md`): the
  runtime owns parsing and peer semantics, the adapter owns native
  delivery and authentication.
- **An agent is never given a human's identity on a transport.** A
  transport that can reach agents only through a human-style account is
  refused, whatever else it offers.
- **The transport today is the Claude-Bridge relay, and it is central:**
  one process, on the operator's account, on the one host, bound to
  `127.0.0.1:8765`, with one database that is the channel's only record
  of its past. Every session on the host is a client of it; every
  managed project's integration joins the same channel, `gzapp:gzcoord`;
  the control plane rides it on `fabric:control` (ADR-029). Hosting it is
  fabric-coordinator's duty.
- **The human relay is the fallback.** When the relay is down, a person
  carries messages between terminals and is the adapter;
  `communication/gzcoord/docs/HUMAN-RELAY-TRANSPORT.md` is the procedure.

## 3. Alternatives Considered

- **Telegram, one bot per instance.** Retired: bots do not see bots.
- **Telegram with a user account per instance.** Refused: the identity
  rule above, which binds every candidate, not only Telegram.
- **The human relay as the transport.** It worked and produced the
  protocol's evidence, at the cost of a person's attention per message,
  no presence and no delivery receipt. Kept as the fallback.
- **A relay per project or per host.** Not taken: one relay with one
  channel is what the sessions on one host need, and a second relay
  would split the record. The cost is that the relay is a single point
  of failure (§6).

## 4. Rationale

The relay clears the bar the first transport failed: it is self-hosted,
the identity an instance carries is an agent's address, and no
third-party human network is involved. What it does not provide is
written down rather than assumed: its `sender` field is a claim, every
instance holds the same bearer token, and delivery is pull (a long poll),
so the session's watch decides when to read. Centralising it on one host
was the smallest thing that worked; stating that it is central is what
lets the decentralisation direction (ADR-000, P5) be measured against it.

## 5. Binding Rules

1. A transport carries GZCOORD/1 without adding or requiring a field; a
   transport-native identifier (a chat id, a bot name, a channel id) never
   appears as core metadata (SPEC §14).
2. An automated adapter satisfies the adapter contract: a stable native
   sender identity where the transport has one, broadcast or a documented
   bootstrap, direct delivery, authentication and allowlists in the
   adapter. A self-declared `FROM` or `ROLE` is never authentication.
3. No transport gives an agent a human-style identity toward third
   parties.
4. A transport candidate is validated with at least two instances, one
   receiving what the other sent; a check of human→agent or agent→channel
   alone proves nothing about the leg the protocol exists for.
5. The relay runs as `gzcoord-relay.service`, a systemd user unit on the
   hosting account, installed by `bootstrap.sh` only where the relay's
   venv exists and gated again by the unit's `ConditionPathExists`; its
   runtime — venv, token, database, log — lives in the workspace's
   `projects/.gzcoord/`, inside no repository. It binds `127.0.0.1` and
   keeps authentication on. The hosting session's start brings it up when
   it is not answering; a client account never hosts.
6. The relay token reaches every account as `CLAUDE_BRIDGE_AUTH_TOKEN`
   from the account's own Doppler config (`fabric-secrets sync`, ADR-012);
   it is never committed.
7. When the relay is down, messages go by the human relay: composed and
   validated in a file, printed in a fenced block, lines of 72 columns or
   fewer, a minted `MESSAGE-ID`; on receipt normalised
   (`gzmsg.mjs normalize`), validated, and the addressee checked before
   the body is read.
8. `MESSAGE-ID`s are minted UUIDv7 (`gzmsg.mjs new-id`) on every
   transport; the sequential per-instance scheme is retired, and loss is a
   question for the sender, retransmitted under the original id.

## 6. Consequences

- **One relay is a single point of failure.** When its process, its
  account's user manager or its host is down, no session receives
  anything and the control plane answers nothing; the human relay and
  the sudo fallbacks (ADR-029) are what remains.
- **No sender is authenticated on the relay.** Any token holder can post
  as any address; messages are advisory and verified against the
  repository (ADR-024), and control-plane actions carry their own
  signature (ADR-029).
- **Everything shares one channel.** Every project's sessions read the
  same `gzapp:gzcoord`; the inbox filters by addressee before it prints a
  body (`inbox.mjs` `forMe`) — the relay itself delivers everything.
- **Delivery is pull.** A session reads only while its watch runs
  (ADR-022).
- The relay's database is the channel's only record of its past; it is
  host state, not repository state, and nothing backs it up.

## 7. Future Evolution

- A second host needs a relay it can reach: today the relay binds
  loopback, and nothing for another host is built (ADR-029 §7).
- The selection record names InterWeave's cross-host transport as what
  comes next; nothing in this tree integrates it, and InterWeave's own
  sessions join this relay as clients.
- A per-instance credential on the relay would make its `sender`
  authenticated; none exists.
- An automated transport that exercises the grammar is what reopens the
  protocol's freeze (ADR-032).

## 8. Decision Status

Accepted. Telegram is retired, the relay is the transport, the human
relay is the fallback, and the relay is central.

## References

- `communication/gzcoord/docs/TRANSPORT-ADAPTER-CONTRACT.md`,
  `communication/gzcoord/docs/HUMAN-RELAY-TRANSPORT.md`.
- `communication/gzcoord/history/telegram-transport/README.md`,
  `communication/gzcoord/history/claude-bridge-selection/README.md`,
  `TRANSPORT-CANDIDATE-CLAUDE-BRIDGE.md`.
- `communication/gzcoord/runtime/gzcoord-relay.service`,
  `communication/gzcoord/runtime/README.md`,
  `runtime/claude-code/bootstrap.sh`,
  `communication/gzcoord/scripts/inbox.mjs` (the relay's activation,
  `forMe`), `communication/gzcoord/scripts/gzmsg.mjs` (`new-id`,
  `normalize`).
- `projects/gzapp/integration/gzcoord/BRIDGE-RELAY-SETUP.md`,
  `projects/*/integration/gzcoord/config.json`.
- `communication/gzcoord/protocol/SPEC.md` §14, §17.
- ADR-012, ADR-022, ADR-024, ADR-029, ADR-032.
