---
role: "python-dev"
class: workflow
topic: "rereview-brief-retyped-by-hand-drifts"
description: "a re-review brief is ~33KB and must be pasted into the Agent prompt by hand; retyping drifted (renamed test, garbled def) — copy exactly, and a same-run section_writers key needs popping"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 054be5b0effc3d5d
---

## a re-review brief is ~33KB and must be pasted into the Agent prompt by hand; retyping drifted (renamed test, garbled def) — copy exactly, and a same-run section_writers key needs popping

j90 (PR 472): `fabric-review next` rendered a 33KB re-review brief (it embeds the whole previous report and the diff). The Agent prompt has to carry it verbatim, and my retyping changed a test name and garbled a `def` line in the embedded diff; the reviewer caught one and read the pinned head instead.

**Why:** the guard never reads the prompt, so nothing flags drift; a reviewer led by a wrong diff could raise false findings.
**How to apply:** copy the brief file's lines exactly, diff included; after the review, say in the hand-off if the paste was not byte-exact. Also: `section_writers_gone` strikes only the *previous* report's keys (slices.merge_report), so a writer a run records and then retires itself must be popped from `run.section_writers` (writer.retire_writers). A full run.sh can fail one unrelated suite once (test_jobs_switch "memory directory has not changed") and pass alone; run the file alone and state it in the arming basis.

*Anchors: `tools/fabric/assembler/writer.py::retire_writers`*

*Observed 2026-11-04 (python-dev)*
