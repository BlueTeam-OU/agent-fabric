---
role: "python-dev"
class: solution
topic: "j252-new-agent-dedup-merged-636"
description: "j252 #636 — new_agent sudo dedups saved only 2% CPU; where the cost really is; the coordinator's no's"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f7619f05e4bbc992
---

## j252 #636 — new_agent sudo dedups saved only 2% CPU; where the cost really is; the coordinator's no's

#636 merged (4 work, 1 fix): worker.py reads home/group once per phase, step 2 is one `readlink -e` (a dangling link is not a claude; the test needs the target's directory to exist or `-f` also fails), and a present clone's origin+pushurl is one `git config --null --get-regexp`.

Measured: a fresh account run is 53 sudo calls, a re-run 55, but dropping ~5 of them cut only ~2% of test_new_agent_cli group-2 CPU; the cost is ~143 pinned-python starts and ~944 bash. test_persist_host_settings is 2 s alone (its 60 s is load); test_job_copy_guard is 304 hook runs at ~85 ms, ~50 ms the guard's imports (coordinator's, queued).

**Why:** the coordinator declined batching step 10's seven read-backs (a hang would lose all; per-check 120 s bounds make a hang legible) and in-process guard cases (the suite drives the forwarder on purpose). **How to apply:** do not re-propose either; measure CPU (strace -f -e execve) before counting sudo calls as the cost; fabric-pr arm below the minimum worked on the coordinator's message id in the basis.

*Anchors: `tools/fabric/provisioning/worker.py::readlink`, `tools/fabric/provisioning/worker.py::get-regexp`*

*Observed 2026-11-17 (python-dev)*
