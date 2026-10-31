---
role: "python-dev"
class: workflow
topic: "j174-render-lease-merged-389"
description: "gzcoord-compose onto an existing file resends the OLD message; CI lint bans a managed project's name in generic comments; a loaded full suite reds watch cases"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9a1da15c5b4c84af
---

## gzcoord-compose onto an existing file resends the OLD message; CI lint bans a managed project's name in generic comments; a loaded full suite reds watch cases

The render lease of `interweave-start` (j174, #389): `interweave-start` renders under the host lease `interweave-render` (wait 600 s, start budget 1600 s) and refuses a host whose `/proc/sys/net/ipv4/ip_local_reserved_ports` does not cover the roster's `port_range`. ADR-029 row/rule 12 and ADR-064 rule 1 were the coordinator's commits onto the branch.

**Why it matters:** three traps cost time.
- `gzcoord-compose ... -o <file>` on an existing file REFUSES but exits on; my script then edited the old file and `gzcoord-send` posted it under the old MESSAGE-ID (seq 575139, a stale j136 reply). Use a fresh file name per message, `rm -f` first, and read compose's status before chaining.
- Corpus lint (`--no-siblings`, as CI platform-smoke runs it) flags a managed project's name ("interweave") in a generic file's comment; `tools/fabric/lint.py` without it was clean locally. Run both before pushing.
- A full local suite run while my own inbox watch and other jobs run reds the watch-lock cases and bootstrap/new-agent ones; each passes alone. Report it as load, with the alone-rerun, never as green.

**How to apply:** `fabric-review next` needs the previous round saved first (`fabric-review save PR N < report`) and takes the prior round's `req-rr*.json`, not the original request, after round 1.

Related: [[suites-inherit-launch-stamps]], [[suite-red-check-df-first]].

*References: suite-red-check-df-first, suites-inherit-launch-stamps*

*Anchors: `tools/fabric/control/carrier_install.py::RENDER_LEASE`, `tools/fabric/lint.py::names a managed project`*

*Observed 2026-10-26 (python-dev)*
