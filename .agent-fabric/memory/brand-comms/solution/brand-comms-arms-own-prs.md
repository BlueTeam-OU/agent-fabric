---
role: "brand-comms"
class: solution
topic: "brand-comms-arms-own-prs"
description: "In blueteam.brand, blueteam.ee, gzapi.brand, gzapi.ge and gzapp.decks, brand-comms arms its own PRs at 1 work commit once the head is reviewed; boundary paths still need 8 or the owner's word."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 13f789c05117248c
---

## In blueteam.brand, blueteam.ee, gzapi.brand, gzapi.ge and gzapp.decks, brand-comms arms its own PRs at 1 work commit once the head is reviewed; boundary paths still need 8 or the owner's word.

Since 2026-10-19 (the owner's decision), a PR in the five brand
repositories can arm at 1 work commit, without anyone's word, if every
commit on it carries `Fabric-Role: brand-comms`. Other roles still need
8. The PR still needs a posted review of its head and no open thread.
blueteam.brand is now **direct**, not owner-only, so `fabric-pr arm`
works there too.

Exception, until fabric-coordinator removes it from the projects'
arm.json (the owner has asked for that): a **boundary** change still
needs 8 work commits or the owner's word in `--basis`. Boundary
includes `.claude/`, `brand/tokens.css` and the fonts in blueteam.brand.
blueteam.brand#5 (`.claude/settings.json`) was armed and merged on the
owner's "arm 5".

**How to apply:** review the head, then run `fabric-pr arm <n> --dry-run`.
It states the count rule that applies. Arm without asking unless it
says "on the owner's word". In a direct repository with no CI check,
the arm merges on the review alone.

*Anchors: `projects/blueteam.brand/integration/gh/arm.json::boundary`*

*Observed 2026-10-19 (brand-comms)*
