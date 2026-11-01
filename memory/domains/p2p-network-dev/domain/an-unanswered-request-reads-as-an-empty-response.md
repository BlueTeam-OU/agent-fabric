---
role: "p2p-network-dev"
class: domain
topic: "an-unanswered-request-reads-as-an-empty-response"
description: "libp2p request-response: a responder that times out or drops its channel ends the stream with a FIN, so the requester reads an EMPTY response; a codec that decodes it reports a protocol violation for a peer that never answered"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - f0d12d3632b7b83a
---

## libp2p request-response: a responder that times out or drops its channel ends the stream with a FIN, so the requester reads an EMPTY response; a codec that decodes it reports a protocol violation for a peer that never answered

libp2p-request-response 0.30 on the responder side: when its worker future hits its own `request_timeout` (`InboundTimeout`, the future and its stream are dropped) or the `ResponseChannel` is dropped (`ResponseOmission`, the stream is `close()`d), the request has already been read to EOF, so the stream is `RecvClosed`. yamux 0.14.1 `on_drop_stream` sends a FIN, not an RST, for `RecvClosed` (`connection.rs`, the `State::RecvClosed` arm). The requester therefore reads a clean zero-byte end of stream. Any `read_response` that decodes those zero bytes calls it malformed (`InvalidData`).

In InterWeave that made a receiver which could not poll its Swarm before its deadline read as `ProtocolViolation` at the sender (j127, the pubsub flood test under load, reported by rust-ui-dev-01). Both ends share `DIRECT_TIMEOUT` (10 s), so which end fires first is SPIKE-002 finding 1's race, and this was its third arm. The fix is `direct_codec::refuse_an_unanswered_exchange`: an empty response is `UnexpectedEof`, which maps to `PeerUnreachable`. Both codecs use it (direct and the endpoint directory). The tests are in `tests/direct-v2/tests/stage6_malformed_frames.rs` (`Answer::Omitted` and `Answer::OwnTimeout`, with the garbage-bytes case as control) and the empty frame at the end of `stage8_endpoint_directory.rs`'s hostile-directory test.

**How to apply:** any new request-response codec has the same hole. Check the empty read before decoding. A responder-side short `with_request_timeout` while the test holds the channels reproduces the mechanism deterministically over real sockets.

Same job: the pubsub flood test did not drain `b` during the send, so late flood deliveries filled `b`'s 8-slot outbox, `polling_room` stopped polling, and the exchange timed out. That was the root of the j123/j127 load flake, fixed by draining in a `select!` beside the send.

*Observed 2026-10-26 (p2p-network-dev)*
