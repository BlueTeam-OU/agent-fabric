---
role: "python-dev"
class: solution
topic: "j127-relay-down-probe-delivered"
description: "j127 watch-on-stop relay-down probe delivered as f81b7aaf on a for/user branch; guard traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1336bd91eb05ce7f
---

## j127 watch-on-stop relay-down probe delivered as f81b7aaf on a for/user branch; guard traps

watch-on-stop.py probes the relay (urllib, no proxy, 2 s) only while a fresh relay-down marker stands; any HTTP response lifts the silence, the hook never deletes the marker. Branch develop-qzapp/python-dev-02/for/user/j638-relay-down-probe, head f81b7aaf, full suite green; REPLY sent to the requester.

**Why:** the marker is cleared only by a running watch's relayAnswered, so a relay back after minutes left sessions deaf up to an hour.

**How to apply:** tests must pass `relay_url` to `decide()` or a fresh-marker case would probe the real relay. The Bash guard refuses `git commit` in a command that carries `$HOME`/`$TMPDIR` (it cannot resolve the directory): commit in a bare command, run `env -i ... tests/run.sh` separately.

*Anchors: `runtime/claude-code/hooks/watch-on-stop.py::relay_answers`*

*Observed 2026-11-09 (python-dev)*
