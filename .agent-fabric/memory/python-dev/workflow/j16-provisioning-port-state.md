---
role: "python-dev"
class: workflow
topic: "j16-provisioning-port-state"
description: "j16 provisioning off shell — DELIVERED: #156 merged 9a731b31; what stayed shell, what is open, lessons"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8e452ec71612b2bc
---

## j16 provisioning off shell — DELIVERED: #156 merged 9a731b31; what stayed shell, what is open, lessons

#156 (14 work, 2 fix) merged 2026-10-10 as 9a731b31, armed by me at the review gate (>= 8 work).
Open: the real throwaway-login run waits on the coordinator's test mode with the owner (dry run was ok);
read the output back when sent. Stayed shell on purpose: new-agent(.worker).sh, moveto/install.sh,
platform/*.sh (CI bare container + ssh-operator.sh; parity test), qubes boot rc, store-enroll.sh.
Carried risk: per-call timeouts kill sudo, not the command under it (bounded.run_bounded not used in worker).

**Lessons:**
- An old shell oracle can pass with real mutations in (fakes accept any argv): plant mutations, add recorder-based unit tests.
- Push: git -c credential.helper='!gh auth git-credential' push.
- Short TMPDIR for the whole suite (AF_UNIX path length); scratch outside the tree.
- capture_output + stderr= raises ValueError: a path no suite reached (host-check) crashed finish.
- CodeQL moves old alerts to "new" when code is split; coordinator dismisses.
- gzcoord login of the coordinator is develop-qzapp/user.

*Observed 2026-10-10 (python-dev)*
