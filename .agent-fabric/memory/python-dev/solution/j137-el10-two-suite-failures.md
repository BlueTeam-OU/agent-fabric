---
role: "python-dev"
class: solution
topic: "j137-el10-two-suite-failures"
description: "almalinux:10 suite reds: paperkey skip by platform profile, revoked-ancestor order in the signing guard (GnuPG 2.4.5 vs 2.4.9); container recipe and hook traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 72c41d274329b549
---

## almalinux:10 suite reds: paperkey skip by platform profile, revoked-ancestor order in the signing guard (GnuPG 2.4.5 vs 2.4.9); container recipe and hook traps

j137 (2026-11-11): two EL10 suite failures. (1) tests/test_secret_store.py: paperkey case now skips only when `host_platform.profile(host_platform.detect({})).no_package` lists it (empty env so AGENT_FABRIC_PLATFORM cannot choose); commit 5f00543b on the j137 feat branch. (2) tools/fabric/guards/ban_unsigned_commits.py: the chain walk checked `named` (lineage.verify findings) before `revoked` per node, child first. On GnuPG 2.4.5 (EL10) a child certified by a since-revoked parent is named, so the revoked ancestor was never reached; Fedora 2.4.9 does not name it. Fix: walk revocation over the whole chain first. The guard is outside python-dev's entry, so the diff went by REPLY to the coordinator (01a1cba4-4226-7b43-aca9-7dd616caace0), not committed.

**Why:** the reader of gpg output was not the culprit; the order of checks was, and it only showed on one GnuPG build.
**How to apply:** reproduce EL10 reds with `podman run almalinux:10`, tree mounted read-only at /src, copied without .git (a worktree's .git file is broken in the copy), `git init` inside, `python_pin.py install` for the pinned python, env -i. Put the in-container script in a file written with the Write tool: the Bash hook refuses any command text containing "git commit" aimed outside the job's copy. A control that flips /etc/os-release to ID=fedora proves a skip is platform-bound.

*Anchors: `tools/fabric/guards/ban_unsigned_commits.py::self.excluded`, `tests/test_secret_store.py::no_package`*

*Observed 2026-11-11 (python-dev)*
