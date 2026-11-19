---
role: "python-dev"
class: workflow
topic: "j158-test-speed-next-round-merged"
description: "j158 #634 merged 2026-11-17 (7 work, 1 fix): what sped the suites up, measurement and review traps"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6c6347805a2b1bc8
---

## j158 #634 merged 2026-11-17 (7 work, 1 fix): what sped the suites up, measurement and review traps

#634 merged on the coordinator's word to arm at 7 (REPLY 01a1e686), after CI green and one blind review of the whole head.

What worked: fake watch bodies that trap-kill their `sleep` child (a captured pipe waits for it); the existing seam AGENT_FABRIC_OPERATOR_CLONE_URL so bootstrap clones from an empty local bare repo; PYTHONPYCACHEPREFIX in a per-case tmp instead of PYTHONDONTWRITEBYTECODE; `-S` on fake interpreters; recording a poll's sleeps instead of waiting; bootstrap_cli GROUPS rebalanced by measured case cost.

**Why:** host load swings CPU ~15%, so only old/new files alternated back to back (2 rounds each) are comparable; my first REPLY overstated the gain and needed a correction. A measured "nothing" (pre-compiled pyc, hard-linked trees, work_lifecycle shared pycache, message_transport) goes in the PR body.

**How to apply:** measure by alternation before claiming; a test commit command with `$HOME` in it is refused by the job-copy guard (run lint in a separate call); `fabric-review save N 1 < report` before `fabric-review next` for a fix-range re-review; `fabric-pr post-review` must be the bare command; labels that embed the scratch dir name must be normalised before diffing; 7 extra real-codex labels in review_codex appeared in some runs, cause unknown.

*Anchors: `tests/test_session_start.py::WATCH_BODY`, `tests/test_bootstrap_cli.py::GROUPS`, `tests/test_gzcoord_protocol.py::in_parallel`*

*Observed 2026-11-17 (python-dev)*
