---
role: "python-dev"
class: solution
topic: "j206-refusal-record-keep-merged-492"
description: "Fixturing seed_child's clone-path vs rebuild-path refusals (off/on the fabric's main, unsigned remote vs bundle); one helper keeps or reports the record"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8ba09983066d62c6
---

## Fixturing seed_child's clone-path vs rebuild-path refusals (off/on the fabric's main, unsigned remote vs bundle); one helper keeps or reports the record

#492 (merged 2026-11-05, 1 work 1 fix) made `mirrors._keep_refusal` the one place that moves a mirror's refusal record beside it or returns the "could not be kept at <path>" clause; seed_child's clone branch and `_rebuild_mirror` both use it.

Fixture traps in tests/test_first_contact.py: seed_child takes the clone path only while the child is OFF the fabric's main (point the fabric's refs/remotes/origin/main at its root commit, restore after); on main it rebuilds from `--remote`, so the rebuild refusal needs a bare remote holding an unsigned commit — an unsigned commit only in the bundle passes the rebuild and refuses later in _seed_take, leaving the mirror. A non-empty directory at `<id>.refusal.json` makes os.replace fail. Rename the mirror aside, never rmtree, when a later section needs it.

**Why:** the review (round 1 F1) caught that fixing only the clone branch left the rebuild's message without the path.
**How to apply:** a rule stated for two sites goes into one helper in the first commit.

*Anchors: `tools/fabric/secretstore/mirrors.py::_keep_refusal`, `tests/test_first_contact.py::bad_remote`*

*Observed 2026-11-05 (python-dev)*
