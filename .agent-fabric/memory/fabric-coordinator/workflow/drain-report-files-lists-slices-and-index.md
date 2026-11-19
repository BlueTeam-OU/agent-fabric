---
role: "fabric-coordinator"
class: workflow
topic: "drain-report-files-lists-slices-and-index"
description: "Briefing a review of a drain commit — last-drain-report.json \"files\" lists slices and INDEX.md only, never crossref.json"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - cb3ec6b4c65c56ae
---

## Briefing a review of a drain commit — last-drain-report.json "files" lists slices and INDEX.md only, never crossref.json

A drain's `last-drain-report.json` `files` (and `files_written`) holds what the
assembler appended to `run.written`: slices and each role's INDEX.md
(tools/fabric/assembler/index.py:279, writer.py, report.py:266-272). `crossref.json`
is written (index.py:224) and never listed. So a review brief for a drain commit
says "the report lists the slices and indexes written", not "every file the
commit writes"; the stronger wording raised F4 on blueteam.ee #16 (2026-11-02),
judged not-real by the review class.

**Why:** a requirement the dispatcher invents becomes a finding the review class
then has to dismiss: one extra adjudication round.
**How to apply:** take a drain brief's requirements from memory/README.md and the
assembler's contract, not from what the report's field name suggests.

*Observed 2026-11-02 (fabric-coordinator)*
