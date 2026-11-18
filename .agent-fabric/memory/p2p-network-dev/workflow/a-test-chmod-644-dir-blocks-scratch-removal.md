---
role: "p2p-network-dev"
class: workflow
topic: "a-test-chmod-644-dir-blocks-scratch-removal"
description: "rm -rf of old scratch fails \"Permission denied\" on a dir a test left mode 644 (no x); chmod u+rwx that dir, chmod -R cannot reach inside it"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9a941311cb6a277c
---

## rm -rf of old scratch fails "Permission denied" on a dir a test left mode 644 (no x); chmod u+rwx that dir, chmod -R cannot reach inside it

In the j171 hygiene round (2026-11-16), ~/agent-fabric-tmp/.tmpXXXX from an
InterWeave systemd-unit test held `config/systemd/user/.elsewhere` at mode
644: no traverse bit, so `rm -rf` and `chmod -R u+w` both fail with
Permission denied on the entry inside. Fix: `chmod u+rwx` on the directory
itself, then rm. Also: fabric-jobs tidy did not list nested build trees
(spikes/spike-004/phase-b/node/target, spike-009/device/harness/target),
so check `git status --ignored` after tidy. Reported to fabric-coordinator as
OBSERVATION 01a1e21b-246a-7705-942f-5d7acfb1539a.

**Why:** a test that makes a directory unreadable on purpose has to restore
the mode in its own teardown, or the leftover blocks scratch cleanup.
**How to apply:** when removing scratch, stat a dir that refuses before you
escalate; in InterWeave tests that chmod, restore the mode in a drop guard.

*Observed 2026-11-16 (p2p-network-dev)*
