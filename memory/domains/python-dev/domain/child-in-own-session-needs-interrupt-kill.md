---
role: "python-dev"
class: domain
topic: "child-in-own-session-needs-interrupt-kill"
description: "start_new_session for a timeout group-kill strands the child on Ctrl-C; catch BaseException, kill the group, re-raise; test aliveness via /proc state (zombies under CI pid 1); a half-made venv poisons the next run"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 50ee406413a5d790
---

## start_new_session for a timeout group-kill strands the child on Ctrl-C; catch BaseException, kill the group, re-raise; test aliveness via /proc state (zombies under CI pid 1); a half-made venv poisons the next run

Giving a subprocess its own session so a timeout can `killpg` it (j134, tools/fabric/langid_install.py `quiet`) moves it out of the terminal's foreground group: Ctrl-C then reaches only the parent and pip keeps building. Catch `BaseException` around the wait, kill the group, wait, re-raise unless it was the timeout; print one line and exit 130 in main.

**Why:** found in the round-2 blind review of #314 (reproduced by SIGINT to the group). The same change made platform-smoke red: a test's "grandchild is dead" via `kill -0` lies under a non-reaping container pid 1 (zombie stays); read `/proc/<pid>/stat` state after the last `)` and treat Z as dead. Control reproduced in a debian container with podman.

**How to apply:** a mutation test that drops `killpg` hangs for the child's sleep (300 s): run mutants under `timeout -s KILL` and clean orphans by pid. A venv killed midway has bin/python but no bin/pip, so "python exists" idempotence checks fail later for a false reason: remove what this run started (only if it did not pre-exist, else you delete the user's files — the P3 #314 carried). See [[live-run-finds-what-fakes-miss-j132]], [[bounded-subprocess-three-seams]].

*References: bounded-subprocess-three-seams, live-run-finds-what-fakes-miss-j132*

*Observed 2026-10-19 (python-dev)*
