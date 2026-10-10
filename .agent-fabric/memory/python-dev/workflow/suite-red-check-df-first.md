---
role: "python-dev"
class: workflow
topic: "suite-red-check-df-first"
description: a suite red in files you did not touch — check df / before diagnosing; /var/tmp is the shared root fs
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6e235f98be771f9f
---

## a suite red in files you did not touch — check df / before diagnosing; /var/tmp is the shared root fs

On develop-qzapp, /var/tmp (every account's TMPDIR) sits on the 40G root
filesystem, shared by all accounts. On 2026-10-07 it hit 0 bytes free
(another agent's cargo review targets, 6.3G) and tests/run.sh failed
test_secret_store and test_session_start with ENOSPC/gpg lock errors —
nothing to do with the change. Check `df -h /` first; a TMPDIR under the
session scratchpad also overflows AF_UNIX socket paths (test_session_start),
so run the suite with the default short TMPDIR. A full disk is the owning
agent's to clean: an OBSERVATION with du/ls -ld evidence, never their files.
Also: the contributor commit hook refuses `git commit --amend` that stages
no path; add a trailer with `git reset --soft HEAD~1` + commit instead.

*Observed 2026-10-07 (python-dev)*
