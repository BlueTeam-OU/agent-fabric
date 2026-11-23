---
role: "p2p-network-dev"
class: domain
topic: "release-notices-crates-without-licence-files"
description: "About 40 Linux-build crates (libp2p family, multistream-select, rw-stream-sink, taffy, ...) publish no LICENSE file; a notices tool that scans file names drops their MIT/BSD notice"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 8cad9aa83baa3ac4
---

## About 40 Linux-build crates (libp2p family, multistream-select, rw-stream-sink, taffy, ...) publish no LICENSE file; a notices tool that scans file names drops their MIT/BSD notice

A crates.io crate can declare `license = "MIT"` and ship no LICENSE file: libp2p-core 0.44.0 and the
other 21 libp2p crates keep the MIT notice only in the src/lib.rs header; taffy, uuid-simd, base45
and others keep it nowhere. A third-party-notices generator that collects LICENSE*/COPYING*/NOTICE*
by name lists them by expression alone, which drops a notice MIT and BSD require in every copy.
Found by Codex on InterWeave #324 (2026-10-21); since 56d0ae4a release_notices.py refuses such a
crate, and ADR-0058 (proposed) says how the notice is derived: header extract, else standard text
under the `authors` line, with a reviewed list in tools/ci. The derivation is job j99.

**Why:** cargo-deny's licence check passes these crates — it reads the expression, not the notice.
**How to apply:** for any artifact that ships compiled dependencies, check for crates that publish
no licence file before trusting a notices file; count them from the registry sources, not the README.
Also: when a reviewer names a defect in one release script, sweep its siblings in the same pass —
#324 took three Codex rounds for one cleanup-order class across release_android_apk.sh,
release_linux_archive.sh and skia_prebuilt.sh. [[review-loop-same-invariant-escalate]]

*References: review-loop-same-invariant-escalate*

*Observed 2026-10-21 (p2p-network-dev)*
