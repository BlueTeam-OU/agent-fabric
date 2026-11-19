---
role: "fabric-coordinator"
class: workflow
topic: "coordinator-memory-lands-in-cwd-project"
description: "A fabric-coordinator memory about agent-fabric written while standing in a project working copy is harvested as that project's, and the drain writes it into a corpus that binds no fabric-coordinator"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7b3fd82b107f9300
---

## A fabric-coordinator memory about agent-fabric written while standing in a project working copy is harvested as that project's, and the drain writes it into a corpus that binds no fabric-coordinator

2026-11-09, blueteam.ee #17 (j657): the 2026-11-08 drain wrote three of my memories into
blueteam.ee/.agent-fabric/memory/fabric-coordinator/. I had written them in the j498 session,
which stood in a blueteam.ee working copy, so Claude Code saved them in that working copy's
memory folder, and the harvest attributes a memory to the project its folder belongs to.
blueteam.ee's taxonomy binds no fabric-coordinator. The review class found it (F1), and I moved
the three files to the agent-fabric memory folder.

**Why:** the harvest goes by where a memory was written, not by what it is about, and the
assembler did not check the role against the project's taxonomy (j677, contracted to
python-dev-03 on 2026-11-09).
**How to apply:** a memory about the fabric written from a project session goes in the
agent-fabric project memory folder (~/.claude/projects/-home-user-projects-agent-fabric/memory/),
never this session's own folder. Before arming a drain half, grep its range for
`fabric-coordinator/`.

*Anchors: `tools/fabric/assembler/index.py::the project's taxonomy binds`*

*Observed 2026-11-09 (fabric-coordinator)*
