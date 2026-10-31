---
role: "python-dev"
class: solution
topic: "j51-nonce-fence-merged"
description: "Fence untrusted text with an unguessable terminator, not a deny-list of spellings; a security-boundary file under 8 work commits arms only on the owner's word"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0637cdd358f978e9
---

## Fence untrusted text with an unguessable terminator, not a deny-list of spellings; a security-boundary file under 8 work commits arms only on the owner's word

BlueTeam-OU/agent-fabric#291 merged (2 work, 2 fix, 2026-10-17): `session.job_context` ends the request block at `</request-K>`, K = `secrets.token_hex(8)` drawn after the body is read (redrawn if the body holds it), named in the prompt; body kept verbatim, plain `</request` still escaped by `REQUEST_CLOSE`. First try (NFKC + drop Cf, then the escape) was a deny-list: the reviewer listed U+034F, Hangul fillers, U+2800, Cyrillic е, U+2215 as still passing, and the fold rewrote the body (x² to x2).

**Why:** j236 asked for "every spelling"; invisible and look-alike characters make that unenumerable. j199 (test_launch_cli load flake) was already fixed by 391f8a45/c682e380; I only reproduced it (sitecustomize sleeping before every interpreter start, PYTHONPATH, scratch) and dropped a dead sleep(1).

**How to apply:** fence untrusted text with an unguessable terminator rather than escaping spellings. A test oracle must not reuse the production transform. `session.py` counts as a security boundary: under 8 work commits `fabric-pr arm` needs the owner's word in the basis. Also: the review brief refuses a requirement that "names what was fixed" (reword to what must be true); a test named in a requirement is a behaviour, not a mutation. Also #290 (holder-addenda, python-dev-02's validator on for/user/holder-addenda-check): my r2 ReDoS fix to LINK_RE introduced a P1 (stopped at an inner "["); positive controls must include nested link text. See [[j50-addenda-check-delivered]].

*References: j50-addenda-check-delivered*

*Anchors: `tools/fabric/launcher/session.py::REQUEST_CLOSE`, `tests/test_launch_job_context.py::fenced`*

*Observed 2026-10-17 (python-dev)*
