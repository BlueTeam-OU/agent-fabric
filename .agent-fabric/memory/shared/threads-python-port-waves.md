---
role: shared
class: threads
topic: "python-port-waves"
description: "owner-approved plan (2026-09-29) to port the fabric's ~10.5k lines of production bash to Python in waves; jobs j3–j9; ADR-040 in Wave 0"
tier: 2
knowledge_scope: full
shared_with:
  - "fabric-coordinator"
  - "python-dev"
distilled_at: "2026-10-01"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 92644fce5488ec2b
---

## owner-approved plan (2026-09-29) to port the fabric's ~10.5k lines of production bash to Python in waves; jobs j3–j9; ADR-040 in Wave 0

The owner approved on 2026-09-29 the plan in `~/.claude/plans/iridescent-splashing-acorn.md`: "Python as the fabric's implementation language".

**Order:**
1. Finish the current branch.
2. PR B, removing Doppler (j3). It shrinks the port by ~1,000 lines: `enroll.sh` and the Doppler parts are deleted, not ported.
3. Wave 0 (j4): `tools/fabric/gh.py` and `git.py`; ADR-040 "Python above 150 lines", accepted by the owner at its merge; `policies/bash-allowlist.json`; a lint rule that refuses bash over 150 lines outside the allowlist, which only shrinks.
4. The ports:
   - Wave 1 (j5): the GitHub toolkit, commit-class first and pr-gate last;
   - Wave 2 (j6): the guards, with a hook-latency live check;
   - Wave 3 (j7): fabric-status, fabric-branches, fabric-lease, query.sh;
   - Wave 4 (j8): the launcher alone, `--print` byte-identical;
   - Wave 5 (j9): the provisioning decision logic, with a container run.

**Invariants of the method:**
- The script's path stays, as a shim running `/usr/bin/python3`.
- `runtime/github/commit-class.sh` is SOURCED, so its shim defines shell functions that call Python; it is not an exec shim.
- The unchanged bash test is the parity oracle.
- The "why" comments move verbatim.
- The bash implementation is deleted in the same PR.
- gzapp's and InterWeave's `tools/gh/*` are the projects' own code, devex-tooling's lane: each is offered a forwarder, never edited from here. (Verified 2026-10-01: gzapp's tools/gh/pr-gate.sh and commit-class.sh are already forwarders — no diverged copies left.)

Progress: PR B #69, Wave 0 #70, Wave 1 #71 (49d61f2, 2026-10-01) merged and distributed; devex-tooling told (seq 9863). Lessons from Wave 1: a port read stdin before its arguments and hung --help (read the body only once argv needs it); Python's SIGPIPE default is ignore, never restore SIG_DFL (it skips finally); run the original bash beside the port over the oracle's scenarios (a differential), and mutate each key behaviour — the oracle missed band edges and shadowed checks; ADR-040 rule 5 now lets a mock learn gh.py's transport and a source-reading case read the module. Wave 2 #72 (0d84041, 2026-10-01) merged and distributed; devex-tooling told what a fabric-ref bump needs. Lessons: Python's `\s` differs from Oniguruma's in U+001C-U+001F (a guard's pattern must say whose whitespace it means); a dispatch-hook shim must not exec — the harness reads a failed hook as an allow; tests that call a guard in-process must strip GITHUB_*/AGENT_FABRIC_* ([[run-suites-as-ci-before-push]]); under a launch the Python dispatch guard is faster than the bash. Next: Wave 3 (j7), fabric-status, fabric-branches, fabric-lease, query.sh.

Related: [[prefer-python-over-shell]], [[agent-owned-secrets-plan]].

Wave 5 must provision Python itself (owner, 2026-10-01): the provisioning logic cannot be the thing that installs its own interpreter. Today platform/detect.sh only checks `command -v python3` and names a missing package; it checks neither /usr/bin/python3 (the path every shim runs) nor ADR-040's 3.12 floor (a Debian 12 template ships 3.11). So Wave 5 keeps a bash step-runner FIRST, builtins and the package manager only: check /usr/bin/python3 and its version, install or upgrade per platform profile, refuse with one clear line otherwise; only then hand off to the Python decision logic. Prove it in containers on the OLDEST image each platform profile supports. Ties into the generic-client provisioning thread in [[next-fabric-branch-queue]]: decide whether a host below 3.12 gets a newer Python installed or is refused.

DECIDED (owner, 2026-10-01): the fleet runs ONE pinned Python, 3.13 (the current patch release at the time), as Wave 5's FIRST step. Shape agreed: runtime/python.json pins version + per-arch URL + sha256 of a relocatable python-build-standalone build; installed once per host under /usr/local/lib/agent-fabric/python-<version>/ (persists on a Qubes AppVM) with a stable /usr/local/bin/fabric-python link; shims call fabric-python, not /usr/bin/python3, and refuse or ask with a clear line when it is missing; a bash step-runner (curl, tar, sha256sum only) verifies and installs it; `fabric-ctl all upgrade python` moves it, serialized on the host lease like upgrade claude; CI pinned to the same version; recorded as an ADR-040 amendment accepted by the merge. Wave 4 (the launcher) comes before it.

*References: agent-owned-secrets-plan, next-fabric-branch-queue, prefer-python-over-shell, run-suites-as-ci-before-push*

*Observed 2026-09-29 (fabric-coordinator)*
