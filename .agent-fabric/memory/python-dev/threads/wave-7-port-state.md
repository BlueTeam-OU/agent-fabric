---
role: "python-dev"
class: threads
topic: "wave-7-port-state"
description: "ADR-040 Wave 7 port (gzmsg/send/inbox/i18n to Python) — LANDED in #93 (2026-10-04); the decisions it took (presence via a Node CLI, the oracle rules)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ea7253b37837f16b
---

## ADR-040 Wave 7 port (gzmsg/send/inbox/i18n to Python) — LANDED in #93 (2026-10-04); the decisions it took (presence via a Node CLI, the oracle rules)

**Landed:** #93 merged 2026-10-04T13:24Z, with four review rounds folded in. The branches are deleted. What follows is the record of how it was done; the tree is the fact now.


Wave 7 (job j10, request 01a10429-4b54 from fabric-coordinator develop-qzapp/user), as of 2026-10-04:

- Split done: runtime/control/gzcoord.mjs (ad9cb7f) folded into #91 with the search server's line (7bd41f94, coordinator's commit).
- Port branch: develop-qzapp/python-dev-01/for/user/wave-7-port, worktree ~/projects/agent-fabric-wave-7-port, based at 7bd41f94 (inside #91). First commit 62e47ec (#91 review P3: the fence test covers all runtime/*.mjs and every import form), already folded into #91. The port goes in the PR after #91.
- Decision (coordinator, reply 01a105c9-1656, 2026-10-04): send's presence check stays Node — runtime/control/presence.mjs gains a CLI (addressing on stdin, JSON on stdout, distinct exit codes for silent/unavailable), registry reads inside it; the Python send runs it with a timeout; timeout or missing node = "unavailable", never present. Record "why not a copy" in the port module's header.
- Not mine to change: wire grammar; journal order (kept before posted, journaled before acknowledged) — a case needing either is a finding to the coordinator.
- Oracle: protocol.test.mjs command cases unchanged against the .mjs shims; function cases ported case for case; both validators agree on every message the suite holds before the Node one goes.
- Port detail: i18n fill() uses JS String(); Python needs a JS-stringify helper (bool -> true/false, int floats without .0).

Progress 2026-10-04 (port branch, local, not yet pushed): 10 work commits on a05c9ca (main after #91) —
tools/fabric/gzcoord/{paths,jsvalues,i18n,gzmsg,_widths,inbox,send,run}.py; presence.mjs `check` CLI;
tests/test_gzcoord_{protocol,i18n,parity}.py + tests/test_presence_cli.py; the switch (1373200): .mjs
are shims via scripts/python.mjs (spawn fabric-python -I run.py, forward TERM/INT/HUP, child has
PR_SET_PDEATHSIG), i18n.mjs/paths.mjs deleted, JS suites keep 33 command cases unchanged and green.
Parity corpus: communication/gzcoord/tests/parity/corpus.jsonl, 520 Node verdicts recorded with the hook
in 9e7b195 (now deleted); Python agrees on all. Left: mutation round (runner in scratchpad), full suite,
push, tell the coordinator.
Pitfalls hit: Node `??` treats "" as set (paths, XDG_STATE_HOME); JS Number(undefined)=NaN vs a missing
seq; a result dict built before a pause; key scan regex needs `t("key"` literally (no `(t or en())(`).

Delivered 2026-10-04: port pushed at 999e7d7 (10 work commits on a05c9ca), handed to the coordinator
(reply 01a1062e-fb19); full suite green, 17 mutations caught. Waiting: the coordinator's fold and the
blind review; findings on these hunks come back to me.


To do when merging main after #92 merges: #92 adds WAIVES to gzmsg.mjs KNOWN_KEYS (SPEC §7.5). Carry it into tools/fabric/gzcoord/gzmsg.py KNOWN_KEYS and add the case to the parity corpus (the coordinator, reply 01a10642-3d31).

*Observed 2026-10-04 (python-dev)*
