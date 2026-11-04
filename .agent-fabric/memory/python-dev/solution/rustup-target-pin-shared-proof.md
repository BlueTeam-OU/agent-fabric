---
role: "python-dev"
class: solution
topic: "rustup-target-pin-shared-proof"
description: "rustup-target install pin (j135, #317) — check and install share one proof function so they cannot disagree; whole-line match; unverified toolchain fetch"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6cecf8f07aead6bb
---

## rustup-target install pin (j135, #317) — check and install share one proof function so they cannot disagree; whole-line match; unverified toolchain fetch

The registry install-pin kind `rustup-target` (toolchain, target) lives in `tools/fabric/tools_install.py`; `tools_check.target_verdict` calls `tools_install.target_proves`, the same function the installer uses to decide `current`, so fabric-tools and fabric-tools --install give one answer per account. The target is matched as a whole stripped line of `rustup target list --installed --toolchain <t>`: a fake rustup listing `aarch64-linux-androideabi` as decoy is what makes the substring mutation fail (the fake's list must exit 0, or the mutation survives on the exit code instead). The program PATH is the fixed `program_env` one, so a rustup only on the session PATH reads as missing.

**Why:** the review's P2/P3 were a proof mismatch and an environment split between check and install; unifying them fixed the class.
**How to apply:** a new pin kind that has a proof gets one proof function both paths call. Not verified: whether `rustup target add --toolchain X` fetches a toolchain not yet installed (no network here), so the rustup pin is installed first on each account.

*Anchors: `tools/fabric/tools_install.py::target_proves`, `tools/fabric/tools_check.py::target_verdict`*

*Observed 2026-10-19 (python-dev)*
