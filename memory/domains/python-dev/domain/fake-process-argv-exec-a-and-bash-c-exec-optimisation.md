---
role: "python-dev"
class: domain
topic: "fake-process-argv-exec-a-and-bash-c-exec-optimisation"
description: "Fixtures that fake a process's command line: exec -a puts it all in argv[0]; bash -c 'one cmd' execs and drops its argv"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 23b42b491dd09812
---

## Fixtures that fake a process's command line: exec -a puts it all in argv[0]; bash -c 'one cmd' execs and drops its argv

j128: watch-on-stop and session-start joined /proc cmdline NULs into spaces, so `grep -r "gzcoord-inbox --follow" .` counted as a watch. Fixed by keeping argv a list (branch for/user/watch-on-stop-argv-list). The session-start test faked watches with `exec -a 'node inbox.mjs --follow' sleep 20`, i.e. a whole command line in ONE argv[0]; a list-reading predicate rightly rejects it.

**Why:** a fixture that only works because argv was split on spaces is evidence of the bug, not of the behaviour.
**How to apply:** fake real argv with `exec bash -c 'sleep 20; :' node inbox.mjs --follow`. The trailing `; :` matters: bash -c with a single simple command execs it, replacing the process and its argv. Change such a fixture deliberately and say so in the reply, since the oracle was edited.

*Observed 2026-11-15 (python-dev)*
