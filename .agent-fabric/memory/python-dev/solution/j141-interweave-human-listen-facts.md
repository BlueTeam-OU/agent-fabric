---
role: "python-dev"
class: solution
topic: "j141-interweave-human-listen-facts"
description: "measured behaviour of interweave-human listen --json --input --consume (0.2.0), scratch two-profile recipe, size bound, what the render lacked"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e35d66a1d7c041f5
---

## measured behaviour of interweave-human listen --json --input --consume (0.2.0), scratch two-profile recipe, size bound, what the render lacked

j141 (ADR-029 rule 18, control carrier), measured 2026-11-12 with two scratch profiles (own XDG_* dirs under a short path, `transportctl --profile X identity init`, hand-written config.yaml with `fabric-control` as `allowed_client_kinds: [human-client]` beside `gzcoord` automated, `transport-daemon --profile X`):
- The live gzcoord profile's rendered config (`tools/fabric/gzcoord/carrier/roster.py render_config`) had NO fabric-control endpoint: `interweave-human --profile gzcoord listen` answers "configures no endpoint a human client may use". The render change belongs to this job.
- Events (one JSON per line): `{"event":"session","session":"ready"}`, `connectivity`, `path`, `outbound` (`id` p<n>, `ref`, `status` accepted, `problem` null — printed TWICE per send, dedupe by ref), `input-refused` (`reason`, `ref` or null), `message` (`author` = sender PeerId, `conversation` "<peer>/fabric-control", `local_endpoint`, `text`, `id` u<n>, `direction` in).
- Input line: `{"send":{"conversation":"<peer>/fabric-control","text":...,"ref":...,"pending":false}}`. EOF on stdin stops reading (a FIFO with no writer then blocks the next open): drive it with subprocess pipes held open, never a shell FIFO.
- Size: random base64 texts of 32768, 49152, 60000 bytes accepted and received whole; 66000+ got no outbound in 4 s. So a 32 KiB part is well inside.
**Why:** next session need not re-measure. **How to apply:** fake child fixture must print outbound twice and echo this shape.

*Observed 2026-11-12 (python-dev)*
