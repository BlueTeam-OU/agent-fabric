---
role: "fabric-coordinator"
class: solution
topic: "render-rereads-checkpoint"
description: "review_brief render() reads a PR re-review's checkpoint a second time after refusals(); a refusal it drops becomes a crash downstream"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 09c4479fa1701a1d
---

## review_brief render() reads a PR re-review's checkpoint a second time after refusals(); a refusal it drops becomes a crash downstream

review_brief.render() calls refusals() (which runs resolve_range, a GitHub read of the PR's checkpoint) and then resolve_range again. Until j573 the second call's refusals were dropped (`info, _ =`), so a second read finding no checkpoint fell to `req["previous_findings"]` → KeyError (reported from a re-review after an adjudication). Fixed on #465, commit 6d0588ea: render raises the refusal. Any other `info, _ = resolve_range(...)` (prepare_evidence, review_rounds) relies on that raise or its own None check, so check the same thing whenever a new caller is added.

Also: a code comment in tools/ naming a managed project (e.g. the project's name) fails corpus lint ("names a managed project in a generic file"); cite the job instead.

*Anchors: `tools/fabric/review_brief.py::info, refused = resolve_range(req)`*

*Observed 2026-11-03 (fabric-coordinator)*
