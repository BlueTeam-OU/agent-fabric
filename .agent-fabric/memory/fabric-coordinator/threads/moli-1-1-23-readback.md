---
role: "fabric-coordinator"
class: threads
topic: "moli-1-1-23-readback"
description: "j750 moli pin 1.1.19 -> 1.1.23: my own read-back of both sha256 on 2026-11-11, the empty-dump behaviour change to document, and what the bump touches"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7291b9a21a9488ac
---

## j750 moli pin 1.1.19 -> 1.1.23: my own read-back of both sha256 on 2026-11-11, the empty-dump behaviour change to document, and what the bump touches

j750 (devex-tooling REQUEST 01a1c620; the owner said on 2026-11-11 to execute it).

I read it back myself on 2026-11-11 from develop-qzapp, downloading the archive with curl from the v1.1.23 release URL:
- moli-x86_64-unknown-linux-gnu.tar.gz is 45237445 bytes, sha256 df360c04e567ce2e56a8391a03dc677d794465848b5821f944d2de10f3f1f430.
- The member moli-v1.1.23-x86_64-unknown-linux-gnu/moli has sha256 109bf352cd1ec2683cbe5a35995d571f111f9578956c853d784e69557e0d7726.
- `moli --version` prints "moli 1.1.23".
These equal devex-tooling's values. The download was removed afterwards.

What the bump touches, as 5383900a did for 1.1.19:
- projects/registry.json: all 14 moli rows (version, download URL, archive sha256, member path);
- ADR-051 rule 1: the version and both sha256, the Amendments row, history/ADR-051-amendments.md, the DIGEST lines, and index.json via `adr.py index --write`.

Also add one line to ADR-051 or the moli-web skill: an empty dump that exits 0 means the page wasn't ready, so add --wait-selector. On Fedlex with the default wait, 1.1.23 gives 0 bytes where 1.1.19 gave a 1.2 KB splash.

Do not touch: the legal-expert slice that quotes 1.1.19 as a tested example.

Acceptance: `fabric-ctl all tools-install moli` installs 1.1.23 on every account. REPLY devex-tooling naming the PR.

#557 was armed at 49b87fcc when the switch ran; the j750 PR opens only after it merges (one open PR).

*Observed 2026-11-11 (fabric-coordinator)*
