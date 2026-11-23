---
role: "p2p-network-dev"
class: domain
description: "What libp2p-autonat 0.15.0's v2 CLIENT actually does — measured, and contradicting several accepted documents"
tier: 2
knowledge_scope: full
distilled_at: "2026-09-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 413bf20d1905f6fc
---

## What libp2p-autonat 0.15.0's v2 CLIENT actually does — measured, and contradicting several accepted documents

Measured 2026-09-09 by reading `libp2p-autonat-0.15.0/src/v2/`, not inferred. Each fact falsified something written down:

- **The client NEVER dials.** Its only `ToSwarm` variants are `ExternalAddrConfirmed`, `GenerateEvent`, `NotifyHandler` (`client/behaviour.rs` 202/238/302) — a probe rides an already-open connection. The dial in AutoNAT v2 is the SERVER's dial-back (`server/behaviour.rs:124`). So step 3 reaches CLAUDE.md §1's routes **2 and 3**, not 1 and 3, and the outbound gate never sees probe traffic.
- **Eligible servers are the ones this profile DIALLED**, not "connected peers": `dial_request::Handler` is installed only in `handle_established_outbound_connection`, and `supports_autonat` is set only from that handler. A peer that dialled us is never a probe server. `random_autonat_server()` picks uniformly over CONNECTIONS, so a peer with two outbound connections is drawn twice.
- **No hook to rank, prefer or veto a server.** Whole public API: `with_max_candidates`, `with_probe_interval`, `new`, `validate_addr`. AUTONAT.md §3's static-precedence rule was therefore unimplementable → owner ruled 2026-09-09 to amend §3 and ADR-0035 rather than re-implement selection.
- **Only two knobs exist, and neither is in-flight count or timeout.** `with_probe_interval` (DEFAULT 5 SECONDS — sixty times §4's refresh, so an adapter that forgets floods every dialled server) and `with_max_candidates`. In-flight requests and the per-probe timeout are hard-coded 10 and 10 s in one `FuturesMap` at `v2/client/handler/dial_request.rs:94`. §4 said 15 s and nothing could make it so; the three knobs naming them were deleted 2026-09-09.
- **A candidate is tested ONCE, ever.** The tick sweeps only `TestStatus::Untested` (`behaviour.rs:319-321`); a result leaves it `Received` (`:166`) or `Failed` (`:232`); only `UnsupportedProtocol`/`Io` reset (`:212,223`); re-reporting an address only raises its score (`:108-112`); `validate_addr` is `#[doc(hidden)]` and only SETS `Received` (`:364`). So `required_distinct_successes: 2` is unreachable and there is no refresh — the finding that forced [[vendored-autonat-client]].
- **Two paths leave a candidate `Pending` for ever with no event**: a server reporting success when no dial-back arrived (`:186-198`), and a request dropped because the handler's ten-slot `FuturesMap` was full (`handler/dial_request.rs:99-113`) AFTER the status was set.
- **No probe-START event** — only completion, so nothing outside the behaviour knows a dial-back is expected.
- **`Event` is emitted for exactly two results**: `Ok(())` and `Err(AddressNotReachable)`. `UnsupportedProtocol` and `Io` emit NOTHING and reset the candidate to `Untested`. So an adapter must map `Ok`→Reachable, `AddressNotReachable`→Unreachable, and nothing else arrives.
- **§6 is violated by the crate pairing, and is UNRESOLVED**: `libp2p-identify` pushes `NewExternalAddrCandidate` for every address a peer *claims* to have observed (`identify/behaviour.rs:370`), and the client probes exactly that set — the "arbitrary remote-supplied addresses" §6 forbids. Recorded in AUTONAT.md's Amendment 2026-09-09; the next owner decision.

**Why:** these are the facts every remaining Stage 11 AutoNAT step rests on, and four accepted documents said otherwise until they were measured.
**How to apply:** before writing AutoNAT code or prose, check against these rather than against the design docs alone. See [[stage-11-progress]], [[measure-the-linter-before-asserting]].

*References: measure-the-linter-before-asserting, stage-11-progress, vendored-autonat-client*
