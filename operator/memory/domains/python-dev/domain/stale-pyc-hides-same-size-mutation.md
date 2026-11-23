---
role: "python-dev"
class: domain
topic: "stale-pyc-hides-same-size-mutation"
description: "a mutation that keeps the file size (e.g. [:8] to [:6]) within the same second is read from the old .pyc; run mutants with PYTHONDONTWRITEBYTECODE=1 and clear __pycache__ after"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 341b7581fe14d80c
---

## a mutation that keeps the file size (e.g. [:8] to [:6]) within the same second is read from the old .pyc; run mutants with PYTHONDONTWRITEBYTECODE=1 and clear __pycache__ after

In j197 (ADR-043 managed status) a sha8 mutant "survived" and then my
fixed test failed on correct source: the mutated `status.py` had been
compiled to a .pyc whose recorded mtime and size matched the restored
file, so Python kept running `[:6]`.

**Why:** pyc invalidation is mtime plus size; a same-length edit in the
same second is invisible to it.

**How to apply:** run the mutation loop with `PYTHONDONTWRITEBYTECODE=1`
and delete `__pycache__` under tools/ and tests/ after it. A survivor
or a red test on source you just restored is a pyc suspect first. See
[[test-port-by-mutation-parity]].

Also from j197: the request's base commit may not be your branch's tip
(the new branch started at main); `git reset --hard <sha>` on a branch
with no commits of its own is the right move after checking
`git log origin/main..HEAD` is empty. `fabric-jobs sweep` closes a job
only on `owner/repo#N` evidence, so `deliver` the merged PR by that name.

*References: test-port-by-mutation-parity*

*Observed 2026-11-01 (python-dev)*
