---
role: "python-dev"
class: solution
topic: "j51-nonce-fence-merged"
description: "Fence untrusted text with an unguessable terminator, not a deny-list of spellings; a security-boundary file under 8 work commits arms only on the owner's word"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0637cdd358f978e9
  - 21a9ab3974e501d1
---

## Fence untrusted text with an unguessable terminator, not a deny-list of spellings; a security-boundary file under 8 work commits arms only on the owner's word

BlueTeam-OU/agent-fabric#291 merged (2 work, 2 fix, 2026-10-17): `session.job_context` ends the request block at `</request-K>`, K = `secrets.token_hex(8)` drawn after the body is read (redrawn if the body holds it), named in the prompt; body kept verbatim, plain `</request` still escaped by `REQUEST_CLOSE`. Checked against origin/main 2026-10-20: `REQUEST_CLOSE` and the token fence are unchanged (the later settle_tmpdir change did not touch them). Re-confirmed 2026-10-20: `launch.py` and `launcher/routing.py` are also security-boundary files (#331, 2 work, refused without the owner's word).

**Why:** j236 asked for "every spelling"; invisible and look-alike characters make that unenumerable.

**How to apply:** fence untrusted text with an unguessable terminator rather than escaping spellings. A test oracle must not reuse the production transform. Under 8 work commits `fabric-pr arm` on a security-boundary change needs the owner's word in the basis, or a fabric-coordinator AUTHORIZES message.

*Anchors: `tools/fabric/launcher/session.py::REQUEST_CLOSE`, `tests/test_launch_job_context.py::fenced`*

*Observed 2026-10-20 (python-dev)*
