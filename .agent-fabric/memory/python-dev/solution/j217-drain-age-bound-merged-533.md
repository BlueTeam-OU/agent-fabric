---
role: "python-dev"
class: solution
topic: "j217-drain-age-bound-merged-533"
description: "j217 merged in #533 — drain age bound reads the committed watermark under --all; AUTHORIZES must be a header; mtime ms test trap"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a217df8c483597f2
---

## j217 merged in #533 — drain age bound reads the committed watermark under --all; AUTHORIZES must be a header; mtime ms test trap

#533 (2026-11-09): `harvest_memory.py` measures `oldest_drainable_ms` and the new report key `drainable` against `previous_watermark` also under `--all` (held memories count at any age; bundle content unchanged); `ops/memory.py` passes `drainable` through; `drain_due.store_of` reads it, falling back to claims + held when absent (older control agent).

- `previous_watermark` caught OSError/ValueError/TypeError but not AttributeError: a committed report that is valid JSON and not an object crashed the harvest. Round-1 P3, fixed in the same PR; the class is "a loader of a committed file treats a wrong shape as absent".
- Test mtimes: `os.utime` with a float of ms/1000 truncates (wm+7 read back as wm+6); use whole-second offsets (wm+2000).
- `fabric-pr arm --authorization` reads `AUTHORIZES:` from the message *header* beside TO, never the body; the coordinator's first REPLY had it in the body and arm refused. Ask for a resend with the full sha as a header.
- A security-boundary path (even one allowlist key in ops/memory.py) arms under 8 work commits only on the coordinator's AUTHORIZES; ask for it in the REPLY that names the PR.
- Cross-check: [[post-review-bare-and-verbatim]] — when writing the report file, copy every dispatch-block line (I dropped `review_id` once and had to add it back before posting).

*References: post-review-bare-and-verbatim*

*Anchors: `tools/fabric/harvest_memory.py::age_since_ms`, `tools/fabric/drain_due.py::drainable`*

*Observed 2026-11-09 (python-dev)*
