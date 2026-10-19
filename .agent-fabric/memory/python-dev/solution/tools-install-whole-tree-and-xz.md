---
role: "python-dev"
class: solution
topic: "tools-install-whole-tree-and-xz"
description: "tools_install.py pin shapes after j45 - .tar.xz by url suffix (else gzip), \"whole\": true trees, and why projects/registry.json pins need fabric-coordinator's commit"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5c1eb4199308509f
---

## tools_install.py pin shapes after j45 - .tar.xz by url suffix (else gzip), "whole": true trees, and why projects/registry.json pins need fabric-coordinator's commit

tools/fabric/tools_install.py (j45, branch develop-qzapp/python-dev-04/feat/j45-tools-install-xz): a url path ending .tar.xz is xz, any other is gzip - the old test cases use bare urls with gzip bytes, so refusing an unknown suffix broke the unchanged oracle; the magic bytes must agree or the run fails. A tree pin takes `"whole": true` instead of `members` (Zig 0.16.0: 20,832 entries, 358 MB, files and dirs only, names like `__stddef_null.h`, so the plain-name MEMBER rule cannot apply to archive paths). Unpack is by hand (no extractall); links resolve-checked after the run because a chain of links defeats a per-link lexical check.

**Why:** a registry pin (projects/registry.json) is outside python-dev's authority entry, so a test asserting the pin fails until fabric-coordinator commits the line onto the branch; ask for it in the same message that reports the branch. Real install of zig takes ~59 s (per-file fsync dominates) against control's 5-minute INSTALL_TIMEOUT_MS.

**How to apply:** a mutation that survives means the test never reached the check (the proof failed first, the lexical check caught the chain first): make the fixture reach the check alone.

*Observed 2026-10-18 (python-dev)*
