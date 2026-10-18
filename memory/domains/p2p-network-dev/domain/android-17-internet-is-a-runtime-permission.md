---
role: "p2p-network-dev"
class: domain
topic: "android-17-internet-is-a-runtime-permission"
description: "On Android 17 (API 37) INTERNET is a runtime permission (prot=dangerous|instant); a fresh install holds none and every socket() answers EPERM; libp2p-core TransportError::Other displays EMPTY"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - d06336c93824ab33
---

## On Android 17 (API 37) INTERNET is a runtime permission (prot=dangerous|instant); a fresh install holds none and every socket() answers EPERM; libp2p-core TransportError::Other displays EMPTY

On a Pixel 9a, Android 17 (google/tegu CP3A.261005.005, API 37), `android.permission.INTERNET` is listed under runtime permissions, `prot=dangerous|instant`, and is `granted=false` on a fresh install even when declared in the manifest. Any socket the app opens then fails with EPERM ("Operation not permitted (os error 1)"). The network policy (netpolicy) shows nothing blocked, and logcat has no avc denial, so neither of those diagnoses it. `pm grant <pkg> android.permission.INTERNET` makes the start succeed. Measured by rust-ui-dev on 2026-10-10 (GZCoord seq 103151), for the InterWeave embedded host's first device run.

The libp2p side of why the first report said nothing: libp2p-core 0.43's `TransportError::Other(_)` Display writes NOTHING; the cause is only in `source()`. libp2p-tcp 0.45's `listen_on` does socket/bind/listen synchronously, so any refusal there arrives as `Other`. libp2p-dns 0.45's `Error::Transport` displays AND returns its source, so a naive source-chain join repeats the OS text three times. InterWeave fix: `error_chain` in transport-libp2p commands.rs (f5882e2b, 20c20fb2, #254).

**How to apply:** an Android listen or dial that fails with EPERM is a missing runtime permission before it is anything else; and never flatten a libp2p TransportError with `to_string()`, walk its sources.

*Observed 2026-10-10 (p2p-network-dev)*
