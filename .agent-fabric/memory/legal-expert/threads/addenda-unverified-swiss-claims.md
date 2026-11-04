---
role: "legal-expert"
class: threads
topic: "addenda-unverified-swiss-claims"
description: "My ADR-060 holder addenda rest on three Swiss-law statements not yet read from Fedlex; verify them and correct the addendum if needed"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "legal-expert-ch"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 04debab3c8b56672
---

## My ADR-060 holder addenda rest on three Swiss-law statements not yet read from Fedlex; verify them and correct the addendum if needed

On 2026-10-17 I drafted my holder addenda (charter-addendum.md, brief-addendum.md) in a host scratch path, against main 8a1f0c36, with validate_set clean. I sent fabric-coordinator a REPLY (01a149d8-3819-7641-ae86-9d82b6859f27) The owner approved them and fabric-coordinator installed them as written in my store at commit 960a3b7 (2026-10-17); I checked the hashes against my drafts. Next: relaunch and report what the launch read (job j4). Three statements in them come from my field knowledge and were not read from source, because Fedlex needs a JS browser and moli was missing ([[fedlex-needs-js-browser]]):
1. The Official Compilation (AS) is the authoritative text, not the Systematic Collection (SR). Source to check: the Publications Act.
2. Civil Code Art. 1 paras 2-3: custom, then the judge's own rule, guided by established doctrine and tradition.
3. Under the FADP, processing needs a justification only where it infringes personality unlawfully.
Open: verify all three once Fedlex is readable, and send any correction to fabric-coordinator. A changed addendum needs a reinstall that the parent signs; I never write settings/roles/ myself.

Also fixed while drafting: a Swiss lawyer registered in one cantonal register may appear anywhere in Switzerland (free movement under the Lawyers Act), so counsel is "admitted to practise in Switzerland", not admitted in the forum's canton. This too is unverified this session.

4. (added 2026-10-18, j6) brief addendum "The EU at the border" says a bilateral-agreement rule "binds through the Swiss act". Swiss treaty practice may make a self-executing provision of a bilateral agreement apply directly (Cst. Art. 5(4)/190: unverified). That is imprecise under the shared charter as of 66eed380. I told fabric-coordinator in REPLY 01a14cd6. Proposing a one-line fix to the owner waits on verification.

*References: fedlex-needs-js-browser*

*Observed 2026-10-17 (legal-expert)*
