---
role: "rust-services-dev"
class: solution
topic: "interweave-bridge-size-load-figures"
description: "InterWeave Claude bridge size limits and load behaviour, measured in tests/desktop-e2e (#375, #379; 2026-10-22); the host-line bound and its two-form measure"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3ba4f8d707ffc674
---

## InterWeave Claude bridge size limits and load behaviour, measured in tests/desktop-e2e (#375, #379; 2026-10-22); the host-line bound and its two-form measure

Measured against two real daemons in tests/desktop-e2e/tests/claude_channel.rs (#375 merged 2026-10-22; #379 holds the 256-byte meta bound as a channel-core unit test).

**Host-line bound.** CHANNEL-EVENT.md §Content: one event is at most 320 KiB. The measure is the LARGER of two forms:
- the push line;
- the pulled form: `receive`'s `{kind, content, meta}` escaped a second time as tool-result text, without the outer quotes.

A control character costs 6 bytes pushed and 7 pulled. #376 (rust-services-dev-02) carries an oversize UTF-8 text as base64url of the recovered bytes. Before #376 the worst cases were:
- plain: 295,309 pushed / 344,452 pulled;
- ;ce=br: 1,180,109 / 1,376,712.

After #376 they are 65,938 / 65,929 and 262,610 / 262,605. #330's 1 MiB ceiling bounds only what the bridge READS.

**Pull mode.** A full pull queue stops the bridge reading its socket. The daemon then closes it as wedged 70–100 s later under the shipped keepalive (30s/10s/3), and what the pipeline held is lost after Accepted. Measured at queue 16 with a 120 s pause: 220 accepted, 124 lost. Inside the window: none lost. This is the contract's stated behaviour, and the threshold is now named in CHANNEL-EVENT.md and TOOL-SURFACE.md.

**Push mode.**
- 64 direct sends: all 64 notified once each.
- 200 broadcasts: 37–40 delivered, within the ingress bucket (32 burst, 120/min). The bucket drops silently with no counter, and broadcast order is not preserved.

**Test lessons:**
- The bucket constants are read from the runtime's source (`source_const`), because desktop-e2e must not gain a dependency.
- A load loop's wait for the first accepted send needs ONE deadline over all refusals, not one per error arm (round-5 F8 of #375).
- Before the first send, PeerUnreachable is a connection race, not a failure.

*Observed 2026-10-22 (rust-services-dev)*
