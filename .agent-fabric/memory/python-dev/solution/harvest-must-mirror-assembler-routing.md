---
role: "python-dev"
class: solution
topic: "harvest-must-mirror-assembler-routing"
description: "a harvest-side recomputation of what the assembler rendered must use the assembler's routing predicate (shared_with minus own role), and fabric-review next needs a commit-pinned range"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f3f3316e69b58c71
---

## a harvest-side recomputation of what the assembler rendered must use the assembler's routing predicate (shared_with minus own role), and fabric-review next needs a commit-pinned range

j204 (#486): the harvest keys a memory as written or as the assembler points its links
(`tools/fabric/corrections.py` holds `point_text`, `applied_stems`, `unique_stems`, `names_in`).
The review's only finding was a routing mismatch: a memory whose `shared_with` names only the
harvesting role stays in the role's slice (`intake.py` discards the role from the owners), so the
harvest points it with `(role, None)`; with a real co-owner it points with `(None,)` only.

**Why:** a recomputation on the harvest side that approximates the assembler's decision errs
toward a wrong key, and a wrong key on the applied lookup re-harvests a correction.
**How to apply:** copy the assembler's predicate (`set(shared_with) - {role}`), not its intent;
give the test one case per branch of it. A carried risk: the harvest rebuilds the map from the
committed report alone, so same-run unlisted moves and legacy entries without `applied_key` can
still be re-harvested (errs toward filing twice, never losing a correction).

`fabric-review next` refuses `range: origin/main..HEAD` ("head 'HEAD' is not a commit id"): pin
the request's range to `<base sha>..<head sha>` before deriving a re-review.

*Anchors: `tools/fabric/harvest_memory.py::keys_of`, `tools/fabric/corrections.py::unique_stems`*

*Observed 2026-11-05 (python-dev)*
