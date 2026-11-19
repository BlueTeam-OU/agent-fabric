---
role: "fabric-coordinator"
class: workflow
topic: "codex-review-never-blocks"
description: "owner 2026-11-12: Codex review never blocks an arm; landed #577 + ADR-055 amendment 11-13 (j809): probe first, any failure posts the marker, exit 1 only for caller errors"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6789f88234b68328
---

## owner 2026-11-12: Codex review never blocks an arm; landed #577 + ADR-055 amendment 11-13 (j809): probe first, any failure posts the marker, exit 1 only for caller errors

The owner decided on 2026-11-12, after #575's two 20-minute Codex timeouts posted nothing and the owner saw Codex unavailable at API level:
- Codex starts only after a cheap API call shows the gateway is reachable and the allowance is not spent.
- If Codex cannot be launched or cannot finish for any reason, it must not block the arm.

Landed 2026-11-13: #577 (python-dev-01, j232; merged 1282189a, distributed with 48127a81) makes `tools/fabric/review_codex.py` probe first, bounded by PROBE_TIMEOUT_S = 20 s. Every failure to launch or finish exits 3 and posts the marker with its reason: capacity, allowance, unreachable, probe-failed, probe-timeout, timeout, crash, failed, gateway, binary-missing. Exit 1 posts nothing; it remains for settings, routing, the request, a refused sign-in, and a head that moved. ADR-055 rule 8 was amended on 2026-11-13 (commit 59aea288, j809). An audit read all 14 repos/*.json in both settings repos: none names codex, so all of them take the fleet default additional_reviews=[codex]. Live positive read-back on 2026-11-13: `fabric-review --engine codex 593 <req> --gateway chatgpt` on head 2c640898 passed the probe against the live backend and ran codex to the end. It then refused at exit 1, posting nothing, because #593 had moved to 16160e93 — the correct caller-error path. Without --gateway it refuses at once (exit 1): AGENT_FABRIC_CODEX_BASE_URL/KEY are not set in a session. Still unobserved live: a probe failure or a spent allowance producing the marker. A docs/live-checks record of this is still owed (j855).

**Why:** the owner's call. An engine that was down cost hours on #575, while the review class's clean review was already in.
**How to apply:** a codex run that ends with no marker now points to a refusal (exit 1) or a defect, not to normal unavailability. Read its stderr before arming on "codex: absent". Related: [[codex-reviews]], [[owner-arm-word-575]].

*References: codex-reviews, owner-arm-word-575*

*Anchors: `tools/fabric/review_codex.py::UNAVAILABLE_MARKER`*

*Observed 2026-11-12 (fabric-coordinator)*
