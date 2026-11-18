---
role: "python-dev"
class: solution
topic: "j135-almalinux-profile-pr554"
description: "j135 — almalinux platform profile, PR 554 head 23fabeff, review r1-r3 clean, waits on owner's arm word; EL10 package facts"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d9852982002a2f37
---

## j135 — almalinux platform profile, PR 554 head 23fabeff, review r1-r3 clean, waits on owner's arm word; EL10 package facts

#554 (1 work, 2 fix at 23fabeff): profile `almalinux`, detect only ID=almalinux; Rocky/RHEL and AlmaLinux+Qubes marker stay unknown. REPLY to develop-qzapp/user sent (seq 1012513) with package list and CI leg text; schema enum and .github are the requester's.

**EL10 facts (measured in almalinux:10.2 via podman):** Fedora names hold; gh, kitty, ShellCheck are EPEL (install epel-release first); paperkey is in no repo (Profile.no_package, audit says install by hand); python3 is 3.12 < host floor 3.13 (open for the owner); minimal image has coreutils-single, needs --allowerasing.

**Traps:** platform/*.sh match the security boundary: arm needs the owner's word (1 work commit). `fabric-pr post-review` must be the bare command with `< file`. Re-review brief: paste the rendered `fabric-review brief` text verbatim; chain needs the previous round posted. `podman run -i ... bash -s < script` (a bind mount hits SELinux).

**Left:** on the owner's arm word run `fabric-pr arm --basis "the owner's word: arm 554" 554` after checks are green, then tell fabric-coordinator it merged.

*Anchors: `tools/fabric/provisioning/host_platform.py::ALMALINUX`, `tools/fabric/provisioning/host_platform.py::split_missing`*

*Observed 2026-11-11 (python-dev)*
