---
role: "python-dev"
class: solution
topic: "j149-lease-line-noise-group-int-unreproduced"
description: "'no cpu slot (No module named lease)' in test_run output is expected noise; the debian group-INT empty-stdout failure was not reproducible"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 077a2cdeecf6cb3a
---

## 'no cpu slot (No module named lease)' in test_run output is expected noise; the debian group-INT empty-stdout failure was not reproducible

j149 (request from the coordinator, 2026-11-14): tests/test_run.py's debian platform-smoke failure of the case
"a group INT during the python section" (run 43417991778) showed `(130, [], '', 'tests/run.py: no cpu slot (No module
named lease)...')`. The lease line is not the cause: tests/test_run.py `tree()` copies tools/fabric/lease.py only with
`lease=True`, so run.py's take_cpu_slot prints it in every python-section case by design. The real symptom was wholly
empty stdout (runner printed nothing). Not reproduced: 6 full test_run runs under 8 CPU burners and 100 isolated
group-INT trials under 20 burners, all green. Candidate only: run.py end_tree(graceful) KILLs the runner after
KILL_WAIT_S (10 s). The coordinator owns run.py and its harness and wrote the elapsed/KILL diagnostic itself.

**Why:** a lease-import message is a decoy; do not chase it again.
**How to apply:** on a repeat of this red, read the diagnostic the coordinator added before theorising; stress with
burners via a standalone script, and stop burners by pid (a `pkill -f` pattern is refused by the hook).

*Anchors: `tests/run.py::no_cpu_slot`, `tests/run.py::KILL_WAIT_S`*

*Observed 2026-11-14 (python-dev)*
