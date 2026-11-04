---
role: "python-dev"
class: solution
topic: "assembler-flat-file-topic-and-links-j163"
description: "assembler flat class file records its topic; second topic splits; links pointed late must be pointed in claims, disk and the pre-pass alike (#368)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - eea21fbbb8b4d4a9
---

## assembler flat class file records its topic; second topic splits; links pointed late must be pointed in claims, disk and the pre-pass alike (#368)

#368 (merged 2026-10-24): a flat `<class>.md` records `topic:` (writer `flat_topic`); `plan_classes` splits the class when a drain brings a topic the file does not hold; older files without a topic keep the crossref reading (known = empty).

**Why:** four blind-review rounds each found a new seam in the link pointing (`[[memory]]` to the slice stem): same-run only (F2), a link-blind `undated` hiding real collisions (F3), disk edits before the refusals (F4), pre-pass reading raw disk text (F5), double-pass over role+shared maps (F6).

**How to apply:** any rewrite of text the corpus compares must be applied to three readers with the same single map: the incoming claims, the sections on disk (written only after every refusal, `Run.disk_links` then `point_disk`), and the collision pre-pass (`pointed`). Never loosen `undated`. Three older tests (harvest merge_target, carried-file, flat two-topic) had to build a legacy flat file by hand or read the directory; CI's platform-smoke caught the one my local summary hid, so grep the suite log for every `Traceback`, not just the FAILED_SUITES line. Related: [[facade-split-monkeypatch-trap]].

*References: facade-split-monkeypatch-trap, memory*

*Observed 2026-10-24 (python-dev)*
