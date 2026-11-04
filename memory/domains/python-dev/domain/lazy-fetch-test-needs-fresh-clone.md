---
role: "python-dev"
class: domain
topic: "lazy-fetch-test-needs-fresh-clone"
description: "Testing that git never lazy-fetches in a promisor clone — fresh clone per trial, which filters miss what, how to count fetch children"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0461aeb1a80fcf2b
---

## Testing that git never lazy-fetches in a promisor clone — fresh clone per trial, which filters miss what, how to count fetch children

A lazy fetch fills the clone it runs in, so a positive control run first makes the guarded trial pass vacuously: clone fresh per trial.
Blobless (`--filter=blob:none`) misses the blobs an inexact rename needs for `diff --name-only`; commits are missing only in a `--filter=tree:0 --depth=1` clone (ancestor of a commit outside the depth).
Count fetch children from GIT_TRACE lines holding `run_command` and ` fetch`; keep a control showing plain git starts one and a live trace for the guarded run. Prove the argv flag and GIT_NO_LAZY_FETCH separately with a subprocess.run spy (either alone keeps the behaviour green). Create clones before installing the spy. j85, review_coverage.py `_git`, 0f55a094.

*Observed 2026-10-24 (python-dev)*
