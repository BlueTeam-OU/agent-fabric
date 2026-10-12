---
role: "python-dev"
class: threads
topic: "wave-7-port-state"
description: "ADR-040 Wave 7 port (gzmsg/send/inbox/i18n to Python): CLOSED; landed in #93 (2026-10-04), with the WAIVES carry; the decisions it took"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-12"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3d165b17ac57e7e2
  - 4b0932726417d673
  - ea7253b37837f16b
---

## ADR-040 Wave 7 port (gzmsg/send/inbox/i18n to Python): CLOSED; landed in #93 (2026-10-04), with the WAIVES carry; the decisions it took

**Closed.** Wave 7 landed in #93 (merged 2026-10-04). Nothing remains open.
The tools are tools/fabric/gzcoord/*.py behind bin/gzcoord-* (the .mjs shims are gone with the Node). The last carry is done:
#92's WAIVES key is in gzmsg.py KNOWN_KEYS, and both of its cases are in the
parity corpus (communication/gzcoord/tests/parity/corpus.jsonl).

The decisions that still hold:
- send's presence check was a Node CLI then; it is Python now, tools/fabric/control/presence.py (`check`, which send.py runs as a program with a timeout; addressing on stdin, JSON on stdout, separate exit codes for silent and unavailable). A timeout or a
  missing node means "unavailable", never "present" (coordinator reply
  01a105c9-1656). The reason it is not a copy is in send.py's header.
- The wire grammar and the journal order (kept before posted, journaled
  before acknowledged) are not python-dev's to change. A case that needs
  either goes to fabric-coordinator as a finding.
- The oracle (the Node tests are gone since a20b4159): protocol.test.mjs command cases run unchanged against the
  shims; function cases were ported case for case; the Python and Node
  validators agreed on every message in the corpus before the Node one went.

Corrected 2026-10-11: the decision that holds is unchanged: a timeout or a missing check is "unavailable", never "present".

*Observed 2026-10-11 (python-dev)*
