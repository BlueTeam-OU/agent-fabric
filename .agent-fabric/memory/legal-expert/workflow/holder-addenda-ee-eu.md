---
role: "legal-expert"
class: workflow
topic: "holder-addenda-ee-eu"
description: "Where legal-expert-ee-eu's Estonia/EU specifics live after ADR-060 (holder addenda), and their state"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "legal-expert-ee-eu"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b6f29b238b64b176
---

## Where legal-expert-ee-eu's Estonia/EU specifics live after ADR-060 (holder addenda), and their state

Under agent-fabric ADR-060, the Estonian/EU specifics of the legal-expert role move from the shared charter and brief into this holder's own charter-addendum.md and brief-addendum.md, installed by fabric-coordinator into the private store (settings/roles/legal-expert/); never written there by the holder. Drafted 2026-10-17 (validate_set clean, against main 8a1f0c36), sent for review in REPLY 01a149d6-... thread; installed by store commit a2734ff (owner approved 2026-10-17); read at launch from 2026-10-17 (fabric-status "addenda store a2734ffd4d06 addenda commit a2734ffd4d06"; launch-prompt.md order: charter, charter addendum, brief, brief addendum), confirmed in REPLY 01a149de-a0a9 to the owner (job j7). Two points in them were not read from source that session: Riigi Teataja English translations non-authoritative; EUR-Lex consolidated versions documentation only. See [[official-text-channels]].

Stage 5 (job j8, 2026-10-17): I drafted the jurisdiction-free shared charter and brief; writing into a host scratch path was refused by my auto-mode check ([Modify Shared Resources]), so the coordinator took them as one REPLY per file with sha256 (verified in fabric-history). From then on the Estonia/EU text exists only in my addenda.

Re-issue (job j10, 2026-10-18): shared texts final at e256eb04 (body digests charter 6888709e…, brief 39503ea9…, computed by tools/fabric/addenda_check.body_digest = sha256 of text without frontmatter). I re-issued both addenda with only against_digest changed (charter a7e02328…, brief ae314885…), sent by message (REPLY 01a14cd6-b394, -b992); hand-offs into a host scratch path go by message since my write there is refused.

*References: official-text-channels*

*Observed 2026-10-18 (legal-expert)*
