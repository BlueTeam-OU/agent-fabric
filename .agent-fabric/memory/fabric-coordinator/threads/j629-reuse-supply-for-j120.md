---
role: "fabric-coordinator"
class: threads
topic: "j629-reuse-supply-for-j120"
description: "j629 closed: gavel's MIT notice for tools/fabric/review_calibration.py is in REUSE.toml (e683ba88, 2026-11-07)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6f3a63779681e59b
---

## j629 closed: gavel's MIT notice for tools/fabric/review_calibration.py is in REUSE.toml (e683ba88, 2026-11-07)

2026-11-07, closed. ADR-066's reader `fabric-review-calibration` (python-dev-02's j120) ports gavel's calibration arithmetic, which is MIT.
The notice landed as e683ba88 ("REUSE: gavel's MIT notice for the ported review_calibration.py", j629): LICENSES/MIT.txt and a REUSE.toml
override for tools/fabric/review_calibration.py, "Apache-2.0 AND MIT", with gavel's tree at 27ff6e1d as the contributor. Nothing is left to supply.

Decided earlier with python-dev-02 (REPLY 01a1b644): the split is sha256 of the coordinates, big-endian, 0 dev and 1 held-out; labels come
from PR reviews (v2) only; the coordinator commits labels.jsonl.

*Observed 2026-11-08 (fabric-coordinator)*
