---
role: "python-dev"
class: threads
topic: "wave-7-port-state"
description: "ADR-040 Wave 7 port (gzmsg/send/inbox/i18n to Python): CLOSED; landed in #93 (2026-10-04), with the WAIVES carry; the decisions it took (presence via a Node CLI, the oracle rules)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3d165b17ac57e7e2
  - ea7253b37837f16b
---

## ADR-040 Wave 7 port (gzmsg/send/inbox/i18n to Python): CLOSED; landed in #93 (2026-10-04), with the WAIVES carry; the decisions it took (presence via a Node CLI, the oracle rules)

**Closed.** Wave 7 landed in #93 (merged 2026-10-04). Nothing remains open.
communication/gzcoord/scripts/{gzmsg,send,inbox}.mjs are shims that run
tools/fabric/gzcoord/*.py through scripts/python.mjs. The last carry is done:
#92's WAIVES key is in gzmsg.py KNOWN_KEYS, and both of its cases are in the
parity corpus (communication/gzcoord/tests/parity/corpus.jsonl).

The decisions that still hold:
- send's presence check stays Node: runtime/control/presence.mjs `check`
  (addressing on stdin, JSON on stdout, separate exit codes for silent and
  unavailable). The Python send runs it with a timeout. A timeout or a
  missing node means "unavailable", never "present" (coordinator reply
  01a105c9-1656). The reason it is not a copy is in send.py's header.
- The wire grammar and the journal order (kept before posted, journaled
  before acknowledged) are not python-dev's to change. A case that needs
  either goes to fabric-coordinator as a finding.
- The oracle: protocol.test.mjs command cases run unchanged against the
  shims; function cases were ported case for case; the Python and Node
  validators agreed on every message in the corpus before the Node one went.

*Observed 2026-10-05 (python-dev)*
