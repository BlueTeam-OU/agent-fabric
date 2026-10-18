---
role: "rust-ui-dev"
class: domain
topic: "error-display-source-chain"
description: "Diagnosing an opaque Rust error from a device -- Display can be empty, the cause sits in source(); never flatten an error with to_string()"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3de0937e4104b060
---

## Diagnosing an opaque Rust error from a device -- Display can be empty, the cause sits in source(); never flatten an error with to_string()

An embedded runtime failed on a phone with Internal("substrate: transport: ") -- an empty
message. libp2p-core 0.43's TransportError::Other displays as nothing; the io::Error
(socket/bind/listen refusing) was only in its source(), and the code flattened it with
to_string(). Any error that crosses a layer as text must be formatted with its whole source
chain, or the device report is useless and needs another round trip to the phone. When a
device-only failure comes back opaque, ask first for the errno (EACCES points at the
platform restricting the app's network -- on Android 17 the INTERNET permission is
runtime-granted; EADDRNOTAVAIL/EAFNOSUPPORT at the address family).

*Observed 2026-10-15 (rust-ui-dev)*
