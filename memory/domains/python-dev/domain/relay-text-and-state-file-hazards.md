---
role: "python-dev"
class: domain
topic: "relay-text-and-state-file-hazards"
description: "writing a record from GZCoord relay text or appending under the agent lock - lone surrogates, FIFOs, and what a reviewer leaves in TMPDIR"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 18dfc115e43e7707
---

## writing a record from GZCoord relay text or appending under the agent lock - lone surrogates, FIFOs, and what a reviewer leaves in TMPDIR

Three hazards found in the j34 supplier review (journal-bypass.jsonl,
tools/fabric/gzcoord/bypass.py, 2026-10-05):

1. Relay JSON may carry a lone surrogate (`\ud800` is valid JSON, and
   json.loads accepts it). Then `text.encode()` and
   `json.dumps(ensure_ascii=False).encode()` raise UnicodeEncodeError. In
   inbox.py that error escapes the journal hook's hold path and is reported
   as "relay unreachable"; in --follow it repeats as "relay down" forever.
   Hash with `encode("utf-8", "surrogatepass")`, which gives the same bytes
   for any valid text, and write ASCII JSON. A test needs the surrogate in a
   FIELD the line carries (MESSAGE-ID), not only in the body: a body the line
   never contains cannot catch the ensure_ascii mutation.
2. `os.open(O_WRONLY)` on a FIFO blocks. Done under identity.agent_lock, it
   stalls every state write of the login. O_NONBLOCK makes it fail with
   ENXIO when nothing reads. A directory gives EISDIR, a socket ENXIO, a
   symlink ELOOP (with O_NOFOLLOW). So an S_ISREG check after the open was
   unreachable for a non-root writer, and I dropped it as untestable.
3. The review class can leave scratch in my TMPDIR when it reproduces a
   finding with the suites' fixtures (P.cmd_env: ws-, home-, send-store-,
   plus its own state dir). Before blaming the suite, run each suspect test
   with its own `TMPDIR=<empty dir>`, compare the timestamps with the
   review's, then remove what is mine and say how much.

**Why:** the first review's P2 was the surrogate; the FIFO was its unproven
risk; the leftovers looked like a suite leak until isolated.
**How to apply:** any code that hashes or serialises relay text, or opens a
path under the agent's state directory while holding its lock. See
[[python-defaults-that-differ-from-node]] and
[[gzcoord-tests-reach-the-host-workspace]].

*References: gzcoord-tests-reach-the-host-workspace, python-defaults-that-differ-from-node*

*Observed 2026-10-05 (python-dev)*
