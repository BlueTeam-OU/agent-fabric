# Transport Adapter Contract

Decisions: agent-fabric ADR-033 (`docs/adr/ADR-033-gzcoord-transports-the-relay-is-central-today.md`).

This is an architectural interface, not a network API.

A transport implementation should provide these operations to the local runtime:

```text
connect()
disconnect()
broadcast(protocolText)
send(nativePeer, protocolText, replyContext?)
onMessage(nativeSender, protocolText, nativeMessageContext)
```

The runtime owns protocol parsing and peer semantics. The adapter owns native delivery and authentication.

## Required properties

### Native sender identity

Inbound delivery MUST expose a stable transport-native sender identity when the transport provides one. The runtime associates it with the logical GZCoord address in the `FROM` of any valid message (SPEC §5); presence, not an announcement, says whether that address is live.

### Broadcast

The adapter SHOULD provide a way for a `BROADCAST` to reach all participating peers (`HELLO`, which once relied on it, is deprecated — SPEC §5). If the transport cannot broadcast to all agent participants, the adapter must define a bootstrap mechanism without altering core protocol fields.

### Direct delivery

Once a peer is discovered, the adapter SHOULD support delivery to its cached native identity.

### Reply context

Native threading/replies MAY be used for presentation. `MESSAGE-ID` / `IN-REPLY-TO` remain available for transport-independent correlation.

### Security

Authentication, group/channel allowlists and credentials belong to the adapter. A self-declared `FROM` or `ROLE` is never sufficient authentication.

## Adapter state

Adapters MAY cache:

- native peer IDs;
- GZCoord address mapping;
- last native message IDs;
- session-level deduplication data;
- connection state.

They SHOULD NOT create project workflow records or source ownership state.
