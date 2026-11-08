---
role: "python-dev"
class: solution
topic: "j104-installer-minisign-merged"
description: "j104/j449 #442 merged — stdlib minisign check in carrier_install; CodeQL false-positive and security-boundary arm traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 57aa0fc063239c6f
---

## j104/j449 #442 merged — stdlib minisign check in carrier_install; CodeQL false-positive and security-boundary arm traps

#442 (4 work, 2 fix) merged 2026-11-01 at head 83ef3f75: `tools/fabric/control/minisign.py` (RFC 8032 5.1.7 verify, prehashed ED, global signature, `file:<name>` tab field) wired at step 4 of `carrier_install.py`; pin shape checked in `pin_problem`.

**Why:** a security-boundary PR under 8 work commits arms only on the owner's word; the owner's typed "merge 442" in the session went into the `--basis` as "the owner's word" and `fabric-pr arm` accepted it (no AUTHORIZES id needed). CodeQL alert 77 (clear-text-storage on a test signer's public .minisig) stayed red; arm did not refuse on it.

**How to apply:** name test signer fixtures so they do not look like credentials; don't wait on a dismissal if the owner says merge. See [[security-boundary-arm-needs-owner]].

*References: security-boundary-arm-needs-owner*

*Anchors: `tools/fabric/control/minisign.py::verify_file`, `tools/fabric/control/carrier_install.py::fetch_and_unpack`*

*Observed 2026-11-01 (python-dev)*
