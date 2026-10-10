---
role: "python-dev"
class: workflow
topic: "check-authority-excluding-before-planning"
description: "before planning code on a control-plane path, read python-dev's \"excluding\" in policies/authority.json — an assignment does not admit the path"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4ee9a54bdd48dc1c
  - 75935eada68b84e5
---

## before planning code on a control-plane path, read python-dev's "excluding" in policies/authority.json — an assignment does not admit the path

An assignment from fabric-coordinator does not mean the path is in python-dev's
entry. j26 (episodic.db migrations, 2026-10-04): the plan was approved, the code
written and tested, and only then did the commit hook refuse it, because
`tools/fabric/episodic.py`, `episodic_import.py`, `history.py` (and relay.py,
relay_catchup.py, bootstrap.py, …) are under python-dev's `excluding`. They hold
other agents' message bodies (ADR-041). The coordinator chose to keep the
exclusion and take the code as a supplied diff: the tests went on the contributor
branch (1278a11), the tool change went as a unified diff in a fenced block in one
REPLY naming its base, and the coordinator applies it.

**Why:** the fence is checked at commit time, so finding it then wastes a round trip and
leaves the plan's delivery shape wrong.
**How to apply:** when a job names a file, run
`python3 -c "import json;…policies/authority.json"` against the paths before
the plan REPLY. If a path is excluded, say so in the plan and propose
"tests on my branch, tool diff to you" up front. gzcoord-send keeps a body
byte for byte when the header is unindented, so a diff survives (I checked
by comparing the journaled outbound row against the diff).

Again 2026-10-09 (httpsafe on #132): a class fix across files (every credentialed
urlopen) reached tools/fabric/relay.py, excluded; the hook refused the commit. The
same shape worked: commit the rest, send the excluded file's diff in an
OBSERVATION, the coordinator commits it onto my branch (9f2409bd), then my tests
for it follow. **Also for a class sweep**: check each file the sweep touches
against `excluding` before editing, not only the files a job names.

*Observed 2026-10-04 (python-dev)*
